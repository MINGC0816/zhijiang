from __future__ import annotations

from langchain.tools import tool

from src.agent.rewrite import format_rewrite_result, rewrite_query as _rewrite
from src.agent.sources import record_retrieved_docs
from src.rag.retriever import (
    format_docs,
    format_source_label,
    get_active_collection,
    get_active_kb_name,
    search_knowledge as _search,
)
from src.rag.store import list_sources


@tool
def rewrite_query(question: str) -> str:
    """把口语化、简称或含指代的问题改写成适合检索的独立查询。
    当用户问法简略（如「年假几天」）、含「呢/和去年比」、或一次问多件事时，
    先调用本工具，再用返回的「主查询」调用 search_knowledge。
    不要用用户原话直接检索。
    Args:
        question: 用户原始问题（可附带需要补全的上下文要点）。
    """
    return format_rewrite_result(_rewrite(question))


@tool
def search_knowledge(query: str) -> str:
    """在企业知识库中检索与问题相关的制度、手册片段。
    使用 BM25 + 向量混合检索，若已部署 reranker 会再交叉编码重排。
    Args:
        query: 检索用的自然语言查询，尽量包含关键制度关键词。
    """
    docs = _search(query)
    record_retrieved_docs(docs)
    return format_docs(docs)


@tool
def list_documents() -> str:
    """列出知识库中已入库的文档名称。"""
    sources = list_sources(collection_name=get_active_collection())
    if not sources:
        return f"知识库「{get_active_kb_name()}」为空，尚未入库任何文档。"
    kb_name = get_active_kb_name()
    lines = [format_source_label(name, kb_name=kb_name) for name in sources]
    return f"知识库「{kb_name}」已入库文档：\n" + "\n".join(f"- {line}" for line in lines)
