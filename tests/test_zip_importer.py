import json
import zipfile
from pathlib import Path
import pytest

from src.db.connection import init_db, get_db_connection
from src.db.models import DailyMetrics
from src.importers.zip_importer import import_garmin_export

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_garmin.db"
    init_db(db_file)
    return db_file

@pytest.fixture
def mock_garmin_zip(tmp_path):
    zip_path = tmp_path / "mock_garmin_export.zip"
    
    sleep_data = [
        {
            "calendarDate": "2024-09-01",
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 7200,
            "remSleepSeconds": 5400,
            "lightSleepSeconds": 16200,
            "sleepQualityScoreValue": 88
        }
    ]
    
    hrv_data = [
        {
            "calendarDate": "2024-09-01",
            "weeklyAvg": 55.5,
            "lastNightAvg": 58.0,
            "status": "BALANCED"
        }
    ]

    user_summary = [
        {
            "calendarDate": "2024-09-01",
            "restingHeartRate": 52,
            "averageStressLevel": 22,
            "totalSteps": 10500,
            "activeKilocalories": 450,
            "bodyBatteryHighestValue": 95
        }
    ]

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/sleepData_2024.json", json.dumps(sleep_data))
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/hrvStatus_2024.json", json.dumps(hrv_data))
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/userSummary_2024.json", json.dumps(user_summary))

    return zip_path

def test_daily_metrics_strict_null():
    metrics = DailyMetrics(date="2024-09-01", sleep_score=80)
    assert metrics.date == "2024-09-01"
    assert metrics.sleep_score == 80
    assert metrics.hrv_last_night is None
    assert metrics.resting_heart_rate is None

def test_import_garmin_export(mock_garmin_zip, temp_db):
    res = import_garmin_export(mock_garmin_zip, db_path=temp_db)
    assert res["dates_processed"] == 1
    assert res["raw_records_inserted"] == 3

    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = '2024-09-01'")
        row = cursor.fetchone()
        assert row is not None
        assert row["sleep_score"] == 88
        assert row["sleep_duration_seconds"] == 28800
        assert row["hrv_last_night"] == 58.0
        assert row["hrv_status"] == "BALANCED"
        assert row["resting_heart_rate"] == 52
        assert row["total_steps"] == 10500
        # Check strict null policy for missing VO2 max
        assert row["vo2_max"] is None
