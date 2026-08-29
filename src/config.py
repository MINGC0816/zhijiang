from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
load_dotenv()  # 也允许从仓库根目录继承

PROJECT_ROOT = _PROJECT_ROOT
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CHROMA_DIR = DATA_DIR / "chroma"
DB_DIR = DATA_DIR / "db"
LOG_DIR = DATA_DIR / "logs"
MODELS_DIR = PROJECT_ROOT / "models"
SAMPLES_DIR = PROJECT_ROOT / "samples"

for _d in (RAW_DIR, CHROMA_DIR, DB_DIR, LOG_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "xxx")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")
VLLM_MODEL = os.getenv("VLLM_MODEL", "xxx")
VLLM_ENABLE_THINKING = os.getenv("VLLM_ENABLE_THINKING", "false").lower() in (
    "1",
    "true",
    "yes",
)


def _resolve_embedding_path(raw: str) -> str:
    """相对路径按项目根解析；已存在的本地目录优先于 HF repo id。"""
    raw = (raw or "").strip() or "models/bge-small-zh-v1.5"
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    if candidate.is_dir():
        return str(candidate.resolve())
    # 仍可能是 HF hub id（如 BAAI/bge-small-zh-v1.5）
    return raw


EMBEDDING_MODEL_PATH = _resolve_embedding_path(
    os.getenv("EMBEDDING_MODEL_PATH", "models/bge-small-zh-v1.5")
)
RETRIEVE_TOP_K = int(os.getenv("RETRIEVE_TOP_K", "4"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "enterprise_kb")
CHECKPOINT_DB = DB_DIR / "kb_agent.db"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
