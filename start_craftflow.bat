@echo off
chcp 65001 >nul
title Craftflow Launcher
cd /d "%~dp0"

echo [1/3] Starting ComfyUI...
start "ComfyUI" cmd /k "cd /d F:\wk\ComfyUI_portable && run_nvidia_gpu.bat"

echo [2/3] Checking Docker Desktop...
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop not running - launching it now...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Waiting for Docker engine to start (this may take 30-60 seconds)...
    :wait_docker
    timeout /t 5 /nobreak >nul
    docker info >nul 2>&1
    if errorlevel 1 goto wait_docker
    echo Docker is ready.
)

echo [3/3] Starting Craftflow containers...
docker compose up -d
if errorlevel 1 (
    echo.
    echo [ERROR] docker compose failed.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo  Craftflow is ready!
echo  Frontend : http://localhost:3000
echo  Backend  : http://localhost:8000/docs
echo  ComfyUI  : http://localhost:8188
echo ==========================================
echo.
pause
