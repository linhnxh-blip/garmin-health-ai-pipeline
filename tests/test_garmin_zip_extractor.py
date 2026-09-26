import json
import zipfile
from pathlib import Path
import pytest

from src.db.connection import init_db, get_db_connection
from src.ingestion.garmin_zip_extractor import GarminZipExtractor, process_garmin_zip_archive

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_garmin_extractor.db"
    init_db(db_file)
    return db_file

@pytest.fixture
def mock_garmin_export_zip(tmp_path):
    zip_path = tmp_path / "garmin_export.zip"
    
    sleep_data = [
        {
            "calendarDate": "2026-09-20",
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 7200,
            "remSleepSeconds": 5400,
            "lightSleepSeconds": 16200,
            "sleepQualityScoreValue": 90
        }
    ]
    
    uds_data = [
        {
            "calendarDate": "2026-09-20",
            "restingHeartRate": 48,
            "userBodyBatteryHighestValue": 98,
            "totalSteps": 12500,
            "lastNightAvg": 65.0,
            "status": "BALANCED"
        }
    ]

    biometrics_data = [
        {
            "calendarDate": "2026-09-20",
            "weight": 68.5,
            "bodyFatPercentage": 14.2,
            "muscleMassPercentage": 45.0,
            "visceralFat": 4.0
        }
    ]

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/sleepData_2026.json", json.dumps(sleep_data))
        zf.writestr("DI_CONNECT/DI-Connect-Wellness/udsFile_2026.json", json.dumps(uds_data))
        zf.writestr("DI_CONNECT/DI-Connect-User/biometrics_2026.json", json.dumps(biometrics_data))

    return zip_path

def test_garmin_zip_extractor(mock_garmin_export_zip, temp_db):
    extractor = GarminZipExtractor(mock_garmin_export_zip, db_path=temp_db)
    result = extractor.extract_and_ingest()

    assert result["sleep_days_count"] == 1
    assert result["total_dates"] == 1
    assert result["min_date"] == "2026-09-20"
    assert result["max_date"] == "2026-09-20"

    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = '2026-09-20'")
        row = cursor.fetchone()
        assert row is not None
        assert row["sleep_score"] == 90
        assert row["resting_heart_rate"] == 48
        assert row["hrv_last_night"] == 65.0
        assert row["weight_kg"] == 68.5
        assert row["body_fat_pct"] == 14.2
        assert row["total_steps"] == 12500

def test_process_garmin_zip_archive_helper(mock_garmin_export_zip, temp_db):
    res = process_garmin_zip_archive(mock_garmin_export_zip, db_path=temp_db)
    assert res["total_dates"] == 1
