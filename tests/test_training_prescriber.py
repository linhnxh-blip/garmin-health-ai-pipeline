"""
Unit tests for Training Prescriber, Dynamic Running Volume Logic,
Sleep Quality Cross-Check & Subjective Fatigue Guardrails.
"""

import pytest
from src.analytics.training_prescriber import (
    evaluate_run_readiness,
    get_post_race_run_volume,
    prescribe_running_workout,
    has_subjective_fatigue,
    has_gct_balance_issue,
    calculate_sleep_stage_percentages
)


def test_evaluate_run_readiness_hardware_barriers():
    # 1. Low Readiness (< 65)
    status, reason = evaluate_run_readiness(
        readiness_score=60, recovery_time_hours=2, deep_sleep_pct=18.0, rem_sleep_pct=22.0
    )
    assert status == "REST_OR_WALK"
    assert "Readiness" in reason

    # 2. High Recovery Time (> 6h)
    status, reason = evaluate_run_readiness(
        readiness_score=85, recovery_time_hours=8, deep_sleep_pct=18.0, rem_sleep_pct=22.0
    )
    assert status == "REST_OR_WALK"
    assert "Recovery Time" in reason

    # 3. Acute Sleep Deprivation (< 5 hours = 18000s)
    status, reason = evaluate_run_readiness(
        readiness_score=85, recovery_time_hours=2, sleep_duration_seconds=17400, deep_sleep_pct=18.0
    )
    assert status == "REST_OR_WALK"
    assert "Thiếu ngủ cấp tính" in reason

    # 4. Unbalanced HRV
    status, reason = evaluate_run_readiness(
        readiness_score=85, recovery_time_hours=2, hrv_status="UNBALANCED", deep_sleep_pct=18.0
    )
    assert status == "REST_OR_WALK"
    assert "HRV" in reason

    # 5. Post-Race Acute Phase (D+1 to D+7)
    status, reason = evaluate_run_readiness(
        readiness_score=85, recovery_time_hours=2, days_since_race=4, deep_sleep_pct=18.0
    )
    assert status == "REST_OR_WALK"
    assert "Post-Race Acute" in reason


def test_sleep_quality_cross_check_deep_and_rem():
    """Verify that despite green hardware metrics (Readiness 83, Recovery 1h),
    depressed Deep Sleep (< 10%) or depressed REM (< 15%) triggers OPTIONAL_ACTIVE_RECOVERY.
    """
    # Real-world 2026-10-25 case: Deep Sleep 9.6% (< 10.0%), REM 12.8% (< 15.0%)
    status, reason = evaluate_run_readiness(
        readiness_score=83,
        recovery_time_hours=1,
        deep_sleep_pct=9.6,
        rem_sleep_pct=12.8,
        sleep_duration_seconds=26160,
        hrv_status="BALANCED",
        days_since_race=21
    )
    assert status == "OPTIONAL_ACTIVE_RECOVERY"
    assert "Deep Sleep đêm qua thấp" in reason
    assert "Đi bộ thả lỏng hoặc bơi nhẹ 500m" in reason

    # Depressed REM alone (< 15%)
    status, reason = evaluate_run_readiness(
        readiness_score=80,
        recovery_time_hours=2,
        deep_sleep_pct=15.0,  # OK
        rem_sleep_pct=12.0,   # Depressed < 15%
        sleep_duration_seconds=27000,
        hrv_status="BALANCED"
    )
    assert status == "OPTIONAL_ACTIVE_RECOVERY"
    assert "REM Sleep đêm qua thấp" in reason


def test_subjective_fatigue_guardrail():
    """Verify that athlete subjective fatigue/soreness downgrades to OPTIONAL_ACTIVE_RECOVERY."""
    # Boolean feedback True
    has_fatigue, msg = has_subjective_fatigue(True)
    assert has_fatigue is True

    # Vietnamese fatigue keywords
    assert has_subjective_fatigue("Hôm nay cảm thấy nặng chân và mỏi cơ")[0] is True
    assert has_subjective_fatigue("Bắp chuối trái hơi căng cứng")[0] is True
    assert has_subjective_fatigue("Sáng nay thấy uể oải, nhức gân gót")[0] is True
    assert has_subjective_fatigue("legs feel sluggish and sore")[0] is True

    # Normal feedback without fatigue
    assert has_subjective_fatigue("Sức khỏe bình thường, tinh thần phấn chấn")[0] is False
    assert has_subjective_fatigue(None)[0] is False

    # Readiness evaluation with subjective fatigue
    status, reason = evaluate_run_readiness(
        readiness_score=85,
        recovery_time_hours=1,
        deep_sleep_pct=16.0,
        rem_sleep_pct=21.0,
        subjective_fatigue="Bắp chuối trái hơi mỏi và nặng chân"
    )
    assert status == "OPTIONAL_ACTIVE_RECOVERY"
    assert "Ghi nhận phản hồi mệt mỏi/nặng chân" in reason


def test_gct_balance_issue_guardrail():
    """Verify GCT asymmetry (> 51.0% L) trips biomechanical guardrail."""
    assert has_gct_balance_issue("51.8% L / 48.2% R")[0] is True
    assert has_gct_balance_issue("50.2% L / 49.8% R")[0] is False
    assert has_gct_balance_issue(51.5)[0] is True

    status, reason = evaluate_run_readiness(
        readiness_score=85,
        recovery_time_hours=1,
        deep_sleep_pct=16.0,
        rem_sleep_pct=21.0,
        gct_balance_issue=True
    )
    assert status == "OPTIONAL_ACTIVE_RECOVERY"
    assert "GCT Balance" in reason


def test_all_clear_go_run():
    """Verify fully primed athlete receives GO_RUN."""
    status, reason = evaluate_run_readiness(
        readiness_score=85,
        recovery_time_hours=2,
        deep_sleep_pct=17.5,
        rem_sleep_pct=21.0,
        sleep_duration_seconds=28000,
        hrv_status="BALANCED",
        days_since_race=18
    )
    assert status == "GO_RUN"
    assert reason is None


def test_dynamic_running_volume_progressive_ladder():
    """Verify progressive 4-week ladder post-marathon:
    - Week 1 (D+1-7): 0km (Acute)
    - Week 2 (D+8-14): 2.0-3.0km (Shakeout)
    - Week 3 (D+15-21): 3.5-5.0km (Progressive Recovery Zone 2)
    - Week 4+ (D+22+): 5.0-7.0km (MAF Zone 2)
    """
    # Week 1
    vol_w1 = get_post_race_run_volume(days_since_race=3)
    assert vol_w1["week"] == 1
    assert vol_w1["min_km"] == 0.0
    assert vol_w1["distance_str"] == "0 km"

    # Week 2 (Shakeout Run)
    vol_w2 = get_post_race_run_volume(days_since_race=10)
    assert vol_w2["week"] == 2
    assert vol_w2["min_km"] == 2.0
    assert vol_w2["max_km"] == 3.0
    assert "2.0 - 3.0 km" in vol_w2["distance_str"]
    assert vol_w2["is_shakeout"] is True
    assert vol_w2["hr_cap_bpm"] == 135

    # Week 3 (Progressive Overload Breakout from 2-3km trap!)
    vol_w3 = get_post_race_run_volume(days_since_race=21)
    assert vol_w3["week"] == 3
    assert vol_w3["min_km"] == 3.5
    assert vol_w3["max_km"] == 5.0
    assert "3.5 - 5.0 km" in vol_w3["distance_str"]
    assert vol_w3["is_shakeout"] is False
    assert vol_w3["hr_cap_bpm"] == 138

    # Week 4+ (MAF Base Building)
    vol_w4 = get_post_race_run_volume(days_since_race=25)
    assert vol_w4["week"] == 4
    assert vol_w4["min_km"] == 5.0
    assert vol_w4["max_km"] == 7.0
    assert "5.0 - 7.0 km" in vol_w4["distance_str"]
    assert vol_w4["hr_cap_bpm"] == 136


def test_prescribe_running_workout_full_pipeline():
    """Verify end-to-end workout prescription generation."""
    # 1. 2026-10-25 case: D+21, Readiness 83, Deep Sleep 9.6% -> OPTIONAL_ACTIVE_RECOVERY
    presc_today = prescribe_running_workout(
        readiness_score=83,
        recovery_time_hours=1,
        deep_sleep_pct=9.6,
        rem_sleep_pct=12.8,
        sleep_duration_seconds=26160,
        hrv_status="BALANCED",
        days_since_race=21,
        phase="POST_RACE_RECOVERY"
    )
    assert presc_today["status"] == "OPTIONAL_ACTIVE_RECOVERY"
    assert "Đi bộ" in presc_today["option_1"]["title"] or "ƯU TIÊN VẬN ĐỘNG PHỤC HỒI" in presc_today["option_1"]["title"]
    assert "Deep Sleep đêm qua thấp" in presc_today["reason"]
    assert "Ưu tiên đi bộ 15-20p hoặc bơi 500m" in presc_today["brief_line"]

    # 2. Primed athlete at Week 3 (D+21, Deep 16%, REM 22%) -> GO_RUN 3.5-5.0km
    presc_primed = prescribe_running_workout(
        readiness_score=83,
        recovery_time_hours=1,
        deep_sleep_pct=16.0,
        rem_sleep_pct=22.0,
        sleep_duration_seconds=26160,
        hrv_status="BALANCED",
        days_since_race=21,
        phase="POST_RACE_RECOVERY"
    )
    assert presc_primed["status"] == "GO_RUN"
    assert "3.5 - 5.0 km" in presc_primed["option_1"]["title"]
    assert "Zone 2" in presc_primed["option_1"]["description"]


def test_calculate_sleep_stage_percentages():
    """Verify exact 100.0% sum for sleep stages."""
    stages = calculate_sleep_stage_percentages(
        deep_sleep_seconds=2520,   # 42.0m
        rem_sleep_seconds=3360,    # 56.0m
        light_sleep_seconds=20280, # 338.0m
        awake_duration_seconds=240 # 4.0m
    )
    assert stages["deep_min"] == 42.0
    assert stages["rem_min"] == 56.0
    assert stages["light_min"] == 338.0
    assert stages["deep_pct"] == 9.6
    assert stages["rem_pct"] == 12.8
    assert stages["light_pct"] == 77.6
    # Exact 100.0%
    assert round(stages["deep_pct"] + stages["rem_pct"] + stages["light_pct"], 1) == 100.0
