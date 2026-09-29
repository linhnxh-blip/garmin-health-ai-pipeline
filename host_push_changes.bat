@echo off
chcp 65001 > nul
title Host Push Changes - Garmin Health AI Pipeline

echo =======================================================
echo   Host Git Push - Source Code Logic Only
echo =======================================================

cd /d "%~dp0"

echo [INFO] Current Git Status:
git status --short
echo.

set /p COMMIT_MSG="Nhap commit message (Bấm Enter de dung mac dinh 'Host update: source code logic'): "
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Host update: source code logic

echo.
echo [INFO] Staging source code files...
git add src/ tests/ config/ main.py *.bat *.md .gitignore requirements.txt

echo [INFO] Committing changes...
git commit -m "%COMMIT_MSG%"

echo [INFO] Pushing logic changes to origin main...
git push origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Source code logic updates successfully pushed to GitHub!
    echo [NOTE] Database (garmin_health.db) and .env were safely excluded.
) else (
    echo.
    echo [ERROR] Git push failed. Please check network connection or git status.
)

pause
