# 无网服务器加载镜像并启动（PowerShell）
# 用法: .\docker-import.ps1
# 或:   .\docker-import.ps1 .\enterprise-kb-agent-1.0.tar

param(
    [string]$Tar = ""
)

$ErrorActionPreference = "Stop"
$Dir = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
Set-Location $Dir

$Image = if ($env:IMAGE) { $env:IMAGE } else { "enterprise-kb-agent:1.0" }
if (-not $Tar) {
    $Tar = Join-Path $Dir "enterprise-kb-agent-1.0.tar"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] 未找到 docker" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Tar)) {
    Write-Host "[ERROR] 找不到镜像包: $Tar" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Dir ".env"))) {
    $example = Join-Path $Dir ".env.example"
    if (Test-Path $example) {
        Copy-Item $example (Join-Path $Dir ".env")
        Write-Host "[INFO] 已复制 .env.example -> .env，请编辑 VLLM_BASE_URL 后重新执行" -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "[INFO] loading $Tar ..."
docker load -i $Tar
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$compose = Join-Path $Dir "docker-compose.yml"
if (Test-Path $compose) {
    Write-Host "[INFO] docker compose up -d"
    docker compose up -d
} else {
    Write-Host "[INFO] docker run ..."
    docker run -d --name enterprise-kb-agent --restart unless-stopped `
        -p 3000:3000 -p 8002:8002 `
        --env-file .env `
        -v kb_data:/app/data `
        $Image
}

Write-Host "[OK] 已启动"
Write-Host "  问答: http://<服务器IP>:3000"
Write-Host "  管理: http://<服务器IP>:3000/admin"
Write-Host "  日志: docker compose logs -f"
