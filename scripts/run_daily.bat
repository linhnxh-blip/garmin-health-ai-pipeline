@echo off
chcp 65001 > nul
cd /d "C:\Users\linhn\.gemini\antigravity-ide\scratch\garmin-health-ai-pipeline"

if not exist "logs" mkdir "logs"

echo ======================================================== >> logs\daily_run.log
echo [ %DATE% %TIME% ] Starting Daily Garmin Health AI Pipeline Run... >> logs\daily_run.log

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python main.py run-daily >> logs\daily_run.log 2>&1

echo [ %DATE% %TIME% ] Daily run completed. >> logs\daily_run.log
