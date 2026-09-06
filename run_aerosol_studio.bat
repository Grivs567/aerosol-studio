@echo off
setlocal enabledelayedexpansion

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%"

if defined VIRTUAL_ENV (
    set "PY=python"
) else if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PY=venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo Starting Aerosol Studio...
"!PY!" --version
if errorlevel 1 (
    echo [ERROR] Python was not found. Activate your environment or add Python to PATH.
    pause
    exit /b 1
)

set "PYTHONPATH=%REPO_ROOT%src;%PYTHONPATH%"
"!PY!" -m aerosolstudio

echo.
pause
endlocal
