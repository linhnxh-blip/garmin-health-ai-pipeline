"""
Card Generator Module.
Generates concise, reality-based Evening Review Reports and Telegram Cards.
Binds strictly to actual logged meals in nutrition_logs, eliminating fictional food hallucinations.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path


def extract_evening_meals(nut_logs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract meals consumed in the evening (timestamp >= 17:00 or meal_type containing evening keywords).
    Returns structured summary with dish names, evening protein, evening fat, drinks, and text description.
    """
    if not nut_logs:
        return {
            "has_evening_meal": False,
            "dishes_text": "",
            "evening_p": 0.0,
            "evening_f": 0.0,
            "evening_c": 0.0,
            "evening_cal": 0,
            "drinks": [],
            "foods": []
        }

    evening_logs = []
    for log in nut_logs:
        ts = str(log.get("timestamp") or "")
        m_type = str(log.get("meal_type") or "").lower()
        is_evening = False

        if len(ts) >= 13 and ":" in ts:
            try:
                t_part = ts.split()[-1]
                hour = int(t_part.split(":")[0])
                if hour >= 17:
                    is_evening = True
            except Exception:
                pass

        if any(kw in m_type for kw in ["tối", "đêm", "dinner", "nhậu"]):
            is_evening = True

        if is_evening:
            evening_logs.append(log)

    # Fallback to the last meal of the day if no logs specifically marked >= 17:00
    if not evening_logs and nut_logs:
        evening_logs = [nut_logs[-1]]

    foods = []
    drinks = []
    tot_p = 0.0
    tot_f = 0.0
    tot_c = 0.0
    tot_cal = 0

    for el in evening_logs:
        d_raw = el.get("dishes") or []
        if isinstance(d_raw, list):
            d_names = [str(x).strip() for x in d_raw if str(x).strip()]
        else:
            d_names = [str(d_raw).strip()]

        p_val = float(el.get("protein_g") or 0.0)
        f_val = float(el.get("fat_g") or 0.0)
        c_val = float(el.get("carb_g") or 0.0)
        cal_val = int(el.get("total_calories") or 0)

        tot_p += p_val
        tot_f += f_val
        tot_c += c_val
        tot_cal += cal_val

        item_str = ", ".join(d_names)
        m_type_el = str(el.get("meal_type") or "").lower()

        is_drink = any(dkw in item_str.lower() or dkw in m_type_el for dkw in [
            "nước", "ép", "juice", "sinh tố", "uống", "bia", "trà", "ml", "rượu"
        ])

        if is_drink:
            drinks.append(item_str)
        else:
            foods.append({
                "name": item_str,
                "p": p_val,
                "f": f_val,
                "c": c_val,
                "cal": cal_val
            })

    tot_food_p = sum(f["p"] for f in foods)
    tot_food_f = sum(f["f"] for f in foods)
    food_names = [f["name"] for f in foods]
    food_names_str = ", ".join(food_names)

    parts = []
    if food_names_str:
        if tot_food_p > 0 or tot_food_f > 0:
            parts.append(f"{food_names_str} ({tot_food_p:.0f}g Protein, {tot_food_f:.0f}g Fat)")
        else:
            parts.append(food_names_str)

    if drinks:
        drinks_str = " + ".join(drinks)
        if parts:
            dishes_text = f"{parts[0]} + {drinks_str}"
        else:
            dishes_text = drinks_str
    else:
        dishes_text = parts[0] if parts else "Bữa tối dinh dưỡng"

    return {
        "has_evening_meal": True,
        "dishes_text": dishes_text,
        "evening_p": round(tot_p, 1),
        "evening_f": round(tot_f, 1),
        "evening_c": round(tot_c, 1),
        "evening_cal": tot_cal,
        "drinks": drinks,
        "foods": foods
    }


def generate_evening_components(baseline_data: Dict[str, Any]) -> Dict[str, str]:
    """Build the 4 clean sections for the ultra-concise Evening Review."""
    target_date = baseline_data.get("target_date") or datetime.now().strftime("%Y-%m-%d")
    db_path = baseline_data.get("db_path")
    tm = baseline_data.get("target_metrics", {})

    from src.analytics.prompt_engine import get_vietnamese_date_str, get_effective_weight_kg, get_race_context
    from src.analytics.pipeline import detect_today_morning_activity
    from src.analytics.nutrition_engine import calculate_daily_macros
    from src.db.nutrition_repository import get_nutrition_logs_by_date, get_today_nutrition_summary

    date_vn = get_vietnamese_date_str(target_date)
    w_eff = get_effective_weight_kg(tm)
    race_ctx = get_race_context(target_date)
    act_info = detect_today_morning_activity(target_date, db_path=db_path)
    act_cals = act_info.get("active_calories", 0.0)

    # 1. Macro targets & actual logged values
    macro_targets = calculate_daily_macros(
        weight_kg=float(w_eff),
        phase=race_ctx["phase"],
        uric_acid_level=442.0,
        active_calories_garmin=act_cals,
        days_since_race=race_ctx["days_since_race"],
        days_to_race=race_ctx["days_to_race"]
    )
    target_cal = float(macro_targets.get("target_calories", 1796.0))
    target_p = float(macro_targets.get("protein_g", 95.0))
    target_c = float(macro_targets.get("carb_g", 243.0))
    target_f = float(macro_targets.get("fat_g", 49.3))

    nut_logs = get_nutrition_logs_by_date(target_date, db_path=db_path)
    nut_sum = get_today_nutrition_summary(target_date, db_path=db_path)

    tot_cal = nut_sum.get("total_cal", 0)
    tot_p = float(nut_sum.get("total_protein", 0.0))
    tot_c = float(nut_sum.get("total_carbs", 0.0))
    tot_f = float(nut_sum.get("total_fat", 0.0))

    cal_diff = round(tot_cal - target_cal, 1)
    p_diff = round(tot_p - target_p, 1)
    c_diff = round(tot_c - target_c, 1)
    f_diff = round(tot_f - target_f, 1)

    # Section 1: TỔNG KẾT NĂNG LƯỢNG & THỰC TẾ ĐÃ NẠP
    if p_diff > 0:
        p_note = f"Thừa +{p_diff:.1f}g đạm"
    elif p_diff < -5:
        p_note = f"Thiếu {abs(p_diff):.1f}g đạm"
    else:
        p_note = "Đạt mục tiêu"

    c_note = f"Thiếu {abs(c_diff):.1f}g" if c_diff < -5 else (f"Thừa +{c_diff:.1f}g" if c_diff > 5 else "Đạt")
    f_note = f"Thừa +{f_diff:.1f}g" if f_diff > 5 else (f"Thiếu {abs(f_diff):.1f}g" if f_diff < -5 else "Đạt")
    cal_diff_str = f"+{cal_diff:.0f}" if cal_diff > 0 else f"{cal_diff:.0f}"

    sec1 = (
        f"📊 **TỔNG KẾT NĂNG LƯỢNG & ĐÃ NẠP**\n"
        f"• Năng lượng: {tot_cal:,} / {target_cal:,.0f} kcal ({cal_diff_str} kcal).\n"
        f"• Đạm: {tot_p:.1f}g / {target_p:.1f}g ({p_note}).\n"
        f"• Carb: {tot_c:.1f}g / {target_c:.1f}g ({c_note}) | Fat: {tot_f:.1f}g / {target_f:.1f}g ({f_note})."
    )
    sec1_card = (
        f"📊 **TỔNG KẾT NĂNG LƯỢNG & ĐÃ NẠP**\n"
        f"• Calo: {tot_cal:,} / {target_cal:,.0f} kcal ({cal_diff_str} kcal).\n"
        f"• Đạm: {tot_p:.1f}g / {target_p:.1f}g ({p_note}).\n"
        f"• C: {tot_c:.1f}g / {target_c:.1f}g | F: {tot_f:.1f}g / {target_f:.1f}g."
    )

    # Section 2: CẢNH BÁO TIÊU HÓA ĐÊM
    evening_info = extract_evening_meals(nut_logs)
    if evening_info["has_evening_meal"] and evening_info["dishes_text"]:
        dishes_str = evening_info["dishes_text"]
        ef = evening_info["evening_f"]

        fat_msg = f"Khẩu phần tối nhiều mỡ ({ef:.0f}g Fat)" if ef >= 20 else f"Khẩu phần tối ({ef:.0f}g Fat)"

        sec2 = (
            f"⚠️ **CẢNH BÁO TIÊU HÓA ĐÊM**\n"
            f"• Bữa tối: {dishes_str}.\n"
            f"• ⚠️ {fat_msg} sát giờ ngủ dễ tăng RHR đêm. Dừng ăn từ bây giờ."
        )
        sec2_card = (
            f"⚠️ **CẢNH BÁO TIÊU HÓA ĐÊM**\n"
            f"• Bữa tối: {dishes_str}.\n"
            f"• ⚠️ Bữa tối nhiều mỡ ({ef:.0f}g Fat) sát giờ ngủ dễ tăng RHR. Dừng nạp thêm."
        )
    else:
        sec2 = (
            f"⚠️ **CẢNH BÁO TIÊU HÓA ĐÊM**\n"
            f"• Chưa có nhật ký bữa tối chi tiết.\n"
            f"• ⚠️ Giữ dạ dày rỗng để bảo vệ HRV và hạ RHR đêm."
        )
        sec2_card = sec2

    # Section 3: ĐỊNH HƯỚNG VẬN ĐỘNG SÁNG MAI
    try:
        dt_target = datetime.strptime(target_date, "%Y-%m-%d").date()
        next_dt = dt_target + timedelta(days=1)
        next_date_str = f"{next_dt.day:02d}/{next_dt.month:02d}"
    except Exception:
        next_date_str = "mai"

    steps = tm.get("total_steps") or 0
    act_summary_raw = tm.get("activities_summary")
    run_dist_km = 0.0

    if act_summary_raw:
        try:
            acts = json.loads(act_summary_raw) if isinstance(act_summary_raw, str) else act_summary_raw
            if isinstance(acts, list):
                for act in acts:
                    act_type = str(act.get("type") or act.get("name") or "").lower()
                    if any(rk in act_type for rk in ["run", "running", "chạy"]):
                        run_dist_km += float(act.get("distance_meters") or 0.0) / 1000.0
        except Exception:
            pass

    if steps >= 10000:
        step_round = steps // 100 * 100
        step_str = f"> {step_round:,} bước".replace(",", ".")
    else:
        step_str = f"{steps:,} bước".replace(",", ".")

    run_str = f" và chạy {run_dist_km:.0f}km" if run_dist_km >= 0.5 else ""

    sec3 = (
        f"🏃‍♂️ **ĐỊNH HƯỚNG VẬN ĐỘNG SÁNG MAI**\n"
        f"• Kế hoạch {next_date_str}: Ưu tiên Nghỉ ngơi (Rest Day) hoặc đi bộ thả lỏng (đã tích lũy {step_str}{run_str}). CHỈ chạy thử 2km nếu sáng mai Readiness >= 68 và Recovery Time <= 4h."
    )
    sec3_card = (
        f"🏃‍♂️ **ĐỊNH HƯỚNG VẬN ĐỘNG SÁNG MAI**\n"
        f"• Kế hoạch {next_date_str}: Nghỉ ngơi/đi bộ nhẹ ({step_str}{run_str}). Chạy 2km khi Readiness >= 68."
    )

    # Section 4: GIAO THỨC TRƯỚC KHI LÊN GIƯỜNG
    sec4 = (
        f"💤 **Giao thức trước khi lên giường**\n"
        f"• 1 viên Magie Bisglycinate với nước ấm, đi tiểu sạch trước khi ngủ.\n"
        f"• Tắt điện thoại, phòng mát (22-24°C), ngủ trước 21:30 để tối ưu Body Battery."
    )
    sec4_card = (
        f"💤 **Giao thức trước khi lên giường**\n"
        f"• 1 viên Magie Bisglycinate + nước ấm, phòng tối mát, ngủ trước 21:30."
    )

    phase_str = str(race_ctx.get("phase") or baseline_data.get("phase") or "")
    days_since = race_ctx.get("days_since_race")
    if phase_str == "POST_RACE_RECOVERY":
        header_title = f"POST_RACE_RECOVERY D+{days_since or 8}"
    elif phase_str == "POST_RACE_ACUTE":
        header_title = f"POST_RACE_ACUTE D+{days_since or 3}"
    elif phase_str:
        header_title = phase_str
    else:
        header_title = ""

    return {
        "date_vn": date_vn,
        "header_title": header_title,
        "sec1": sec1,
        "sec1_card": sec1_card,
        "sec2": sec2,
        "sec2_card": sec2_card,
        "sec3": sec3,
        "sec3_card": sec3_card,
        "sec4": sec4,
        "sec4_card": sec4_card
    }


def generate_evening_report(baseline_data: Dict[str, Any]) -> str:
    """Generate concise, reality-based Evening Review Report (< 150 words)."""
    c = generate_evening_components(baseline_data)
    hdr = f" ({c['header_title']})" if c.get("header_title") else ""
    title = f"# 🌙 Báo cáo Tổng kết Ngày & Giao thức Phục hồi Tối{hdr} ({c['date_vn']})"
    return f"{title}\n\n===SECTION_BREAK===\n{c['sec1']}\n\n===SECTION_BREAK===\n{c['sec2']}\n\n===SECTION_BREAK===\n{c['sec3']}\n\n===SECTION_BREAK===\n{c['sec4']}"


def generate_evening_card(baseline_data: Dict[str, Any]) -> str:
    """Generate concise Telegram Evening Glanceable Card (< 150 words)."""
    c = generate_evening_components(baseline_data)
    hdr = f" ({c['header_title']})" if c.get("header_title") else ""
    return f"🌙 **TỔNG KẾT PHỤC HỒI TỐI{hdr} ({c['date_vn']})**\n\n{c['sec1_card']}\n\n{c['sec2_card']}\n\n{c['sec3_card']}\n\n{c['sec4_card']}"
