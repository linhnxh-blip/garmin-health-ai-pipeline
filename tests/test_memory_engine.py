import json
import pytest
from pathlib import Path
from src.db.connection import init_db, get_db_connection
from src.analytics.memory_engine import (
    calculate_deep_sleep_bb_correlation,
    calculate_hrv_capacity,
    calculate_rhr_sensitivity,
    extract_recent_running_dynamics,
    build_memory_context
)

@pytest.fixture
def temp_memory_db(tmp_path):
    db_file = tmp_path / "test_memory.db"
    init_db(db_file)
    return db_file

def test_deep_sleep_bb_correlation_empty():
    res = calculate_deep_sleep_bb_correlation([])
    assert res["correlation_r"] is None
    assert res["bb_per_15m_deep"] is None
    assert res["sample_count"] == 0

def test_deep_sleep_bb_correlation_valid():
    rows = [
        {"deep_sleep_seconds": 3600, "body_battery_charged": 40},
        {"deep_sleep_seconds": 5400, "body_battery_charged": 60},
        {"deep_sleep_seconds": 7200, "body_battery_charged": 80},
    ]
    res = calculate_deep_sleep_bb_correlation(rows)
    assert res["correlation_r"] == 1.0
    assert res["bb_per_15m_deep"] > 0
    assert res["sample_count"] == 3

def test_hrv_capacity_empty():
    res = calculate_hrv_capacity([])
    assert res["mean_hrv"] is None
    assert res["fatigue_threshold"] is None

def test_hrv_capacity_valid():
    rows = [
        {"hrv_last_night": 40.0},
        {"hrv_last_night": 50.0},
        {"hrv_last_night": 60.0},
    ]
    res = calculate_hrv_capacity(rows)
    assert res["mean_hrv"] == 50.0
    assert res["std_hrv"] == 10.0
    assert res["fatigue_threshold"] == 40.0

def test_rhr_sensitivity_valid():
    rows = [
        {"date": "2026-09-01", "resting_heart_rate": 50, "avg_stress_level": 40},
        {"date": "2026-09-02", "resting_heart_rate": 54, "avg_stress_level": 20},
        {"date": "2026-09-03", "resting_heart_rate": 50, "avg_stress_level": 15},
    ]
    res = calculate_rhr_sensitivity(rows)
    assert res["baseline_rhr_mean"] == 51.3
    assert res["avg_rhr_elevation"] is not None

def test_extract_recent_running_dynamics():
    rows = [
        {
            "date": "2026-09-18",
            "activities_summary": json.dumps([
                {
                    "name": "Evening Run",
                    "type": "running",
                    "avg_cadence": 172,
                    "gct_balance": "50.5% L / 49.5% R"
                }
            ])
        }
    ]
    res = extract_recent_running_dynamics(rows)
    assert res is not None
    assert res["date"] == "2026-09-18"
    assert res["cadence"] == 172
    assert res["gct_balance"] == "50.5% L / 49.5% R"

def test_build_memory_context_empty(temp_memory_db):
    res = build_memory_context("2026-09-19", days=60, db_path=temp_memory_db)
    assert "ADAPTIVE MEMORY" in res["memory_text"]
    assert "Chưa có đủ dữ liệu" in res["memory_text"]

def test_build_memory_context_with_data(temp_memory_db):
    with get_db_connection(temp_memory_db) as conn:
        cursor = conn.cursor()
        for i in range(1, 10):
            d_str = f"2026-09-{i:02d}"
            cursor.execute(
                """
                INSERT INTO daily_metrics (date, sleep_score, deep_sleep_seconds, body_battery_charged, hrv_last_night, resting_heart_rate, avg_stress_level)
                VALUES (?, 75, 5400, 65, 45.0, 52, 25)
                """,
                (d_str,)
            )
        conn.commit()

    res = build_memory_context("2026-09-19", days=60, db_path=temp_memory_db)
    assert "ADAPTIVE MEMORY 9 NGÀY" in res["memory_text"]
    assert "Tương quan Giấc ngủ sâu" in res["memory_text"]
    assert "Khả năng chịu tải & Ngưỡng HRV" in res["memory_text"]
