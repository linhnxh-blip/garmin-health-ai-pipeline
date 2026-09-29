@echo off
chcp 65001 > nul
title Garmin Health AI Pipeline - Central Bot Server

echo =======================================================
echo   Garmin Health AI Pipeline - Central Bot Server
echo =======================================================

:: Switch to script directory
cd /d "%~dp0"

:: 1. Activate Python Virtual Environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found. Using system Python environment.
)

:: 2. Ensure logs directory exists
if not exist "logs" mkdir logs

:: 3. Remove stale lock files if present
if exist ".bot.lock" (
    echo [INFO] Removing stale .bot.lock file...
    del /f /q ".bot.lock"
)
if exist "data\.bot.lock" (
    echo [INFO] Removing stale data\.bot.lock file...
    del /f /q "data\.bot.lock"
)

:: 4. Run Telegram Bot Server with unbuffered output logged to logs/bot_runner.log and console
set PYTHONUNBUFFERED=1
echo [INFO] Starting Telegram Bot Server...
echo [INFO] Logging output to logs\bot_runner.log and console.
echo =======================================================

powershell -Command "python main.py bot 2>&1 | Tee-Object -FilePath 'logs\bot_runner.log' -Append"

pause
