from __future__ import annotations

import json
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.kb_agent import ask, delete_thread, get_thread_messages, iter_ask_events
from src.api.routes_auth import admin_router, router as auth_router
from src.auth.deps import AuthUser, get_client_ip, get_current_user, require_admin, require_kb_admin
from src.auth.store import init_auth_db, seed_default_admin, write_audit_log
from src.ingest.chunking import split_documents
from src.ingest.loaders import SUPPORTED_SUFFIXES, load_file
from src.ingest.pipeline import ingest_files, ingest_raw_dir, iter_ingest_events
from src.kb.registry import (
    create_kb,
    delete_chroma_collection,
    delete_kb,
    ensure_default_kb,
    get_kb,
    get_kb_raw_dir,
    init_kb_db,
    list_kbs,
    migrate_legacy_raw_files,
    update_kb,
)
from src.logging_config import get_logger, setup_logging
from src.rag.retriever import compare_retrieval
from src.rag.store import count_chunks, delete_by_source, get_vectorstore, list_sources
from src.sessions.store import create_thread, get_thread, list_threads

setup_logging()
log = get_logger("qizhi.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_auth_db()
    seed_default_admin()
    init_kb_db()
    default_kb = ensure_default_kb()
    migrate_legacy_raw_files(default_kb)
    log.info("API startup (auth + kb initialized, default_kb=%s)", default_kb.get("kb_id"))
    yield
    log.info("API shutdown")


app = FastAPI(
    title="Enterprise KB Agent",
    description="企业内部员工知识问答智能体 API",
    version="0.3.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    except Exception:
        log.exception("unhandled error path=%s", request.url.path)
        raise
    finally:
        # 健康检查太吵，降为 debug
        elapsed_ms = (time.perf_counter() - started) * 1000
        msg = "%s %s -> %s (%.1fms)" % (
            request.method,
            request.url.path,
            status,
            elapsed_ms,
        )
        if request.url.path == "/health":
            log.debug(msg)
        elif status >= 500:
            log.error(msg)
        elif status >= 400:
            log.warning(msg)
        else:
            log.info(msg)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


class IngestRequest(BaseModel):
    filename: Optional[str] = None
    replace: bool = True


class CreateThreadRequest(BaseModel):
    title: str = "新对话"
    kb_id: Optional[str] = None


class CreateKbRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class UpdateKbRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    description: Optional[str] = Field(None, max_length=500)


class KbItemResponse(BaseModel):
    kb_id: str
    name: str
    description: str
    collection_name: str
    created_at: str
    updated_at: str


class KbListResponse(BaseModel):
    knowledge_bases: list[KbItemResponse]


class KbDetailStatsResponse(BaseModel):
    kb_id: str
    name: str
    total_documents: int
    total_size_bytes: int
    indexed_documents: int
    not_indexed_documents: int
    chunk_count: int


def _ensure_thread_owner(thread_id: str, user_id: str) -> dict:
    row = get_thread(thread_id)
    if not row:
        raise HTTPException(status_code=404, detail="会话不存在")
    if row["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    return row


class PreviewChunk(BaseModel):
    chunk_id: int
    page: int | None = None
    content: str


class RecallHit(BaseModel):
    source: str
    page: int | None = None
    chunk_id: int | None = None
    content: str
    score: float
    score_kind: str = "distance"
    channels: list[str] = Field(default_factory=list)


class RecallLane(BaseModel):
    mode: str
    label: str
    hits: list[RecallHit]


class RecallResponse(BaseModel):
    query: str
    limit: int
    hit_count: int
    hits: list[RecallHit]
    lanes: list[RecallLane] = Field(default_factory=list)
    reranker_ready: bool = False


class KbStatsResponse(BaseModel):
    kb_count: int
    kb_names: list[str]
    total_documents: int
    total_size_bytes: int
    indexed_documents: int
    not_indexed_documents: int
    chunk_count: int
    knowledge_bases: list[KbDetailStatsResponse] = Field(default_factory=list)


def _require_kb(kb_id: str) -> dict:
    row = get_kb(kb_id)
    if not row:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return row


def _default_kb_id() -> str:
    return ensure_default_kb()["kb_id"]


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- 用户问答 / 会话 ----------


@app.get("/api/v1/threads")
def api_list_threads(user: AuthUser = Depends(get_current_user)):
    return {"threads": list_threads(user_id=user.user_id)}


@app.post("/api/v1/threads")
def api_create_thread(
    body: CreateThreadRequest = CreateThreadRequest(),
    user: AuthUser = Depends(get_current_user),
):
    row = create_thread(user_id=user.user_id, title=body.title, kb_id=body.kb_id)
    log.info("thread created id=%s user=%s", row.get("thread_id"), user.user_id)
    return row


@app.get("/api/v1/threads/{thread_id}")
def api_get_thread(thread_id: str, user: AuthUser = Depends(get_current_user)):
    return _ensure_thread_owner(thread_id, user.user_id)


@app.get("/api/v1/threads/{thread_id}/messages")
def api_thread_messages(thread_id: str, user: AuthUser = Depends(get_current_user)):
    _ensure_thread_owner(thread_id, user.user_id)
    return {"thread_id": thread_id, "messages": get_thread_messages(thread_id)}


@app.delete("/api/v1/threads/{thread_id}")
def api_delete_thread(thread_id: str, user: AuthUser = Depends(get_current_user)):
    _ensure_thread_owner(thread_id, user.user_id)
    delete_thread(thread_id)
    log.info("thread deleted id=%s user=%s", thread_id, user.user_id)
    return {"ok": True, "thread_id": thread_id}


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(body: ChatRequest, user: AuthUser = Depends(get_current_user)):
    _ensure_thread_owner(body.thread_id, user.user_id)
    log.info(
        "chat start thread=%s q_len=%s",
        body.thread_id,
        len(body.message),
    )
    try:
        answer = ask(body.message, thread_id=body.thread_id, user_id=user.user_id)
    except Exception as e:  # noqa: BLE001
        log.exception("chat failed thread=%s", body.thread_id)
        raise HTTPException(status_code=500, detail=str(e)) from e
    log.info(
        "chat done thread=%s answer_len=%s",
        body.thread_id,
        len(answer or ""),
    )
    return ChatResponse(answer=answer, thread_id=body.thread_id)


@app.post("/api/v1/chat/stream")
def chat_stream(body: ChatRequest, user: AuthUser = Depends(get_current_user)):
    _ensure_thread_owner(body.thread_id, user.user_id)
    log.info("chat stream start thread=%s q_len=%s", body.thread_id, len(body.message))

    def event_stream():
        for evt in iter_ask_events(
            body.message,
            thread_id=body.thread_id,
            user_id=user.user_id,
        ):
            yield json.dumps(evt, ensure_ascii=False) + "\n"

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- 知识库管理（Admin） ----------


@app.get("/api/v1/admin/kbs", response_model=KbListResponse)
def admin_list_kbs(_admin: AuthUser = Depends(require_kb_admin)):
    rows = list_kbs()
    return {"knowledge_bases": rows}


@app.post("/api/v1/admin/kbs", response_model=KbItemResponse)
def admin_create_kb(
    body: CreateKbRequest,
    admin: AuthUser = Depends(require_kb_admin),
):
    try:
        row = create_kb(name=body.name, description=body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log.info("kb created name=%s by=%s", row["name"], admin.username)
    return row


@app.get("/api/v1/admin/kbs/{kb_id}", response_model=KbItemResponse)
def admin_get_kb(kb_id: str, _admin: AuthUser = Depends(require_kb_admin)):
    return _require_kb(kb_id)


@app.patch("/api/v1/admin/kbs/{kb_id}", response_model=KbItemResponse)
def admin_update_kb(
    kb_id: str,
    body: UpdateKbRequest,
    admin: AuthUser = Depends(require_kb_admin),
):
    _require_kb(kb_id)
    if body.name is None and body.description is None:
        raise HTTPException(status_code=400, detail="请提供 name 或 description")
    try:
        row = update_kb(kb_id, name=body.name, description=body.description)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    log.info("kb updated id=%s name=%s by=%s", kb_id, row["name"], admin.username)
    return row


@app.delete("/api/v1/admin/kbs/{kb_id}")
def admin_delete_kb(kb_id: str, admin: AuthUser = Depends(require_kb_admin)):
    row = _require_kb(kb_id)
    all_kbs = list_kbs()
    if len(all_kbs) <= 1:
        raise HTTPException(status_code=400, detail="至少保留一个知识库")
    delete_chroma_collection(row["collection_name"])
    if not delete_kb(kb_id):
        raise HTTPException(status_code=404, detail="知识库不存在")
    log.info("kb deleted id=%s name=%s by=%s", kb_id, row["name"], admin.username)
    return {"ok": True, "kb_id": kb_id}


@app.get("/api/v1/admin/kbs/{kb_id}/stats", response_model=KbDetailStatsResponse)
def admin_kb_detail_stats(kb_id: str, _admin: AuthUser = Depends(require_kb_admin)):
    row = _require_kb(kb_id)
    return _kb_detail_stats(row)


@app.get("/api/v1/admin/kbs/{kb_id}/recall", response_model=RecallResponse)
def admin_kb_recall(
    kb_id: str,
    query: str,
    limit: int = 10,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    q = (query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="查询词不能为空")
    cap = max(1, min(limit, 50))
    compared = compare_retrieval(q, k=cap, collection_name=row["collection_name"])

    def to_hit(ranked) -> RecallHit:
        meta = ranked.doc.metadata or {}
        chunk_id = meta.get("chunk_id")
        try:
            chunk_id = int(chunk_id) if chunk_id is not None else None
        except (TypeError, ValueError):
            chunk_id = None
        page_val = meta.get("page")
        page = page_val if isinstance(page_val, int) else None
        return RecallHit(
            source=str(meta.get("source") or "未知"),
            page=page,
            chunk_id=chunk_id,
            content=ranked.doc.page_content,
            score=float(ranked.score),
            score_kind=ranked.score_kind,
            channels=list(ranked.channels or []),
        )

    lanes = [
        RecallLane(
            mode=lane["mode"],
            label=lane["label"],
            hits=[to_hit(h) for h in lane["hits"]],
        )
        for lane in compared["lanes"]
    ]
    hits = [to_hit(h) for h in compared["hits"]]
    log.info(
        "recall compare ok kb=%s q_len=%s lanes=%s reranker=%s",
        kb_id,
        len(q),
        [lane.mode for lane in lanes],
        compared["reranker_ready"],
    )
    return RecallResponse(
        query=q,
        limit=cap,
        hit_count=len(hits),
        hits=hits,
        lanes=lanes,
        reranker_ready=bool(compared["reranker_ready"]),
    )


@app.get("/api/v1/admin/kbs/{kb_id}/documents")
def admin_kb_documents(
    kb_id: str,
    query: str = "",
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    return _documents_payload(row, query)


@app.get("/api/v1/admin/recall", response_model=RecallResponse)
def admin_recall(
    query: str,
    limit: int = 10,
    kb_id: str | None = None,
    _admin: AuthUser = Depends(require_kb_admin),
):
    """召回测试（兼容旧路径，默认使用指定或默认知识库）。"""
    target_id = kb_id or _default_kb_id()
    return admin_kb_recall(target_id, query, limit, _admin)


@app.get("/api/v1/admin/documents")
def admin_documents(
    query: str = "",
    kb_id: str | None = None,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return _documents_payload(row, query)


def _documents_payload(kb_row: dict, query: str = "") -> dict:
    raw_dir = get_kb_raw_dir(kb_row["kb_id"])
    collection = kb_row["collection_name"]
    indexed = set(list_sources(collection_name=collection))
    files = sorted(
        p.name
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    for name in sorted(indexed):
        if name not in files:
            files.append(name)

    q = (query or "").strip()
    if q:
        needle = q.casefold()
        files = [name for name in files if needle in name.casefold()]

    return {
        "kb_id": kb_row["kb_id"],
        "documents": [
            {
                "filename": name,
                "indexed": name in indexed,
                "has_raw": (raw_dir / name).is_file(),
            }
            for name in files
        ],
    }


def _kb_detail_stats(kb_row: dict) -> dict:
    documents = _documents_payload(kb_row)["documents"]
    total = len(documents)
    indexed = sum(1 for d in documents if d["indexed"])
    raw_dir = get_kb_raw_dir(kb_row["kb_id"])
    total_size = 0
    for d in documents:
        if not d.get("has_raw"):
            continue
        path = raw_dir / d["filename"]
        if path.is_file():
            try:
                total_size += path.stat().st_size
            except OSError:
                pass

    return {
        "kb_id": kb_row["kb_id"],
        "name": kb_row["name"],
        "total_documents": total,
        "total_size_bytes": total_size,
        "indexed_documents": indexed,
        "not_indexed_documents": max(0, total - indexed),
        "chunk_count": count_chunks(collection_name=kb_row["collection_name"]),
    }


def _kb_stats_payload() -> dict:
    rows = list_kbs()
    per_kb = [_kb_detail_stats(r) for r in rows]
    kb_names = [r["name"] for r in rows]
    return {
        "kb_count": len(rows),
        "kb_names": kb_names,
        "total_documents": sum(x["total_documents"] for x in per_kb),
        "total_size_bytes": sum(x["total_size_bytes"] for x in per_kb),
        "indexed_documents": sum(x["indexed_documents"] for x in per_kb),
        "not_indexed_documents": sum(x["not_indexed_documents"] for x in per_kb),
        "chunk_count": sum(x["chunk_count"] for x in per_kb),
        "knowledge_bases": per_kb,
    }


@app.get("/api/v1/admin/stats", response_model=KbStatsResponse)
def admin_kb_stats(_admin: AuthUser = Depends(require_kb_admin)):
    return _kb_stats_payload()


@app.get("/api/v1/admin/kbs/{kb_id}/documents/{filename}/preview")
def admin_kb_document_preview(
    kb_id: str,
    filename: str,
    max_chars: int = 8000,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    return _document_preview(row, filename, max_chars)


@app.get("/api/v1/admin/documents/{filename}/preview")
def admin_document_preview(
    filename: str,
    max_chars: int = 8000,
    kb_id: str | None = None,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return _document_preview(row, filename, max_chars)


def _document_preview(kb_row: dict, filename: str, max_chars: int) -> dict:
    path = get_kb_raw_dir(kb_row["kb_id"]) / filename
    collection = kb_row["collection_name"]

    # 优先用已入库切片，避免国标 PDF 预览时整本 OCR 导致代理超时（ECONNRESET）
    store = get_vectorstore(collection)
    data = store.get(
        where={"source": filename},
        include=["documents", "metadatas"],
    )
    vs_docs = data.get("documents") or []
    vs_metas = data.get("metadatas") or []
    if vs_docs:
        page_map: dict[int, list[str]] = {}
        for doc_text, meta in zip(vs_docs, vs_metas):
            if not isinstance(doc_text, str):
                continue
            page = 1
            if isinstance(meta, dict) and isinstance(meta.get("page"), int):
                page = meta["page"]
            page_map.setdefault(page, []).append(doc_text)
        pages = [
            {"page": p, "content": "\n".join(parts)}
            for p, parts in sorted(page_map.items())
        ]
        full_text = "\n\n".join(p["content"] for p in pages).strip()
        full_text = full_text[: max(500, min(max_chars, 50000))]
        log.info(
            "preview from vectorstore kb=%s file=%s pages=%s",
            kb_row["kb_id"],
            filename,
            len(pages),
        )
        return {
            "kb_id": kb_row["kb_id"],
            "filename": filename,
            "page_count": len(pages),
            "content_preview": full_text,
            "pages": pages,
            "from_vectorstore": True,
        }

    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filename}")

    try:
        # 未入库时仅 OCR 前 2 页做快速预览，避免代理超时
        docs = load_file(path, max_pages=2, allow_ocr=True)
    except ValueError as e:
        log.warning("preview rejected file=%s err=%s", filename, e)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("preview failed file=%s", filename)
        raise HTTPException(status_code=500, detail=f"解析失败: {e}") from e

    pages = [
        {
            "page": d.metadata.get("page"),
            "content": d.page_content,
        }
        for d in docs
    ]
    total_pages = docs[0].metadata.get("page_count") if docs else len(pages)
    full_text = "\n\n".join(d.page_content for d in docs).strip()
    if isinstance(total_pages, int) and total_pages > len(pages):
        full_text += f"\n\n…（共 {total_pages} 页，预览仅显示前 {len(pages)} 页；重建索引后可查看全文）"
    full_text = full_text[: max(500, min(max_chars, 50000))]
    log.info("preview ok kb=%s file=%s pages=%s", kb_row["kb_id"], filename, len(pages))
    return {
        "kb_id": kb_row["kb_id"],
        "filename": filename,
        "page_count": total_pages if isinstance(total_pages, int) else len(pages),
        "content_preview": full_text,
        "pages": pages,
        "from_vectorstore": False,
    }


@app.get("/api/v1/admin/kbs/{kb_id}/documents/{filename}/chunks")
def admin_kb_document_chunks(
    kb_id: str,
    filename: str,
    max_chunks: int = 200,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    return _document_chunks(row, filename, max_chunks)


@app.get("/api/v1/admin/documents/{filename}/chunks")
def admin_document_chunks(
    filename: str,
    max_chunks: int = 200,
    kb_id: str | None = None,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return _document_chunks(row, filename, max_chunks)


def _document_chunks(kb_row: dict, filename: str, max_chunks: int) -> dict:
    path = get_kb_raw_dir(kb_row["kb_id"]) / filename
    has_raw = path.is_file()
    collection = kb_row["collection_name"]

    store = get_vectorstore(collection)
    data = store.get(
        where={"source": filename},
        include=["documents", "metadatas"],
    )
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    chunks: list[PreviewChunk] = []

    for doc_text, meta in zip(docs, metas):
        if not isinstance(doc_text, str):
            continue
        chunk_id = -1
        page = None
        if isinstance(meta, dict):
            try:
                chunk_id = int(meta.get("chunk_id", -1))
            except Exception:
                chunk_id = -1
            page_val = meta.get("page")
            if isinstance(page_val, int):
                page = page_val
        chunks.append(PreviewChunk(chunk_id=chunk_id, page=page, content=doc_text))

    chunks.sort(key=lambda c: c.chunk_id)
    if chunks:
        log.info(
            "chunks from vectorstore kb=%s file=%s count=%s",
            kb_row["kb_id"],
            filename,
            len(chunks),
        )
        return {
            "kb_id": kb_row["kb_id"],
            "filename": filename,
            "from_vectorstore": True,
            "chunk_count": len(chunks),
            "chunks": [c.model_dump() for c in chunks[: max(1, min(max_chunks, 1000))]],
        }

    if not has_raw:
        raise HTTPException(
            status_code=404,
            detail=f"文件不存在且向量库无切片: {filename}",
        )

    try:
        # 未入库时只快速解析前几页做切片预览，避免整本 OCR 卡死代理
        preview_docs = load_file(path, max_pages=3, allow_ocr=True)
    except ValueError as e:
        log.warning("chunks rejected file=%s err=%s", filename, e)
        raise HTTPException(
            status_code=422,
            detail=f"{e}；国标类 PDF 请先「重建索引」后再查看切片",
        ) from e
    except Exception as e:  # noqa: BLE001
        log.exception("chunks failed file=%s", filename)
        raise HTTPException(status_code=500, detail=f"解析失败: {e}") from e

    split = split_documents(preview_docs)
    for idx, ch in enumerate(split):
        page_val = ch.metadata.get("page")
        page = page_val if isinstance(page_val, int) else None
        chunks.append(
            PreviewChunk(
                chunk_id=idx,
                page=page,
                content=ch.page_content,
            )
        )

    log.info("chunks preview split kb=%s file=%s count=%s", kb_row["kb_id"], filename, len(chunks))
    return {
        "kb_id": kb_row["kb_id"],
        "filename": filename,
        "from_vectorstore": False,
        "chunk_count": len(chunks),
        "chunks": [c.model_dump() for c in chunks[: max(1, min(max_chunks, 1000))]],
    }


@app.post("/api/v1/admin/kbs/{kb_id}/upload")
async def admin_kb_upload(
    kb_id: str,
    file: UploadFile = File(...),
    admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    return await _upload_to_kb(row, file, admin)


@app.post("/api/v1/admin/upload")
async def admin_upload(
    file: UploadFile = File(...),
    kb_id: str | None = None,
    admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return await _upload_to_kb(row, file, admin)


async def _upload_to_kb(kb_row: dict, file: UploadFile, admin: AuthUser) -> dict:
    raw_name = Path(file.filename or "").name
    suffix = Path(raw_name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}，支持 {sorted(SUPPORTED_SUFFIXES)}",
        )
    raw_dir = get_kb_raw_dir(kb_row["kb_id"])
    dest = raw_dir / raw_name
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:  # noqa: BLE001
        log.exception("upload failed kb=%s file=%s", kb_row["kb_id"], raw_name)
        raise HTTPException(status_code=500, detail=f"保存文件失败: {e}") from e
    size = dest.stat().st_size if dest.is_file() else 0
    log.info(
        "upload ok kb=%s file=%s size=%s by=%s",
        kb_row["kb_id"],
        dest.name,
        size,
        admin.username,
    )
    return {
        "kb_id": kb_row["kb_id"],
        "saved": dest.name,
        "path": str(dest),
    }


@app.post("/api/v1/admin/kbs/{kb_id}/ingest")
def admin_kb_ingest(
    kb_id: str,
    body: IngestRequest = IngestRequest(),
    admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    return _ingest_kb(row, body, admin)


@app.post("/api/v1/admin/kbs/{kb_id}/ingest/stream")
def admin_kb_ingest_stream(
    kb_id: str,
    body: IngestRequest = IngestRequest(),
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    raw_dir = get_kb_raw_dir(row["kb_id"])
    collection = row["collection_name"]

    if body.filename:
        path = raw_dir / body.filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {body.filename}")
        paths = [path]
    else:
        paths = sorted(
            p
            for p in raw_dir.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        )

    def event_stream():
        for evt in iter_ingest_events(
            paths,
            collection_name=collection,
            replace=body.replace,
        ):
            yield json.dumps(evt, ensure_ascii=False) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/api/v1/admin/ingest")
def admin_ingest(
    body: IngestRequest = IngestRequest(),
    kb_id: str | None = None,
    admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return _ingest_kb(row, body, admin)


def _ingest_kb(kb_row: dict, body: IngestRequest, admin: AuthUser) -> dict:
    raw_dir = get_kb_raw_dir(kb_row["kb_id"])
    collection = kb_row["collection_name"]
    log.info(
        "ingest start kb=%s filename=%s replace=%s",
        kb_row["kb_id"],
        body.filename,
        body.replace,
    )
    if body.filename:
        path = raw_dir / body.filename
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {body.filename}")
        result = ingest_files(
            [path],
            collection_name=collection,
            replace=body.replace,
        )
    else:
        result = ingest_raw_dir(
            raw_dir,
            collection_name=collection,
            replace=body.replace,
        )
    log.info(
        "ingest done kb=%s ingested=%s chunks=%s errors=%s by=%s",
        kb_row["kb_id"],
        len(result.get("ingested") or []),
        result.get("chunk_count"),
        len(result.get("errors") or []),
        admin.username,
    )
    return result


@app.delete("/api/v1/admin/kbs/{kb_id}/documents/{filename}")
def admin_kb_delete_document(
    kb_id: str,
    filename: str,
    admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id)
    return _delete_document(row, filename, admin)


@app.delete("/api/v1/admin/documents/{filename}")
def admin_delete_document(
    filename: str,
    kb_id: str | None = None,
    admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return _delete_document(row, filename, admin)


def _delete_document(kb_row: dict, filename: str, admin: AuthUser) -> dict:
    """删除原始文件（若存在）并清除向量库中对应切片。"""
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name:
        raise HTTPException(status_code=400, detail="非法文件名")

    raw_dir = get_kb_raw_dir(kb_row["kb_id"])
    path = raw_dir / safe_name
    collection = kb_row["collection_name"]
    indexed = safe_name in set(list_sources(collection_name=collection))
    has_raw = path.is_file()

    if not has_raw and not indexed:
        raise HTTPException(status_code=404, detail=f"文档不存在: {safe_name}")

    deleted_raw = False
    if has_raw:
        last_err: Exception | None = None
        for attempt in range(5):
            try:
                path.unlink()
                deleted_raw = True
                last_err = None
                break
            except PermissionError as e:
                # Windows：预览/OCR 刚释放文件时偶发占用
                last_err = e
                time.sleep(0.35 * (attempt + 1))
            except Exception as e:  # noqa: BLE001
                last_err = e
                break
        if not deleted_raw:
            log.exception("delete raw failed kb=%s file=%s", kb_row["kb_id"], safe_name)
            raise HTTPException(
                status_code=500,
                detail=f"删除文件失败（文件可能仍被占用，请稍后重试）: {last_err}",
            ) from last_err

    deleted_index = False
    if indexed:
        delete_by_source(safe_name, collection_name=collection)
        deleted_index = True

    log.info(
        "document deleted kb=%s file=%s raw=%s index=%s by=%s",
        kb_row["kb_id"],
        safe_name,
        deleted_raw,
        deleted_index,
        admin.username,
    )
    return {
        "ok": True,
        "kb_id": kb_row["kb_id"],
        "filename": safe_name,
        "deleted_raw": deleted_raw,
        "deleted_index": deleted_index,
    }


# 兼容旧路径（可选）
@app.get("/api/v1/documents")
def documents_compat(
    kb_id: str | None = None,
    _admin: AuthUser = Depends(require_kb_admin),
):
    row = _require_kb(kb_id or _default_kb_id())
    return _documents_payload(row)


@app.post("/api/v1/upload")
async def upload_compat(
    file: UploadFile = File(...),
    kb_id: str | None = None,
    admin: AuthUser = Depends(require_kb_admin),
):
    return await admin_upload(file=file, kb_id=kb_id, admin=admin)


@app.post("/api/v1/ingest")
def ingest_compat(
    body: IngestRequest = IngestRequest(),
    kb_id: str | None = None,
    admin: AuthUser = Depends(require_kb_admin),
):
    return admin_ingest(body=body, kb_id=kb_id, admin=admin)


# 问答侧：列出可用知识库
@app.get("/api/v1/kbs")
def api_list_kbs_for_chat(user: AuthUser = Depends(get_current_user)):
    rows = list_kbs()
    return {
        "knowledge_bases": [
            {
                "kb_id": r["kb_id"],
                "name": r["name"],
                "description": r.get("description") or "",
            }
            for r in rows
        ]
    }
