"""
Unit tests for Midday Review Clinical Sports Medicine Logic:
- calculate_evening_targets (protein caps, anti-carb-dumping, realistic fat status)
- detect_high_purine_lunch (purine detection, alkaline hydration counter-measures)
- calculate_midday_nutrition_plan (unconsumed carb, natural fat floor)
- strip_stale_midday_footer
- prompt engine integration for midday review
"""

import pytest
from src.analytics.midday_review import (
    MacroTarget,
    calculate_evening_targets,
    detect_high_purine_lunch,
    calculate_midday_nutrition_plan,
    strip_stale_midday_footer
)


def test_calculate_evening_targets_protein_cap_overload():
    """When logged protein >= 80g (e.g. 81g), dinner protein is strictly capped at min(rem_p, 15.0)."""
    daily_target = MacroTarget(protein=93.4, carb=344.8, fat=48.3)
    logged_intake = MacroTarget(protein=81.0, carb=136.0, fat=48.5)

    p_target, c_target, fat_status = calculate_evening_targets(
        daily_target, logged_intake, uric_acid_level=442.0
    )

    # 93.4 - 81.0 = 12.4g -> min(12.4, 15.0) = 12.4
    assert p_target == 12.4
    assert p_target <= 15.0

    # If rem_p was 25.0g with logged >= 80g:
    daily_target_high = MacroTarget(protein=110.0, carb=350.0, fat=50.0)
    logged_high = MacroTarget(protein=85.0, carb=150.0, fat=40.0)
    p_high, _, _ = calculate_evening_targets(daily_target_high, logged_high, uric_acid_level=442.0)
    assert p_high == 15.0  # strictly capped at 15g


def test_calculate_evening_targets_protein_cap_normal():
    """When logged protein < 80g, dinner protein target is capped at min(rem_p, 28.0)."""
    daily_target = MacroTarget(protein=95.0, carb=250.0, fat=50.0)
    logged_intake = MacroTarget(protein=50.0, carb=120.0, fat=25.0)

    p_target, c_target, fat_status = calculate_evening_targets(
        daily_target, logged_intake, uric_acid_level=442.0
    )

    # 95 - 50 = 45 -> min(45, 28.0) = 28.0
    assert p_target == 28.0

    # When remaining protein is small (< 28g), e.g. 18g:
    logged_almost = MacroTarget(protein=77.0, carb=150.0, fat=35.0)
    p_almost, _, _ = calculate_evening_targets(daily_target, logged_almost, uric_acid_level=442.0)
    assert p_almost == 18.0


def test_calculate_evening_targets_carb_cap_no_dumping():
    """Remaining carbs are capped at 70g for dinner to prevent Carb-Dumping Syndrome."""
    daily_target = MacroTarget(protein=93.4, carb=344.8, fat=48.3)
    logged_intake = MacroTarget(protein=81.0, carb=136.0, fat=48.5)

    # Remaining carb = 344.8 - 136.0 = 208.8g
    _, c_target, _ = calculate_evening_targets(daily_target, logged_intake, uric_acid_level=442.0)
    assert c_target == 70.0
    assert c_target <= 75.0

    # When remaining carb is small (< 70g):
    daily_low_c = MacroTarget(protein=90.0, carb=180.0, fat=45.0)
    logged_low_c = MacroTarget(protein=60.0, carb=140.0, fat=35.0)
    _, c_low, _ = calculate_evening_targets(daily_low_c, logged_low_c, uric_acid_level=442.0)
    assert c_low == 40.0


def test_calculate_evening_targets_fat_status():
    """Fat status returns EXCEEDED when rem_f <= 0, and AVAILABLE when rem_f > 0."""
    # Exceeded fat
    dt = MacroTarget(protein=90.0, carb=200.0, fat=48.0)
    li_exceeded = MacroTarget(protein=70.0, carb=100.0, fat=48.5)
    _, _, status_exc = calculate_evening_targets(dt, li_exceeded)
    assert status_exc == "EXCEEDED"

    # Available fat
    li_avail = MacroTarget(protein=70.0, carb=100.0, fat=35.0)
    _, _, status_avail = calculate_evening_targets(dt, li_avail)
    assert status_avail == "AVAILABLE"


def test_calculate_evening_targets_dict_compatibility():
    """calculate_evening_targets accepts both dictionaries and objects seamlessly."""
    dt_dict = {"protein": 94.0, "carb": 300.0, "fat": 50.0}
    li_dict = {"protein": 82.0, "carb": 150.0, "fat": 52.0}

    p, c, f_stat = calculate_evening_targets(dt_dict, li_dict)
    assert p == 12.0
    assert c == 70.0
    assert f_stat == "EXCEEDED"


def test_detect_high_purine_lunch_overload():
    """Detects combination of beef, ribs, and salmon with high protein as high purine."""
    dishes = [
        "Cơm trắng",
        "Rau cải luộc chấm trứng",
        "Đỗ xào thịt bò",
        "Sườn xào chua ngọt",
        "Cá hồi áp chảo",
        "Canh rau"
    ]
    res = detect_high_purine_lunch(dishes, protein_g=62.0, uric_acid_level=442.0)

    assert res["is_high_purine"] is True
    assert len(res["detected_sources"]) >= 3
    assert any("bò" in s for s in res["detected_sources"])
    assert any("sườn" in s for s in res["detected_sources"])
    assert any("cá hồi" in s for s in res["detected_sources"])
    assert "Fujiwa" in res["counter_measure_protocol"]
    assert "1.5L - 2.0L" in res["counter_measure_protocol"]
    assert "TUYỆT ĐỐI CẤM thịt đỏ" in res["counter_measure_protocol"]


def test_detect_high_purine_lunch_clean():
    """Clean lunch with lean chicken breast and tofu is not flagged as high purine."""
    dishes = ["Cơm trắng", "Ức gà luộc", "Đậu phụ non sốt cà", "Canh bí đao"]
    res = detect_high_purine_lunch(dishes, protein_g=32.0, uric_acid_level=442.0)
    assert res["is_high_purine"] is False


def test_calculate_midday_nutrition_plan_unconsumed_carb():
    """Unconsumed daytime carb is calculated and marked as unconsumed rather than dumped into dinner."""
    dt = {"protein": 93.4, "carb": 344.8, "fat": 48.3, "calories": 2187.5}
    li = {"protein": 81.0, "carb": 136.0, "fat": 48.5, "calories": 1280.0}
    logs = [
        {"meal_type": "Bữa sáng", "timestamp": "08:52", "dishes": ["Bánh mì trứng"], "protein_g": 19.0, "carb_g": 61.0, "fat_g": 14.5},
        {"meal_type": "Bữa trưa", "timestamp": "12:20", "dishes": ["Thịt bò", "Sườn xào", "Cá hồi"], "protein_g": 62.0, "carb_g": 75.0, "fat_g": 34.0}
    ]

    plan = calculate_midday_nutrition_plan(dt, li, nut_logs=logs, uric_acid_level=442.0)

    assert plan["dinner_protein_target"] == 12.4
    assert plan["dinner_carb_target"] == 70.0
    assert plan["dinner_natural_fat"] >= 5.0
    assert plan["fat_status"] == "EXCEEDED"
    assert plan["unconsumed_carb"] > 90.0  # ~93.8g unconsumed
    assert plan["purine_evaluation"]["is_high_purine"] is True


def test_strip_stale_midday_footer():
    """Removes the contradictory morning framework footer from midday reports."""
    raw_text = (
        "### 🍱 3. Đối soát Dinh dưỡng & Quota Macro Cho Chiều/Tối:\n"
        "Total calo ~900 kcal.\n"
        "💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."
    )
    cleaned = strip_stale_midday_footer(raw_text)
    assert "Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng" not in cleaned
    assert "Thẻ Nhịp Trưa" not in cleaned


def test_prompt_engine_midday_clinical_guards():
    """Prompt engine for midday includes anti-carb-dumping, realistic fat floor, and no stale footer."""
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_system_prompt

    sys_prompt = get_system_prompt("midday", "Chủ Nhật, 25/10/2026", "65.6")
    assert "Khóa Trần Carb Bữa tối & Chống Carb-Dumping" in sys_prompt
    assert "Sàn Chất béo Tự nhiên & Chống Ảo giác Zero-Fat" in sys_prompt
    assert "Cảnh báo Tải Purine Bữa trưa" in sys_prompt
    assert "LOẠI BỎ FOOTER CŨ" in sys_prompt

    baseline_data = {
        "report_type": "midday",
        "target_date": "2026-10-25",
        "target_metrics": {
            "weight_kg": 65.6,
            "training_readiness_score": 79,
            "sleep_score": 80,
            "active_calories": 420.0
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-25", "end": "2026-10-24"}
    }
    user_prompt = build_advanced_user_prompt(baseline_data)
    assert "CHỐNG HỘI CHỨNG CARB-DUMPING" in user_prompt or "Trần Carb bữa tối" in user_prompt
    assert "Realistic Fat Floor" in user_prompt or "Sàn chất béo tự nhiên" in user_prompt
    assert "BỎ HOÀN TOÀN FOOTER CŨ" in user_prompt
