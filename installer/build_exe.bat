@echo off
REM Build dist\CraftflowSetup.exe with PyInstaller.
REM Uses its own venv (installer\.venv) so the shared pyenv site-packages
REM used by ComfyUI is never touched. Keep this file pure ASCII.
setlocal
cd /d "%~dp0.."
set "VENV=installer\.venv"
if not exist "%VENV%\Scripts\python.exe" (
    py -3.11 -m venv "%VENV%" || python -m venv "%VENV%" || goto :err
)
"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check -q "pyinstaller>=6.0" pytest || goto :err
"%VENV%\Scripts\python.exe" -m pytest -q installer\tests || goto :err
"%VENV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --console ^
    --name CraftflowSetup --paths installer ^
    --distpath dist --workpath build\installer --specpath build\installer ^
    installer\craftflow_setup.py || goto :err
echo.
echo [OK] dist\CraftflowSetup.exe
exit /b 0
:err
echo [ERROR] build failed
exit /b 1
