import json
import time
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from garminconnect import Garmin
from src.db.connection import get_db_connection, init_db
from src.db.models import DailyMetrics
from src.db.schema import UPSERT_DAILY_METRICS_SQL
from .garmin_client import get_garmin_client

def _safe_get(dictionary: Any, *keys: str) -> Any:
    """Safely extract nested dictionary values without raising KeyError."""
    current = dictionary
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return None
    return current

def fetch_and_store_daily_data(
    target_date: str,
    client: Optional[Garmin] = None,
    db_path: Optional[Path] = None,
    verbose: bool = True
) -> DailyMetrics:
    """Fetch live daily metrics from Garmin Cloud API for target_date (YYYY-MM-DD),
    save raw payloads, normalize to DailyMetrics, and upsert into SQLite DB.
    """
    garmin_client = client or get_garmin_client()
    target_db_path = init_db(db_path)

    metrics: Dict[str, Any] = {
        "date": target_date,
        "raw_sync_timestamp": datetime.now().isoformat()
    }
    raw_payloads: List[tuple] = []

    # 1. Fetch Sleep Data
    try:
        sleep_data = garmin_client.get_sleep_data(target_date)
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
            metrics["awake_duration_seconds"] = daily_dto.get("awakeSleepSeconds")
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch sleep data for {target_date}: {e}")

    # 2. Fetch HRV Data
    try:
        hrv_data = garmin_client.get_hrv_data(target_date)
        if hrv_data:
            raw_payloads.append((target_date, "HRV", json.dumps(hrv_data)))
            hrv_summary = hrv_data.get("hrvSummary") or {}
            if hrv_summary.get("weeklyAvg") is not None:
                metrics["hrv_weekly_avg"] = float(hrv_summary["weeklyAvg"])
            if hrv_summary.get("lastNightAvg") is not None:
                metrics["hrv_last_night"] = float(hrv_summary["lastNightAvg"])
            if hrv_summary.get("status") is not None:
                metrics["hrv_status"] = str(hrv_summary["status"])
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch HRV data for {target_date}: {e}")

    # 3. Fetch User Daily Summary
    try:
        user_summary = garmin_client.get_user_summary(target_date)
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
            elif user_summary.get("vo2MaxRunning") is not None:
                metrics["vo2_max"] = float(user_summary["vo2MaxRunning"])

            if user_summary.get("lowestRespirationValue") is not None:
                metrics["respiration_min"] = float(user_summary["lowestRespirationValue"])
            if user_summary.get("highestRespirationValue") is not None:
                metrics["respiration_max"] = float(user_summary["highestRespirationValue"])
            if user_summary.get("avgWakingRespirationValue") is not None:
                metrics["respiration_avg"] = float(user_summary["avgWakingRespirationValue"])

            if user_summary.get("averageSpo2") is not None:
                metrics["spo2_avg"] = float(user_summary["averageSpo2"])
            if user_summary.get("lowestSpo2") is not None:
                metrics["spo2_min"] = float(user_summary["lowestSpo2"])

            if user_summary.get("trainingLoad7Days") is not None:
                metrics["training_load_7d"] = float(user_summary["trainingLoad7Days"])
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch user summary for {target_date}: {e}")

    # 4. Fetch Body Battery
    try:
        bb_data = garmin_client.get_body_battery(target_date)
        if bb_data:
            raw_payloads.append((target_date, "BODY_BATTERY", json.dumps(bb_data)))
            # Body battery endpoint often returns array of records
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
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch Body Battery for {target_date}: {e}")

    # 5. Fetch Activities
    try:
        activities = garmin_client.get_activities_by_date(target_date, target_date)
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
                        "avg_cadence": act.get("averageRunningCadenceInStepsPerMinute") or act.get("averageCadence"),
                        "gct_balance": act.get("avgGroundContactBalance") or act.get("groundContactBalance") or act.get("avgGroundContactTimeBalance"),
                        "stride_length_cm": act.get("averageStrideLength"),
                        "aerobic_training_effect": act.get("aerobicTrainingEffect")
                    })
            if act_summary_list:
                metrics["activities_summary"] = json.dumps(act_summary_list)
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch Activities for {target_date}: {e}")

    # 6. Fetch Dedicated Respiration Data
    try:
        resp_data = garmin_client.get_respiration_data(target_date)
        if resp_data and isinstance(resp_data, dict):
            raw_payloads.append((target_date, "RESPIRATION", json.dumps(resp_data)))
            if resp_data.get("lowestRespirationValue") is not None:
                metrics["respiration_min"] = float(resp_data["lowestRespirationValue"])
            if resp_data.get("highestRespirationValue") is not None:
                metrics["respiration_max"] = float(resp_data["highestRespirationValue"])
            
            avg_resp = resp_data.get("avgSleepRespirationValue") or resp_data.get("avgWakingRespirationValue")
            if avg_resp is not None:
                metrics["respiration_avg"] = float(avg_resp)
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch Respiration for {target_date}: {e}")

    # 7. Fetch Dedicated SpO2 Data
    try:
        spo2_data = garmin_client.get_spo2_data(target_date)
        if spo2_data and isinstance(spo2_data, dict):
            raw_payloads.append((target_date, "SPO2", json.dumps(spo2_data)))
            avg_spo2 = spo2_data.get("avgSleepSpO2") or spo2_data.get("averageSpO2")
            if avg_spo2 is not None:
                metrics["spo2_avg"] = float(avg_spo2)
            if spo2_data.get("lowestSpO2") is not None:
                metrics["spo2_min"] = float(spo2_data["lowestSpO2"])
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch SpO2 for {target_date}: {e}")

    # 8. Fetch Training Readiness
    try:
        readiness_data = garmin_client.get_training_readiness(target_date)
        if readiness_data:
            raw_payloads.append((target_date, "TRAINING_READINESS", json.dumps(readiness_data)))
            r_item = readiness_data[0] if isinstance(readiness_data, list) and readiness_data else (readiness_data if isinstance(readiness_data, dict) else {})
            if isinstance(r_item, dict):
                if r_item.get("score") is not None:
                    metrics["training_readiness_score"] = int(r_item["score"])
                rec_val = r_item.get("recoveryTime") or r_item.get("recoveryTimeHours")
                if rec_val is not None:
                    metrics["recovery_time_hours"] = int(rec_val // 60) if rec_val > 100 else int(rec_val)
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch Training Readiness for {target_date}: {e}")

    # 9. Fetch Training Status & VO2 Max
    try:
        status_data = garmin_client.get_training_status(target_date)
        if status_data and isinstance(status_data, dict):
            raw_payloads.append((target_date, "TRAINING_STATUS", json.dumps(status_data)))
            # Extract VO2 Max
            vo2_dto = _safe_get(status_data, "mostRecentVO2Max", "generic") or _safe_get(status_data, "mostRecentVO2Max", "running")
            if isinstance(vo2_dto, dict):
                vo2_val = vo2_dto.get("vo2MaxPreciseValue") or vo2_dto.get("vo2MaxValue")
                if vo2_val is not None:
                    metrics["vo2_max"] = float(vo2_val)

            # Extract Training Status
            ts_data_map = _safe_get(status_data, "mostRecentTrainingStatus", "latestTrainingStatusData")
            if isinstance(ts_data_map, dict):
                for key, ts_obj in ts_data_map.items():
                    if isinstance(ts_obj, dict):
                        phrase = ts_obj.get("trainingStatusFeedbackPhrase") or ts_obj.get("trainingStatus")
                        if phrase:
                            metrics["training_status"] = str(phrase)
                        break
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch Training Status for {target_date}: {e}")

    # 10. Fetch Body Composition / Weight
    try:
        weight_data = garmin_client.get_body_composition(target_date)
        if weight_data and isinstance(weight_data, dict):
            raw_payloads.append((target_date, "BODY_COMPOSITION", json.dumps(weight_data)))
            weight_list = weight_data.get("dateWeightList") or []
            if not weight_list and weight_data.get("totalAverage"):
                avg_item = weight_data["totalAverage"]
                if isinstance(avg_item, dict) and avg_item.get("weight") is not None:
                    weight_list = [avg_item]

            if weight_list and isinstance(weight_list, list):
                w_item = weight_list[-1]
                if isinstance(w_item, dict):
                    w_val = w_item.get("weight")
                    if w_val is not None:
                        w_kg = float(w_val) / 1000.0 if float(w_val) > 200 else float(w_val)
                        metrics["weight_kg"] = round(w_kg, 2)
                    if w_item.get("bodyFat") is not None or w_item.get("bodyFatPercentage") is not None:
                        metrics["body_fat_pct"] = float(w_item.get("bodyFat") or w_item.get("bodyFatPercentage"))
                    if w_item.get("muscleMass") is not None or w_item.get("muscleMassPercentage") is not None:
                        metrics["muscle_mass_pct"] = float(w_item.get("muscleMass") or w_item.get("muscleMassPercentage"))
                    if w_item.get("visceralFat") is not None:
                        metrics["visceral_fat"] = int(w_item["visceralFat"])
    except Exception as e:
        if verbose:
            print(f"⚠️ Warning: Failed to fetch Body Composition for {target_date}: {e}")

    # Validate with Pydantic DailyMetrics model
    daily_model = DailyMetrics(**metrics)

    # Save to SQLite Database
    with get_db_connection(target_db_path) as conn:
        cursor = conn.cursor()
        if raw_payloads:
            cursor.executemany(
                "INSERT INTO raw_garmin_data (date, data_type, raw_json) VALUES (?, ?, ?)",
                raw_payloads
            )
        cursor.execute(UPSERT_DAILY_METRICS_SQL, daily_model.to_db_tuple())
        conn.commit()

    # 11. Fetch & Sync Google Health Data (Weight / Body Fat)
    try:
        from src.ingestion.google_health_client import fetch_and_store_google_health_data
        fetch_and_store_google_health_data(target_date, verbose=verbose)
    except Exception as gh_err:
        if verbose:
            print(f"⚠️ Warning: Failed to sync Google Health data for {target_date}: {gh_err}")

    if verbose:
        print(f"✅ Successfully fetched and stored Garmin health data for {target_date}.")
    return daily_model


def backfill_historical_data(
    days: int = 30,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    force: bool = False,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Backfill historical health data from Garmin Connect API into SQLite DB.
    Loops backward date by date with random delays (1.5s - 3.0s) to prevent rate limits.
    Skips dates already present in daily_metrics unless force=True.
    """
    target_db_path = init_db(db_path)
    garmin_client = get_garmin_client()

    if start_date and end_date:
        dt_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        dt_end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        dt_end = datetime.now().date() - timedelta(days=1)
        dt_start = dt_end - timedelta(days=days - 1)

    # Generate date list from newest (end_date) backward to oldest (start_date)
    date_list = []
    curr = dt_end
    while curr >= dt_start:
        date_list.append(curr.strftime("%Y-%m-%d"))
        curr -= timedelta(days=1)

    # Check existing dates in DB
    existing_dates = set()
    with get_db_connection(target_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT date FROM daily_metrics")
        existing_dates = {row[0] for row in cursor.fetchall()}

    total_dates = len(date_list)
    synced_count = 0
    skipped_count = 0
    error_count = 0

    print(f"🚀 Starting backfill for {total_dates} dates ({date_list[-1]} to {date_list[0]})...\n")

    for idx, date_str in enumerate(date_list, 1):
        if not force and date_str in existing_dates:
            print(f"[{idx}/{total_dates}] ⏭️  {date_str}... SKIPPED (already in DB)")
            skipped_count += 1
            continue

        print(f"[{idx}/{total_dates}] 🔄 Fetching {date_str}...", end="", flush=True)
        try:
            res = fetch_and_store_daily_data(date_str, client=garmin_client, db_path=target_db_path, verbose=False)
            print(f" OK (Sleep: {res.sleep_score or 'N/A'}, HRV: {res.hrv_last_night or 'N/A'}, RHR: {res.resting_heart_rate or 'N/A'}, Steps: {res.total_steps or 'N/A'})")
            synced_count += 1
        except Exception as err:
            print(f" ❌ ERROR: {err}")
            error_count += 1

        if idx < total_dates:
            delay = random.uniform(1.5, 3.0)
            time.sleep(delay)

    return {
        "total_dates": total_dates,
        "synced": synced_count,
        "skipped": skipped_count,
        "errors": error_count,
        "date_range": {"start": date_list[-1], "end": date_list[0]} if date_list else {}
    }
