from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import CHROMA_COLLECTION, CHECKPOINT_DB, KBS_DIR, RAW_DIR
from src.ingest.loaders import SUPPORTED_SUFFIXES
from src.logging_config import get_logger

log = get_logger("qizhi.kb")

_KB_DDL = """
CREATE TABLE IF NOT EXISTS knowledge_bases (
    kb_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    collection_name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kbs_name ON knowledge_bases(name);
"""

_DEFAULT_KB_NAME = "默认知识库"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def _conn():
    import sqlite3

    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_kb_db() -> None:
    conn = _conn()
    conn.executescript(_KB_DDL)
    conn.commit()


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _collection_name_for_kb(kb_id: str) -> str:
    slug = kb_id.replace("-", "_")
    return f"kb_{slug}"


def _validate_kb_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("知识库名称不能为空")
    if len(cleaned) > 80:
        raise ValueError("知识库名称不能超过 80 个字符")
    return cleaned


def get_kb_raw_dir(kb_id: str) -> Path:
    path = KBS_DIR / kb_id / "raw"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_kbs() -> list[dict[str, Any]]:
    rows = _conn().execute(
        "SELECT * FROM knowledge_bases ORDER BY created_at ASC",
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_kb(kb_id: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT * FROM knowledge_bases WHERE kb_id = ?",
        (kb_id,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def get_kb_by_collection(collection_name: str) -> dict[str, Any] | None:
    row = _conn().execute(
        "SELECT * FROM knowledge_bases WHERE collection_name = ?",
        (collection_name,),
    ).fetchone()
    return _row_to_dict(row) if row else None


def create_kb(*, name: str, description: str = "") -> dict[str, Any]:
    title = _validate_kb_name(name)
    desc = (description or "").strip()[:500]
    kb_id = str(uuid.uuid4())
    collection_name = _collection_name_for_kb(kb_id)
    ts = _now()
    conn = _conn()
    conn.execute(
        """
        INSERT INTO knowledge_bases(
            kb_id, name, description, collection_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (kb_id, title, desc, collection_name, ts, ts),
    )
    conn.commit()
    get_kb_raw_dir(kb_id)
    log.info("kb created id=%s name=%s collection=%s", kb_id, title, collection_name)
    return get_kb(kb_id)  # type: ignore[return-value]


def update_kb(
    kb_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    row = get_kb(kb_id)
    if not row:
        raise ValueError("知识库不存在")
    if name is None and description is None:
        raise ValueError("请提供要更新的字段")
    new_name = _validate_kb_name(name) if name is not None else row["name"]
    if description is not None:
        new_desc = (description or "").strip()[:500]
    else:
        new_desc = row.get("description") or ""
    ts = _now()
    conn = _conn()
    conn.execute(
        """
        UPDATE knowledge_bases
        SET name = ?, description = ?, updated_at = ?
        WHERE kb_id = ?
        """,
        (new_name, new_desc, ts, kb_id),
    )
    conn.commit()
    log.info("kb updated id=%s name=%s", kb_id, new_name)
    return get_kb(kb_id)  # type: ignore[return-value]


def delete_kb(kb_id: str) -> bool:
    row = get_kb(kb_id)
    if not row:
        return False
    kb_path = KBS_DIR / kb_id
    if kb_path.is_dir():
        shutil.rmtree(kb_path, ignore_errors=True)
    conn = _conn()
    conn.execute("DELETE FROM knowledge_bases WHERE kb_id = ?", (kb_id,))
    conn.commit()
    log.info("kb deleted id=%s name=%s", kb_id, row.get("name"))
    return True


def ensure_default_kb() -> dict[str, Any]:
    """确保存在默认知识库，并绑定 legacy Chroma 集合。"""
    init_kb_db()
    rows = list_kbs()
    if rows:
        return rows[0]

    kb_id = str(uuid.uuid4())
    ts = _now()
    conn = _conn()
    conn.execute(
        """
        INSERT INTO knowledge_bases(
            kb_id, name, description, collection_name, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            kb_id,
            _DEFAULT_KB_NAME,
            "系统默认知识库（含历史迁移文档）",
            CHROMA_COLLECTION,
            ts,
            ts,
        ),
    )
    conn.commit()
    get_kb_raw_dir(kb_id)
    log.info("default kb created id=%s collection=%s", kb_id, CHROMA_COLLECTION)
    return get_kb(kb_id)  # type: ignore[return-value]


def migrate_legacy_raw_files(default_kb: dict[str, Any] | None = None) -> int:
    """将扁平 data/raw 下的文档迁移到默认知识库目录。"""
    default_kb = default_kb or ensure_default_kb()
    target_dir = get_kb_raw_dir(default_kb["kb_id"])
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for path in sorted(RAW_DIR.iterdir()):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        dest = target_dir / path.name
        if dest.exists():
            continue
        shutil.move(str(path), str(dest))
        moved += 1
        log.info("migrated raw file %s -> %s", path.name, dest)
    return moved


def delete_chroma_collection(collection_name: str) -> None:
    try:
        import chromadb

        from src.config import CHROMA_DIR

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
    except Exception:
        log.exception("delete chroma collection failed name=%s", collection_name)
