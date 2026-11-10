import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings
from src.db.connection import get_db_connection
from src.analytics.vision_analyst import sanitize_vision_analysis
from src.delivery.telegram_bot import TelegramMealBot, build_telegram_nutrition_reply

SYSTEM_PROMPT = """Bạn là Chuyên gia Dinh dưỡng Thể thao & Bác sĩ Sinh lý học Thể thao hàng đầu Việt Nam.
Nhiệm vụ của bạn là phân tích dinh dưỡng và đánh giá sinh học chuyên sâu cho bữa ăn của Vận động viên chạy bộ đường dài (Marathon).

ĐẶC BIỆT CHÚ Ý CÁC YẾU TỐ SINH HỌC & Y KHOA CỦA VĐV:
1. Tải Purine & Axit Uric:
   - Đánh giá cụ thể nồng độ axit uric và tải purine từ các món ăn.
   - Nhấn mạnh: Trứng gà luộc và hạt chia là nguồn thực phẩm purine cực thấp (low-purine), hoàn toàn an toàn và lý tưởng cho người cần kiểm soát acid uric.
2. Kháng viêm & Gân gót Achilles:
   - Phân tích tác động của axit béo Omega-3 ALA tự nhiên từ hạt chia trong việc kháng viêm, giảm vi chấn thương tại điểm bám gân gót Achilles sau các bài chạy.
   - Protein chất lượng cao (albumin, axit amin glycine, proline) từ trứng luộc lòng đào hỗ trợ tổng hợp collagen tái tạo cấu trúc gân.
3. Phục hồi sinh học sau hiến máu & vận động:
   - 600ml nước ấm (300ml nước ấm + 300ml nước ấm hạt chia) lúc 6h sáng giúp bù đắp thể tích tuần hoàn hiệu quả, giảm độ nhớt của máu, thúc đẩy tuần hoàn máu và vi mạch.
   - Protein sinh học, vi chất Sắt (Fe), vitamin nhóm B (B12, Folate), Choline từ lòng đỏ trứng luộc lòng đào và khoáng chất (Magie, Kẽm, Canxi) từ hạt chia hỗ trợ tích cực cho quá trình kích hoạt tủy xương tái tạo hồng cầu sau hiến máu/chạy bộ.
   - Ngũ cốc B'Fast cung cấp carbohydrate tiêu hóa nhanh, nạp Glycogen buổi sáng lành mạnh mà không gây quá tải tiêu hóa.

YÊU CẦU ĐẦU RA (BẮT BUỘC TRẢ VỀ DUY NHẤT 1 OBJECT JSON CHUẨN, KHÔNG KÈM KHỐI MÃ MARKDOWN):
{
  "meal_type": "Bữa chính",
  "dishes": [
    "Ngũ cốc dinh dưỡng B'Fast (1 gói)",
    "2 quả trứng gà luộc lòng đào",
    "Nước ấm hạt chia (300ml)",
    "Nước ấm ban mai (300ml)"
  ],
  "total_calories": 395,
  "protein_g": 18.5,
  "carb_g": 46.0,
  "fat_g": 15.0,
  "alcohol_units": 0.0,
  "alcohol_description": "Không có cồn",
  "sleep_risk_assessment": "✅ Đánh giá Dinh dưỡng & Phục hồi: ... [nội dung nhận xét phục hồi, purine thấp an toàn acid uric, Omega-3 bảo vệ gân Achilles, bù nước 600ml và tái tạo hồng cầu sau hiến máu] ...",
  "short_summary": "Đã ghi nhận: Bữa sáng phục hồi (Ngũ cốc B'Fast, 2 trứng luộc lòng đào, nước ấm hạt chia) (~395 kcal | P: 18.5g | C: 46g | F: 15g)."
}
"""


def call_gemini_reanalyze(user_prompt: str) -> Tuple[Dict[str, Any], str]:
    """Call Gemini LLM API with fallback models (gemini-2.5-flash, gemini-3.8-flash)
    and exponential backoff retry.
    """
    api_key = (getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", "") or "").strip().strip('"').strip("'")
    if not api_key:
        raise ValueError("GEMINI_API_KEY không được tìm thấy trong .env hoặc settings.")

    models_to_try = [
        "gemini-2.5-flash",
        "gemini-3.8-flash",
    ]
    deprecated_models = {"gemini-2.0-flash", "gemini-1.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"}
    env_model = (getattr(settings, "gemini_model", None) or os.getenv("GEMINI_MODEL") or "").strip()
    if env_model and env_model not in models_to_try and env_model not in deprecated_models:
        models_to_try.insert(0, env_model)

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    raw_response_text = ""
    last_err = None
    model_used = None

    for model in models_to_try:
        max_retries = 3
        delay = 2
        success = False

        for attempt in range(1, max_retries + 1):
            try:
                print(f"📡 Đang gọi Gemini model '{model}' (Lần thử {attempt}/{max_retries})...")
                response = client.models.generate_content(
                    model=model,
                    contents=[user_prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.2,
                        response_mime_type="application/json"
                    )
                )
                txt = (response.text or "").strip()
                if txt:
                    raw_response_text = txt
                    model_used = model
                    success = True
                    print(f"✅ Gemini model '{model}' trả lời thành công!")
                    break
            except Exception as exc:
                last_err = exc
                err_str = str(exc)
                err_lower = err_str.lower()
                print(f"⚠️ Thất bại với model '{model}' (Lần {attempt}/{max_retries}): {exc}")

                # If model is deprecated or not found (404), switch immediately to next model
                if "404" in err_str or "not found" in err_lower or "no longer available" in err_lower:
                    print(f"🔄 Model '{model}' is deprecated/not found (404). Skipping retries and switching to next model...")
                    break

                if attempt < max_retries:
                    print(f"⏳ Chờ {delay}s trước khi thử lại...")
                    time.sleep(delay)
                    delay *= 2
                else:
                    print(f"🔄 Model '{model}' hết 3 lần thử. Chuyển sang model tiếp theo...")

        if success:
            break

    if not raw_response_text:
        raise RuntimeError(f"Tất cả candidate Gemini models đều thất bại. Lỗi cuối: {last_err}")

    # Parse and sanitize JSON
    cleaned = raw_response_text
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    parsed = json.loads(cleaned)
    return parsed, raw_response_text


def reanalyze_meal_record(meal_id: int, send_telegram: bool = True, chat_id: str = "1022843967") -> Dict[str, Any]:
    """Re-analyze a meal log in SQLite by ID, update DB, and deliver message card to Telegram."""
    db_path = Path(settings.db_path)
    print(f"📂 Đang kết nối CSDL: {db_path}...")

    # 1. Fetch meal record from SQLite
    with get_db_connection(db_path) as conn:
        conn.row_factory = None
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, timestamp, meal_type, dishes, total_calories, protein_g, carb_g, fat_g, short_summary FROM nutrition_logs WHERE id = ?", (meal_id,))
        row = cursor.fetchone()

    if not row:
        raise ValueError(f"Không tìm thấy bản ghi bữa ăn với ID = {meal_id} trong SQLite.")

    rec_id, rec_date, rec_ts, rec_meal_type, rec_dishes, old_cal, old_p, old_c, old_f, old_summary = row

    # Extract dish description text
    meal_desc = ""
    try:
        parsed_dishes = json.loads(rec_dishes)
        if isinstance(parsed_dishes, list):
            meal_desc = ", ".join(str(d).strip() for d in parsed_dishes if d)
        else:
            meal_desc = str(parsed_dishes).strip()
    except Exception:
        meal_desc = str(rec_dishes).strip()

    print(f"\n🍱 Tìm thấy bản ghi bữa ăn #{rec_id} ({rec_date} {rec_ts}):")
    print(f"   • Mô tả: {meal_desc}")
    print(f"   • Chỉ số hiện tại: {old_cal} kcal | P: {old_p}g | C: {old_c}g | F: {old_f}g")

    user_prompt = (
        f"Thời điểm nạp bữa ăn: {rec_ts} (Ngày {rec_date}).\n"
        f"Mô tả chi tiết bữa ăn của Vận động viên Marathon: '{meal_desc}'.\n"
        f"Hãy phân tích chi tiết lượng Calo, Protein, Carb, Fat, và cung cấp nhận xét sinh lý học/y học thể thao chuyên sâu "
        f"về: nồng độ acid uric (tải purine thấp), bảo vệ gân gót Achilles (Omega-3 ALA & amino acids tổng hợp collagen), "
        f"bù nước tuần hoàn (600ml nước ấm ban mai) và tái tạo thể trạng hồng cầu sau hiến máu/chạy bộ."
    )

    # 2. Call AI Analyst
    print("\n🚀 Đang gọi LLM Analyst với cơ chế Fallback & Exponential Backoff...")
    parsed_ai, raw_ai_text = call_gemini_reanalyze(user_prompt)

    # Sanitize and extract values
    def _to_num(val, default, is_int=False):
        try:
            n = float(val)
            return int(round(n)) if is_int else round(n, 1)
        except Exception:
            return default

    new_cal = _to_num(parsed_ai.get("total_calories"), 395, is_int=True)
    new_p = _to_num(parsed_ai.get("protein_g"), 18.5)
    new_c = _to_num(parsed_ai.get("carb_g"), 46.0)
    new_f = _to_num(parsed_ai.get("fat_g"), 15.0)
    new_meal_type = parsed_ai.get("meal_type") or "Bữa chính"
    new_dishes = parsed_ai.get("dishes") or [meal_desc]
    new_risk = parsed_ai.get("sleep_risk_assessment") or ""
    new_summary = parsed_ai.get("short_summary") or f"Đã ghi nhận: {meal_desc} (~{new_cal} kcal | P: {new_p}g | C: {new_c}g | F: {new_f}g)."

    parsed_ai["date"] = rec_date
    parsed_ai["timestamp"] = rec_ts
    parsed_ai["total_calories"] = new_cal
    parsed_ai["protein_g"] = new_p
    parsed_ai["carb_g"] = new_c
    parsed_ai["fat_g"] = new_f
    parsed_ai["meal_type"] = new_meal_type
    parsed_ai["dishes"] = new_dishes
    parsed_ai["sleep_risk_assessment"] = new_risk
    parsed_ai["short_summary"] = new_summary

    sanitized = sanitize_vision_analysis(parsed_ai, rec_date, rec_ts)

    dishes_json = json.dumps(new_dishes, ensure_ascii=False) if isinstance(new_dishes, list) else str(new_dishes)

    # 3. Update SQLite Database
    print(f"\n💾 Đang cập nhật dữ liệu mới vào SQLite cho ID = {meal_id}...")
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE nutrition_logs SET
                meal_type = ?,
                dishes = ?,
                total_calories = ?,
                protein_g = ?,
                carb_g = ?,
                fat_g = ?,
                alcohol_units = ?,
                alcohol_description = ?,
                sleep_risk_assessment = ?,
                short_summary = ?,
                raw_ai_response = ?
            WHERE id = ?
            """,
            (
                sanitized.get("meal_type", "Bữa chính"),
                dishes_json,
                sanitized.get("total_calories"),
                sanitized.get("protein_g"),
                sanitized.get("carb_g"),
                sanitized.get("fat_g"),
                sanitized.get("alcohol_units", 0.0),
                sanitized.get("alcohol_description", "Không có cồn"),
                sanitized.get("sleep_risk_assessment"),
                sanitized.get("short_summary"),
                raw_ai_text,
                meal_id
            )
        )
        conn.commit()

    print("✅ Đã cập nhật thành công bản ghi ID = 129 vào SQLite:")
    print(f"   • Calories: {old_cal} -> {sanitized['total_calories']} kcal")
    print(f"   • Protein:  {old_p}g -> {sanitized['protein_g']}g")
    print(f"   • Carb:     {old_c}g -> {sanitized['carb_g']}g")
    print(f"   • Fat:      {old_f}g -> {sanitized['fat_g']}g")
    print(f"   • Cột raw_ai_response: Đã lưu ({len(raw_ai_text)} ký tự)")

    # 4. Format Message Card and send to Telegram
    card_text = build_telegram_nutrition_reply(sanitized)
    print("\n" + "=" * 60)
    print("📱 NỘI DUNG TELEGRAM MESSAGE CARD:")
    print("=" * 60)
    print(card_text)
    print("=" * 60)

    if send_telegram:
        target_chat_id = chat_id or settings.telegram_chat_id or "1022843967"
        print(f"\n📲 Đang gửi Message Card tới Telegram Chat ID: {target_chat_id}...")
        bot = TelegramMealBot(bot_token=settings.telegram_bot_token)
        send_res = bot.send_message(chat_id=target_chat_id, text=card_text)
        if send_res.get("ok"):
            print(f"✅ Gửi Telegram thành công! (Message ID: {send_res.get('result', {}).get('message_id')})")
        else:
            print(f"⚠️ Gửi Telegram thất bại: {send_res}")

    return {
        "status": "success",
        "meal_id": meal_id,
        "analysis": sanitized,
        "raw_ai_response": raw_ai_text,
        "card_text": card_text
    }


def main():
    parser = argparse.ArgumentParser(description="Phân tích lại dinh dưỡng và sinh học chuyên sâu cho bữa ăn trong SQLite.")
    parser.add_argument("--meal-id", type=int, default=129, help="ID của bản ghi bữa ăn trong bảng nutrition_logs (Mặc định: 129)")
    parser.add_argument("--chat-id", type=str, default="1022843967", help="Telegram chat ID để gửi kết quả (Mặc định: 1022843967)")
    parser.add_argument("--no-telegram", action="store_true", help="Không gửi tin nhắn Telegram")
    args = parser.parse_args()

    reanalyze_meal_record(
        meal_id=args.meal_id,
        send_telegram=not args.no_telegram,
        chat_id=args.chat_id
    )


if __name__ == "__main__":
    main()

