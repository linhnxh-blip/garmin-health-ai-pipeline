#!/usr/bin/env bash
# ==============================================================================
# EXPORT & PUSH SOURCE CODE LÊN GITLAB (Bản Bash cho Git Bash / WSL / Linux / macOS)
# Sử dụng:
#   chmod +x export_and_push_gitlab.sh
#   ./export_and_push_gitlab.sh "git@gitlab.com:username/garmin-health-ai-pipeline.git"
# ==============================================================================

set -e

GITLAB_URL="${1:-}"
REMOTE_NAME="${2:-origin}"
BRANCH="${3:-main}"
COMMIT_MSG="chore(migration): package clean source code for GitLab & ROG Ally X server"

echo "=================================================================="
echo " 🚀 EXPORT & PUSH SOURCE CODE LÊN GITLAB (SOURCE MACHINE)"
echo "=================================================================="

# Chuyển về thư mục chứa script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -z "$GITLAB_URL" ]; then
    echo "💡 Định dạng URL hỗ trợ:"
    echo "   - SSH:   git@gitlab.com:<username>/garmin-health-ai-pipeline.git"
    echo "   - Token: https://oauth2:<TOKEN>@gitlab.com/<username>/garmin-health-ai-pipeline.git"
    read -rp "👉 Nhập URL GitLab Repository của bạn: " GITLAB_URL
    if [ -z "$GITLAB_URL" ]; then
        echo "❌ Lỗi: Chưa nhập GitLab URL. Hủy thao tác."
        exit 1
    fi
fi

# 1. Khởi tạo Git nếu chưa có
if [ ! -d ".git" ]; then
    echo "🔧 Khởi tạo Git repository..."
    git init
    git branch -M "$BRANCH"
else
    echo "✅ Git repository đã tồn tại."
fi

# 2. Đảm bảo loại bỏ các file nhạy cảm khỏi git index nếu từng bị track
echo "🛡️ Kiểm tra loại trừ file nhạy cảm (.env, *.db, backups/)..."
git rm -r --cached --ignore-unmatch .env .env.txt "data/*.db" backups/ data/backups/ data/garmin_cookies.txt 2>/dev/null || true

# 3. Stage & Commit
echo "📦 Đang stage toàn bộ source code sạch..."
git add .

if [ -n "$(git status --porcelain)" ]; then
    echo "📝 Commit mã nguồn: '$COMMIT_MSG'"
    git commit -m "$COMMIT_MSG"
else
    echo "ℹ️ Working tree sạch, không có thay đổi mới cần commit."
fi

git branch -M "$BRANCH"

# 4. Thiết lập Remote
if git remote | grep -q "^${REMOTE_NAME}$"; then
    echo "🔄 Cập nhật remote '$REMOTE_NAME' -> $GITLAB_URL"
    git remote set-url "$REMOTE_NAME" "$GITLAB_URL"
else
    echo "➕ Thêm remote '$REMOTE_NAME' -> $GITLAB_URL"
    git remote add "$REMOTE_NAME" "$GITLAB_URL"
fi

# 5. Push lên GitLab
echo "⬆️ Đang đẩy nhánh '$BRANCH' lên GitLab ($REMOTE_NAME)..."
git push -u "$REMOTE_NAME" "$BRANCH"

echo "=================================================================="
echo " 🎉 Đẩy source code lên GitLab thành công!"
echo " 👉 Bước tiếp theo: Chạy ./dump_database.sh để sao lưu Database."
echo "=================================================================="

