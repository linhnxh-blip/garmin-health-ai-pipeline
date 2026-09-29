@echo off
chcp 65001 > nul
title Garmin Health AI Pipeline - SQLite Backup Engine

echo =======================================================
echo   Garmin Health AI Pipeline - Instant SQLite Backup
echo =======================================================

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] Virtual environment not found. Using system Python environment.
)

python scripts/backup_db.py

echo.
pause
