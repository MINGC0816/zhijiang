#!/bin/sh
set -eu

cd /app

# 禁止运行时访问 HuggingFace（无网环境）
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE:-1}"

mkdir -p /app/data/raw /app/data/kbs /app/data/chroma /app/data/db /app/data/logs

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8002}"
WEB_PORT="${WEB_PORT:-3000}"

echo "[INFO] starting API on ${API_HOST}:${API_PORT}"
python -m uvicorn src.api.main:app \
  --host "${API_HOST}" \
  --port "${API_PORT}" \
  --workers 1 &
API_PID=$!

shutdown() {
  echo "[INFO] shutting down..."
  kill "${API_PID}" 2>/dev/null || true
  wait "${API_PID}" 2>/dev/null || true
  exit 0
}
trap shutdown INT TERM

echo "[INFO] waiting for API health..."
i=0
while [ "$i" -lt 90 ]; do
  if wget -q -O - "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo "[OK] API is ready"
    break
  fi
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "[ERROR] API process exited"
    exit 1
  fi
  i=$((i + 1))
  sleep 1
done
if [ "$i" -ge 90 ]; then
  echo "[ERROR] API health timeout"
  kill "${API_PID}" 2>/dev/null || true
  exit 1
fi

echo "[INFO] starting Web on 0.0.0.0:${WEB_PORT}"
echo "[INFO] 问答页 http://<服务器IP>:${WEB_PORT}"
echo "[INFO] 管理页 http://<服务器IP>:${WEB_PORT}/admin"
echo "[INFO] API    http://<服务器IP>:${API_PORT}/docs"

cd /app/web
export HOSTNAME=0.0.0.0
export PORT="${WEB_PORT}"
# Next standalone 服务端 rewrite 指向同容器 API
export API_ORIGIN="http://127.0.0.1:${API_PORT}"

exec node server.js
