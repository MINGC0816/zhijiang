# 企知 Docker 离线部署（有网机构建 → 无网机运行）
# 用法（PowerShell）: .\scripts\docker-export.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Image = if ($env:IMAGE) { $env:IMAGE } else { "enterprise-kb-agent:1.0" }
$OutDir = if ($env:OUT_DIR) { $env:OUT_DIR } else { Join-Path $Root "dist" }
$TarName = if ($env:TAR_NAME) { $env:TAR_NAME } else { "enterprise-kb-agent-1.0.tar" }

$modelDir = Join-Path $Root "models\bge-small-zh-v1.5"
if (-not (Test-Path (Join-Path $modelDir "config.json"))) {
    Write-Host "[ERROR] 缺少 models/bge-small-zh-v1.5，请先准备 Embedding 权重" -ForegroundColor Red
    exit 1
}
$hasWeight = (Test-Path (Join-Path $modelDir "model.safetensors")) -or (Test-Path (Join-Path $modelDir "pytorch_model.bin"))
if (-not $hasWeight) {
    Write-Host "[ERROR] 缺少 model.safetensors / pytorch_model.bin" -ForegroundColor Red
    exit 1
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 docker，请先安装 Docker Desktop" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Write-Host "[INFO] building $Image ..."
docker build -t $Image .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$tarPath = Join-Path $OutDir $TarName
Write-Host "[INFO] saving to $tarPath ..."
docker save $Image -o $tarPath
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Copy-Item (Join-Path $Root "docker-compose.yml") (Join-Path $OutDir "docker-compose.yml") -Force
Copy-Item (Join-Path $Root ".env.example") (Join-Path $OutDir ".env.example") -Force
Copy-Item (Join-Path $Root "docker\README.md") (Join-Path $OutDir "README-Docker.md") -Force
Copy-Item (Join-Path $Root "scripts\docker-import.ps1") (Join-Path $OutDir "docker-import.ps1") -Force
Copy-Item (Join-Path $Root "scripts\docker-import.sh") (Join-Path $OutDir "docker-import.sh") -Force

$size = (Get-Item $tarPath).Length / 1GB
Write-Host ("[OK] 离线包大小约 {0:N2} GB" -f $size)
Write-Host "[OK] 目录: $OutDir"
Write-Host "  1) 将 dist/ 拷到无网服务器"
Write-Host "  2) 复制 .env.example 为 .env 并填写 VLLM_BASE_URL"
Write-Host "  3) 执行 docker-import 脚本启动"
