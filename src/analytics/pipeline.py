"""
Garmin Health AI Pipeline - Activity Sync, Mode Switching & Intraday Versioning Module.
Supports auto-detection and CLI flags for morning, midday, and evening reports.
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from src.db.connection import get_db_connection, init_db
from src.db.report_repository import save_report, get_report_by_type, get_all_reports_for_date
from src.services.nutrition_calculator import calculate_daily_macro_targets


def auto_detect_report_type(hour: Optional[int] = None) -> str:
    """
    Auto-detect intraday report_type based on current local hour:
    - hour < 10: 'morning'
    - 10 <= hour < 16: 'midday'
    - hour >= 16: 'evening'
    """
    if hour is None:
        hour = datetime.now().hour
    if hour < 10:
        return "morning"
    elif hour < 16:
        return "midday"
    else:
        return "evening"


def detect_today_morning_activity(
    target_date: str,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Query Garmin API / SQLite database for activities completed today (target_date).
    If a running/workout activity is completed:
      - returns morning_workout_done = True
      - workout details (type, distance_km, duration_min, avg_hr, cadence, gct_balance, calories)
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT activities_summary, active_calories FROM daily_metrics WHERE date = ?", (target_date,))
        row = cursor.fetchone()

    activities = []
    active_cal = 0.0

    if row:
        act_summary_raw, active_cal_db = row[0], row[1]
        active_cal = float(active_cal_db or 0.0)
        if act_summary_raw:
            try:
                parsed = json.loads(act_summary_raw)
                if isinstance(parsed, list):
                    activities = parsed
            except Exception:
                pass

    running_workout_types = ["running", "run", "treadmill_running", "trail_running", "cycling", "swimming", "workout", "fitness"]
    morning_workout = None

    for act in activities:
        act_type = str(act.get("type") or act.get("name") or "").lower()
        if any(t in act_type for t in running_workout_types) or (act.get("distance_meters") or 0) > 0 or (act.get("calories") or 0) > 100:
            morning_workout = act
            break

    workout_done = morning_workout is not None or (len(activities) > 0 and active_cal > 150)

    if morning_workout:
        act_cals = float(morning_workout.get("calories") or 250.0)
    else:
        act_cals = active_cal if workout_done else 0.0

    return {
        "morning_workout_done": workout_done,
        "morning_workout": morning_workout,
        "activities": activities,
        "active_calories": act_cals
    }


def resolve_day_mode(
    target_date: str,
    morning_workout_done: bool,
    days_to_race: Optional[int] = None,
    report_type: str = "morning"
) -> Tuple[str, str]:
    """
    Resolve dynamic day_type and Section 3 header title based on morning activity sync and report_type.
    """
    r_type = (report_type or "morning").lower()
    if r_type == "midday" or morning_workout_done:
        day_type = "taper_active" if (days_to_race is not None and days_to_race <= 14) else "easy_run"
        section_3_title = "3. Đánh giá Buổi tập Sáng nay & Kế hoạch Phục hồi Chiều"
    elif r_type == "evening":
        day_type = "taper_active" if (days_to_race is not None and days_to_race <= 14) else "rest"
        section_3_title = "3. Tổng kết Tải Vận động & Kế hoạch Tái tạo Đêm"
    else:
        day_type = "rest"
        section_3_title = "3. Kê đơn Vận động & Tải Tập luyện Hôm nay"

    return day_type, section_3_title


def run_health_pipeline(
    target_date: Optional[str] = None,
    report_type: str = "auto",
    dry_run: bool = False,
    send_telegram: bool = False,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Execute full intraday health analysis pipeline (morning, midday, evening).
    Preserves morning baseline context and saves versioned reports unique on (date, report_type).
    """
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    r_type = auto_detect_report_type() if report_type == "auto" else report_type.lower()

    from src.analytics.baseline import calculate_baseline
    from src.analytics.llm_analyst import generate_health_analysis
    from src.analytics.report_manager import save_report_to_db, export_report_to_file

    baseline_data = calculate_baseline(date_str, days=30, db_path=db_path)
    baseline_data["report_type"] = r_type
    if db_path:
        baseline_data["db_path"] = db_path

    if r_type != "morning":
        from src.db.report_repository import get_report_by_type
        m_rep = get_report_by_type(date_str, "morning", db_path=db_path)
        if m_rep and m_rep.get("content"):
            baseline_data["morning_report_snapshot"] = m_rep["content"]

    analysis_res = generate_health_analysis(baseline_data, dry_run=dry_run)


    if not dry_run:
        save_report_to_db(
            date=date_str,
            report_markdown=analysis_res["report_markdown"],
            raw_prompt=analysis_res.get("raw_prompt", ""),
            model_used=analysis_res.get("model_used", ""),
            status="SUCCESS",
            prompt_tokens=analysis_res.get("prompt_tokens", 0),
            completion_tokens=analysis_res.get("completion_tokens", 0),
            report_type=r_type,
            db_path=db_path
        )
        export_path = export_report_to_file(date_str, analysis_res["report_markdown"], report_type=r_type)
        analysis_res["exported_path"] = str(export_path)

        if send_telegram:
            from src.delivery.telegram_bot import send_multi_section_report
            from src.analytics.prompt_engine import generate_telegram_card_fallback
            from config.settings import settings
            card_text = analysis_res.get("telegram_card")
            if not card_text:
                card_text = generate_telegram_card_fallback(baseline_data)
            report_link = f"{settings.base_web_url}/report/{date_str}/{r_type}"
            telegram_msg = f"{card_text}\n\n📄 Xem phân tích chi tiết: {report_link}"
            send_multi_section_report([telegram_msg])
            analysis_res["sent_telegram"] = True

    return analysis_res


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Garmin Health AI Pipeline - Intraday Report Generator")
    parser.add_argument("--date", default=None, help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--type", choices=["auto", "morning", "midday", "evening"], default="auto", help="Report type (default: auto)")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt preview without calling API")
    parser.add_argument("--send-telegram", action="store_true", help="Send report to Telegram")

    args = parser.parse_args()
    print(f"🚀 Running Intraday Health Pipeline: date={args.date or 'today'}, type={args.type}...")
    res = run_health_pipeline(
        target_date=args.date,
        report_type=args.type,
        dry_run=args.dry_run,
        send_telegram=args.send_telegram
    )
    if args.dry_run:
        print("\n--- DRY RUN PROMPT PREVIEW ---")
        print(res.get("raw_prompt", ""))
    else:
        from config.settings import settings
        date_used = args.date or datetime.now().strftime("%Y-%m-%d")
        r_type_used = auto_detect_report_type() if args.type == "auto" else args.type.lower()
        report_link = f"{settings.base_web_url}/report/{date_used}/{r_type_used}"
        print(f"\n✅ Report generated successfully ({res.get('model_used')})!")
        print(f"📄 Saved full report markdown ({r_type_used}): {res.get('exported_path')}")
        print("\n--- TELEGRAM GLANCEABLE CARD OUTPUT ---")
        print(res.get("telegram_card", ""))
        print(f"\n📄 Xem phân tích chi tiết: {report_link}")


