from __future__ import annotations

import re
from contextvars import ContextVar

from src.rag.retriever import format_source_label, get_active_kb_name

_retrieved_sources: ContextVar[list[dict] | None] = ContextVar(
    "_retrieved_sources",
    default=None,
)

_OLD_SOURCE_LINE = re.compile(r"^[^/]+/.+：来源：.+$")
_NEW_SOURCE_IN_TOOL = re.compile(
    r"\[\d+\]\s*(来源：.+?)\s*\|\s*页/段:\s*(\S+)",
)
_LEGACY_SOURCE_IN_TOOL = re.compile(
    r"\[\d+\]\s*(.+?/.*?：来源：.+?)\s*\|\s*页/段:\s*(\S+)",
)


def reset_retrieved_sources() -> None:
    _retrieved_sources.set([])


def record_retrieved_docs(docs: list) -> None:
    """记录本轮检索到的文档来源（去重，保持顺序）。"""
    kb_name = get_active_kb_name()
    seen: set[str] = set()
    rows: list[dict] = []
    for doc in docs:
        meta = doc.metadata or {}
        filename = str(meta.get("source") or "未知").strip() or "未知"
        label = format_source_label(filename, kb_name=kb_name)
        if label in seen:
            continue
        seen.add(label)
        page = meta.get("page")
        rows.append(
            {
                "label": label,
                "filename": filename,
                "page": page if isinstance(page, int) else None,
            }
        )
    _retrieved_sources.set(rows)


def get_retrieved_sources() -> list[dict]:
    val = _retrieved_sources.get()
    return list(val) if val else []


def _format_source_line(item: dict) -> str:
    return item["label"]


def _is_source_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("来源："):
        return True
    if _OLD_SOURCE_LINE.match(stripped):
        return True
    if "{知识库名称}" in stripped or "{文件名}" in stripped:
        return True
    return False


def parse_sources_from_tool_output(text: str) -> list[dict]:
    """从 search_knowledge 工具返回文本解析来源列表。"""
    rows: list[dict] = []
    seen: set[str] = set()

    for match in _NEW_SOURCE_IN_TOOL.finditer(text):
        label = match.group(1).strip()
        if label in seen:
            continue
        seen.add(label)
        page_raw = match.group(2)
        page = int(page_raw) if page_raw.isdigit() else None
        filename = label.removeprefix("来源：").rsplit("/", 1)[-1].strip()
        rows.append({"label": label, "filename": filename, "page": page})

    if rows:
        return rows

    for match in _LEGACY_SOURCE_IN_TOOL.finditer(text):
        legacy = match.group(1).strip()
        if "：来源：" not in legacy:
            continue
        path_part = legacy.split("：来源：", 1)[0].strip()
        filename = legacy.rsplit("：来源：", 1)[-1].strip()
        label = f"来源：{path_part}" if "/" in path_part else f"来源：{path_part}/{filename}"
        if label in seen:
            continue
        seen.add(label)
        page_raw = match.group(2)
        page = int(page_raw) if page_raw.isdigit() else None
        rows.append({"label": label, "filename": filename, "page": page})

    return rows


def merge_source_rows(*groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            label = item.get("label", "")
            if not label or label in seen:
                continue
            seen.add(label)
            merged.append(item)
    return merged


def finalize_answer_sources(answer: str, sources: list[dict] | None = None) -> str:
    """清理误输出的来源行，并追加准确来源。"""
    text = (answer or "").strip()
    if not text:
        return text

    cleaned_lines: list[str] = []
    for line in text.splitlines():
        if _is_source_line(line):
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines).rstrip()
    while text.splitlines() and _is_source_line(text.splitlines()[-1]):
        text = "\n".join(text.splitlines()[:-1]).rstrip()

    active_sources = merge_source_rows(sources or []) if sources is not None else get_retrieved_sources()
    if not active_sources:
        return text

    labels = [_format_source_line(s) for s in active_sources]
    if labels and all(label in text for label in labels):
        return text

    if not labels:
        return text

    return f"{text}\n\n" + "\n".join(labels)
