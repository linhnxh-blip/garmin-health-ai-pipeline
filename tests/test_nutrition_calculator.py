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
    # Target protein strictly capped at 85.0g for Uric Acid 442 µmol/L
    assert res["protein_g"] <= 85.0
    # Carb target 3.5 - 4.0 * weight_kg (~230g - 265g)
    assert 230.0 <= res["carb_g"] <= 265.0
    # Calorie target dynamically calculated from macros (~1788 kcal, strictly within 1700 - 1900 kcal)
    assert 1700 <= res["target_calories"] <= 1900


def test_carbo_loading_t2_t1_low_residue_macros():
    # Carbo-loading T-2 / T-1 with Uric Acid 442 µmol/L
    res = calculate_daily_macro_targets(
        weight_kg=64.8,
        day_type="carbo_loading_t2",
        uric_acid_umol_l=442.0,
        days_to_race=2
    )
    assert res["protein_g"] <= 85.0
    assert 320.0 <= res["carb_g"] <= 340.0
    assert res["fat_g"] <= 35.0
    assert 1950 <= res["target_calories"] <= 2050


def test_hard_workout_day_macro_target():
    res = calculate_daily_macro_targets(
        weight_kg=65.4,
        day_type="workout",
        active_calories_garmin=450.0,
        uric_acid_umol_l=350.0
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


def test_omron_target_benchmarks_constants():
    from src.analytics.constants import OMRON_TARGET_BENCHMARKS
    assert OMRON_TARGET_BENCHMARKS["age"] == 44
    assert OMRON_TARGET_BENCHMARKS["gender"] == "male"
    assert OMRON_TARGET_BENCHMARKS["weight_target_min_kg"] == 64.0
    assert OMRON_TARGET_BENCHMARKS["weight_target_max_kg"] == 65.0
    assert OMRON_TARGET_BENCHMARKS["weight_target_median_kg"] == 64.5
    assert OMRON_TARGET_BENCHMARKS["body_fat_pct_target_range"] == [0.140, 0.165]
    assert OMRON_TARGET_BENCHMARKS["skeletal_muscle_pct_target_range"] == [0.385, 0.405]
    assert OMRON_TARGET_BENCHMARKS["visceral_fat_max_safe"] == 9
    assert OMRON_TARGET_BENCHMARKS["max_daily_protein_g_per_kg"] == 1.35
    assert OMRON_TARGET_BENCHMARKS["max_dinner_protein_g"] == 30.0


def test_post_race_recovery_macros():
    # Weight ~64.8kg, 3 days post FM race
    res = calculate_daily_macro_targets(
        weight_kg=64.8,
        day_type="post_race_recovery",
        days_since_race=3
    )
    # Target protein 1.45 g/kg (~93.96g)
    assert 90.0 <= res["protein_g"] <= 100.0
    # Carb 3.0 g/kg (~194.4g)
    assert 190.0 <= res["carb_g"] <= 205.0
    # Target calories strictly around 1600 - 1700 kcal
    assert 1600 <= res["target_calories"] <= 1700
    # Coherence check
    true_cal = (res["protein_g"] * 4) + (res["carb_g"] * 4) + (res["fat_g"] * 9)
    assert abs(res["target_calories"] - true_cal) <= 5.0


def test_post_race_recovery_macros_with_active_workout_burn():
    # Weight 65.6kg, D+9 post race, active run burn 335.0 kcal
    res = calculate_daily_macro_targets(
        weight_kg=65.6,
        day_type="post_race_recovery",
        active_calories_garmin=335.0,
        days_since_race=9,
        uric_acid_umol_l=442.0
    )
    # Target protein capped at 95.0g
    assert res["protein_g"] == 95.0
    # Carb replenished: 242.7 + 83.8 = 326.5g
    assert res["carb_g"] == 326.5
    assert res["fat_g"] == 49.2
    assert res["target_calories"] == 2128.8
    assert res["dinner_protein_cap"] == 28.0
    # Coherence check
    true_cal = (res["protein_g"] * 4) + (res["carb_g"] * 4) + (res["fat_g"] * 9)
    assert abs(res["target_calories"] - true_cal) <= 5.0


def test_rice_carb_fabrication_detection():
    # Hallucinated 10.7g Carb on 1 bát con cơm trắng
    valid, _, msg = verify_macro_integrity("1 bát con cơm trắng mềm + đậu phụ", stated_protein_g=28.0, stated_carb_g=10.7)
    assert not valid
    assert "bịa đặt Carbohydrate" in msg or "phi sinh học" in msg

    # Realistic 38g Carb on 1 bát con cơm trắng
    valid_ok, _, _ = verify_macro_integrity("1 bát con cơm trắng mềm + đậu phụ", stated_protein_g=15.0, stated_carb_g=38.0)
    assert valid_ok

    # Dish atwater check
    from src.services.nutrition_calculator import verify_dish_atwater_integrity
    valid_dish, msg_dish = verify_dish_atwater_integrity("1 bát con cơm trắng", item_p=4.0, item_c=10.7, item_f=0.5, item_cal=63.3)
    assert not valid_dish
    assert "phi sinh học" in msg_dish


def test_validate_dinner_purine_safety():
    from src.services.nutrition_calculator import validate_dinner_purine_safety

    # High purine shrimp in dinner with Uric Acid 442 µmol/L
    valid_shrimp, msg_shrimp = validate_dinner_purine_safety("1 bát cơm + 5-6 con tôm hấp", uric_acid_umol_l=442.0)
    assert not valid_shrimp
    assert "CẢNH BÁO NGUY CƠ ACID URIC BỮA TỐI" in msg_shrimp

    # Safe low-purine tofu and chicken breast in dinner
    valid_safe, msg_safe = validate_dinner_purine_safety("1 bát cơm + đậu phụ non + ức gà nạc áp chảo", uric_acid_umol_l=442.0)
    assert valid_safe



