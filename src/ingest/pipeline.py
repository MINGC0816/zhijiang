from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from src.config import CHROMA_COLLECTION
from src.ingest.chunking import split_documents
from src.ingest.loaders import SUPPORTED_SUFFIXES, load_file
from src.logging_config import get_logger
from src.rag.hybrid import invalidate_lexical_index
from src.rag.store import add_documents, delete_by_source

log = get_logger("qizhi.ingest")


def ingest_files(
    paths: list[Path],
    *,
    collection_name: str = CHROMA_COLLECTION,
    replace: bool = True,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    """解析、分块并写入向量库。"""
    total_chunks = 0
    ingested: list[str] = []
    errors: list[str] = []
    paths = [Path(p) for p in paths]
    total = len(paths)

    if on_progress:
        on_progress(
            {
                "phase": "start",
                "total": total,
                "percent": 0,
                "message": f"准备入库 {total} 个文件",
            }
        )

    for idx, path in enumerate(paths):
        if on_progress:
            on_progress(
                {
                    "phase": "processing",
                    "current": idx + 1,
                    "total": total,
                    "filename": path.name,
                    "percent": int(idx / total * 100) if total else 0,
                    "message": f"正在入库 {path.name} ({idx + 1}/{total})",
                }
            )
        try:
            log.info("ingest file start name=%s collection=%s", path.name, collection_name)
            docs = load_file(path)
            chunks = split_documents(docs)
            for i, chunk in enumerate(chunks):
                chunk.metadata["chunk_id"] = i
            if replace:
                delete_by_source(path.name, collection_name=collection_name)
            add_documents(chunks, collection_name=collection_name)
            invalidate_lexical_index(collection_name)
            total_chunks += len(chunks)
            ingested.append(path.name)
            log.info(
                "ingest file ok name=%s docs=%s chunks=%s",
                path.name,
                len(docs),
                len(chunks),
            )
        except Exception as e:  # noqa: BLE001 — 批量入库需汇总错误
            log.exception("ingest file failed name=%s", path.name)
            errors.append(f"{path.name}: {e}")

    result = {
        "ingested": ingested,
        "chunk_count": total_chunks,
        "errors": errors,
    }
    if on_progress:
        on_progress(
            {
                "phase": "done",
                "percent": 100,
                "message": "入库完成",
                "result": result,
            }
        )
    return result


def ingest_raw_dir(
    raw_dir: Path,
    *,
    collection_name: str = CHROMA_COLLECTION,
    replace: bool = True,
    on_progress: Callable[[dict], None] | None = None,
) -> dict:
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return {"ingested": [], "chunk_count": 0, "errors": ["raw 目录不存在"]}
    paths = sorted(
        p
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
    )
    if not paths:
        log.warning("ingest raw empty dir=%s", raw_dir)
        result = {"ingested": [], "chunk_count": 0, "errors": ["raw 目录无支持的文件"]}
        if on_progress:
            on_progress(
                {
                    "phase": "done",
                    "percent": 100,
                    "message": "无支持的文件",
                    "result": result,
                }
            )
        return result
    log.info("ingest raw dir=%s files=%s collection=%s", raw_dir, len(paths), collection_name)
    return ingest_files(
        paths,
        collection_name=collection_name,
        replace=replace,
        on_progress=on_progress,
    )


def _ingest_one_file(
    path: Path,
    *,
    collection_name: str,
    replace: bool,
) -> tuple[int, str | None]:
    """入库单个文件，返回 (切片数, 错误信息)。"""
    try:
        docs = load_file(path)
        chunks = split_documents(docs)
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_id"] = i
        if replace:
            delete_by_source(path.name, collection_name=collection_name)
        add_documents(chunks, collection_name=collection_name)
        invalidate_lexical_index(collection_name)
        log.info(
            "ingest file ok name=%s docs=%s chunks=%s",
            path.name,
            len(docs),
            len(chunks),
        )
        return len(chunks), None
    except Exception as e:  # noqa: BLE001
        log.exception("ingest file failed name=%s", path.name)
        return 0, f"{path.name}: {e}"


def iter_ingest_events(
    paths: list[Path],
    *,
    collection_name: str = CHROMA_COLLECTION,
    replace: bool = True,
) -> Iterator[dict]:
    """逐条产出入库进度事件，供流式 API 使用。"""
    paths = [Path(p) for p in paths]
    total = len(paths)
    yield {
        "phase": "start",
        "total": total,
        "percent": 0,
        "message": f"准备入库 {total} 个文件",
    }

    total_chunks = 0
    ingested: list[str] = []
    errors: list[str] = []

    for idx, path in enumerate(paths):
        yield {
            "phase": "processing",
            "current": idx + 1,
            "total": total,
            "filename": path.name,
            "percent": int(idx / total * 100) if total else 0,
            "message": f"正在入库 {path.name} ({idx + 1}/{total})",
        }
        log.info("ingest file start name=%s collection=%s", path.name, collection_name)
        chunks, err = _ingest_one_file(
            path,
            collection_name=collection_name,
            replace=replace,
        )
        if err:
            errors.append(err)
        else:
            total_chunks += chunks
            ingested.append(path.name)

    result = {
        "ingested": ingested,
        "chunk_count": total_chunks,
        "errors": errors,
    }
    yield {
        "phase": "done",
        "percent": 100,
        "message": "入库完成",
        "result": result,
    }
