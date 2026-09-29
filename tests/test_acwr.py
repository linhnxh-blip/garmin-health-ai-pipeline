import sqlite3
import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from src.analytics.acwr import calculate_acwr, ACWRCalculator
from src.db.connection import init_db
from src.analytics.prompt_engine import build_advanced_user_prompt
from src.analytics.baseline import calculate_baseline


def test_acwr_acute_load_very_low_zone(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_dt = datetime(2026, 9, 26)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    # Days 1..21 (21 days): high workload 100
    # Days 22..28 (7 days): low workload 20
    with sqlite3.connect(str(db_file)) as conn:
        for i in range(28):
            d_str = (target_dt - timedelta(days=27 - i)).strftime("%Y-%m-%d")
            load = 20.0 if i >= 21 else 100.0
            conn.execute(
                "INSERT OR REPLACE INTO daily_metrics (date, active_calories) VALUES (?, ?)",
                (d_str, load)
            )
        conn.commit()

    res = calculate_acwr(target_date_str, days=28, db_path=db_file)
    assert res["acute_load"] == 20.0
    assert res["chronic_load"] == 80.0
    assert res["acwr"] == 0.25
    assert res["status"] == "ACUTE_LOAD_VERY_LOW"
    assert "Tải cấp tính rất thấp" in res["zone_desc"]


def test_acwr_tapering_deep_recovery_zone(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_dt = datetime(2026, 9, 26)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    # Days 1..21 (21 days): high workload 100
    # Days 22..28 (7 days): workload 40 (ACWR ~0.47)
    with sqlite3.connect(str(db_file)) as conn:
        for i in range(28):
            d_str = (target_dt - timedelta(days=27 - i)).strftime("%Y-%m-%d")
            load = 40.0 if i >= 21 else 100.0
            conn.execute(
                "INSERT OR REPLACE INTO daily_metrics (date, active_calories) VALUES (?, ?)",
                (d_str, load)
            )
        conn.commit()

    res = calculate_acwr(target_date_str, days=28, db_path=db_file)
    assert res["acute_load"] == 40.0
    assert res["acwr"] == 0.47
    assert res["status"] == "TAPERING_DEEP_RECOVERY"
    assert "Rất an toàn" in res["zone_desc"]


def test_acwr_sweet_spot_optimal_zone(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_dt = datetime(2026, 9, 26)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    # Constant workload of 100.0 for 28 days
    with sqlite3.connect(str(db_file)) as conn:
        for i in range(28):
            d_str = (target_dt - timedelta(days=27 - i)).strftime("%Y-%m-%d")
            conn.execute(
                "INSERT OR REPLACE INTO daily_metrics (date, active_calories) VALUES (?, ?)",
                (d_str, 100.0)
            )
        conn.commit()

    res = calculate_acwr(target_date_str, days=28, db_path=db_file)
    assert res["acute_load"] == 100.0
    assert res["chronic_load"] == 100.0
    assert res["acwr"] == 1.0
    assert res["status"] == "SWEET_SPOT_OPTIMAL"
    assert "Vùng tải tối ưu" in res["zone_desc"]


def test_acwr_elevated_risk_and_danger_zone(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_dt = datetime(2026, 9, 26)
    target_date_str = target_dt.strftime("%Y-%m-%d")

    # Days 1..21 (21 days): low workload 50
    # Days 22..28 (7 days): high workload 150
    with sqlite3.connect(str(db_file)) as conn:
        for i in range(28):
            d_str = (target_dt - timedelta(days=27 - i)).strftime("%Y-%m-%d")
            load = 150.0 if i >= 21 else 50.0
            conn.execute(
                "INSERT OR REPLACE INTO daily_metrics (date, active_calories) VALUES (?, ?)",
                (d_str, load)
            )
        conn.commit()

    res = calculate_acwr(target_date_str, days=28, db_path=db_file)
    # Acute Load = 150.0
    # Chronic Load = (21 * 50 + 7 * 150) / 28 = (1050 + 1050) / 28 = 75.0
    # ACWR = 150.0 / 75.0 = 2.0 (> 1.5)
    assert res["acute_load"] == 150.0
    assert res["chronic_load"] == 75.0
    assert res["acwr"] == 2.0
    assert res["status"] == "DANGER_HIGH_INJURY_SPIKE"
    assert "Báo động đỏ" in res["zone_desc"]


def test_acwr_insufficient_data_fallback(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_date_str = "2026-09-26"
    # Insert only 2 days of data
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute("INSERT OR REPLACE INTO daily_metrics (date, active_calories) VALUES ('2026-09-25', 100.0)")
        conn.execute("INSERT OR REPLACE INTO daily_metrics (date, active_calories) VALUES ('2026-09-26', 120.0)")
        conn.commit()

    res = calculate_acwr(target_date_str, days=28, db_path=db_file)
    assert isinstance(res, dict)
    assert "acute_load" in res
    assert "chronic_load" in res
    assert "acwr" in res
    assert "status" in res


def test_achilles_tendon_warning_flag_logic(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_date_str = "2026-09-26"
    act_summary = [
        {
            "name": "Morning Run",
            "type": "running",
            "duration_seconds": 1800,
            "distance_meters": 5000,
            "avg_cadence": 175,
            "gct_balance": 51.7
        }
    ]
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO daily_metrics (date, activities_summary, hrv_status) VALUES (?, ?, ?)",
            (target_date_str, json.dumps(act_summary), "BALANCED")
        )
        conn.commit()

    base_data = calculate_baseline(target_date_str, days=30, db_path=db_file)
    prompt_text = build_advanced_user_prompt(base_data)

    assert "CHỈ SỐ Y HỌC THỂ THAO ACWR" in prompt_text
    assert "BẢO VỆ GÂN ACHILLES TRÁI" in prompt_text
    assert "178 - 182 spm" in prompt_text
    assert "Eccentric Heel Drops" in prompt_text


def test_hrv_unbalanced_override_prompt_logic(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    target_date_str = "2026-09-26"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO daily_metrics (date, hrv_status, hrv_last_night) VALUES (?, ?, ?)",
            (target_date_str, "UNBALANCED", 35.0)
        )
        conn.commit()

    base_data = calculate_baseline(target_date_str, days=30, db_path=db_file)
    prompt_text = build_advanced_user_prompt(base_data)

    assert "CỜ CHỈ DẪN GHI ĐÈ BÀI TẬP" in prompt_text
    assert "Bơi lội Zone 1" in prompt_text or "Nghỉ ngơi hoàn toàn" in prompt_text
