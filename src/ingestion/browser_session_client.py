import os
import sys
import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import requests
from dotenv import load_dotenv

from config.settings import settings, BASE_DIR
from src.db.connection import get_db_connection, init_db
from src.db.models import DailyMetrics
from src.db.schema import UPSERT_DAILY_METRICS_SQL

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure .env is explicitly loaded
ENV_PATH = BASE_DIR / ".env"
ENV_TXT_PATH = BASE_DIR / ".env.txt"
target_env_file = ENV_PATH if ENV_PATH.exists() else (ENV_TXT_PATH if ENV_TXT_PATH.exists() else ENV_PATH)
if target_env_file.exists():
    load_dotenv(dotenv_path=target_env_file, override=True)

COOKIE_FILE_PATH = BASE_DIR / "data" / "garmin_cookies.txt"

def _safe_get(dictionary: Any, *keys: str) -> Any:
    current = dictionary
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current

def parse_curl_or_cookies(raw_input: str = "") -> Dict[str, str]:
    """Parse raw string input (cURL command, raw cookie string, or header block)
    and extract Cookie string and headers robustly.
    """
    raw_str = raw_input.strip()
    if not raw_str:
        if COOKIE_FILE_PATH.exists() and COOKIE_FILE_PATH.stat().st_size > 0:
            raw_str = COOKIE_FILE_PATH.read_text(encoding="utf-8").strip()
        elif os.getenv("GARMIN_COOKIES"):
            raw_str = os.getenv("GARMIN_COOKIES", "").strip()
        elif os.getenv("GARMIN_CURL"):
            raw_str = os.getenv("GARMIN_CURL", "").strip()

    if not raw_str:
        return {}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "NK": "NT",
        "Origin": "https://connect.garmin.com",
        "Referer": "https://connect.garmin.com/modern/"
    }

    clean_str = re.sub(r'\\\r?\n', ' ', raw_str)
    extracted_cookie = None

    # Strategy 1: Match -H / --header 'Cookie: ...'
    match_h = re.search(
        r"(?:-H|--header)\s+['\"](?:cookie|Cookie):\s*(.+?)['\"](?:\s+-[a-zA-Z]|\s+--|\s*$)",
        clean_str,
        re.IGNORECASE | re.DOTALL
    )
    if not match_h:
        match_h = re.search(
            r"(?:-H|--header)\s+['\"](?:cookie|Cookie):\s*(.+?)['\"]",
            clean_str,
            re.IGNORECASE | re.DOTALL
        )
    if match_h:
        extracted_cookie = match_h.group(1).strip()

    # Strategy 2: Match --cookie or -b flag
    if not extracted_cookie:
        match_b = re.search(
            r"(?:--cookie|-b)\s+['\"]?(.+?)['\"]?(?:\s+-[a-zA-Z]|\s+--|\s*$)",
            clean_str,
            re.IGNORECASE
        )
        if match_b:
            extracted_cookie = match_b.group(1).strip()

    # Strategy 3: Match line or block starting with 'Cookie:'
    if not extracted_cookie:
        match_line = re.search(
            r"(?:^|\n|\s)(?:cookie|Cookie):\s*(.+?)(?:\r?\n|$)",
            clean_str,
            re.IGNORECASE
        )
        if match_line:
            extracted_cookie = match_line.group(1).strip()

    # Strategy 4: Raw cookie string input
    if not extracted_cookie and ("=" in clean_str or ";" in clean_str):
        extracted_cookie = re.sub(r"^(?:cookie|Cookie):\s*", "", clean_str, flags=re.IGNORECASE).strip()

    if extracted_cookie:
        headers["Cookie"] = extracted_cookie
        # Auto extract JWT_WEB into Authorization header if present
        jwt_match = re.search(r'JWT_WEB=([^;]+)', extracted_cookie)
        if jwt_match:
            headers["Authorization"] = f"Bearer {jwt_match.group(1).strip()}"

    # Extract NK header if present in cURL
    nk_match = re.search(r"(?:-H|--header)\s+['\"](?:nk|NK):\s*(.+?)['\"]", clean_str, re.IGNORECASE)
    if nk_match:
        headers["NK"] = nk_match.group(1).strip()

    # Extract Authorization header if present in cURL
    auth_match = re.search(r"(?:-H|--header)\s+['\"](?:authorization|Authorization):\s*(.+?)['\"]", clean_str, re.IGNORECASE)
    if auth_match:
        headers["Authorization"] = auth_match.group(1).strip()

    return headers

class BrowserGarminClient:
    """Garmin Connect Web API Client utilizing Browser Session Cookies."""

    BASE_URL = "https://connect.garmin.com"

    def __init__(self, raw_curl_or_cookie: str = "", username: str = ""):
        self.headers = parse_curl_or_cookies(raw_curl_or_cookie)
        if not self.headers.get("Cookie"):
            print(
                "❌ Error: No valid Cookie found! Please pass a cURL command string, cookie header string, "
                "or save your cookie in `data/garmin_cookies.txt` or `.env` as GARMIN_COOKIES.",
                file=sys.stderr
            )
            raise ValueError("No valid Garmin Session Cookie found.")

        self.username = username or settings.effective_garmin_username or os.getenv("GARMIN_USERNAME", "")
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        url = f"{self.BASE_URL}{endpoint}" if not endpoint.startswith("http") else endpoint
        try:
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type or "<title>Garmin Connect | Sign In</title>" in resp.text:
                    print(
                        f"⚠️ Warning: Cookie expired! Garmin Connect returned Sign-In page for {endpoint}.\n"
                        f"👉 Please open connect.garmin.com in your browser and run `python scripts/paste_cookie.py` with a fresh cURL/Cookie.",
                        file=sys.stderr
                    )
                    return None
                try:
                    return resp.json()
                except Exception as json_err:
                    print(f"⚠️ Warning: Could not parse JSON from {endpoint}: {json_err}", file=sys.stderr)
                    return None
            elif resp.status_code == 401:
                print(f"⚠️ Warning: Garmin Web API returned 401 Unauthorized for {endpoint}. Cookie is expired.", file=sys.stderr)
            elif resp.status_code == 403:
                print(f"⚠️ Warning: Garmin Web API returned 403 Forbidden for {endpoint}.", file=sys.stderr)
            else:
                print(f"⚠️ Warning: Garmin Web API {endpoint} returned status {resp.status_code}", file=sys.stderr)
            return None
        except Exception as err:
            print(f"⚠️ HTTP Error requesting {endpoint}: {err}", file=sys.stderr)
            return None

    def get_sleep_data(self, date_str: str) -> Optional[Dict[str, Any]]:
        return self._get("/modern/proxy/wellness-service/wellness/dailySleepData", params={"date": date_str})

    def get_user_summary(self, date_str: str) -> Optional[Dict[str, Any]]:
        return self._get("/modern/proxy/usersummary-service/usersummary/daily", params={"calendarDate": date_str})

    def get_hrv_data(self, date_str: str) -> Optional[Dict[str, Any]]:
        return self._get(f"/modern/proxy/hrv-service/hrv/daily/{date_str}")

    def get_body_battery(self, date_str: str) -> Optional[Any]:
        return self._get(
            "/modern/proxy/wellness-service/wellness/bodyBattery/reports/dailyData",
            params={"startDate": date_str, "endDate": date_str}
        )

    def get_activities_by_date(self, date_str: str) -> Optional[List[Dict[str, Any]]]:
        return self._get(
            "/modern/proxy/activitylist-service/activities/search/activities",
            params={"startDate": date_str, "endDate": date_str}
        )

def fetch_and_store_daily_data_browser(
    target_date: str,
    raw_curl_or_cookie: str = "",
    db_path: Optional[Path] = None
) -> DailyMetrics:
    """Fetch daily metrics using Browser Session Cookie, save raw JSON to raw_garmin_data,
    normalize into DailyMetrics model, and upsert to SQLite database.
    """
    client = BrowserGarminClient(raw_curl_or_cookie=raw_curl_or_cookie)
    target_db_path = init_db(db_path)

    metrics: Dict[str, Any] = {
        "date": target_date,
        "raw_sync_timestamp": datetime.now().isoformat()
    }
    raw_payloads: List[tuple] = []

    # 1. Sleep Data
    sleep_data = client.get_sleep_data(target_date)
    if sleep_data:
        raw_payloads.append((target_date, "SLEEP", json.dumps(sleep_data)))
        daily_dto = sleep_data.get("dailySleepDTO") or {}
        score = _safe_get(daily_dto, "sleepScores", "overall", "value")
        if score is None:
            score = daily_dto.get("sleepQualityScoreValue")
        if score is not None:
            metrics["sleep_score"] = int(score)

        metrics["sleep_duration_seconds"] = daily_dto.get("sleepTimeSeconds")
        metrics["deep_sleep_seconds"] = daily_dto.get("deepSleepSeconds")
        metrics["rem_sleep_seconds"] = daily_dto.get("remSleepSeconds") or daily_dto.get("remSleepDataSeconds")
        metrics["light_sleep_seconds"] = daily_dto.get("lightSleepSeconds")

    # 2. HRV Data
    hrv_data = client.get_hrv_data(target_date)
    if hrv_data:
        raw_payloads.append((target_date, "HRV", json.dumps(hrv_data)))
        hrv_summary = hrv_data.get("hrvSummary") or {}
        if hrv_summary.get("weeklyAvg") is not None:
            metrics["hrv_weekly_avg"] = float(hrv_summary["weeklyAvg"])
        if hrv_summary.get("lastNightAvg") is not None:
            metrics["hrv_last_night"] = float(hrv_summary["lastNightAvg"])
        if hrv_summary.get("status") is not None:
            metrics["hrv_status"] = str(hrv_summary["status"])

    # 3. User Summary Data
    user_summary = client.get_user_summary(target_date)
    if user_summary:
        raw_payloads.append((target_date, "USER_SUMMARY", json.dumps(user_summary)))
        if user_summary.get("restingHeartRate") is not None:
            metrics["resting_heart_rate"] = int(user_summary["restingHeartRate"])
        if user_summary.get("averageStressLevel") is not None:
            metrics["avg_stress_level"] = int(user_summary["averageStressLevel"])
        if user_summary.get("maxStressLevel") is not None:
            metrics["max_stress_level"] = int(user_summary["maxStressLevel"])
        if user_summary.get("bodyBatteryHighestValue") is not None:
            metrics["body_battery_highest"] = int(user_summary["bodyBatteryHighestValue"])
        if user_summary.get("bodyBatteryLowestValue") is not None:
            metrics["body_battery_lowest"] = int(user_summary["bodyBatteryLowestValue"])
        if user_summary.get("totalSteps") is not None:
            metrics["total_steps"] = int(user_summary["totalSteps"])
        if user_summary.get("activeKilocalories") is not None:
            metrics["active_calories"] = int(user_summary["activeKilocalories"])
        if user_summary.get("vo2Max") is not None:
            metrics["vo2_max"] = float(user_summary["vo2Max"])

    # 4. Body Battery Data
    bb_data = client.get_body_battery(target_date)
    if bb_data:
        raw_payloads.append((target_date, "BODY_BATTERY", json.dumps(bb_data)))
        bb_items = bb_data if isinstance(bb_data, list) else [bb_data]
        for item in bb_items:
            if isinstance(item, dict):
                if item.get("chargedValue") is not None or item.get("charged") is not None:
                    metrics["body_battery_charged"] = int(item.get("chargedValue") or item.get("charged"))
                if item.get("drainedValue") is not None or item.get("drained") is not None:
                    metrics["body_battery_drained"] = int(item.get("drainedValue") or item.get("drained"))
                if item.get("highestValue") is not None or item.get("highest") is not None:
                    if metrics.get("body_battery_highest") is None:
                        metrics["body_battery_highest"] = int(item.get("highestValue") or item.get("highest"))
                if item.get("lowestValue") is not None or item.get("lowest") is not None:
                    if metrics.get("body_battery_lowest") is None:
                        metrics["body_battery_lowest"] = int(item.get("lowestValue") or item.get("lowest"))

    # 5. Activities Data
    activities = client.get_activities_by_date(target_date)
    if activities:
        raw_payloads.append((target_date, "ACTIVITIES", json.dumps(activities)))
        act_summary_list = []
        for act in activities:
            if isinstance(act, dict):
                act_summary_list.append({
                    "name": act.get("activityName") or act.get("activityType", {}).get("typeKey"),
                    "type": act.get("activityType", {}).get("typeKey"),
                    "duration_seconds": act.get("duration"),
                    "distance_meters": act.get("distance"),
                    "calories": act.get("calories"),
                    "avg_hr": act.get("averageHR"),
                    "max_hr": act.get("maxHR"),
                    "aerobic_training_effect": act.get("aerobicTrainingEffect")
                })
        if act_summary_list:
            metrics["activities_summary"] = json.dumps(act_summary_list)

    if not raw_payloads:
        print(
            f"❌ Failed to fetch any health metrics for {target_date}!\n"
            f"   - Cause: All API endpoints failed because your browser cookie in `data/garmin_cookies.txt` is expired.\n"
            f"   - Solution: Open connect.garmin.com in your browser, copy a fresh cURL, and run `python scripts/paste_cookie.py`.",
            file=sys.stderr
        )
        raise RuntimeError(f"No valid health data retrieved for {target_date}. Cookie in `data/garmin_cookies.txt` is expired.")

    # Validate with DailyMetrics Pydantic Model
    daily_model = DailyMetrics(**metrics)

    # Save to SQLite Database
    with get_db_connection(target_db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany(
            "INSERT INTO raw_garmin_data (date, data_type, raw_json) VALUES (?, ?, ?)",
            raw_payloads
        )
        cursor.execute(UPSERT_DAILY_METRICS_SQL, daily_model.to_db_tuple())
        conn.commit()

    print(f"✅ Successfully fetched and stored Garmin health data for {target_date} via Browser Session Adapter.")
    return daily_model
