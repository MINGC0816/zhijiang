from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from src.config import (
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    TRACE_DIR,
)
from src.logging_config import get_logger

log = get_logger("qizhi.trace")


def langfuse_enabled() -> bool:
    return bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)


class LocalJsonTraceHandler(BaseCallbackHandler):
    """始终写入 data/traces/，无 Langfuse 账号时也能留面试用轨迹。"""

    def __init__(self, *, session_id: str, user_id: str = "", name: str = "kb-agent"):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id
        self.name = name
        self.events: list[dict[str, Any]] = []
        self.error: str | None = None
        self._started = datetime.now(timezone.utc).isoformat()

    def on_tool_start(self, serialized, input_str, **kwargs):  # noqa: ANN001
        name = (serialized or {}).get("name") or "tool"
        self.events.append(
            {
                "type": "tool_start",
                "name": name,
                "input": input_str,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def on_tool_end(self, output, **kwargs):  # noqa: ANN001
        text = output if isinstance(output, str) else str(output)
        self.events.append(
            {
                "type": "tool_end",
                "output": text[:800],
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def on_tool_error(self, error, **kwargs):  # noqa: ANN001
        self.error = str(error)
        self.events.append(
            {
                "type": "tool_error",
                "error": str(error),
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def on_chain_error(self, error, **kwargs):  # noqa: ANN001
        self.error = str(error)
        self.events.append(
            {
                "type": "chain_error",
                "error": str(error),
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def dump(self, *, output: str = "", failed: bool = False) -> Path:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": self.name,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "started_at": self._started,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "level": "ERROR" if (failed or self.error) else "DEFAULT",
            "error": self.error,
            "output": (output or "")[:2000],
            "events": self.events,
        }
        latest = TRACE_DIR / "last.json"
        latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if failed or self.error:
            fail_path = TRACE_DIR / "last_fail.json"
            fail_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return fail_path
        return latest


def get_langfuse_handler(*, session_id: str, user_id: str = ""):
    if not langfuse_enabled():
        return None
    try:
        from langfuse.callback import CallbackHandler
    except ImportError:
        try:
            from langfuse.langchain import CallbackHandler
        except ImportError:
            log.warning("langfuse 未安装，仅写本地 traces")
            return None
    try:
        return CallbackHandler(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST or None,
            session_id=session_id,
            user_id=user_id or None,
        )
    except TypeError:
        return CallbackHandler(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST or None,
        )
    except Exception:
        log.exception("langfuse handler init failed")
        return None


def build_callbacks(*, session_id: str, user_id: str = "", name: str = "kb-agent"):
    local = LocalJsonTraceHandler(session_id=session_id, user_id=user_id, name=name)
    callbacks: list = [local]
    remote = get_langfuse_handler(session_id=session_id, user_id=user_id)
    if remote is not None:
        callbacks.append(remote)
    return callbacks, local


def agent_run_config(*, thread_id: str, user_id: str = "") -> tuple[dict, LocalJsonTraceHandler]:
    callbacks, local = build_callbacks(session_id=thread_id, user_id=user_id)
    return {
        "configurable": {"thread_id": thread_id},
        "callbacks": callbacks,
    }, local
