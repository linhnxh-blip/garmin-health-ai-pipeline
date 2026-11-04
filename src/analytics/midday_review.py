"""
Garmin Health AI Pipeline - Midday Review Clinical Nutrition & Exercise Logic.
Clinical Sports Medicine module for midday physiological assessment and remaining macro allocation.
Enforces realistic macro caps, natural fat floors, purine load monitoring, and anti-carb-dumping guards.
"""

import re
from typing import Dict, Any, Optional, List, Tuple, Union


class MacroTarget:
    """Container for macro nutrient targets/intakes with attribute-based access."""
    def __init__(
        self,
        protein: float = 0.0,
        carb: float = 0.0,
        fat: float = 0.0,
        calories: float = 0.0
    ):
        self.protein = float(protein or 0.0)
        self.carb = float(carb or 0.0)
        self.fat = float(fat or 0.0)
        self.calories = float(calories or 0.0)

    def __repr__(self) -> str:
        return f"MacroTarget(protein={self.protein}g, carb={self.carb}g, fat={self.fat}g, calories={self.calories}kcal)"


def _to_macro_obj(val: Any) -> MacroTarget:
    """Coerce dictionary or existing object into MacroTarget with .protein, .carb, .fat."""
    if isinstance(val, MacroTarget):
        return val
    if isinstance(val, dict):
        p = val.get("protein", val.get("protein_g", val.get("total_protein", 0.0)))
        c = val.get("carb", val.get("carb_g", val.get("total_carbs", 0.0)))
        f = val.get("fat", val.get("fat_g", val.get("total_fat", 0.0)))
        cal = val.get("calories", val.get("total_calories", val.get("target_calories", 0.0)))
        return MacroTarget(protein=p, carb=c, fat=f, calories=cal)

    p = getattr(val, "protein", getattr(val, "protein_g", getattr(val, "total_protein", 0.0)))
    c = getattr(val, "carb", getattr(val, "carb_g", getattr(val, "total_carbs", 0.0)))
    f = getattr(val, "fat", getattr(val, "fat_g", getattr(val, "total_fat", 0.0)))
    cal = getattr(val, "calories", getattr(val, "total_calories", getattr(val, "target_calories", 0.0)))
    return MacroTarget(protein=p, carb=c, fat=f, calories=cal)


def calculate_evening_targets(
    daily_target: Union[MacroTarget, Dict[str, Any], Any],
    logged_intake: Union[MacroTarget, Dict[str, Any], Any],
    uric_acid_level: float = 442.0
) -> Tuple[float, float, str]:
    """
    Clinical Guards for Midday Remaining Macro Allocation:
    
    1. Evening Protein Cap:
       Stricter (min(rem_p, 15.0)) if logged intake >= 80g; else min(rem_p, 28.0).
    2. Realistic Evening Carb Cap:
       min(rem_c, 70.0) (~1.5 small bowls of rice ~60-70g C) to prevent Carb-Dumping Syndrome.
    3. Realistic Fat Floor:
       Any meal with plant/animal protein has 4-7g natural lipids.
       fat_status = 'EXCEEDED' if rem_f <= 0 else 'AVAILABLE'.
    """
    dt = _to_macro_obj(daily_target)
    li = _to_macro_obj(logged_intake)

    rem_p = round(max(0.0, dt.protein - li.protein), 1)
    rem_c = round(max(0.0, dt.carb - li.carb), 1)
    rem_f = round(dt.fat - li.fat, 1)

    # Clinical Guard 1: Evening Protein Cap (Stricter if lunchtime was a protein overload)
    if li.protein >= 80.0:
        dinner_protein_target = round(min(rem_p, 15.0), 1)  # Absolute light dinner
    else:
        dinner_protein_target = round(min(rem_p, 28.0), 1)

    # Clinical Guard 2: Realistic Evening Carb Cap (No Carb Dumping)
    dinner_carb_target = round(min(rem_c, 70.0), 1)  # Max ~1.5 small bowls of rice (~60-70g C)

    # Clinical Guard 3: Realistic Fat Floor
    # Any meal with plant or animal protein will have at least 4-7g natural fat
    fat_status = "EXCEEDED" if rem_f <= 0 else "AVAILABLE"

    return dinner_protein_target, dinner_carb_target, fat_status


def detect_high_purine_lunch(
    dishes: List[str],
    protein_g: float,
    uric_acid_level: float = 442.0
) -> Dict[str, Any]:
    """
    Evaluate purine load from lunch dishes and protein volume.
    Issues clinical hydration and urine alkalinization protocol if purine overload is detected.
    """
    dishes_text = " ".join(dishes).lower() if isinstance(dishes, list) else str(dishes).lower()
    
    # Categories of purine sources
    purine_categories = {
        "red_meat": ["bò", "thịt bò", "dê", "thịt dê", "cừu"],
        "pork_ribs": ["sườn", "sườn xào", "sườn nướng", "thịt heo", "thịt lợn", "thịt đỏ", "ba chỉ"],
        "rich_seafood": ["cá hồi", "salmon", "tôm", "cua", "mực", "nghêu", "sò", "ốc", "hải sản", "cá thu", "cá ngừ", "cá trích"],
        "viscera": ["lòng", "gan", "dạ trường", "phủ tạng", "dồi"]
    }

    detected_sources = []
    for cat_name, keywords in purine_categories.items():
        matched = [kw for kw in keywords if kw in dishes_text]
        if matched:
            detected_sources.append((cat_name, matched[0]))

    # Triggers:
    # 1. Multiple purine categories (e.g. beef + ribs + salmon)
    # 2. Single major high-purine item with high lunch protein (>= 45g)
    # 3. Lunch protein >= 50g when uric acid level >= 420 umol/L
    is_multi_purine = len(detected_sources) >= 2
    is_protein_overload = protein_g >= 50.0 and uric_acid_level >= 420.0
    is_high_purine = is_multi_purine or is_protein_overload

    matched_names = [src[1] for src in detected_sources]

    if is_high_purine:
        warning_msg = (
            f"Bữa trưa chứa hàm lượng Purine cao (ghi nhận: {', '.join(matched_names) if matched_names else 'đạm tập trung cao'} "
            f"với {protein_g:.1f}g Protein). Với Acid Uric nền {uric_acid_level:.0f} µmol/L, tải purine dồn dập "
            f"làm tăng nồng độ urate huyết thanh, tiềm ẩn nguy cơ viêm/kết tinh tinh thể urate tại gân Achilles trái "
            f"và tạo áp lực lọc lên cầu thận."
        )
        protocol = (
            "💧 **Giao thức Kiềm hóa & Thải trừ Cấp (Alkaline Hydration Protocol):**\n"
            "  * Uống ngay 1 cốc lớn (350 - 400ml) nước khoáng kiềm pH 8.5 - 9.0 (Fujiwa) đầu giờ chiều.\n"
            "  * Bổ sung rải đều chiều/tối tối thiểu 1.5L - 2.0L nước (tổng cả ngày đạt >= 3.0L) để nâng pH nước tiểu lên > 6.5, tăng độ hòa tan acid uric.\n"
            "  * Bữa tối TUYỆT ĐỐI CẤM thịt đỏ, sườn heo, cá béo và hải sản vỏ cứng."
        )
    else:
        warning_msg = ""
        protocol = ""

    return {
        "is_high_purine": is_high_purine,
        "detected_sources": matched_names,
        "warning_message": warning_msg,
        "counter_measure_protocol": protocol
    }


def strip_stale_midday_footer(text: str) -> str:
    """Remove contradictory hardcoded morning framework notices from Midday reports."""
    if not text:
        return ""
    
    # Strip: 💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng...
    pattern = r'[\r\n]+\s*(?:[-*•]\s*)?💡?\s*Lưu ý:\s*Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng\.[^\n]*\n?'
    cleaned = re.sub(pattern, '\n', text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def calculate_midday_nutrition_plan(
    daily_target: Union[MacroTarget, Dict[str, Any]],
    logged_intake: Union[MacroTarget, Dict[str, Any]],
    nut_logs: Optional[List[Dict[str, Any]]] = None,
    uric_acid_level: float = 442.0
) -> Dict[str, Any]:
    """
    Comprehensive Midday Nutrition & Remaining Macro Plan.
    Enforces all clinical sports medicine guards and prepares clear output data.
    """
    dt = _to_macro_obj(daily_target)
    li = _to_macro_obj(logged_intake)

    rem_p = max(0.0, round(dt.protein - li.protein, 1))
    rem_c = max(0.0, round(dt.carb - li.carb, 1))
    rem_f = round(dt.fat - li.fat, 1)

    dinner_p_target, dinner_c_target, fat_status = calculate_evening_targets(
        dt, li, uric_acid_level=uric_acid_level
    )

    # Afternoon Snack allocation
    snack_p = round(max(0.0, rem_p - dinner_p_target), 1)
    if rem_c > 30.0:
        snack_c = min(45.0, round(rem_c * 0.25, 1))
    else:
        snack_c = round(rem_c, 1)
    snack_f = 0.0
    snack_cal = round(snack_p * 4.0 + snack_c * 4.0 + snack_f * 9.0, 1)

    # Dinner allocation (Realistic Natural Fat Floor: ~5-6g from tofu/lean protein)
    dinner_p = dinner_p_target
    dinner_c = dinner_c_target
    dinner_f_natural = 5.5  # 1 bìa đậu non (~4.8g) + protein nạc (~0.7g)
    dinner_cal = round(dinner_p * 4.0 + dinner_c * 4.0 + dinner_f_natural * 9.0, 1)

    # Unconsumed daytime carb
    unconsumed_c = max(0.0, round(rem_c - (snack_c + dinner_c), 1))

    # Evaluate lunch purine load from logs
    lunch_log = None
    if nut_logs:
        for log in nut_logs:
            m_type = str(log.get("meal_type") or "").lower()
            ts = str(log.get("timestamp") or "")
            if any(kw in m_type for kw in ["trưa", "lunch"]) or ("11:" in ts or "12:" in ts or "13:" in ts):
                lunch_log = log
        if not lunch_log and len(nut_logs) > 1:
            lunch_log = nut_logs[-1]

    lunch_dishes = lunch_log.get("dishes", []) if lunch_log else []
    lunch_protein = float(lunch_log.get("protein_g", 0.0) if lunch_log else 0.0)
    purine_eval = detect_high_purine_lunch(lunch_dishes, lunch_protein, uric_acid_level)

    # Fat narrative text
    if fat_status == "EXCEEDED":
        fat_narrative = (
            f"0.0g (Đã vượt +{abs(rem_f):.1f}g Fat hạn mức ngày). "
            f"Chất béo trong ngày đã nạp đủ, bữa chiều & tối tối ưu chế biến hấp/luộc không thêm dầu mỡ. "
            f"Lưu ý lâm sàng: Các nguồn đạm thanh đạm (đậu phụ non, trứng/ức gà nạc) vẫn chứa chất béo nội tại tự nhiên "
            f"(~5-6g Fat), không thể triệt tiêu phi sinh học về 0.0g."
        )
    else:
        fat_narrative = f"{rem_f:.1f}g Fat (Còn khả dụng trong ngày, có thể thêm 1 thìa nhỏ dầu mè/dầu olive trộn canh rau)."

    return {
        "daily_target": dt,
        "logged_intake": li,
        "remaining_p": rem_p,
        "remaining_c": rem_c,
        "remaining_f": rem_f,
        "fat_status": fat_status,
        "fat_narrative": fat_narrative,
        "dinner_protein_target": dinner_p,
        "dinner_carb_target": dinner_c,
        "dinner_natural_fat": dinner_f_natural,
        "dinner_calories": dinner_cal,
        "snack_protein": snack_p,
        "snack_carb": snack_c,
        "snack_fat": snack_f,
        "snack_calories": snack_cal,
        "unconsumed_carb": unconsumed_c,
        "purine_evaluation": purine_eval
    }
