#!/usr/bin/env bash
# ==============================================================================
# DATABASE EXPORT & BACKUP SCRIPT (SQLite / PostgreSQL / MySQL)
# Sử dụng:
#   ./dump_database.sh sqlite [data/garmin_health.db]
#   ./dump_database.sh postgres <db_user> <db_name> [db_host] [db_port]
#   ./dump_database.sh mysql <db_user> <db_name> [db_host] [db_port]
# ==============================================================================

set -e

DB_TYPE="${1:-sqlite}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKUP_DIR="$SCRIPT_DIR/backups"
mkdir -p "$BACKUP_DIR"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"

echo "=================================================================="
echo " 💾 DATABASE EXPORT & BACKUP TOOL (LOẠI DB: ${DB_TYPE^^})"
echo "=================================================================="

case "$DB_TYPE" in
    sqlite)
        SQLITE_PATH="${2:-data/garmin_health.db}"
        if [ ! -f "$SQLITE_PATH" ]; then
            echo "❌ Không tìm thấy file SQLite tại: $SQLITE_PATH"
            exit 1
        fi
        DST_TIMESTAMP="$BACKUP_DIR/garmin_health_${TIMESTAMP}.db"
        DST_LATEST="$BACKUP_DIR/db_backup.sqlite3"

        echo "📦 Đang sao lưu an toàn SQLite từ '$SQLITE_PATH'..."
        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 "$SQLITE_PATH" ".backup '$DST_TIMESTAMP'"
        else
            cp -f "$SQLITE_PATH" "$DST_TIMESTAMP"
        fi
        cp -f "$DST_TIMESTAMP" "$DST_LATEST"

        echo "✅ Đã tạo file backup SQLite:"
        echo "   - $DST_TIMESTAMP"
        echo "   - $DST_LATEST"
        ;;

    postgres|postgresql)
        DB_USER="${2:-postgres}"
        DB_NAME="${3:-garmin_health}"
        DB_HOST="${4:-localhost}"
        DB_PORT="${5:-5432}"
        DUMP_FILE="$BACKUP_DIR/db_backup.dump"
        DUMP_TS="$BACKUP_DIR/db_backup_${TIMESTAMP}.dump"

        echo "🐘 Đang xuất PostgreSQL Database '$DB_NAME' (User: $DB_USER)..."
        pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" -F c -b -v -f "$DUMP_TS"
        cp -f "$DUMP_TS" "$DUMP_FILE"
        echo "✅ Đã xuất PostgreSQL dump tại: $DUMP_FILE"
        ;;

    mysql|mariadb)
        DB_USER="${2:-root}"
        DB_NAME="${3:-garmin_health}"
        DB_HOST="${4:-localhost}"
        DB_PORT="${5:-3306}"
        SQL_FILE="$BACKUP_DIR/db_backup.sql"
        SQL_TS="$BACKUP_DIR/db_backup_${TIMESTAMP}.sql"

        echo "🐬 Đang xuất MySQL/MariaDB Database '$DB_NAME' (User: $DB_USER)..."
        mysqldump -u "$DB_USER" -p -h "$DB_HOST" -P "$DB_PORT" --single-transaction --routines --triggers "$DB_NAME" > "$SQL_TS"
        cp -f "$SQL_TS" "$SQL_FILE"
        echo "✅ Đã xuất MySQL dump tại: $SQL_FILE"
        ;;

    *)
        echo "❌ Loại DB không hợp lệ: $DB_TYPE (Hỗ trợ: sqlite | postgres | mysql)"
        exit 1
        ;;
esac

echo "=================================================================="
echo " 🎉 Hoàn tất sao lưu tại thư mục: $BACKUP_DIR"
echo "=================================================================="

