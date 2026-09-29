import pytest
from pathlib import Path
from src.db.connection import init_db, get_db_connection
from src.db.report_repository import (
    save_report,
    get_report_by_type,
    get_all_reports_for_date,
    delete_report_by_type
)
from src.analytics.pipeline import auto_detect_report_type, run_health_pipeline
from src.analytics.prompt_engine import REPORT_TYPE_HEADERS, get_report_title_header


def test_intraday_report_versioning_non_overwriting(tmp_path: Path):
    """
    Verify that saving a 'midday' or 'evening' report does NOT overwrite or delete an existing 'morning' report
    for the same date in the daily_reports SQLite table.
    """
    db_file = tmp_path / "test_intraday.db"
    init_db(db_file)

    target_date = "2026-09-29"

    # 1. Save Morning Report
    morning_content = "# 🌅 Báo cáo Khởi động Ngày & Đánh giá Giấc ngủ (Morning Briefing)\nMorning physiological baseline details."
    morning_snapshot = {"sleep_score": 85, "hrv_last_night": 65, "rhr": 52}
    saved_morning = save_report(target_date, "morning", morning_content, morning_snapshot, db_path=db_file)
    assert saved_morning["report_type"] == "morning"

    # Verify Morning Report exists
    rep_m = get_report_by_type(target_date, "morning", db_path=db_file)
    assert rep_m is not None
    assert rep_m["content"] == morning_content
    assert rep_m["metrics_snapshot"]["sleep_score"] == 85

    # 2. Save Midday Report for the SAME date
    midday_content = "# ☀️ Báo cáo Đánh giá Vận động Sáng & Điều chỉnh Trưa (Midday Review)\nMorning run completed, afternoon recovery planned."
    midday_snapshot = {"active_calories": 450, "workout_done": True}
    saved_midday = save_report(target_date, "midday", midday_content, midday_snapshot, db_path=db_file)
    assert saved_midday["report_type"] == "midday"

    # 3. VERIFY MORNING REPORT IS STILL INTACT AND NOT OVERWRITTEN BY MIDDAY REPORT
    rep_m_after = get_report_by_type(target_date, "morning", db_path=db_file)
    assert rep_m_after is not None
    assert rep_m_after["content"] == morning_content
    assert rep_m_after["metrics_snapshot"]["sleep_score"] == 85

    rep_mid = get_report_by_type(target_date, "midday", db_path=db_file)
    assert rep_mid is not None
    assert rep_mid["content"] == midday_content
    assert rep_mid["metrics_snapshot"]["active_calories"] == 450

    # 4. Save Evening Report for the SAME date
    evening_content = "# 🌙 Báo cáo Tổng kết Ngày & Vệ sinh Giấc ngủ (Evening Review)\nDaily calorie balance and sleep hygiene."
    saved_evening = save_report(target_date, "evening", evening_content, db_path=db_file)
    assert saved_evening["report_type"] == "evening"

    # 5. VERIFY ALL THREE REPORTS EXIST FOR THE SAME DATE
    all_reports = get_all_reports_for_date(target_date, db_path=db_file)
    assert len(all_reports) == 3

    types_found = [r["report_type"] for r in all_reports]
    assert "morning" in types_found
    assert "midday" in types_found
    assert "evening" in types_found

    # 6. Test delete by type
    deleted = delete_report_by_type(target_date, "midday", db_path=db_file)
    assert deleted is True
    remaining = get_all_reports_for_date(target_date, db_path=db_file)
    assert len(remaining) == 2
    assert get_report_by_type(target_date, "midday", db_path=db_file) is None
    assert get_report_by_type(target_date, "morning", db_path=db_file) is not None


def test_auto_detect_report_type_hours():
    """Verify hour boundaries for auto report_type detection."""
    # Morning: hour < 10
    assert auto_detect_report_type(hour=5) == "morning"
    assert auto_detect_report_type(hour=9) == "morning"

    # Midday: 10 <= hour < 16
    assert auto_detect_report_type(hour=10) == "midday"
    assert auto_detect_report_type(hour=12) == "midday"
    assert auto_detect_report_type(hour=15) == "midday"

    # Evening: hour >= 16
    assert auto_detect_report_type(hour=16) == "evening"
    assert auto_detect_report_type(hour=20) == "evening"
    assert auto_detect_report_type(hour=23) == "evening"


def test_report_type_headers():
    """Verify Telegram distinct headers for morning, midday, and evening reports."""
    assert "Morning Briefing" in REPORT_TYPE_HEADERS["morning"]
    assert "Midday Review" in REPORT_TYPE_HEADERS["midday"]
    assert "Evening Review" in REPORT_TYPE_HEADERS["evening"]

    header_m = get_report_title_header("morning", "Thứ Ba, 29/09/2026")
    assert "# 🌅 Báo cáo Khởi động Ngày & Đánh giá Giấc ngủ (Morning Briefing) (Thứ Ba, 29/09/2026)" in header_m

    header_mid = get_report_title_header("midday", "Thứ Ba, 29/09/2026")
    assert "# ☀️ Báo cáo Đánh giá Vận động Sáng & Điều chỉnh Trưa (Midday Review) (Thứ Ba, 29/09/2026)" in header_mid

    header_eve = get_report_title_header("evening", "Thứ Ba, 29/09/2026")
    assert "# 🌙 Báo cáo Tổng kết Ngày & Vệ sinh Giấc ngủ (Evening Review) (Thứ Ba, 29/09/2026)" in header_eve


def test_pipeline_dry_run_intraday_snapshot(tmp_path: Path):
    """
    Verify that generating a midday report dry-run embeds the morning snapshot context when available.
    """
    db_file = tmp_path / "test_pipeline.db"
    init_db(db_file)

    target_date = "2026-09-29"

    # Seed Morning report in DB
    morning_text = "MORNING_BASELINE_SLEEP_SCORE_88_HRV_70MS"
    save_report(target_date, "morning", morning_text, db_path=db_file)

    # Run pipeline dry run for midday
    res = run_health_pipeline(
        target_date=target_date,
        report_type="midday",
        dry_run=True,
        db_path=db_file
    )

    raw_prompt = res.get("raw_prompt", "")
    assert "MIDDAY" in raw_prompt
    assert "MORNING BRIEFING SNAPSHOT CONTEXT" in raw_prompt
    assert morning_text in raw_prompt
