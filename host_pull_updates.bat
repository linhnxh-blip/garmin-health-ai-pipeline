@echo off
chcp 65001 > nul
title Host Server - Pull Updates from Remote (PC Server)

echo ============================================================
echo 🖥️ PC CENTRAL SERVER - HOST PULL PIPELINE
echo ============================================================

echo.
echo 🔄 Pulling latest code changes from GitHub (origin/main)...
git pull origin main
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
