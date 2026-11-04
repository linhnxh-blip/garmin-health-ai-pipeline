"""
Tests for Report Architecture & Evening Review Integrity.
Validates:
1. Evening report binds to actual logged meals in nutrition_logs (no fictional hallucinations).
2. Elimination of nonsense variable output (string 'trần Protein <= 0.0g' never appears).
3. Reconciled non-contradictory next-day exercise directives.
4. Concise report format strictly under 200 words (card under 150 words).
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from src.db.connection import get_db_connection, init_db
from src.db.nutrition_repository import save_nutrition_log
from src.analytics.card_generator import (
    extract_evening_meals,
    generate_evening_components,
    generate_evening_report,
    generate_evening_card
)
from src.analytics.llm_analyst import generate_health_analysis
from src.analytics.prompt_engine import build_advanced_user_prompt, get_system_prompt


@pytest.fixture
def test_env(tmp_path):
    test_db = tmp_path / "test_garmin.db"
    init_db(test_db)

    # 1. Insert daily metrics for 2026-10-20
    acts = [
        {
            "name": "Chạy MAF Zone 2",
            "type": "running",
            "duration_seconds": 2340,
            "distance_meters": 6000,
            "avg_cadence": 176,
            "avg_heart_rate": 146
        }
    ]

    with get_db_connection(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_metrics (
                date, total_steps, step_goal, active_calories,
                training_readiness_score, recovery_time_hours,
                activities_summary, training_status, weight_kg
            ) VALUES (
                '2026-10-20', 10825, 10000, 576.0,
                72, 14,
                ?, 'RECOVERY', 65.3
            )
            """,
            (json.dumps(acts),)
        )
        conn.commit()

    # 2. Insert actual nutrition logs for 2026-10-20
    # Lunch
    save_nutrition_log({
        "date": "2026-10-20",
        "timestamp": "2026-10-20 12:30:00",
        "meal_type": "Bữa trưa",
        "dishes": ["Cơm trắng", "Cá hồi hấp", "Canh cải"],
        "total_calories": 780,
        "protein_g": 59.2,
        "carb_g": 78.0,
        "fat_g": 9.5
    }, db_path=test_db)

    # Evening Dinner at 19:23
    save_nutrition_log({
        "date": "2026-10-20",
        "timestamp": "2026-10-20 19:23:00",
        "meal_type": "Bữa tối",
        "dishes": ["Thịt quay", "sườn", "cơm", "canh bắp cải"],
        "total_calories": 920,
        "protein_g": 42.0,
        "carb_g": 85.0,
        "fat_g": 44.0
    }, db_path=test_db)

    # Evening Drink at 20:10
    save_nutrition_log({
        "date": "2026-10-20",
        "timestamp": "2026-10-20 20:10:00",
        "meal_type": "Thức uống",
        "dishes": ["400ml nước ép dưa hấu"],
        "total_calories": 140,
        "protein_g": 1.0,
        "carb_g": 32.0,
        "fat_g": 0.5
    }, db_path=test_db)

    baseline_data = {
        "target_date": "2026-10-20",
        "report_type": "evening",
        "db_path": test_db,
        "target_metrics": {
            "date": "2026-10-20",
            "total_steps": 10825,
            "step_goal": 10000,
            "active_calories": 576.0,
            "training_readiness_score": 72,
            "recovery_time_hours": 14,
            "training_status": "RECOVERY",
            "weight_kg": 65.3,
            "activities_summary": json.dumps(acts)
        }
    }

    return {
        "db_path": test_db,
        "baseline_data": baseline_data
    }


def test_evening_report_binds_to_actual_nutrition_logs(test_env):
    """Assert that evening report includes the exact food names from today's nutrition_logs (e.g. thịt quay, dưa hấu)."""
    baseline_data = test_env["baseline_data"]
    report = generate_evening_report(baseline_data)
    card = generate_evening_card(baseline_data)

    rep_lower = report.lower()
    card_lower = card.lower()

    # 1. Exact food names must appear (NO fictional tofu/tomato sauce)
    assert "thịt quay" in rep_lower
    assert "sườn" in rep_lower
    assert "dưa hấu" in rep_lower

    assert "thịt quay" in card_lower
    assert "sườn" in card_lower
    assert "dưa hấu" in card_lower

    assert "đậu phụ" not in rep_lower
    assert "cà chua" not in rep_lower
    assert "đậu phụ" not in card_lower


def test_evening_report_protein_cap_logic(test_env):
    """Assert that string 'trần Protein <= 0.0g' NEVER appears in output and delta is shown."""
    baseline_data = test_env["baseline_data"]
    report = generate_evening_report(baseline_data)
    card = generate_evening_card(baseline_data)

    assert "trần Protein <= 0.0g" not in report
    assert "<= 0.0g" not in report
    assert "trần Protein <= 0.0g" not in card
    assert "<= 0.0g" not in card

    # Deviation calculation check (total protein = 59.2 + 42.0 + 1.0 = 102.2g)
    assert "102.2g" in report
    assert "vượt trần đạm an toàn" in report or "Thừa" in report


def test_evening_report_word_count_limits(test_env):
    """Assert report length is under 200 words and card is under 150 words."""
    baseline_data = test_env["baseline_data"]
    report = generate_evening_report(baseline_data)
    card = generate_evening_card(baseline_data)

    report_words = report.split()
    card_words = card.split()

    assert len(report_words) < 200, f"Evening report word count {len(report_words)} exceeds 200 words"
    assert len(card_words) < 150, f"Evening card word count {len(card_words)} exceeds 150 words"


def test_evening_report_reconciled_workout_advice(test_env):
    """Assert non-contradictory next-day exercise directive."""
    baseline_data = test_env["baseline_data"]
    report = generate_evening_report(baseline_data)

    assert "21/10" in report
    assert "Ưu tiên Nghỉ ngơi (Rest Day) hoặc đi bộ thả lỏng" in report
    assert "CHỈ chạy thử 2km nếu sáng mai Readiness >= 68 và Recovery Time <= 4h" in report


def test_evening_report_via_llm_analyst_pipeline(test_env):
    """Assert full pipeline integration via generate_health_analysis."""
    baseline_data = test_env["baseline_data"]
    res = generate_health_analysis(baseline_data)

    report = res["report_markdown"]
    card = res["telegram_card"]

    assert "thịt quay" in report.lower()
    assert "dưa hấu" in report.lower()
    assert "trần Protein <= 0.0g" not in report
    assert len(report.split()) < 200
    assert len(card.split()) < 150


def test_prompt_engine_no_zero_protein_cap_leak(test_env):
    """Assert prompt engine never outputs 'trần Protein <= 0.0g' when protein is in surplus."""
    baseline_data = test_env["baseline_data"]
    prompt = build_advanced_user_prompt(baseline_data)

    assert "trần Protein <= 0.0g" not in prompt
    assert "<= 0.0g" not in prompt
    assert "vượt trần đạm an toàn" in prompt
