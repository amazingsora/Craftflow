# Craftflow 後端本機啟動腳本（Windows / PowerShell）
# 用法：在專案根目錄執行  .\run_backend.ps1
# log 由後端自動寫到 data\logs\backend.log（RotatingFileHandler，5MB×3），任何啟動方式皆同。

$BackendDir = Join-Path $PSScriptRoot "backend"
$Venv       = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path $Venv)) {
    Write-Host "找不到 venv，請先執行：" -ForegroundColor Yellow
    Write-Host "  cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host "啟動 Craftflow 後端（本機模式）... log -> data\logs\backend.log" -ForegroundColor Cyan
Set-Location $BackendDir
& $Venv main:app --reload --reload-exclude "logs/*" --host 127.0.0.1 --port 8000
