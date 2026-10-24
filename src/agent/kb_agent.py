from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from functools import lru_cache

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from src.kb.registry import ensure_default_kb, get_kb
from src.rag.retriever import set_active_collection, set_active_kb_name
from src.agent.sources import (
    finalize_answer_sources,
    merge_source_rows,
    parse_sources_from_tool_output,
    reset_retrieved_sources,
    get_retrieved_sources,
)
from src.agent.tools import list_documents, rewrite_query, search_knowledge
from src.config import CHECKPOINT_DB
from src.llm import get_llm
from src.tracing import agent_run_config
from src.logging_config import get_logger
from src.agent.prompts import SYSTEM_PROMPT
from src.sessions.store import delete_thread_meta, get_thread, touch_thread

log = get_logger("qizhi.agent")


def _extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return str(content)


@lru_cache(maxsize=1)
def _get_connection() -> sqlite3.Connection:
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)


@lru_cache(maxsize=1)
def get_checkpointer() -> SqliteSaver:
    checkpointer = SqliteSaver(_get_connection())
    checkpointer.setup()
    return checkpointer


@lru_cache(maxsize=1)
def get_agent():
    return create_agent(
        model=get_llm(),
        tools=[rewrite_query, search_knowledge, list_documents],
        checkpointer=get_checkpointer(),
        system_prompt=SYSTEM_PROMPT,
    )


def _resolve_kb_for_thread(thread_id: str) -> tuple[str, str]:
    """返回 (collection_name, kb_display_name)。"""
    row = get_thread(thread_id)
    kb_id = row.get("kb_id") if row else None
    if kb_id:
        kb = get_kb(kb_id)
        if kb:
            return kb["collection_name"], kb["name"]
    default = ensure_default_kb()
    return default["collection_name"], default["name"]


def _sources_for_latest_turn(messages) -> list[dict]:
    """从本轮对话中的 search_knowledge 工具结果解析来源。"""
    last_human_idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = i
    tool_sources: list[dict] = []
    for msg in messages[last_human_idx + 1 :]:
        if not isinstance(msg, ToolMessage):
            continue
        content = _extract_text(msg.content)
        if "页/段:" not in content:
            continue
        tool_sources.extend(parse_sources_from_tool_output(content))
    return merge_source_rows(get_retrieved_sources(), tool_sources)


def _prepare_agent(thread_id: str):
    collection, kb_name = _resolve_kb_for_thread(thread_id)
    set_active_collection(collection)
    set_active_kb_name(kb_name)
    reset_retrieved_sources()
    return get_agent(), kb_name


def _tool_input_text(tool_call: dict) -> str:
    args = tool_call.get("args") or tool_call.get("arguments") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return args[:200]
    if isinstance(args, dict):
        if "query" in args:
            return str(args.get("query") or "")
        return json.dumps(args, ensure_ascii=False)[:240]
    return str(args)[:200]


def _iter_update_messages(update) -> Iterator:
    if update is None:
        return
    if isinstance(update, dict):
        msgs = update.get("messages")
        if msgs is None:
            return
        if isinstance(msgs, list):
            for msg in msgs:
                yield msg
        else:
            yield msgs
        return
    if isinstance(update, list):
        for msg in update:
            yield msg
        return
    yield update


def iter_ask_events(
    question: str,
    *,
    thread_id: str = "default",
    user_id: str = "local",
) -> Iterator[dict]:
    """流式问答：产出 status / tool_start / tool_end / token / done / error。"""
    log.info("ask stream thread=%s q=%s", thread_id, question[:80].replace("\n", " "))
    agent, _kb_name = _prepare_agent(thread_id)
    run_config, local_trace = agent_run_config(thread_id=thread_id, user_id=user_id)
    yield {"type": "status", "message": "正在分析问题…"}

    streamed: list[str] = []
    started_calls: set[str] = set()
    last_messages = []

    def emit_tool_start(tool_call: dict) -> dict | None:
        name = str(tool_call.get("name") or "tool")
        call_id = str(tool_call.get("id") or name)
        if call_id in started_calls:
            return None
        started_calls.add(call_id)
        return {
            "type": "tool_start",
            "name": name,
            "input": _tool_input_text(tool_call),
        }

    try:
        try:
            stream = agent.stream(
                {"messages": [HumanMessage(content=question)]},
                run_config,
                stream_mode=["updates", "messages"],
            )
        except TypeError:
            stream = agent.stream(
                {"messages": [HumanMessage(content=question)]},
                run_config,
                stream_mode="updates",
            )
        for item in stream:
            mode, data = ("updates", item)
            if isinstance(item, tuple) and len(item) == 2:
                mode, data = item

            if mode == "messages":
                chunk = data[0] if isinstance(data, tuple) else data
                if isinstance(chunk, AIMessageChunk):
                    for tc in getattr(chunk, "tool_call_chunks", None) or []:
                        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                        if name:
                            evt = emit_tool_start(
                                {
                                    "name": name,
                                    "id": tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", name),
                                    "args": tc.get("args") if isinstance(tc, dict) else {},
                                }
                            )
                            if evt:
                                yield evt
                    if getattr(chunk, "tool_calls", None):
                        continue
                    text = _extract_text(chunk.content)
                    if text:
                        streamed.append(text)
                        yield {"type": "token", "text": text}
                continue

            if mode != "updates" or not isinstance(data, dict):
                continue
            for _node, update in data.items():
                for msg in _iter_update_messages(update):
                    if isinstance(msg, AIMessage):
                        last_messages.append(msg)
                        for tc in getattr(msg, "tool_calls", None) or []:
                            evt = emit_tool_start(tc if isinstance(tc, dict) else {
                                "name": getattr(tc, "name", "tool"),
                                "id": getattr(tc, "id", None),
                                "args": getattr(tc, "args", {}),
                            })
                            if evt:
                                yield evt
                    elif isinstance(msg, ToolMessage):
                        last_messages.append(msg)
                        preview = _extract_text(msg.content).replace("\n", " ").strip()
                        yield {
                            "type": "tool_end",
                            "name": getattr(msg, "name", None) or "tool",
                            "preview": (preview[:180] + "…") if len(preview) > 180 else preview,
                        }
                    elif isinstance(msg, HumanMessage):
                        last_messages.append(msg)
    except Exception as exc:  # noqa: BLE001
        log.exception("ask stream failed thread=%s", thread_id)
        local_trace.dump(output=str(exc), failed=True)
        yield {"type": "error", "message": str(exc)}
        return

    answer = "".join(streamed).strip()
    if not answer:
        for msg in reversed(last_messages):
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                text = _extract_text(msg.content).strip()
                if text:
                    answer = text
                    break

    # 用 checkpoint 里的完整消息做来源拼接，避免流式切片丢 metadata
    try:
        result = agent.get_state({"configurable": {"thread_id": thread_id}})
        values = (result.values if result else None) or {}
        messages = values.get("messages") or last_messages
    except Exception:  # noqa: BLE001
        messages = last_messages

    answer = finalize_answer_sources(answer, _sources_for_latest_turn(messages))
    touch_thread(
        thread_id,
        title=question.strip()[:40] or "新对话",
        preview=(answer or question)[:120],
        user_id=user_id,
    )
    log.info("ask stream done thread=%s answer_len=%s tools=%s", thread_id, len(answer), len(started_calls))
    local_trace.dump(output=answer, failed=False)
    yield {"type": "done", "answer": answer, "thread_id": thread_id}


def ask(question: str, *, thread_id: str = "default", user_id: str = "local") -> str:
    """同步问答，返回最终助手文本，并更新会话元数据。"""
    log.info("ask thread=%s q=%s", thread_id, question[:80].replace("\n", " "))
    collection, kb_name = _resolve_kb_for_thread(thread_id)
    set_active_collection(collection)
    set_active_kb_name(kb_name)
    reset_retrieved_sources()
    agent = get_agent()
    run_config, local_trace = agent_run_config(thread_id=thread_id, user_id=user_id)
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=question)]},
            run_config,
        )
    except Exception as exc:
        log.exception("ask failed thread=%s", thread_id)
        local_trace.dump(output=str(exc), failed=True)
        raise
    messages = result.get("messages") or []
    answer = ""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            text = _extract_text(msg.content).strip()
            if text:
                answer = text
                break

    answer = finalize_answer_sources(answer, _sources_for_latest_turn(messages))

    touch_thread(
        thread_id,
        title=question.strip()[:40] or "新对话",
        preview=(answer or question)[:120],
        user_id=user_id,
    )
    log.info("ask done thread=%s answer_len=%s", thread_id, len(answer))
    local_trace.dump(output=answer, failed=False)
    return answer


def get_thread_messages(thread_id: str) -> list[dict]:
    """从 checkpoint 读取可展示的 user/assistant 消息。"""
    checkpointer = get_checkpointer()
    checkpoint = checkpointer.get({"configurable": {"thread_id": thread_id}})
    if not checkpoint:
        return []
    channel_values = checkpoint.get("channel_values") or {}
    raw = channel_values.get("messages") or []
    out: list[dict] = []
    pending_sources: list[dict] = []
    for msg in raw:
        if isinstance(msg, ToolMessage):
            content = _extract_text(msg.content)
            if "页/段:" in content:
                pending_sources = parse_sources_from_tool_output(content)
            continue
        if isinstance(msg, HumanMessage):
            text = _extract_text(msg.content).strip()
            if text:
                out.append({"role": "user", "content": text})
            pending_sources = []
        elif isinstance(msg, AIMessage):
            if getattr(msg, "tool_calls", None):
                continue
            text = _extract_text(msg.content).strip()
            if text:
                text = finalize_answer_sources(text, pending_sources)
                pending_sources = []
                out.append({"role": "assistant", "content": text})
    return out


def delete_thread(thread_id: str) -> None:
    """删除会话元数据；checkpoint 随不再引用自然闲置（V1 不强制清 checkpoints 表）。"""
    delete_thread_meta(thread_id)
