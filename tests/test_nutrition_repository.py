import pytest
from pathlib import Path
from datetime import datetime

from src.db.connection import init_db
from src.db.nutrition_repository import save_nutrition_log, get_nutrition_logs_by_date

def test_save_and_get_nutrition_logs(tmp_path):
    db_file = tmp_path / "test_garmin.db"
    init_db(db_file)

    sample_log = {
        "date": "2026-09-19",
        "timestamp": "2026-09-19 19:30:00",
        "meal_type": "Bữa tối / Nhậu",
        "dishes": ["Lẩu hải sản", "2 lon bia"],
        "total_calories": 750,
        "protein_g": 45.0,
        "carb_g": 60.0,
        "fat_g": 25.0,
        "alcohol_units": 2.0,
        "alcohol_description": "2 lon bia",
        "sleep_risk_assessment": "Ăn sát giờ ngủ và uống 2 lon bia làm tăng RHR đêm.",
        "short_summary": "Đã ghi nhận: Lẩu hải sản + 2 lon bia (~750 kcal).",
        "image_path": "/path/to/test.jpg"
    }

    record_id = save_nutrition_log(sample_log, db_path=db_file)
    assert record_id > 0

    retrieved = get_nutrition_logs_by_date("2026-09-19", db_path=db_file)
    assert len(retrieved) == 1
    item = retrieved[0]
    assert item["meal_type"] == "Bữa tối / Nhậu"
    assert "Lẩu hải sản" in item["dishes"]
    assert item["total_calories"] == 750
    assert item["alcohol_units"] == 2.0

def test_get_today_nutrition_summary(tmp_path):
    from src.db.nutrition_repository import get_today_nutrition_summary

    db_file = tmp_path / "test_summary.db"
    init_db(db_file)

    log1 = {
        "date": "2026-09-22",
        "timestamp": "2026-09-22 08:00:00",
        "meal_type": "Bữa sáng",
        "dishes": ["Bánh mì"],
        "total_calories": 530,
        "protein_g": 29.0,
        "carb_g": 60.0,
        "fat_g": 18.0
    }
    log2 = {
        "date": "2026-09-22",
        "timestamp": "2026-09-22 12:00:00",
        "meal_type": "Bữa trưa",
        "dishes": ["Cơm sườn"],
        "total_calories": 560,
        "protein_g": 48.0,
        "carb_g": 56.0,
        "fat_g": 13.0
    }
    # Log from yesterday (should NOT be included in today summary)
    log_prev = {
        "date": "2026-09-21",
        "timestamp": "2026-09-21 19:00:00",
        "meal_type": "Bữa tối",
        "dishes": ["Phở"],
        "total_calories": 850,
        "protein_g": 55.0,
        "carb_g": 90.0,
        "fat_g": 20.0
    }

    save_nutrition_log(log1, db_path=db_file)
    save_nutrition_log(log2, db_path=db_file)
    save_nutrition_log(log_prev, db_path=db_file)

    summary = get_today_nutrition_summary("2026-09-22", db_path=db_file)
    assert summary["total_cal"] == 1090
    assert summary["total_protein"] == 77.0
    assert summary["total_carbs"] == 116.0
    assert summary["total_fat"] == 31.0


def test_reparse_uncalculated_meal_logs(tmp_path, monkeypatch):
    from src.db.nutrition_repository import reparse_uncalculated_meal_logs
    from src.db.connection import get_db_connection

    db_file = tmp_path / "test_reparse.db"
    init_db(db_file)

    # Insert log with 0 calories and 0 protein
    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO nutrition_logs (date, timestamp, meal_type, dishes, total_calories, protein_g, carb_g, fat_g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-11-10", "2026-11-10 08:30:00", "Bữa sáng", '["1 phở bò bắp"]', 0, 0.0, 0.0, 0.0)
        )
        # Insert normal already-calculated log
        cursor.execute(
            """
            INSERT INTO nutrition_logs (date, timestamp, meal_type, dishes, total_calories, protein_g, carb_g, fat_g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-11-10", "2026-11-10 12:30:00", "Bữa trưa", '["Cơm sườn"]', 600, 35.0, 70.0, 20.0)
        )
        conn.commit()

    # Mock analyze_quick_log_text
    def fake_analyze(text, timestamp=None):
        return {
            "meal_type": "Bữa sáng",
            "dishes": [text],
            "total_calories": 530,
            "protein_g": 36.0,
            "carb_g": 58.0,
            "fat_g": 14.0,
            "short_summary": f"Đã ghi nhận: {text} (~530 kcal)",
            "sleep_risk_assessment": "✅ Đánh giá phục hồi tốt."
        }

    monkeypatch.setattr("src.analytics.vision_analyst.analyze_quick_log_text", fake_analyze)

    # 1. Test Dry Run
    res_dry = reparse_uncalculated_meal_logs(db_path=db_file, dry_run=True)
    assert res_dry["total_found"] == 1
    assert res_dry["records"][0]["new"]["calories"] == 530

    # Verify not yet changed in DB
    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT total_calories, protein_g FROM nutrition_logs WHERE id = 1")
        row = cursor.fetchone()
        assert row[0] == 0

    # 2. Test Real Reparse & Update
    res_real = reparse_uncalculated_meal_logs(db_path=db_file, dry_run=False)
    assert res_real["updated_count"] == 1

    # Verify updated in DB
    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT total_calories, protein_g, carb_g, fat_g FROM nutrition_logs WHERE id = 1")
        row = cursor.fetchone()
        assert row[0] == 530
        assert row[1] == 36.0
        assert row[2] == 58.0
        assert row[3] == 14.0

        # Normal log remains unchanged
        cursor.execute("SELECT total_calories, protein_g FROM nutrition_logs WHERE id = 2")
        row2 = cursor.fetchone()
        assert row2[0] == 600
        assert row2[1] == 35.0

