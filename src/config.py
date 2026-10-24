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
KBS_DIR = DATA_DIR / "kbs"
CHROMA_DIR = DATA_DIR / "chroma"
DB_DIR = DATA_DIR / "db"
LOG_DIR = DATA_DIR / "logs"
MODELS_DIR = PROJECT_ROOT / "models"
SAMPLES_DIR = PROJECT_ROOT / "samples"

TRACE_DIR = DATA_DIR / "traces"
for _d in (RAW_DIR, KBS_DIR, CHROMA_DIR, DB_DIR, LOG_DIR, MODELS_DIR, TRACE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://10.60.40.130:12333/v1")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen3.5-VL-122B")
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
RERANKER_MODEL_PATH = _resolve_embedding_path(
    os.getenv("RERANKER_MODEL_PATH", "models/bge-reranker-base")
)
RETRIEVE_TOP_K = int(os.getenv("RETRIEVE_TOP_K", "4"))
RETRIEVE_CANDIDATE_K = int(os.getenv("RETRIEVE_CANDIDATE_K", "20"))
RETRIEVE_MODE = (os.getenv("RETRIEVE_MODE", "hybrid_rerank") or "hybrid_rerank").strip()
RRF_K = int(os.getenv("RRF_K", "60"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "700"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))

CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "enterprise_kb")
CHECKPOINT_DB = DB_DIR / "kb_agent.db"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# 统一身份认证
JWT_SECRET = os.getenv("JWT_SECRET", "qizhi-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
JWT_KB_ADMIN_EXPIRE_MINUTES = int(os.getenv("JWT_KB_ADMIN_EXPIRE_MINUTES", "120"))
DEFAULT_ADMIN_USERNAME = os.getenv("DEFAULT_ADMIN_USERNAME", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")

# Langfuse（可选；未配置时只写 data/traces 本地轨迹）
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "").strip()
