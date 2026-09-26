from unittest.mock import MagicMock
import pytest
from src.db.connection import init_db, get_db_connection
from src.ingestion.collector import fetch_and_store_daily_data

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_garmin_ingestion.db"
    init_db(db_file)
    return db_file

@pytest.fixture
def mock_garmin_api():
    client = MagicMock()
    client.get_sleep_data.return_value = {
        "dailySleepDTO": {
            "calendarDate": "2024-09-18",
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 5400,
            "remSleepSeconds": 3600,
            "lightSleepSeconds": 18000,
            "sleepScores": {"overall": {"value": 82}}
        }
    }
    client.get_hrv_data.return_value = {
        "hrvSummary": {
            "calendarDate": "2024-09-18",
            "weeklyAvg": 52.0,
            "lastNightAvg": 56.0,
            "status": "BALANCED"
        }
    }
    client.get_user_summary.return_value = {
        "calendarDate": "2024-09-18",
        "restingHeartRate": 50,
        "averageStressLevel": 20,
        "maxStressLevel": 65,
        "totalSteps": 12000,
        "activeKilocalories": 500,
        "vo2Max": 49.5
    }
    client.get_body_battery.return_value = [
        {"chargedValue": 80, "drainedValue": 75, "highestValue": 90, "lowestValue": 15}
    ]
    client.get_activities_by_date.return_value = [
        {
            "activityName": "Evening Run",
            "activityType": {"typeKey": "running"},
            "duration": 1800.0,
            "distance": 5000.0,
            "calories": 320,
            "averageHR": 145,
            "maxHR": 168
        }
    ]
    return client

def test_fetch_and_store_daily_data(mock_garmin_api, temp_db):
    result = fetch_and_store_daily_data("2024-09-18", client=mock_garmin_api, db_path=temp_db)
    
    assert result.date == "2024-09-18"
    assert result.sleep_score == 82
    assert result.hrv_last_night == 56.0
    assert result.hrv_status == "BALANCED"
    assert result.resting_heart_rate == 50
    assert result.total_steps == 12000
    assert result.body_battery_highest == 90
    assert "Evening Run" in result.activities_summary

    # Check DB persistence
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = '2024-09-18'")
        row = cursor.fetchone()
        assert row is not None
        assert row["sleep_score"] == 82
        assert row["hrv_status"] == "BALANCED"

        cursor.execute("SELECT COUNT(*) FROM raw_garmin_data WHERE date = '2024-09-18'")
        raw_count = cursor.fetchone()[0]
        assert raw_count == 5

def test_activities_extraction(mock_garmin_api, temp_db):
    mock_garmin_api.get_activities_by_date.return_value = [
        {
            "activityName": "Morning Interval Run",
            "activityType": {"typeKey": "running"},
            "duration": 2400.0,
            "distance": 8000.0,
            "calories": 550,
            "averageHR": 158,
            "maxHR": 175,
            "aerobicTrainingEffect": 3.8,
            "anaerobicTrainingEffect": 2.1,
            "activityTrainingLoad": 125.5
        }
    ]
    result = fetch_and_store_daily_data("2024-09-18", client=mock_garmin_api, db_path=temp_db)
    import json
    acts = json.loads(result.activities_summary)
    assert len(acts) == 1
    assert acts[0]["name"] == "Morning Interval Run"
    assert acts[0]["aerobic_training_effect"] == 3.8
    assert acts[0]["anaerobic_training_effect"] == 2.1
    assert acts[0]["activity_training_load"] == 125.5


