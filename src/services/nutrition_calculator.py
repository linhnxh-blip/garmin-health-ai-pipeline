"""
Clinical Nutrition Calculator & Verified Macro Reference Table.
Implements sports medicine guidelines for endurance athletes with biochemical considerations (e.g., Uric Acid).
"""

from typing import Dict, Any, Tuple, Optional, List

# Verified Nutritional Database per 100g (or standard serving unit)
VERIFIED_NUTRITION_TABLE = {
    "tofu_raw_100g": {"protein_g": 8.1, "carb_g": 1.9, "fat_g": 4.8, "calories": 76.4},
    "chicken_breast_cooked_100g": {"protein_g": 31.0, "carb_g": 0.0, "fat_g": 3.6, "calories": 156.4},
    "cooked_rice_150g_bowl": {"protein_g": 4.0, "carb_g": 41.0, "fat_g": 0.4, "calories": 183.6},
    "salmon_cooked_100g": {"protein_g": 22.0, "carb_g": 0.0, "fat_g": 12.0, "calories": 196.0},
    "egg_whole_50g": {"protein_g": 6.3, "carb_g": 0.4, "fat_g": 4.8, "calories": 70.0},
    "lean_beef_cooked_100g": {"protein_g": 26.0, "carb_g": 0.0, "fat_g": 7.0, "calories": 167.0},
    "lean_fish_cooked_100g": {"protein_g": 20.0, "carb_g": 0.0, "fat_g": 1.5, "calories": 93.5},
    "chobani_greek_yogurt_150g": {"protein_g": 15.0, "carb_g": 6.0, "fat_g": 0.0, "calories": 84.0},
    "sweet_potato_100g": {"protein_g": 1.6, "carb_g": 20.0, "fat_g": 0.1, "calories": 87.3},
    "oats_raw_50g": {"protein_g": 6.5, "carb_g": 33.0, "fat_g": 3.5, "calories": 189.5},
    "lean_pork_cooked_100g": {"protein_g": 21.0, "carb_g": 0.0, "fat_g": 5.0, "calories": 129.0},
    "rau_ngot_100g": {"protein_g": 3.0, "carb_g": 5.0, "fat_g": 0.4, "calories": 35.6},
    "canh_rau_ngot_thit_nac_30g": {"protein_g": 7.8, "carb_g": 2.5, "fat_g": 1.5, "calories": 54.7},
    "orange_fresh_100g": {"protein_g": 0.9, "carb_g": 9.5, "fat_g": 0.1, "calories": 47.0}
}


def calculate_calories_from_macros(protein_g: float, carb_g: float, fat_g: float) -> float:
    """
    Calculate exact calories from macronutrients: (Protein * 4) + (Carb * 4) + (Fat * 9).
    Strictly guarantees mathematical coherence.
    """
    return round((float(protein_g) * 4.0) + (float(carb_g) * 4.0) + (float(fat_g) * 9.0), 1)


def calculate_daily_macro_targets(
    weight_kg: float,
    day_type: str = "rest",
    uric_acid_umol_l: Optional[float] = None,
    height_cm: float = 168.0,
    age: int = 44,
    active_calories_garmin: float = 0.0
) -> Dict[str, Any]:
    """
    Calculate daily macro and calorie targets based on day type and clinical flags.

    Refactoring Rules:
    - Calorie-Macro Coherence:
      total_calories is strictly calculated via calculate_calories_from_macros(P, C, F).
    - Rest / Recovery Day (~65.6kg):
      * Protein target: Strictly 1.5 - 1.6 * weight_kg (98g - 105g for ~65.6kg).
      * Carb target: 3.5 - 4.0 * weight_kg (230g - 260g).
      * Fat target: 45g - 55g (e.g., 50.0g).
      * Realistic calorie target dynamically set to ~1,850 - 1,950 kcal derived from (P*4)+(C*4)+(F*9).
    - Workout Day: Protein target 1.8 - 2.0 * weight_kg (~120 - 130g).
    - Carbo-Loading Day: Carbs 7.0 - 10.0 * weight_kg (70% total energy).

    Returns:
        Dict with target_calories, protein_g, carb_g, fat_g, bmr, and clinical_notes.
    """
    w = max(40.0, min(150.0, float(weight_kg)))
    bmr = round(10 * w + 6.25 * height_cm - 5 * age + 5)
    
    is_high_uric = (uric_acid_umol_l is not None and uric_acid_umol_l >= 420.0)

    d_type = day_type.lower()
    if d_type in ["rest", "recovery", "active_recovery", "rest day / active recovery day"] or (d_type not in ["workout", "hard workout day", "carbo_loading"] and active_calories_garmin <= 300):
        # Rest / Recovery Day: 1.5 - 1.6 g/kg protein, 3.5 - 4.0 g/kg carbs, 45-55g fat
        protein_multiplier = 1.55
        carb_multiplier = 3.75  # 3.5 - 4.0 g/kg
        
        target_p = round(protein_multiplier * w, 1)
        target_c = round(carb_multiplier * w, 1)
        target_f = 50.0  # 45g - 55g fat
        
        # Calculate exact total calories from macros (P*4 + C*4 + F*9)
        target_cal = round(calculate_calories_from_macros(target_p, target_c, target_f), 1)
        
        notes = (
            f"Rest/Recovery Day: Target Protein strictly 1.5-1.6g/kg ({target_p}g) "
            f"to protect kidneys & prevent purine accumulation (Uric Acid = {uric_acid_umol_l or 442} µmol/L). "
            f"Carbs: 3.5-4.0g/kg ({target_c}g) low GI complex carbs. Fat: {target_f}g. "
            f"Derived total calories: {target_cal} kcal (mathematically coherent via P*4 + C*4 + F*9)."
        )

    elif "carbo" in d_type:
        protein_multiplier = 1.55
        target_p = round(protein_multiplier * w, 1)
        target_c = round(8.0 * w, 1)  # 7.0 - 10.0g/kg
        target_f = 40.0
        target_cal = round(calculate_calories_from_macros(target_p, target_c, target_f), 1)
        notes = f"Carbo-Loading Day: Carbs ~{target_c}g (70% total calories), Protein: {target_p}g, Fat: {target_f}g. Total: {target_cal} kcal."

    else:
        # Workout / Active Day
        protein_multiplier = 1.8 if is_high_uric else 1.9
        target_p = round(protein_multiplier * w, 1)
        target_f = round(0.9 * w, 1)
        target_c = round(max(200.0, (bmr + max(active_calories_garmin, 450.0) + 500 - (target_p * 4 + target_f * 9)) / 4.0), 1)
        target_cal = round(calculate_calories_from_macros(target_p, target_c, target_f), 1)
        notes = f"Workout Day: Target Protein: {target_p}g (1.8-1.9g/kg), Carbs: {target_c}g, Fat: {target_f}g. Total: {target_cal} kcal."

    return {
        "target_calories": target_cal,
        "protein_g": target_p,
        "carb_g": target_c,
        "fat_g": target_f,
        "bmr": bmr,
        "clinical_notes": notes
    }


def verify_macro_integrity(dishes_description: str, stated_protein_g: float) -> Tuple[bool, float, str]:
    """
    Verify whether stated macro numbers for a dish are realistic vs verified nutrition data.
    E.g., 130g raw tofu + 150g rice + veg provides ~10.5g + 4g = ~14.5-17g protein, NOT 36.6g!

    Returns:
        (is_valid, realistic_protein_estimate, suggestion_if_hallucinated)
    """
    desc_lower = dishes_description.lower()
    
    if "tofu" in desc_lower and "rice" in desc_lower and stated_protein_g > 25.0:
        realistic_p = 17.0
        suggestion = (
            f"Stated protein ({stated_protein_g}g) is inflated. 130g raw tofu (~10.5g P) + 150g rice (~4g P) + veg "
            f"actually provides ~{realistic_p}g protein. Suggest adding 1 egg (+6.3g P) or 100g lean fish (+20g P) to hit protein target safely."
        )
        return False, realistic_p, suggestion

    if ("rau ngót" in desc_lower or "rau ngot" in desc_lower) and ("30g" in desc_lower or "thịt nạc" in desc_lower or "thit nac" in desc_lower or "pork" in desc_lower) and stated_protein_g > 8.5:
        realistic_p = 7.8
        suggestion = (
            f"Stated protein ({stated_protein_g}g) is inflated. Canh rau ngót với 30g thịt nạc (6.3g P) + 50g rau ngót (1.5g P) "
            f"actually provides ~{realistic_p}g protein, not {stated_protein_g}g."
        )
        return False, realistic_p, suggestion

    return True, stated_protein_g, ""


def verify_dish_atwater_integrity(item_name: str, item_p: float, item_c: float, item_f: float, item_cal: float) -> Tuple[bool, str]:
    """
    Assert that for every individual dish: abs(item_cal - (item_p*4 + item_c*4 + item_f*9)) <= 5.0.
    Disallow inflating a single low-carb fruit (e.g. 100g fresh orange) to > 15g carbs.
    """
    calc_cal = (float(item_p) * 4.0) + (float(item_c) * 4.0) + (float(item_f) * 9.0)
    diff = abs(float(item_cal) - calc_cal)
    
    name_lower = item_name.lower()
    if ("cam" in name_lower or "orange" in name_lower) and float(item_c) > 15.0:
        return (
            False,
            f"Lỗi Carbohydrate cam tươi: Món '{item_name}' khai báo {item_c}g Carb vượt quá giới hạn hoa quả tươi (< 15g/100g cam tươi = 9.5g C, ~47 kcal). Cần phân bổ Carb còn thiếu vào tinh bột sạch (cơm, yến mạch, bánh mì)."
        )
        
    if diff > 5.0:
        return (
            False,
            f"Lỗi Atwater Math: Món '{item_name}' khai báo {item_cal} kcal nhưng tổng macros ({item_p}g P * 4 + {item_c}g C * 4 + {item_f}g F * 9) tính ra {round(calc_cal, 1)} kcal (lệch {round(diff, 1)} kcal > 5.0 kcal)."
        )

    return True, "Dish macro Atwater integrity verified."


def validate_dinner_protein_cap(dinner_protein_g: float, day_type: str = "rest") -> Tuple[bool, str]:
    """
    Restrict dinner protein to a maximum of 30.0g for Rest/Taper days to protect overnight renal filtration
    and sleep HRV for an athlete with high Uric Acid (442 µmol/L).
    Shift excess protein quota to afternoon snack (e.g., Greek yogurt Chobani).
    """
    d_type = day_type.lower()
    is_rest_or_taper = any(k in d_type for k in ["rest", "taper", "recovery", "easy_run"])
    if is_rest_or_taper and dinner_protein_g > 30.0:
        return (
            False,
            f"CẢNH BÁO GIỚI HẠN PROTEIN BỮA TỐI: Bữa tối ({dinner_protein_g}g Protein) vượt trần 30.0g cho ngày Rest/Taper "
            f"(bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L). Hãy hạ protein bữa tối <= 30.0g và chuyển phần protein thừa sang bữa phụ chiều (ví dụ: 1 hũ sữa chua Hy Lạp Chobani 15g P)."
        )
    return True, "Hàm lượng protein bữa tối nằm trong giới hạn an toàn (<= 30.0g)."


def validate_menu_protein_cap(
    total_protein_g: float,
    weight_kg: float = 65.6,
    day_type: str = "rest"
) -> Tuple[bool, str]:
    """
    Validate that total menu protein does not exceed protein target cap on Rest Days.
    Target cap on Rest Day is 1.55 * weight_kg (+/- 3g tolerance).
    E.g. For ~65.6kg, max allowable protein is 105.0g. Overruns like 116.4g violate Uric Acid constraints.
    """
    d_type = day_type.lower()
    if d_type in ["rest", "recovery", "active_recovery", "rest day / active recovery day"]:
        max_p = round(1.55 * float(weight_kg) + 3.0, 1)
        if total_protein_g > max_p:
            return (
                False,
                f"CẢNH BÁO VƯỢT TRẦN PROTEIN: Tổng protein thực đơn ({total_protein_g}g) vượt trần khuyến nghị {max_p}g/ngày nghỉ "
                f"(1.55g/kg bảo vệ thận & Uric Acid 442 µmol/L). Hãy hạ bớt khẩu phần (ví dụ dùng 100g ức gà thay vì 150g)."
            )
    return True, "Hàm lượng protein nằm trong giới hạn cho phép."



def validate_menu_starch_duplication(dishes_list: List[str]) -> Tuple[bool, str]:
    """
    Ensure no duplicate starch ingredients are prescribed in the same meal.
    For example: Forbidding multiple lines of 'khoai lang' in dinner (e.g. 250g + 100g = 350g).
    Caps sweet potato at max 150g-200g per meal.
    """
    lower_dishes = [d.lower() for d in dishes_list]
    khoai_lang_count = sum(1 for d in lower_dishes if "khoai lang" in d)
    
    if khoai_lang_count > 1:
        return (
            False,
            "Lỗi lặp lại nguyên liệu: Phát hiện lặp lại món khoai lang trong cùng một bữa ăn. "
            "Chỉ được dùng 1 phần khoai lang tối đa 150g-200g cho bữa tối để tránh đầy hơi, chướng bụng ban đêm."
        )
    
    # Check for excessive sweet potato quantity (> 200g)
    for dish in lower_dishes:
        if "khoai lang" in dish:
            import re
            m = re.search(r"(\d+)\s*g", dish)
            if m and int(m.group(1)) > 200:
                return (
                    False,
                    f"Giới hạn tinh bột tối: {m.group(1)}g khoai lang vượt ngưỡng khuyến nghị (max 150g-200g). "
                    "Hãy giảm xuống 150g-200g hoặc thay bằng cơm trắng dễ tiêu hóa."
                )

    return True, "Menu hợp lệ, không bị lặp tinh bột."


def validate_bedtime_snack_composition(snack_description: str, fat_g: float) -> Tuple[bool, str]:
    """
    Enforce bedtime snack safety:
    - Bedtime snacks scheduled within 2 hours of bedtime (e.g. 20:00 for 21:30 bedtime) MUST be virtually fat-free (< 3g fat) and easily absorbable (e.g. 1/2 banana or 100ml warm skimmed milk).
    - STRICTLY NO nuts/almonds/high-fat items (> 3g fat) within 2 hours of bedtime to prevent delayed gastric emptying and sleep disruption.
    """
    snack_lower = snack_description.lower()
    
    forbidden_items = ["hạnh nhân", "hạt", "almond", "nuts", "lạc", "đậu phụng", "bơ"]
    contains_nuts = any(item in snack_lower for item in forbidden_items)
    
    if contains_nuts or fat_g > 3.0:
        return (
            False,
            f"CẢNH BÁO BỮA PHỤ ĐÊM: Bữa phụ lúc 20:00 có chứa hạt/chất béo ({fat_g}g fat). "
            "Nghiêm cấm ăn hạt hạnh nhân/chất béo trong vòng 2 tiếng trước giờ ngủ (21:30). "
            "Bữa phụ trước đi ngủ chỉ được dùng thực phẩm hầu như không chứa chất béo (<3g fat) như 1/2 quả chuối chín hoặc 100ml sữa tách béo ấm, "
            "hoặc gộp tinh bột vào bữa tối 19:00 và bỏ hẳn bữa phụ 20:00 để giữ dạ dày rỗng 2.5-3.0 tiếng trước khi ngủ."
        )
        
    return True, "Bữa phụ đêm hợp lệ (hầu như không chứa chất béo, dễ tiêu hóa)."
