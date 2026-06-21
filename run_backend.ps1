# Craftflow 後端本機啟動腳本（Windows / PowerShell）
# 用法：在專案根目錄執行  .\run_backend.ps1
# 2026-06-21：輸出同時導到 backend\logs\backend.log（每次啟動覆蓋），方便事後 debug。

$BackendDir = Join-Path $PSScriptRoot "backend"
$Venv       = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"
$LogDir     = Join-Path $BackendDir "logs"
$LogFile    = Join-Path $LogDir "backend.log"

if (-not (Test-Path $Venv)) {
    Write-Host "找不到 venv，請先執行：" -ForegroundColor Yellow
    Write-Host "  cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "啟動 Craftflow 後端（本機模式）... log -> $LogFile" -ForegroundColor Cyan
Set-Location $BackendDir
# 2>&1 合併 stderr；Tee-Object 同時印到 console 與寫檔
& $Venv main:app --reload --host 0.0.0.0 --port 8000 2>&1 | Tee-Object -FilePath $LogFile
