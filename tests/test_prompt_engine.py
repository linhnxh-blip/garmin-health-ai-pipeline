import json
import pytest
from pathlib import Path
from src.analytics.prompt_engine import get_next_upcoming_race, build_advanced_user_prompt

@pytest.fixture
def mock_race_config(tmp_path):
    race_file = tmp_path / "races.json"
    data = [
        {
            "name": "Hanoi Full Marathon",
            "date": "2026-10-04",
            "distance": "42.195km",
            "type": "running",
            "priority": "A"
        },
        {
            "name": "Da Nang Half Marathon",
            "date": "2026-11-15",
            "distance": "21.0975km",
            "type": "running",
            "priority": "B"
        }
    ]
    with open(race_file, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return race_file

def test_get_next_upcoming_race_valid(mock_race_config):
    race = get_next_upcoming_race("2026-09-19", config_path=mock_race_config)
    assert race is not None
    assert race["name"] == "Hanoi Full Marathon"
    assert race["days_to_race"] == 15
    assert race["priority"] == "A"

def test_get_next_upcoming_race_past_events(tmp_path):
    race_file = tmp_path / "past_races.json"
    data = [
        {
            "name": "Old Marathon 2025",
            "date": "2025-10-04",
            "distance": "42km",
            "priority": "A"
        }
    ]
    with open(race_file, "w", encoding="utf-8") as f:
        json.dump(data, f)

    race = get_next_upcoming_race("2026-09-19", config_path=race_file)
    assert race is None

def test_get_next_upcoming_race_missing_file(tmp_path):
    non_existent = tmp_path / "non_existent.json"
    race = get_next_upcoming_race("2026-09-19", config_path=non_existent)
    assert race is None

def test_get_next_upcoming_race_empty_file(tmp_path):
    empty_file = tmp_path / "empty.json"
    with open(empty_file, "w", encoding="utf-8") as f:
        f.write("[]")

    race = get_next_upcoming_race("2026-09-19", config_path=empty_file)
    assert race is None

def test_carbo_loading_activation_in_prompt(mock_race_config, monkeypatch):
    from src.analytics.prompt_engine import generate_executive_brief
    # Target date 2026-10-02 (2 days before Hanoi Full Marathon 2026-10-04)
    baseline_data = {
        "target_date": "2026-10-02",
        "target_metrics": {"weight_kg": 64.9, "sleep_score": 85, "hrv_last_night": 45, "resting_heart_rate": 58},
        "metrics_baseline": {"sleep_score": {"avg": 80}, "hrv_last_night": {"avg": 42}, "resting_heart_rate": {"avg": 60}},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-02", "end": "2026-10-01"}
    }
    
    # Patch get_next_upcoming_race to use mock_race_config
    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date: get_next_upcoming_race(date, config_path=mock_race_config))

    prompt = build_advanced_user_prompt(baseline_data)
    assert "CARBO-LOADING" in prompt
    assert "70% tổng năng lượng" in prompt

    baseline_data["race_info"] = get_next_upcoming_race("2026-10-02", config_path=mock_race_config)
    brief = generate_executive_brief(baseline_data)
    assert "CARBO-LOADING" in brief
    assert "70% Carbs" in brief

def test_nocturnal_hypoglycemia_warning(monkeypatch):
    from src.analytics.prompt_engine import build_advanced_user_prompt
    baseline_data = {
        "target_date": "2026-09-25",
        "target_metrics": {"weight_kg": 64.9, "sleep_score": 75, "sleep_duration_seconds": 25200, "hrv_last_night": 45},
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-25", "end": "2026-09-24"}
    }
    
    # Mock nutrition log with deficit < 1600 kcal
    mock_log = [{
        "meal_type": "Bữa tối",
        "timestamp": "2026-09-24 13:00:00",
        "total_calories": 1200,
        "protein_g": 80,
        "carb_g": 100,
        "fat_g": 30
    }]
    monkeypatch.setattr("src.db.nutrition_repository.get_nutrition_logs_by_date", lambda d: mock_log if d == "2026-09-24" else [])

    prompt = build_advanced_user_prompt(baseline_data)
    assert "Nocturnal Hypoglycemia" in prompt
    assert "Hạ đường huyết ban đêm" in prompt

def test_cadence_sweet_spot_and_single_leg_doubling():
    from src.analytics.prompt_engine import build_advanced_user_prompt
    activities_json = json.dumps([{
        "name": "Walking / Single Leg Run",
        "type": "running",
        "duration_seconds": 1800,
        "distance_meters": 3000,
        "avg_cadence": 89,
        "gct_balance": 51.7
    }])
    baseline_data = {
        "target_date": "2026-09-25",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 80,
            "sleep_duration_seconds": 25200,
            "activities_summary": activities_json
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-25", "end": "2026-09-24"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "SPM chuẩn x2 = 178 spm" in prompt
    assert "178 - 182 spm" in prompt
    assert "50.3% L" in prompt

def test_emergency_recovery_protocol_trigger():
    from src.analytics.prompt_engine import build_advanced_user_prompt, generate_executive_brief
    baseline_data = {
        "target_date": "2026-09-25",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 45,
            "sleep_duration_seconds": 14400,  # 4 hours < 5 hours
            "body_battery_highest": 25,        # < 30
            "hrv_last_night": 30
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-25", "end": "2026-09-24"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "EMERGENCY RECOVERY PROTOCOL" in prompt
    assert "Power Nap 20 phút" in prompt
    assert "12:00 trưa" in prompt
    assert "Tryptophan" in prompt

    brief = generate_executive_brief(baseline_data)
    assert "EMERGENCY RECOVERY PROTOCOL" in brief

def test_clean_report_text_removes_chinese_tokens():
    from src.analytics.prompt_engine import clean_report_text, SYSTEM_PROMPT
    dirty_text = "指数 HRV đêm qua đạt 44 ms, trạng thái 恢复 tốt và 睡眠 đầy đủ."
    cleaned = clean_report_text(dirty_text)
    assert "Chỉ số HRV" in cleaned
    assert "Phục hồi" in cleaned
    assert "Giấc ngủ" in cleaned
    assert "指数" not in cleaned
    assert "恢复" not in cleaned
    assert "睡眠" not in cleaned

    assert "tiếng Việt y khoa chuẩn mực" in SYSTEM_PROMPT
    assert "tiếng Trung" in SYSTEM_PROMPT

def test_sleep_norms_benchmark_table_prompt_data():
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT
    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 85,
            "sleep_duration_seconds": 25200,  # 420m (7h)
            "deep_sleep_seconds": 5040,      # 84m (20%)
            "rem_sleep_seconds": 5670,       # 94.5m (22.5%)
            "light_sleep_seconds": 13230,    # 220.5m (52.5%)
            "awake_duration_seconds": 1260   # 21m (5%)
        },
        "metrics_baseline": {},
        "metrics_baseline_180d": {
            "sleep_duration_seconds": {"avg": 24000},
            "deep_sleep_seconds": {"avg": 4800},
            "rem_sleep_seconds": {"avg": 5400},
            "light_sleep_seconds": {"avg": 12600},
            "awake_duration_seconds": {"avg": 1200}
        },
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "SLEEP NORMS BENCHMARK FOR SECTION 2" in prompt
    assert "Deep Sleep Đêm qua: 84.0 phút (20.0%)" in prompt
    assert "Siêu phục hồi" in prompt
    assert "SLEEP NORMS BENCHMARK" in SYSTEM_PROMPT

def test_cross_training_options_and_high_readiness():
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT
    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 88,
            "sleep_duration_seconds": 27000,
            "training_readiness_score": 82
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "LỰA CHỌN 1 (Chạy bộ - Neuromuscular Priming)" in prompt
    assert "LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực)" in prompt
    assert "KHÔNG khuyến nghị Sprint 100% all-out" in prompt
    assert "CROSS-TRAINING & ADAPTIVE WORKOUT" in SYSTEM_PROMPT

def test_real_time_dynamic_nutrition_time():
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT
    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {"weight_kg": 64.9, "sleep_score": 80, "sleep_duration_seconds": 25200},
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "MỐC THỜI GIAN THỰC TẾ HÔM NAY KHI LẬP BÁO CÁO:" in prompt
    assert "QUY TẮC BẮT BUỘC ĐỘNG HÓA THỜI GIAN CHO MỤC 4" in prompt
    assert "ĐỘNG HÓA THỜI GIAN THEO THỰC TẾ TRONG THỰC ĐƠN" in SYSTEM_PROMPT

def test_180d_sleep_baseline_sql_and_prompt_formatting(tmp_path):
    from src.analytics.baseline import get_180d_sleep_baseline, calculate_baseline
    from src.analytics.prompt_engine import build_advanced_user_prompt
    from src.db.connection import get_db_connection, init_db

    db_file = tmp_path / "test_garmin.db"
    init_db(db_file)

    # Populate sample records in daily_metrics for baseline
    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        for i in range(1, 10):
            d_str = f"2026-09-{i:02d}"
            cursor.execute(
                """
                INSERT OR REPLACE INTO daily_metrics 
                (date, sleep_score, sleep_duration_seconds, deep_sleep_seconds, rem_sleep_seconds, light_sleep_seconds, awake_duration_seconds)
                VALUES (?, 80, 25200, 5040, 5670, 13230, 1260)
                """,
                (d_str,)
            )
        conn.commit()

    res_sql = get_180d_sleep_baseline("2026-09-10", db_path=db_file)
    assert res_sql["sleep_duration_seconds"] == 25200.0
    assert res_sql["deep_sleep_seconds"] == 5040.0
    assert res_sql["rem_sleep_seconds"] == 5670.0
    assert res_sql["light_sleep_seconds"] == 13230.0
    assert res_sql["awake_duration_seconds"] == 1260.0

    b_data = calculate_baseline("2026-09-10", days=30, db_path=db_file)
    prompt = build_advanced_user_prompt(b_data)
    assert "N/A" not in prompt.split("SLEEP NORMS BENCHMARK FOR SECTION 2")[1].split("⚠️ YÊU CẦU")[0]
    assert "Baseline 180d: 84.0m (20.0%)" in prompt

def test_multi_dimensional_spo2_analysis_rules():
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT
    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 80,
            "sleep_duration_seconds": 25200,
            "spo2_avg": 94.0,
            "spo2_min": 78.0,
            "respiration_avg": 14.5,
            "respiration_min": 12.0,
            "respiration_max": 18.0,
            "awake_duration_seconds": 1200
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "SPO2 TỤT THẤP (< 85%, THỰC TẾ = 78.0%" in prompt
    assert "TUYỆT ĐỐI KHÔNG khẳng định cứng nhắc" in prompt
    assert "Yếu tố Thiết bị & Vị trí đeo" in prompt
    assert "Yếu tố Tư thế & Môi trường hô hấp" in prompt
    assert "Multi-dimensional SpO2 Analysis" in SYSTEM_PROMPT

def test_taper_madness_and_weather_adaptation_rules(mock_race_config, monkeypatch):
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT, get_next_upcoming_race
    # Target date 2026-10-02 (2 days before 2026-10-04, days_to_race <= 3)
    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date: get_next_upcoming_race(date, config_path=mock_race_config))

    baseline_data = {
        "target_date": "2026-10-02",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 90,
            "sleep_duration_seconds": 28800,
            "body_battery_highest": 95,
            "training_readiness_score": 85
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-02", "end": "2026-10-01"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "Bứt rứt Tapering (Taper Madness)" in prompt
    assert "Chuẩn bị thích nghi thời tiết sát ngày Race (Còn 2 ngày <= 3 ngày)" in prompt
    assert "Fujiwa" in prompt
    assert "MENTAL & RACE ADAPTATION" in SYSTEM_PROMPT

def test_race_weather_rule_when_far_from_race(mock_race_config, monkeypatch):
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT, get_next_upcoming_race
    # Target date 2026-09-26 (8 days before 2026-10-04, days_to_race > 3)
    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date: get_next_upcoming_race(date, config_path=mock_race_config))

    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {
            "weight_kg": 64.9,
            "sleep_score": 90,
            "sleep_duration_seconds": 28800,
            "body_battery_highest": 95,
            "training_readiness_score": 85
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "Quy tắc thời tiết xa ngày Race (Còn 8 ngày > 3 ngày)" in prompt
    assert "TUYỆT ĐỐI KHÔNG tự bịa nhiệt độ hay độ ẩm tương lai" in prompt
    assert "Thời tiết thực tế ngày thi đấu sẽ được hệ thống theo dõi và cập nhật sát ngày (từ T-3 ngày)" in prompt
    assert "RACE WEATHER ADAPTATION" in SYSTEM_PROMPT

def test_hotpot_dinner_timing_feasibility_note():
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT
    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {"weight_kg": 64.9, "sleep_score": 80, "sleep_duration_seconds": 25200},
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "Nếu chọn ăn lẩu, nên bắt đầu sớm (trước 17:45) để kịp kết thúc trước 18:45" in prompt
    assert "BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC" in prompt
    assert "17:45" in SYSTEM_PROMPT
    assert "18:45" in SYSTEM_PROMPT


def test_athlete_biometric_norms_and_weight_tapering(mock_race_config, monkeypatch):
    from src.analytics.prompt_engine import build_advanced_user_prompt, SYSTEM_PROMPT, get_next_upcoming_race
    # Target date 2026-10-02 (2 days before 2026-10-04, days_to_race <= 10)
    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date: get_next_upcoming_race(date, config_path=mock_race_config))

    baseline_data = {
        "target_date": "2026-10-02",
        "target_metrics": {
            "weight_kg": 65.8,
            "body_fat_pct": 17.5,
            "muscle_mass_pct": 37.2,
            "visceral_fat": 6,
            "sleep_score": 85
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-02", "end": "2026-10-01"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "HỒ SƠ VẬN ĐỘNG VIÊN ĐA MÔN" in SYSTEM_PROMPT
    assert "Dải cân nặng thi đấu tối ưu (Optimal Race Weight): 63.5 kg - 65.5 kg" in SYSTEM_PROMPT
    assert "Body Fat mục tiêu: 14% - 16%" in SYSTEM_PROMPT
    assert "TUYỆT ĐỐI KHÔNG SIẾT CÂN HAY CẮT GIẢM CALO" in prompt
    assert "Thể trạng tối ưu, giữ nguyên phong độ" in prompt
    assert "tích trữ năng lượng hoàn toàn bình thường" in prompt


def test_athlete_weight_management_general_training(mock_race_config, monkeypatch):
    from src.analytics.prompt_engine import build_advanced_user_prompt, get_next_upcoming_race
    # Target date 2026-09-19 (15 days before 2026-10-04, days_to_race > 10)
    monkeypatch.setattr("src.analytics.prompt_engine.get_next_upcoming_race", lambda date: get_next_upcoming_race(date, config_path=mock_race_config))

    baseline_data = {
        "target_date": "2026-09-19",
        "target_metrics": {
            "weight_kg": 65.8,
            "body_fat_pct": 17.5,
            "sleep_score": 80
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-19", "end": "2026-09-18"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "GIAI ĐOẠN HUẤN LƯỢNG THÔNG THƯỜNG / PHỤC HỒI SAU RACE" in prompt
    assert "63.5 - 64.5 kg" in prompt
    assert "giảm 4.5 - 6.0 kg lực xung kích" in prompt
    assert "gân Achilles trái" in prompt


def test_dynamic_bmr_calorie_target_and_exact_macro_subtraction(monkeypatch):
    from src.analytics.prompt_engine import build_advanced_user_prompt
    baseline_data = {
        "target_date": "2026-09-26",
        "target_metrics": {
            "weight_kg": 65.4,
            "sleep_score": 80,
            "active_calories": 450
        },
        "daily_data": {
            "activities": [{"calories": 450, "type": "running"}]
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-08-26", "end": "2026-09-25"}
    }

    # Mock nutrition log
    mock_log = [{
        "meal_type": "Bữa sáng",
        "timestamp": "2026-09-26 07:30:00",
        "dishes": ["Phở bò"],
        "total_calories": 500,
        "protein_g": 30,
        "carb_g": 60,
        "fat_g": 15
    }]
    monkeypatch.setattr("src.db.nutrition_repository.get_nutrition_logs_by_date", lambda d: mock_log if d == "2026-09-26" else [])

    prompt = build_advanced_user_prompt(baseline_data)
    # BMR for 65.4kg = 10 * 65.4 + 835 = 1489
    # Target Calo = 1489 + 450 + 500 = 2439 kcal
    # Target Protein = 1.9 * 65.4 = 124.3g
    # Remaining Calo = 2439 - 500 = 1939 kcal
    # Remaining Protein = 124.3 - 30 = 94.3g
    assert "Hard Workout Day" in prompt
    assert "BMR cơ bản ~1489 kcal" in prompt
    assert "Phép tính bù trừ" in prompt
    assert "BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC" in prompt






