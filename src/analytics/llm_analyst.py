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
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.5-pro",
        "gemini-flash-latest",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-flash-lite-latest",
        "gemini-3.6-flash"
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

from .prompt_engine import SYSTEM_PROMPT, build_advanced_user_prompt, get_vietnamese_date_str

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
    target_date = baseline_data["target_date"]
    date_vn = get_vietnamese_date_str(target_date)
    system_prompt = SYSTEM_PROMPT.format(date=date_vn)
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
            raise RuntimeError(
                f"Both LLM Providers failed. Primary ({provider}): {primary_err} | Fallback: {fallback_err}"
            )

    res["raw_prompt"] = raw_prompt
    return res
