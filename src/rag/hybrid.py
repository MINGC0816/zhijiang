from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from src.config import RETRIEVE_CANDIDATE_K, RRF_K
from src.logging_config import get_logger
from src.rag.store import count_chunks, get_all_documents

log = get_logger("qizhi.rag.hybrid")

_STOP = {
    "的",
    "了",
    "是",
    "在",
    "和",
    "与",
    "及",
    "或",
    "等",
    "为",
    "对",
    "就",
    "也",
    "而",
    "并",
    "其",
    "中",
    "上",
    "下",
    "这",
    "那",
    "一个",
    "可以",
    "需要",
    "进行",
    "相关",
}

_lock = threading.Lock()
_cache: dict[str, tuple[int, BM25Okapi, list[Document]]] = {}


@dataclass
class RankedHit:
    doc: Document
    score: float
    score_kind: str
    channels: list[str] = field(default_factory=list)


def doc_key(doc: Document) -> str:
    meta = doc.metadata or {}
    src = str(meta.get("source") or "")
    cid = str(meta.get("chunk_id") if meta.get("chunk_id") is not None else "")
    digest = hashlib.md5(
        (doc.page_content or "").encode("utf-8", errors="ignore")
    ).hexdigest()[:12]
    return f"{src}#{cid}#{digest}"


def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in jieba.lcut((text or "").strip().lower()):
        t = tok.strip()
        if len(t) < 1 or t in _STOP:
            continue
        tokens.append(t)
    return tokens


def invalidate_lexical_index(collection_name: str | None = None) -> None:
    with _lock:
        if collection_name is None:
            _cache.clear()
        else:
            _cache.pop(collection_name, None)


def _get_bm25(collection_name: str) -> tuple[BM25Okapi, list[Document]] | None:
    n = count_chunks(collection_name=collection_name)
    if n <= 0:
        return None
    with _lock:
        cached = _cache.get(collection_name)
        if cached and cached[0] == n:
            return cached[1], cached[2]
        docs = get_all_documents(collection_name=collection_name)
        if not docs:
            return None
        corpus = [tokenize(d.page_content) for d in docs]
        bm25 = BM25Okapi(corpus)
        _cache[collection_name] = (len(docs), bm25, docs)
        log.info("bm25 index rebuilt collection=%s docs=%s", collection_name, len(docs))
        return bm25, docs


def bm25_search(
    query: str,
    *,
    collection_name: str,
    k: int,
) -> list[RankedHit]:
    packed = _get_bm25(collection_name)
    if not packed:
        return []
    bm25, docs = packed
    tokens = tokenize(query)
    if not tokens:
        return []
    scores = bm25.get_scores(tokens)
    order = sorted(range(len(scores)), key=lambda i: float(scores[i]), reverse=True)
    top = order[: max(1, k)]
    hits: list[RankedHit] = []
    for idx in top:
        score = float(scores[idx])
        if score <= 0:
            continue
        hits.append(
            RankedHit(
                doc=docs[idx],
                score=score,
                score_kind="bm25",
                channels=["bm25"],
            )
        )
    return hits


def rrf_fuse(
    lanes: list[list[RankedHit]],
    *,
    rrf_k: int = RRF_K,
) -> list[RankedHit]:
    scores: dict[str, float] = {}
    channels: dict[str, set[str]] = {}
    docs: dict[str, Document] = {}
    for lane in lanes:
        for rank, hit in enumerate(lane):
            key = doc_key(hit.doc)
            docs[key] = hit.doc
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank + 1)
            channels.setdefault(key, set()).update(hit.channels)
    fused = [
        RankedHit(
            doc=docs[key],
            score=score,
            score_kind="rrf",
            channels=sorted(channels.get(key) or []),
        )
        for key, score in scores.items()
    ]
    fused.sort(key=lambda h: h.score, reverse=True)
    return fused


def lexical_candidates(
    query: str,
    *,
    collection_name: str,
    k: int = RETRIEVE_CANDIDATE_K,
) -> list[RankedHit]:
    return bm25_search(query, collection_name=collection_name, k=k)
