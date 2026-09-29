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
    assert "Còn lại:" in res
    assert "cần phân bổ cho các bữa tiếp theo" in res


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

