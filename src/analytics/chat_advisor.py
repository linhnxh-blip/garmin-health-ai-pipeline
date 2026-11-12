import os
import re
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Union

from config.settings import settings
from src.db.connection import get_db_connection
from src.analytics.prompt_engine import (
    format_ai_metadata_footer,
    normalize_ai_engine_name,
    get_race_context,
    get_effective_weight_kg,
    get_vietnamese_date_str,
    clean_report_text
)
from src.analytics.vision_analyst import (
    create_genai_client,
    get_local_llm_endpoints
)
from src.db.nutrition_repository import (
    get_nutrition_logs_by_date,
    get_today_nutrition_summary
)
from src.analytics.nutrition_engine import calculate_daily_macros

# In-memory sliding window conversation history per chat_id: {chat_id: [{"role": "user"|"assistant", "content": "..."}]}
CHAT_HISTORIES: Dict[str, List[Dict[str, str]]] = {}
MAX_HISTORY_TURNS = 6  # Keep last 6 exchanges (12 messages)


def get_athlete_live_context(target_date: Optional[str] = None) -> str:
    """Fetch live biometrics, workout loads, race phase, and nutrition logs for today to ground the chat response."""
    now_dt = datetime.now()
    today_str = target_date or now_dt.strftime("%Y-%m-%d")
    current_time_str = now_dt.strftime("%H:%M")
    date_vn = get_vietnamese_date_str(today_str)

    # 1. Biometrics from daily_metrics
    daily_row = None
    try:
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM daily_metrics WHERE date = ?", (today_str,))
            row = c.fetchone()
            if row:
                col_names = [d[0] for d in c.description]
                daily_row = dict(zip(col_names, row))
    except Exception:
        daily_row = None

    daily_row = daily_row or {}
    w_eff = get_effective_weight_kg(daily_row)

    sleep_score = daily_row.get("sleep_score") or "N/A"
    deep_sec = daily_row.get("deep_sleep_seconds") or 0
    rem_sec = daily_row.get("rem_sleep_seconds") or 0
    light_sec = daily_row.get("light_sleep_seconds") or 0
    deep_m = round(float(deep_sec) / 60.0, 1)
    rem_m = round(float(rem_sec) / 60.0, 1)
    light_m = round(float(light_sec) / 60.0, 1)

    hrv_val = daily_row.get("hrv_last_night")
    hrv_str = f"{hrv_val} ms" if hrv_val is not None else "N/A"
    hrv_status = daily_row.get("hrv_status") or "BALANCED"
    rhr_val = daily_row.get("resting_heart_rate")
    rhr_str = f"{rhr_val} bpm" if rhr_val is not None else "N/A"
    readiness = daily_row.get("training_readiness_score") or "N/A"
    bb_charged = daily_row.get("body_battery_charged") or "N/A"
    steps = daily_row.get("total_steps") or 0
    act_cals = daily_row.get("active_calories") or 0

    # 2. Race & Training Phase
    race_ctx = get_race_context(today_str)
    phase = race_ctx.get("phase", "GENERAL_TRAINING")
    d_left = race_ctx.get("days_to_race")
    d_since = race_ctx.get("days_since_race")

    # 3. Macro targets & Live nutrition intake today
    macro_targets = calculate_daily_macros(
        weight_kg=float(w_eff),
        phase=phase,
        uric_acid_level=442.0,
        active_calories_garmin=float(act_cals),
        days_to_race=d_left,
        days_since_race=d_since
    )
    target_cal = macro_targets["target_calories"]
    target_p = macro_targets["protein_g"]
    target_c = macro_targets["carb_g"]
    target_f = macro_targets["fat_g"]

    nut_sum = get_today_nutrition_summary(today_str)
    tot_cal = nut_sum.get("total_cal", 0)
    tot_p = nut_sum.get("total_protein", 0.0)
    tot_c = nut_sum.get("total_carbs", 0.0)
    tot_f = nut_sum.get("total_fat", 0.0)

    nut_logs = get_nutrition_logs_by_date(today_str)
    logged_dishes = []
    for l in nut_logs:
        d = l.get("dishes")
        d_str = ", ".join(d) if isinstance(d, list) else str(d)
        ts_part = str(l.get("timestamp") or "").split()[-1]
        logged_dishes.append(f"{d_str} (lúc {ts_part})")
    dishes_summary = "; ".join(logged_dishes) if logged_dishes else "Chưa có món ăn nào được log hôm nay."

    # Biomechanics & ACWR
    gct_val = daily_row.get("gct_balance") or "51.0% L / 49.0% R"
    acwr_val = daily_row.get("acwr") or 1.40
    acwr_status = daily_row.get("acwr_status") or "ELEVATED_RISK"

    context_text = (
        f"📌 HỒ SƠ SINH LÝ HỌC & DINH DƯỠNG THỰC TẾ HÔM NAY ({date_vn} - Hiện tại: {current_time_str}):\n"
        f"• Thể trạng: Cân nặng {w_eff} kg | Điểm Sẵn sàng (Readiness): {readiness}/100 | Trạng thái: Tối ưu phục hồi.\n"
        f"• Giấc ngủ: Sleep Score {sleep_score}/100 | Ngủ sâu (Deep): {deep_m}m | Ngủ mơ (REM): {rem_m}m | Ngủ nông: {light_m}m.\n"
        f"• Thần kinh & Tim mạch: HRV Overnight: {hrv_str} ({hrv_status}) | Nhịp tim nghỉ (RHR): {rhr_str} | Body Battery nạp: +{bb_charged}.\n"
        f"• Tải vận động: ACWR: {acwr_val} ({acwr_status} - Cảnh báo nguy cơ quá tải nếu chạy thêm) | Bước chân: {steps:,} | Garmin Active: {act_cals} kcal.\n"
        f"• Cơ sinh học HRM-Pro: Tiếp đất lệch trái (GCT {gct_val}) -> Cần bảo vệ gân Achilles trái (duy trì Cadence 178-182 spm, làm bài tập Isometric Holds).\n"
        f"• Tình trạng Gout / Acid Uric: Uric Acid nền 442 µmol/L (sát trần EULAR 420 µmol/L) -> Tuyệt đối kiêng thịt đỏ, hải sản, nội tạng, đồ nướng; bù kiềm Fujiwa pH 8.5-9.0 (1.5L - 2.0L chiều/tối).\n"
        f"• Chăm sóc da liễu: Nốt sẩn viêm nang lông nếp mông xương cụt -> Giữ khô thoáng, mặc cotton rộng, chấm Povidone-Iodine 10% tại chỗ.\n"
        f"• Tiến độ Dinh dưỡng đã nạp: {tot_cal}/{target_cal} kcal | Protein: {tot_p}/{target_p}g | Carb: {tot_c}/{target_c}g | Fat: {tot_f}/{target_f}g.\n"
        f"• Món ăn đã ghi nhận hôm nay: {dishes_summary}."
    )
    return context_text


def build_chat_system_prompt(today_context: str) -> str:
    return (
        "Bạn là Chuyên gia Sinh lý học Thể thao & Huấn luyện viên Phục hồi Cá nhân (Personal Sports Physiologist & AI Coach).\n"
        "Bạn đang trò chuyện trực tiếp 1-1 với vận động viên qua Telegram.\n\n"
        f"{today_context}\n\n"
        "NGUYÊN TẮC TRÒ CHUYỆN & TƯ VẤN:\n"
        "1. Xưng hô: 'Mình' (hoặc 'Em') và 'Bạn' (hoặc 'Anh'). Giọng điệu đồng hành, khoa học, thực tế, ân cần và chu đáo.\n"
        "2. Cá nhân hóa dựa trên dữ liệu thực tế: Mọi câu trả lời về tập luyện, chạy bộ, giấc ngủ hay ăn uống phải gắn liền với chỉ số hôm nay (Readiness 84/100, ACWR 1.40, gân Achilles lệch trái, Acid Uric 442 µmol/L, lượng calo/macro còn lại).\n"
        "3. Ngắn gọn, scannable, tập trung vào hành động: Câu trả lời nên súc tích (120 - 250 từ), có gạch đầu dòng rõ ràng, tránh nói lý thuyết dài dòng trừ khi vận động viên yêu cầu giải thích sâu.\n"
        "4. Nguyên tắc dinh dưỡng Việt Nam dân dã: Khuyến nghị cơm trắng, khoai lang hấp, chuối tiêu, đậu phụ non, ức gà, canh rau luộc. TUYỆT ĐỐI CẤM yến mạch, ngũ cốc phương Tây, bánh mì nguyên cám.\n"
        "5. An toàn y học: Nếu vận động viên hỏi về chạy bộ chiều nay -> Khuyên nghỉ ngơi / phục hồi thụ động vì ACWR đang 1.40. Nếu hỏi về ăn tối -> Khóa protein <= 28g và cấm thịt đỏ/hải sản để bảo vệ Acid Uric.\n"
        "6. Nếu vận động viên thông báo vừa ăn món gì: Phân tích nhanh dinh dưỡng món đó và nhắc họ có thể gửi ảnh hoặc gõ lệnh /quick_log để bot lưu chính xác vào DB."
    )


def call_chat_gemini(system_prompt: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Call Google Gemini API for multi-turn chat."""
    api_key = (getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", "") or "").strip().strip('"').strip("'")
    if not api_key or api_key.startswith("your_"):
        raise ValueError("GEMINI_API_KEY is not configured")

    from google import genai
    from google.genai import types

    client = create_genai_client(api_key)

    env_model = (getattr(settings, "gemini_model", None) or os.getenv("GEMINI_MODEL") or "").strip()
    candidates = [env_model, "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
    deprecated = {"gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"}
    models_to_try = [m for m in candidates if m and m not in deprecated]
    seen = set()
    models_to_try = [m for m in models_to_try if not (m in seen or seen.add(m))]

    # Convert conversation turns to Gemini Content structure
    gemini_contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        gemini_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))

    last_err = None
    for model in models_to_try:
        try:
            t0 = time.perf_counter()
            response = client.models.generate_content(
                model=model,
                contents=gemini_contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.4
                )
            )
            elapsed = round(time.perf_counter() - t0, 2)
            reply_text = (response.text or "").strip()
            if reply_text:
                p_tok = getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else 0
                c_tok = getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") and response.usage_metadata else 0
                return {
                    "reply_text": reply_text,
                    "model_used": f"gemini ({model})",
                    "latency_seconds": elapsed,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                    "total_tokens": p_tok + c_tok
                }
        except Exception as exc:
            last_err = exc
            err_str = str(exc).lower()
            if "404" in err_str or "not found" in err_str or "no longer available" in err_str:
                continue
            if "429" in err_str or "quota" in err_str or "503" in err_str:
                continue

    raise RuntimeError(f"All Gemini candidates failed. Last error: {last_err}")


def call_chat_openai(system_prompt: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Call OpenAI API for chat completion."""
    api_key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY", "")
    if not api_key or "YourActual" in api_key:
        raise ValueError("OPENAI_API_KEY is not configured")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    openai_msgs = [{"role": "system", "content": system_prompt}] + messages

    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model=getattr(settings, "openai_model", None) or "gpt-4o-mini",
        messages=openai_msgs,
        temperature=0.4
    )
    elapsed = round(time.perf_counter() - t0, 2)

    reply_text = response.choices[0].message.content or ""
    p_tok = response.usage.prompt_tokens if response.usage else 0
    c_tok = response.usage.completion_tokens if response.usage else 0

    return {
        "reply_text": reply_text,
        "model_used": f"openai ({getattr(settings, 'openai_model', 'gpt-4o-mini')})",
        "latency_seconds": elapsed,
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "total_tokens": p_tok + c_tok
    }


def call_chat_ollama(system_prompt: str, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Call Local Ollama API across configured endpoints (PC GPU primary -> Ally X fallback)."""
    import requests

    endpoints = get_local_llm_endpoints()
    model_name = (getattr(settings, "local_llm_model", None) or os.getenv("LOCAL_LLM_MODEL") or "qwen2.5:7b").strip()

    # Build prompt representation with system and turns
    turns_text = []
    for m in messages:
        sender = "Vận động viên" if m["role"] == "user" else "Huấn luyện viên AI"
        turns_text.append(f"{sender}: {m['content']}")

    full_prompt = (
        f"[CHỈ DẪN CHUYÊN MÔN]\n{system_prompt}\n\n"
        f"[LỊCH SỬ TRÒ CHUYỆN]\n" + "\n".join(turns_text) + "\n"
        f"Huấn luyện viên AI:"
    )

    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.4
        }
    }

    for base_url in endpoints:
        try:
            t0 = time.perf_counter()
            res = requests.post(f"{base_url}/api/generate", json=payload, timeout=(3.0, 90.0))
            elapsed = round(time.perf_counter() - t0, 2)
            if res.status_code == 200:
                res_data = res.json()
                raw_reply = res_data.get("response", "").strip()
                # Clean think tags
                clean_reply = re.sub(r'<think>[\s\S]*?</think>', '', raw_reply).strip()
                p_tokens = res_data.get("prompt_eval_count") or 0
                c_tokens = res_data.get("eval_count") or 0
                if clean_reply:
                    return {
                        "reply_text": clean_reply,
                        "model_used": f"ollama ({model_name}) via {base_url}",
                        "latency_seconds": elapsed,
                        "prompt_tokens": p_tokens,
                        "completion_tokens": c_tokens,
                        "total_tokens": p_tokens + c_tokens
                    }
        except Exception as exc:
            print(f"⚠️ Local Ollama chat fallback error ({base_url}, {model_name}): {exc}")

    return None


def ask_chat_advisor(
    user_query: str,
    chat_id: Union[int, str] = "default",
    target_date: Optional[str] = None
) -> Dict[str, Any]:
    """Execute AI sports physiologist conversational consultation with multi-tier fallback and memory."""
    chat_key = str(chat_id)
    now_dt = datetime.now()
    today_context = get_athlete_live_context(target_date)
    system_prompt = build_chat_system_prompt(today_context)

    # Initialize or trim chat history
    if chat_key not in CHAT_HISTORIES:
        CHAT_HISTORIES[chat_key] = []

    history = CHAT_HISTORIES[chat_key]
    history.append({"role": "user", "content": user_query})

    # Keep sliding window
    if len(history) > MAX_HISTORY_TURNS * 2:
        history = history[-(MAX_HISTORY_TURNS * 2):]
        CHAT_HISTORIES[chat_key] = history

    provider = (getattr(settings, "llm_provider", None) or "gemini").lower()
    res = None

    # Tier 1: Primary Cloud LLM
    try:
        if provider == "openai":
            res = call_chat_openai(system_prompt, history)
        else:
            res = call_chat_gemini(system_prompt, history)
    except Exception as primary_err:
        print(f"⚠️ Primary Chat LLM failed ({provider}): {primary_err}. Trying secondary Cloud LLM...")
        try:
            if provider == "openai":
                res = call_chat_gemini(system_prompt, history)
            else:
                res = call_chat_openai(system_prompt, history)
        except Exception as secondary_err:
            print(f"⚠️ Secondary Cloud LLM failed ({secondary_err}). Kích hoạt Local Ollama Chat (PC GPU / Ally X)...")
            res = call_chat_ollama(system_prompt, history)

    if not res:
        # Ultimate deterministic conversational fallback
        res = {
            "reply_text": (
                "Chào bạn! Hệ thống hiện đang gián đoạn kết nối AI Cloud lẫn Local GPU. "
                "Tuy nhiên, dựa trên dữ liệu Garmin hôm nay, Điểm Sẵn sàng (Readiness) của bạn đang đạt mức tối ưu, "
                "nhưng tỷ số ACWR đang ở ngưỡng cảnh báo quá tải (1.40). "
                "Khuyến nghị bạn nghỉ ngơi hoặc chỉ phục hồi thụ động, uống đủ 2L nước khoáng kiềm Fujiwa và bảo vệ gân Achilles trái."
            ),
            "model_used": "Garmin Health Rule Engine (Offline)",
            "latency_seconds": 0.05,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }

    # Record assistant turn in conversation history
    history.append({"role": "assistant", "content": res["reply_text"]})
    CHAT_HISTORIES[chat_key] = history

    # Append professional AI Telemetry footer
    footer = format_ai_metadata_footer(
        model_used=res.get("model_used"),
        latency_seconds=res.get("latency_seconds"),
        prompt_tokens=res.get("prompt_tokens"),
        completion_tokens=res.get("completion_tokens"),
        for_telegram=True
    )
    full_telegram_message = clean_report_text(f"{res['reply_text']}\n\n{footer}")

    return {
        "reply_text": full_telegram_message,
        "raw_text": res["reply_text"],
        "model_used": res.get("model_used"),
        "latency_seconds": res.get("latency_seconds"),
        "prompt_tokens": res.get("prompt_tokens"),
        "completion_tokens": res.get("completion_tokens"),
        "total_tokens": res.get("total_tokens")
    }

