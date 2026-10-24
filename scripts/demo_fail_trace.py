#!/usr/bin/env python
"""生成一条「改写后仍无法回答」的失败轨迹，供面试打开。

默认只写本地文件：
  data/traces/last_fail.json
  evals/sample_fail_trace.json

若配置了 LANGFUSE_PUBLIC_KEY / SECRET_KEY，会同步打到 Langfuse。
不依赖 vLLM。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.agent.rewrite import format_rewrite_result, rewrite_query
from src.config import PROJECT_ROOT
from src.tracing import TRACE_DIR, langfuse_enabled


QUESTION = "这个和去年比有变化吗？"
WHY = (
    "用户原话含指代（「这个」「和去年比」），单次 RAG 链会把原句直接 embedding，"
    "容易命中干扰文档或空结果。Agent 先 rewrite_query 补全省略，再 search_knowledge；"
    "知识库没有「同比变化」条款时应拒答，而不是编造。"
)


def build_payload() -> dict:
    rewritten = rewrite_query(QUESTION)
    rewrite_text = format_rewrite_result(rewritten)
    # 故意用「去年对比」这类库中不存在的约束，模拟检索失败
    search_query = rewritten["primary"] + " 相对去年 条款变更"
    search_output = "（未检索到相关内容）"
    answer = "知识库中未找到相关规定"
    now = datetime.now(timezone.utc).isoformat()
    return {
        "name": "kb-agent-fail-demo",
        "level": "ERROR",
        "input": QUESTION,
        "output": answer,
        "why": WHY,
        "started_at": now,
        "ended_at": now,
        "events": [
            {
                "type": "tool_start",
                "name": "rewrite_query",
                "input": QUESTION,
                "at": now,
            },
            {
                "type": "tool_end",
                "name": "rewrite_query",
                "output": rewrite_text,
                "at": now,
            },
            {
                "type": "tool_start",
                "name": "search_knowledge",
                "input": search_query,
                "at": now,
            },
            {
                "type": "tool_end",
                "name": "search_knowledge",
                "output": search_output,
                "at": now,
            },
        ],
        "rewrite": rewritten,
    }


def push_langfuse(payload: dict) -> str | None:
    if not langfuse_enabled():
        return None
    try:
        from langfuse import Langfuse
    except ImportError:
        print("[WARN] 已配置 Langfuse key，但未安装 langfuse：pip install 'langfuse>=2.60,<3'")
        return None

    from src.config import LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY

    kwargs = {
        "public_key": LANGFUSE_PUBLIC_KEY,
        "secret_key": LANGFUSE_SECRET_KEY,
    }
    if LANGFUSE_HOST:
        kwargs["host"] = LANGFUSE_HOST
    client = Langfuse(**kwargs)
    try:
        trace = client.trace(
            name=payload["name"],
            input=payload["input"],
            output=payload["output"],
            metadata={"why": payload["why"], "level": "ERROR"},
        )
        for evt in payload["events"]:
            if evt["type"] != "tool_start":
                continue
            # 下一条 tool_end 作为 output
            output = ""
            idx = payload["events"].index(evt)
            if idx + 1 < len(payload["events"]) and payload["events"][idx + 1]["type"] == "tool_end":
                output = payload["events"][idx + 1].get("output", "")
            trace.span(name=evt["name"], input=evt.get("input"), output=output)
        client.flush()
        url = getattr(trace, "get_trace_url", lambda: None)()
        return url
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Langfuse 上报失败: {exc}")
        return None


def main() -> None:
    payload = build_payload()
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    local = TRACE_DIR / "last_fail.json"
    sample = PROJECT_ROOT / "evals" / "sample_fail_trace.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    local.write_text(text, encoding="utf-8")
    sample.write_text(text, encoding="utf-8")
    print(f"[OK] local fail trace: {local}")
    print(f"[OK] sample (可入库 Git): {sample}")
    print(f"     question: {payload['input']}")
    print(f"     rewrite : {payload['rewrite']['primary']}")
    print(f"     output  : {payload['output']}")
    url = push_langfuse(payload)
    if url:
        print(f"[OK] Langfuse: {url}")
    elif langfuse_enabled():
        print("[INFO] 已配置 Langfuse，但未拿到 URL，请到控制台按 name=kb-agent-fail-demo 查找")
    else:
        print("[INFO] 未配置 LANGFUSE_*，仅本地轨迹。面试可打开 evals/sample_fail_trace.json")


if __name__ == "__main__":
    main()
