import os
import sys
import json
import sqlite3
import requests
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings

def run_reanalyze():
    print("▶️ [1/5] Khởi động script reanalyze record 131...", flush=True)

    db_path = Path(settings.db_path) if getattr(settings, "db_path", None) else BASE_DIR / "data" / "garmin_health.db"
    print(f"📂 [2/5] Kết nối database tại: {db_path} (timeout=10.0s)...", flush=True)
    
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM nutrition_logs WHERE id = 131")
    row = cursor.fetchone()
    if not row:
        print("❌ Không tìm thấy bản ghi ID 131 trong database!", flush=True)
        conn.close()
        return False

    record = dict(row)
    print(f"📋 Bản ghi 131 hiện tại: {record.get('dishes')} | Calories: {record.get('total_calories')} kcal", flush=True)

    meal_text = "cơm trắng với cá bống kho ớt và canh sườn dưa"
    print(f"🍲 [3/5] Bắt đầu phân tích dinh dưỡng cho món: '{meal_text}'...", flush=True)

    analysis_data = None
    raw_ai_text = ""

    # Thử Tuyến 1: Gemini 2.5 Flash
    api_key = (getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", "")).strip().strip('"').strip("'")
    if api_key and not api_key.startswith("your_"):
        print("📡 Đang gọi Google Gemini API (model: gemini-2.5-flash, timeout: 20s)...", flush=True)
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            prompt = (
                f"Bạn là chuyên gia dinh dưỡng thể thao hàng đầu Việt Nam. Hãy phân tích bữa ăn sau: \"{meal_text}\".\n"
                "BẮT BUỘC trả về duy nhất 1 chuỗi JSON thuần túy (không bọc ```json, không markdown) theo đúng schema sau:\n"
                "{\n"
                "  \"calories\": <số thực tổng calo>,\n"
                "  \"protein\": <số thực gram protein>,\n"
                "  \"carb\": <số thực gram carb>,\n"
                "  \"fat\": <số thực gram fat>,\n"
                "  \"summary\": \"<tên các món ăn và định lượng ước tính>\",\n"
                "  \"recovery_impact\": \"<đánh giá phục hồi cơ bắp, kháng viêm, nạp glycogen, tải purine/axit uric>\"\n"
                "}"
            )

            # Gọi generate_content
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json"
                )
            )
            raw_ai_text = (response.text or "").strip()
            if raw_ai_text:
                print("✅ Nhận phản hồi thành công từ Gemini 2.5 Flash!", flush=True)
                clean_json = raw_ai_text
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                elif clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                analysis_data = json.loads(clean_json.strip())
        except Exception as e:
            print(f"⚠️ Gemini API gặp lỗi hoặc quá thời gian: {e}", flush=True)

    # Thử Tuyến 2: Ollama Local LLM (qwen2.5:7b) nếu Gemini chưa có kết quả
    if not analysis_data:
        local_url = (getattr(settings, "local_llm_url", None) or os.getenv("LOCAL_LLM_URL") or "http://localhost:11434").rstrip("/")
        model_name = (getattr(settings, "local_llm_model", None) or os.getenv("LOCAL_LLM_MODEL") or "qwen2.5:7b").strip()
        print(f"🔄 Chuyển sang Ollama Local ({model_name} tại {local_url}, timeout: 15s)...", flush=True)
        try:
            payload = {
                "model": model_name,
                "prompt": (
                    f"Bạn là chuyên gia dinh dưỡng thể thao. Phân tích bữa ăn: \"{meal_text}\".\n"
                    "Trả về duy nhất 1 JSON:\n"
                    "{\n"
                    "  \"calories\": <số thực calo>,\n"
                    "  \"protein\": <số thực protein>,\n"
                    "  \"carb\": <số thực carb>,\n"
                    "  \"fat\": <số thực fat>,\n"
                    "  \"summary\": \"<mô tả món ăn>\",\n"
                    "  \"recovery_impact\": \"<đánh giá phục hồi>\"\n"
                    "}"
                ),
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.2}
            }
            res = requests.post(f"{local_url}/api/generate", json=payload, timeout=(3.0, 15.0))
            if res.status_code == 200:
                raw_response = res.json().get("response", "{}")
                raw_ai_text = raw_response
                clean_json = raw_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                elif clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                analysis_data = json.loads(clean_json.strip())
                print(f"✅ Nhận phản hồi thành công từ Local Ollama ({model_name})!", flush=True)
        except Exception as ollama_err:
            print(f"⚠️ Ollama Local cũng không phản hồi: {ollama_err}", flush=True)

    # Nếu cả 2 đều không phản hồi, dùng công thức ước tính chuyên gia thực tế cho bữa ăn này
    if not analysis_data:
        print("ℹ️ Dùng tính toán dinh dưỡng tiêu chuẩn Việt Nam cho bữa ăn cơm cá bống kho + canh sườn dưa...", flush=True)
        # 1 bát cơm trắng: ~200 kcal, 4g P, 45g C, 0.5g F
        # Cá bống kho ớt (khoảng 100g): ~150 kcal, 22g P, 3g C, 5g F
        # Canh sườn nấu dưa chua (1 bát tô vừa, 2-3 dẻ sườn): ~220 kcal, 16g P, 6g C, 14g F
        analysis_data = {
            "calories": 570.0,
            "protein": 42.0,
            "carb": 54.0,
            "fat": 19.5,
            "summary": "1 bát cơm trắng, cá bống kho ớt tiêu (~100g), canh sườn chua dưa cải",
            "recovery_impact": "✅ Đánh giá Dinh dưỡng & Phục hồi: Giàu đạm sinh học (42g) từ cá bống và sườn lợn giúp tái tạo mô cơ và gân. Dưa chua cung cấp men vi sinh tiêu hóa, tinh bột từ cơm nạp bù Glycogen. Tải purine mức trung bình, an toàn cho acid uric."
        }
        raw_ai_text = json.dumps(analysis_data, ensure_ascii=False)

    cal = int(round(float(analysis_data.get("calories") or 570)))
    p = round(float(analysis_data.get("protein") or 42.0), 1)
    c = round(float(analysis_data.get("carb") or 54.0), 1)
    f = round(float(analysis_data.get("fat") or 19.5), 1)
    summary = str(analysis_data.get("summary") or meal_text).strip()
    recovery = str(analysis_data.get("recovery_impact") or "Bữa ăn cân bằng giàu đạm và năng lượng phục hồi.").strip()

    short_summary = f"Đã ghi nhận: {summary} (~{cal} kcal | P: {p}g | C: {c}g | F: {f}g)."
    sleep_risk = recovery if recovery.startswith("✅") or recovery.startswith("⚠️") else f"✅ {recovery}"

    print(f"\n📊 KẾT QUẢ DINH DƯỠNG MỚI CHO BẢN GHI 131:", flush=True)
    print(f"• Calories: {cal} kcal", flush=True)
    print(f"• Protein:  {p} g", flush=True)
    print(f"• Carb:     {c} g", flush=True)
    print(f"• Fat:      {f} g", flush=True)
    print(f"• Tóm tắt:  {short_summary}", flush=True)
    print(f"• Phục hồi: {sleep_risk}", flush=True)

    print("\n💾 [4/5] Thực hiện UPDATE vào bảng nutrition_logs trong SQLite...", flush=True)
    cursor.execute("""
        UPDATE nutrition_logs
        SET total_calories = ?,
            protein_g = ?,
            carb_g = ?,
            fat_g = ?,
            sleep_risk_assessment = ?,
            short_summary = ?,
            raw_ai_response = ?
        WHERE id = 131
    """, (cal, p, c, f, sleep_risk, short_summary, raw_ai_text))
    conn.commit()
    conn.close()
    print("✅ [5/5] Cập nhật bản ghi 131 thành công!", flush=True)
    return True

if __name__ == "__main__":
    run_reanalyze()
