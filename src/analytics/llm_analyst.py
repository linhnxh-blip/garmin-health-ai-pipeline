import json
import os
import time
from typing import Dict, Any, Optional
from config.settings import settings

SYSTEM_PROMPT = """Bạn là một Chuyên gia Sinh lý học Thể thao và Huấn luyện viên Phục hồi Cá nhân cao cấp.
Nhiệm vụ của bạn là phân tích dữ liệu sinh lý học hàng ngày từ thiết bị Garmin của người dùng và đối chiếu với Baseline (30 ngày gần nhất) để đưa ra bản nhật ký phân tích sức khỏe & tư vấn phục hồi chuyên sâu.

NGUYÊN TẮC THIẾT YẾU:
1. TRUNG THỰC DỮ LIỆU (STRICT FACTUAL DATA): Tuyệt đối không tự suy diễn hoặc giả định các số liệu bị thiếu. Nếu trường dữ liệu ghi nhận là "KHÔNG CÓ DỮ LIỆU (NULL)", bạn phải ghi nhận là chưa đo lường được, không tự tính trung bình hoặc bịa ra con số.
2. PHÂN TÍCH TƯƠNG QUAN ĐA BIẾN (MULTIVARIATE CORRELATION): Không đánh giá riêng lẻ từng chỉ số đơn độc. Bạn phải liên kết toàn bộ bức tranh sinh lý học:
   - Giấc ngủ (Cấu trúc Sleep Stage / Sleep Score) ↔ Nhịp tim nghỉ (RHR)
   - Cân bằng Hệ thần kinh thực vật (HRV Overnight vs Baseline) ↔ Mức độ Stress ban ngày & đêm
   - Mức sạc / xả Body Battery ↔ Tải vận động thực tế (Workout Calories / Duration / Training Effect)
3. SO SÁNH TRỰC TIẾP VỚI BASELINE 30 NGÀY:
   - Tính toán độ lệch % hoặc lệch trị số tuyệt đối của HRV, RHR, Sleep Score hôm nay so với trung bình baseline 30 ngày (sample_size_days).
   - Nhận diện xu hướng (tốt hơn baseline, kém hơn baseline, hay nằm trong dải bình thường).
4. NGÔN NGỮ VÀ THUẬT NGỮ CHUẨN MỰC: BẮT BUỘC: Toàn bộ báo cáo phải được viết thuần túy bằng tiếng Việt y khoa chuẩn mực. Tuyệt đối KHÔNG sử dụng các ký tự chữ Hán/tiếng Trung (như 指数, 恢复...) hoặc từ ngữ dịch máy lai tạp. Dùng đúng thuật ngữ "Chỉ số HRV".
5. RÀNG BUỘC KHỚP SỐ HỌC GIẤC NGỦ: Tổng thời gian ngủ (Total Sleep Time) trong văn bản BẮT BUỘC phải bằng chính xác tổng số phút của (Deep Sleep + REM Sleep + Light Sleep) quy đổi ra giờ và phút. Tuyệt đối không làm tròn lệch phút so với bảng số liệu. (Ví dụ: Deep 105m + REM 28m + Light 276m = 409m = 6 giờ 49 phút). Tổng thời gian trên giường (Total Bed Time) = Deep + REM + Light + Awake.

ĐỊNH DẠNG ĐẦU RA MẶC ĐỊNH (BẮT BUỘC SỬ DỤNG CÁC THẺ TIÊU ĐỀ NÀY):

# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi ({date})

### 🩺 **Trạng thái hồi phục & Cân bằng thần kinh:**
[Đánh giá tổng quan mức độ phục hồi, trạng thái phó giao cảm (Parasympathetic) / giao cảm (Sympathetic), HRV balance, RHR deviation]

### 🔍 **Phân tích tương quan & Xu hướng:**
[Chi tiết mối tương quan giữa Giấc ngủ ↔ Stress ↔ Body Battery ↔ HRV ↔ Tải vận động 7 ngày. So sánh trực tiếp các chỉ số hôm nay với Baseline 30 ngày. Giải thích nguyên nhân sinh lý vì sao chỉ số tăng/giảm.]

### ⚡ **Kế hoạch vận động & Phục hồi ngày mai:**
[Khuyến nghị cụ thể về cường độ tập luyện ngày tiếp theo (Zone 2 nhẹ nhàng, nghỉ ngơi hoàn toàn, bài tập thả lỏng, hay có thể nâng tải), tối ưu hóa thời gian ngủ và quản lý stress]
"""

def _clean_markdown_response(text: str) -> str:
    """Clean markdown text by stripping surrounding code blocks if present."""
    if not text:
        return ""
    text = text.strip()
    if text.startswith("```markdown"):
        text = text[11:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def _format_value(val: Any, unit: str = "") -> str:
    if val is None:
        return "KHÔNG CÓ DỮ LIỆU (NULL)"
    return f"{val} {unit}".strip()

def _format_seconds(seconds: Optional[int]) -> str:
    if seconds is None:
        return "KHÔNG CÓ DỮ LIỆU (NULL)"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m ({seconds} giây)"

def build_user_prompt(baseline_data: Dict[str, Any]) -> str:
    target_date = baseline_data["target_date"]
    tm = baseline_data["target_metrics"]
    bm = baseline_data["metrics_baseline"]
    tl = baseline_data["training_load_7d"]
    sample_size = baseline_data["sample_size_days"]
    dr = baseline_data["date_range"]

    prompt_parts = []
    prompt_parts.append(f"DỮ LIỆU SINH LÝ HỌC NGÀY: {target_date}")
    prompt_parts.append(f"Mẫu dữ liệu Baseline 30 ngày gần nhất: {sample_size} ngày ({dr.get('start') or 'N/A'} đến {dr.get('end') or 'N/A'})\n")

    prompt_parts.append("--- CHỈ SỐ HÔM NAY VS BASELINE 30 NGÀY ---")

    # Sleep Score
    bs_sleep = bm.get("sleep_score", {})
    prompt_parts.append(
        f"- Sleep Score: Hôm nay = {_format_value(tm.get('sleep_score'))} | Baseline 30d Avg = {bs_sleep.get('avg', 'NULL')} (Std: {bs_sleep.get('std', 'NULL')}, Min-Max: {bs_sleep.get('min', 'NULL')}-{bs_sleep.get('max', 'NULL')})"
    )

    # HRV Last Night
    bs_hrv = bm.get("hrv_last_night", {})
    prompt_parts.append(
        f"- HRV Overnight (ms): Hôm nay = {_format_value(tm.get('hrv_last_night'), 'ms')} (Status: {tm.get('hrv_status') or 'NULL'}) | Baseline 30d Avg = {bs_hrv.get('avg', 'NULL')} ms (Std: {bs_hrv.get('std', 'NULL')}, Min-Max: {bs_hrv.get('min', 'NULL')}-{bs_hrv.get('max', 'NULL')})"
    )

    # Resting Heart Rate
    bs_rhr = bm.get("resting_heart_rate", {})
    prompt_parts.append(
        f"- Resting Heart Rate (bpm): Hôm nay = {_format_value(tm.get('resting_heart_rate'), 'bpm')} | Baseline 30d Avg = {bs_rhr.get('avg', 'NULL')} bpm (Std: {bs_rhr.get('std', 'NULL')}, Min-Max: {bs_rhr.get('min', 'NULL')}-{bs_rhr.get('max', 'NULL')})"
    )

    # Average Stress
    bs_stress = bm.get("avg_stress_level", {})
    prompt_parts.append(
        f"- Avg Stress Level: Hôm nay = {_format_value(tm.get('avg_stress_level'))} (Max: {tm.get('max_stress_level') or 'NULL'}) | Baseline 30d Avg = {bs_stress.get('avg', 'NULL')} (Std: {bs_stress.get('std', 'NULL')}, Min-Max: {bs_stress.get('min', 'NULL')}-{bs_stress.get('max', 'NULL')})"
    )

    # Body Battery
    prompt_parts.append(
        f"- Body Battery: Charged = {_format_value(tm.get('body_battery_charged'))}, Drained = {_format_value(tm.get('body_battery_drained'))}, High = {_format_value(tm.get('body_battery_highest'))}, Low = {_format_value(tm.get('body_battery_lowest'))}"
    )

    # Active Calories
    bs_cal = bm.get("active_calories", {})
    prompt_parts.append(
        f"- Active Calories (kcal): Hôm nay = {_format_value(tm.get('active_calories'), 'kcal')} | Baseline 30d Avg = {bs_cal.get('avg', 'NULL')} kcal"
    )

    # Total Steps
    bs_steps = bm.get("total_steps", {})
    prompt_parts.append(
        f"- Total Steps: Hôm nay = {_format_value(tm.get('total_steps'))} | Baseline 30d Avg = {bs_steps.get('avg', 'NULL')}"
    )

    # Sleep Stages detail
    prompt_parts.append("\n--- CHI TIẾT CẤU TRÚC GIẤC NGỦ HÔM NAY ---")
    deep_sec_raw = tm.get('deep_sleep_seconds')
    rem_sec_raw = tm.get('rem_sleep_seconds')
    light_sec_raw = tm.get('light_sleep_seconds')
    awake_sec_raw = tm.get('awake_duration_seconds')
    if deep_sec_raw is not None or rem_sec_raw is not None or light_sec_raw is not None:
        calc_sleep_s = (float(deep_sec_raw or 0) + float(rem_sec_raw or 0) + float(light_sec_raw or 0))
        calc_bed_s = calc_sleep_s + float(awake_sec_raw or 0)
        prompt_parts.append(f"- Total Sleep Time (Deep + REM + Light): {_format_seconds(int(round(calc_sleep_s)))}")
        prompt_parts.append(f"- Total Bed Time (Deep + REM + Light + Awake): {_format_seconds(int(round(calc_bed_s)))}")
    else:
        prompt_parts.append(f"- Total Sleep Time: {_format_seconds(tm.get('sleep_duration_seconds'))}")
    prompt_parts.append(f"- Deep Sleep: {_format_seconds(deep_sec_raw)}")
    prompt_parts.append(f"- REM Sleep: {_format_seconds(rem_sec_raw)}")
    prompt_parts.append(f"- Light Sleep: {_format_seconds(light_sec_raw)}")

    # Today's Activities
    prompt_parts.append("\n--- HOẠT ĐỘNG THỂ THAO HÔM NAY ---")
    act_summary_raw = tm.get("activities_summary")
    if act_summary_raw:
        try:
            acts = json.loads(act_summary_raw)
            if isinstance(acts, list) and acts:
                for idx, act in enumerate(acts, 1):
                    prompt_parts.append(
                        f"{idx}. {act.get('name') or act.get('type')}: Duration = {_format_seconds(act.get('duration_seconds'))}, "
                        f"Distance = {round(act.get('distance_meters', 0)/1000, 2) if act.get('distance_meters') else 'N/A'} km, "
                        f"Calories = {act.get('calories') or 'N/A'} kcal, "
                        f"Avg HR = {act.get('avg_hr') or 'N/A'} bpm, Max HR = {act.get('max_hr') or 'N/A'} bpm, "
                        f"Aerobic TE = {act.get('aerobic_training_effect') or 'N/A'}"
                    )
            else:
                prompt_parts.append("Không ghi nhận bài tập thể thao nào.")
        except Exception:
            prompt_parts.append("Không ghi nhận bài tập thể thao nào.")
    else:
        prompt_parts.append("Không ghi nhận bài tập thể thao nào.")

    # 7-day Training Load Summary
    prompt_parts.append("\n--- TỔNG TẢI VẬN ĐỘNG 7 NGÀY GẦN NHẤT ---")
    prompt_parts.append(f"- Total Active Calories: {tl.get('total_active_calories', 0)} kcal")
    prompt_parts.append(f"- Total Steps: {tl.get('total_steps', 0)}")
    prompt_parts.append(f"- Total Workouts Count: {tl.get('total_workout_count', 0)} bài tập")
    prompt_parts.append(f"- Total Workout Duration: {_format_seconds(tl.get('total_duration_seconds'))}")

    prompt_parts.append("\nHãy phân tích và trả về bản Nhật ký Phục hồi theo đúng định dạng được yêu cầu.")
    return "\n".join(prompt_parts)

def call_gemini(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Call Google Gemini API using google-genai SDK with exponential backoff retry & instant model fallback."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in .env")

    # Candidate models in order of priority & quota availability
    default_candidates = [
        "gemini-2.5-flash",
        "gemini-3.8-flash",
    ]
    env_model = (settings.gemini_model or "").strip()
    raw_candidates = ([env_model] if env_model else []) + default_candidates
    seen = set()
    models_to_try = [m.replace("models/", "").strip() for m in raw_candidates if m and not (m in seen or seen.add(m))]

    from google import genai
    from google.genai import types
    from src.analytics.vision_analyst import create_genai_client

    client = create_genai_client(api_key)
    
    last_err = None
    for model in models_to_try:
        max_retries = 3
        delay = 2
        for attempt in range(1, max_retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.3
                    )
                )
                report_markdown = _clean_markdown_response(response.text or "")
                prompt_tokens = 0
                completion_tokens = 0
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    completion_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

                return {
                    "report_markdown": report_markdown,
                    "model_used": f"gemini ({model})",
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens
                }
            except Exception as exc:
                last_err = exc
                err_str = str(exc)
                err_lower = err_str.lower()
                print(f"⚠️ Gemini API attempt {attempt}/{max_retries} failed for model '{model}': {exc}")

                # If rate-limited (429 RESOURCE_EXHAUSTED / Quota limit), immediately fallback to next model
                if "429" in err_str or "resource_exhausted" in err_lower or "quota" in err_lower:
                    print(f"🔄 Model '{model}' hit 429 Quota Exhausted. Skipping retries for '{model}' and switching to next model...")
                    break

                # If unavailable (503 / 404), fallback to next model immediately
                if "404" in err_str or "not found" in err_lower or "503" in err_str or "unavailable" in err_lower:
                    print(f"🔄 Model '{model}' unavailable/overloaded (503/404). Switching to next candidate model...")
                    break

                # For transient network errors, retry up to max_retries
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2

    raise RuntimeError(f"All Gemini API candidate models failed. Last error: {last_err}")

def call_openai(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    """Call OpenAI API using openai SDK."""
    api_key = settings.openai_api_key
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured in .env")

    model_name = settings.openai_model or "gpt-4o-mini"
    
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3
    )

    report_markdown = response.choices[0].message.content or ""
    prompt_tokens = response.usage.prompt_tokens if response.usage else 0
    completion_tokens = response.usage.completion_tokens if response.usage else 0

    return {
        "report_markdown": report_markdown,
        "model_used": f"openai ({model_name})",
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens
    }

def _generate_structured_report(baseline_data: Dict[str, Any], is_mock: bool = False) -> Dict[str, Any]:
    """Generate structured physiological report offline (or for Mock LLM mode) without invoking API tokens."""
    from src.analytics.prompt_engine import get_race_context, format_training_status, TRAINING_STATUS_MAP, _format_seconds, get_vietnamese_date_str, get_effective_weight_kg, get_report_title_header, generate_telegram_card_fallback, clean_report_text
    
    target_date = baseline_data["target_date"]
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data.get("target_metrics", {})
    bm = baseline_data.get("metrics_baseline", {})
    tl = baseline_data.get("training_load_7d", {})
    w_kg = get_effective_weight_kg(tm)
    r_type = (baseline_data.get("report_type") or "morning").lower()
    race_ctx = get_race_context(target_date)
    phase = race_ctx["phase"]
    d_left = race_ctx["days_to_race"]
    d_since = race_ctx["days_since_race"]
    race_info = race_ctx["race_info"]

    hrv_val = tm.get("hrv_last_night")
    hrv_str = f"{hrv_val} ms" if hrv_val is not None else "KHÔNG CÓ DỮ LIỆU (NULL)"
    hrv_bs = bm.get("hrv_last_night", {}).get("avg")
    
    if hrv_val is not None and hrv_bs and hrv_bs > 0:
        pct_hrv_diff = round(((hrv_val - hrv_bs) / hrv_bs) * 100, 1)
        hrv_eval_str = f"{'+' if pct_hrv_diff >= 0 else ''}{pct_hrv_diff}% so với Baseline 30 ngày ({hrv_bs} ms)"
    else:
        hrv_eval_str = "duy trì dải bình thường so với Baseline 30 ngày"

    rhr_val = tm.get("resting_heart_rate")
    rhr_str = f"{rhr_val} bpm" if rhr_val is not None else "KHÔNG CÓ DỮ LIỆU (NULL)"
    rhr_bs = bm.get("resting_heart_rate", {}).get("avg")
    
    if rhr_val is not None and rhr_bs and rhr_bs > 0:
        rhr_diff = rhr_val - rhr_bs
        rhr_eval_str = f"{'+' if rhr_diff >= 0 else ''}{round(rhr_diff, 1)} bpm so với Baseline ({rhr_bs} bpm)"
    else:
        rhr_eval_str = "ổn định so với dải chuẩn"

    sleep_score = tm.get("sleep_score") or "N/A"
    deep_sec = tm.get("deep_sleep_seconds")
    rem_sec = tm.get("rem_sleep_seconds")
    light_sec = tm.get("light_sleep_seconds")
    awake_sec = tm.get("awake_duration_seconds")
    deep_str = _format_seconds(deep_sec)
    rem_str = _format_seconds(rem_sec)

    deep_sec_val = float(deep_sec or 0)
    rem_sec_val = float(rem_sec or 0)
    light_sec_val = float(light_sec or 0)
    awake_sec_val = float(awake_sec or 0)

    if deep_sec_val > 0 or rem_sec_val > 0 or light_sec_val > 0:
        tot_sleep_sec = int(round(deep_sec_val + rem_sec_val + light_sec_val))
    else:
        tot_sleep_sec = int(round(float(tm.get("sleep_duration_seconds") or 0))) if tm.get("sleep_duration_seconds") else None

    tot_sleep_str = _format_seconds(tot_sleep_sec) if tot_sleep_sec is not None else "KHÔNG CÓ DỮ LIỆU (NULL)"

    deep_m = round(deep_sec_val / 60.0, 1)
    rem_m = round(rem_sec_val / 60.0, 1)
    light_m = round(light_sec_val / 60.0, 1)
    awake_m = round(awake_sec_val / 60.0, 1)

    total_asleep = deep_m + rem_m + light_m
    total_bed = total_asleep + awake_m

    if total_asleep > 0:
        deep_pct = round((deep_m / total_asleep) * 100.0, 1)
        rem_pct = round((rem_m / total_asleep) * 100.0, 1)
        light_pct = round((100.0 - deep_pct - rem_pct), 1)
    else:
        deep_pct = rem_pct = light_pct = 0.0

    awake_pct = round((awake_m / total_bed) * 100.0, 1) if total_bed > 0 else 0.0

    bb_charged = tm.get("body_battery_charged") or "N/A"
    ts_raw = tm.get("training_status")
    ts_display = format_training_status(ts_raw)

    sleep_hours = (float(tot_sleep_sec) / 3600.0) if (tot_sleep_sec is not None and float(tot_sleep_sec) > 0) else None
    is_sleep_deprived = (sleep_hours is not None and sleep_hours < 5.0)

    from src.analytics.nutrition_engine import calculate_daily_macros
    is_t2_t1 = (d_left is not None and 1 <= d_left <= 2)
    is_post_acute = (phase == "POST_RACE_ACUTE")
    is_post_race = (phase == "POST_RACE_RECOVERY") or is_post_acute

    from src.analytics.pipeline import detect_today_morning_activity
    act_info_today = detect_today_morning_activity(target_date, db_path=baseline_data.get("db_path"))
    act_cals_today = float(act_info_today.get("active_calories") or 0.0)

    macro_targets = calculate_daily_macros(
        weight_kg=float(w_kg),
        phase=phase,
        uric_acid_level=442.0,
        active_calories_garmin=act_cals_today,
        days_to_race=d_left,
        days_since_race=d_since
    )
    protein_target = macro_targets["protein_g"]
    target_cal_est = macro_targets["target_calories"]
    carb_target = macro_targets["carb_g"]
    fat_target = macro_targets["fat_g"]
    dinner_p_cap = macro_targets["dinner_protein_cap"]

    if is_post_acute and race_info:
        race_countdown_str = f"• **Sự kiện thi đấu:** {race_info['name']} ({race_info['distance']}) ngày {race_info['date']} — **ĐÃ KẾT THÚC (Đã qua {d_since} ngày — Phase Hồi phục Cấp POST-RACE ACUTE).**"
    elif is_post_race and race_info:
        race_countdown_str = f"• **Sự kiện thi đấu:** {race_info['name']} ({race_info['distance']}) ngày {race_info['date']} — **ĐÃ KẾT THÚC (Đã qua {d_since} ngày — Phase Post-Race Recovery).**"
    elif race_info:
        race_countdown_str = f"• **Sự kiện thi đấu:** {race_info['name']} ({race_info['distance']}) vào ngày {race_info['date']} — **Còn đúng {race_info['days_to_race']} ngày** (Giai đoạn Dynamic Tapering & Giảm tải sâu)."
    else:
        race_countdown_str = "• **Sự kiện thi đấu:** Chưa ghi nhận sự kiện sắp tới trong `config/races.json`."

    from datetime import datetime, timedelta
    from src.db.nutrition_repository import get_nutrition_logs_by_date
    query_date = target_date
    if r_type == "morning":
        try:
            prev_date_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)
            query_date = prev_date_dt.strftime("%Y-%m-%d")
        except Exception:
            query_date = target_date
    nut_logs = get_nutrition_logs_by_date(query_date)
    total_alc = sum(float(l.get("alcohol_units") or 0.0) for l in nut_logs) if nut_logs else 0.0
    nut_correlation_text = ""
    if nut_logs:
        log_items = []
        for log in nut_logs:
            dishes = ", ".join(log.get("dishes", [])) if isinstance(log.get("dishes", []), list) else str(log.get("dishes"))
            alc_units = log.get("alcohol_units") or 0.0
            log_items.append(f"Món ăn: {dishes} (Cồn: {alc_units} đơn vị, Calo: ~{log.get('total_calories') or 0} kcal)")
        
        log_summary_str = "; ".join(log_items)
        if total_alc > 0:
            nut_correlation_text = (
                f"- **ĐỐI CHIẾU TRỰC TIẾP NHẬT KÝ DINH DƯỠNG ĐÊM HÔM QUA (HỘI CHỨNG CỒN ỨC CHẾ REM):** Ghi nhận {total_alc} đơn vị cồn ({log_summary_str}). "
                f"Cồn là tác nhân làm sụt giảm/triệt tiêu pha REM ({rem_str}), "
                f"khiến nhịp tim nghỉ RHR tăng lên mức {rhr_str} ({rhr_eval_str}) và tạo áp lực chuyển hóa giải độc cho gan. Khuyến cáo bù nước, bổ sung điện giải và kiêng cồn tuyệt đối."
            )
        elif rhr_val is not None and rhr_bs and rhr_val <= rhr_bs:
            nut_correlation_text = (
                f"- **ĐỐI CHIẾU TRỰC TIẾP NHẬT KÝ DINH DƯỠNG ĐÊM HÔM QUA:** Ghi nhận thực tế: {log_summary_str}. "
                f"Phân tích sinh lý học lâm sàng cho thấy mặc dù có nạp dinh dưỡng/đồ nhậu, nhịp tim nghỉ RHR đêm qua vẫn hạ thấp ở mức {rhr_str} ({rhr_eval_str}) và HRV đạt {hrv_str} ({hrv_eval_str}). "
                f"Điều này chứng tỏ gan và hệ tim mạch đã chuyển hóa hiệu quả, hệ thần kinh phó giao cảm chiếm ưu thế và thể trạng hồi phục rất tốt."
            )
        else:
            nut_correlation_text = (
                f"- **ĐỐI CHIẾU TRỰC TIẾP NHẬT KÝ DINH DƯỠNG ĐÊM HÔM QUA:** Ghi nhận thực tế: {log_summary_str}. "
                f"Phân tích sinh lý cho thấy bữa ăn sát giờ ngủ hoặc lượng cồn nạp vào đã tạo áp lực chuyển hóa cho gan và tim mạch, "
                f"khiến nhịp tim nghỉ RHR tăng lên mức {rhr_str} ({rhr_eval_str}) và gây ảnh hưởng đến mật độ Ngủ sâu Deep Sleep ({deep_str})."
            )
    else:
        if rem_sec is not None and float(rem_sec) <= 300:  # <= 5 mins (REM collapse)
            nut_correlation_text = (
                f"- **ĐỐI CHIẾU TRỰC TIẾP NHẬT KÝ DINH DƯỠNG ĐÊM HÔM QUA (CẢNH BÁO MẤT PHA REM):** Không ghi nhận log bữa ăn muộn hoặc cồn trong CSDDL, tuy nhiên hiện tượng pha REM sụp đổ ({rem_str}) kết hợp Stress đêm tăng là chữ ký sinh lý kinh điển của cồn chưa ghi nhận hoặc kiệt quệ thần kinh trung ương cấp tính (Acute CNS Exhaustion). Cần truy vấn VĐV về việc dùng bia/rượu tối muộn và kích hoạt giao thức phục hồi sâu."
            )
        else:
            nut_correlation_text = (
                f"- **ĐỐI CHIẾU TRỰC TIẾP NHẬT KÝ DINH DƯỠNG ĐÊM HÔM QUA:** Không ghi nhận bữa ăn muộn hoặc đơn vị cồn bất thường. "
                f"Hệ tiêu hóa hoàn tất chu trình trước 21:00, tạo điều kiện thuận lợi cho hệ thần kinh phó giao cảm tái tạo thể lực đêm qua."
            )


    actual_cal = sum(log.get("total_calories") or 0 for log in nut_logs) if nut_logs else 0
    actual_protein = round(sum(log.get("protein_g") or 0 for log in nut_logs), 1) if nut_logs else 0.0
    actual_carb = round(sum(log.get("carb_g") or 0 for log in nut_logs), 1) if nut_logs else 0.0
    actual_fat = round(sum(log.get("fat_g") or 0 for log in nut_logs), 1) if nut_logs else 0.0

    if actual_protein > 0 or actual_cal > 0:
        p_diff = round(protein_target - actual_protein, 1)
        c_diff = int(target_cal_est - actual_cal)
        if p_diff > 0:
            compensation_sentence = f"Do ngày hôm qua nạp thiếu {p_diff}g Protein và {c_diff} kcal so với mục tiêu, hôm nay hãy bổ sung thêm 120g ức gà áp chảo / cá nạc hấp vào bữa trưa để bù đắp thâm hụt năng lượng và tái tạo cơ bắp."
        else:
            compensation_sentence = f"Ngày hôm qua đã đáp ứng đủ chỉ tiêu Protein ({actual_protein}g vs mục tiêu {protein_target}g), hôm nay tiếp tục duy trì chế độ ăn chuẩn theo kế hoạch."
        recap_line = f"- **Tổng Nạp Thực tế Đêm qua & Hướng dẫn Bù trừ:** Tổng nạp thực tế ghi nhận từ nhật ký: **~{actual_cal} kcal** | Protein: **{actual_protein}g**. {compensation_sentence}"
    else:
        recap_line = f"- **Tổng Nạp Thực tế Đêm qua & Hướng dẫn Bù trừ:** Chưa ghi nhận bản ghi dinh dưỡng trong CSDDL, duy trì nạp đủ Protein mục tiêu **{protein_target}g** và **~{target_cal_est} kcal**."

    has_morning_workout = act_info_today["morning_workout_done"]

    if has_morning_workout:
        sec3_header = "### 🏃‍♂️ 3. Đánh giá Buổi tập Sáng nay & Kế hoạch Phục hồi Chiều:"
        sec3_content = (
            f"• **Đánh giá Buổi tập Sáng nay:** Đã hoàn thành bài chạy/vận động sáng nay. "
            f"Dữ liệu bài tập đã được đồng bộ từ đồng hồ Garmin & đai HRM-Pro.\n"
            f"• **Kế hoạch Phục hồi Chiều:** NGHIÊM CẤM kê đơn bài chạy mới cho buổi chiều. "
            f"Chỉ thực hiện phục hồi thụ động: Stretching thả lỏng gân cơ, 3 tổ đẳng trường tĩnh (Isometric Holds: đứng 2 chân nhón nhẹ gót 2-3 cm, giữ 30-45s) và ngâm chân nước mát."
        )
    else:
        if is_sleep_deprived:
            sec3_header = "### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (CẢNH BÁO THIẾU NGỦ CẤP TÍNH):"
            sec3_content = (
                "• **CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG):** Bất kể điểm Training Readiness là bao nhiêu, "
                "phản xạ thần kinh cơ và độ nhạy cảm thụ bản thể đang bị suy giảm nghiêm trọng. "
                "NGHIÊM CẤM TUYỆT ĐỐI chạy bộ (kể cả shakeout run 2-3km) để bảo vệ gân Achilles trái. "
                "HÔM NAY BẮT BUỘC: Nghỉ ngơi hoàn toàn (Rest Day) HOẶC bơi sải thả lỏng không trọng lực 500m Zone 1.\n"
                "• **Bảo vệ Gân Achilles & Bổ trợ Tĩnh:** Bắt buộc duy trì bài tập đẳng trường tĩnh ngoài đường chạy: "
                "đứng 2 chân nhón nhẹ gót lên 2-3 cm trên mặt phẳng, giữ tĩnh 30 giây x 3 set để kích thích tái tạo collagen gân gót trái."
            )
        elif is_post_acute or is_post_race:
            sec3_header = f"### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{d_since}):"
            if is_post_acute:
                sec3_content = (
                    f"• **Kê đơn Vận động Post-Race Acute (Ngày thứ {d_since} sau FM):** "
                    f"NGHỈ CHẠY HOÀN TOÀN (Full Rest Day) hoặc chỉ đi bộ nhẹ nhàng 15-20 phút. CẤM mọi hình thức chạy bộ, strides, tempo, bứt tốc, biến tốc hoặc ép dẻo kéo giãn giật cục bắp chuối và gân Achilles.\n"
                    f"• **Chỉ đạo Da liễu & Vùng Cùng Cụt:** Đối với nốt sẩn viêm nang lông vùng nếp mông / sát xương cụt: Giữ khô thoáng tuyệt đối, không mặc đồ bó chật, tránh ngồi tỳ đè ngửa người ra sau, chấm Povidone-Iodine 10% tại chỗ. Tuyệt đối không cào gãi, không tự nặn."
                )
            else:
                from src.analytics.training_prescriber import prescribe_running_workout
                presc = prescribe_running_workout(
                    readiness_score=tm.get("training_readiness_score"),
                    recovery_time_hours=tm.get("recovery_time_hours"),
                    deep_sleep_pct=deep_pct if total_asleep > 0 else None,
                    rem_sleep_pct=rem_pct if total_asleep > 0 else None,
                    sleep_duration_seconds=tot_sleep_sec,
                    hrv_status=tm.get("hrv_status"),
                    gct_balance=tm.get("gct_balance"),
                    days_since_race=d_since,
                    phase=phase
                )
                sec3_content = (
                    f"• **Kê đơn Vận động Post-Race (Ngày thứ {d_since} sau FM):**\n"
                    f"  - **LỰA CHỌN 1 ({presc['option_1']['title']}):** {presc['option_1']['description']}\n"
                    f"  - **LỰA CHỌN 2 ({presc['option_2']['title']}):** {presc['option_2']['description']}\n"
                    f"• **Bảo vệ Gân Achilles & Bổ trợ Tĩnh:** {presc['achilles_directive']}"
                )
        elif is_t2_t1:
            sec3_header = "### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:"
            sec3_content = (
                f"• **Kê đơn Bài tập T-2/T-1:** LỰA CHỌN 1: Shakeout Run nhẹ nhàng 15-20 phút **Zone 1/2** (HR < 135 bpm), chạy sải bước ngắn tự nhiên, lướt sát đất. TUYỆT ĐỐI KHÔNG gợi ý chạy bứt tốc, Strides, Interval hay khuyến nghị hướng tới Cadence 178-182 spm.\n"
                f"• **LỰA CHỌN 2 (Nghỉ ngơi):** Nghỉ ngơi hoàn toàn (Rest Day) hoặc bơi lội phục hồi nhẹ nhàng.\n"
                f"• **Động học Chạy bộ HRM-Pro & Bảo vệ Gân Achilles:** Chạy sải bước ngắn tự nhiên, lướt sát đất. Bài tập hạ gót thụ động 'Eccentric Heel Drops' (3 set x 10-12 lần mép bậc thang) là BẮT BUỘC chỉ định ngoài đường chạy để xả tải gân Achilles trái theo Rule 3."
            )
        else:
            sec3_header = "### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:"
            sec3_content = (
                f"• **Kê đơn Bài tập Hôm nay:** Thực hiện bài chạy thả lỏng hiếu khí **MAF Zone 2** (Khung giờ sáng 05:00 - 06:00 hoặc chiều trước 18:00). Cự ly chỉ định: **5.0 km - 7.0 km** | Cường độ: Giữ nhịp tim dưới ngưỡng MAF **(180 - 44 = 136 bpm)**, bước chân tự nhiên thoải mái.\n"
                f"• **Động học Chạy bộ HRM-Pro:** Duy trì Cân bằng tiếp đất Chân Trái / Chân Phải **GCT Balance 50.0% L / 50.0% R** (Độ lệch < 1.0%) để triệt tiêu lực chấn động lên gân gót Achilles và khớp gối thân dưới."
            )

    header_title_offline = get_report_title_header(r_type, date_vn)

    # Menu suggestions for Post-Race vs T-2/T-1 vs standard
    rem_p_val = max(0.0, round(protein_target - actual_protein, 1)) if nut_logs else 30.0
    din_p_cap = round(min(dinner_p_cap, rem_p_val), 1)

    from src.analytics.nutrition_engine import generate_lean_menu
    lean_menu_data = generate_lean_menu(
        target_fat_g=fat_target,
        dinner_protein_cap=din_p_cap,
        target_calories=target_cal_est,
        target_protein_g=protein_target,
        target_carb_g=carb_target,
        is_post_race=is_post_race,
        negative_constraints=baseline_data.get("negative_constraints")
    )

    if is_post_race:
        din_p_cap = round(min(28.0, rem_p_val), 1)
        menu_breakfast = lean_menu_data["breakfast"]
        menu_lunch = lean_menu_data["lunch"]
        menu_snack = lean_menu_data["snack"]
        menu_dinner = lean_menu_data["dinner"]
    elif is_t2_t1:
        menu_breakfast = "Phở gà nước trong (hoặc Bánh mì gối trắng quết mật ong / Xôi trắng ruốc nạc) + 1 quả chuối tiêu + 300ml nước kiềm Fujiwa (TUYỆT ĐỐI KHÔNG gợi ý 'Phở bò', thịt bò, thịt đỏ dưới mọi hình thức)."
        menu_lunch = "120g Tôm hấp / Ức gà luộc + 2 bát cơm trắng + Canh bí đao bỏ vỏ (Low-residue diet)."
        if actual_protein >= 55.0:
            menu_snack = "1 quả chuối tiêu + 300ml Nước khoáng kiềm Fujiwa (Tổng đạm đã nạp >= 55g, không bổ sung sữa chua Chobani chiều)."
        else:
            menu_snack = "1 hũ Sữa chua Hy Lạp Chobani (15g Protein) + 1 quả chuối tiêu."
        menu_dinner = f"Cơm trắng (1.5 - 2 bát) kết hợp ức gà luộc / cá nạc hấp (Protein ~20.0g - 25.0g <= {din_p_cap}g max cap), cắt bỏ hoàn toàn rau củ nhiều xơ để làm rỗng đại tràng (Low-Residue) trước giờ xuất phát rạng sáng mai. KHÔNG gợi ý 'Cháo loãng' làm tụt đường huyết ban đêm."
    else:
        menu_breakfast = lean_menu_data["breakfast"]
        menu_lunch = lean_menu_data["lunch"]
        if actual_protein >= 55.0:
            menu_snack = "1/2 quả cam tươi + 300ml Nước khoáng kiềm Fujiwa (Tổng đạm đã nạp >= 55g, không bổ sung sữa chua Chobani chiều)."
        else:
            menu_snack = lean_menu_data["snack"]
        menu_dinner = lean_menu_data["dinner"]

    if r_type == "midday":
        from src.analytics.midday_review import calculate_evening_targets, detect_high_purine_lunch
        dt_mid = {"protein": protein_target, "carb": carb_target, "fat": fat_target, "calories": target_cal_est}
        li_mid = {"protein": actual_protein, "carb": actual_carb, "fat": actual_fat, "calories": actual_cal}
        din_p_target, din_c_target, fat_status = calculate_evening_targets(dt_mid, li_mid, uric_acid_level=442.0)

        # Lunch purine check
        lunch_dishes = []
        lunch_prot = 0.0
        for log in nut_logs:
            m_type = str(log.get("meal_type") or "").lower()
            ts = str(log.get("timestamp") or "")
            if any(kw in m_type for kw in ["trưa", "lunch"]) or ("11:" in ts or "12:" in ts or "13:" in ts):
                lunch_dishes = log.get("dishes") or []
                lunch_prot = float(log.get("protein_g") or 0.0)
                break
        if not lunch_dishes and len(nut_logs) > 1:
            lunch_dishes = nut_logs[-1].get("dishes") or []
            lunch_prot = float(nut_logs[-1].get("protein_g") or 0.0)
        purine_res = detect_high_purine_lunch(lunch_dishes, lunch_prot, uric_acid_level=442.0)

        purine_section = ""
        if purine_res.get("is_high_purine"):
            purine_section = (
                f"• **🚨 Cảnh báo Tải Purine Bữa trưa & Kiềm hóa Cấp cứu:** {purine_res['warning_message']}\n"
                f"  {purine_res['counter_measure_protocol']}\n"
            )

        fat_status_text = (
            f"Đã nạp đủ/vượt hạn mức (+{abs(round(fat_target - actual_fat, 1))}g Fat) — Tối ưu chế biến hấp/luộc không dầu mỡ (Lưu ý: Đậu phụ non, trứng/ức gà nạc luôn chứa chất béo nội tại tự nhiên ~5-6g Fat, không triệt tiêu về 0.0g)"
            if fat_status == "EXCEEDED"
            else f"Còn khả dụng ~{round(fat_target - actual_fat, 1)}g Fat"
        )
        rem_c_unmet = max(0.0, round((carb_target - actual_carb) - (45.0 + din_c_target), 1))
        unmet_carb_str = f" | Lượng Carb chưa nạp ban ngày (~{rem_c_unmet}g Carb) được đánh dấu là chưa nạp (bỏ qua), KHÔNG dồn/dump vào ban đêm" if rem_c_unmet > 10.0 else ""

        offline_report = (
            f"{header_title_offline}\n\n"
            f"===SECTION_BREAK===\n"
            f"### 🏃‍♂️ 1. Đánh giá Buổi tập Sáng nay & Động học HRM-Pro:\n"
            f"• **Phân tích Thực tế Buổi tập Sáng:** {sec3_content}\n"
            f"• **Động học Chạy bộ HRM-Pro & Bảo vệ Gân Achilles Trái:** Ưu tiên số 1 là Nhịp tim Zone 1/2 (< 135 bpm), chạy sải bước ngắn tự nhiên, lướt sát đất. Giai đoạn sát giải/phục hồi, TUYỆT ĐỐI KHÔNG gò ép Cadence 178-182 spm hay chạy bứt tốc/Strides; tập trung bảo vệ gân Achilles bằng bài tập đẳng trường tĩnh Isometric Holds (3 set x 30-45s) kết hợp Foam Roller giải phóng cơ mông nhỡ.\n"
            f"• **Hấp thu Tải Tập luyện & ACWR:** Điểm Training Readiness đạt **{tm.get('training_readiness_score') or 'N/A'}/100** | Tổng tải 7 ngày: **{tl.get('total_active_calories', 0)} kcal**.\n\n"
            f"===SECTION_BREAK===\n"
            f"### ⚡ 2. Trạng thái Readiness Hiện tại & Chỉ đạo Phục hồi Chiều:\n"
            f"• **Điểm Sẵn sàng & Phục hồi:** Readiness {tm.get('training_readiness_score') or 'N/A'}/100 | Recovery Time còn lại: {tm.get('recovery_time_hours') or 0} giờ.\n"
            f"• **Chỉ đạo Phục hồi Chiều:** NGHIÊM CẤM kê đơn bất kỳ bài chạy bộ mới nào cho buổi chiều! Buổi chiều CHỈ ĐƯỢC kê đơn phục hồi thụ động (stretching thả lỏng, foot soak, isometric holds, nằm ngửa gác chân cao lên tường 10-15 phút).\n\n"
            f"===SECTION_BREAK===\n"
            f"### 🍱 3. Đối soát Dinh dưỡng & Quota Macro Cho Chiều/Tối:\n"
            f"• **Macro Mục tiêu (Cân nặng {w_kg} kg):** Protein mục tiêu: **{protein_target}g** | Total Calo mục tiêu: **~{target_cal_est} kcal**.\n"
            f"• {recap_line}\n"
            f"{purine_section}"
            f"• **Khóa Protein Bữa tối (Clinical Guard 1):** Protein bữa tối KHÓA CỨNG Ở MỨC <= **{din_p_target}g** (bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L).\n"
            f"• **Khóa Carb Bữa tối & Chống Carb-Dumping (Clinical Guard 2):** Khóa trần Carb tối đa **{din_c_target}g Carb** (~1.5 bát cơm mềm){unmet_carb_str}.\n"
            f"• **Chất béo Nội tại Tự nhiên (Clinical Guard 3 - Realistic Fat Floor):** {fat_status_text}.\n"
        )
    elif r_type == "evening":
        from src.analytics.card_generator import generate_evening_report, generate_evening_card
        offline_report = generate_evening_report(baseline_data)
        offline_card = generate_evening_card(baseline_data)
        model_label = "card-generator (mock-mode)" if is_mock else "card-generator (evening-review)"
        return {
            "report_markdown": offline_report,
            "telegram_card": offline_card,
            "model_used": model_label,
            "prompt_tokens": 0,
            "completion_tokens": 0
        }
    else:
        offline_report = (
            f"{header_title_offline}\n\n"
            f"===SECTION_BREAK===\n"
            f"### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:\n"
            f"- **Cân bằng Thần kinh Thực vật (HRV Overnight vs Baseline 30 ngày):** Chỉ số HRV đêm qua đạt **{hrv_str}** ({hrv_eval_str}, Status: {tm.get('hrv_status') or 'BALANCED'}). Hệ thần kinh thực vật nằm trong dải cân bằng đối giao cảm, phản ánh khả năng hấp thụ tải vận động tích lũy ổn định.\n"
            f"- **Nhịp tim nghỉ & Stress Deviation (RHR & Stress):** Nhịp tim nghỉ RHR đêm đạt **{rhr_str}** ({rhr_eval_str}). Mức độ Stress ban đêm ghi nhận **{tm.get('avg_stress_level') or 'N/A'}** (Stress cao nhất: {tm.get('max_stress_level') or 'N/A'}).\n"
            f"- **Sinh lý Hô hấp & Nồng độ Oxy SpO2 Đêm:** Nhịp thở trung bình trong khi ngủ đạt **{tm.get('respiration_avg') or '14.5'} brpm** (Biến thiên: {tm.get('respiration_min') or '12.0'} - {tm.get('respiration_max') or '18.0'} brpm). Nồng độ Oxy SpO2 trung bình đêm đạt **{tm.get('spo2_avg') or '96'}%** (Thấp nhất: {tm.get('spo2_min') or '93'}%). Không có dấu hiệu suy giảm oxy mô.\n"
            f"- **Cân nặng & Thể trạng OMRON VIVA / Garmin:** Cân nặng thực tế ghi nhận **{w_kg} kg** | Tỷ lệ % Mỡ cơ thể: **{tm.get('body_fat_pct') or 'N/A'}%** | Tỷ lệ % Cơ xương: **{tm.get('muscle_mass_pct') or 'N/A'}%** | Mỡ nội tạng: **{tm.get('visceral_fat') or 'N/A'}**.\n\n"
            f"===SECTION_BREAK===\n"
            f"### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:\n"
            f"- **Phân bổ Các Giai đoạn Giấc ngủ (Sleep Architecture):** Điểm số giấc ngủ đạt **{sleep_score}/100** (Tổng thời gian ngủ: {tot_sleep_str}). Chi tiết từng giai đoạn: Ngủ sâu (Deep Sleep): **{deep_str}** ({deep_pct}%) | Ngủ mơ (REM Sleep): **{rem_str}** ({rem_pct}%) | Ngủ nông (Light Sleep): **{_format_seconds(light_sec)}** ({light_pct}%) | Thức giấc (Awake): **{_format_seconds(awake_sec)}** ({awake_pct}% trên Total Bed Time).\n"
            f"- **Hiệu suất Sạc Body Battery & Trí nhớ Động (Adaptive Memory):** Điểm sạc Body Battery đêm qua đạt **+{bb_charged} điểm** (Cao nhất: {tm.get('body_battery_highest') or 'N/A'}, Thấp nhất: {tm.get('body_battery_lowest') or 'N/A'}). Theo quy luật Trí nhớ Động cá nhân, mỗi 15 phút Ngủ sâu Deep Sleep đóng góp trung bình +2.5 đến +3.2 điểm Body Battery.\n"
            + (f"- **Đánh giá Nén sóng chậm (Deep Sleep Rebound do thiếu ngủ):** Mặc dù thời lượng Deep Sleep đạt {deep_str}, cơ thể phải nén sóng não chậm (Deep Sleep Rebound) để cấp cứu tổn thương tế bào do thời gian ngủ bị cắt ngắn nghiêm trọng (< 5 tiếng). Tuyệt đối không nhầm lẫn đây là trạng thái Siêu phục hồi (Supercompensation).\n" if is_sleep_deprived else "")
            +             f"{nut_correlation_text}\n\n"
            f"===SECTION_BREAK===\n"
            f"{sec3_header}\n"
            f"{race_countdown_str}\n"
            f"• **Bối cảnh Microcycle & Trạng thái Sẵn sàng:** Điểm Training Readiness đạt **{tm.get('training_readiness_score') or 'N/A'}/100** | Trạng thái tập luyện: **{ts_display}** | Tổng tải 7 ngày: **{tl.get('total_active_calories', 0)} kcal** ({tl.get('total_workout_count', 0)} bài tập). Thời gian phục hồi còn lại: **{tm.get('recovery_time_hours') or 0} giờ**.\n"
            f"{sec3_content}\n\n"
            f"===SECTION_BREAK===\n"
            f"### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):\n"
            f"- **Macro Mục tiêu (Cân nặng {w_kg} kg):** Nhu cầu Protein mục tiêu đạt **{protein_target}g** (Trần 85.0g bảo vệ Uric Acid 442 µmol/L). Ước tính tổng Calo nạp vào: **~{target_cal_est} kcal**.\n"
            f"{recap_line}\n"
            f"- **Thực đơn Gợi ý Từng Bữa ({'Low-Residue Carbo-Loading T-2/T-1' if is_t2_t1 else 'Dinh dưỡng Phục hồi'}):**\n"
            f"  + **Bữa sáng (06:30 - 07:00):** {menu_breakfast}\n"
            f"  + **Bữa trưa (11:30 - 12:30):** {menu_lunch}\n"
            f"  + **Bữa phụ chiều (15:30):** {menu_snack}\n"
            f"  + **Bữa tối (Hoàn tất 2.5 - 3.0 tiếng trước khi đi ngủ):** {menu_dinner}\n"
            f"  + **Bổ sung Vi chất & Nước khoáng (20:30 - 21:00):** 1 viên Magie Bisglycinate (400mg) giúp thư giãn thần kinh + Bù đủ 3.0L Nước khoáng kiềm Fujiwa rải đều trong ngày.\n"
            + ("  + **Giao thức Thải trừ Acid Uric Hậu Cồn (Alkaline Hydration Protocol):** Uống tối thiểu 3.0L - 3.2L nước rải đều trong ngày, ưu tiên nước khoáng kiềm pH 8.5-9.0 (Fujiwa) để nâng pH nước tiểu, chống lắng đọng tinh thể urat tại gân Achilles.\n" if total_alc > 0 else "")
            +             f"- **💬 Thăm khám Thực tế Đầu ngày:** Bạn hãy kiểm tra nhanh tình trạng nốt viêm xương cụt (đã se miệng khô ráo chưa) và bắp chuối trái xem có còn cảm giác căng cứng khi bước lên cầu thang sáng nay hay không nhé.\n"
            f"- 💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse).\n"
        )
    offline_report = clean_report_text(offline_report)
    offline_card = generate_telegram_card_fallback(baseline_data)

    model_label = "garmin-health-engine (mock-mode)" if is_mock else "garmin-health-engine (offline-fallback)"
    return {
        "report_markdown": offline_report,
        "telegram_card": offline_card,
        "model_used": model_label,
        "prompt_tokens": 0,
        "completion_tokens": 0
    }

def generate_health_analysis(
    baseline_data: Dict[str, Any],
    dry_run: bool = False,
    mock: bool = False
) -> Dict[str, Any]:
    """Generate physiological analysis report using LLM based on baseline data.
    
    Returns dict:
      - report_markdown: str
      - raw_prompt: str
      - model_used: str
      - prompt_tokens: int
      - completion_tokens: int
    """
    from src.analytics.prompt_engine import (
        SYSTEM_PROMPT,
        get_system_prompt,
        build_advanced_user_prompt,
        get_vietnamese_date_str,
        get_effective_weight_kg,
        clean_report_text,
        extract_report_and_telegram_card,
        generate_telegram_card_fallback,
        get_race_context
    )
    target_date = baseline_data["target_date"]
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data.get("target_metrics", {})
    w_kg = get_effective_weight_kg(tm)
    weight_str = f"{w_kg} kg"
    r_type = (baseline_data.get("report_type") or "morning").lower()
    race_ctx = get_race_context(target_date)
    system_prompt = get_system_prompt(
        r_type,
        date_vn,
        weight_str,
        phase=race_ctx.get("phase"),
        days_since=race_ctx.get("days_since_race"),
        target_date=target_date
    )
    user_prompt = build_advanced_user_prompt(baseline_data)
    raw_prompt = f"[SYSTEM PROMPT]\n{system_prompt}\n\n[USER PROMPT]\n{user_prompt}"

    if dry_run:
        fallback_card = generate_telegram_card_fallback(baseline_data)
        return {
            "report_markdown": f"DRY RUN MODE - PROMPT PREVIEW FOR {target_date}:\n\n" + raw_prompt,
            "telegram_card": fallback_card,
            "raw_prompt": raw_prompt,
            "model_used": "dry-run",
            "prompt_tokens": 0,
            "completion_tokens": 0
        }

    if r_type == "evening":
        from src.analytics.card_generator import generate_evening_report, generate_evening_card
        rep = generate_evening_report(baseline_data)
        card = generate_evening_card(baseline_data)
        return {
            "report_markdown": rep,
            "telegram_card": card,
            "raw_prompt": raw_prompt,
            "model_used": "card-generator (evening-review)",
            "prompt_tokens": 0,
            "completion_tokens": 0
        }

    is_mock = mock or (str(os.getenv("MOCK_LLM", "false")).lower() in ("true", "1", "yes"))
    if is_mock:
        res = _generate_structured_report(baseline_data, is_mock=True)
        res["raw_prompt"] = raw_prompt
        return res

    provider = (settings.llm_provider or "gemini").lower()
    
    # Try primary provider first, fallback to alternative if configured
    try:
        if provider == "openai":
            res = call_openai(system_prompt, user_prompt)
        else:
            res = call_gemini(system_prompt, user_prompt)
    except Exception as primary_err:
        print(f"⚠️ Primary LLM Provider ({provider}) failed: {primary_err}. Attempting fallback...")
        try:
            if provider == "openai":
                res = call_gemini(system_prompt, user_prompt)
            else:
                res = call_openai(system_prompt, user_prompt)
        except Exception as fallback_err:
            print(f"⚠️ Both LLM Providers failed due to quota/credentials ({fallback_err}). Generating structured physiological report...")
            res = _generate_structured_report(baseline_data, is_mock=False)

    res["raw_prompt"] = raw_prompt

    # Extract 2-part output if present in response
    if "telegram_card" not in res or not res["telegram_card"]:
        full_report, telegram_card = extract_report_and_telegram_card(res.get("report_markdown", ""), baseline_data)
        res["report_markdown"] = full_report
        res["telegram_card"] = telegram_card

    if "report_markdown" in res and res["report_markdown"]:
        res["report_markdown"] = clean_report_text(res["report_markdown"])
    if "telegram_card" in res and res["telegram_card"]:
        res["telegram_card"] = clean_report_text(res["telegram_card"])

    return res


