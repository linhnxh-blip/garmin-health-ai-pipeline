import os
import pytest
from pathlib import Path
from src.analytics.baseline import calculate_baseline
from src.analytics.llm_analyst import generate_health_analysis
from src.analytics.pipeline import run_health_pipeline
from src.analytics.prompt_engine import build_advanced_user_prompt
from src.services.nutrition_calculator import calculate_daily_macro_targets, validate_menu_protein_cap

def test_mock_llm_mode_parameter(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    from src.db.connection import init_db
    init_db(db_file)

    baseline_data = calculate_baseline("2026-10-02", days=30, db_path=db_file)
    res = generate_health_analysis(baseline_data, mock=True)

    assert res["model_used"] == "garmin-health-engine (mock-mode)"
    assert res["prompt_tokens"] == 0
    assert res["completion_tokens"] == 0
    assert "report_markdown" in res and len(res["report_markdown"]) > 100
    assert "telegram_card" in res and len(res["telegram_card"]) > 50

def test_mock_llm_mode_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    db_file = tmp_path / "garmin_health.db"
    from src.db.connection import init_db
    init_db(db_file)

    baseline_data = calculate_baseline("2026-10-02", days=30, db_path=db_file)
    res = generate_health_analysis(baseline_data, mock=False)

    assert res["model_used"] == "garmin-health-engine (mock-mode)"
    assert res["prompt_tokens"] == 0
    assert res["completion_tokens"] == 0

def test_run_health_pipeline_mock_mode(tmp_path):
    db_file = tmp_path / "garmin_health.db"
    from src.db.connection import init_db
    init_db(db_file)

    res = run_health_pipeline(
        target_date="2026-10-02",
        report_type="morning",
        dry_run=False,
        mock=True,
        db_path=db_file
    )

    assert res["model_used"] == "garmin-health-engine (mock-mode)"
    assert "report_markdown" in res
    assert "exported_path" in res

def test_protein_hard_cap_high_uric_acid():
    # 442 umol/L Uric acid protein target cap <= 85.0g
    macros = calculate_daily_macro_targets(weight_kg=65.0, day_type="rest", uric_acid_umol_l=442.0)
    assert macros["protein_g"] <= 85.0

    valid, msg = validate_menu_protein_cap(total_protein_g=95.0)
    assert not valid
    assert "vượt trần 85.0g" in msg

def test_t2_t1_low_residue_prompt_rules():
    baseline_data = {
        "target_date": "2026-10-02",
        "target_metrics": {"weight_kg": 64.8, "sleep_score": 82, "hrv_last_night": 46, "resting_heart_rate": 56},
        "metrics_baseline": {"sleep_score": {"avg": 80}, "hrv_last_night": {"avg": 45}},
        "training_load_7d": {},
        "sample_size_days": 30,
        "date_range": {"start": "2026-09-02", "end": "2026-10-01"}
    }
    prompt = build_advanced_user_prompt(baseline_data)

    # Clean starch preference
    assert "Cơm trắng" in prompt
    assert "bánh phở" in prompt
    assert "bánh mì gối trắng" in prompt
    # Forbid coarse fiber starch
    assert "Yến mạch cán vỡ" in prompt
    assert "gạo lứt" in prompt
    # No 180d or All-Time baseline text
    assert "Baseline 180d" not in prompt
    assert "Baseline All-Time" not in prompt
