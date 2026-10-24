from __future__ import annotations

from functools import lru_cache

from langchain_chroma import Chroma
from langchain_core.documents import Document

from src.config import CHROMA_COLLECTION, CHROMA_DIR
from src.rag.embeddings import get_embeddings


def list_kb_collections() -> list[str]:
    """列出 Chroma 持久化目录中的向量集合名称。"""
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return sorted(c.name for c in client.list_collections())
    except Exception:
        return [CHROMA_COLLECTION]


@lru_cache(maxsize=32)
def get_vectorstore(collection_name: str = CHROMA_COLLECTION) -> Chroma:
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )


def add_documents(
    docs: list[Document],
    *,
    collection_name: str = CHROMA_COLLECTION,
) -> list[str]:
    if not docs:
        return []
    store = get_vectorstore(collection_name)
    ids = store.add_documents(docs)
    return ids


def delete_by_source(
    source: str,
    *,
    collection_name: str = CHROMA_COLLECTION,
) -> None:
    store = get_vectorstore(collection_name)
    try:
        store.delete(where={"source": source})
    except Exception:
        pass


def list_sources(*, collection_name: str = CHROMA_COLLECTION) -> list[str]:
    store = get_vectorstore(collection_name)
    data = store.get(include=["metadatas"])
    metadatas = data.get("metadatas") or []
    sources = sorted(
        {
            m.get("source")
            for m in metadatas
            if isinstance(m, dict) and m.get("source")
        }
    )
    return sources


def count_chunks(*, collection_name: str = CHROMA_COLLECTION) -> int:
    try:
        data = get_vectorstore(collection_name).get(include=[])
        return len(data.get("ids") or [])
    except Exception:
        return 0


def get_all_documents(*, collection_name: str = CHROMA_COLLECTION) -> list[Document]:
    """取出集合内全部切片，供 BM25 词法索引使用。"""
    try:
        data = get_vectorstore(collection_name).get(include=["documents", "metadatas"])
    except Exception:
        return []
    texts = data.get("documents") or []
    metas = data.get("metadatas") or []
    docs: list[Document] = []
    for text, meta in zip(texts, metas):
        if not text:
            continue
        docs.append(Document(page_content=str(text), metadata=dict(meta or {})))
    return docs
