import pytest
from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT
from src.analytics.acwr import calculate_acwr


def test_exercise_guardrail_low_readiness_or_gct_imbalance():
    baseline_data = {
        "target_date": "2026-09-28",
        "target_metrics": {
            "weight_kg": 65.6,
            "training_readiness_score": 34,
            "gct_balance": "51.7% Left",
            "sleep_score": 75
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-28", "end": "2026-09-27"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "PROHIBIT" in prompt or "NGHIÊM CẤM" in prompt or "CẢNH BÁO NGUY CƠ CAO" in prompt
    assert "Zone 2" in prompt


def test_acwr_under_0_3_stale_legs_warning(tmp_path):
    from src.db.connection import get_db_connection
    db_file = tmp_path / "test_acwr.db"

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE daily_metrics (date TEXT PRIMARY KEY, training_load_7d REAL, active_calories REAL, activities_summary TEXT)")
        # Insert 28 days where acute 7d is low (10.0 per day) and chronic 28d is high (50.0 per day)
        for i in range(28):
            d_str = f"2026-09-{i+1:02d}"
            load_val = 10.0 if i >= 21 else 100.0
            cursor.execute("INSERT INTO daily_metrics (date, active_calories) VALUES (?, ?)", (d_str, load_val))
        conn.commit()

    res = calculate_acwr("2026-09-28", db_path=db_file)
    assert res["acwr"] < 0.3
    assert res["status"] == "ACUTE_LOAD_VERY_LOW"
    assert "ì cơ" in res["zone_desc"] or "stale legs" in res["zone_desc"]


def test_system_prompt_clinical_guardrails():
    assert "2.5 - 3.0 tiếng" in SYSTEM_PROMPT
    assert "ACWR < 0.3" in SYSTEM_PROMPT
    assert "Acute load is very low" in SYSTEM_PROMPT or "Tải cấp tính rất thấp" in SYSTEM_PROMPT
    assert "1.5 - 1.6" in SYSTEM_PROMPT


def test_gct_imbalance_strips_strides_from_workout():
    baseline_data = {
        "target_date": "2026-09-29",
        "target_metrics": {
            "weight_kg": 65.59,
            "training_readiness_score": 75,  # High readiness but imbalanced GCT
            "gct_balance": "51.66% Left",
            "sleep_score": 80
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-29", "end": "2026-09-28"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "BIOMECHANICS & READINESS OVERRIDE" in prompt
    assert "51.0%" in prompt or "51.66%" in prompt or "CẤM TUYỆT ĐỐI STRIDES" in prompt
    assert "KHÔNG BỨT TỐC / KHÔNG STRIDES / KHÔNG TĂNG TỐC 85%" in prompt


def test_telegram_bot_remaining_quota_uses_dynamic_targets():
    from src.delivery.telegram_bot import calculate_live_progress
    from src.services.nutrition_calculator import calculate_daily_macro_targets
    
    # Target for 65.6kg Rest day: ~1840.8 kcal, 101.7g Protein
    dyn_targets = calculate_daily_macro_targets(weight_kg=65.6, day_type="rest")
    
    res = calculate_live_progress(date_str="2026-09-29")
    assert "2150" not in res
    assert "124.6" not in res
    assert "📊 TIẾN ĐỘ HÔM NAY (ĐÃ NẠP / MỤC TIÊU):" in res
    assert "Năng lượng:" in res
    assert "Protein:" in res
    assert "Carb:" in res
    assert "Fat:" in res


def test_rau_ngot_pork_macro_integrity():
    from src.services.nutrition_calculator import verify_macro_integrity
    is_valid, realistic_p, msg = verify_macro_integrity("Canh rau ngót nấu 30g thịt nạc", 11.2)
    assert not is_valid
    assert abs(realistic_p - 7.8) < 0.2
    assert "inflated" in msg


def test_rest_day_protein_cap_validation():
    from src.services.nutrition_calculator import validate_menu_protein_cap
    # 116.4g protein on a Rest day for 65.6kg athlete (cap ~104.7 - 105.0g)
    valid, msg = validate_menu_protein_cap(116.4, weight_kg=65.6, day_type="rest")
    assert not valid
    assert "CẢNH BÁO VƯỢT TRẦN PROTEIN" in msg


def test_midday_report_detects_morning_activity(tmp_path):
    import json
    from src.db.connection import get_db_connection
    from src.analytics.pipeline import detect_today_morning_activity
    from src.analytics.prompt_engine import build_advanced_user_prompt
    from src.analytics.llm_analyst import generate_health_analysis

    db_file = tmp_path / "test_midday.db"
    date_str = "2026-09-29"

    act_json = json.dumps([
        {
            "name": "Morning Run",
            "type": "running",
            "duration_seconds": 1800,
            "distance_meters": 5000,
            "calories": 320,
            "avg_hr": 134,
            "avg_cadence": 178,
            "gct_balance": "50.8% Left"
        }
    ])

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE daily_metrics (date TEXT PRIMARY KEY, sleep_score INTEGER, activities_summary TEXT, active_calories REAL)")
        cursor.execute("INSERT INTO daily_metrics (date, sleep_score, activities_summary, active_calories) VALUES (?, ?, ?, ?)", (date_str, 80, act_json, 320.0))
        conn.commit()

    detected = detect_today_morning_activity(date_str, db_path=db_file)
    assert detected["morning_workout_done"] is True
    assert detected["active_calories"] == 320.0

    baseline_data = {
        "report_type": "midday",
        "target_date": date_str,
        "target_metrics": {
            "weight_kg": 65.6,
            "activities_summary": act_json,
            "active_calories": 320.0,
            "sleep_score": 80
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-29", "end": "2026-09-28"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "Đánh giá Buổi tập Sáng nay & Kế hoạch Phục hồi Chiều" in prompt
    assert "TUYỆT ĐỐI KHÔNG kê đơn bất kỳ bài chạy bộ nào mới cho buổi chiều" in prompt

    from unittest.mock import patch
    with patch('src.analytics.llm_analyst.call_gemini', return_value={'report_markdown': 'Đánh giá Buổi tập Sáng nay: phục hồi kéo giãn thả lỏng chiều', 'model_used': 'mock', 'prompt_tokens': 0, 'completion_tokens': 0}):
        res = generate_health_analysis(baseline_data, dry_run=False)
    assert "Đánh giá Buổi tập Sáng nay" in res["report_markdown"]
    assert any(kw in res["report_markdown"].lower() for kw in ["nghiêm cấm", "stretching", "thả lỏng", "phục hồi", "chiều"])


def test_dish_macro_atwater_integrity():
    from src.services.nutrition_calculator import verify_dish_atwater_integrity

    # Hallucinated 44.2g Carb in 40 kcal for 1/2 orange 100g -> Impossible math (44.2*4 = 176.8 kcal != 40 kcal)
    valid, msg = verify_dish_atwater_integrity("1/2 quả cam tươi (100g)", item_p=0.9, item_c=44.2, item_f=0.1, item_cal=40.0)
    assert not valid
    assert "Lỗi Carbohydrate cam tươi" in msg or "Atwater" in msg

    # Correct verified 100g fresh orange (9.5g Carb, 0.9g Protein, 0.1g Fat, 47 kcal)
    valid_correct, msg_ok = verify_dish_atwater_integrity("1/2 quả cam tươi (100g)", item_p=0.9, item_c=9.5, item_f=0.1, item_cal=47.0)
    assert valid_correct


def test_dinner_protein_cap_rest_day():
    from src.services.nutrition_calculator import validate_dinner_protein_cap

    # 44.2g protein forced into dinner on Rest day
    valid, msg = validate_dinner_protein_cap(44.2, day_type="rest")
    assert not valid
    assert "CẢNH BÁO GIỚI HẠN PROTEIN BỮA TỐI" in msg

    # Safe 24.0g protein dinner
    valid_safe, msg_safe = validate_dinner_protein_cap(24.0, day_type="rest")
    assert valid_safe


def test_carbo_loading_tapering_macro_targets():
    from src.services.nutrition_calculator import calculate_daily_macro_targets

    # Test T-3 / T-2 Carbo-loading target (weight 65.6kg) -> 5.0 - 5.5 g/kg Carb (~330 - 360g), calories 1,950 - 2,150 kcal
    t3_targets = calculate_daily_macro_targets(weight_kg=65.6, day_type="carbo_loading", days_to_race=3)
    assert 320.0 <= t3_targets["carb_g"] <= 365.0
    assert 1950.0 <= t3_targets["target_calories"] <= 2150.0

    # Test T-1 Carbo-loading target (weight 65.6kg) -> ~320 - 340g Carb, calories ~1,950 - 2,050 kcal
    t1_targets = calculate_daily_macro_targets(weight_kg=65.6, day_type="carbo_loading", days_to_race=1)
    assert 320.0 <= t1_targets["carb_g"] <= 340.0
    assert 1950.0 <= t1_targets["target_calories"] <= 2050.0


def test_rule_3_biomechanics_t1_t2_race(tmp_path, monkeypatch):
    import json
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_next_upcoming_race as real_get_next_race

    race_file = tmp_path / "races.json"
    with open(race_file, "w", encoding="utf-8") as f:
        json.dump([{
            "name": "Hanoi Full Marathon",
            "date": "2026-10-04",
            "distance": "42.195km",
            "priority": "A"
        }], f)

    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date, *args, **kwargs: real_get_next_race(date, config_path=race_file))

    baseline_data = {
        "target_date": "2026-10-03", # T-1
        "target_metrics": {
            "weight_kg": 64.9,
            "training_readiness_score": 85,
            "gct_balance": "51.7% Left",
            "sleep_score": 80
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-03", "end": "2026-10-02"}
    }

    prompt = build_advanced_user_prompt(baseline_data)

    # 1. Shakeout Run 15-20 min Zone 1/2 HR < 135 bpm
    assert "Shakeout Run" in prompt
    assert "15-20 phút Zone 1/2" in prompt or "HR < 135 bpm" in prompt

    # 2. Cadence 178-182 spm prohibited, natural short stride required
    assert "Chạy sải bước ngắn tự nhiên, lướt sát đất" in prompt
    assert "TUYỆT ĐỐI KHÔNG" in prompt

    # 3. Passive heel drop Eccentric Heel Drops mandatory off-track for left Achilles
    assert "Eccentric Heel Drops" in prompt
    assert "3 set x 10-12 lần mép bậc thang" in prompt


def test_uric_acid_t1_race_menu_constraints(tmp_path, monkeypatch):
    import json
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_next_upcoming_race as real_get_next_race, SYSTEM_PROMPT

    race_file = tmp_path / "races.json"
    with open(race_file, "w", encoding="utf-8") as f:
        json.dump([{
            "name": "Hanoi Full Marathon",
            "date": "2026-10-04",
            "distance": "42.195km",
            "priority": "A"
        }], f)

    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date, *args, **kwargs: real_get_next_race(date, config_path=race_file))

    baseline_data = {
        "target_date": "2026-10-03", # T-1
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 85
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-03", "end": "2026-10-02"}
    }

    prompt = build_advanced_user_prompt(baseline_data)

    # 1. No beef / Phở bò
    assert "Phở bò" in prompt or "thịt bò" in prompt
    assert "TUYỆT ĐỐI KHÔNG gợi ý 'Phở bò'" in prompt or "TUYỆT ĐỐI KHÔNG gợi ý \"Phở bò\"" in prompt or "Phở bò" in SYSTEM_PROMPT

    # 2. T-1 Breakfast menu: Phở gà nước trong / Bánh mì gối trắng quết mật ong / Xôi trắng ruốc nạc
    assert "Phở gà nước trong" in prompt
    assert "Bánh mì gối trắng quết mật ong" in prompt
    assert "Xôi trắng ruốc nạc" in prompt

    # 3. T-1 Dinner menu: Cơm trắng (1.5 - 2 bát) + ức gà luộc/tôm hấp, NO Cháo loãng
    assert "Cơm trắng (1.5 - 2 bát)" in prompt
    assert "Cháo loãng" in prompt  # Mentioned in prompt as prohibited: "KHÔNG gợi ý 'Cháo loãng'"


def test_offline_fallback_t1_race_report(tmp_path, monkeypatch):
    import json
    from src.analytics.baseline import calculate_baseline
    from src.analytics.llm_analyst import generate_health_analysis

    db_file = tmp_path / "garmin_health.db"
    from src.db.connection import init_db
    init_db(db_file)

    race_file = tmp_path / "races.json"
    with open(race_file, "w", encoding="utf-8") as f:
        json.dump([{
            "name": "Hanoi Full Marathon",
            "date": "2026-10-04",
            "distance": "42.195km",
            "priority": "A"
        }], f)

    from src.analytics.prompt_engine import get_next_upcoming_race as real_get_next_race
    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date, *args, **kwargs: real_get_next_race(date, config_path=race_file))

    baseline_data = calculate_baseline("2026-10-03", days=30, db_path=db_file)
    baseline_data["db_path"] = db_file
    res = generate_health_analysis(baseline_data, mock=True)

    report = res["report_markdown"]
    assert "Shakeout Run" in report
    assert "Zone 1/2" in report
    assert "Eccentric Heel Drops" in report
    assert "Phở gà nước trong" in report
    assert "Cơm trắng" in report
    assert "Cháo loãng làm tụt đường huyết" not in report


def test_alcohol_and_rem_drop_detection_in_prompt():
    """Verify REM collapse detection, alcohol attribution and prohibition of naive empty stomach claims."""
    from src.analytics.prompt_engine import build_advanced_user_prompt

    # Case 1: REM is 0 mins (0%) with NO alcohol logged
    data_no_alc = {
        "target_date": "2026-10-12",
        "target_metrics": {
            "weight_kg": 65.2,
            "sleep_duration_seconds": 19920,
            "rem_sleep_seconds": 0,
            "deep_sleep_seconds": 3900,
            "light_sleep_seconds": 16020,
            "awake_duration_seconds": 3180,
            "resting_heart_rate": 61,
            "hrv_last_night": 31.0,
            "sleep_stress": 43
        },
        "metrics_baseline": {
            "rem_sleep_seconds": {"avg": 4500},
            "sleep_duration_seconds": {"avg": 25200}
        },
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-12", "end": "2026-10-11"}
    }

    prompt_no_alc = build_advanced_user_prompt(data_no_alc)
    assert "HỘI CHỨNG MẤT PHA REM" in prompt_no_alc
    assert "ACUTE REM SLEEP COLLAPSE" in prompt_no_alc or "ALCOHOL SUPPRESSION SYNDROME" in prompt_no_alc
    assert "TUYỆT ĐỐI NGHIÊM CẤM kết luận rằng dạ dày rỗng lý tưởng" in prompt_no_alc
    assert "Kiệt quệ hệ thần kinh trung ương cấp tính" in prompt_no_alc or "Acute CNS Exhaustion" in prompt_no_alc

    # Case 2: REM is 0 mins with Alcohol logged in yesterday's nutrition
    data_with_alc = dict(data_no_alc)
    # We test with nutrition log returning alcohol
    import src.db.nutrition_repository as nr
    original_get_nut = nr.get_nutrition_logs_by_date
    try:
        nr.get_nutrition_logs_by_date = lambda d: [{
            "meal_type": "Bữa tối",
            "timestamp": "2026-10-11 20:00:00",
            "dishes": ["Bia tươi", "Mực nướng"],
            "total_calories": 400,
            "alcohol_units": 2.5
        }] if d == "2026-10-11" else []
        prompt_with_alc = build_advanced_user_prompt(data_with_alc)
        assert "XÁC NHẬN CỒN HÔM QUA" in prompt_with_alc or "XÁC NHẬN NGUYÊN NHÂN TỪ CỒN" in prompt_with_alc
        assert "2.5" in prompt_with_alc
    finally:
        nr.get_nutrition_logs_by_date = original_get_nut


def test_system_prompt_sleep_table_and_rem_drop_rules():
    """Verify system prompt contains unindented Markdown table format and REM drop clinical instructions."""
    from src.analytics.prompt_engine import get_system_prompt

    prompt = get_system_prompt("morning", "Thứ Hai, 12/10/2026", "65.2")
    assert "| Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |" in prompt
    assert "Bảng Markdown PHẢI viết sát lề trái" in prompt
    assert "Hội chứng Cồn & Mất pha REM" in prompt or "Hội chứng Cồn" in prompt
    assert "TUYỆT ĐỐI NGHIÊM CẤM kết luận rằng dạ dày rỗng lý tưởng" in prompt or "TUYỆT ĐỐI KHÔNG kết luận ngây thơ" in prompt


def test_midday_protein_dinner_and_snack_consistency():
    """Verify midday dinner protein matches din_p_cap exactly (max 28g) and snack receives the rest."""
    import src.db.nutrition_repository as nr
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_system_prompt

    data = {
        "target_date": "2026-10-12",
        "report_type": "midday",
        "target_metrics": {
            "weight_kg": 65.2,
            "training_readiness_score": 26,
            "recovery_time_hours": 15,
            "total_steps": 2500,
            "active_calories": 150
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-12", "end": "2026-10-11"},
        "acwr": {
            "acute_load": 400.0,
            "chronic_load": 800.0,
            "acwr": 0.48,
            "status": "POST_RACE_RECOVERY",
            "zone_desc": "Phục hồi hậu marathon"
        }
    }

    orig_logs = nr.get_nutrition_logs_by_date
    try:
        # Mock 2 meals totaling 57.5g protein (target is 94.5g -> remaining is 37.0g)
        nr.get_nutrition_logs_by_date = lambda d: [
            {"meal_type": "Bữa sáng", "timestamp": "08:15", "dishes": ["Bánh mì Phúc Long"], "total_calories": 470, "protein_g": 17.5, "carb_g": 62.0, "fat_g": 16.0},
            {"meal_type": "Bữa trưa", "timestamp": "11:33", "dishes": ["Cơm trắng", "Thịt bò gân", "Canh bầu"], "total_calories": 530, "protein_g": 40.0, "carb_g": 53.0, "fat_g": 14.0}
        ] if d == "2026-10-12" else []

        prompt = build_advanced_user_prompt(data)
        assert "28.0g" in prompt
        assert "9.0g" in prompt
        assert "9.0g + 28.0g = 37.0g" in prompt
        assert "TUYỆT ĐỐI KHÔNG ĐƯỢC VIẾT là 31.0g" in prompt

        sys_prompt = get_system_prompt("midday", "Thứ Hai, 12/10/2026", "65.2")
        assert "TUYỆT ĐỐI KHÔNG để số protein ở dòng thực đơn bữa tối vượt quá 28.0g" in sys_prompt
        assert "Bữa phụ chiều nhận đúng số Protein dư còn lại" in sys_prompt
    finally:
        nr.get_nutrition_logs_by_date = orig_logs


def test_post_race_acwr_tapering_keywords_prohibited():
    """Verify that during POST_RACE_RECOVERY / POST_RACE_ACUTE, ACWR never displays TAPERING keywords."""
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_system_prompt

    data = {
        "target_date": "2026-10-12",
        "report_type": "midday",
        "target_metrics": {
            "weight_kg": 65.2,
            "training_readiness_score": 26,
            "hrv_status": "BALANCED",
            "total_steps": 2500,
            "active_calories": 150
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-12", "end": "2026-10-11"},
        "acwr": {
            "acute_load": 350.0,
            "chronic_load": 750.0,
            "acwr": 0.48,
            "status": "TAPERING_DEEP_RECOVERY",  # simulate dirty cached status
            "zone_desc": "Tapering"
        }
    }

    prompt = build_advanced_user_prompt(data)
    assert "POST_RACE_RECOVERY" in prompt
    assert "Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY" in prompt
    assert "Siêu bù (Supercompensation) cho giải Hanoi Full Marathon" not in prompt

    sys_prompt = get_system_prompt("midday", "Thứ Hai, 12/10/2026", "65.2")
    assert "nhãn dải tải là POST_RACE_RECOVERY hoặc ACUTE_REST_RECOVERY" in sys_prompt
    assert "Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY" in sys_prompt


def test_low_readiness_achilles_heel_drop_prohibited():
    """Verify that when training_readiness < 30, Eccentric Heel Drops is strictly forbidden."""
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_system_prompt

    data = {
        "target_date": "2026-10-12",
        "report_type": "midday",
        "target_metrics": {
            "weight_kg": 65.2,
            "training_readiness_score": 26,  # < 30
            "gct_balance": "51.8% Left / 48.2% Right",
            "total_steps": 2500,
            "active_calories": 150
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-12", "end": "2026-10-11"}
    }

    prompt = build_advanced_user_prompt(data)
    assert "KHÓA AN TOÀN GÂN ACHILLES KHI READINESS THẤP (< 30/100" in prompt or "READINESS < 30" in prompt
    assert "TUYỆT ĐỐI CẤM kê đơn bài tập 'Eccentric Heel Drops'" in prompt
    assert "Isometric Holds" in prompt
    assert "mặt phẳng" in prompt

    sys_prompt = get_system_prompt("midday", "Thứ Hai, 12/10/2026", "65.2")
    assert "Nếu Training Readiness < 30" in sys_prompt
    assert "TUYỆT ĐỐI CẤM kê đơn bài tập \"Eccentric Heel Drops\"" in sys_prompt


def test_sleep_under_5h_locks_out_running():
    """Assert that when sleep_duration_seconds < 18000 (5 hours), Choice 1 running/shakeout run
    is completely removed, regardless of Readiness >= 65.
    """
    from src.analytics.prompt_engine import (
        build_advanced_user_prompt,
        generate_executive_brief,
        generate_telegram_card_fallback
    )
    from src.analytics.periodization import is_post_race_shakeout_eligible
    from src.analytics.llm_analyst import _generate_structured_report

    data = {
        "target_date": "2026-10-16",
        "report_type": "morning",
        "target_metrics": {
            "weight_kg": 65.09,
            "training_readiness_score": 66,  # High Readiness >= 65
            "recovery_time_hours": 1,         # Low recovery time <= 6h
            "hrv_status": "BALANCED",         # Balanced HRV
            "sleep_duration_seconds": 17880,  # 4h 58m (< 5 hours = 18000s)
            "sleep_score": 75,
            "deep_sleep_seconds": 6240,       # 104m
            "rem_sleep_seconds": 3540,
            "light_sleep_seconds": 8100,
            "awake_duration_seconds": 0,
            "body_battery_highest": 65,
            "body_battery_charged": 40
        },
        "metrics_baseline": {
            "deep_sleep_seconds": {"avg": 3288},
            "sleep_duration_seconds": {"avg": 24000},
            "hrv_last_night": {"avg": 40.0},
            "resting_heart_rate": {"avg": 60}
        },
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-16", "end": "2026-10-15"}
    }

    # 1. Periodization helper rejects shakeout run when sleep < 18000s
    assert not is_post_race_shakeout_eligible(66, 1, "BALANCED", sleep_duration_seconds=17880)

    # 2. Prompt engine removes running from Choice 1
    prompt = build_advanced_user_prompt(data)
    assert "CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG)" in prompt
    assert "NGHIÊM CẤM TUYỆT ĐỐI chạy bộ (kể cả shakeout run 2-3km) để bảo vệ gân Achilles trái" in prompt
    assert "HÔM NAY BẮT BUỘC: Nghỉ ngơi hoàn toàn (Rest Day) HOẶC bơi sải thả lỏng không trọng lực 500m Zone 1" in prompt
    
    # Choice 1 running/shakeout run must be completely removed
    assert "LỰA CHỌN 1 (Shakeout Run" not in prompt
    assert "Cho phép chạy thử thích ứng 2.0 km - 3.0 km" not in prompt

    # 3. Executive brief & Telegram card lockout
    brief = generate_executive_brief(data)
    assert "CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG)" in brief
    assert "CẤM CHẠY TUYỆT ĐỐI" in brief
    assert "Shakeout Run" not in brief

    card = generate_telegram_card_fallback(data)
    assert "CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG)" in card
    assert "CẤM CHẠY BỘ TUYỆT ĐỐI" in card
    assert "Shakeout Run" not in card

    # 4. Offline / structured report generator lockout & realistic sleep debt tone
    report = _generate_structured_report(data)
    assert "CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG)" in report["report_markdown"]
    assert "Deep Sleep Rebound do thiếu ngủ" in report["report_markdown"]
    assert "Siêu phục hồi xuất sắc" not in report["report_markdown"]


def test_oil_free_dinner_fat_upper_bound():
    """Assert that a boiled/oil-free dinner of tofu and chicken breast cannot report
    Fat > 10.0g without an explicit fat source.
    """
    from src.services.nutrition_calculator import verify_single_dish_integrity

    # Dish without explicit fat source and Fat > 10.0g MUST fail
    dish_inflated = "1 bát con cơm trắng mềm (~140g) + Đậu phụ non sốt cà chua nhạt (1 bìa, ~100g) + 70g ức gà áp chảo không dầu + Canh rau cải luộc nước trong"
    
    # 22.0g Fat as in the 2026-10-16 morning report
    valid, msg = verify_single_dish_integrity(
        dish_name=dish_inflated,
        item_p=28.0,
        item_c=59.3,
        item_f=22.0,
        item_cal=552.0
    )
    assert not valid
    assert "Lỗi thổi phồng chất béo (Fat Inflation)" in msg
    assert "vượt quá trần sinh học 10.0g Fat" in msg

    # Realistic fat <= 10.0g MUST pass
    valid_ok, _ = verify_single_dish_integrity(
        dish_name=dish_inflated,
        item_p=28.0,
        item_c=59.3,
        item_f=7.5,
        item_cal=416.7
    )
    assert valid_ok

    # Explicit fat source (e.g. olive oil) added to hit higher fat/calories MUST pass
    dish_with_olive_oil = "1 bát con cơm trắng mềm + Đậu phụ non sốt cà chua + 70g ức gà không dầu + Canh rau cải thêm 1 thìa cà phê 5ml dầu olive"
    valid_oil, _ = verify_single_dish_integrity(
        dish_name=dish_with_olive_oil,
        item_p=28.0,
        item_c=59.3,
        item_f=12.5,
        item_cal=461.7
    )
    assert valid_oil


def test_sleep_table_and_text_duration_match():
    """Verify that the parsed hours/minutes in the narrative match (deep + rem + light) from input JSON."""
    from src.analytics.prompt_engine import build_advanced_user_prompt, clean_report_text
    from src.analytics.llm_analyst import _generate_structured_report

    baseline_data = {
        "target_date": "2026-10-18",
        "target_metrics": {
            "weight_kg": 65.3,
            "sleep_score": 70,
            "sleep_duration_seconds": 24520,  # e.g. raw 6h 48m 40s (slight disconnect from rounded stages)
            "deep_sleep_seconds": 6300,      # 105m
            "rem_sleep_seconds": 1680,       # 28m
            "light_sleep_seconds": 16560,    # 276m
            "awake_duration_seconds": 780,   # 13m
            "resting_heart_rate": 58,
            "hrv_last_night": 40.0,
            "hrv_status": "BALANCED",
            "training_readiness_score": 66,
            "recovery_time_hours": 1
        },
        "metrics_baseline": {
            "deep_sleep_seconds": {"avg": 3294.0},
            "rem_sleep_seconds": {"avg": 4500.0},
            "light_sleep_seconds": {"avg": 14670.0},
            "awake_duration_seconds": {"avg": 978.0},
            "sleep_duration_seconds": {"avg": 24540.0}
        },
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-18", "end": "2026-10-17"}
    }

    # Deep 105m + REM 28m + Light 276m = 409m = 6h 49m (Awake 13m -> Bed Time = 422m = 7h 2m)
    expected_sleep_m = 105 + 28 + 276
    expected_h = expected_sleep_m // 60
    expected_m = expected_sleep_m % 60
    assert expected_h == 6
    assert expected_m == 49

    # 1. Verify prompt strictly derives 6h 49m and binds LLM deterministically
    prompt = build_advanced_user_prompt(baseline_data)
    assert "Tổng thời gian ngủ (Total Sleep Time) trong văn bản BẮT BUỘC phải bằng chính xác tổng số phút của (Deep Sleep + REM Sleep + Light Sleep)" in prompt
    assert "6 giờ 49 phút" in prompt or "6h 49m" in prompt

    # 2. Verify structured report generator uses exact derived duration
    rep = _generate_structured_report(baseline_data)
    rep_md = rep["report_markdown"]
    assert "6h 49m" in rep_md or "6 giờ 49 phút" in rep_md
    assert "6 giờ 48 phút" not in rep_md

    # 3. Verify clean_report_text corrects any 1-minute text drift to match table
    drifted_text = """### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
| Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |
| :--- | :--- | :--- | :--- | :--- |
| Deep Sleep | 105.0m (25.7%) | 54.9m (13.4%) | 15% - 25% | Tối ưu hóa phục hồi mô cơ sâu |
| REM Sleep | 28.0m (6.9%) | 75.0m (18.3%) | 20% - 25% | Sụt giảm REM do cấu trúc giấc ngủ phân đoạn |
| Light Sleep | 276.0m (67.6%) | 244.5m (59.7%) | 50% - 60% | Chiếm ưu thế duy trì trạng thái nghỉ ngơi |
| Awake | 13.0m (3.2%) | 16.3m (4.0%) | < 5% | Thức giấc trong giới hạn an toàn |

- **Đánh giá Siêu phục hồi (Supercompensation) & Tái tạo Chậm:**
  * Tổng thời gian ngủ đêm qua đạt 6 giờ 48 phút với điểm số giấc ngủ 70/100.
"""
    cleaned = clean_report_text(drifted_text)
    assert "6 giờ 49 phút" in cleaned
    assert "6 giờ 48 phút" not in cleaned


def test_menu_fat_transparency():
    """Verify that when target fat is ~49g, the menu doesn't rely on oil-free foods alone,
    but includes explicit clean fat cooking ingredients to close the gap within +-3g margin.
    """
    from src.analytics.prompt_engine import generate_lean_menu, build_advanced_user_prompt
    from src.analytics.llm_analyst import _generate_structured_report
    from src.services.nutrition_calculator import verify_single_dish_integrity

    target_fat = 49.0
    menu = generate_lean_menu(target_fat_g=target_fat, dinner_protein_cap=28.0)

    # 1. Must explicitly list healthy fat additions to food preparation
    assert any(term in menu["breakfast"].lower() for term in ["dầu thực vật", "dầu phi hành", "dầu ăn"])
    assert "+5g fat" in menu["breakfast"].lower() or "+8g fat" in menu["breakfast"].lower() or "dầu" in menu["breakfast"].lower()

    assert any(term in menu["lunch"].lower() for term in ["dầu mè", "dầu olive"])
    assert any(term in menu["dinner"].lower() for term in ["dầu mè", "dầu olive"])

    # 2. Sum(Dish Fat) matches Daily Target Fat within +-3g margin
    total_fat = menu["total_menu_fat"]
    assert abs(total_fat - target_fat) <= 3.0

    # 3. Test structured report generation for target fat ~49g
    baseline_data = {
        "target_date": "2026-10-18",
        "target_metrics": {
            "weight_kg": 65.3,
            "training_readiness_score": 66,
            "sleep_score": 70,
            "deep_sleep_seconds": 6300,
            "rem_sleep_seconds": 1680,
            "light_sleep_seconds": 16560,
            "awake_duration_seconds": 780
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-18", "end": "2026-10-17"}
    }
    report = _generate_structured_report(baseline_data)
    md = report["report_markdown"]

    # Must contain explicit clean fat additions in Section 4
    assert "dầu" in md.lower()
    assert "dầu mè" in md.lower() or "dầu olive" in md.lower() or "dầu phi hành" in md.lower()

    # Must contain Intraday Dynamic Notice at the end of Section 4
    notice = "💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."
    assert notice in md

    # 4. Prompt engine must contain explicit fat allocation instructions
    prompt = build_advanced_user_prompt(baseline_data)
    assert "PHÂN BỔ CHẤT BÉO SẠCH TƯỜNG MINH" in prompt
    assert "Dùng 1 thìa nhỏ dầu thực vật/dầu phi hành thơm nấu cháo" in prompt
    assert "Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc" in prompt
    assert notice in prompt

    # 5. Individual dishes with explicit fat must pass single dish integrity validation
    valid, _ = verify_single_dish_integrity(
        dish_name=menu["dinner"],
        item_p=25.0,
        item_c=40.0,
        item_f=menu["dish_fats"]["dinner"],
        item_cal=round(25.0 * 4 + 40.0 * 4 + menu["dish_fats"]["dinner"] * 9, 1)
    )
    assert valid


def test_telegram_remaining_protein_sync(monkeypatch):
    """Verify that with 14.6g protein consumed on 2026-10-18 (target 94.7g for 65.3kg athlete),
    remaining protein equals 94.7 - 14.6 = 80.1g (not 70.4g).
    """
    from src.db.nutrition_repository import get_remaining_nutrition_quota
    from src.services.nutrition_calculator import calculate_daily_macro_targets
    from src.delivery.telegram_bot import calculate_live_progress
    import src.db.nutrition_repository as repo
    import src.services.nutrition_service as nut_svc

    user_date = "2026-10-18"
    weight_kg = 65.3

    # Deterministically mock the 14.6g morning intake specified in test
    mock_summary = {"total_cal": 220, "total_protein": 14.6, "total_carbs": 5.0, "total_fat": 11.0, "alcohol_units": 0.0}
    monkeypatch.setattr(repo, "get_today_nutrition_summary", lambda *args, **kwargs: mock_summary)

    # 1. Single source of truth targets
    targets = calculate_daily_macro_targets(target_date=user_date, weight_kg=weight_kg)
    assert targets["target_calories"] == 1786.2
    assert targets["protein_g"] == 94.7
    assert targets["carb_g"] == 241.6
    assert targets["fat_g"] == 49.0

    # 2. Quota remaining check
    quota = get_remaining_nutrition_quota(user_date=user_date, weight_kg=weight_kg)
    logged_p = quota["logged"]["total_protein"]
    assert logged_p == 14.6
    assert quota["target"]["protein_g"] == 94.7
    assert quota["remaining_protein"] == 80.1

    # 3. Output string formatting
    progress_str = calculate_live_progress(date_str=user_date)
    assert "80.1g" in progress_str
    assert "70.4g" not in progress_str


def test_no_oatmeal_in_feedback():
    """Assert that generated meal feedback prompts and analysis outputs contain zero occurrences of 'yến mạch'
    and strictly prioritize traditional foods (khoai lang, chuối tiêu, cháo trắng, cơm trắng).
    """
    from src.analytics.vision_analyst import VISION_SYSTEM_PROMPT, _get_intraday_cumulative_context, sanitize_vision_analysis
    from src.delivery.telegram_bot import format_sleep_risk

    # 1. System prompt checks
    prompt_lower = VISION_SYSTEM_PROMPT.lower()
    assert "như khoai lang, yến mạch" not in prompt_lower
    assert "cơm, yến mạch" not in prompt_lower

    # 2. Cumulative context prompt checks
    ctx = _get_intraday_cumulative_context("2026-10-18")
    assert "cơm, yến mạch" not in ctx.lower()
    assert any(term in ctx for term in ["khoai lang hấp", "chuối tiêu", "cháo trắng", "cơm trắng"])

    # 3. Feedback sanitization purge
    mock_dirty_analysis = {
        "date": "2026-10-18",
        "timestamp": "2026-10-18 07:33:26",
        "meal_type": "Thức uống",
        "dishes": ["Nước hạt chia (300ml)"],
        "sleep_risk_assessment": "Bổ sung yến mạch, bánh mì nguyên cám và quinoa để nạp Carb.",
        "short_summary": "Đã ghi nhận nước hạt chia và yến mạch."
    }
    sanitized = sanitize_vision_analysis(mock_dirty_analysis, "2026-10-18", "2026-10-18 07:33:26")
    assert "yến mạch" not in sanitized["sleep_risk_assessment"].lower()
    assert "yến mạch" not in sanitized["short_summary"].lower()
    assert "bánh mì nguyên cám" not in sanitized["sleep_risk_assessment"].lower()
    assert "quinoa" not in sanitized["sleep_risk_assessment"].lower()

    # 4. Telegram bot risk format debouncing
    reply_risk = format_sleep_risk(mock_dirty_analysis)
    assert "yến mạch" not in reply_risk.lower()
    assert "bánh mì nguyên cám" not in reply_risk.lower()







