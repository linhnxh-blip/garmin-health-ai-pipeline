<#
.SYNOPSIS
    Đóng gói toàn bộ source code sạch của dự án và đẩy lên GitLab Repository.

.DESCRIPTION
    Script thực hiện tuần tự:
    1. Kiểm tra & khởi tạo Git repository (nếu chưa có).
    2. Kiểm tra file nhạy cảm (.env, *.db, backups/) đảm bảo không bị dính vào git tracking.
    3. Stage & Commit toàn bộ mã nguồn sạch.
    4. Cấu hình remote 'gitlab' (hoặc cập nhật 'origin') trỏ về URL dự án trên GitLab.
    5. Push nhánh 'main' lên GitLab.

.PARAMETER GitLabUrl
    URL của GitLab Repository (Hỗ trợ SSH: git@gitlab.com:user/repo.git hoặc HTTPS/Token: https://oauth2:<TOKEN>@gitlab.com/user/repo.git)

.PARAMETER RemoteName
    Tên remote muốn đặt (Mặc định: 'origin', hoặc có thể truyền 'gitlab' nếu muốn giữ song song GitHub & GitLab).

.PARAMETER Branch
    Nhánh đẩy lên (Mặc định: 'main').

.EXAMPLE
    .\export_and_push_gitlab.ps1 -GitLabUrl "git@gitlab.com:username/garmin-health-ai-pipeline.git"
    .\export_and_push_gitlab.ps1 -GitLabUrl "https://oauth2:glpat-xxxx@gitlab.com/username/garmin-health-ai-pipeline.git"
#>

param (
    [Parameter(Mandatory = $false)]
    [string]$GitLabUrl = "",

    [Parameter(Mandatory = $false)]
    [string]$RemoteName = "origin",

    [Parameter(Mandatory = $false)]
    [string]$Branch = "main",

    [Parameter(Mandatory = $false)]
    [string]$CommitMessage = "chore(migration): package clean source code for GitLab & ROG Ally X server"
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " 🚀 EXPORT & PUSH SOURCE CODE LÊN GITLAB (SOURCE MACHINE)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# Di chuyển về thư mục gốc của dự án
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
Write-Host "📂 Thư mục dự án: $ProjectRoot" -ForegroundColor Gray

# 1. Yêu cầu nhập GitLab URL nếu chưa truyền qua tham số
if ([string]::IsNullOrWhiteSpace($GitLabUrl)) {
    Write-Host ""
    Write-Host "💡 Gợi ý định dạng GitLab URL:" -ForegroundColor Yellow
    Write-Host "   - SSH:   git@gitlab.com:<username>/garmin-health-ai-pipeline.git"
    Write-Host "   - HTTPS: https://gitlab.com/<username>/garmin-health-ai-pipeline.git"
    Write-Host "   - Token: https://oauth2:<PERSONAL_ACCESS_TOKEN>@gitlab.com/<username>/garmin-health-ai-pipeline.git"
    $GitLabUrl = Read-Host "👉 Nhập URL GitLab Repository của bạn"
    if ([string]::IsNullOrWhiteSpace($GitLabUrl)) {
        Write-Host "❌ Lỗi: Bạn chưa nhập GitLab Repository URL. Hủy thao tác." -ForegroundColor Red
        exit 1
    }
}

# 2. Khởi tạo Git nếu chưa có
if (-not (Test-Path ".git")) {
    Write-Host "🔧 Khởi tạo Git repository mới..." -ForegroundColor Yellow
    git init
    git branch -M $Branch
} else {
    Write-Host "✅ Git repository đã tồn tại." -ForegroundColor Green
}

# 3. Đảm bảo các file nhạy cảm bị gỡ khỏi git cache nếu lỡ được track trước đó
Write-Host "🛡️ Kiểm tra bảo mật & loại trừ file nhạy cảm (.env, *.db, backups/)..." -ForegroundColor Yellow
$SensitivePatterns = @(".env", ".env.txt", "data/*.db", "backups/", "data/backups/", "data/garmin_cookies.txt")
foreach ($pattern in $SensitivePatterns) {
    git rm -r --cached --ignore-unmatch $pattern 2>$null | Out-Null
}

# 4. Stage & Commit toàn bộ mã nguồn sạch
Write-Host "📦 Đang đóng gói (git add) toàn bộ source code sạch..." -ForegroundColor Yellow
git add .

$GitStatus = git status --porcelain
if (-not [string]::IsNullOrWhiteSpace($GitStatus)) {
    Write-Host "📝 Tạo commit mới: '$CommitMessage'" -ForegroundColor Yellow
    git commit -m "$CommitMessage"
} else {
    Write-Host "ℹ️ Không có thay đổi mới nào cần commit (Working tree clean)." -ForegroundColor Gray
}

# Đảm bảo nhánh hiện tại đúng tên ($Branch)
git branch -M $Branch

# 5. Cấu hình Remote trỏ về GitLab
$ExistingRemotes = git remote
if ($ExistingRemotes -contains $RemoteName) {
    $CurrentUrl = git remote get-url $RemoteName
    Write-Host "🔄 Cập nhật remote '$RemoteName' từ [$CurrentUrl] sang [$GitLabUrl]..." -ForegroundColor Yellow
    git remote set-url $RemoteName $GitLabUrl
} else {
    Write-Host "➕ Thêm remote '$RemoteName' -> [$GitLabUrl]..." -ForegroundColor Yellow
    git remote add $RemoteName $GitLabUrl
}

# 6. Đẩy (Push) mã nguồn lên GitLab
Write-Host "⬆️ Đang đẩy nhánh '$Branch' lên GitLab ($RemoteName)..." -ForegroundColor Cyan
git push -u $RemoteName $Branch

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host " 🎉 THÀNH CÔNG! Toàn bộ source code sạch đã được đẩy lên GitLab!" -ForegroundColor Green
    Write-Host " 👉 Bước tiếp theo: Chạy .\dump_database.ps1 để trích xuất Database." -ForegroundColor Green
    Write-Host "==================================================================" -ForegroundColor Green
} else {
    Write-Host "❌ Đẩy code lên GitLab thất bại. Vui lòng kiểm tra quyền truy cập SSH Key hoặc Personal Access Token." -ForegroundColor Red
    exit $LASTEXITCODE
}

