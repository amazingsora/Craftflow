@echo off
chcp 65001 >nul
echo.
echo  ╔══════════════════════════════════════╗
echo  ║      Craftflow 一鍵安裝程式          ║
echo  ╚══════════════════════════════════════╝
echo.

REM ── Python 版本檢查 ───────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請先安裝 Python 3.11：
    echo        winget install --id Python.Python.3.11 -e
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [✓] Python %PYVER%

REM ── Node.js 版本檢查 ──────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [錯誤] 找不到 Node.js，請先安裝 Node.js 20 LTS：
    echo        winget install --id OpenJS.NodeJS.LTS -e
    pause & exit /b 1
)
for /f %%v in ('node --version 2^>^&1') do set NODEVER=%%v
echo [✓] Node.js %NODEVER%

echo.

REM ── [1/3] 後端 venv + pip install ────────────────────────────
echo [1/3] 安裝後端套件...
if not exist "%~dp0backend\.venv" (
    echo      建立虛擬環境...
    python -m venv "%~dp0backend\.venv"
)
echo      安裝 Python 套件（首次約 2-3 分鐘）...
"%~dp0backend\.venv\Scripts\pip" install -r "%~dp0backend\requirements.txt" -q --disable-pip-version-check
if errorlevel 1 (
    echo [錯誤] pip install 失敗，請確認 requirements.txt 存在
    pause & exit /b 1
)
echo [✓] 後端套件安裝完成

REM ── [2/3] 前端 npm install ────────────────────────────────────
echo [2/3] 安裝前端套件...
cd /d "%~dp0frontend"
npm install --silent
if errorlevel 1 (
    echo [錯誤] npm install 失敗
    pause & exit /b 1
)
echo [✓] 前端套件安裝完成

REM ── [3/3] .env ────────────────────────────────────────────────
echo [3/3] 設定環境檔...
if not exist "%~dp0.env" (
    copy "%~dp0.env.example" "%~dp0.env" >nul
    echo [✓] .env 已建立（從 .env.example 複製）
    echo      模型可在前端「設定」頁面即時切換，無需重啟
) else (
    echo [✓] .env 已存在，略過
)

echo.
echo  ╔══════════════════════════════════════╗
echo  ║  安裝完成！                          ║
echo  ║  請確認 Ollama 已啟動後              ║
echo  ║  執行 start.bat 啟動服務             ║
echo  ╚══════════════════════════════════════╝
echo.
pause
