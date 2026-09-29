@echo off
chcp 65001 > nul
title Register Task Scheduler - Garmin Health Bot Server

echo =======================================================
echo   Registering Garmin Health Bot Server Task Scheduler
echo =======================================================

cd /d "%~dp0"
set "BOT_SCRIPT=%~dp0start_bot_server.bat"

echo [INFO] Registering Task Scheduler 'GarminHealthBotServer'...
echo [INFO] Target script: %BOT_SCRIPT%

powershell -Command " $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c \"\"%BOT_SCRIPT%\"\"' ; $trigger = New-ScheduledTaskTrigger -AtLogOn ; $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0 ; Register-ScheduledTask -TaskName 'GarminHealthBotServer' -Action $action -Trigger $trigger -Settings $settings -Description 'Garmin Health AI Pipeline - Telegram Bot Server' -Force "

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Task Scheduler 'GarminHealthBotServer' created successfully!
    echo [INFO] The bot server will automatically start whenever you log into Windows PC.
) else (
    echo.
    echo [ERROR] Failed to register task. Please right-click this batch file and select 'Run as administrator'.
)

pause
