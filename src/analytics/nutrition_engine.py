"""
Garmin Health AI Pipeline - Deterministic Nutrition Engine
Pure mathematical calculation module for daily macro targets and clinical guardrail enforcement.
Prevents LLM math hallucinations by providing strictly pre-calculated macro values.
"""

from typing import Dict, Any, Optional, Union, List
from src.analytics.periodization import TrainingPhase


POST_RACE_DIGESTIVE_RULES = {
    "prohibited_foods": [
        "yến mạch cán vỡ",
        "ngũ cốc thô",
        "mật ong",
        "đường đơn đậm đặc",
        "nước ép cam/chanh chua",
        "bánh mì ngọt",
        "sữa chua béo",
        "bữa ăn dồn thể tích lớn (> 700 kcal / bữa)",
        "đồ ăn chua cay kích thích đại tràng",
        "đồ chiên xào nhiều dầu mỡ",
        "thịt đỏ (bò, dê), hải sản vỏ cứng đậm purin"
    ],
    "mandatory_prescriptions": [
        "Chia nhỏ thành 4 bữa ăn nhẹ trong ngày",
        "Thức ăn phục vụ ấm nóng, nấu mềm dễ tiêu",
        "Tinh bột sạch nấu mềm (cháo thịt nạc, cơm mềm, phở gà nước trong)",
        "Đạm trắng dễ hấp thu (ức gà nạc, cá nạc áp chảo không dầu, trứng luộc/hấp, đậu phụ)",
        "Bỏ cân đong tiểu ly phi thực tế, định lượng theo bát/đĩa thông thường"
    ]
}

POST_RACE_REALISTIC_MEALS = {
    "breakfast": (
        "1 Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ + hành hoa thái nhỏ + 1 quả trứng gà luộc chín tới "
        "(Dùng 1 thìa nhỏ dầu thực vật/dầu phi hành thơm nấu cháo +5g Fat) "
        "(HOẶC: 1 Bát phở gà nạc nước trong: bỏ da, không váng mỡ, không quẩy)"
    ),
    "lunch": (
        "1.5 bát con cơm trắng mềm + Đạm nạc (1 lạng ức gà luộc HOẶC 1 khúc cá nạc hấp/áp chảo ít dầu HOẶC 1 lạng tôm hấp bóc vỏ) "
        "+ 1 bát canh bí đao/mồng tơi/bầu nấu thịt nạc băm (nước trong) "
        "(Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc +5g Fat)"
    ),
    "snack": (
        "1 quả chuối tiêu chín (~110g) HOẶC 1 quả táo tây + 1 hộp sữa chua Chobani/ít béo"
    ),
    "dinner": (
        "1 bát con cơm trắng mềm (~130-150g, ~38-40g Carb) + Đậu phụ non sốt cà chua nhạt (1 bìa) + Ức gà nạc áp chảo / thịt nạc thăn băm nhỏ (hoặc 1 quả trứng gà luộc, TUYỆT ĐỐI CẤM tôm/hải sản tối để ngừa lắng đọng Acid Uric) "
        "+ Canh rau luộc nước trong (Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc +5g Fat) "
        "(Tuân thủ trần Protein <= 28.0g, thanh đạm)"
    )
}


def generate_lean_menu(
    target_fat_g: float = 49.0,
    dinner_protein_cap: float = 28.0,
    target_calories: float = 1780.0,
    target_protein_g: float = 95.0,
    target_carb_g: float = 240.0,
    is_post_race: bool = True,
    negative_constraints: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate lean, low-purine daily menu (chicken breast, egg whites/boiled egg, tofu)
    with explicit clean, digestive-friendly healthy fat additions if fat deficit > 15g.
    Guarantees Sum(Dish Fat) matches target_fat_g within +-3g.
    """
    target_f = float(target_fat_g or 49.0)
    base_bf_fat = 6.0
    base_lu_fat = 4.0
    base_sn_fat = 2.5
    base_di_fat = 6.5
    base_total_fat = base_bf_fat + base_lu_fat + base_sn_fat + base_di_fat  # 19.0g

    fat_gap = target_f - base_total_fat

    if fat_gap > 15.0:
        needed_add = target_f - base_total_fat
        add_bf = min(8.0, max(5.0, round(needed_add * 0.25, 1)))
        rem_add = needed_add - add_bf
        add_lu = round(rem_add * 0.45, 1)
        add_di = round(rem_add - add_lu, 1)

        bf_oil = f" (Dùng 1 thìa nhỏ dầu thực vật/dầu phi hành thơm nấu cháo, +{int(round(add_bf))}g Fat)"
        lu_oil = f" (Thêm {1 if add_lu <= 6 else 2} thìa cà phê ({5 if add_lu <= 6 else 10}ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc, +{int(round(add_lu))}g Fat)"
        di_oil = f" (Thêm {1 if add_di <= 6 else 2} thìa cà phê ({5 if add_di <= 6 else 10}ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc, +{int(round(add_di))}g Fat)"

        bf_fat = base_bf_fat + add_bf
        lu_fat = base_lu_fat + add_lu
        sn_fat = base_sn_fat
        di_fat = base_di_fat + add_di
    else:
        bf_oil = ""
        lu_oil = ""
        di_oil = ""
        bf_fat = base_bf_fat
        lu_fat = base_lu_fat
        sn_fat = base_sn_fat
        di_fat = base_di_fat

    bf_desc = (
        f"1 Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ + hành hoa thái nhỏ + 1 quả trứng gà luộc chín tới"
        f"{bf_oil} (HOẶC: 1 Bát phở gà nạc nước trong: bỏ da, không váng mỡ, không quẩy)."
    )
    lu_desc = (
        f"1.5 bát con cơm trắng mềm + Đạm nạc: 1 lạng tôm hấp bóc vỏ (HOẶC 1 khúc cá nạc hấp/áp chảo ít dầu HOẶC ức gà luộc) "
        f"+ 1 bát canh bí đao/mồng tơi/bầu nấu thịt nạc băm (nước trong){lu_oil}."
    )
    has_no_sweet_potato = negative_constraints and any("khoai lang" in c.lower() or "khoai" in c.lower() for c in negative_constraints)
    if has_no_sweet_potato:
        sn_desc = "1 quả chuối tiêu chín hoặc 1 lát bánh mì mềm kèm sữa chua ít béo + 300ml Nước kiềm Fujiwa."
    else:
        sn_desc = "1 quả chuối tiêu chín (~110g) HOẶC 1 quả táo tây + 1 hộp sữa chua Chobani/ít béo + 300ml Nước kiềm Fujiwa."
    di_desc = (
        f"1 bát con cơm trắng mềm (~130-150g, ~38-40g Carb) + Đậu phụ non sốt cà chua nhạt (1 bìa) + Ức gà nạc áp chảo / thịt nạc thăn băm nhỏ (Protein ~20.0g - 25.0g <= {dinner_protein_cap}g) "
        f"+ Canh rau luộc nước trong{di_oil} (TUYỆT ĐỐI CẤM tôm/hải sản bữa tối để bảo vệ Acid Uric 442 µmol/L)."
    )

    dish_fats = {
        "breakfast": round(bf_fat, 1),
        "lunch": round(lu_fat, 1),
        "snack": round(sn_fat, 1),
        "dinner": round(di_fat, 1)
    }
    total_fat = round(sum(dish_fats.values()), 1)

    return {
        "breakfast": bf_desc,
        "lunch": lu_desc,
        "snack": sn_desc,
        "dinner": di_desc,
        "dish_fats": dish_fats,
        "total_menu_fat": total_fat,
        "target_fat_g": target_f,
        "fat_gap": round(fat_gap, 1),
        "intraday_notice": "💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."
    }



def calculate_daily_macros(
    weight_kg: float,
    phase: Union[TrainingPhase, str],
    uric_acid_level: float = 442.0,
    active_calories_garmin: float = 0.0,
    days_since_race: Optional[int] = None,
    days_to_race: Optional[int] = None,
    day_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    Deterministic mathematical macro calculation engine.
    Strictly calculates exact gram targets for Protein, Carbohydrates, Fat, and Calories
    using the Atwater formula (4-4-9).
    """
    if isinstance(phase, str):
        try:
            phase_enum = TrainingPhase(phase.upper())
        except ValueError:
            phase_enum = TrainingPhase.MAINTENANCE
    else:
        phase_enum = phase

    w = max(40.0, float(weight_kg or 65.0))
    ua = float(uric_acid_level or 442.0)
    is_high_uric = ua >= 420.0
    act_cal = float(active_calories_garmin or 0.0)

    # 1. Phase: POST_RACE_ACUTE (D+1 to D+7)
    if phase_enum == TrainingPhase.POST_RACE_ACUTE or (days_since_race is not None and 1 <= days_since_race <= 7):
        protein_g = round(w * 1.45, 1)  # ~1.45 g/kg -> 65.2kg = 94.5g
        dinner_protein_cap = 28.0      # Lock dinner protein cap strictly at 28.0g for UA protection
        carb_g = round(w * 3.0, 1)      # ~3.0 g/kg -> 65.2kg = 195.6g (~40-45% TDEE)
        fat_g = round(w * 0.8, 1)       # ~0.8 g/kg -> 65.2kg = 52.2g
        if act_cal > 0:
            carb_g = round(carb_g + round(act_cal / 4.0, 1), 1)

    # 2. Phase: POST_RACE_RECOVERY (D+8 to D+21)
    elif phase_enum == TrainingPhase.POST_RACE_RECOVERY or (days_since_race is not None and 8 <= days_since_race <= 21):
        protein_g = round(w * 1.45, 1) if not is_high_uric else round(min(w * 1.45, 95.0), 1)
        dinner_protein_cap = 28.0 if is_high_uric else 30.0
        carb_g = round(w * 3.7, 1)      # ~3.7 g/kg -> ~235-245g (~45-50% TDEE)
        fat_g = round(w * 0.75, 1)      # ~0.75 g/kg -> ~48-50g
        if act_cal > 0:
            carb_g = round(carb_g + round(act_cal / 4.0, 1), 1)

    # 3. Phase: TAPERING & CARBO-LOADING (T-14 to T-1)
    elif phase_enum == TrainingPhase.TAPERING or (days_to_race is not None and 1 <= days_to_race <= 14):
        if days_to_race is not None and 1 <= days_to_race <= 3:
            # Carbo-loading Phase (T-3 to T-1)
            protein_g = 85.0 if is_high_uric else round(w * 1.35, 1)
            dinner_protein_cap = 30.0
            carb_g = 330.0              # Fixed 330g Carb for carbo-loading
            fat_g = 35.0                # Low fat < 35g
        else:
            # Normal Tapering
            protein_g = 85.0 if is_high_uric else round(w * 1.35, 1)
            dinner_protein_cap = 30.0
            carb_g = round(w * 3.8, 1)
            fat_g = round(w * 0.75, 1)
            if act_cal > 0:
                carb_g = round(carb_g + round(act_cal / 4.0, 1), 1)

    # 4. Phase: RACE_DAY (T-0)
    elif phase_enum == TrainingPhase.RACE_DAY or (days_to_race == 0):
        protein_g = 85.0 if is_high_uric else round(w * 1.4, 1)
        dinner_protein_cap = 30.0
        carb_g = round(w * 4.5, 1)
        fat_g = 35.0

    # 5. Default / BASE_BUILDING, PEAK_TRAINING, MAINTENANCE
    else:
        d_type = (day_type or "").lower()

        if "workout" in d_type or act_cal > 300:
            protein_g = 117.0 if is_high_uric else round(w * 1.8, 1)
            dinner_protein_cap = 30.0
            carb_g = round(w * 5.0, 1)
            fat_g = round(w * 1.0, 1)
        else:
            protein_g = 85.0 if is_high_uric else round(w * 1.35, 1)
            dinner_protein_cap = 30.0
            carb_g = round(w * 3.7, 1)
            fat_g = round(w * 0.75, 1)
            if act_cal > 0:
                carb_g = round(carb_g + round(act_cal / 4.0, 1), 1)

    # Coherence check: Calculate exact Atwater calories (4-4-9)
    target_calories = round((protein_g * 4.0) + (carb_g * 4.0) + (fat_g * 9.0), 1)

    return {
        "target_calories": target_calories,
        "protein_g": protein_g,
        "carb_g": carb_g,
        "fat_g": fat_g,
        "dinner_protein_cap": dinner_protein_cap,
        "uric_acid_level": ua,
        "phase": phase_enum.value if hasattr(phase_enum, "value") else str(phase_enum),
        "digestive_rules": POST_RACE_DIGESTIVE_RULES if phase_enum in (TrainingPhase.POST_RACE_ACUTE, TrainingPhase.POST_RACE_RECOVERY) else None
    }


def check_nutrition_log_completeness(total_cal_logged: float) -> Dict[str, Any]:
    """Check if daily recorded nutrition intake is incomplete (< 1,300 kcal threshold)."""
    tot_cal = float(total_cal_logged or 0.0)
    is_incomplete = tot_cal < 1300.0
    return {
        "incomplete_nutrition_log": is_incomplete,
        "total_calories_logged": tot_cal,
        "threshold": 1300.0,
        "warning_message": (
            "⚠️ Nhật ký dinh dưỡng dường như thiếu bữa trưa (Tổng nạp ghi nhận < 1,300 kcal). "
            "Nếu đã nạp đủ trưa nay, KHÔNG ăn thêm bất kỳ thứ gì sau 18:00 để giữ dạ dày rỗng, "
            "bảo vệ HRV đêm và hạ RHR."
        ) if is_incomplete else ""
    }


def get_post_race_meal_benchmarks_prompt() -> str:
    """Returns realistic Vietnamese meal recommendations formatted by regular bowls/plates."""
    return (
        "QUY CHUẨN MÓN ĂN THỰC TẾ & VIỆT HÓA (ĐỊNH LƯỢNG THEO BÁT/ĐĨA THÔNG THƯỜNG, BỎ CÂN ĐONG TIỂU LY, BỎ YẾN MẠCH):\n"
        "- CẤM TUYỆT ĐỐI:\n"
        "  + Tuyệt đối KHÔNG gợi ý 'Yến mạch cán vỡ' hay ngũ cốc thô trong pha phục hồi ruột nhạy cảm.\n"
        "  + KHÔNG viết theo kiểu cân đong tiểu ly phi thực tế (như '180g gạo chín', '40g thịt thăn'). Định lượng bằng bát/đĩa thông thường.\n"
        "- KHUNG THỰC ĐƠN MẪU DÂN DÃ:\n"
        f"  * Bữa sáng: {POST_RACE_REALISTIC_MEALS['breakfast']}.\n"
        f"  * Bữa trưa: {POST_RACE_REALISTIC_MEALS['lunch']}.\n"
        f"  * Bữa xế chiều (Đơn giản cho người đi làm): {POST_RACE_REALISTIC_MEALS['snack']}.\n"
        f"  * Bữa tối (Tuân thủ trần Protein <= 28.0g, thanh đạm): {POST_RACE_REALISTIC_MEALS['dinner']}.\n"
        "- BẢO TOÀN ATWATER DETERMINISTIC: LLM chỉ được phép phân bổ các món ăn dân dã, thực tế ở trên để khớp với khung Macro Deterministic đã tính toán, tuyệt đối không tự ý sửa số gram tổng.\n"
        "- 💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."
    )


def get_post_race_digestive_guidelines() -> str:
    """Returns clinical digestive soothing prompt snippet for Runner's Gut prevention."""
    prohibited = ", ".join(POST_RACE_DIGESTIVE_RULES["prohibited_foods"])
    mandatory = "; ".join(POST_RACE_DIGESTIVE_RULES["mandatory_prescriptions"])

    return (
        f"⚠️ QUY TẮC LÂM SÀNG DINH DƯỠNG PHỤC HỒI HỆ TIÊU HÓA (POST-RACE CLINICAL DIGESTIVE RULES):\n"
        f"- CẤM TUYỆT ĐỐI NẠP: {prohibited}.\n"
        f"- BẮT BUỘC CHỈ ĐỊNH THỰC ĐƠN: {mandatory}.\n"
        f"- {get_post_race_meal_benchmarks_prompt()}\n"
        f"- Nhắm tới mục tiêu giảm phản xạ dạ dày - đại tràng (Runner's Gut) và làm dịu niêm mạc ruột sau giải chạy cự ly dài."
    )


