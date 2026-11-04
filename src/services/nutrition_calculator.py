"""
Clinical Nutrition Calculator & Verified Macro Reference Table.
Implements sports medicine guidelines for endurance athletes with biochemical considerations (e.g., Uric Acid).
"""

from typing import Dict, Any, Tuple, Optional, List, Union
from src.analytics.constants import OMRON_TARGET_BENCHMARKS

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
    weight_kg: Optional[Union[float, str]] = 65.3,
    day_type: str = "rest",
    uric_acid_umol_l: Optional[float] = None,
    height_cm: float = 168.0,
    age: int = 44,
    active_calories_garmin: float = 0.0,
    days_to_race: Optional[int] = None,
    days_since_race: Optional[int] = None,
    target_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate daily macro and calorie targets based on day type, target date, and clinical flags.
    Enforces single source of truth for daily targets across reporting and meal logging.
    """
    # Handle case where target_date is passed as first positional argument
    if isinstance(weight_kg, str) and not target_date:
        target_date = weight_kg
        weight_kg = 65.3

    if target_date:
        from src.analytics.prompt_engine import get_race_context
        race_ctx = get_race_context(target_date)
        if days_to_race is None:
            days_to_race = race_ctx.get("days_to_race")
        if days_since_race is None:
            days_since_race = race_ctx.get("days_since_race")
        phase_str = race_ctx.get("phase", "")
        if day_type == "rest" and phase_str:
            if phase_str == "POST_RACE_ACUTE":
                day_type = "post_race_acute"
            elif phase_str == "POST_RACE_RECOVERY":
                day_type = "post_race_recovery"
            elif phase_str == "TAPERING":
                day_type = "tapering"

    w_val = 65.3 if weight_kg is None else float(weight_kg)
    w = max(40.0, min(150.0, w_val))
    bmr = round(10 * w + 6.25 * height_cm - 5 * age + 5)
    
    is_high_uric = (uric_acid_umol_l is not None and uric_acid_umol_l >= 420.0)
    MAX_DAILY_PROTEIN_HIGH_URIC = 85.0  # Clinical cap for Uric Acid 442 µmol/L in standard training

    from src.analytics.nutrition_engine import calculate_daily_macros
    from src.analytics.periodization import detect_current_phase, TrainingPhase

    d_type = (day_type or "").lower()

    if "acute" in d_type or (days_since_race is not None and 1 <= days_since_race <= 7):
        p_enum = TrainingPhase.POST_RACE_ACUTE
    elif "post_race" in d_type or "recovery_post" in d_type or (days_since_race is not None and 8 <= days_since_race <= 21):
        p_enum = TrainingPhase.POST_RACE_RECOVERY
    elif "carbo" in d_type or "taper" in d_type or (days_to_race is not None and 1 <= days_to_race <= 14):
        p_enum = TrainingPhase.TAPERING
    elif "workout" in d_type or active_calories_garmin > 300:
        p_enum = TrainingPhase.PEAK_TRAINING
    else:
        p_enum = TrainingPhase.MAINTENANCE

    m_res = calculate_daily_macros(
        weight_kg=w,
        phase=p_enum,
        uric_acid_level=uric_acid_umol_l or 442.0,
        active_calories_garmin=active_calories_garmin,
        days_since_race=days_since_race,
        days_to_race=days_to_race,
        day_type=day_type
    )

    return {
        "target_calories": m_res["target_calories"],
        "protein_g": m_res["protein_g"],
        "carb_g": m_res["carb_g"],
        "fat_g": m_res["fat_g"],
        "dinner_protein_cap": m_res["dinner_protein_cap"],
        "bmr": bmr,
        "clinical_notes": f"Deterministic Engine ({p_enum.value}): Protein {m_res['protein_g']}g, Carb {m_res['carb_g']}g, Fat {m_res['fat_g']}g -> Total Calories {m_res['target_calories']} kcal (Atwater 4-4-9)."
    }


def verify_macro_integrity(
    dishes_description: str,
    stated_protein_g: float,
    stated_carb_g: Optional[float] = None
) -> Tuple[bool, float, str]:
    """
    Verify whether stated macro numbers for a dish are realistic vs verified nutrition data.
    E.g., 130g raw tofu + 150g rice + veg provides ~10.5g + 4g = ~14.5-17g protein, NOT 36.6g!
    E.g., 1 bowl of cooked white rice (~130-150g) inherently provides ~35-40g Carbs, NOT 10.7g!

    Returns:
        (is_valid, realistic_protein_estimate, suggestion_if_hallucinated)
    """
    desc_lower = dishes_description.lower()
    
    # Check for white rice carb under-reporting / fabrication (< 25g Carb per bowl)
    if stated_carb_g is not None and ("cơm" in desc_lower or "rice" in desc_lower) and ("bát" in desc_lower or "chén" in desc_lower or "150g" in desc_lower or "130g" in desc_lower):
        if stated_carb_g < 25.0:
            return (
                False,
                stated_protein_g,
                f"Lỗi bịa đặt Carbohydrate: Món cơm trắng ('{dishes_description}') khai báo {stated_carb_g}g Carb là phi sinh học. 1 bát con cơm trắng (130-150g) có ít nhất ~35-41g Carb. Tuyệt đối không hạ khống Carb của cơm để ép khớp quota."
            )

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


def verify_single_dish_integrity(
    dish_name: str,
    *args,
    item_p: float = 0.0,
    item_c: float = 0.0,
    item_f: float = 0.0,
    item_cal: float = 0.0,
    fat_g: Optional[float] = None,
    stated_fat_g: Optional[float] = None,
    stated_protein_g: Optional[float] = None,
    stated_carb_g: Optional[float] = None,
    stated_calories: Optional[float] = None,
    **kwargs
) -> Tuple[bool, str]:
    """
    Assert realistic macronutrient upper bounds and Atwater consistency for individual dishes.
    - Low-fat dishes (e.g. oil-free chicken breast 70g + soft tofu 100g + boiled vegetables + rice)
      MUST NOT exceed 10.0g Fat without an explicit fat source (e.g. added olive oil).
    - Prohibits inflating Fat to match arbitrary calorie goals.
    - If calories are lacking, clean healthy fats must be explicitly specified
      (e.g. 'thêm 1 thìa cà phê 5ml dầu olive trộn canh/rau' = 45 kcal / 5g fat).
    """
    # Parse parameters flexibly to support positional or keyword invocations
    if len(args) == 1:
        f_val = float(args[0])
        p_val = float(item_p)
        c_val = float(item_c)
        cal_val = float(item_cal)
    elif len(args) == 4:
        p_val, c_val, f_val, cal_val = float(args[0]), float(args[1]), float(args[2]), float(args[3])
    else:
        p_val = float(stated_protein_g if stated_protein_g is not None else item_p)
        c_val = float(stated_carb_g if stated_carb_g is not None else item_c)
        cal_val = float(stated_calories if stated_calories is not None else item_cal)
        if stated_fat_g is not None:
            f_val = float(stated_fat_g)
        elif fat_g is not None:
            f_val = float(fat_g)
        elif item_f != 0.0:
            f_val = float(item_f)
        elif "fat" in kwargs:
            f_val = float(kwargs["fat"])
        elif "f" in kwargs:
            f_val = float(kwargs["f"])
        elif "stated_fat" in kwargs:
            f_val = float(kwargs["stated_fat"])
        else:
            f_val = float(item_f)

    name_lower = dish_name.lower()

    # 1. Check for boiled / oil-free chicken breast + tofu + boiled veg fat upper bound
    has_tofu = any(k in name_lower for k in ["đậu phụ", "tofu", "dau phu"])
    has_chicken = any(k in name_lower for k in ["ức gà", "uc ga", "chicken", "thịt thăn", "thit than"])

    explicit_fat_sources = [
        "dầu olive", "dau olive", "olive oil", "dầu mè", "dau me", "dầu ăn", "dau an",
        "dầu thực vật", "dau thuc vat", "dầu hạt", "mỡ", "mo", "thịt ba chỉ", "thịt mỡ",
        "bơ", "butter", "lạc", "đậu phộng", "dau phong", "hạt điều", "hạnh nhân",
        "chiên ngập dầu", "rán", "sốt dầu"
    ]
    has_explicit_fat = any(src in name_lower for src in explicit_fat_sources)

    # Low-fat chicken breast & tofu dish check (e.g. oil_free_chicken_breast_70g + soft_tofu_100g + boiled_veg)
    if (has_tofu and has_chicken) or ("chicken_breast" in name_lower and "tofu" in name_lower):
        if not has_explicit_fat and f_val > 10.0:
            return (
                False,
                f"Lỗi thổi phồng chất béo (Fat Inflation): Món ăn '{dish_name}' khai báo {f_val}g Fat vượt quá trần sinh học 10.0g Fat cho món luộc/áp chảo không dầu. "
                "100g đậu phụ non (~4.8g Fat) + 70g ức gà không dầu (~2.5g Fat) + canh rau luộc nước trong chỉ chứa tối đa ~6-8g Fat (không vượt quá 10.0g Fat). "
                "Tuyệt đối cấm tự ý gán thêm mỡ ảo vào món thanh đạm để ép khớp chỉ tiêu Atwater. "
                "Nếu thiếu năng lượng/Fat, phải bổ sung nguồn chất béo sạch tường minh (ví dụ: 'thêm 1 thìa cà phê 5ml dầu olive trộn canh/rau' = 45 kcal / 5g fat)."
            )

    # 2. Fruit carb limit check
    if ("cam" in name_lower or "orange" in name_lower) and float(c_val) > 15.0:
        return (
            False,
            f"Lỗi Carbohydrate cam tươi: Món '{dish_name}' khai báo {c_val}g Carb vượt quá giới hạn hoa quả tươi (< 15g/100g cam tươi = 9.5g C, ~47 kcal). Cần phân bổ Carb còn thiếu vào tinh bột sạch (cơm, yến mạch, bánh mì)."
        )

    # 3. Rice carb lower bound check
    if ("cơm" in name_lower or "rice" in name_lower) and any(b in name_lower for b in ["bát", "chén", "bowl", "150g", "130g", "140g"]) and 0.0 < float(c_val) < 25.0:
        return (
            False,
            f"Lỗi Carbohydrate cơm trắng: Món '{dish_name}' khai báo {c_val}g Carb là phi sinh học (hallucination). "
            "1 bát con cơm trắng (130-150g) chứa ~35-41g Carb. Không được hạ khống Carb của cơm trắng để ép khớp quota."
        )

    # 4. Atwater mathematical consistency check (if calories provided)
    if cal_val > 0.0 and (p_val > 0.0 or c_val > 0.0 or f_val > 0.0):
        calc_cal = (p_val * 4.0) + (c_val * 4.0) + (f_val * 9.0)
        diff = abs(cal_val - calc_cal)
        if diff > 5.0:
            return (
                False,
                f"Lỗi Atwater Math: Món '{dish_name}' khai báo {cal_val} kcal nhưng tổng macros ({p_val}g P * 4 + {c_val}g C * 4 + {f_val}g F * 9) tính ra {round(calc_cal, 1)} kcal (lệch {round(diff, 1)} kcal > 5.0 kcal)."
            )

    return True, "Dish macro and ingredient integrity verified."


def verify_dish_atwater_integrity(item_name: str, item_p: float, item_c: float, item_f: float, item_cal: float) -> Tuple[bool, str]:
    """
    Assert that for every individual dish: abs(item_cal - (item_p*4 + item_c*4 + item_f*9)) <= 5.0.
    Disallow inflating a single low-carb fruit (e.g. 100g fresh orange) to > 15g carbs.
    Disallow deflating cooked rice bowl carbs to < 25g.
    Disallow inflating Fat in boiled/oil-free dishes to > 10.0g.
    """
    return verify_single_dish_integrity(
        dish_name=item_name,
        item_p=item_p,
        item_c=item_c,
        item_f=item_f,
        item_cal=item_cal
    )


def validate_dinner_purine_safety(dishes_description: str, uric_acid_umol_l: float = 442.0) -> Tuple[bool, str]:
    """
    Enforce low-purine dinner protein selection for athletes with elevated uric acid (>= 420 µmol/L).
    Nghiêm cấm kê đơn tôm, hải sản, cua, sò, ốc, mực, thịt đỏ cho bữa tối để tránh kết tinh urate ban đêm.
    """
    if uric_acid_umol_l < 420.0:
        return True, "Uric acid mức bình thường."

    desc_lower = dishes_description.lower()
    high_purine_items = ["tôm", "shrimp", "hải sản", "seafood", "cua", "crab", "sò", "ốc", "mực", "squid", "thịt bò", "beef", "thịt dê"]
    found_items = [item for item in high_purine_items if item in desc_lower]
    if found_items:
        return (
            False,
            f"CẢNH BÁO NGUY CƠ ACID URIC BỮA TỐI: Món ăn bữa tối có chứa '{', '.join(found_items)}' - nguồn thực phẩm giàu purin. "
            f"Với nồng độ Acid Uric {uric_acid_umol_l} µmol/L, bữa tối TUYỆT ĐỐI KHÔNG dùng tôm/hải sản hay thịt đỏ để tránh nguy cơ kết tinh tinh thể Urate khi ngủ. "
            f"Bắt buộc thay thế bằng đạm thanh đạm ít purin: đậu phụ non, ức gà nạc không da, thịt nạc thăn băm nhỏ hoặc trứng gà luộc."
        )
    return True, "Thực đơn bữa tối an toàn cho Acid Uric."


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
    Validate that total menu protein does not exceed protein target cap (max 85.0g daily for Uric Acid 442 µmol/L).
    """
    max_p = 85.0
    if total_protein_g > max_p:
        return (
            False,
            f"CẢNH BÁO VƯỢT TRẦN PROTEIN: Tổng protein thực đơn ({total_protein_g}g) vượt trần 85.0g/ngày "
            f"(bảo vệ thận & Uric Acid 442 µmol/L). Hãy hạ bớt khẩu phần (ví dụ dùng 100g ức gà/cá/thịt thay vì 150g)."
        )
    return True, "Hàm lượng protein nằm trong giới hạn cho phép (<= 85.0g)."



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
