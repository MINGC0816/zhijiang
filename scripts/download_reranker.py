#!/usr/bin/env python
"""下载 BAAI/bge-reranker-base 到 models/bge-reranker-base（默认走 hf-mirror）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
TARGET = _ROOT / "models" / "bge-reranker-base"

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def main() -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit("需要 huggingface_hub，请先安装 sentence-transformers") from exc

    TARGET.mkdir(parents=True, exist_ok=True)
    print(f"downloading BAAI/bge-reranker-base -> {TARGET}")
    snapshot_download(
        repo_id="BAAI/bge-reranker-base",
        local_dir=str(TARGET),
    )
    print("[OK] reranker ready")
    print("确认 .env: RERANKER_MODEL_PATH=models/bge-reranker-base")


if __name__ == "__main__":
    sys.exit(main())
