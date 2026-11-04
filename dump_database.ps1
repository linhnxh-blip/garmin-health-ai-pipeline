<#
.SYNOPSIS
    Script trích xuất & sao lưu Cơ Sở Dữ Liệu (Database Export) kèm đóng gói di chuyển sang ASUS ROG Ally X.

.DESCRIPTION
    Hỗ trợ 3 hệ quản trị CSDL phổ biến:
    1. SQLite (Mặc định của dự án Garmin Health AI Pipeline):
       - Sử dụng sqlite3 Online Backup API để tạo bản sao an toàn (không sợ lock/corrupt file WAL) ra `backups/garmin_health_<timestamp>.db` và bản chuẩn `backups/db_backup.sqlite3`.
       - Tùy chọn đóng gói kèm Garmin Session Tokens (`data/.garmin_tokens`), ảnh bữa ăn (`data/nutrition_images`), báo cáo (`data/reports`) thành 1 file nén `backups/allyx_migration_bundle_<timestamp>.zip`.
    2. PostgreSQL:
       - Chạy `pg_dump -U <user> -h <host> -p <port> -d <dbname> -F c -b -v -f backups/db_backup.dump`.
    3. MySQL / MariaDB:
       - Chạy `mysqldump -u <user> -p -h <host> -P <port> <dbname> > backups/db_backup.sql`.

.PARAMETER DbType
    Loại Database: 'sqlite' (mặc định), 'postgres', hoặc 'mysql'.

.PARAMETER SqlitePath
    Đường dẫn tới file SQLite nguồn (Mặc định: 'data/garmin_health.db').

.PARAMETER DbUser
    Username cho PostgreSQL hoặc MySQL (Mặc định: 'postgres' hoặc 'root').

.PARAMETER DbName
    Tên Database cho PostgreSQL hoặc MySQL.

.PARAMETER DbHost
    Host của Database server (Mặc định: 'localhost').

.PARAMETER DbPort
    Port của Database server (5432 cho Postgres, 3306 cho MySQL).

.EXAMPLE
    .\dump_database.ps1
    .\dump_database.ps1 -DbType postgres -DbUser postgres -DbName garmin_health
    .\dump_database.ps1 -DbType mysql -DbUser root -DbName garmin_health
#>

param (
    [Parameter(Mandatory = $false)]
    [ValidateSet("sqlite", "postgres", "mysql")]
    [string]$DbType = "sqlite",

    [Parameter(Mandatory = $false)]
    [string]$SqlitePath = "data\garmin_health.db",

    [Parameter(Mandatory = $false)]
    [string]$DbUser = "postgres",

    [Parameter(Mandatory = $false)]
    [string]$DbName = "garmin_health",

    [Parameter(Mandatory = $false)]
    [string]$DbHost = "localhost",

    [Parameter(Mandatory = $false)]
    [int]$DbPort = 0
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$BackupDir = Join-Path $ProjectRoot "backups"
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " 💾 DATABASE EXPORT & BACKUP TOOL (LOẠI DB: $($DbType.ToUpper()))" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

switch ($DbType) {
    "sqlite" {
        $SourceDb = Join-Path $ProjectRoot $SqlitePath
        if (-not (Test-Path $SourceDb)) {
            # Tìm kiếm các file .db hoặc .sqlite3 khác trong dự án nếu đường dẫn mặc định không thấy
            $FoundDb = Get-ChildItem -Path $ProjectRoot -Include *.db, *.sqlite, *.sqlite3 -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notmatch "\\backups\\" } | Select-Object -First 1
            if ($FoundDb) {
                $SourceDb = $FoundDb.FullName
            } else {
                Write-Host "❌ Không tìm thấy file SQLite tại: $SourceDb" -ForegroundColor Red
                exit 1
            }
        }

        $BackupTimestampFile = Join-Path $BackupDir "garmin_health_$Timestamp.db"
        $BackupLatestFile = Join-Path $BackupDir "db_backup.sqlite3"

        Write-Host "📦 Đang trích xuất an toàn SQLite từ: $SourceDb" -ForegroundColor Yellow

        # Ưu tiên gọi Python sqlite3.backup API để đảm bảo tính toàn vẹn ACID ngay cả khi DB đang mở
        $PythonExe = if (Test-Path "venv\Scripts\python.exe") { "venv\Scripts\python.exe" }
                     elseif (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" }
                     else { "python" }

        $PyCode = @"
import sqlite3, shutil
src = r'$SourceDb'
dst = r'$BackupTimestampFile'
latest = r'$BackupLatestFile'
s_conn = sqlite3.connect(src)
d_conn = sqlite3.connect(dst)
with d_conn:
    s_conn.backup(d_conn)
d_conn.close()
s_conn.close()
shutil.copy2(dst, latest)
"@
        try {
            & $PythonExe -c $PyCode
            Write-Host "✅ Đã sao lưu SQLite an toàn qua sqlite3 Online Backup API!" -ForegroundColor Green
        } catch {
            Write-Host "⚠️ Python backup gặp lỗi, chuyển sang chế độ Copy-Item trực tiếp..." -ForegroundColor Yellow
            Copy-Item -Path $SourceDb -Destination $BackupTimestampFile -Force
            Copy-Item -Path $SourceDb -Destination $BackupLatestFile -Force
        }

        $FileSizeMB = [math]::Round((Get-Item $BackupTimestampFile).Length / 1MB, 2)
        Write-Host "   - File theo Timestamp : $BackupTimestampFile ($FileSizeMB MB)" -ForegroundColor Gray
        Write-Host "   - File chuẩn Restore  : $BackupLatestFile ($FileSizeMB MB)" -ForegroundColor Gray

        # Đóng gói thành gói ZIP tiện gửi qua Tailscale/LAN sang ROG Ally X
        $BundleZip = Join-Path $BackupDir "allyx_migration_bundle_$Timestamp.zip"
        $BundleLatestZip = Join-Path $BackupDir "allyx_migration_bundle_latest.zip"
        Write-Host "🗜️ Đang nén gói dữ liệu Migration (Database + Garmin Tokens + Reports)..." -ForegroundColor Yellow

        $PathsToArchive = @($BackupLatestFile)
        if (Test-Path "data\.garmin_tokens") { $PathsToArchive += "data\.garmin_tokens" }
        if (Test-Path "data\reports") { $PathsToArchive += "data\reports" }
        if (Test-Path "data\nutrition_images") { $PathsToArchive += "data\nutrition_images" }

        Compress-Archive -Path $PathsToArchive -DestinationPath $BundleZip -Force
        Copy-Item -Path $BundleZip -Destination $BundleLatestZip -Force
        $ZipSizeMB = [math]::Round((Get-Item $BundleZip).Length / 1MB, 2)
        Write-Host "✅ Đã đóng gói Bundle Migration: $BundleZip ($ZipSizeMB MB)" -ForegroundColor Green
    }

    "postgres" {
        if ($DbPort -eq 0) { $DbPort = 5432 }
        $DumpFileTimestamp = Join-Path $BackupDir "db_backup_$Timestamp.dump"
        $DumpFileLatest = Join-Path $BackupDir "db_backup.dump"
        $SqlFileLatest = Join-Path $BackupDir "db_backup_postgres.sql"

        Write-Host "🐘 Đang chạy pg_dump cho PostgreSQL Database '$DbName' (User: $DbUser, Host: ${DbHost}:${DbPort})..." -ForegroundColor Yellow
        Write-Host "   (Lưu ý: Nhập mật khẩu PostgreSQL nếu được hỏi, hoặc đặt biến môi trường `$env:PGPASSWORD` trước khi chạy)" -ForegroundColor Gray

        # 1. Xuất định dạng Custom (-F c -b -v) tối ưu cho pg_restore
        pg_dump -U $DbUser -h $DbHost -p $DbPort -d $DbName -F c -b -v -f $DumpFileTimestamp
        Copy-Item -Path $DumpFileTimestamp -Destination $DumpFileLatest -Force

        # 2. Xuất thêm bản Plain SQL dự phòng
        pg_dump -U $DbUser -h $DbHost -p $DbPort -d $DbName --clean --if-exists -f $SqlFileLatest

        Write-Host "✅ Xuất PostgreSQL hoàn tất:" -ForegroundColor Green
        Write-Host "   - Custom Dump : $DumpFileLatest"
        Write-Host "   - Plain SQL   : $SqlFileLatest"
    }

    "mysql" {
        if ($DbPort -eq 0) { $DbPort = 3306 }
        if ($DbUser -eq "postgres") { $DbUser = "root" }
        $SqlFileTimestamp = Join-Path $BackupDir "db_backup_$Timestamp.sql"
        $SqlFileLatest = Join-Path $BackupDir "db_backup.sql"

        Write-Host "🐬 Đang chạy mysqldump cho MySQL/MariaDB Database '$DbName' (User: $DbUser, Host: ${DbHost}:${DbPort})..." -ForegroundColor Yellow
        cmd /c "mysqldump -u $DbUser -p -h $DbHost -P $DbPort --single-transaction --routines --triggers $DbName > `"$SqlFileTimestamp`""
        Copy-Item -Path $SqlFileTimestamp -Destination $SqlFileLatest -Force

        Write-Host "✅ Xuất MySQL/MariaDB hoàn tất:" -ForegroundColor Green
        Write-Host "   - SQL File : $SqlFileLatest"
    }
}

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host " 🎉 HOÀN TẤT TRÍCH XUẤT DỮ LIỆU TẠI THƯ MỤC: $BackupDir" -ForegroundColor Green
Write-Host " 📌 Cách chuyển thư mục 'backups/' sang ASUS ROG Ally X qua Tailscale/LAN:" -ForegroundColor Cyan
Write-Host "    - Cách 1 (Taildrop): chuột phải vào file trong 'backups/' -> Send to ROG Ally X qua Tailscale" -ForegroundColor White
Write-Host "    - Cách 2 (SCP/SMB) : scp backups\db_backup.sqlite3 <user>@<Tailscale-IP-AllyX>:C:/Servers/garmin-health-ai-pipeline/backups/" -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Green
