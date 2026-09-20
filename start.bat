@echo off
echo Starting Craftflow...
REM 2026-09-20 perf: watch only backend\app instead of all of backend\.
REM Rationale: the default --reload scans .venv\ (tens of thousands of
REM files), uploads\ and craftflow.db, so generated images and DB backups
REM kept showing up as "N changes detected".
REM NOTE: no wildcards here on purpose. --reload-exclude .venv/* style
REM patterns get expanded into real paths before uvicorn sees them and
REM uvicorn then dies with "Got unexpected extra arguments".
REM Trade-off: editing backend\main.py no longer triggers a reload.
start "Craftflow Backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\uvicorn.exe main:app --reload --reload-dir app --host 0.0.0.0 --port 8000"
start "Craftflow Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo.
echo Backend  : http://localhost:8000
echo Frontend : http://localhost:3000
echo.
timeout /t 3 >nul
start http://localhost:3000
