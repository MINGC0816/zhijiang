from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from src.config import CHECKPOINT_DB, DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME
from src.auth.security import hash_password

_AUTH_DDL = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    username TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    ip_address TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created ON audit_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def _conn() -> sqlite3.Connection:
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    conn = _conn()
    conn.executescript(_AUTH_DDL)
    conn.commit()


def seed_default_admin() -> None:
    conn = _conn()
    row = conn.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (DEFAULT_ADMIN_USERNAME,),
    ).fetchone()
    if row:
        return
    ts = _now()
    conn.execute(
        """
        INSERT INTO users(
            user_id, username, password_hash, display_name, email,
            role, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'admin', 'active', ?, ?)
        """,
        (
            str(uuid.uuid4()),
            DEFAULT_ADMIN_USERNAME,
            hash_password(DEFAULT_ADMIN_PASSWORD),
            "系统管理员",
            "",
            ts,
            ts,
        ),
    )
    conn.commit()


def _user_row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if not row:
        return None
    data = dict(row)
    data.pop("password_hash", None)
    return data


def get_user_by_id(user_id: str) -> dict | None:
    row = _conn().execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return _user_row_to_dict(row)


def get_user_by_username(username: str) -> dict | None:
    row = _conn().execute(
        "SELECT * FROM users WHERE username = ?",
        (username.strip(),),
    ).fetchone()
    if not row:
        return None
    return dict(row)


def create_user(
    *,
    username: str,
    password: str,
    display_name: str = "",
    email: str = "",
    role: str = "user",
) -> dict:
    if role != "user":
        raise ValueError("仅允许创建普通用户")
    user_id = str(uuid.uuid4())
    ts = _now()
    conn = _conn()
    conn.execute(
        """
        INSERT INTO users(
            user_id, username, password_hash, display_name, email,
            role, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'user', 'active', ?, ?)
        """,
        (
            user_id,
            username.strip(),
            hash_password(password),
            display_name.strip() or username.strip(),
            email.strip(),
            ts,
            ts,
        ),
    )
    conn.commit()
    user = get_user_by_id(user_id)
    assert user is not None
    return user


def list_users(*, role: str | None = "user", limit: int = 200) -> list[dict]:
    conn = _conn()
    if role:
        rows = conn.execute(
            """
            SELECT user_id, username, display_name, email, role, status,
                   created_at, updated_at
            FROM users
            WHERE role = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (role, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT user_id, username, display_name, email, role, status,
                   created_at, updated_at
            FROM users
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_user(
    user_id: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    status: str | None = None,
) -> dict | None:
    user = get_user_by_id(user_id)
    if not user:
        return None
    if user["role"] == "admin":
        raise ValueError("不能通过此接口修改管理员账号")
    fields: list[str] = []
    values: list[Any] = []
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(display_name.strip())
    if email is not None:
        fields.append("email = ?")
        values.append(email.strip())
    if status is not None:
        if status not in {"active", "frozen"}:
            raise ValueError("status 必须为 active 或 frozen")
        fields.append("status = ?")
        values.append(status)
    if not fields:
        return user
    fields.append("updated_at = ?")
    values.append(_now())
    values.append(user_id)
    _conn().execute(
        f"UPDATE users SET {', '.join(fields)} WHERE user_id = ?",
        values,
    )
    _conn().commit()
    return get_user_by_id(user_id)


def reset_user_password(user_id: str, new_password: str) -> bool:
    user = get_user_by_id(user_id)
    if not user:
        return False
    if user["role"] == "admin":
        raise ValueError("不能重置管理员密码")
    _conn().execute(
        """
        UPDATE users SET password_hash = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (hash_password(new_password), _now(), user_id),
    )
    _conn().commit()
    return True


def delete_user(user_id: str) -> bool:
    user = get_user_by_id(user_id)
    if not user:
        return False
    if user["role"] == "admin":
        raise ValueError("不能删除管理员账号")
    cur = _conn().execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    _conn().commit()
    return cur.rowcount > 0


def write_audit_log(
    *,
    action: str,
    user_id: str | None = None,
    username: str | None = None,
    detail: str = "",
    ip_address: str = "",
) -> None:
    _conn().execute(
        """
        INSERT INTO audit_logs(user_id, username, action, detail, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, username, action, detail, ip_address, _now()),
    )
    _conn().commit()


def list_audit_logs(
    *,
    action: str | None = None,
    user_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if action:
        clauses.append("action = ?")
        params.append(action)
    if user_id:
        clauses.append("user_id = ?")
        params.append(user_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    rows = _conn().execute(
        f"""
        SELECT id, user_id, username, action, detail, ip_address, created_at
        FROM audit_logs
        {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]
