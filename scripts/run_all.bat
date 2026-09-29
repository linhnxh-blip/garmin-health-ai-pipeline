@echo off
chcp 65001 > nul
title Garmin Health AI Pipeline - Services Launcher

echo =======================================================
echo   Garmin Health AI Pipeline - Services Launcher
echo =======================================================

cd /d "%~dp0\.."

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found. Using system Python.
)

if not exist "logs" mkdir logs

echo [INFO] Launching Local Web Dashboard Server (http://localhost:8000)...
start "Garmin Web Dashboard" cmd /k "python main.py web"

echo [INFO] Launching Telegram Bot Listener...
start "Garmin Telegram Bot" cmd /k "python main.py bot"

echo =======================================================
echo   ✅ Both services started in background windows!
echo   - Local Web Dashboard: http://localhost:8000
echo   - Telegram Bot: Active & Listening
echo =======================================================
