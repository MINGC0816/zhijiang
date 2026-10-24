from langchain_core.documents import Document

from src.agent.sources import (
    finalize_answer_sources,
    parse_sources_from_tool_output,
    record_retrieved_docs,
    reset_retrieved_sources,
)
from src.rag.retriever import set_active_kb_name


def test_parse_tool_output_new_format():
    text = (
        "[1] 来源：默认知识库/休假管理制度.md | 页/段: 1\n年休假 5 个工作日\n\n"
        "[2] 来源：默认知识库/休假管理制度.md | 页/段: 2\n事假不计发工资"
    )
    rows = parse_sources_from_tool_output(text)
    assert len(rows) == 1
    assert rows[0]["filename"] == "休假管理制度.md"
    assert rows[0]["label"] == "来源：默认知识库/休假管理制度.md"
    assert rows[0]["page"] == 1


def test_finalize_strips_model_invented_source_and_appends_real():
    answer = "年休假为 5 个工作日。\n来源：通义千问/胡编.md"
    sources = [
        {
            "label": "来源：默认知识库/休假管理制度.md",
            "filename": "休假管理制度.md",
            "page": 1,
        }
    ]
    out = finalize_answer_sources(answer, sources)
    assert "通义千问" not in out
    assert "胡编.md" not in out
    assert out.endswith("来源：默认知识库/休假管理制度.md")
    assert "5 个工作日" in out


def test_finalize_no_sources_keeps_body():
    assert finalize_answer_sources("没有依据。", []) == "没有依据。"


def test_record_retrieved_docs_dedupes():
    set_active_kb_name("制度库")
    reset_retrieved_sources()
    docs = [
        Document(page_content="a", metadata={"source": "休假管理制度.md", "page": 1}),
        Document(page_content="b", metadata={"source": "休假管理制度.md", "page": 2}),
        Document(page_content="c", metadata={"source": "报销管理办法.md"}),
    ]
    record_retrieved_docs(docs)
    from src.agent.sources import get_retrieved_sources

    rows = get_retrieved_sources()
    assert [r["filename"] for r in rows] == ["休假管理制度.md", "报销管理办法.md"]
    assert all(r["label"].startswith("来源：制度库/") for r in rows)
