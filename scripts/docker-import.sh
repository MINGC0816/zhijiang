#!/usr/bin/env bash
# 无网服务器：加载镜像并启动
# 用法（在含 tar 的目录下）:
#   cp .env.example .env && vi .env
#   ./docker-import.sh
# 或: ./docker-import.sh /path/to/enterprise-kb-agent-1.0.tar

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${DIR}"

IMAGE="${IMAGE:-enterprise-kb-agent:1.0}"
TAR="${1:-${DIR}/enterprise-kb-agent-1.0.tar}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未找到 docker"
  exit 1
fi

if [[ ! -f "${TAR}" ]]; then
  echo "[ERROR] 找不到镜像包: ${TAR}"
  exit 1
fi

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "[INFO] 已复制 .env.example -> .env，请先编辑 VLLM_BASE_URL 等后再启动"
    echo "       编辑完成后重新执行本脚本"
    exit 1
  fi
  echo "[WARN] 无 .env，将使用 docker-compose 默认环境变量"
fi

echo "[INFO] loading ${TAR} ..."
docker load -i "${TAR}"

if [[ -f docker-compose.yml ]]; then
  echo "[INFO] docker compose up -d"
  docker compose up -d
else
  echo "[INFO] docker run ..."
  # shellcheck disable=SC2086
  docker run -d --name enterprise-kb-agent --restart unless-stopped \
    -p 3000:3000 -p 8002:8002 \
    --env-file .env \
    -v kb_data:/app/data \
    "${IMAGE}"
fi

echo ""
echo "[OK] 已启动"
echo "  问答: http://<服务器IP>:3000"
echo "  管理: http://<服务器IP>:3000/admin"
echo "  API : http://<服务器IP>:8002/docs"
echo "  查看日志: docker compose logs -f   或  docker logs -f enterprise-kb-agent"
