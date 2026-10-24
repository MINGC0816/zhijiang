from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from src.config import CHECKPOINT_DB

_THREADS_DDL = """
CREATE TABLE IF NOT EXISTS chat_threads (
    thread_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '新对话',
    preview TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_threads_updated
ON chat_threads(updated_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_thread_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_THREADS_DDL)
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(chat_threads)").fetchall()
    }
    if "kb_id" not in cols:
        conn.execute("ALTER TABLE chat_threads ADD COLUMN kb_id TEXT")
    conn.commit()


@lru_cache(maxsize=1)
def _conn() -> sqlite3.Connection:
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_thread_schema(conn)
    return conn


def create_thread(
    *,
    user_id: str = "local",
    title: str = "新对话",
    kb_id: str | None = None,
) -> dict:
    thread_id = str(uuid.uuid4())
    ts = _now()
    conn = _conn()
    conn.execute(
        """
        INSERT INTO chat_threads(
            thread_id, title, preview, user_id, kb_id, created_at, updated_at
        )
        VALUES (?, ?, '', ?, ?, ?, ?)
        """,
        (thread_id, title, user_id, kb_id, ts, ts),
    )
    conn.commit()
    return get_thread(thread_id)  # type: ignore[return-value]


def get_thread(thread_id: str) -> dict | None:
    row = _conn().execute(
        "SELECT * FROM chat_threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    return dict(row) if row else None


def list_threads(*, user_id: str = "local", limit: int = 50) -> list[dict]:
    rows = _conn().execute(
        """
        SELECT * FROM chat_threads
        WHERE user_id = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def touch_thread(
    thread_id: str,
    *,
    title: str | None = None,
    preview: str | None = None,
    user_id: str = "local",
) -> dict:
    """不存在则插入；存在则更新 updated_at / title / preview。"""
    existing = get_thread(thread_id)
    ts = _now()
    conn = _conn()
    if existing is None:
        conn.execute(
            """
            INSERT INTO chat_threads(thread_id, title, preview, user_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                thread_id,
                (title or "新对话")[:80],
                (preview or "")[:120],
                user_id,
                ts,
                ts,
            ),
        )
    else:
        new_title = existing["title"]
        if title and existing["title"] in ("新对话", ""):
            new_title = title[:80]
        new_preview = preview[:120] if preview is not None else existing["preview"]
        conn.execute(
            """
            UPDATE chat_threads
            SET title = ?, preview = ?, updated_at = ?
            WHERE thread_id = ?
            """,
            (new_title, new_preview, ts, thread_id),
        )
    conn.commit()
    return get_thread(thread_id)  # type: ignore[return-value]


def delete_thread_meta(thread_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM chat_threads WHERE thread_id = ?", (thread_id,))
    conn.commit()
    return cur.rowcount > 0
