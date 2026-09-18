import os
import sys
import json
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
from datetime import datetime
from tqdm import tqdm

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.db.connection import get_db_connection, init_db
from src.db.models import DailyMetrics
from src.db.schema import UPSERT_DAILY_METRICS_SQL

def _clean_date_string(raw_val: Any) -> Optional[str]:
    """Helper to convert timestamps or date strings into YYYY-MM-DD format."""
    if not raw_val:
        return None
    val_str = str(raw_val).strip()
    if len(val_str) >= 10 and val_str[4] == '-' and val_str[7] == '-':
        return val_str[:10]
    # Check timestamp in ms or seconds
    try:
        ts = float(val_str)
        if ts > 1e11:  # ms timestamp
            ts /= 1000.0
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None

class GarminZipImporter:
    def __init__(self, source_path: Union[str, Path], db_path: Optional[Path] = None):
        self.source_path = Path(source_path)
        self.db_path = init_db(db_path)
        self.daily_records: Dict[str, Dict[str, Any]] = {}
        self.raw_records: List[tuple] = []

    def _get_or_create_daily(self, date_str: str) -> Dict[str, Any]:
        if date_str not in self.daily_records:
            self.daily_records[date_str] = {"date": date_str}
        return self.daily_records[date_str]

    def _read_json_file(self, content_bytes: bytes) -> Any:
        try:
            return json.loads(content_bytes.decode("utf-8"))
        except Exception:
            return None

    def _process_json_content(self, filename: str, data: Any):
        if not data:
            return

        fname_lower = filename.lower()
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and "hrvSummaries" in data:
            items = data["hrvSummaries"]

        for item in items:
            if not isinstance(item, dict):
                continue

            date_str = _clean_date_string(
                item.get("calendarDate") or item.get("date") or item.get("startTimeLocal") or item.get("startTimeGmt")
            )
            if not date_str:
                continue

            daily = self._get_or_create_daily(date_str)

            # 1. Sleep Data
            if "sleep" in fname_lower:
                self.raw_records.append((date_str, "SLEEP", json.dumps(item)))
                if item.get("sleepQualityScoreValue") is not None:
                    daily["sleep_score"] = int(item["sleepQualityScoreValue"])
                elif isinstance(item.get("sleepScores"), dict) and isinstance(item["sleepScores"].get("overall"), dict):
                    daily["sleep_score"] = item["sleepScores"]["overall"].get("value")

                daily["sleep_duration_seconds"] = item.get("sleepTimeSeconds") or item.get("userInitiatedSleepTimeSeconds")
                daily["deep_sleep_seconds"] = item.get("deepSleepSeconds")
                daily["rem_sleep_seconds"] = item.get("remSleepSeconds") or item.get("remSleepDataSeconds")
                daily["light_sleep_seconds"] = item.get("lightSleepSeconds")

            # 2. HRV Status
            elif "hrv" in fname_lower:
                self.raw_records.append((date_str, "HRV", json.dumps(item)))
                if item.get("weeklyAvg") is not None:
                    daily["hrv_weekly_avg"] = float(item["weeklyAvg"])
                if item.get("lastNightAvg") is not None:
                    daily["hrv_last_night"] = float(item["lastNightAvg"])
                if item.get("status") is not None:
                    daily["hrv_status"] = str(item["status"])

            # 3. Resting Heart Rate
            elif "restingheartrate" in fname_lower or "rhr" in fname_lower:
                self.raw_records.append((date_str, "RHR", json.dumps(item)))
                if item.get("restingHeartRate") is not None:
                    daily["resting_heart_rate"] = int(item["restingHeartRate"])

            # 4. Stress Details
            elif "stress" in fname_lower:
                self.raw_records.append((date_str, "STRESS", json.dumps(item)))
                if item.get("averageStressLevel") is not None or item.get("avgStressLevel") is not None:
                    daily["avg_stress_level"] = int(item.get("averageStressLevel") or item.get("avgStressLevel"))
                if item.get("maxStressLevel") is not None:
                    daily["max_stress_level"] = int(item["maxStressLevel"])

            # 5. Body Battery
            elif "bodybattery" in fname_lower:
                self.raw_records.append((date_str, "BODY_BATTERY", json.dumps(item)))
                if item.get("chargedValue") is not None or item.get("charged") is not None:
                    daily["body_battery_charged"] = int(item.get("chargedValue") or item.get("charged"))
                if item.get("drainedValue") is not None or item.get("drained") is not None:
                    daily["body_battery_drained"] = int(item.get("drainedValue") or item.get("drained"))
                if item.get("highestValue") is not None or item.get("highest") is not None:
                    daily["body_battery_highest"] = int(item.get("highestValue") or item.get("highest"))
                if item.get("lowestValue") is not None or item.get("lowest") is not None:
                    daily["body_battery_lowest"] = int(item.get("lowestValue") or item.get("lowest"))

            # 6. User Summary (General Daily Overview)
            elif "usersummary" in fname_lower or "user_summary" in fname_lower:
                self.raw_records.append((date_str, "USER_SUMMARY", json.dumps(item)))
                if item.get("restingHeartRate") is not None and daily.get("resting_heart_rate") is None:
                    daily["resting_heart_rate"] = int(item["restingHeartRate"])
                if (item.get("averageStressLevel") is not None) and daily.get("avg_stress_level") is None:
                    daily["avg_stress_level"] = int(item["averageStressLevel"])
                if item.get("maxStressLevel") is not None and daily.get("max_stress_level") is None:
                    daily["max_stress_level"] = int(item["maxStressLevel"])
                if item.get("totalSteps") is not None:
                    daily["total_steps"] = int(item["totalSteps"])
                if item.get("activeKilocalories") is not None:
                    daily["active_calories"] = int(item["activeKilocalories"])
                if item.get("vo2Max") is not None:
                    daily["vo2_max"] = float(item["vo2Max"])
                if item.get("bodyBatteryHighestValue") is not None and daily.get("body_battery_highest") is None:
                    daily["body_battery_highest"] = int(item["bodyBatteryHighestValue"])

            # 7. Activities
            elif "activities" in fname_lower or "activity" in fname_lower:
                self.raw_records.append((date_str, "ACTIVITIES", json.dumps(item)))
                act_list = daily.get("_activities_list", [])
                act_summary = {
                    "name": item.get("activityName") or item.get("name") or item.get("activityType"),
                    "type": item.get("activityType"),
                    "duration_seconds": item.get("duration"),
                    "distance_meters": item.get("distance"),
                    "calories": item.get("calories") or item.get("activeKilocalories"),
                    "avg_hr": item.get("averageHR"),
                    "max_hr": item.get("maxHR")
                }
                act_list.append(act_summary)
                daily["_activities_list"] = act_list

    def scan_and_parse(self):
        if not self.source_path.exists():
            raise FileNotFoundError(f"Garmin Export path does not exist: {self.source_path}")

        if self.source_path.is_file() and self.source_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(self.source_path, "r") as zf:
                for member in zf.infolist():
                    if member.filename.endswith(".json"):
                        content = zf.read(member)
                        json_data = self._read_json_file(content)
                        self._process_json_content(member.filename, json_data)
        elif self.source_path.is_dir():
            for root, _, files in os.walk(self.source_path):
                for file in files:
                    if file.endswith(".json"):
                        full_p = Path(root) / file
                        with open(full_p, "rb") as f:
                            json_data = self._read_json_file(f.read())
                            self._process_json_content(file, json_data)
        else:
            raise ValueError(f"Invalid source path: {self.source_path}. Must be a .zip file or folder.")

    def save_to_db(self) -> Dict[str, Any]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Insert raw records in batch
            if self.raw_records:
                cursor.executemany(
                    "INSERT INTO raw_garmin_data (date, data_type, raw_json) VALUES (?, ?, ?)",
                    self.raw_records
                )

            # Insert / Upsert daily metrics
            validated_tuples = []
            for date_str, daily_dict in self.daily_records.items():
                if "_activities_list" in daily_dict:
                    daily_dict["activities_summary"] = json.dumps(daily_dict.pop("_activities_list"))

                # Validate with Pydantic model (strict NULL enforcement)
                model = DailyMetrics(**daily_dict)
                validated_tuples.append(model.to_db_tuple())

            print(f"📦 Importing {len(validated_tuples)} daily metric records into database...")
            for tup in tqdm(validated_tuples, desc="Ingesting Daily Metrics"):
                cursor.execute(UPSERT_DAILY_METRICS_SQL, tup)

            conn.commit()

        return {
            "dates_processed": len(self.daily_records),
            "raw_records_inserted": len(self.raw_records),
            "db_path": str(self.db_path)
        }

def import_garmin_export(source_path: Union[str, Path], db_path: Optional[Path] = None) -> Dict[str, Any]:
    importer = GarminZipImporter(source_path, db_path)
    importer.scan_and_parse()
    return importer.save_to_db()
