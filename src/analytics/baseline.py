import json
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.db.connection import get_db_connection

TARGET_METRICS_KEYS = [
    "sleep_score",
    "hrv_last_night",
    "resting_heart_rate",
    "avg_stress_level",
    "active_calories",
    "total_steps"
]

def _calc_stats(values: List[float]) -> Dict[str, Any]:
    """Calculate summary statistics (avg, std, min, max, count) for numeric values, ignoring Nones."""
    valid_vals = [v for v in values if v is not None]
    if not valid_vals:
        return {
            "avg": None,
            "std": None,
            "min": None,
            "max": None,
            "sample_count": 0
        }
    
    n = len(valid_vals)
    avg = sum(valid_vals) / n
    std = statistics.stdev(valid_vals) if n > 1 else 0.0
    
    return {
        "avg": round(avg, 2),
        "std": round(std, 2),
        "min": min(valid_vals),
        "max": max(valid_vals),
        "sample_count": n
    }

def calculate_baseline(
    target_date: str,
    days: int = 30,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Calculate physiological baseline statistics over N days prior to target_date.
    
    Returns a dictionary containing:
      - target_date: target date string
      - target_metrics: dict of target date's metrics (or None values if missing)
      - sample_size_days: number of available historical records found in window
      - baseline_days_requested: N (default 30)
      - date_range: {"start": str, "end": str} of baseline data
      - metrics_baseline: dict of stat summaries for sleep_score, hrv_last_night, resting_heart_rate, avg_stress_level, active_calories, total_steps
      - training_load_7d: 7-day total training load and activity summary
    """
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    start_dt = target_dt - timedelta(days=days)
    start_date_str = start_dt.strftime("%Y-%m-%d")

    seven_days_dt = target_dt - timedelta(days=7)
    seven_days_str = seven_days_dt.strftime("%Y-%m-%d")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Fetch Target Date Metrics
        cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (target_date,))
        target_row = cursor.fetchone()
        target_metrics: Dict[str, Any] = {}
        if target_row:
            target_metrics = dict(target_row)
        else:
            for k in [
                "date", "sleep_score", "sleep_duration_seconds", "deep_sleep_seconds",
                "rem_sleep_seconds", "light_sleep_seconds", "hrv_weekly_avg",
                "hrv_last_night", "hrv_status", "resting_heart_rate", "avg_stress_level",
                "max_stress_level", "body_battery_charged", "body_battery_drained",
                "body_battery_highest", "body_battery_lowest", "active_calories",
                "total_steps", "vo2_max", "activities_summary"
            ]:
                target_metrics[k] = None
            target_metrics["date"] = target_date

        # 2. Fetch Baseline Rows (strictly prior to target_date up to N days)
        cursor.execute(
            """
            SELECT * FROM daily_metrics 
            WHERE date < ? AND date >= ? 
            ORDER BY date ASC
            """,
            (target_date, start_date_str)
        )
        baseline_rows = [dict(row) for row in cursor.fetchall()]

        # 3. Fetch 7-day rows for training load
        cursor.execute(
            """
            SELECT * FROM daily_metrics
            WHERE date < ? AND date >= ?
            ORDER BY date ASC
            """,
            (target_date, seven_days_str)
        )
        seven_day_rows = [dict(row) for row in cursor.fetchall()]

    sample_size_days = len(baseline_rows)
    date_range = {
        "start": baseline_rows[0]["date"] if baseline_rows else None,
        "end": baseline_rows[-1]["date"] if baseline_rows else None
    }

    # Aggregate metric series
    metric_series: Dict[str, List[float]] = {key: [] for key in TARGET_METRICS_KEYS}
    for row in baseline_rows:
        for key in TARGET_METRICS_KEYS:
            val = row.get(key)
            if val is not None:
                metric_series[key].append(float(val))

    metrics_baseline = {
        key: _calc_stats(metric_series[key])
        for key in TARGET_METRICS_KEYS
    }

    # 4. Calculate 7-day Training Load / Volume
    total_active_cal = 0
    total_steps_7d = 0
    total_workout_count = 0
    total_duration_sec = 0
    activities_7d: List[Dict[str, Any]] = []

    for row in seven_day_rows:
        if row.get("active_calories"):
            total_active_cal += row["active_calories"]
        if row.get("total_steps"):
            total_steps_7d += row["total_steps"]
        
        act_summary_raw = row.get("activities_summary")
        if act_summary_raw:
            try:
                acts = json.loads(act_summary_raw)
                if isinstance(acts, list):
                    for act in acts:
                        total_workout_count += 1
                        dur = act.get("duration_seconds") or 0
                        total_duration_sec += dur
                        activities_7d.append({
                            "date": row["date"],
                            **act
                        })
            except Exception:
                pass

    training_load_7d = {
        "total_active_calories": total_active_cal,
        "total_steps": total_steps_7d,
        "total_workout_count": total_workout_count,
        "total_duration_seconds": total_duration_sec,
        "activities": activities_7d
    }

    return {
        "target_date": target_date,
        "target_metrics": target_metrics,
        "sample_size_days": sample_size_days,
        "baseline_days_requested": days,
        "date_range": date_range,
        "metrics_baseline": metrics_baseline,
        "training_load_7d": training_load_7d
    }
