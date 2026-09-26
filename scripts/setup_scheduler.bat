@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

set TASK_NAME=GarminHealthAIPipeline
set BATCH_PATH=%~dp0run_daily.bat
set DEFAULT_TIME=04:45

rem Read REPORT_SCHEDULE_TIME from .env if present
set SCHEDULE_TIME=
if exist "%~dp0..\.env" (
    for /f "tokens=1,2 delims==" %%A in ('type "%~dp0..\.env"') do (
        if /i "%%A"=="REPORT_SCHEDULE_TIME" (
            set SCHEDULE_TIME=%%B
        )
    )
)

rem Remove quotes if any
if defined SCHEDULE_TIME (
    set SCHEDULE_TIME=!SCHEDULE_TIME:"=!
    set SCHEDULE_TIME=!SCHEDULE_TIME:'=!
)

rem Fallback to command argument or DEFAULT_TIME
if "%~1" neq "" (
    set SCHEDULE_TIME=%~1
)

if "%SCHEDULE_TIME%"=="" (
    set SCHEDULE_TIME=%DEFAULT_TIME%
)

echo ========================================================
echo ⏰ Cấu hình Windows Task Scheduler cho Garmin Health AI Pipeline
echo 📌 Task Name: %TASK_NAME%
echo 📌 Daily Time: %SCHEDULE_TIME%
echo 📌 Script Path: %BATCH_PATH%
echo ========================================================

schtasks /create /tn "%TASK_NAME%" /tr "\"%BATCH_PATH%\"" /sc daily /st %SCHEDULE_TIME% /f

if %ERRORLEVEL% equ 0 (
    echo ✅ Đã tạo Task Scheduler thành công! Tự động phát báo cáo mỗi sáng lúc %SCHEDULE_TIME%.
) else (
    echo ❌ Lỗi khi đăng ký Task Scheduler. Hãy thử chạy CMD với quyền Administrator.
)

pause
