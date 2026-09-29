"""
Database repository for intraday versioned reports (morning, midday, evening).
Ensures reports are unique on (date, report_type) and prevents overwriting morning baseline context.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.db.connection import get_db_connection, init_db


def save_report(
    date: str,
    report_type: str,
    content: str,
    metrics_snapshot: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Save or update an intraday health report in SQLite database (`daily_reports` table).
    Unique on (date, report_type) ON CONFLICT REPLACE.
    """
    target_db_path = init_db(db_path)
    snapshot_json = json.dumps(metrics_snapshot, ensure_ascii=False) if metrics_snapshot else None

    r_type = (report_type or "morning").lower()
    if r_type not in ["morning", "midday", "evening"]:
        r_type = "morning"

    with get_db_connection(target_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_reports (date, report_type, content, metrics_snapshot, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(date, report_type) DO UPDATE SET
                content = excluded.content,
                metrics_snapshot = COALESCE(excluded.metrics_snapshot, daily_reports.metrics_snapshot),
                created_at = CURRENT_TIMESTAMP
            """,
            (date, r_type, content, snapshot_json)
        )
        conn.commit()

    return {
        "date": date,
        "report_type": r_type,
        "content": content,
        "metrics_snapshot": metrics_snapshot
    }


def get_report_by_type(
    date: str,
    report_type: str,
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Retrieve an existing intraday report by date and report_type ('morning', 'midday', 'evening').
    """
    r_type = (report_type or "morning").lower()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM daily_reports WHERE date = ? AND report_type = ?",
            (date, r_type)
        )
        row = cursor.fetchone()
        if row:
            d = dict(row)
            if d.get("metrics_snapshot"):
                try:
                    d["metrics_snapshot"] = json.loads(d["metrics_snapshot"])
                except Exception:
                    pass
            return d
    return None


def get_all_reports_for_date(
    date: str,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Return all generated intraday reports for a specific date ('morning', 'midday', 'evening').
    """
    results = []
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM daily_reports WHERE date = ? ORDER BY created_at ASC",
            (date,)
        )
        rows = cursor.fetchall()
        for row in rows:
            d = dict(row)
            if d.get("metrics_snapshot"):
                try:
                    d["metrics_snapshot"] = json.loads(d["metrics_snapshot"])
                except Exception:
                    pass
            results.append(d)
    return results


def delete_report_by_type(
    date: str,
    report_type: str,
    db_path: Optional[Path] = None
) -> bool:
    """
    Delete a specific intraday report by date and report_type.
    """
    r_type = (report_type or "morning").lower()
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM daily_reports WHERE date = ? AND report_type = ?",
            (date, r_type)
        )
        conn.commit()
        return cursor.rowcount > 0
