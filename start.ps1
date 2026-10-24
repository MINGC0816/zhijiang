# 智匠 Windows 一键启动（同终端，不另开窗口）
# 用法: .\start.ps1  或  .\start.bat

param(
    [int]$ApiPort = 8002,
    [int]$WebPort = 3000
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Set-Location $Root

$script:ApiProc = $null
$ApiOut = Join-Path $Root "data\api.out.log"
$ApiErr = Join-Path $Root "data\api.err.log"

function Get-PidsOnPort([int]$Port) {
    $pids = @()
    try {
        $pids = @(
            Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique |
                Where-Object { $_ -and $_ -ne 0 }
        )
    } catch {}
    if ($pids.Count -eq 0) {
        $pattern = ":" + $Port + "\s+.*LISTENING"
        $lines = netstat -ano 2>$null | Select-String $pattern
        foreach ($line in $lines) {
            $parts = @(($line.ToString() -split "\s+") | Where-Object { $_ })
            if ($parts.Count -gt 0) {
                $procId = $parts[-1]
                if ($procId -match "^\d+$" -and [int]$procId -ne 0) {
                    $pids += [int]$procId
                }
            }
        }
        $pids = @($pids | Select-Object -Unique)
    }
    return @($pids)
}

function Stop-Tree([int]$ProcessId) {
    if (-not $ProcessId -or $ProcessId -eq 0) { return }
    # 通过 cmd 重定向，避免 taskkill 找不到进程时被 PowerShell 当成终止错误
    cmd.exe /c "taskkill /F /T /PID $ProcessId >nul 2>&1" | Out-Null
}

function Free-Port([int]$Port, [string]$Label = "") {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $tag = if ($Label) { " ($Label)" } else { "" }
        $pids = Get-PidsOnPort $Port
        if ($pids.Count -eq 0) {
            Write-Host ("[INFO] port :{0}{1} is free" -f $Port, $tag)
            return
        }

        Write-Host ("[INFO] killing old process on :{0}{1} -> {2}" -f $Port, $tag, ($pids -join ", "))
        foreach ($procId in $pids) { Stop-Tree $procId }

        # 最多重试 5 次，直到端口真正释放
        for ($i = 0; $i -lt 5; $i++) {
            Start-Sleep -Milliseconds 500
            $left = Get-PidsOnPort $Port
            if ($left.Count -eq 0) {
                Write-Host ("[OK] port :{0}{1} released" -f $Port, $tag)
                return
            }
            Write-Host ("[INFO] retry kill :{0} -> {1}" -f $Port, ($left -join ", "))
            foreach ($procId in $left) { Stop-Tree $procId }
        }

        $still = Get-PidsOnPort $Port
        if ($still.Count -gt 0) {
            Write-Host ("[WARN] port :{0} still held by {1}" -f $Port, ($still -join ", ")) -ForegroundColor Yellow
        }
    } finally {
        $ErrorActionPreference = $prev
    }
}

function Ensure-PortsFree {
    Write-Host "[INFO] checking ports before start..."
    Free-Port $ApiPort "API"
    Free-Port $WebPort "Web"
}

function Stop-AllServices {
    # 清理阶段绝不能因 taskkill 噪音而再抛错
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        Write-Host ""
        Write-Host "[INFO] shutting down, releasing ports..."
        if ($script:ApiProc -and -not $script:ApiProc.HasExited) {
            Stop-Tree $script:ApiProc.Id
        }
        Free-Port $ApiPort "API"
        Free-Port $WebPort "Web"
        Write-Host "[OK] ports released"
    } catch {
        Write-Host ("[WARN] cleanup: {0}" -f $_.Exception.Message)
    } finally {
        $ErrorActionPreference = $prev
    }
}

Write-Host "========================================"
Write-Host " Zhijiang - start API + Web (same terminal)"
Write-Host "========================================"

$pyCandidates = @(
    (Join-Path $Root "..\.venv\Scripts\python.exe"),
    (Join-Path $Root ".venv\Scripts\python.exe")
)
$Python = $pyCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) {
    Write-Host "[ERROR] venv python not found" -ForegroundColor Red
    Write-Host "Run from repo root: .\.venv\Scripts\pip install -e .\enterprise_kb_agent"
    exit 1
}

if (-not (Test-Path (Join-Path $Root ".env"))) {
    $example = Join-Path $Root ".env.example"
    if (Test-Path $example) {
        Copy-Item $example (Join-Path $Root ".env")
        Write-Host "[INFO] copied .env.example -> .env"
    }
}

$webDir = Join-Path $Root "web"
if (-not (Test-Path (Join-Path $webDir "package.json"))) {
    Write-Host "[ERROR] web/ missing" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
    Write-Host "[INFO] npm install..."
    Push-Location $webDir
    npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit 1 }
    Pop-Location
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
Ensure-PortsFree

try {
    Write-Host "[INFO] starting API on http://127.0.0.1:$ApiPort (background, no extra window)"
    foreach ($f in @($ApiOut, $ApiErr)) {
        if (Test-Path $f) { Remove-Item $f -Force -ErrorAction SilentlyContinue }
    }

    $script:ApiProc = Start-Process -PassThru -WindowStyle Hidden `
        -WorkingDirectory $Root `
        -FilePath $Python `
        -ArgumentList @(
            "-m", "uvicorn", "src.api.main:app",
            "--host", "127.0.0.1",
            "--port", "$ApiPort",
            "--reload",
            "--reload-dir", "src"
        ) `
        -RedirectStandardOutput $ApiOut `
        -RedirectStandardError $ApiErr

    Write-Host "[INFO] waiting for API health... (logs: data\api.*.log)"
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        if ($script:ApiProc.HasExited) { break }
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch {}
        Start-Sleep -Seconds 1
    }
    if (-not $ok) {
        Write-Host "[ERROR] API failed. Last logs:" -ForegroundColor Red
        if (Test-Path $ApiErr) { Get-Content $ApiErr -Tail 40 -ErrorAction SilentlyContinue }
        if (Test-Path $ApiOut) { Get-Content $ApiOut -Tail 20 -ErrorAction SilentlyContinue }
        throw "API health timeout"
    }
    Write-Host "[OK] API is ready"

    Write-Host "[INFO] Frontend http://127.0.0.1:$WebPort"
    Write-Host "[INFO] Admin     http://127.0.0.1:$WebPort/admin"
    Write-Host "[INFO] API docs  http://127.0.0.1:$ApiPort/docs"
    Write-Host "[INFO] Ctrl+C stops both and frees ports"
    Write-Host "----------------------------------------"

    Push-Location $webDir
    $env:API_ORIGIN = "http://127.0.0.1:$ApiPort"
    Set-Content -Path (Join-Path $webDir ".env.local") -Value "API_ORIGIN=http://127.0.0.1:$ApiPort" -Encoding ASCII
    npm run dev -- --port $WebPort --hostname 127.0.0.1
} finally {
    Pop-Location -ErrorAction SilentlyContinue
    Stop-AllServices
}
