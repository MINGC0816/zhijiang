# 企知 / 智匠 · 企业知识问答 Agent
# 单镜像：FastAPI (8002) + Next.js (3000)
# 大模型走内网 vLLM，不打进镜像；Embedding 权重随镜像打包。

# ---------- 前端构建 ----------
FROM node:20-bookworm-slim AS web-builder
WORKDIR /web

COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
# 同容器内 API，构建时写入 rewrite 目标
ENV API_ORIGIN=http://127.0.0.1:8002
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- Python 依赖 ----------
FROM python:3.11-slim-bookworm AS py-deps
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# CPU 版 PyTorch，避免拉 CUDA 巨大包
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
      torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -e .

# ---------- 运行镜像 ----------
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    EMBEDDING_MODEL_PATH=/app/models/bge-small-zh-v1.5 \
    API_PORT=8002 \
    WEB_PORT=3000 \
    NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Node 运行 Next standalone（从官方 node 镜像拷贝）
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
# node 可能依赖的动态库已在 bookworm-slim 中基本齐备

COPY --from=py-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=py-deps /usr/local/bin /usr/local/bin

COPY pyproject.toml README.md ./
COPY src ./src
COPY scripts ./scripts
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh \
    && pip install --no-cache-dir -e . --no-deps

# Embedding 模型（构建机必须已有完整 models/bge-small-zh-v1.5）
COPY models/bge-small-zh-v1.5 /app/models/bge-small-zh-v1.5

# Next.js standalone
COPY --from=web-builder /web/.next/standalone /app/web
COPY --from=web-builder /web/.next/static /app/web/.next/static
COPY --from=web-builder /web/public /app/web/public

RUN mkdir -p /app/data/raw /app/data/kbs /app/data/chroma /app/data/db /app/data/logs \
    && test -f /app/models/bge-small-zh-v1.5/config.json \
    && (test -f /app/models/bge-small-zh-v1.5/model.safetensors \
        -o -f /app/models/bge-small-zh-v1.5/pytorch_model.bin)

EXPOSE 3000 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:8002/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
