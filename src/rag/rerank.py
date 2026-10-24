from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document

from src.config import RERANKER_MODEL_PATH
from src.logging_config import get_logger

log = get_logger("qizhi.rag.rerank")


@lru_cache(maxsize=1)
def get_reranker():
    """加载本地 bge-reranker；目录不存在则返回 None（不阻塞启动）。"""
    path = (RERANKER_MODEL_PATH or "").strip()
    local = Path(path)
    if not local.is_dir():
        log.warning(
            "reranker dir missing, hybrid will skip CrossEncoder: %s",
            path,
        )
        return None
    try:
        from sentence_transformers import CrossEncoder

        log.info("loading reranker from local dir: %s", local)
        return CrossEncoder(str(local), device="cpu")
    except Exception:
        log.exception("failed to load reranker from %s", local)
        return None


def reranker_ready() -> bool:
    return get_reranker() is not None


def rerank_documents(
    query: str,
    docs: list[Document],
    *,
    top_k: int,
) -> list[tuple[Document, float]]:
    if not docs:
        return []
    model = get_reranker()
    if model is None:
        return []
    pairs = [(query, (doc.page_content or "")[:800]) for doc in docs]
    scores = model.predict(pairs, batch_size=8, show_progress_bar=False)
    ranked = sorted(
        zip(docs, [float(s) for s in scores]),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[: max(1, top_k)]
