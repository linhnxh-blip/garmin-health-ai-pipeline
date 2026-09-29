@echo off
chcp 65001 > nul
title Host Server - Pull Updates from Remote (PC Server)

echo ============================================================
echo 🖥️ PC CENTRAL SERVER - HOST PULL PIPELINE
echo ============================================================

cd /d "%~dp0"

echo.
echo [INFO] Stopping any running bot server processes...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*main.py bot*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul

if exist ".bot.lock" (
    echo [INFO] Removing .bot.lock file...
    del /f /q ".bot.lock"
)
if exist "data\.bot.lock" (
    echo [INFO] Removing data\.bot.lock file...
    del /f /q "data\.bot.lock"
)

echo.
echo 🔄 Pulling latest code changes from GitHub (origin/main)...
git pull --rebase origin main
if %errorlevel% neq 0 (
    echo.
    echo ❌ Git pull failed! Please check for local merge conflicts.
    pause
    exit /b %errorlevel%
)

echo.
echo 🧪 Running quick pytest verification...
python -m pytest

echo.
echo ============================================================
echo ✅ Server PC đã cập nhật mã nguồn mới nhất thành công!
echo ============================================================
echo.
pause
