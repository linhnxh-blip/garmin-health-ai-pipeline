import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.db.connection import init_db
from src.ingestion.browser_session_client import parse_curl_or_cookies, BrowserGarminClient, fetch_and_store_daily_data_browser

def test_parse_curl_or_cookies():
    raw_cookie = "_ga=GA1.2; SESSIONID=12345; GARMIN-SSO-GUID=abc"
    h1 = parse_curl_or_cookies(raw_cookie)
    assert h1.get("Cookie") == raw_cookie
    assert h1.get("User-Agent") is not None

    curl_cmd = """curl 'https://connect.garmin.com/wellness-service/wellness/dailySleepData' -H 'Cookie: _ga=GA1.2; SESSIONID=999;' -H 'NK: NT'"""
    h2 = parse_curl_or_cookies(curl_cmd)
    assert "_ga=GA1.2; SESSIONID=999;" in h2.get("Cookie", "")
    assert h2.get("NK") == "NT"

@patch("requests.Session.get")
def test_fetch_and_store_daily_data_browser(mock_get, tmp_path: Path):
    db_p = tmp_path / "test_browser.db"
    init_db(db_p)

    def mock_response(url, params=None, timeout=15):
        m = MagicMock()
        m.status_code = 200
        if "dailySleepData" in url:
            m.json.return_value = {
                "dailySleepDTO": {
                    "sleepScores": {"overall": {"value": 82}},
                    "sleepTimeSeconds": 28800,
                    "deepSleepSeconds": 7200,
                    "remSleepSeconds": 5400,
                    "lightSleepSeconds": 16200
                }
            }
        elif "hrv" in url:
            m.json.return_value = {
                "hrvSummary": {
                    "weeklyAvg": 58.0,
                    "lastNightAvg": 62.0,
                    "status": "BALANCED"
                }
            }
        elif "usersummary" in url:
            m.json.return_value = {
                "restingHeartRate": 55,
                "averageStressLevel": 22,
                "maxStressLevel": 65,
                "totalSteps": 10500,
                "activeKilocalories": 450
            }
        elif "bodyBattery" in url:
            m.json.return_value = [{
                "chargedValue": 85,
                "drainedValue": 80,
                "highestValue": 98,
                "lowestValue": 18
            }]
        elif "activities" in url:
            m.json.return_value = [{
                "activityName": "Evening Run",
                "activityType": {"typeKey": "running"},
                "duration": 1800,
                "distance": 5000,
                "calories": 350
            }]
        else:
            m.json.return_value = {}
        return m

    mock_get.side_effect = mock_response

    raw_cookie = "SESSIONID=test_session_123"
    metrics = fetch_and_store_daily_data_browser("2026-09-18", raw_curl_or_cookie=raw_cookie, db_path=db_p)

    assert metrics.date == "2026-09-18"
    assert metrics.sleep_score == 82
    assert metrics.hrv_last_night == 62.0
    assert metrics.resting_heart_rate == 55
    assert metrics.total_steps == 10500
