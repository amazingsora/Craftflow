# Craftflow 後端本機啟動腳本（Windows / PowerShell）
# 用法：在專案根目錄執行  .\run_backend.ps1

$BackendDir = Join-Path $PSScriptRoot "backend"
$Venv       = Join-Path $BackendDir ".venv\Scripts\uvicorn.exe"

if (-not (Test-Path $Venv)) {
    Write-Host "找不到 venv，請先執行：" -ForegroundColor Yellow
    Write-Host "  cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}

Write-Host "啟動 Craftflow 後端（本機模式）..." -ForegroundColor Cyan
Set-Location $BackendDir
& $Venv main:app --reload --host 0.0.0.0 --port 8000
