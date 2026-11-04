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
    assert "Deep Sleep Đêm qua: 84.0 phút (21.1%)" in prompt
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
    assert "LỰA CHỌN 1" in prompt
    assert "LỰA CHỌN 2" in prompt
    assert "Sprint 100% all-out" in SYSTEM_PROMPT
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
    assert "Baseline 30d: 84.0m (21.1%)" in prompt

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
    # SpO2 drop < 85% pathological warning block is removed per Requirement 4
    assert "SPO2 TỤT THẤP (< 85%" not in prompt

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
    assert "2.5 - 3.0 tiếng" in prompt
    assert "BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC" in prompt
    assert "2.5 - 3.0 tiếng" in SYSTEM_PROMPT


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
    assert "64.0 kg - 65.0 kg" in SYSTEM_PROMPT
    assert "14.0% - 16.5%" in SYSTEM_PROMPT
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
    assert "Achilles" in prompt


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


def test_post_race_recovery_phase_detection(mock_race_config, monkeypatch):
    from src.analytics.prompt_engine import get_race_context, build_advanced_user_prompt, generate_executive_brief

    # Target date 2026-10-07 (3 days after Hanoi Full Marathon 2026-10-04)
    monkeypatch.setattr(
        "src.analytics.prompt_engine.get_race_context",
        lambda date: get_race_context(date, config_path=mock_race_config)
    )

    ctx = get_race_context("2026-10-07", config_path=mock_race_config)
    assert ctx["phase"] == "POST_RACE_ACUTE"
    assert ctx["days_since_race"] == 3
    assert ctx["taper_strict_mode"] is False

    ctx_recovery = get_race_context("2026-10-15", config_path=mock_race_config)
    assert ctx_recovery["phase"] == "POST_RACE_RECOVERY"
    assert ctx_recovery["days_since_race"] == 11

    baseline_data = {
        "target_date": "2026-10-07",
        "target_metrics": {
            "weight_kg": 64.8,
            "sleep_score": 85,
            "hrv_last_night": 46,
            "body_battery_highest": 80
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-07", "end": "2026-10-06"}
    }

    prompt = build_advanced_user_prompt(baseline_data)

    # Must contain Post-Race instructions
    assert "POST-RACE" in prompt or "POST_RACE" in prompt
    assert "Chấm dứt" in prompt or "CHẤM DỨT" in prompt
    assert "ức gà" in prompt or "đạm trắng" in prompt
    assert "NGHỈ CHẠY HOÀN TOÀN" in prompt or "Full Rest" in prompt
    assert "XÓA BỎ BẮT BUỘC CÁC TỪ KHÓA" in prompt or "NGHIÊM CẤM" in prompt

    # Strictly prohibit tapering phrases in generated brief & fallback cards
    forbidden_terms = ["chuẩn bị glycogen", "kích hoạt thần kinh cơ", "Strides"]
    brief = generate_executive_brief(baseline_data)
    assert "Phục hồi" in brief
    for term in forbidden_terms:
        assert term not in brief, f"Forbidden term '{term}' found in brief!"

    from src.analytics.prompt_engine import generate_telegram_card_fallback
    card = generate_telegram_card_fallback(baseline_data)
    for term in forbidden_terms:
        assert term not in card, f"Forbidden term '{term}' found in fallback card!"


def test_master_prompt_upgrade_section_3_title_and_no_dynamic_tapering():
    """Verify Section 3 title and complete removal of Dynamic Tapering in post-race prompts."""
    from src.analytics.prompt_engine import get_system_prompt
    from src.analytics.periodization import TrainingPhase

    for phase in [TrainingPhase.POST_RACE_ACUTE, TrainingPhase.POST_RACE_RECOVERY]:
        prompt = get_system_prompt(
            report_type="morning",
            date_vn="Thứ Bảy, 11/10/2026",
            weight_kg="64.8",
            phase=phase,
            days_since=7
        )
        # Check Section 3 Title matches exact standard and lacks Dynamic Tapering
        expected_title = "### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+7):"
        assert expected_title in prompt
        # Verify Section 3 block explicitly
        matching_secs = [s for s in prompt.split("===SECTION_BREAK===") if expected_title in s]
        assert len(matching_secs) == 1
        sec3_content = matching_secs[0]
        assert "Dynamic Tapering" not in sec3_content


def test_master_prompt_upgrade_vietnamese_realistic_meals():
    """Verify realistic Vietnamese meal portions (bowls/plates) and prohibition of oats & lab grams."""
    from src.analytics.prompt_engine import get_system_prompt
    from src.analytics.nutrition_engine import POST_RACE_DIGESTIVE_RULES, POST_RACE_REALISTIC_MEALS

    # Check prohibited foods in nutrition_engine
    assert "yến mạch cán vỡ" in POST_RACE_DIGESTIVE_RULES["prohibited_foods"]
    assert "ngũ cốc thô" in POST_RACE_DIGESTIVE_RULES["prohibited_foods"]

    # Check realistic benchmark meals structure
    assert "cháo gạo trắng" in POST_RACE_REALISTIC_MEALS["breakfast"].lower()
    assert "phở gà nạc" in POST_RACE_REALISTIC_MEALS["breakfast"].lower()
    assert "1.5 bát con cơm trắng mềm" in POST_RACE_REALISTIC_MEALS["lunch"].lower()
    assert "chuối tiêu chín" in POST_RACE_REALISTIC_MEALS["snack"].lower()
    assert "đậu phụ non" in POST_RACE_REALISTIC_MEALS["dinner"].lower()
    assert "<= 28.0g" in POST_RACE_REALISTIC_MEALS["dinner"]

    # Check prompt contains realistic guidelines
    prompt = get_system_prompt(
        report_type="morning",
        date_vn="Thứ Bảy, 11/10/2026",
        weight_kg="64.8",
        phase="POST_RACE_RECOVERY",
        days_since=7
    )
    assert "Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ" in prompt
    assert "1.5 bát con cơm trắng mềm" in prompt
    assert "1 quả chuối tiêu chín" in prompt
    assert "Đậu phụ non sốt cà chua nhạt" in prompt
    assert "trần Protein <= 28.0g" in prompt or "bữa tối <= 28.0g" in prompt


def test_post_race_atwater_deterministic_macros():
    """Verify Atwater deterministic calculations (4-4-9) and dinner protein cap <= 28.0g."""
    from src.analytics.nutrition_engine import calculate_daily_macros
    from src.analytics.periodization import TrainingPhase

    macros = calculate_daily_macros(
        weight_kg=64.8,
        phase=TrainingPhase.POST_RACE_RECOVERY,
        uric_acid_level=442.0,
        days_since_race=7
    )

    # Deterministic Atwater: Total calories = P*4 + C*4 + F*9
    calculated_calories = macros["protein_g"] * 4 + macros["carb_g"] * 4 + macros["fat_g"] * 9
    assert macros["target_calories"] == calculated_calories
    # Dinner protein capped <= 28.0g for Uric acid 442 umol/L
    assert macros["dinner_protein_cap"] <= 28.0
    assert macros["dinner_protein_cap"] == 28.0


def test_post_race_recovery_shakeout_eligible_prompt(mock_race_config, monkeypatch):
    """Test conditional shakeout run is enabled in POST_RACE_RECOVERY when metrics are green."""
    from src.analytics.prompt_engine import (
        get_race_context,
        build_advanced_user_prompt,
        generate_executive_brief,
        generate_telegram_card_fallback
    )

    monkeypatch.setattr(
        "src.analytics.prompt_engine.get_race_context",
        lambda date: get_race_context(date, config_path=mock_race_config)
    )

    baseline_data = {
        "target_date": "2026-10-15",  # D+11 post race (POST_RACE_RECOVERY)
        "target_metrics": {
            "weight_kg": 64.8,
            "sleep_score": 88,
            "training_readiness_score": 75,  # >= 65
            "recovery_time_hours": 3,         # <= 6
            "hrv_status": "BALANCED",         # BALANCED
            "hrv_last_night": 52,
            "body_battery_highest": 85,
            "total_steps": 3000,
            "active_calories": 200
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-15", "end": "2026-10-14"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "POST_RACE_RECOVERY" in prompt
    assert "2.0 km - 3.0 km" in prompt or "2.0-3.0km" in prompt
    assert "Zone 1 / Low Zone 2" in prompt
    assert "<= 135 bpm" in prompt
    assert "DỪNG NGAY LẬP TỨC" in prompt
    assert "Isometric Holds" in prompt
    brief = generate_executive_brief(baseline_data)
    assert "Shakeout Run 2.0-3.0km" in brief
    assert "Isometric Holds" in brief
    assert "Dynamic Tapering" not in brief

    card = generate_telegram_card_fallback(baseline_data)
    assert "Shakeout Run thích ứng 2.0-3.0 km" in card
    assert "Isometric Holds" in card
    assert "Dynamic Tapering" not in card


def test_post_race_recovery_shakeout_not_eligible_prompt(mock_race_config, monkeypatch):
    """Test shakeout run is gated when recovery metrics are not green in POST_RACE_RECOVERY."""
    from src.analytics.prompt_engine import (
        get_race_context,
        build_advanced_user_prompt,
        generate_executive_brief,
        generate_telegram_card_fallback
    )

    monkeypatch.setattr(
        "src.analytics.prompt_engine.get_race_context",
        lambda date: get_race_context(date, config_path=mock_race_config)
    )

    baseline_data = {
        "target_date": "2026-10-15",  # D+11 post race (POST_RACE_RECOVERY)
        "target_metrics": {
            "weight_kg": 64.8,
            "sleep_score": 60,
            "training_readiness_score": 50,  # < 65 (Not eligible)
            "recovery_time_hours": 18,        # > 6 (Not eligible)
            "hrv_status": "UNBALANCED",       # Not BALANCED
            "hrv_last_night": 32,
            "body_battery_highest": 45,
            "total_steps": 2000,
            "active_calories": 100
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-15", "end": "2026-10-14"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "POST_RACE_RECOVERY" in prompt
    assert "CHƯA ĐẠT ĐIỀU KIỆN CHẠY" in prompt
    assert "CẤM chạy bộ" in prompt
    assert "Isometric Holds" in prompt

    brief = generate_executive_brief(baseline_data)
    assert "Nghỉ hoàn toàn hoặc chỉ đi bộ 15 phút" in brief
    assert "Isometric Holds" in brief

    card = generate_telegram_card_fallback(baseline_data)
    assert "Nghỉ ngơi hoàn toàn hoặc chỉ đi bộ nhẹ 15 phút" in card
    assert "Isometric Holds" in card


def test_post_race_acute_strict_no_running(mock_race_config, monkeypatch):
    """Verify POST_RACE_ACUTE (D+1 to D+7) strictly prohibits running even if metrics are green."""
    from src.analytics.prompt_engine import (
        get_race_context,
        build_advanced_user_prompt,
        generate_executive_brief,
        generate_telegram_card_fallback
    )

    monkeypatch.setattr(
        "src.analytics.prompt_engine.get_race_context",
        lambda date: get_race_context(date, config_path=mock_race_config)
    )

    baseline_data = {
        "target_date": "2026-10-08",  # D+4 post race (POST_RACE_ACUTE)
        "target_metrics": {
            "weight_kg": 64.8,
            "sleep_score": 90,
            "training_readiness_score": 85,  # High readiness
            "recovery_time_hours": 0,         # 0 hours
            "hrv_status": "BALANCED",         # BALANCED
            "hrv_last_night": 55,
            "body_battery_highest": 92,
            "total_steps": 3500,
            "active_calories": 150
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-08", "end": "2026-10-07"}
    }

    prompt = build_advanced_user_prompt(baseline_data)
    assert "POST_RACE_ACUTE" in prompt
    assert "CẤM CHẠY HOÀN TOÀN" in prompt
    assert "Isometric Holds" in prompt

    brief = generate_executive_brief(baseline_data)
    assert "CẤM CHẠY HOÀN TOÀN" in brief
    assert "Isometric Holds" in brief

    card = generate_telegram_card_fallback(baseline_data)
    assert "CẤM mọi hình thức chạy bộ" in card
    assert "Isometric Holds" in card


def test_evening_review_post_race_recovery_d9_and_immediate_pre_sleep_protocol(mock_race_config, monkeypatch):
    """Verify Evening Review on D+9:
    1. Correctly synchronizes POST_RACE_RECOVERY (Giai đoạn Hồi phục Thích ứng D+9), NOT POST_RACE_ACUTE.
    2. Rest day recommendation without extreme prohibition like 'nghỉ đến hết tuần'.
    3. Section 4 is Immediate Pre-Sleep Protocol with Bước 1, Bước 2, Bước 3, Bước 4.
    """
    from src.analytics.prompt_engine import (
        get_system_prompt,
        build_advanced_user_prompt,
        generate_telegram_card_fallback,
        get_race_context
    )

    monkeypatch.setattr(
        "src.analytics.prompt_engine.get_race_context",
        lambda date, config_path=None: get_race_context(date, config_path=mock_race_config)
    )

    baseline_data = {
        "target_date": "2026-10-13",  # D+9 post race
        "report_type": "evening",
        "target_metrics": {
            "weight_kg": 65.4,
            "sleep_score": 88,
            "training_readiness_score": 65,
            "recovery_time_hours": 11,
            "hrv_status": "BALANCED",
            "hrv_last_night": 41,
            "total_steps": 13165,
            "active_calories": 769
        },
        "metrics_baseline": {},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-13", "end": "2026-10-12"}
    }

    # 1. System Prompt for Evening Review
    sys_prompt = get_system_prompt(
        report_type="evening",
        date_vn="Thứ Ba, 13/10/2026",
        weight_kg="65.4 kg",
        phase="POST_RACE_RECOVERY",
        days_since=9,
        target_date="2026-10-13"
    )

    # Must specify POST_RACE_RECOVERY (Giai đoạn Hồi phục Thích ứng D+9)
    assert "POST_RACE_RECOVERY (Giai đoạn Hồi phục Thích ứng D+9)" in sys_prompt
    assert "TUYỆT ĐỐI KHÔNG gọi là `POST_RACE_ACUTE`" in sys_prompt
    # Movement guidance: absorb 13.000 steps without extreme prohibition
    assert "hấp thu 13.000 bước" in sys_prompt
    assert "TUYỆT ĐỐI KHÔNG dùng từ ngữ cấm đoán cực đoan như \"nghỉ đến hết tuần\"" in sys_prompt
    # Section 4: Immediate Pre-Sleep Protocol
    assert "### 💤 4. Giao thức Thực hiện Ngay Trước Khi Lên Giường (Immediate Pre-Sleep Protocol):" in sys_prompt
    assert "Bước 1 (Uống vi chất & bù nước):" in sys_prompt
    assert "Bước 2 (Xả tải cơ học):" in sys_prompt
    assert "Bước 3 (Ngắt thiết bị):" in sys_prompt
    assert "Bước 4 (Đi ngủ):" in sys_prompt
    # Must NOT have fixed past time markers in Section 4
    assert "20:30: Uống 1 viên" not in sys_prompt
    assert "21:00: Digital Detox" not in sys_prompt

    # 2. Advanced User Prompt
    user_prompt = build_advanced_user_prompt(baseline_data)
    assert "POST_RACE_RECOVERY" in user_prompt
    assert "Giai đoạn Hồi phục Thích ứng D+9" in user_prompt

    # 3. Telegram Card Fallback for Evening
    card = generate_telegram_card_fallback(baseline_data)
    assert "POST_RACE_RECOVERY" in card
    assert "nghỉ hết tuần" not in card
    assert "Giao thức trước khi lên giường" in card
    assert "Magie Bisglycinate" in card


def test_anti_meta_leak_and_pseudo_code_sanitization():
    """Verify clean_report_text strips meta rules, pseudo-code and converts MAINTAINING_4."""
    from src.analytics.prompt_engine import clean_report_text

    dirty_report = """# 🌅 Báo cáo Khởi động Ngày
| Pha giấc ngủ | Đêm qua |
| Deep Sleep | 58m |

*Quy tắc Bảng Markdown:* Bảng Markdown PHẢI viết sát lề trái (không thụt lề đầu dòng), có 1 dòng trống trước và sau bảng để render HTML hoàn hảo trên Web Dashboard.

- **Đối chiếu Dinh dưỡng & Đồ nhậu Hôm qua:** Do đó không xuất hiện hiện tượng ức chế acetylcholine hay hội chứng cồn ức chế pha REM.
- **Bối cảnh Microcycle:** Trạng thái MAINTAINING_4 (Mã Garmin gốc: MAINTAINING_4). Tuyệt đối KHÔNG nhầm lẫn giữa phục hồi sau giải (Post-Race) với giảm tải trước giải (Tapering).
- **Quy tắc Kê đơn Vận động Có Điều kiện (Reverse Taper Shakeout Run):**
  + **Điều kiện để mở cửa chạy thử (Shakeout Run):**
    * training_readiness >= 65 (Đạt: 65)
    * recovery_time_hours <= 6 (Chưa đạt: 11 giờ)
    * hrv_status == "BALANCED" (Đạt: BALANCED)
  + Trạng thái thể lực ghi nhận mức Sẵn sàng 65/100.
- **Dynamic Macro Targets (Cân nặng 65.59 kg):** Sử dụng chính xác 100% mục tiêu Macro Deterministic do hệ thống quy định:
"""
    cleaned = clean_report_text(dirty_report)

    # 1. Anti-meta leak checks
    assert "*Quy tắc Bảng Markdown:*" not in cleaned
    assert "Bảng Markdown PHẢI viết sát lề" not in cleaned
    assert "Tuyệt đối KHÔNG nhầm lẫn giữa phục hồi" not in cleaned
    assert "Tuyệt đối không nhầm lẫn giữa phục hồi" not in cleaned
    assert "Sử dụng chính xác 100% mục tiêu Macro Deterministic" not in cleaned
    assert "Macro Deterministic" not in cleaned

    # 2. No pseudo-code checks
    assert "training_readiness >=" not in cleaned
    assert "recovery_time_hours <=" not in cleaned
    assert "hrv_status ==" not in cleaned
    assert "MAINTAINING_4" not in cleaned
    assert "(Mã Garmin gốc:" not in cleaned
    assert "Duy trì (Maintaining)" in cleaned

    # 3. Fluff check
    assert "ức chế acetylcholine" not in cleaned


def test_morning_system_prompt_anti_meta_and_clinical_templates():
    """Verify system prompt enforces clinical sports medicine prose and closing inquiry."""
    from src.analytics.prompt_engine import get_system_prompt

    prompt = get_system_prompt(
        report_type="morning",
        date_vn="Thứ Tư, 14/10/2026",
        weight_kg="65.59",
        phase="POST_RACE_RECOVERY",
        days_since=10
    )

    # Must contain system instructions forbidding leaks
    assert "Bảng Markdown PHẢI viết sát lề trái" in prompt
    assert "TUYỆT ĐỐI CẤM in các câu chỉ dẫn meta" in prompt
    assert "TUYỆT ĐỐI CẤM in nguyên xi cú pháp biến logic hoặc mã code kiểu developer" in prompt

    # Template must NOT contain pseudo-code expressions
    # Verify section 3 block has clinical phrasing
    assert "thời gian hồi phục mô liên kết (Recovery Time) vẫn còn" in prompt
    assert "Do chưa đạt mốc an toàn sinh học (<= 6 giờ)" in prompt

    # Template must contain closing physical health check-in
    assert "nốt viêm xương cụt" in prompt
    assert "bắp chuối trái" in prompt


def test_format_training_status_all_suffixes():
    """Verify format_training_status normalizes any numeric suffix."""
    from src.analytics.prompt_engine import format_training_status

    assert format_training_status("MAINTAINING_4") == "Duy trì (Maintaining)"
    assert format_training_status("MAINTAINING_2") == "Duy trì (Maintaining)"
    assert format_training_status("MAINTAINING") == "Duy trì (Maintaining)"
    assert format_training_status("RECOVERY_2") == "Phục hồi (Recovery)"
    assert format_training_status("PRODUCTIVE_3") == "Hiệu quả (Productive)"
    assert format_training_status("PEAKING_2") == "Đạt đỉnh (Peaking)"
    assert format_training_status(None) == "Chưa xác định"


def test_negative_constraint_purges_sweet_potato():
    """Verify that active negative constraint forbids sweet potato and replaces it properly."""
    from src.analytics.prompt_engine import clean_report_text
    from src.analytics.nutrition_engine import generate_lean_menu

    # 1. Test generate_lean_menu respects negative constraint
    menu = generate_lean_menu(
        target_fat_g=50.0,
        dinner_protein_cap=28.0,
        target_calories=1800,
        target_protein_g=90.0,
        target_carb_g=240.0,
        is_post_race=True,
        negative_constraints=["không khoai lang"]
    )
    assert "khoai lang" not in menu["snack"].lower()
    assert "chuối tiêu" in menu["snack"] or "bánh mì" in menu["snack"]

    # 2. Test clean_report_text purges sweet potato when negative constraint is present
    dirty_text = (
        "### 🍱 4. Kế hoạch Dinh dưỡng:\n"
        "- Thực đơn (Không khoai lang):\n"
        "  + Bữa xế chiều: 1 củ khoai lang hấp cỡ vừa (~120g) + 1 hộp sữa chua ít béo.\n"
    )
    cleaned = clean_report_text(dirty_text)
    assert "khoai lang" not in cleaned.lower()
    assert ("chuối tiêu chín" in cleaned) or ("bánh mì mềm" in cleaned)

    # 3. Test that 'không yến mạch' does NOT get converted to 'không khoai lang'
    prompt_header = "Thực đơn Thực tế Dân dã (Không yến mạch):"
    cleaned_header = clean_report_text(prompt_header)
    assert "Không khoai lang" not in cleaned_header
    assert "Không ngũ cốc thô" in cleaned_header


def test_deterministic_sleep_stage_math():
    """Verify sleep stage math calculates Deep, REM, Light over Time Asleep (sum 100%) and Awake over Total Bed Time."""
    from src.analytics.prompt_engine import clean_report_text

    # Given: Deep 34m, REM 42m, Light 310m (Total asleep = 386m), Awake 34m (Total bed = 420m)
    # Expected: Deep = 34/386 = 8.8%, REM = 42/386 = 10.9%, Light = 100 - 8.8 - 10.9 = 80.3%
    # Awake = 34/420 = 8.1% (previously buggy 8.8% calculated on 386m)
    buggy_table = (
        "| Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |\n"
        "| :--- | :--- | :--- | :--- | :--- |\n"
        "| Deep Sleep | 34.0m (8.8%) | 54.9m (13.4%) | 15% - 25% | Suy giảm nặng |\n"
        "| REM Sleep | 42.0m (10.9%) | 75.0m (18.3%) | 20% - 25% | Bị ức chế |\n"
        "| Light Sleep | 310.0m (80.4%) | 244.5m (59.7%) | 50% - 60% | Tăng vọt |\n"
        "| Awake | 34.0m (8.8%) | 16.3m (4.0%) | < 5% | Gián đoạn |\n"
        "\n"
        "Cơ thể dành đến 80.4% thời lượng giấc ngủ ở pha ngủ nông (Light Sleep)."
    )
    cleaned = clean_report_text(buggy_table)

    assert "| Light Sleep | 310.0m (80.3%) |" in cleaned
    assert "| Awake | 34.0m (8.1%) |" in cleaned
    assert "80.3% thời lượng giấc ngủ ở pha ngủ nông" in cleaned


def test_post_alcohol_uric_acid_flush_protocol():
    """Verify that alcohol detection enforces alkaline hydration protocol for Uric Acid protection."""
    from src.analytics.prompt_engine import clean_report_text

    report_with_alcohol = (
        "### 💤 2. Bóc tách Cấu trúc Giấc ngủ:\n"
        "- Tiệc nhậu lúc 19:30 tối qua với 10.5 đơn vị cồn làm ức chế REM.\n"
        "===SECTION_BREAK===\n"
        "### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa:\n"
        "- Macro Mục tiêu: Protein 85.0g.\n"
        "- Bảo vệ Lâm sàng Acid Uric & Tiêu hóa:\n"
        "  * Bữa tối tuân thủ nghiêm ngặt trần Protein 28.0g.\n"
        "💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng.\n"
    )

    cleaned = clean_report_text(report_with_alcohol)
    required_str = (
        "Uống tối thiểu 3.0L - 3.2L nước rải đều trong ngày, ưu tiên nước khoáng kiềm pH 8.5-9.0 (Fujiwa) "
        "để nâng pH nước tiểu, chống lắng đọng tinh thể urat tại gân Achilles."
    )
    assert required_str in cleaned










