#!/usr/bin/env bash
# 有网机构建镜像并导出为 tar，便于拷到无网服务器
# 用法: ./scripts/docker-export.sh
# 产物: dist/enterprise-kb-agent-1.0.tar  + dist/docker-compose.yml + dist/.env.example

set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
IMAGE="${IMAGE:-enterprise-kb-agent:1.0}"
OUT_DIR="${OUT_DIR:-${ROOT}/dist}"
TAR_NAME="${TAR_NAME:-enterprise-kb-agent-1.0.tar}"

if [[ ! -f models/bge-small-zh-v1.5/config.json ]]; then
  echo "[ERROR] 缺少 models/bge-small-zh-v1.5，请先按 models/README.md 准备 Embedding 权重"
  exit 1
fi
if [[ ! -f models/bge-small-zh-v1.5/model.safetensors && ! -f models/bge-small-zh-v1.5/pytorch_model.bin ]]; then
  echo "[ERROR] 缺少 model.safetensors / pytorch_model.bin"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] 未找到 docker，请先安装 Docker Desktop / Docker Engine"
  exit 1
fi

mkdir -p "${OUT_DIR}"

echo "[INFO] building ${IMAGE} ..."
docker build -t "${IMAGE}" .

echo "[INFO] saving to ${OUT_DIR}/${TAR_NAME} ..."
docker save "${IMAGE}" -o "${OUT_DIR}/${TAR_NAME}"

cp docker-compose.yml "${OUT_DIR}/docker-compose.yml"
cp .env.example "${OUT_DIR}/.env.example"
cp docker/README.md "${OUT_DIR}/README-Docker.md"
cp scripts/docker-import.sh "${OUT_DIR}/docker-import.sh"
chmod +x "${OUT_DIR}/docker-import.sh"

# 体积提示
if command -v du >/dev/null 2>&1; then
  du -h "${OUT_DIR}/${TAR_NAME}" || true
fi

echo ""
echo "[OK] 离线包已生成: ${OUT_DIR}/"
echo "  1) 将 dist/ 目录拷到无网服务器"
echo "  2) 编辑 .env（从 .env.example 复制），填写内网 VLLM_BASE_URL"
echo "  3) 执行: ./docker-import.sh"
