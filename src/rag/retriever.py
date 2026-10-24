from __future__ import annotations

from contextvars import ContextVar

from langchain_core.documents import Document

from src.config import (
    CHROMA_COLLECTION,
    RETRIEVE_CANDIDATE_K,
    RETRIEVE_MODE,
    RETRIEVE_TOP_K,
)
from src.rag.hybrid import RankedHit, doc_key, lexical_candidates, rrf_fuse
from src.rag.rerank import rerank_documents, reranker_ready
from src.rag.store import get_vectorstore

_active_collection: ContextVar[str] = ContextVar(
    "active_collection",
    default=CHROMA_COLLECTION,
)
_active_kb_name: ContextVar[str] = ContextVar(
    "active_kb_name",
    default="默认知识库",
)

LANE_LABELS = {
    "vector": "仅向量",
    "hybrid": "BM25 + 向量",
    "hybrid_rerank": "混合 + Rerank",
}


def set_active_collection(collection_name: str) -> None:
    _active_collection.set(collection_name or CHROMA_COLLECTION)


def set_active_kb_name(kb_name: str) -> None:
    _active_kb_name.set((kb_name or "").strip() or "默认知识库")


def get_active_kb_name() -> str:
    return _active_kb_name.get()


def get_active_collection() -> str:
    return _active_collection.get()


def format_source_label(filename: str, *, kb_name: str | None = None) -> str:
    """统一来源标签：来源：{知识库}/{文档}"""
    doc = (filename or "未知").strip() or "未知"
    kb = (kb_name or get_active_kb_name()).strip() or "默认知识库"
    return f"来源：{kb}/{doc}"


def _vector_hits(
    query: str,
    *,
    k: int,
    collection_name: str,
) -> list[RankedHit]:
    store = get_vectorstore(collection_name)
    pairs = store.similarity_search_with_score(query, k=max(1, k))
    hits: list[RankedHit] = []
    for doc, score in pairs:
        hits.append(
            RankedHit(
                doc=doc,
                score=float(score),
                score_kind="distance",
                channels=["vector"],
            )
        )
    return hits


def _take(hits: list[RankedHit], k: int) -> list[RankedHit]:
    return hits[: max(1, k)]


def retrieve(
    query: str,
    *,
    k: int | None = None,
    collection_name: str | None = None,
    mode: str | None = None,
    candidate_k: int | None = None,
) -> list[RankedHit]:
    """按模式检索。hybrid_rerank 在无 reranker 时自动降级为 hybrid。"""
    coll = collection_name or get_active_collection()
    top_k = k or RETRIEVE_TOP_K
    cand = candidate_k or RETRIEVE_CANDIDATE_K
    chosen = (mode or RETRIEVE_MODE or "hybrid_rerank").strip().lower()

    vector_lane = _vector_hits(query, k=cand, collection_name=coll)
    if chosen == "vector":
        return _take(vector_lane, top_k)

    bm25_lane = lexical_candidates(query, collection_name=coll, k=cand)
    if chosen == "bm25":
        return _take(bm25_lane, top_k)

    fused = rrf_fuse([vector_lane, bm25_lane])
    if chosen == "hybrid" or not reranker_ready():
        return _take(fused, top_k)

    reranked = rerank_documents(query, [h.doc for h in fused[: max(cand, top_k)]], top_k=top_k)
    if not reranked:
        return _take(fused, top_k)

    origin = {doc_key(h.doc): h.channels for h in fused}
    out: list[RankedHit] = []
    for doc, score in reranked:
        out.append(
            RankedHit(
                doc=doc,
                score=float(score),
                score_kind="rerank",
                channels=origin.get(doc_key(doc), ["vector", "bm25"]),
            )
        )
    return out


def search_knowledge(query: str, *, k: int | None = None) -> list[Document]:
    return [hit.doc for hit in retrieve(query, k=k)]


def search_knowledge_fuzzy(
    query: str,
    *,
    k: int = 20,
    collection_name: str | None = None,
) -> list[tuple[Document, float]]:
    """语义相似度检索，返回 (文档, 距离) 元组；距离越小越相似。"""
    coll = collection_name or get_active_collection()
    hits = _vector_hits(query, k=max(1, min(k, 100)), collection_name=coll)
    return [(h.doc, h.score) for h in hits]


def compare_retrieval(
    query: str,
    *,
    k: int = 10,
    collection_name: str | None = None,
) -> dict:
    """召回对比：仅向量 / BM25+向量 / 混合+Rerank（若可用）。"""
    coll = collection_name or get_active_collection()
    top_k = max(1, min(k, 50))
    modes = ["vector", "hybrid"]
    if reranker_ready():
        modes.append("hybrid_rerank")
    lanes = []
    for mode in modes:
        hits = retrieve(query, k=top_k, collection_name=coll, mode=mode)
        lanes.append(
            {
                "mode": mode,
                "label": LANE_LABELS.get(mode, mode),
                "hits": hits,
            }
        )
    default_hits = lanes[-1]["hits"] if lanes else []
    return {
        "lanes": lanes,
        "hits": default_hits,
        "reranker_ready": reranker_ready(),
    }


def format_docs(docs: list[Document]) -> str:
    if not docs:
        return "（未检索到相关内容）"
    kb_name = get_active_kb_name()
    parts: list[str] = []
    for i, doc in enumerate(docs, start=1):
        meta = doc.metadata or {}
        source = str(meta.get("source") or "未知")
        page = meta.get("page", "?")
        label = format_source_label(source, kb_name=kb_name)
        parts.append(
            f"[{i}] {label} | 页/段: {page}\n{doc.page_content.strip()}"
        )
    return "\n\n".join(parts)
