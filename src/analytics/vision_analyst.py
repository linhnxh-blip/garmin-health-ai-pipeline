import json
import io
import time
from typing import Dict, Any, Optional, Union
from pathlib import Path
from datetime import datetime
from PIL import Image

from config.settings import settings

VISION_SYSTEM_PROMPT = """Bạn là một Chuyên gia Dinh dưỡng Thể thao & Chuyên gia Sinh lý học Thể thao hàng đầu Việt Nam.
Nhiệm vụ của bạn là nhận diện và phân tích toàn diện ảnh chụp bữa ăn / đồ nhậu / thức uống của vận động viên.

ĐẶC THÙ MÓN ĂN & NGUYÊN TẮC PHÂN TÍCH:
1. NHẬN DIỆN MÓN ĂN & BỔ SUNG ĐẦY ĐỦ 3 CHỈ SỐ MACRO (PROTEIN - CARB - FAT):
   - Phân loại rõ meal_type vào 1 trong các nhóm: "Bữa chính" (Bữa sáng/Trưa/Tối), "Thức uống" (Nước ép/Sinh tố/Trà/Cà phê), "Bữa phụ / Snack", hoặc "Đồ nhậu / Cồn".
   - BẮT BUỘC ước tính và xuất đủ cả 3 chỉ số Macro: Protein (g), Carbohydrate (g), Fat (g) cùng Total Calories. Không được bỏ sót Fat hay Carb.
   - NẾU CÓ LẠC RANG (đậu phộng): BẮT BUỘC tính thêm nguồn Protein thực vật và chất béo Fat từ hạt lạc.
   - Khay cơm văn phòng / bình dân: Tính toán Protein thực tế trong khoảng 45g - 50g nếu có 2 món đạm kết hợp lạc rang/đậu phụ.

2. ĐÁNH GIÁ DƯỢC LÝ & Y HỌC THỂ THAO CHO NƯỚC ÉP / VI CHẤT / HOA QUẢ:
   - Dứa (Pineapple): Nhận diện enzyme Bromelain (kháng viêm tự nhiên mạnh mẽ, hỗ trợ làm dịu vi tổn thương cơ bắp và gân gót Achilles).
   - Cần tây / Củ dền: Nhận diện nguồn Nitrate tự nhiên và điện giải (Kali, Natri hữu cơ giúp giãn nở vi mạch, hạ áp lực tuần hoàn và tăng cường lưu thông máu).
   - Trái cây giàu Carb (Dưa hấu, xoài, chuối, táo): Đánh giá khả năng bù đắp Glycogen nhanh trước hoặc sau vận động.
   - Chuối chín: Giàu Kali & Magie chống chuột rút, cân bằng điện giải.

3. LOGIC ĐÁNH GIÁ THEO MỐC THỜI GIAN TRONG NGÀY (TIME-AWARE RECOVERY & NUTRITION):
   - NẾU BỮA ĂN DIỄN RA TRƯỚC 14:00 (SÁNG / TRƯA / PHỤ SÁNG):
     + TUYỆT ĐỐI KHÔNG phân tích rập khuôn "không ảnh hưởng đến giấc ngủ đêm" hay nhắc nhở giờ ngủ 21:30.
     + ĐÁNH GIÁ TÍNH CÂN BẰNG NĂNG LƯỢNG & MACRO: Đánh giá xem bữa ăn có đủ Carbohydrate để duy trì đường huyết và nạp/phục hồi dự trữ Glycogen hay chưa. NẾU bữa sáng/trưa thiếu Carb (chỉ có đạm/trứng/thịt), BẮT BUỘC nhắc nhở: "Nên bổ sung thêm nguồn Carb lành mạnh (như khoai lang hấp, chuối tiêu chín, cháo trắng thịt băm, cơm trắng) để duy trì đường huyết và nạp Glycogen cho ngày phục hồi".
   - NẾU BỮA ĂN DIỄN RA SAU 18:00 (TỐI / ĐỒ NHẬU):
     + MỚI ĐÁNH GIÁ thời gian tiêu hóa (cần kết thúc trước 18:45 hoặc ít nhất 2.5 - 3 tiếng trước giờ ngủ 21:30) và tác động tới nhịp tim nghỉ RHR đêm / chất lượng giấc ngủ.

4. ĐÁNH GIÁ TÍNH TÍCH LŨY TRONG NGÀY (CUMULATIVE CONTEXT AWARENESS):
   - Khi có thông tin nhật ký dinh dưỡng đã nạp trong ngày, hãy liên kết món mới với các món VĐV đã ăn trước đó.
   - NẾU VĐV đã nạp đủ Protein trước đó (ví dụ trứng, thịt bò, ức gà trong vòng 1-2 tiếng trước) và hiện tại đang nạp tinh bột (khoai lang hấp, chuối tiêu, cơm trắng), BẮT BUỘC ghi nhận: "Món này kết hợp hoàn hảo với lượng protein từ [món đạm đã ăn trước đó], giúp hoàn thiện cân bằng Macro cho bữa ăn."
   - TUYỆT ĐỐI KHÔNG đưa ra lời nhắc nhở mù quáng yêu cầu nạp thêm đạm/trứng nếu VĐV đã nạp đạm/trứng trong cùng buổi sáng/ngày đó.

5. NGUYÊN TẮC TINH BỘT DÂN DÃ & CẤM YẾN MẠCH (TRADITIONAL LOCAL FOODS ONLY):
   - Vận động viên KHÔNG ăn yến mạch hay các loại ngũ cốc kiêng phương Tây.
   - TUYỆT ĐỐI CẤM gợi ý, nhắc nhở hoặc kê đơn: ["yến mạch", "oatmeal", "bánh mì nguyên cám", "quinoa"].
   - BẮT BUỘC ưu tiên các nguồn tinh bột sạch, dân dã, thân thiện tiêu hóa của Việt Nam: ["khoai lang hấp", "chuối tiêu chín", "cháo trắng thịt băm", "cơm trắng"].

6. XỬ LÝ GHI NHẬN LIÊN TIẾP TRONG VÒNG 5 PHÚT (RAPID CONSECUTIVE LOGS DEBOUNCE):
   - NẾU món mới được ghi nhận trong vòng 5 phút sau một món ăn/thức uống trước đó trong cùng buổi sáng (ví dụ uống nước hạt chia ngay sau khi ăn trứng luộc):
   - BẮT BUỘC coi đây là thức uống/món ăn bổ sung đi kèm trong cùng một bữa sáng đang diễn ra.
   - TUYỆT ĐỐI KHÔNG lặp lại bài giảng macro rập khuôn hay lặp lại lời cảnh báo thiếu Carb từ món trước!
   - Ghi nhận tích cực về công dụng bù nước/vi chất của món mới và tính gắn kết với bữa ăn vừa nạp.

7. YÊU CẦU ĐẦU RA (BẮT BUỘC TRẢ VỀ DUY NHẤT 1 OBJECT JSON CHUẨN SANITIZED, KHÔNG CHỨA KHỐI MÃ MARKDOWN):
{
  "meal_type": "Bữa chính / Thức uống / Bữa phụ / Đồ nhậu",
  "dishes": ["Nước ép cần tây dứa", "1 quả chuối"],
  "total_calories": 150,
  "protein_g": 2.0,
  "carb_g": 35.0,
  "fat_g": 0.5,
  "alcohol_units": 0.0,
  "alcohol_description": "Không có cồn",
  "sleep_risk_assessment": "✅ Đánh giá Dinh dưỡng & Phục hồi: Thức uống nạp lúc 15:30. Enzyme Bromelain từ dứa kháng viêm gân Achilles, Nitrate tự nhiên từ cần tây giúp giãn vi mạch máu.",
  "short_summary": "Đã ghi nhận: 1 ly Nước ép cần tây dứa và 1 quả chuối (~150 kcal | P: 2g | C: 35g | F: 0.5g)."
}
"""

def analyze_meal_image_openai(img_bytes: bytes, user_text: str) -> Optional[str]:
    """Fallback helper to analyze image using OpenAI Vision API (gpt-4o-mini)."""
    import base64
    import requests
    import os
    openai_key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY", "")
    if not openai_key or "YourActual" in openai_key:
        return None
    try:
        base64_image = base64.b64encode(img_bytes).decode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_key}"
        }
        payload = {
            "model": getattr(settings, "openai_model", None) or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            "max_tokens": 500
        }
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            res_data = res.json()
            return res_data["choices"][0]["message"]["content"]
    except Exception as err:
        print(f"⚠️ OpenAI Vision fallback exception: {err}")
    return None

def sanitize_vision_analysis(parsed: Dict[str, Any], date_str: str, current_ts: str) -> Dict[str, Any]:
    """Sanitize vision AI output: purge prohibited grains and debounce rapid consecutive log warnings."""
    import re
    risk_text = parsed.get("sleep_risk_assessment") or ""
    summary_text = parsed.get("short_summary") or ""

    # 1. Purge modern western grains (oatmeal, quinoa, whole wheat bread)
    replacements = [
        (r'\b(?:yến mạch|oatmeal)\b', 'khoai lang hấp'),
        (r'\bbánh mì nguyên cám\b', 'chuối tiêu chín'),
        (r'\bquinoa\b', 'cơm trắng'),
    ]
    for pat, rep in replacements:
        risk_text = re.sub(pat, rep, risk_text, flags=re.IGNORECASE)
        summary_text = re.sub(pat, rep, summary_text, flags=re.IGNORECASE)

    # 2. Debounce rapid consecutive logs (< 5 minutes from previous meal today)
    try:
        from src.db.nutrition_repository import get_nutrition_logs_by_date
        logs = get_nutrition_logs_by_date(date_str)
        if logs:
            prev_log = logs[-1]
            prev_ts = str(prev_log.get("timestamp") or "")
            t_fmt = "%Y-%m-%d %H:%M:%S"
            c_dt = datetime.strptime(current_ts, t_fmt) if len(current_ts) >= 19 else datetime.now()
            p_dt = datetime.strptime(prev_ts, t_fmt) if len(prev_ts) >= 19 else None
            if p_dt and 0 <= (c_dt - p_dt).total_seconds() <= 300:
                macro_warning_patterns = [
                    r'Tuy nhiên,?\s*(?:bữa ăn|tổng lượng Carbohydrate)[^.]*?(?:nên bổ sung|cần bổ sung)[^.]*\.?',
                    r'Tuy nhiên,?\s*bữa ăn hiện tại đang hoàn toàn thiếu Carbohydrate[^.]*\.?',
                    r'VĐV nên bổ sung thêm nguồn Carb[^.]*\.?',
                    r'bạn nên bổ sung thêm nguồn Carb[^.]*\.?'
                ]
                for pat in macro_warning_patterns:
                    risk_text = re.sub(pat, '', risk_text, flags=re.IGNORECASE).strip()
                if not risk_text or risk_text in [".", "✅", "⚠️"]:
                    prev_dish = ", ".join(prev_log.get("dishes") or []) if isinstance(prev_log.get("dishes"), list) else str(prev_log.get("dishes") or "")
                    risk_text = f"✅ Đánh giá Dinh dưỡng & Phục hồi: Thức uống/món ăn bổ sung ngay trong bữa sáng ({prev_dish}), hỗ trợ bù nước và vi chất lành mạnh."
    except Exception:
        pass

    parsed["sleep_risk_assessment"] = risk_text
    parsed["short_summary"] = summary_text
    return parsed


def _get_intraday_cumulative_context(date_str: str, current_ts: Optional[str] = None) -> str:
    """Fetch previously logged meals today to build intraday cumulative awareness for meal review prompts."""
    try:
        from src.db.nutrition_repository import get_nutrition_logs_by_date, get_today_nutrition_summary
        logs = get_nutrition_logs_by_date(date_str)
        if not logs:
            return "\n📌 NHẬT KÝ DINH DƯỠNG TRONG NGÀY: Chưa có món ăn nào được ghi nhận trước đó hôm nay."
        
        prev_items = []
        for l in logs:
            d_list = l.get("dishes") or []
            d_str = ", ".join(d_list) if isinstance(d_list, list) else str(d_list)
            ts = str(l.get("timestamp") or "")
            t_part = ts.split()[-1] if len(ts.split()) > 1 else ts
            p_val = l.get("protein_g") or 0.0
            c_val = l.get("carb_g") or 0.0
            prev_items.append(f"• {d_str} (lúc {t_part} - {p_val}g Protein, {c_val}g Carb)")

        rapid_notice = ""
        last_log = logs[-1]
        last_ts_str = str(last_log.get("timestamp") or "")
        try:
            t_fmt = "%Y-%m-%d %H:%M:%S"
            c_dt = datetime.strptime(current_ts, t_fmt) if current_ts else datetime.now()
            l_dt = datetime.strptime(last_ts_str, t_fmt) if len(last_ts_str) >= 19 else None
            if l_dt and 0 <= (c_dt - l_dt).total_seconds() <= 300:
                sec_diff = int((c_dt - l_dt).total_seconds())
                last_dishes = ", ".join(last_log.get("dishes") or []) if isinstance(last_log.get("dishes"), list) else str(last_log.get("dishes") or "")
                rapid_notice = (
                    f"\n⚡ LƯU Ý GHI NHẬN LIÊN TIẾP ({sec_diff} GIÂY TRƯỚC): VĐV vừa ghi nhận món '{last_dishes}' cách đây chưa đầy 5 phút. "
                    f"Món hiện tại là thức uống/món ăn bổ sung đi kèm trong cùng bữa ăn này. "
                    f"BẮT BUỘC ghi nhận tự nhiên, TUYỆT ĐỐI KHÔNG lặp lại các đoạn văn cảnh báo macro rập khuôn hay lặp lại lời khuyên thiếu Carb từ món trước!\n"
                )
        except Exception:
            pass

        summary = get_today_nutrition_summary(date_str)
        return (
            f"\n📌 NHẬT KÝ DINH DƯỠNG ĐÃ NẠP TRONG NGÀY HÔM NAY:\n"
            f"Các món đã ăn trước đó:\n" + "\n".join(prev_items) + "\n"
            f"Tổng lũy kế đã nạp hôm nay: {summary['total_cal']} kcal | Protein: {summary['total_protein']}g | Carb: {summary['total_carbs']}g | Fat: {summary['total_fat']}g.\n"
            f"{rapid_notice}"
            f"⚠️ QUY TẮC ĐÁNH GIÁ TÍCH LŨY (CUMULATIVE CONTEXT AWARENESS):\n"
            f"- Liên kết món mới này với các món VĐV đã ăn trước đó trong ngày.\n"
            f"- NẾU VĐV đã ăn nguồn đạm/protein (trứng, thịt, cá, sữa chua) trước đó và hiện tại đang nạp tinh bột (khoai lang hấp, chuối tiêu, cơm trắng, cháo), BẮT BUỘC ghi nhận sự kết hợp hoàn hảo giữa món tinh bột này và lượng protein đã nạp trước đó. TUYỆT ĐỐI KHÔNG nhắc nhở mù quáng ép VĐV ăn thêm trứng/đạm mà họ vừa mới ăn xong!\n"
            f"⚠️ CẤM YẾN MẠCH & BÁNH MÌ NGUYÊN CÁM (LOCAL TRADITIONAL FOODS ONLY):\n"
            f"- TUYỆT ĐỐI CẤM nhắc đến hoặc khuyên dùng: ['yến mạch', 'oatmeal', 'bánh mì nguyên cám', 'quinoa'].\n"
            f"- BẮT BUỘC ưu tiên các món truyền thống dân dã dễ tiêu: ['khoai lang hấp', 'chuối tiêu chín', 'cháo trắng thịt băm', 'cơm trắng']."
        )
    except Exception:
        return ""


def analyze_meal_image(
    image_input: Union[bytes, str, Path, Image.Image],
    caption: Optional[str] = None,
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """Analyze a meal/drink photo using Gemini Multimodal Vision API.
    Returns structured dict with macros, alcohol info, sleep risk, and short_summary.
    """
    import os
    now_dt = datetime.now()
    date_str = now_dt.strftime("%Y-%m-%d")
    ts_str = timestamp or now_dt.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Check for Mock Mode
    is_mock = os.getenv("MOCK_LLM", "false").lower() == "true" or getattr(settings, "mock_llm", False)
    if is_mock:
        dish_name = caption or "Bữa ăn dinh dưỡng (Mock Mode)"
        caption_desc = f" ({caption})" if caption else ""
        return {
            "date": date_str,
            "timestamp": ts_str,
            "meal_type": "Bữa chính",
            "dishes": [dish_name],
            "total_calories": 600,
            "protein_g": 30.0,
            "carb_g": 50.0,
            "fat_g": 20.0,
            "alcohol_units": 0.0,
            "alcohol_description": "Không có cồn",
            "sleep_risk_assessment": "✅ Đánh giá Dinh dưỡng & Phục hồi: Bữa ăn cân bằng hỗ trợ phục hồi cơ bắp và dự trữ Glycogen.",
            "short_summary": f"Đã ghi nhận: {dish_name}{caption_desc} (~600 kcal | P: 30g | C: 50g | F: 20g).",
            "raw_ai_response": "mock_response"
        }

    api_key = (getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", "") or "").strip().strip('"').strip("'")

    # Prepare PIL Image
    if isinstance(image_input, (str, Path)):
        img = Image.open(image_input)
    elif isinstance(image_input, bytes):
        img = Image.open(io.BytesIO(image_input))
    elif isinstance(image_input, Image.Image):
        img = image_input
    else:
        raise ValueError("Unsupported image_input format")

    if img.mode != "RGB":
        img = img.convert("RGB")

    user_text = f"Thời điểm gửi ảnh/bữa ăn: {ts_str} (Giờ thực tế: {now_dt.strftime('%H:%M')})."
    if caption:
        user_text += f"\nChú thích của vận động viên: '{caption}'."
    user_text += _get_intraday_cumulative_context(date_str, current_ts=ts_str)

    # Ensure image is encoded to JPEG bytes with explicit mime_type
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG", quality=95)
    img_jpeg_bytes = img_byte_arr.getvalue()

    last_err = None
    ai_raw_text = ""

    def _safe_print(msg: str):
        try:
            print(msg)
        except Exception:
            print(msg.encode("ascii", "replace").decode("ascii"))

    if api_key and not api_key.startswith("your_"):
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            image_part = types.Part.from_bytes(data=img_jpeg_bytes, mime_type="image/jpeg")

            vision_env_model = (getattr(settings, "gemini_vision_model", None) or os.getenv("GEMINI_VISION_MODEL") or getattr(settings, "gemini_model", None) or "").strip()
            primary_model = vision_env_model or "gemini-3.6-flash"

            candidate_models = [
                primary_model,
                "gemini-3.6-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-pro-preview"
            ]
            seen = set()
            models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

            for model in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[image_part, user_text],
                        config=types.GenerateContentConfig(
                            system_instruction=VISION_SYSTEM_PROMPT,
                            temperature=0.2,
                            response_mime_type="application/json"
                        )
                    )
                    ai_raw_text = (response.text or "").strip()
                    if ai_raw_text:
                        _safe_print(f"✅ Gemini Vision analysis succeeded using model '{model}'")
                        break
                except Exception as exc:
                    last_err = exc
                    err_str = str(exc)
                    err_lower = err_str.lower()
                    if "429" in err_str or "resource_exhausted" in err_lower or "quota" in err_lower:
                        _safe_print(f"🔄 Model '{model}' hit 429 Quota Exhausted. Auto-falling back to next model...")
                    elif "404" in err_str or "not found" in err_lower:
                        _safe_print(f"⚠️ Model '{model}' not found or deprecated (404). Auto-falling back to next model...")
                    else:
                        _safe_print(f"❌ Vision analysis attempt failed for model '{model}': {exc}")
                    continue
        except Exception as init_err:
            last_err = init_err
            _safe_print(f"❌ Failed to initialize Google GenAI Client: {init_err}")
    else:
        last_err = "GEMINI_API_KEY is missing or invalid"

    if not ai_raw_text:
        # Try OpenAI Vision as secondary fallback if API key is present
        openai_res = analyze_meal_image_openai(img_jpeg_bytes, user_text)
        if openai_res:
            _safe_print("✅ Vision analysis succeeded using OpenAI Vision fallback (gpt-4o-mini)")
            ai_raw_text = openai_res.strip()

    if not ai_raw_text:
        # Structured fallback record if vision API failed completely or missing credentials/quota
        err_msg = str(last_err or "Unknown error")
        err_lower = err_msg.lower()

        if "401" in err_msg or "unauthenticated" in err_lower or "invalid authentication" in err_lower or "access_token" in err_lower:
            fallback_risk = "⚠️ Gemini Vision API chưa được xác thực (Lỗi 401 Unauthenticated). Vui lòng kiểm tra lại GEMINI_API_KEY trong file .env."
            fallback_summary = f"Đã ghi nhận: {caption or 'Bữa ăn chưa phân biệt'} (~600 kcal | P: 30g | C: 50g | F: 20g)."
        elif "429" in err_msg or "prepayment" in err_lower or "depleted" in err_lower or "quota" in err_lower:
            fallback_risk = "⚠️ Gemini Vision API tạm thời hết Quota (Lỗi 429 Depleted). Vui lòng kiểm tra lại Quota tại AI Studio."
            fallback_summary = f"Đã ghi nhận: {caption or 'Bữa ăn chưa phân biệt'} (~600 kcal | P: 30g | C: 50g | F: 20g)."
        else:
            fallback_risk = "⚠️ Tạm thời không thể kết nối AI Vision. Bữa ăn đã được ghi nhận vào hệ thống theo chú thích."
            fallback_summary = f"Đã ghi nhận: {caption or 'Bữa ăn chưa phân biệt'} (~600 kcal | P: 30g | C: 50g | F: 20g)."

        return {
            "date": date_str,
            "timestamp": ts_str,
            "meal_type": "Bữa chính",
            "dishes": [caption or "Bữa ăn chưa phân biệt"],
            "total_calories": 600,
            "protein_g": 30.0,
            "carb_g": 50.0,
            "fat_g": 20.0,
            "alcohol_units": 0.0,
            "alcohol_description": "Không ghi nhận",
            "sleep_risk_assessment": fallback_risk,
            "short_summary": fallback_summary,
            "raw_ai_response": str(last_err)
        }

    # Parse JSON output from Gemini
    clean_text = ai_raw_text
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    elif clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    clean_text = clean_text.strip()

    try:
        parsed = json.loads(clean_text)
    except Exception:
        parsed = {}

    parsed["date"] = date_str
    parsed["timestamp"] = ts_str
    parsed["raw_ai_response"] = ai_raw_text

    # Ensure required default keys exist
    parsed.setdefault("meal_type", "Bữa chính")
    parsed.setdefault("dishes", [caption] if caption else ["Bữa ăn"])
    parsed.setdefault("total_calories", 600)
    parsed.setdefault("protein_g", 30.0)
    parsed.setdefault("carb_g", 50.0)
    parsed.setdefault("fat_g", 20.0)
    parsed.setdefault("alcohol_units", 0.0)
    parsed.setdefault("alcohol_description", "")
    parsed.setdefault("sleep_risk_assessment", "✅ Đánh giá Dinh dưỡng & Phục hồi: Khẩu phần nạp phù hợp thể trạng VĐV.")

    if not parsed.get("short_summary"):
        dishes_str = ", ".join(parsed["dishes"]) if isinstance(parsed["dishes"], list) else str(parsed["dishes"])
        parsed["short_summary"] = (
            f"Đã ghi nhận: {dishes_str} (~{parsed['total_calories']} kcal | P: {parsed['protein_g']}g | C: {parsed['carb_g']}g | F: {parsed['fat_g']}g)."
        )

    return sanitize_vision_analysis(parsed, date_str, ts_str)


def analyze_quick_log_text(description_text: str, timestamp: Optional[str] = None) -> Dict[str, Any]:
    """Estimate nutrition macros and sleep risk for a text description using Gemini LLM API."""
    import os
    now_dt = datetime.now()
    date_str = now_dt.strftime("%Y-%m-%d")
    ts_str = timestamp or now_dt.strftime("%Y-%m-%d %H:%M:%S")

    is_mock = os.getenv("MOCK_LLM", "false").lower() == "true" or getattr(settings, "mock_llm", False)
    if is_mock:
        return {
            "date": date_str,
            "timestamp": ts_str,
            "meal_type": "Bữa chính",
            "dishes": [description_text],
            "total_calories": 550,
            "protein_g": 28.0,
            "carb_g": 65.0,
            "fat_g": 18.0,
            "alcohol_units": 0.0,
            "alcohol_description": "Không có cồn",
            "sleep_risk_assessment": "✅ Đánh giá Dinh dưỡng & Phục hồi: Ghi nhận nhanh qua văn bản (Mock Mode).",
            "short_summary": f"Đã ghi nhận (Quick Log): {description_text} (~550 kcal | P: 28g | C: 65g | F: 18g)."
        }

    api_key = (getattr(settings, "gemini_api_key", None) or os.getenv("GEMINI_API_KEY", "") or "").strip().strip('"').strip("'")

    fallback_parsed = {
        "date": date_str,
        "timestamp": ts_str,
        "meal_type": "Bữa ăn",
        "dishes": [description_text],
        "total_calories": 550,
        "protein_g": 28.0,
        "carb_g": 65.0,
        "fat_g": 18.0,
        "alcohol_units": 0.0,
        "alcohol_description": "Không có cồn",
        "sleep_risk_assessment": "✅ Tác động Phục hồi & Giấc ngủ: Ghi nhận nhanh qua văn bản.",
        "short_summary": f"Đã ghi nhận (Quick Log): {description_text} (~550 kcal, 28g Protein)."
    }

    if not api_key or api_key.startswith("your_"):
        return fallback_parsed

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        user_prompt = (
            f"Thời điểm ghi nhận: {ts_str}.\n"
            f"Mô tả món ăn/bữa ăn của vận động viên: '{description_text}'.\n"
            f"Hãy phân tích và ước lượng hàm lượng dinh dưỡng Macros, calo, cồn và đánh giá giấc ngủ."
            + _get_intraday_cumulative_context(date_str, current_ts=ts_str)
        )

        env_model = (getattr(settings, "gemini_model", None) or os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip()

        response = client.models.generate_content(
            model=env_model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=VISION_SYSTEM_PROMPT,
                temperature=0.2,
                response_mime_type="application/json"
            )
        )
        ai_raw_text = (response.text or "").strip()
        if ai_raw_text.startswith("```json"):
            ai_raw_text = ai_raw_text[7:]
        elif ai_raw_text.startswith("```"):
            ai_raw_text = ai_raw_text[3:]
        if ai_raw_text.endswith("```"):
            ai_raw_text = ai_raw_text[:-3]
        ai_raw_text = ai_raw_text.strip()

        parsed = json.loads(ai_raw_text)
        parsed["date"] = date_str
        parsed["timestamp"] = ts_str
        parsed.setdefault("meal_type", "Bữa ăn")
        parsed.setdefault("dishes", [description_text])
        parsed.setdefault("total_calories", 550)
        parsed.setdefault("protein_g", 28.0)
        parsed.setdefault("carb_g", 65.0)
        parsed.setdefault("fat_g", 18.0)
        parsed.setdefault("alcohol_units", 0.0)
        parsed.setdefault("alcohol_description", "Không có cồn")
        parsed.setdefault("sleep_risk_assessment", "✅ Tác động Phục hồi & Giấc ngủ: Ghi nhận nhanh qua văn bản.")
        if not parsed.get("short_summary"):
            parsed["short_summary"] = f"Đã ghi nhận: {description_text} (~{parsed['total_calories']} kcal, {parsed['protein_g']}g Protein)."
        return sanitize_vision_analysis(parsed, date_str, ts_str)
    except Exception as err:
        print(f"⚠️ Quick Log AI estimation fallback: {err}")
        return sanitize_vision_analysis(fallback_parsed, date_str, ts_str)

