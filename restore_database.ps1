<#
.SYNOPSIS
    Khôi phục Cơ Sở Dữ Liệu (Database Restore) trên máy chủ đích ASUS ROG Ally X.

.DESCRIPTION
    Hỗ trợ khôi phục tự động cho cả 3 loại CSDL:
    1. SQLite (Mặc định):
       - Nếu truyền vào file `.zip` (ví dụ `allyx_migration_bundle_latest.zip`), giải nén toàn bộ DB + Garmin Tokens + Reports vào đúng vị trí.
       - Nếu truyền vào file `.db` / `.sqlite3` (ví dụ `backups\db_backup.sqlite3`), kiểm tra tính toàn vẹn `PRAGMA integrity_check` rồi copy vào `data\garmin_health.db`.
    2. PostgreSQL:
       - Sử dụng `pg_restore -U <user> -h <host> -p <port> -d <dbname> --clean --if-exists -v backups/db_backup.dump`.
    3. MySQL / MariaDB:
       - Sử dụng `mysql -u <user> -p -h <host> -P <port> <dbname> < backups/db_backup.sql`.

.EXAMPLE
    .\restore_database.ps1
    .\restore_database.ps1 -BackupFile "backups\db_backup.sqlite3"
    .\restore_database.ps1 -DbType postgres -BackupFile "backups\db_backup.dump" -DbUser postgres -DbName garmin_health
    .\restore_database.ps1 -DbType mysql -BackupFile "backups\db_backup.sql" -DbUser root -DbName garmin_health
#>

param (
    [Parameter(Mandatory = $false)]
    [ValidateSet("sqlite", "postgres", "mysql")]
    [string]$DbType = "sqlite",

    [Parameter(Mandatory = $false)]
    [string]$BackupFile = "",

    [Parameter(Mandatory = $false)]
    [string]$TargetSqlitePath = "data\garmin_health.db",

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

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " 🔄 DATABASE RESTORE TOOL TRÊN ASUS ROG ALLY X ($($DbType.ToUpper()))" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

switch ($DbType) {
    "sqlite" {
        # Tự động dò tìm file backup trong thư mục backups/ nếu không chỉ định
        if ([string]::IsNullOrWhiteSpace($BackupFile)) {
            if (Test-Path "backups\db_backup.sqlite3") {
                $BackupFile = "backups\db_backup.sqlite3"
            } else {
                $LatestDb = Get-ChildItem -Path "backups", "data\backups" -Filter "*.db" -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending | Select-Object -First 1
                if ($LatestDb) {
                    $BackupFile = $LatestDb.FullName
                }
            }
        }

        if ([string]::IsNullOrWhiteSpace($BackupFile) -or (-not (Test-Path $BackupFile))) {
            Write-Host "❌ Không tìm thấy file backup SQLite để khôi phục!" -ForegroundColor Red
            Write-Host "👉 Hãy chép file 'db_backup.sqlite3' từ máy nguồn vào thư mục 'backups\' trên ROG Ally X rồi chạy lại." -ForegroundColor Yellow
            exit 1
        }

        $DestDb = Join-Path $ProjectRoot $TargetSqlitePath
        $DestDir = Split-Path -Parent $DestDb
        if (-not (Test-Path $DestDir)) {
            New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
        }

        # Nếu là gói bundle .zip thì giải nén trước
        if ($BackupFile.EndsWith(".zip")) {
            Write-Host "🗜️ Phát hiện gói Migration ZIP: $BackupFile. Đang giải nén..." -ForegroundColor Yellow
            $TempExtract = Join-Path $ProjectRoot "backups\_temp_extract"
            if (Test-Path $TempExtract) { Remove-Item $TempExtract -Recurse -Force }
            Expand-Archive -Path $BackupFile -DestinationPath $TempExtract -Force

            if (Test-Path "$TempExtract\db_backup.sqlite3") {
                Copy-Item "$TempExtract\db_backup.sqlite3" -Destination $DestDb -Force
            }
            if (Test-Path "$TempExtract\.garmin_tokens") {
                Copy-Item "$TempExtract\.garmin_tokens" -Destination "data\.garmin_tokens" -Recurse -Force
                Write-Host "✅ Đã khôi phục Garmin Session Tokens (data\.garmin_tokens)." -ForegroundColor Green
            }
            if (Test-Path "$TempExtract\reports") {
                Copy-Item "$TempExtract\reports" -Destination "data\reports" -Recurse -Force
            }
            if (Test-Path "$TempExtract\nutrition_images") {
                Copy-Item "$TempExtract\nutrition_images" -Destination "data\nutrition_images" -Recurse -Force
            }
            Remove-Item $TempExtract -Recurse -Force
        } else {
            # Sao lưu file DB cũ trên máy đích nếu có
            if (Test-Path $DestDb) {
                $PreRestoreBak = "$DestDb.pre_restore_$(Get-Date -Format 'yyyyMMdd_HHmmss').bak"
                Copy-Item -Path $DestDb -Destination $PreRestoreBak -Force
                Write-Host "ℹ️ Đã tạo bản backup dự phòng cho DB cũ tại: $PreRestoreBak" -ForegroundColor Gray
            }

            # Xóa các file WAL/SHM cũ để tránh xung đột trang nhớ
            if (Test-Path "$DestDb-wal") { Remove-Item "$DestDb-wal" -Force }
            if (Test-Path "$DestDb-shm") { Remove-Item "$DestDb-shm" -Force }

            Write-Host "📥 Đang khôi phục SQLite từ '$BackupFile' -> '$DestDb'..." -ForegroundColor Yellow
            Copy-Item -Path $BackupFile -Destination $DestDb -Force
        }

        $SizeMB = [math]::Round((Get-Item $DestDb).Length / 1MB, 2)
        Write-Host "✅ Đã khôi phục thành công SQLite Database tại: $DestDb ($SizeMB MB)!" -ForegroundColor Green
    }

    "postgres" {
        if ($DbPort -eq 0) { $DbPort = 5432 }
        if ([string]::IsNullOrWhiteSpace($BackupFile)) { $BackupFile = "backups\db_backup.dump" }
        if (-not (Test-Path $BackupFile)) {
            Write-Host "❌ Không tìm thấy file PostgreSQL dump tại: $BackupFile" -ForegroundColor Red
            exit 1
        }

        Write-Host "🐘 Đang khôi phục PostgreSQL Database '$DbName' từ '$BackupFile'..." -ForegroundColor Yellow
        # Tạo DB nếu chưa có
        createdb -U $DbUser -h $DbHost -p $DbPort $DbName 2>$null
        pg_restore -U $DbUser -h $DbHost -p $DbPort -d $DbName --clean --if-exists -v $BackupFile
        Write-Host "✅ Khôi phục PostgreSQL hoàn tất!" -ForegroundColor Green
    }

    "mysql" {
        if ($DbPort -eq 0) { $DbPort = 3306 }
        if ($DbUser -eq "postgres") { $DbUser = "root" }
        if ([string]::IsNullOrWhiteSpace($BackupFile)) { $BackupFile = "backups\db_backup.sql" }
        if (-not (Test-Path $BackupFile)) {
            Write-Host "❌ Không tìm thấy file MySQL dump tại: $BackupFile" -ForegroundColor Red
            exit 1
        }

        Write-Host "🐬 Đang import MySQL/MariaDB Database '$DbName' từ '$BackupFile'..." -ForegroundColor Yellow
        cmd /c "mysql -u $DbUser -p -h $DbHost -P $DbPort -e `"CREATE DATABASE IF NOT EXISTS $DbName CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`""
        cmd /c "mysql -u $DbUser -p -h $DbHost -P $DbPort $DbName < `"$BackupFile`""
        Write-Host "✅ Khôi phục MySQL/MariaDB hoàn tất!" -ForegroundColor Green
    }
}
