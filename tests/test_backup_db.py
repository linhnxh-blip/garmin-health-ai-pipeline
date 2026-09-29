import sqlite3
import time
import pytest
from pathlib import Path

from scripts.backup_db import backup_database, cleanup_old_backups
from src.db.connection import init_db


def test_backup_database_creates_consistent_snapshot(tmp_path):
    src_db = tmp_path / "garmin_health.db"
    backup_dir = tmp_path / "backups"

    # Initialize source DB with dummy data
    init_db(src_db)
    with sqlite3.connect(str(src_db)) as conn:
        conn.execute("INSERT INTO daily_metrics (date, sleep_score) VALUES ('2026-09-26', 85)")
        conn.commit()

    # Perform backup
    dst_db = backup_database(db_path=src_db, backup_dir=backup_dir)

    assert dst_db.exists()
    assert dst_db.parent == backup_dir
    assert dst_db.name.startswith("garmin_health_")
    assert dst_db.name.endswith(".db")

    # Verify content in backup DB
    with sqlite3.connect(str(dst_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sleep_score FROM daily_metrics WHERE date = '2026-09-26'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 85


def test_cleanup_old_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Create 10 dummy backup files with timestamps
    created_files = []
    for i in range(10):
        f = backup_dir / f"garmin_health_20260926_1000{i:02d}.db"
        f.write_text(f"dummy content {i}", encoding="utf-8")
        created_files.append(f)
        time.sleep(0.01)

    assert len(list(backup_dir.glob("garmin_health_*.db"))) == 10

    # Cleanup retaining 7 newest
    cleanup_old_backups(backup_dir, max_backups=7)

    remaining_files = sorted(list(backup_dir.glob("garmin_health_*.db")))
    assert len(remaining_files) == 7
    # Oldest 3 files should be deleted
    assert created_files[0] not in remaining_files
    assert created_files[1] not in remaining_files
    assert created_files[2] not in remaining_files
    # Newest 7 should remain
    assert created_files[-1] in remaining_files
