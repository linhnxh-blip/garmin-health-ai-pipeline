import pytest
import json
from src.db.connection import get_db_connection, init_db
from src.analytics.evening_checkin import generate_evening_checkin

def test_generate_evening_checkin(tmp_path):
    test_db = tmp_path / "test_garmin.db"
    init_db(test_db)

    # Insert test daily metric record
    activities = [
        {
            "name": "Chạy MAF Zone 2",
            "type": "running",
            "duration_seconds": 2700,
            "distance_meters": 6000,
            "avg_cadence": 172
        }
    ]

    with get_db_connection(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_metrics (date, total_steps, step_goal, activities_summary, training_status)
            VALUES ('2026-09-22', 12500, 10000, ?, 'PRODUCTIVE')
            """,
            (json.dumps(activities),)
        )
        conn.commit()

    res = generate_evening_checkin("2026-09-22", db_path=test_db)

    assert res["date"] == "2026-09-22"
    assert res["total_steps"] == 12500
    assert res["step_goal"] == 10000
    assert res["run_steps"] > 0
    assert res["neat_steps"] >= 0
    assert "🌙 **CHECK-IN PHỤC HỒI & TỔNG KẾT BƯỚC CHÂN CUỐI NGÀY**" in res["card_markdown"]
    assert "Magie Bisglycinate" in res["card_markdown"]


def test_generate_evening_checkin_rest_day_high_neat(tmp_path):
    test_db = tmp_path / "test_garmin.db"
    init_db(test_db)

    with get_db_connection(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_metrics (date, total_steps, step_goal, activities_summary, training_status)
            VALUES ('2026-09-22', 11500, 10000, NULL, 'RECOVERY')
            """
        )
        conn.commit()

    res = generate_evening_checkin("2026-09-22", db_path=test_db)

    assert res["is_rest_day"] is True
    assert res["neat_steps"] == 11500
    assert "⚠️ **Cảnh báo Tải trọng Cơ học:**" in res["card_markdown"]
