import pytest
from src.services.nutrition_calculator import (
    calculate_daily_macro_targets,
    verify_macro_integrity,
    VERIFIED_NUTRITION_TABLE
)


def test_rest_day_protein_target_high_uric_acid():
    # Weight ~65.6kg, Rest day, High Uric acid (442 µmol/L)
    res = calculate_daily_macro_targets(
        weight_kg=65.6,
        day_type="rest",
        uric_acid_umol_l=442.0
    )
    # Target protein must be strictly 1.5 - 1.6 * weight_kg (around 98g - 105g)
    assert 98.0 <= res["protein_g"] <= 105.0
    # Carb target 3.5 - 4.0 * weight_kg (~230g - 265g)
    assert 230.0 <= res["carb_g"] <= 265.0
    # Calorie target dynamically calculated from macros (~1840 kcal, strictly within 1800 - 1980 kcal)
    assert 1800 <= res["target_calories"] <= 1980


def test_hard_workout_day_macro_target():
    res = calculate_daily_macro_targets(
        weight_kg=65.4,
        day_type="workout",
        active_calories_garmin=450.0
    )
    # Target protein 1.8 - 2.0g/kg
    assert res["protein_g"] >= 117.0


def test_macro_integrity_verification():
    # Hallucinated 130g tofu + rice + veg claiming 36.6g protein
    is_valid, realistic_p, msg = verify_macro_integrity("130g tofu + 150g rice + veg", 36.6)
    assert not is_valid
    assert realistic_p <= 20.0
    assert "inflated" in msg

    # Realistic 200g chicken breast claiming 60g protein
    is_valid_cb, p_est, _ = verify_macro_integrity("200g cooked chicken breast", 62.0)
    assert is_valid_cb


def test_calorie_macro_coherence_formula():
    from src.services.nutrition_calculator import calculate_calories_from_macros
    p, c, f = 93.3, 268.0, 50.7
    expected_calories = (93.3 * 4) + (268.0 * 4) + (50.7 * 9)  # 1901.5 kcal
    computed_calories = calculate_calories_from_macros(p, c, f)
    assert abs(computed_calories - expected_calories) < 0.1

    # Test daily macro target coherence within 5 kcal rounding margin
    res = calculate_daily_macro_targets(weight_kg=65.6, day_type="rest")
    true_cal = (res["protein_g"] * 4) + (res["carb_g"] * 4) + (res["fat_g"] * 9)
    assert abs(res["target_calories"] - true_cal) <= 5.0


def test_menu_starch_deduplication():
    from src.services.nutrition_calculator import validate_menu_starch_duplication

    # Case 1: Duplicate starch entries in the same meal
    duplicate_dishes = ["250g khoai lang hấp", "100g khoai lang ăn thêm bù Carb", "150g ức gà"]
    valid, msg = validate_menu_starch_duplication(duplicate_dishes)
    assert not valid
    assert "lặp lại món khoai lang" in msg

    # Case 2: Excessive sweet potato (> 200g)
    excessive_dish = ["250g khoai lang hấp", "150g ức gà"]
    valid_exc, msg_exc = validate_menu_starch_duplication(excessive_dish)
    assert not valid_exc
    assert "vượt ngưỡng" in msg_exc

    # Case 3: Valid meal with single starch <= 200g
    valid_dishes = ["150g khoai lang hấp", "150g ức gà", "200g rau luộc"]
    valid_ok, _ = validate_menu_starch_duplication(valid_dishes)
    assert valid_ok


def test_bedtime_snack_fat_and_nuts_validation():
    from src.services.nutrition_calculator import validate_bedtime_snack_composition

    # Case 1: High fat snack with almonds scheduled at 20:00
    invalid_snack, msg1 = validate_bedtime_snack_composition("15g hạt hạnh nhân + 1 quả chuối", fat_g=7.5)
    assert not invalid_snack
    assert "Nghiêm cấm" in msg1

    # Case 2: High fat snack without nuts (>3g fat)
    invalid_fat, msg2 = validate_bedtime_snack_composition("100g bơ quả", fat_g=14.0)
    assert not invalid_fat

    # Case 3: Fat-free/virtually fat-free snack (< 3g fat)
    valid_snack1, _ = validate_bedtime_snack_composition("1/2 quả chuối chín", fat_g=0.2)
    assert valid_snack1

    valid_snack2, _ = validate_bedtime_snack_composition("100ml sữa tách béo ấm", fat_g=0.1)
    assert valid_snack2

