#!/usr/bin/env bash
# 智匠 Linux/macOS 一键启动（同终端）
# 用法: ./start.sh
# 环境变量可选: API_PORT=8002 WEB_PORT=3000

set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

API_PORT="${API_PORT:-8002}"
WEB_PORT="${WEB_PORT:-3000}"
API_PID=""
API_LOG="${ROOT}/data/api.log"

echo "========================================"
echo " Zhijiang - start API + Web (same terminal)"
echo "========================================"

if [[ -x "../.venv/bin/python" ]]; then
  PY="../.venv/bin/python"
elif [[ -x ".venv/bin/python" ]]; then
  PY=".venv/bin/python"
else
  echo "[ERROR] venv python not found"
  echo "From repo root: .venv/bin/pip install -e ./enterprise_kb_agent"
  exit 1
fi

if [[ ! -f ".env" && -f ".env.example" ]]; then
  cp .env.example .env
  echo "[INFO] copied .env.example -> .env"
fi

if [[ ! -f "web/package.json" ]]; then
  echo "[ERROR] web/ missing"
  exit 1
fi

if [[ ! -d "web/node_modules" ]]; then
  echo "[INFO] npm install..."
  (cd web && npm install)
fi

mkdir -p data

free_port() {
  local port="$1"
  local label="${2:-}"
  local pids=""
  local i left

  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  elif command -v fuser >/dev/null 2>&1; then
    pids="$(fuser -t "tcp:${port}" 2>/dev/null || true)"
  fi

  if [[ -z "${pids}" ]]; then
    echo "[INFO] port :${port}${label:+ ($label)} is free"
    return 0
  fi

  echo "[INFO] killing old process on :${port}${label:+ ($label)} -> ${pids}"
  # shellcheck disable=SC2086
  kill -9 ${pids} 2>/dev/null || true

  for i in 1 2 3 4 5; do
    sleep 0.4
    left=""
    if command -v lsof >/dev/null 2>&1; then
      left="$(lsof -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
    elif command -v fuser >/dev/null 2>&1; then
      left="$(fuser -t "tcp:${port}" 2>/dev/null || true)"
    fi
    if [[ -z "${left}" ]]; then
      echo "[OK] port :${port}${label:+ ($label)} released"
      return 0
    fi
    echo "[INFO] retry kill :${port} -> ${left}"
    # shellcheck disable=SC2086
    kill -9 ${left} 2>/dev/null || true
  done
  echo "[WARN] port :${port} may still be busy"
}

echo "[INFO] checking ports before start..."
free_port "${API_PORT}" "API"
free_port "${WEB_PORT}" "Web"

cleanup() {
  echo ""
  echo "[INFO] shutting down, releasing ports..."
  if [[ -n "${API_PID}" ]] && kill -0 "${API_PID}" 2>/dev/null; then
    kill "${API_PID}" 2>/dev/null || true
    wait "${API_PID}" 2>/dev/null || true
  fi
  free_port "${API_PORT}" "API"
  free_port "${WEB_PORT}" "Web"
  echo "[OK] ports released"
}
trap cleanup EXIT INT TERM

echo "[INFO] starting API on http://127.0.0.1:${API_PORT} (background, same terminal)"
: > "${API_LOG}"
"${PY}" -m uvicorn src.api.main:app \
  --host 127.0.0.1 \
  --port "${API_PORT}" \
  --reload \
  --reload-dir src \
  >>"${API_LOG}" 2>&1 &
API_PID=$!

echo "[INFO] waiting for API health... (log: data/api.log)"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo "[OK] API is ready"
    break
  fi
  if ! kill -0 "${API_PID}" 2>/dev/null; then
    echo "[ERROR] API process exited. Last log:"
    tail -n 40 "${API_LOG}" || true
    exit 1
  fi
  sleep 1
  if [[ "$i" -eq 60 ]]; then
    echo "[ERROR] API health timeout. Last log:"
    tail -n 40 "${API_LOG}" || true
    exit 1
  fi
done

echo "[INFO] Frontend http://127.0.0.1:${WEB_PORT}"
echo "[INFO] Admin     http://127.0.0.1:${WEB_PORT}/admin"
echo "[INFO] API docs  http://127.0.0.1:${API_PORT}/docs"
echo "[INFO] Ctrl+C stops both and frees ports"
echo "----------------------------------------"

cd "${ROOT}/web"
echo "API_ORIGIN=http://127.0.0.1:${API_PORT}" > .env.local
export API_ORIGIN="http://127.0.0.1:${API_PORT}"
npm run dev -- --port "${WEB_PORT}" --hostname 127.0.0.1
