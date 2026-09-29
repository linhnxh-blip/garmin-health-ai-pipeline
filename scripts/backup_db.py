import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings


def cleanup_old_backups(backup_dir: Path, max_backups: int = 7):
    """
    Retain only the max_backups newest backup files matching garmin_health_*.db,
    and remove the rest.
    """
    backups = sorted(
        [f for f in backup_dir.glob("garmin_health_*.db") if f.is_file()],
        key=lambda p: p.stat().st_mtime
    )

    if len(backups) > max_backups:
        to_delete = backups[:-max_backups]
        print(f"🧹 Dọn dẹp bản sao lưu cũ (Giữ lại {max_backups} bản mới nhất, xóa {len(to_delete)} bản cũ)...")
        for old_file in to_delete:
            try:
                old_file.unlink()
                print(f"   - Đã xóa bản sao lưu cũ: {old_file.name}")
            except Exception as e:
                print(f"   ⚠️ Không thể xóa file {old_file.name}: {e}")
    else:
        print(f"ℹ️ Tổng số bản sao lưu hiện tại: {len(backups)} (Giới hạn tối đa: {max_backups})")


def backup_database(db_path: Path = None, backup_dir: Path = None, max_backups: int = 7) -> Path:
    """
    Backup SQLite database consistently using sqlite3 Connection.backup() API.
    """
    src_db = Path(db_path) if db_path else settings.absolute_db_path
    target_backup_dir = Path(backup_dir) if backup_dir else (BASE_DIR / "data" / "backups")

    target_backup_dir.mkdir(parents=True, exist_ok=True)

    if not src_db.exists():
        print(f"⚠️ Cơ sở dữ liệu nguồn '{src_db}' chưa tồn tại. Tiến hành khởi tạo DB...")
        from src.db.connection import init_db
        init_db(src_db)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_db = target_backup_dir / f"garmin_health_{timestamp}.db"

    print(f"📦 Đang tiến hành sao lưu SQLite từ '{src_db.name}' sang '{dst_db.name}'...")

    src_conn = sqlite3.connect(str(src_db))
    dst_conn = sqlite3.connect(str(dst_db))
    try:
        with dst_conn:
            src_conn.backup(dst_conn)
        print(f"✅ Sao lưu cơ sở dữ liệu SQLite thành công: {dst_db}")
    finally:
        dst_conn.close()
        src_conn.close()

    # Retention cleanup
    cleanup_old_backups(target_backup_dir, max_backups=max_backups)
    return dst_db


if __name__ == "__main__":
    try:
        backup_database()
    except Exception as err:
        print(f"❌ Thất bại khi sao lưu cơ sở dữ liệu: {err}", file=sys.stderr)
        sys.exit(1)
