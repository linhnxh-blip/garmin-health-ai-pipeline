<#
.SYNOPSIS
    Script thiết lập tự động (One-Click Server Provisioning) trên máy chủ đích ASUS ROG Ally X (Windows 11).

.DESCRIPTION
    Thực hiện tuần tự các bước chuẩn hóa máy chủ ROG Ally X chạy 24/7:
    1. Kiểm tra hoặc Clone repository từ GitLab về C:\Servers\garmin-health-ai-pipeline.
    2. Khởi tạo file .env từ .env.example (cấu hình sẵn WEB_HOST=0.0.0.0 và tự điền Tailscale IP nếu có).
    3. Khôi phục cơ sở dữ liệu (SQLite / PostgreSQL / MySQL) qua restore_database.ps1.
    4. Thiết lập môi trường chạy:
       - Chế độ 'venv' (Mặc định, nhẹ nhất cho ROG Ally X): Tạo Python venv & cài đặt requirements.txt.
       - Chế độ 'docker': Build & khởi chạy container qua Docker Compose.
    5. Cấu hình Windows Power Plan chống Sleep/Hibernate khi cắm sạc AC (Tắt màn hình sau 5 phút để tiết kiệm điện).
    6. Mở cổng Inbound trên Windows Defender Firewall (Port 8000) cho mạng Tailscale & LAN Private.
    7. Đăng ký dịch vụ chạy ngầm 24/7 tự khởi động cùng Windows (NSSM Windows Service, PM2, hoặc Task Scheduler).

.PARAMETER GitLabUrl
    URL GitLab Repository để clone nếu thư mục đích chưa có code.

.PARAMETER InstallDir
    Thư mục cài đặt Server trên ROG Ally X (Mặc định: C:\Servers\garmin-health-ai-pipeline).

.PARAMETER RuntimeMode
    Môi trường chạy: 'venv' (Python Virtualenv trực tiếp - khuyến nghị) hoặc 'docker' (Docker Desktop/WSL2).

.PARAMETER ServiceManager
    Trình quản lý chạy ngầm 24/7: 'nssm' (Windows Service chuẩn), 'pm2', hoặc 'taskscheduler'.

.PARAMETER Port
    Cổng Web Dashboard / API Server (Mặc định: 8000).

.EXAMPLE
    # Chạy trực tiếp trong thư mục đã clone trên ROG Ally X (với quyền Administrator):
    .\setup_server.ps1 -RuntimeMode venv -ServiceManager nssm

    # Hoặc chạy từ bất kỳ đâu để tự động clone từ GitLab về C:\Servers\garmin-health-ai-pipeline:
    .\setup_server.ps1 -GitLabUrl "git@gitlab.com:username/garmin-health-ai-pipeline.git"
#>

param (
    [Parameter(Mandatory = $false)]
    [string]$GitLabUrl = "",

    [Parameter(Mandatory = $false)]
    [string]$InstallDir = "C:\Servers\garmin-health-ai-pipeline",

    [Parameter(Mandatory = $false)]
    [ValidateSet("venv", "docker")]
    [string]$RuntimeMode = "venv",

    [Parameter(Mandatory = $false)]
    [ValidateSet("nssm", "pm2", "taskscheduler", "none")]
    [string]$ServiceManager = "nssm",

    [Parameter(Mandatory = $false)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " 🎮 ASUS ROG ALLY X - LOCAL SERVER AUTO-SETUP (WINDOWS 11 24/7)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# Kiểm tra quyền Administrator (Cần cho PowerCfg, Firewall & Windows Service)
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) {
    Write-Host "⚠️ CẢNH BÁO: Bạn đang không chạy PowerShell với quyền Administrator!" -ForegroundColor Yellow
    Write-Host "   Các bước mở Firewall, chỉnh Powercfg và tạo NSSM Service sẽ cần quyền Admin." -ForegroundColor Yellow
}

# ==============================================================================
# BƯỚC 1: XÁC ĐỊNH THƯ MỤC DỰ ÁN HOẶC CLONE TỪ GITLAB
# ==============================================================================
$CurrentScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path (Join-Path $CurrentScriptDir "main.py")) {
    $InstallDir = $CurrentScriptDir
    Write-Host "📂 Đang chạy trực tiếp tại thư mục dự án: $InstallDir" -ForegroundColor Green
} else {
    $ParentDir = Split-Path -Parent $InstallDir
    if (-not (Test-Path $ParentDir)) {
        New-Item -ItemType Directory -Path $ParentDir -Force | Out-Null
    }
    if (-not (Test-Path (Join-Path $InstallDir ".git"))) {
        if ([string]::IsNullOrWhiteSpace($GitLabUrl)) {
            $GitLabUrl = Read-Host "👉 Nhập GitLab Repository URL để clone về $InstallDir"
        }
        Write-Host "⏬ Đang clone dự án từ GitLab về $InstallDir..." -ForegroundColor Yellow
        git clone $GitLabUrl $InstallDir
    } else {
        Write-Host "🔄 Thư mục $InstallDir đã tồn tại. Đang kéo code mới nhất (git pull)..." -ForegroundColor Yellow
        Push-Location $InstallDir
        git pull origin main
        Pop-Location
    }
}

Set-Location $InstallDir

# Tạo sẵn các thư mục vận hành
foreach ($dir in @("data", "data\backups", "data\reports", "backups", "logs")) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# ==============================================================================
# BƯỚC 2: PHÁT HIỆN TAILSCALE IP / LAN IP & KHỞI TẠO FILE .ENV
# ==============================================================================
Write-Host ""
Write-Host "--- [BƯỚC 2/6] CẤU HÌNH MẠNG TAILSCALE/LAN & BIẾN MÔI TRƯỜNG (.ENV) ---" -ForegroundColor Cyan

$TailscaleIP = ""
try {
    $tsStatus = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($tsStatus) {
        $TailscaleIP = (tailscale ip -4 2>$null | Select-Object -First 1).Trim()
    }
} catch {}

$LanIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL" -and $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -notlike "100.*"
} | Select-Object -First 1).IPAddress

$PreferredHostIP = if (-not [string]::IsNullOrWhiteSpace($TailscaleIP)) { $TailscaleIP }
                   elseif (-not [string]::IsNullOrWhiteSpace($LanIP)) { $LanIP }
                   else { "localhost" }

Write-Host "🌐 Địa chỉ IP phát hiện trên ROG Ally X:" -ForegroundColor Green
Write-Host "   - Tailscale IPv4 : $(if ($TailscaleIP) { $TailscaleIP } else { 'Chưa bật / Chưa cài Tailscale' })"
Write-Host "   - LAN IPv4 nội bộ: $(if ($LanIP) { $LanIP } else { 'Không xác định' })"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        # Tự động cập nhật BASE_WEB_URL theo IP thực tế của ROG Ally X
        $EnvContent = Get-Content ".env" -Raw
        $EnvContent = $EnvContent -replace 'BASE_WEB_URL="http://100\.x\.y\.z:8000"', "BASE_WEB_URL=`"http://${PreferredHostIP}:${Port}`""
        Set-Content ".env" -Value $EnvContent -Encoding UTF8
        Write-Host "✅ Đã khởi tạo file '.env' từ '.env.example' (BASE_WEB_URL=http://${PreferredHostIP}:${Port})." -ForegroundColor Green
        Write-Host "⚠️ LƯU Ý: Hãy mở file '.env' và điền TELEGRAM_BOT_TOKEN, GEMINI_API_KEY của bạn!" -ForegroundColor Yellow
    }
} else {
    Write-Host "✅ File '.env' đã tồn tại." -ForegroundColor Green
}

# ==============================================================================
# BƯỚC 3: KHÔI PHỤC DATABASE (NẾU CÓ FILE BACKUP TRONG THƯ MỤC BACKUPS/)
# ==============================================================================
Write-Host ""
Write-Host "--- [BƯỚC 3/6] KIỂM TRA & KHÔI PHỤC CƠ SỞ DỮ LIỆU ---" -ForegroundColor Cyan

$HasBackup = (Test-Path "backups\allyx_migration_bundle_latest.zip") -or (Test-Path "backups\db_backup.sqlite3")
if ($HasBackup -and (Test-Path ".\restore_database.ps1")) {
    if (Test-Path "backups\allyx_migration_bundle_latest.zip") {
        & .\restore_database.ps1 -DbType sqlite -BackupFile "backups\allyx_migration_bundle_latest.zip"
    } else {
        & .\restore_database.ps1 -DbType sqlite -BackupFile "backups\db_backup.sqlite3"
    }
} elseif (Test-Path "data\garmin_health.db") {
    Write-Host "✅ Đã có sẵn cơ sở dữ liệu tại 'data\garmin_health.db'." -ForegroundColor Green
} else {
    Write-Host "ℹ️ Chưa có file backup trong 'backups\'. Hệ thống sẽ tự khởi tạo SQLite DB mới hoặc bạn có thể chạy .\restore_database.ps1 sau." -ForegroundColor Yellow
}

# ==============================================================================
# BƯỚC 4: THIẾT LẬP MÔI TRƯỜNG CHẠY (PYTHON VENV HOẶC DOCKER)
# ==============================================================================
Write-Host ""
Write-Host "--- [BƯỚC 4/6] THIẾT LẬP MÔI TRƯỜNG CHẠY ($($RuntimeMode.ToUpper())) ---" -ForegroundColor Cyan

if ($RuntimeMode -eq "venv") {
    if (-not (Test-Path "venv\Scripts\python.exe")) {
        Write-Host "🐍 Đang tạo môi trường ảo Python (venv)..." -ForegroundColor Yellow
        python -m venv venv
    }
    $VenvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
    Write-Host "📦 Đang cài đặt / cập nhật thư viện từ requirements.txt..." -ForegroundColor Yellow
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt

    # Khởi tạo schema DB đảm bảo sẵn sàng
    & $VenvPython -c "from src.db.connection import init_db; init_db()"
    Write-Host "✅ Môi trường Python Virtualenv đã sẵn sàng!" -ForegroundColor Green
} elseif ($RuntimeMode -eq "docker") {
    Write-Host "🐳 Đang khởi dựng và chạy Docker Compose (garmin-web & garmin-bot)..." -ForegroundColor Yellow
    docker compose up -d --build
    Write-Host "✅ Các container Docker đã được khởi chạy (restart: unless-stopped)!" -ForegroundColor Green
}

# ==============================================================================
# BƯỚC 5: CẤU HÌNH WINDOWS POWER (CHỐNG SLEEP 24/7) & FIREWALL
# ==============================================================================
Write-Host ""
Write-Host "--- [BƯỚC 5/6] TỐI ƯU NGUỒN ĐIỆN ROG ALLY X (CHỐNG SLEEP) & MỞ FIREWALL ---" -ForegroundColor Cyan

if ($IsAdmin) {
    # 1. Chỉnh Powercfg không bao giờ Sleep/Hibernate khi cắm sạc AC, tắt màn hình sau 5 phút
    Write-Host "⚡ Đang cấu hình Windows Power Plan (AC Power = Never Sleep/Hibernate, Turn off screen = 5 mins)..." -ForegroundColor Yellow
    powercfg /change standby-timeout-ac 0
    powercfg /change hibernate-timeout-ac 0
    powercfg /change monitor-timeout-ac 5
    powercfg /change disk-timeout-ac 0
    Write-Host "✅ Đã khóa chống Sleep/Hibernate khi cắm sạc trên ROG Ally X!" -ForegroundColor Green

    # 2. Mở cổng Firewall Inbound cho Web Dashboard & API
    $RuleName = "GarminHealthAI_Server_Port_$Port"
    $ExistingRule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
    if ($ExistingRule) {
        Remove-NetFirewallRule -DisplayName $RuleName
    }
    New-NetFirewallRule -DisplayName $RuleName `
        -Direction Inbound `
        -LocalPort $Port `
        -Protocol TCP `
        -Action Allow `
        -Profile Private,Domain,Public `
        -Description "Cho phep truy cap Garmin Health AI Web Dashboard qua Tailscale va LAN" | Out-Null
    Write-Host "🛡️ Đã mở cổng TCP $Port trên Windows Defender Firewall!" -ForegroundColor Green
} else {
    Write-Host "⚠️ Bỏ qua bước Powercfg & Firewall vì chưa chạy quyền Admin. Hãy chạy lệnh sau trong PowerShell (Admin):" -ForegroundColor Yellow
    Write-Host "   powercfg /change standby-timeout-ac 0 ; powercfg /change hibernate-timeout-ac 0"
    Write-Host "   New-NetFirewallRule -DisplayName 'GarminHealthAI_Port_$Port' -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow"
}

# ==============================================================================
# BƯỚC 6: ĐĂNG KÝ TIẾN TRÌNH CHẠY NGẦM 24/7 (NSSM / PM2 / TASK SCHEDULER)
# ==============================================================================
Write-Host ""
Write-Host "--- [BƯỚC 6/6] ĐĂNG KÝ DỊCH VỤ CHẠY NGẦM 24/7 ($($ServiceManager.ToUpper())) ---" -ForegroundColor Cyan

$VenvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
$MainPy = Join-Path $InstallDir "main.py"

if ($RuntimeMode -eq "venv") {
    switch ($ServiceManager) {
        "nssm" {
            $NssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
            if (-not $NssmCmd) {
                Write-Host "ℹ️ Chưa tìm thấy NSSM trong PATH. Đang thử cài đặt NSSM tự động qua Winget..." -ForegroundColor Yellow
                try {
                    winget install --id NSSM.NSSM -e --accept-source-agreements --accept-package-agreements
                    $NssmCmd = Get-Command nssm -ErrorAction SilentlyContinue
                } catch {}
            }

            if ($NssmCmd -and $IsAdmin) {
                # Dịch vụ 1: Web Dashboard Server
                $WebSvc = "GarminHealthWeb"
                nssm stop $WebSvc 2>$null | Out-Null
                nssm remove $WebSvc confirm 2>$null | Out-Null
                nssm install $WebSvc $VenvPython "`"$MainPy`" web --host 0.0.0.0 --port $Port"
                nssm set $WebSvc AppDirectory $InstallDir
                nssm set $WebSvc AppStdout (Join-Path $InstallDir "logs\nssm_web_out.log")
                nssm set $WebSvc AppStderr (Join-Path $InstallDir "logs\nssm_web_err.log")
                nssm set $WebSvc AppExit Default Restart
                nssm set $WebSvc AppRestartDelay 5000
                nssm set $WebSvc Start SERVICE_AUTO_START
                nssm start $WebSvc

                # Dịch vụ 2: Telegram Bot Daemon
                $BotSvc = "GarminHealthBot"
                nssm stop $BotSvc 2>$null | Out-Null
                nssm remove $BotSvc confirm 2>$null | Out-Null
                nssm install $BotSvc $VenvPython "`"$MainPy`" bot"
                nssm set $BotSvc AppDirectory $InstallDir
                nssm set $BotSvc AppStdout (Join-Path $InstallDir "logs\nssm_bot_out.log")
                nssm set $BotSvc AppStderr (Join-Path $InstallDir "logs\nssm_bot_err.log")
                nssm set $BotSvc AppExit Default Restart
                nssm set $BotSvc AppRestartDelay 5000
                nssm set $BotSvc Start SERVICE_AUTO_START
                nssm start $BotSvc

                Write-Host "✅ Đã đăng ký và khởi chạy 2 Windows Services qua NSSM: '$WebSvc' & '$BotSvc'!" -ForegroundColor Green
            } else {
                Write-Host "⚠️ Không thể cài NSSM Service (Thiếu NSSM hoặc quyền Admin). Tự động chuyển sang đăng ký Windows Task Scheduler..." -ForegroundColor Yellow
                $ServiceManager = "taskscheduler"
            }
        }

        "pm2" {
            $Pm2Cmd = Get-Command pm2 -ErrorAction SilentlyContinue
            if ($Pm2Cmd) {
                pm2 start ecosystem.config.js
                pm2 save
                Write-Host "✅ Đã khởi chạy Web & Bot qua PM2 (ecosystem.config.js)!" -ForegroundColor Green
            } else {
                Write-Host "⚠️ Chưa cài đặt PM2 (`npm install -g pm2`). Hãy cài Node.js & PM2 hoặc dùng NSSM." -ForegroundColor Yellow
            }
        }
    }

    if ($ServiceManager -eq "taskscheduler" -and $IsAdmin) {
        # Tạo Task Scheduler chạy cả Web Server & Telegram Bot khi khởi động máy
        $WebAction = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$MainPy`" web --host 0.0.0.0 --port $Port" -WorkingDirectory $InstallDir
        $BotAction = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$MainPy`" bot" -WorkingDirectory $InstallDir
        $Trigger = New-ScheduledTaskTrigger -AtLogOn
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 0) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)

        Register-ScheduledTask -TaskName "GarminHealthWebServer" -Action $WebAction -Trigger $Trigger -Settings $Settings -Description "Garmin Health AI Web Dashboard (0.0.0.0:$Port)" -Force | Out-Null
        Register-ScheduledTask -TaskName "GarminHealthBotServer" -Action $BotAction -Trigger $Trigger -Settings $Settings -Description "Garmin Health AI Telegram Bot Listener" -Force | Out-Null

        Start-ScheduledTask -TaskName "GarminHealthWebServer"
        Start-ScheduledTask -TaskName "GarminHealthBotServer"
        Write-Host "✅ Đã đăng ký & chạy nền 'GarminHealthWebServer' và 'GarminHealthBotServer' trong Task Scheduler!" -ForegroundColor Green
    }
}

# Đăng ký thêm lịch chạy tự động thu thập & phân tích báo cáo hàng ngày (06:30, 11:30, 21:00) nếu chạy quyền Admin
if ($IsAdmin -and ($RuntimeMode -eq "venv")) {
    Write-Host "⏰ Đang thiết lập lịch tự động tổng hợp báo cáo sức khỏe hàng ngày (06:30 Sáng, 11:30 Trưa, 21:00 Tối)..." -ForegroundColor Yellow
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

    $MorningAction = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$MainPy`" run-daily --type morning" -WorkingDirectory $InstallDir
    Register-ScheduledTask -TaskName "GarminHealth_MorningReport" -Action $MorningAction -Trigger (New-ScheduledTaskTrigger -Daily -At "06:30") -Settings $Settings -Force | Out-Null

    $MiddayAction = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$MainPy`" run-daily --type midday" -WorkingDirectory $InstallDir
    Register-ScheduledTask -TaskName "GarminHealth_MiddayReport" -Action $MiddayAction -Trigger (New-ScheduledTaskTrigger -Daily -At "11:30") -Settings $Settings -Force | Out-Null

    $EveningAction = New-ScheduledTaskAction -Execute $VenvPython -Argument "`"$MainPy`" evening-checkin" -WorkingDirectory $InstallDir
    Register-ScheduledTask -TaskName "GarminHealth_EveningCheckin" -Action $EveningAction -Trigger (New-ScheduledTaskTrigger -Daily -At "21:00") -Settings $Settings -Force | Out-Null

    Write-Host "✅ Đã đăng ký lịch tự động gửi báo cáo Telegram 3 khung giờ/ngày!" -ForegroundColor Green
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " 🎉 HOÀN TẤT THIẾT LẬP LOCAL SERVER TRÊN ASUS ROG ALLY X!" -ForegroundColor Green
Write-Host " 🌐 Truy cập Web Dashboard từ máy hiện tại : http://localhost:$Port" -ForegroundColor White
if ($TailscaleIP) {
    Write-Host " 📱 Truy cập từ xa qua Tailscale (Mac/iPhone): http://${TailscaleIP}:${Port}" -ForegroundColor Cyan
}
if ($LanIP) {
    Write-Host " 💻 Truy cập qua mạng Wi-Fi LAN nội bộ       : http://${LanIP}:${Port}" -ForegroundColor Cyan
}
Write-Host "==================================================================" -ForegroundColor Green

