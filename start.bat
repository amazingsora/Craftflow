@echo off
echo Starting Craftflow...
start "Craftflow Backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\uvicorn.exe main:app --reload --reload-exclude "logs/*" --host 0.0.0.0 --port 8000"
start "Craftflow Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo.
echo Backend  : http://localhost:8000
echo Frontend : http://localhost:3000
echo.
timeout /t 3 >nul
start http://localhost:3000
