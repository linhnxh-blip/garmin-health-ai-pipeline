"""
Unit tests for Deterministic Nutrition Engine (src/analytics/nutrition_engine.py).
"""

import pytest
from src.analytics.periodization import TrainingPhase
from src.analytics.nutrition_engine import (
    calculate_daily_macros,
    get_post_race_digestive_guidelines,
    POST_RACE_DIGESTIVE_RULES
)


def test_calculate_daily_macros_post_race_acute():
    # Weight 65.2 kg, POST_RACE_ACUTE phase
    res = calculate_daily_macros(
        weight_kg=65.2,
        phase=TrainingPhase.POST_RACE_ACUTE,
        uric_acid_level=442.0
    )

    # Protein: 1.45 g/kg -> 65.2 * 1.45 = 94.54g (~94.5g)
    assert res["protein_g"] == 94.5
    # Dinner cap strictly locked at 28.0g
    assert res["dinner_protein_cap"] == 28.0
    # Carb: 3.0 g/kg -> 65.2 * 3.0 = 195.6g
    assert res["carb_g"] == 195.6
    # Fat: 0.8 g/kg -> 65.2 * 0.8 = 52.2g
    assert res["fat_g"] == 52.2

    # Atwater Coherence Check: (P*4 + C*4 + F*9)
    expected_calories = (94.5 * 4.0) + (195.6 * 4.0) + (52.2 * 9.0)  # 1630.2 kcal
    assert abs(res["target_calories"] - expected_calories) < 0.1


def test_calculate_daily_macros_post_race_recovery():
    # Weight 64.8 kg, POST_RACE_RECOVERY phase
    res = calculate_daily_macros(
        weight_kg=64.8,
        phase=TrainingPhase.POST_RACE_RECOVERY,
        uric_acid_level=442.0
    )

    assert 90.0 <= res["protein_g"] <= 95.0
    assert res["dinner_protein_cap"] == 28.0
    assert 235.0 <= res["carb_g"] <= 245.0
    # Atwater Coherence Check
    expected_calories = (res["protein_g"] * 4.0) + (res["carb_g"] * 4.0) + (res["fat_g"] * 9.0)
    assert abs(res["target_calories"] - expected_calories) < 0.1


def test_post_race_digestive_guidelines():
    guidelines = get_post_race_digestive_guidelines()
    assert "Runner's Gut" in guidelines
    assert "mật ong" in guidelines
    assert "cháo thịt nạc" in guidelines


def test_calculate_daily_macros_post_race_recovery_with_active_burn():
    # Athlete ran 5.07 km burning 335.0 kcal in morning
    res = calculate_daily_macros(
        weight_kg=65.6,
        phase=TrainingPhase.POST_RACE_RECOVERY,
        uric_acid_level=442.0,
        active_calories_garmin=335.0,
        days_since_race=9
    )
    # Target protein strictly capped at 95.0g for UA protection
    assert res["protein_g"] == 95.0
    # Carb replenished with 335 / 4 = 83.8g: 242.7 + 83.8 = 326.5g
    assert res["carb_g"] == 326.5
    assert res["fat_g"] == 49.2
    assert res["target_calories"] == 2128.8
    # Dinner protein cap locked at 28.0g
    assert res["dinner_protein_cap"] == 28.0
    # Coherence check
    expected_calories = (res["protein_g"] * 4.0) + (res["carb_g"] * 4.0) + (res["fat_g"] * 9.0)
    assert abs(res["target_calories"] - expected_calories) < 0.1
