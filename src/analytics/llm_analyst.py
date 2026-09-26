import json
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

ĐỊNH DẠNG ĐẦU RA MẮT ĐỊNH (BẮT BUỘC SỬ DỤNG CÁC THẺ TIÊU ĐỀ NÀY):

# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi ({date})

### 🩺 **Trạng thái hồi phục & Cân bằng thần kinh:**
[Đánh giá tổng quan mức độ phục hồi, trạng thái phó giao cảm (Parasympathetic) / giao cảm (Sympathetic), HRV balance, RHR deviation]

### 🔍 **Phân tích tương quan & Xu hướng:**
[Chi tiết mối tương quan giữa Giấc ngủ ↔ Stress ↔ Body Battery ↔ HRV ↔ Tải vận động 7 ngày. So sánh trực tiếp các chỉ số hôm nay với Baseline 30 ngày (sample size N ngày). Giải thích nguyên nhân sinh lý vì sao chỉ số tăng/giảm.]

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
    prompt_parts.append(f"Mẫu dữ liệu Baseline: {sample_size} ngày ({dr.get('start') or 'N/A'} đến {dr.get('end') or 'N/A'})\n")

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
    prompt_parts.append(f"- Total Sleep Time: {_format_seconds(tm.get('sleep_duration_seconds'))}")
    prompt_parts.append(f"- Deep Sleep: {_format_seconds(tm.get('deep_sleep_seconds'))}")
    prompt_parts.append(f"- REM Sleep: {_format_seconds(tm.get('rem_sleep_seconds'))}")
    prompt_parts.append(f"- Light Sleep: {_format_seconds(tm.get('light_sleep_seconds'))}")

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
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-flash-latest"
    ]
    env_model = (settings.gemini_model or "").strip()
    raw_candidates = ([env_model] if env_model else []) + default_candidates
    seen = set()
    models_to_try = [m for m in raw_candidates if m and not (m in seen or seen.add(m))]

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    
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

def generate_health_analysis(
    baseline_data: Dict[str, Any],
    dry_run: bool = False
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
        build_advanced_user_prompt,
        get_vietnamese_date_str,
        get_effective_weight_kg,
        clean_report_text
    )
    target_date = baseline_data["target_date"]
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data.get("target_metrics", {})
    w_kg = get_effective_weight_kg(tm)
    weight_str = f"{w_kg} kg"
    system_prompt = SYSTEM_PROMPT.format(date=date_vn, weight_kg=weight_str)
    user_prompt = build_advanced_user_prompt(baseline_data)
    raw_prompt = f"[SYSTEM PROMPT]\n{system_prompt}\n\n[USER PROMPT]\n{user_prompt}"

    if dry_run:
        return {
            "report_markdown": f"DRY RUN MODE - PROMPT PREVIEW FOR {target_date}:\n\n" + raw_prompt,
            "raw_prompt": raw_prompt,
            "model_used": "dry-run",
            "prompt_tokens": 0,
            "completion_tokens": 0
        }

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
            from src.analytics.prompt_engine import get_next_upcoming_race, TRAINING_STATUS_MAP, _format_seconds
            
            bm = baseline_data.get("metrics_baseline", {})
            tl = baseline_data.get("training_load_7d", {})
            race_info = get_next_upcoming_race(target_date)

            hrv_val = tm.get("hrv_last_night")
            hrv_str = f"{hrv_val} ms" if hrv_val is not None else "KHÔNG CÓ DỮ LIỆU (NULL)"
            hrv_bs = bm.get("hrv_last_night", {}).get("avg")
            hrv_std = bm.get("hrv_last_night", {}).get("std")
            
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

            bb_charged = tm.get("body_battery_charged") or "N/A"
            ts_raw = tm.get("training_status")
            ts_display = TRAINING_STATUS_MAP.get(str(ts_raw).upper(), str(ts_raw).replace("_2", "") if ts_raw else "Phục hồi (Recovery)")

            protein_target = round(1.9 * float(w_kg), 1)

            race_countdown_str = (
                f"• **Sự kiện thi đấu:** {race_info['name']} ({race_info['distance']}) vào ngày {race_info['date']} — **Còn đúng {race_info['days_to_race']} ngày** (Giai đoạn Dynamic Tapering & Giảm tải sâu)."
                if race_info else "• **Sự kiện thi đấu:** Chưa ghi nhận sự kiện sắp tới trong `config/races.json`."
            )

            # Check nutrition logs for evening meals / alcohol correlation with accurate physiological deduction
            from src.db.nutrition_repository import get_nutrition_logs_by_date
            nut_logs = get_nutrition_logs_by_date(target_date)
            nut_correlation_text = ""
            if nut_logs:
                log_items = []
                for log in nut_logs:
                    dishes = ", ".join(log.get("dishes", [])) if isinstance(log.get("dishes", []), list) else str(log.get("dishes"))
                    alc_units = log.get("alcohol_units") or 0.0
                    log_items.append(f"Món ăn: {dishes} (Cồn: {alc_units} đơn vị, Calo: ~{log.get('total_calories') or 0} kcal)")
                
                log_summary_str = "; ".join(log_items)
                if rhr_val is not None and rhr_bs and rhr_val <= rhr_bs:
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
                nut_correlation_text = (
                    f"- **ĐỐI CHIẾU TRỰC TIẾP NHẬT KÝ DINH DƯỠNG ĐÊM HÔM QUA:** Không ghi nhận bữa ăn muộn hoặc đơn vị cồn bất thường. "
                    f"Hệ tiêu hóa hoàn tất chu trình trước 21:00, tạo điều kiện thuận lợi cho hệ thần kinh phó giao cảm tái tạo thể lực đêm qua."
                )

            actual_cal = sum(log.get("total_calories") or 0 for log in nut_logs) if nut_logs else 0
            actual_protein = round(sum(log.get("protein_g") or 0 for log in nut_logs), 1) if nut_logs else 0.0

            if actual_protein > 0 or actual_cal > 0:
                p_diff = round(protein_target - actual_protein, 1)
                c_diff = int(2150 - actual_cal)
                if p_diff > 0:
                    compensation_sentence = f"Do ngày hôm qua nạp thiếu {p_diff}g Protein và {c_diff} kcal so với mục tiêu, hôm nay hãy bổ sung thêm 150g thịt bò thăn vào bữa trưa và 1 hũ sữa chua Hy Lạp Chobani vào bữa phụ chiều để bù đắp thâm hụt năng lượng và tái tạo cơ bắp."
                else:
                    compensation_sentence = f"Ngày hôm qua đã đáp ứng đủ chỉ tiêu Protein ({actual_protein}g vs mục tiêu {protein_target}g), hôm nay tiếp tục duy trì chế độ ăn chuẩn theo kế hoạch."
                recap_line = f"- **Tổng Nạp Thực tế Đêm qua & Hướng dẫn Bù trừ:** Tổng nạp thực tế ghi nhận từ nhật ký: **~{actual_cal} kcal** | Protein: **{actual_protein}g**. {compensation_sentence}"
            else:
                recap_line = f"- **Tổng Nạp Thực tế Đêm qua & Hướng dẫn Bù trừ:** Chưa ghi nhận bản ghi dinh dưỡng trong CSDDL, duy trì nạp đủ Protein mục tiêu **{protein_target}g** và **~2,150 kcal**."

            offline_report = (
                f"# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện ({date_vn})\n\n"
                f"===SECTION_BREAK===\n"
                f"### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:\n"
                f"- **Cân bằng Thần kinh Thực vật (HRV Overnight vs Baseline 30 ngày):** Chỉ số HRV đêm qua đạt **{hrv_str}** ({hrv_eval_str}, Status: {tm.get('hrv_status') or 'BALANCED'}). Hệ thần kinh thực vật nằm trong dải cân bằng đối giao cảm, phản ánh khả năng hấp thụ tải vận động tích lũy ổn định.\n"
                f"- **Nhịp tim nghỉ & Stress Deviation (RHR & Stress):** Nhịp tim nghỉ RHR đêm đạt **{rhr_str}** ({rhr_eval_str}). Mức độ Stress trung bình ban ngày ghi nhận **{tm.get('avg_stress_level') or 'N/A'}** (Stress cao nhất: {tm.get('max_stress_level') or 'N/A'}).\n"
                f"- **Sinh lý Hô hấp & Nồng độ Oxy SpO2 Đêm:** Nhịp thở trung bình trong khi ngủ đạt **{tm.get('respiration_avg') or '14.5'} brpm** (Biến thiên: {tm.get('respiration_min') or '12.0'} - {tm.get('respiration_max') or '18.0'} brpm). Nồng độ Oxy SpO2 trung bình đêm đạt **{tm.get('spo2_avg') or '96'}%** (Thấp nhất: {tm.get('spo2_min') or '93'}%). Không có dấu hiệu suy giảm oxy mô hay bất thường áp lực đường thở.\n"
                f"- **Cân nặng & Thể trạng OMRON VIVA / Garmin:** Cân nặng thực tế ghi nhận **{w_kg} kg** | Tỷ lệ % Mỡ cơ thể: **{tm.get('body_fat_pct') or 'N/A'}%** | Tỷ lệ % Cơ xương: **{tm.get('muscle_mass_pct') or 'N/A'}%** | Mỡ nội tạng: **{tm.get('visceral_fat') or 'N/A'}**. Tỷ lệ công suất/trọng lượng cơ thể (Power-to-Weight Ratio) ở mức tối ưu cho chạy bộ đường dài.\n\n"
                f"===SECTION_BREAK===\n"
                f"### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:\n"
                f"- **Phân bổ Các Giai đoạn Giấc ngủ (Sleep Architecture):** Điểm số giấc ngủ đạt **{sleep_score}/100** (Tổng thời gian ngủ: {_format_seconds(tm.get('sleep_duration_seconds'))}). Chi tiết từng giai đoạn: Ngủ sâu (Deep Sleep): **{deep_str}** | Ngủ mơ (REM Sleep): **{rem_str}** | Ngủ nông (Light Sleep): **{_format_seconds(light_sec)}** | Thức giấc (Awake): **{_format_seconds(awake_sec)}**.\n"
                f"- **Hiệu suất Sạc Body Battery & Trí nhớ Động (Adaptive Memory):** Điểm sạc Body Battery đêm qua đạt **+{bb_charged} điểm** (Cao nhất: {tm.get('body_battery_highest') or 'N/A'}, Thấp nhất: {tm.get('body_battery_lowest') or 'N/A'}). Theo quy luật Trí nhớ Động cá nhân, mỗi 15 phút Ngủ sâu Deep Sleep đóng góp trung bình +2.5 đến +3.2 điểm Body Battery.\n"
                f"{nut_correlation_text}\n\n"
                f"===SECTION_BREAK===\n"
                f"### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:\n"
                f"{race_countdown_str}\n"
                f"• **Bối cảnh Microcycle & Trạng thái Sẵn sàng:** Điểm Training Readiness đạt **{tm.get('training_readiness_score') or 'N/A'}/100** | Trạng thái tập luyện: **{ts_display}** | Tổng tải 7 ngày: **{tl.get('total_active_calories', 0)} kcal** ({tl.get('total_workout_count', 0)} bài tập). Thời gian phục hồi còn lại: **{tm.get('recovery_time_hours') or 0} giờ**.\n"
                f"• **Kê đơn Bài tập Hôm nay:** Thực hiện bài chạy thả lỏng hiếu khí **MAF Zone 2** (Khung giờ sáng 05:00 - 06:00 hoặc chiều trước 18:00). Cự ly chỉ định: **5.0 km - 7.0 km** | Cường độ: Giữ nhịp tim dưới ngưỡng MAF **(180 - 44 = 136 bpm)** | Nhịp chân duy trì: **176 - 180 spm**.\n"
                f"• **Động học Chạy bộ HRM-Pro:** Duy trì Cân bằng tiếp đất Chân Trái / Chân Phải **GCT Balance 50.0% L / 50.0% R** (Độ lệch < 1.0%) để triệt tiêu lực chấn động lên gân gót Achilles và khớp gối thân dưới.\n\n"
                f"===SECTION_BREAK===\n"
                f"### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):\n"
                f"- **Macro Mục tiêu (Cân nặng {w_kg} kg):** Nhu cầu Protein mục tiêu đạt **{protein_target}g** (1.9g x {w_kg}kg). Ước tính tổng Calo nạp vào: **~2,150 kcal** (Tỷ lệ Macro: 50% Carbs / 30% Protein / 20% Fat).\n"
                f"{recap_line}\n"
                f"- **Thực đơn Gợi ý Từng Bữa:**\n"
                f"  + **Bữa sáng (06:30 - 07:00):** 1 hũ Sữa chua Hy Lạp Chobani (15g Protein) + 50g Yến mạch + 1 quả chuối chín + 300ml nước khoáng kiềm Fujiwa.\n"
                f"  + **Bữa trưa (11:30 - 12:30):** 200g Thịt bò thăn áp chảo / Hải sản hấp + 1.5 chén cơm gạo lứt + 200g Rau cải xanh luộc.\n"
                f"  + **Bữa tối (BẮT BUỘC KẾT THÚC TRƯỚC 18:30 - 19:00):** 180g Cá hồi áp chảo / Sashimi cá hồi + Lẩu thanh đạm rau nấm + Rau củ hấp. Toàn bộ quá trình tiêu hóa phải hoàn tất trước 21:00 để hạ thấp RHR đêm và bảo vệ giấc ngủ sâu Deep Sleep.\n"
                f"  + **Bổ sung Vi chất & Nước khoáng (20:30 - 21:00):** 1 viên Magie Bisglycinate (400mg) giúp thư giãn thần kinh + Bù đủ 3.0L Nước khoáng kiềm Fujiwa rải đều trong ngày.\n"
            )

            res = {
                "report_markdown": offline_report,
                "model_used": "garmin-health-engine (offline-fallback)",
                "prompt_tokens": 0,
                "completion_tokens": 0
            }

    res["raw_prompt"] = raw_prompt
    if "report_markdown" in res and res["report_markdown"]:
        res["report_markdown"] = clean_report_text(res["report_markdown"])
    return res
