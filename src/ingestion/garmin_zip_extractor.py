import io
import os
import sys
import json
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Union, Optional, Tuple
from datetime import datetime
from tqdm import tqdm

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import fitparse

from src.db.connection import get_db_connection, init_db
from src.db.schema import UPSERT_DAILY_METRICS_SQL, INSERT_NUTRITION_LOG_SQL

def _clean_date_str(raw_val: Any) -> Optional[str]:
    """Helper to convert timestamps or date strings into YYYY-MM-DD format."""
    if not raw_val:
        return None
    val_str = str(raw_val).strip()
    if len(val_str) >= 10 and val_str[4] == '-' and val_str[7] == '-':
        return val_str[:10]
    try:
        ts = float(val_str)
        if ts > 1e11:
            ts /= 1000.0
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None

def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None

def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(round(float(val)))
    except (ValueError, TypeError):
        return None


class GarminZipExtractor:
    """Automated in-memory ZIP extractor for Garmin Data Export zip archives.
    Parses Wellness JSON, UDS Aggregator JSON, Biometrics JSON, and nested FIT activity files.
    """
    def __init__(self, zip_path: Union[str, Path], db_path: Optional[Path] = None):
        self.zip_path = Path(zip_path)
        if not self.zip_path.exists():
            raise FileNotFoundError(f"Garmin Data Export ZIP file not found at: {self.zip_path}")
        
        self.db_path = init_db(db_path)
        self.daily_metrics: Dict[str, Dict[str, Any]] = {}
        self.raw_records: List[Tuple[str, str, str]] = []
        
        self.sleep_days_count = 0
        self.uds_days_count = 0
        self.biometrics_days_count = 0
        self.fit_running_count = 0
        self.hrm_pro_count = 0

    def _get_or_create_daily(self, date_str: str) -> Dict[str, Any]:
        if date_str not in self.daily_metrics:
            self.daily_metrics[date_str] = {
                "date": date_str,
                "_activities": []
            }
        return self.daily_metrics[date_str]

    def _parse_sleep_data(self, item: Dict[str, Any]):
        date_str = _clean_date_str(item.get("calendarDate") or item.get("date"))
        if not date_str:
            return
        
        daily = self._get_or_create_daily(date_str)
        self.sleep_days_count += 1
        self.raw_records.append((date_str, "SLEEP", json.dumps(item)))

        # Sleep scores
        scores = item.get("sleepScores")
        if isinstance(scores, dict):
            if scores.get("overallScore") is not None:
                daily["sleep_score"] = _safe_int(scores.get("overallScore"))
            elif isinstance(scores.get("overall"), dict):
                daily["sleep_score"] = _safe_int(scores["overall"].get("value"))
        elif item.get("sleepQualityScoreValue") is not None:
            daily["sleep_score"] = _safe_int(item.get("sleepQualityScoreValue"))

        # Sleep durations
        if item.get("deepSleepSeconds") is not None:
            daily["deep_sleep_seconds"] = _safe_int(item["deepSleepSeconds"])
        if item.get("remSleepSeconds") is not None:
            daily["rem_sleep_seconds"] = _safe_int(item["remSleepSeconds"])
        if item.get("lightSleepSeconds") is not None:
            daily["light_sleep_seconds"] = _safe_int(item["lightSleepSeconds"])
        if item.get("awakeSleepSeconds") is not None:
            daily["awake_duration_seconds"] = _safe_int(item["awakeSleepSeconds"])
        
        tot_dur = item.get("sleepTimeSeconds") or item.get("userInitiatedSleepTimeSeconds")
        if tot_dur is None and all(daily.get(k) is not None for k in ["deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds"]):
            tot_dur = (daily.get("deep_sleep_seconds") or 0) + (daily.get("light_sleep_seconds") or 0) + (daily.get("rem_sleep_seconds") or 0) + (daily.get("awake_duration_seconds") or 0)
        if tot_dur is not None:
            daily["sleep_duration_seconds"] = _safe_int(tot_dur)

        # Respiration
        if item.get("averageRespiration") is not None:
            daily["respiration_avg"] = _safe_float(item["averageRespiration"])
        if item.get("lowestRespiration") is not None:
            daily["respiration_min"] = _safe_float(item["lowestRespiration"])
        if item.get("highestRespiration") is not None:
            daily["respiration_max"] = _safe_float(item["highestRespiration"])

        # SpO2
        spo2_sum = item.get("spo2SleepSummary")
        if isinstance(spo2_sum, dict):
            if spo2_sum.get("averageSPO2") is not None:
                daily["spo2_avg"] = _safe_float(spo2_sum["averageSPO2"])
            if spo2_sum.get("lowestSPO2") is not None:
                daily["spo2_min"] = _safe_float(spo2_sum["lowestSPO2"])

    def _parse_uds_data(self, item: Dict[str, Any]):
        date_str = _clean_date_str(item.get("calendarDate") or item.get("date"))
        if not date_str:
            return
        
        daily = self._get_or_create_daily(date_str)
        self.uds_days_count += 1
        self.raw_records.append((date_str, "UDS", json.dumps(item)))

        if item.get("restingHeartRate") is not None:
            daily["resting_heart_rate"] = _safe_int(item["restingHeartRate"])
        elif item.get("currentDayRestingHeartRate") is not None:
            daily["resting_heart_rate"] = _safe_int(item["currentDayRestingHeartRate"])

        if item.get("totalSteps") is not None:
            daily["total_steps"] = _safe_int(item["totalSteps"])
        if item.get("dailyStepGoal") is not None:
            daily["step_goal"] = _safe_int(item["dailyStepGoal"])
        if item.get("activeKilocalories") is not None:
            daily["active_calories"] = _safe_int(item["activeKilocalories"])
        if item.get("vo2Max") is not None:
            daily["vo2_max"] = _safe_float(item["vo2Max"])

        # HRV Status from UDS or HRV summary
        if item.get("lastNightAvg") is not None:
            daily["hrv_last_night"] = _safe_float(item["lastNightAvg"])
        if item.get("weeklyAvg") is not None:
            daily["hrv_weekly_avg"] = _safe_float(item["weeklyAvg"])
        if item.get("status") is not None:
            daily["hrv_status"] = str(item["status"])

        # Stress
        stress_info = item.get("allDayStress")
        if isinstance(stress_info, dict) and isinstance(stress_info.get("aggregatorList"), list):
            for agg in stress_info["aggregatorList"]:
                if isinstance(agg, dict) and agg.get("type") == "TOTAL":
                    if agg.get("averageStressLevel") is not None:
                        daily["avg_stress_level"] = _safe_int(agg["averageStressLevel"])
                    if agg.get("maxStressLevel") is not None:
                        daily["max_stress_level"] = _safe_int(agg["maxStressLevel"])
                    break

        # SpO2
        if item.get("averageSpo2Value") is not None:
            daily["spo2_avg"] = _safe_float(item["averageSpo2Value"])
        if item.get("lowestSpo2Value") is not None:
            daily["spo2_min"] = _safe_float(item["lowestSpo2Value"])

        # Body Battery
        bb_info = item.get("bodyBattery")
        if isinstance(bb_info, dict):
            if bb_info.get("chargedValue") is not None:
                daily["body_battery_charged"] = _safe_int(bb_info["chargedValue"])
            if bb_info.get("drainedValue") is not None:
                daily["body_battery_drained"] = _safe_int(bb_info["drainedValue"])
            
            stats = bb_info.get("bodyBatteryStatList")
            if isinstance(stats, list):
                for st in stats:
                    if isinstance(st, dict):
                        st_type = st.get("bodyBatteryStatType")
                        if st_type == "HIGHEST" and st.get("statsValue") is not None:
                            daily["body_battery_highest"] = _safe_int(st["statsValue"])
                        elif st_type == "LOWEST" and st.get("statsValue") is not None:
                            daily["body_battery_lowest"] = _safe_int(st["statsValue"])

    def _parse_biometrics_data(self, item: Dict[str, Any]):
        date_str = _clean_date_str(item.get("calendarDate") or item.get("date") or item.get("sampleTime"))
        if not date_str:
            return
        
        daily = self._get_or_create_daily(date_str)
        self.biometrics_days_count += 1
        self.raw_records.append((date_str, "BIOMETRICS", json.dumps(item)))

        # Weight in grams or kg
        raw_w = item.get("weight") or item.get("weightKg") or item.get("weight_kg")
        if raw_w is not None:
            w_val = float(raw_w)
            if w_val > 1000.0:  # weight in grams
                w_val /= 1000.0
            if 30.0 < w_val < 250.0:
                daily["weight_kg"] = round(w_val, 2)

        bf = item.get("bodyFat") or item.get("bodyFatPct") or item.get("percentFat") or item.get("bodyFatPercentage") or item.get("body_fat_pct")
        if bf is not None:
            daily["body_fat_pct"] = _safe_float(bf)

        mm = item.get("muscleMassPct") or item.get("muscleMass") or item.get("muscleMassPercentage") or item.get("muscle_mass_pct")
        if mm is not None:
            daily["muscle_mass_pct"] = _safe_float(mm)

        vf = item.get("visceralFatRating") or item.get("visceralFat") or item.get("visceral_fat")
        if vf is not None:
            daily["visceral_fat"] = _safe_int(vf)

    def _parse_summarized_activities(self, item: Dict[str, Any]):
        activities_list = item if isinstance(item, list) else [item]
        for act in activities_list:
            if not isinstance(act, dict):
                continue
            date_str = _clean_date_str(act.get("startTimeLocal") or act.get("startTimeGmt") or act.get("beginTimestamp"))
            if not date_str:
                continue
            
            daily = self._get_or_create_daily(date_str)
            act_entry = {
                "name": act.get("activityName") or act.get("name") or act.get("activityType"),
                "type": act.get("activityType"),
                "duration_seconds": act.get("duration") or act.get("elapsedDuration"),
                "distance_meters": act.get("distance"),
                "calories": act.get("calories") or act.get("activeKilocalories"),
                "avg_hr": act.get("averageHR") or act.get("avgHr"),
                "max_hr": act.get("maxHR") or act.get("maxHr")
            }
            if act.get("avgFractionalCadence") is not None:
                cad = float(act["avgFractionalCadence"])
                act_entry["avg_cadence"] = round(cad * 2) if cad < 120 else round(cad)
            
            daily["_activities"].append(act_entry)

    def _parse_fit_stream(self, fit_bytes: bytes, filename: str):
        if len(fit_bytes) < 20000:
            return

        try:
            ff = fitparse.FitFile(io.BytesIO(fit_bytes), check_crc=False)
            session_msgs = list(ff.get_messages("session"))
            if not session_msgs:
                return

            for msg in session_msgs:
                fields = {f.name: f.value for f in msg.fields}
                sport = str(fields.get("sport") or "").lower()
                
                # We focus primarily on running activities and activities with biomechanics
                is_running = "run" in sport
                if is_running:
                    self.fit_running_count += 1

                ts_val = fields.get("timestamp") or fields.get("start_time")
                date_str = _clean_date_str(ts_val)
                if not date_str:
                    continue

                daily = self._get_or_create_daily(date_str)

                # Extract HRM-Pro running dynamics
                gct_bal = fields.get("avg_stance_time_balance") or fields.get("stance_time_balance")
                gct_ms = fields.get("avg_stance_time") or fields.get("stance_time")
                vert_osc = fields.get("avg_vertical_oscillation") or fields.get("vertical_oscillation")
                step_len = fields.get("avg_step_length") or fields.get("step_length")
                vert_ratio = fields.get("avg_vertical_ratio") or fields.get("vertical_ratio")
                cadence = fields.get("avg_running_cadence") or fields.get("avg_cadence")

                has_hrm_pro = any(v is not None for v in [gct_bal, gct_ms, vert_osc])
                if has_hrm_pro and is_running:
                    self.hrm_pro_count += 1

                act_entry = {
                    "filename": filename,
                    "name": f"Chạy bộ Garmin ({fields.get('total_distance', 0)/1000:.2f} km)" if is_running else f"Bài tập Garmin ({sport})",
                    "type": sport or "running",
                    "duration_seconds": _safe_float(fields.get("total_timer_time") or fields.get("total_elapsed_time")),
                    "distance_meters": _safe_float(fields.get("total_distance")),
                    "calories": _safe_int(fields.get("total_calories")),
                    "avg_hr": _safe_int(fields.get("avg_heart_rate")),
                    "max_hr": _safe_int(fields.get("max_heart_rate")),
                    "avg_cadence": _safe_int(cadence),
                    "gct_balance": gct_bal,
                    "gct_ms": _safe_float(gct_ms),
                    "vertical_oscillation_mm": _safe_float(vert_osc),
                    "step_length_mm": _safe_float(step_len),
                    "vertical_ratio_pct": _safe_float(vert_ratio)
                }

                daily["_activities"].append(act_entry)
        except Exception:
            pass

    def extract_and_ingest(self) -> Dict[str, Any]:
        """Process main ZIP archive in-memory without unzipping to disk."""
        print(f"📦 Opening Garmin Export ZIP Archive: '{self.zip_path}'...")
        
        with zipfile.ZipFile(self.zip_path, "r") as main_zf:
            all_entries = main_zf.namelist()
            print(f"🔍 Found {len(all_entries)} items in root ZIP archive. Scanning files...")

            for item_name in tqdm(all_entries, desc="Scanning Garmin Export Archive"):
                item_lower = item_name.lower()
                
                # Ignore zero-byte / junk / HTML UI / system log files
                if item_lower.endswith(("/", ".html", ".png", ".jpg", ".css", ".js", ".txt")) or "junk" in item_lower:
                    continue

                # 1. Process nested .zip archives (e.g. UploadedFiles_*.zip)
                if item_name.endswith(".zip"):
                    try:
                        inner_bytes = main_zf.read(item_name)
                        with zipfile.ZipFile(io.BytesIO(inner_bytes), "r") as inner_zf:
                            for inner_info in inner_zf.infolist():
                                inner_name = inner_info.filename
                                inner_lower = inner_name.lower()
                                if inner_lower.endswith(".fit"):
                                    if inner_info.file_size > 20000:
                                        fit_data = inner_zf.read(inner_name)
                                        self._parse_fit_stream(fit_data, inner_name)
                                elif inner_lower.endswith(".json"):
                                    json_bytes = inner_zf.read(inner_name)
                                    try:
                                        data = json.loads(json_bytes.decode("utf-8"))
                                        self._process_single_json(inner_name, data)
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                    continue

                # 2. Process direct .fit files in main zip
                if item_name.endswith(".fit"):
                    try:
                        info = main_zf.getinfo(item_name)
                        if info.file_size > 20000:
                            fit_data = main_zf.read(item_name)
                            self._parse_fit_stream(fit_data, item_name)
                    except Exception:
                        pass
                    continue

                # 3. Process direct .json files in main zip
                if item_name.endswith(".json"):
                    try:
                        json_bytes = main_zf.read(item_name)
                        data = json.loads(json_bytes.decode("utf-8"))
                        self._process_single_json(item_name, data)
                    except Exception:
                        pass

        # Save aggregated metrics to SQLite DB
        return self._save_to_database()

    def _process_single_json(self, filename: str, data: Any):
        if not data:
            return

        fname_lower = filename.lower()
        items = data if isinstance(data, list) else [data]

        if isinstance(data, dict) and "hrvSummaries" in data:
            items = data["hrvSummaries"]
        elif isinstance(data, dict) and "summarizedActivitiesExport" in data:
            items = data["summarizedActivitiesExport"]

        for item in items:
            if not isinstance(item, dict):
                continue
            
            if "sleepdata" in fname_lower or "sleep" in fname_lower:
                self._parse_sleep_data(item)
            elif "udsfile" in fname_lower or "uds" in fname_lower or "usersummary" in fname_lower:
                self._parse_uds_data(item)
            elif "biometric" in fname_lower or "weight" in fname_lower:
                self._parse_biometrics_data(item)
            elif "summarizedactivities" in fname_lower or "activities" in fname_lower:
                self._parse_summarized_activities(item)

    def _save_to_database(self) -> Dict[str, Any]:
        """Save parsed daily metrics and raw logs into SQLite `daily_metrics` table."""
        if not self.daily_metrics:
            return {
                "sleep_days_count": 0,
                "fit_running_count": 0,
                "hrm_pro_count": 0,
                "total_dates": 0,
                "min_date": None,
                "max_date": None
            }

        sorted_dates = sorted(self.daily_metrics.keys())
        min_date = sorted_dates[0]
        max_date = sorted_dates[-1]

        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Batch insert raw JSON logs if any
            if self.raw_records:
                cursor.executemany(
                    "INSERT INTO raw_garmin_data (date, data_type, raw_json) VALUES (?, ?, ?)",
                    self.raw_records
                )

            # Insert / Upsert daily metrics
            upsert_tuples = []
            for date_str in sorted_dates:
                d = self.daily_metrics[date_str]
                acts = d.get("_activities", [])
                acts_json = json.dumps(acts, ensure_ascii=False) if acts else None

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                tup = (
                    date_str,
                    d.get("sleep_score"),
                    d.get("sleep_duration_seconds"),
                    d.get("deep_sleep_seconds"),
                    d.get("rem_sleep_seconds"),
                    d.get("light_sleep_seconds"),
                    d.get("awake_duration_seconds"),
                    d.get("hrv_weekly_avg"),
                    d.get("hrv_last_night"),
                    d.get("hrv_status"),
                    d.get("resting_heart_rate"),
                    d.get("avg_stress_level"),
                    d.get("max_stress_level"),
                    d.get("body_battery_charged"),
                    d.get("body_battery_drained"),
                    d.get("body_battery_highest"),
                    d.get("body_battery_lowest"),
                    d.get("active_calories"),
                    d.get("total_steps"),
                    d.get("step_goal"),
                    d.get("vo2_max"),
                    d.get("respiration_min"),
                    d.get("respiration_max"),
                    d.get("respiration_avg"),
                    d.get("spo2_avg"),
                    d.get("spo2_min"),
                    d.get("training_load_7d"),
                    d.get("training_readiness_score"),
                    d.get("recovery_time_hours"),
                    d.get("training_status"),
                    d.get("skin_temp_deviation"),
                    d.get("weight_kg"),
                    d.get("body_fat_pct"),
                    d.get("muscle_mass_pct"),
                    d.get("visceral_fat"),
                    acts_json,
                    d.get("raw_sync_timestamp") or now_str,
                    now_str
                )
                upsert_tuples.append(tup)

            print(f"\n💾 Upserting {len(upsert_tuples)} daily metric records into SQLite `daily_metrics`...")
            for tup in tqdm(upsert_tuples, desc="Ingesting Daily Metrics to DB"):
                cursor.execute(UPSERT_DAILY_METRICS_SQL, tup)

            conn.commit()

        return {
            "total_dates": len(sorted_dates),
            "min_date": min_date,
            "max_date": max_date,
            "sleep_days_count": self.sleep_days_count,
            "uds_days_count": self.uds_days_count,
            "biometrics_days_count": self.biometrics_days_count,
            "fit_running_count": self.fit_running_count,
            "hrm_pro_count": self.hrm_pro_count
        }


def process_garmin_zip_archive(zip_path: Union[str, Path], db_path: Optional[Path] = None) -> Dict[str, Any]:
    extractor = GarminZipExtractor(zip_path, db_path=db_path)
    return extractor.extract_and_ingest()
