@echo off
chcp 65001 > nul
title Push Dev Changes to Remote (ROG Ally X -> PC Server)

echo ============================================================
echo 🚀 ROG ALLY X WORKSTATION - DEV PUSH PIPELINE
echo ============================================================

echo.
echo 🧪 Step 1: Running quick pytest verification...
python -m pytest
if %errorlevel% neq 0 (
    echo.
    echo ❌ Pytest check failed! Please fix test errors before pushing.
    pause
    exit /b %errorlevel%
)

echo.
echo 📦 Step 2: Staging changed code files...
git add .

echo.
echo 📝 Step 3: Creating git commit...
git commit -m "Dev from AllyX: %date% %time%"

echo.
echo ⬆️ Step 4: Pushing commits to GitHub (origin/main)...
git push origin main
if %errorlevel% neq 0 (
    echo.
    echo ❌ Git push failed! Please check your network connection or git status.
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo ✅ Đã đẩy code lên remote thành công!
echo 👉 Hãy chạy host_pull_updates.bat trên PC để áp dụng thay đổi.
echo ============================================================
echo.
pause
