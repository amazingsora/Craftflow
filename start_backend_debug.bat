@echo off
REM Diagnostic launcher: runs the backend in THIS window with no --reload,
REM and tees everything (including import-time tracebacks that never reach
REM data\logs\backend.log) into data\logs\startup_err.txt
cd /d "%~dp0backend"
echo Writing output to ..\data\logs\startup_err.txt
.venv\Scripts\python.exe -X faulthandler -m uvicorn main:app --host 0.0.0.0 --port 8000 > "%~dp0data\logs\startup_err.txt" 2>&1
echo.
echo ---- exit code: %ERRORLEVEL% ----
type "%~dp0data\logs\startup_err.txt"
pause
