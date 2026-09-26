@echo off
chcp 65001 > nul
cd /d "%~dp0.."

echo ========================================================
echo 🤖 Starting Garmin Health AI Telegram Meal Bot Listener...
echo ========================================================

python main.py bot
pause
