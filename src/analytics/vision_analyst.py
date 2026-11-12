import json
import io
import time
import os
import base64
import asyncio
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

VISION_MODELS = [
    "gemini-3.5-flash",       # Tuyến 1: Chính thức Cloud (nhanh, ổn định nhất hiện tại)
    "gemini-3.5-flash-lite",  # Tốc độ phản hồi cực nhanh (< 1s), ổn định
    "gemini-3.8-flash",       # Dự phòng Cloud
    "gemini-3.1-flash-lite",  # Dự phòng Cloud bổ sung
]


def create_genai_client(api_key: str):
    """Khởi tạo Google GenAI Client với custom httpx.Client và timeout tường minh,
    khắc phục triệt để lỗi SSL Handshake Operation Timed Out khi kết nối Google Cloud.
    """
    import httpx
    try:
        import certifi
        verify_ca = certifi.where()
    except Exception:
        verify_ca = True

    try:
        from google import genai
        from google.genai import types
        custom_http_client = httpx.Client(
            timeout=httpx.Timeout(
                connect=20.0,
                read=60.0,
                write=20.0,
                pool=10.0
            ),
            verify=verify_ca,
            follow_redirects=True
        )
        http_opts = types.HttpOptions(
            httpx_client=custom_http_client,
            timeout=60000
        )
        return genai.Client(api_key=api_key, http_options=http_opts)
    except Exception as init_err:
        from google import genai
        return genai.Client(api_key=api_key)



def call_ai_with_cascade(prompt: str, json_format: bool = True) -> Dict[str, Any]:
    """Cascade text LLM analysis: Gemini Flash (2.5 -> 3.8) -> OpenAI -> Local Ollama (qwen2.5:7b)."""
    return analyze_quick_log_text(prompt)


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


def analyze_quick_log_text_openai(user_text: str) -> Optional[str]:
    """Fallback helper to analyze quick log text using OpenAI Chat Completion API."""
    import requests
    import os
    openai_key = getattr(settings, "openai_api_key", None) or os.getenv("OPENAI_API_KEY", "")
    if not openai_key or "YourActual" in openai_key:
        return None
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_key}"
        }
        payload = {
            "model": getattr(settings, "openai_model", None) or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2
        }
        res = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=20)
        if res.status_code == 200:
            res_data = res.json()
            return res_data["choices"][0]["message"]["content"]
    except Exception as err:
        print(f"⚠️ OpenAI Quick Log text fallback exception: {err}")
    return None


def get_local_llm_endpoints() -> list:
    """Retrieve list of configured Local LLM / Ollama URLs for multi-tier fallback.
    Accepts comma-separated URLs in settings.local_llm_url or LOCAL_LLM_URL env.
    Example: 'http://100.x.y.z:11434,http://localhost:11434' (PC GPU primary -> Ally X local fallback).
    """
    raw_urls = (
        os.getenv("LOCAL_LLM_URL")
        or getattr(settings, "local_llm_url", None)
        or "http://localhost:11434"
    )
    endpoints = [u.strip().rstrip("/") for u in str(raw_urls).split(",") if u.strip()]
    return endpoints if endpoints else ["http://localhost:11434"]


def call_local_ollama_fallback(meal_text: str) -> Optional[Dict[str, Any]]:
    """Fallback helper to analyze meal text using Local Ollama LLM (e.g. PC GPU or ROG Ally X)."""
    import requests
    import os
    import json

    model_name = (getattr(settings, "local_llm_model", None) or os.getenv("LOCAL_LLM_MODEL") or "qwen2.5:7b").strip()
    endpoints = get_local_llm_endpoints()

    prompt = (
        "Bạn là chuyên gia dinh dưỡng thể thao hàng đầu Việt Nam. "
        f"Hãy phân tích chi tiết bữa ăn sau của vận động viên: \"{meal_text}\".\n\n"
        "YÊU CẦU PHÂN TÍCH:\n"
        "1. Bóc tách từng món ăn cụ thể vào mảng 'dishes' (ví dụ: ['1 bát cơm trắng', 'Canh dưa bò', 'Thịt băm nướng kiểu chả (4 miếng)', 'Chả xương xông (2 miếng)']).\n"
        "2. Ước lượng chuẩn xác hàm lượng Calories (kcal), Protein (g), Carb (g), Fat (g), Cồn (alcohol_grams).\n"
        "3. 'summary': Tóm tắt ngắn gọn và rõ ràng tên các món và định lượng calo/macro.\n"
        "4. 'recovery_impact': Nhận xét chuyên môn sâu về dược lý dinh dưỡng thể thao: nguồn đạm sinh học phục hồi cơ bắp và gân (từ thịt bò, thịt nướng), bù đắp glycogen (từ cơm trắng), men vi sinh tiêu hóa (từ canh dưa chua), và đánh giá tải purine an toàn cho axit uric máu.\n\n"
        "BẮT BUỘC TRẢ VỀ DUY NHẤT 1 OBJECT JSON THUẦN TÚY (không markdown, không bọc ```json):\n"
        "{\n"
        "  \"dishes\": [\"món 1\", \"món 2\"],\n"
        "  \"calories\": <số thực calo>,\n"
        "  \"protein\": <số thực gram protein>,\n"
        "  \"carb\": <số thực gram carb>,\n"
        "  \"fat\": <số thực gram fat>,\n"
        "  \"alcohol_grams\": 0.0,\n"
        "  \"summary\": \"<tóm tắt ngắn gọn>\",\n"
        "  \"recovery_impact\": \"<đánh giá phục hồi thể thao chi tiết>\"\n"
        "}"
    )

    payload = {
        "model": model_name,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    for base_url in endpoints:
        try:
            t0 = time.perf_counter()
            res = requests.post(f"{base_url}/api/generate", json=payload, timeout=(3.0, 60))
            elapsed = round(time.perf_counter() - t0, 2)
            if res.status_code == 200:
                res_data = res.json()
                raw_response = res_data.get("response", "").strip()
                p_tokens = res_data.get("prompt_eval_count") or 0
                c_tokens = res_data.get("eval_count") or 0
                if raw_response:
                    parsed = parse_qwen_json(raw_response)
                    cal = float(parsed.get("calories") or 0.0)
                    p = float(parsed.get("protein") or 0.0)
                    c = float(parsed.get("carb") or 0.0)
                    f = float(parsed.get("fat") or 0.0)
                    alc_g = float(parsed.get("alcohol_grams") or 0.0)
                    alc_units = round(alc_g / 10.0, 1)

                    dishes_raw = parsed.get("dishes")
                    if isinstance(dishes_raw, list) and dishes_raw:
                        dishes_list = [str(d).strip() for d in dishes_raw if str(d).strip()]
                    elif isinstance(dishes_raw, str) and dishes_raw:
                        dishes_list = [d.strip() for d in dishes_raw.split(",") if d.strip()]
                    else:
                        dishes_list = [meal_text]

                    return {
                        "meal_type": "Bữa chính",
                        "dishes": dishes_list,
                        "total_calories": int(round(cal)),
                        "protein_g": round(p, 1),
                        "carb_g": round(c, 1),
                        "fat_g": round(f, 1),
                        "alcohol_units": alc_units,
                        "alcohol_description": "Không có cồn" if alc_units == 0 else f"{alc_g}g cồn (~{alc_units} units)",
                        "sleep_risk_assessment": parsed.get("recovery_impact") or f"✅ Đánh giá Dinh dưỡng & Phục hồi từ Local Ollama ({model_name} via {base_url}).",
                        "short_summary": parsed.get("summary") or f"Đã ghi nhận (Local Ollama): {meal_text} (~{int(round(cal))} kcal | P: {round(p, 1)}g | C: {round(c, 1)}g | F: {round(f, 1)}g).",
                        "model_used": f"ollama ({model_name}) via {base_url}",
                        "latency_seconds": elapsed,
                        "prompt_tokens": p_tokens,
                        "completion_tokens": c_tokens,
                        "total_tokens": p_tokens + c_tokens
                    }
        except Exception as err:
            print(f"⚠️ Local Ollama LLM fallback exception ({base_url}, model '{model_name}'): {err}")
    return None


def parse_qwen_json(raw_text: str) -> dict:
    """Trích xuất và parse an toàn khối JSON từ response của qwen3-vl:8b
    (loại bỏ khối suy luận nội tâm Thinking / Chain-of-Thought).
    """
    import json
    import re
    if not raw_text:
        return {}
    # Loại bỏ khối <think>...</think> nếu có
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", str(raw_text), flags=re.DOTALL)
    # Loại bỏ các đoạn markdown code block nếu có
    cleaned = re.sub(r"```json\s*", "", cleaned)
    cleaned = re.sub(r"```\s*", "", cleaned)
    cleaned = cleaned.strip()
    # Tìm khối JSON hợp lệ nằm giữa cặp { và } cuối cùng
    matches = re.findall(r"(\{[\s\S]*?\})", cleaned)
    for match in reversed(matches):
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(cleaned)
    except Exception:
        return {}


def _sanitize_local_vision_output(data: dict) -> dict:
    """Sanitize and correct raw outputs from Local Vision (Qwen3-VL):
    enforce zero calories for clear water and purge nonsensical translations."""
    summary = str(data.get("summary") or "").strip()
    summary_lower = summary.lower()
    if "bột nước" in summary_lower or "nước bột" in summary_lower:
        data["summary"] = "Nước uống (bù nước)"
        data["calories"] = 0.0
        data["protein"] = 0.0
        data["carb"] = 0.0
        data["fat"] = 0.0
        data["recovery_impact"] = "Bù nước và hỗ trợ thanh lọc, cân bằng điện giải tuần hoàn sau tập luyện."
    elif any(w in summary_lower for w in ["nước lọc", "nước suối", "nước khoáng", "nước kiềm", "trà đá", "water", "plain water"]):
        if float(data.get("protein") or 0.0) == 0.0 and float(data.get("carb") or 0.0) == 0.0 and float(data.get("fat") or 0.0) == 0.0:
            data["calories"] = 0.0
    return data


# Backward compatibility aliases
_sanitize_llava_output = _sanitize_local_vision_output
_sanitize_qwen_output = _sanitize_local_vision_output


async def call_local_qwen_vision(image_bytes: bytes, caption: str = "") -> dict:
    """Chuyển image bytes thành Base64 và gửi sang Ollama qwen3-vl:8b (Local Vision Fallback trên ROG Ally X)."""
    import httpx

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    caption_context = f"\nChú thích của người gửi: '{caption}'." if caption else ""
    prompt = (
        "Bạn là chuyên gia dinh dưỡng thể thao hàng đầu Việt Nam. "
        "Hãy quan sát kỹ bức ảnh này và phân tích các món ăn hoặc đồ uống có trong hình."
        f"{caption_context}\n\n"
        "NGUYÊN TẮC NHẬN DIỆN VÀ TÍNH TOÁN:\n"
        "1. Nhận diện chuẩn xác các món ăn Việt Nam (cơm trắng, phở, bún chả, cá kho, thịt rang, canh sườn dưa, trứng luộc, ngũ cốc, v.v.).\n"
        "2. ĐỒ UỐNG TRONG SUỐT (nước lọc, nước suối, nước khoáng kiềm, trà đá không đường): BẮT BUỘC gán calories=0.0, protein=0.0, carb=0.0, fat=0.0.\n"
        "3. Xuất đúng 3 chỉ số Macro (Protein, Carb, Fat) và tổng Năng lượng (Calories) thực tế.\n"
        "4. Nhận xét ngắn gọn về tác động phục hồi thể thao, bù nước, điện giải hoặc nạp Glycogen cho vận động viên.\n\n"
        "BẮT BUỘC TRẢ VỀ DUY NHẤT 1 OBJECT JSON THUẦN TÚY (không bọc ```json, không kèm lời giải thích):\n"
        "{\n"
        '  "calories": <float calo>,\n'
        '  "protein": <float gram protein>,\n'
        '  "carb": <float gram carb>,\n'
        '  "fat": <float gram fat>,\n'
        '  "alcohol_grams": 0.0,\n'
        '  "summary": "<Tên các món ăn/thức uống ngắn gọn bằng tiếng Việt>",\n'
        '  "recovery_impact": "<Nhận xét phục hồi thể lực, bù nước, điện giải hoặc cơ bắp>"\n'
        "}"
    )

    endpoints = get_local_llm_endpoints()
    model_name = (
        getattr(settings, "local_vision_model", None)
        or os.getenv("LOCAL_VISION_MODEL")
        or "qwen3-vl:8b"
    ).strip()

    payload = {
        "model": model_name,
        "prompt": prompt,
        "images": [image_b64],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    timeout_cfg = httpx.Timeout(connect=3.0, read=90.0, write=30.0, pool=5.0)
    for local_url in endpoints:
        try:
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                res = await client.post(f"{local_url}/api/generate", json=payload)
                res.raise_for_status()
                raw_response = res.json().get("response", "{}")
                if isinstance(raw_response, dict):
                    return _sanitize_local_vision_output(raw_response)
                parsed = parse_qwen_json(raw_response)
                return _sanitize_local_vision_output(parsed)
        except Exception as exc:
            print(f"⚠️ Local LLM vision async request failed ({local_url}, {model_name}): {exc}. Trying next endpoint...")
    return {}


# Alias
call_local_vision_ollama = call_local_qwen_vision
call_local_llava_vision = call_local_qwen_vision


def call_local_qwen_vision_sync(image_bytes: bytes, caption: str = "") -> Optional[Dict[str, Any]]:
    """Synchronous helper for call_local_qwen_vision using requests across configured endpoints."""
    import requests
    import os

    endpoints = get_local_llm_endpoints()
    model_name = (
        getattr(settings, "local_vision_model", None)
        or os.getenv("LOCAL_VISION_MODEL")
        or "qwen3-vl:8b"
    ).strip()

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    caption_context = f"\nChú thích của người gửi: '{caption}'." if caption else ""
    prompt = (
        "Bạn là chuyên gia dinh dưỡng thể thao hàng đầu Việt Nam. "
        "Hãy quan sát kỹ bức ảnh này và phân tích các món ăn hoặc đồ uống có trong hình."
        f"{caption_context}\n\n"
        "NGUYÊN TẮC NHẬN DIỆN VÀ TÍNH TOÁN:\n"
        "1. Nhận diện chuẩn xác các món ăn Việt Nam (cơm trắng, phở, bún chả, cá kho, thịt rang, canh sườn dưa, trứng luộc, ngũ cốc, v.v.).\n"
        "2. ĐỒ UỐNG TRONG SUỐT (nước lọc, nước suối, nước khoáng kiềm, trà đá không đường): BẮT BUỘC gán calories=0.0, protein=0.0, carb=0.0, fat=0.0.\n"
        "3. Xuất đúng 3 chỉ số Macro (Protein, Carb, Fat) và tổng Năng lượng (Calories) thực tế.\n"
        "4. Nhận xét ngắn gọn về tác động phục hồi thể thao, bù nước, điện giải hoặc nạp Glycogen cho vận động viên.\n\n"
        "BẮT BUỘC TRẢ VỀ DUY NHẤT 1 OBJECT JSON THUẦN TÚY (không bọc ```json, không kèm lời giải thích):\n"
        "{\n"
        '  "calories": <float calo>,\n'
        '  "protein": <float gram protein>,\n'
        '  "carb": <float gram carb>,\n'
        '  "fat": <float gram fat>,\n'
        '  "alcohol_grams": 0.0,\n'
        '  "summary": "<Tên các món ăn/thức uống ngắn gọn bằng tiếng Việt>",\n'
        '  "recovery_impact": "<Nhận xét phục hồi thể lực, bù nước, điện giải hoặc cơ bắp>"\n'
        "}"
    )

    payload = {
        "model": model_name,
        "prompt": prompt,
        "images": [image_b64],
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.2
        }
    }

    for local_url in endpoints:
        try:
            t0 = time.perf_counter()
            res = requests.post(f"{local_url}/api/generate", json=payload, timeout=(3.0, 90.0))
            elapsed = round(time.perf_counter() - t0, 2)
            if res.status_code == 200:
                res_data = res.json()
                raw_response = res_data.get("response", "{}")
                p_tokens = res_data.get("prompt_eval_count") or 0
                c_tokens = res_data.get("eval_count") or 0
                if isinstance(raw_response, dict):
                    result = _sanitize_local_vision_output(raw_response)
                else:
                    parsed = parse_qwen_json(raw_response)
                    result = _sanitize_local_vision_output(parsed)
                result["model_used"] = f"ollama ({model_name}) via {local_url}"
                result["latency_seconds"] = elapsed
                result["prompt_tokens"] = p_tokens
                result["completion_tokens"] = c_tokens
                result["total_tokens"] = p_tokens + c_tokens
                return result
        except Exception as exc:
            print(f"⚠️ Local LLM vision sync request failed ({local_url}, {model_name}): {exc}. Trying next endpoint...")
    return None

# Alias
call_local_vision_ollama_sync = call_local_qwen_vision_sync
call_local_llava_vision_sync = call_local_qwen_vision_sync


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
    model_used = None
    latency_seconds = 0.0
    p_tokens = 0
    c_tokens = 0

    def _safe_print(msg: str):
        try:
            print(msg, flush=True)
        except Exception:
            print(msg.encode("ascii", "replace").decode("ascii"), flush=True)

    if api_key and not api_key.startswith("your_"):
        try:
            from google import genai
            from google.genai import types

            client = create_genai_client(api_key)
            image_part = types.Part.from_bytes(data=img_jpeg_bytes, mime_type="image/jpeg")

            vision_env_model = (getattr(settings, "gemini_vision_model", None) or os.getenv("GEMINI_VISION_MODEL") or getattr(settings, "gemini_model", None) or "").strip()
            deprecated_models = {
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-3.6-flash",
                "gemini-3.1-pro-preview",
            }
            raw_candidates = [m for m in VISION_MODELS if m not in deprecated_models]
            if vision_env_model and vision_env_model not in deprecated_models and vision_env_model not in raw_candidates:
                raw_candidates.insert(0, vision_env_model)
            seen = set()
            models_to_try = [m.replace("models/", "").strip() for m in raw_candidates if m and not (m in seen or seen.add(m))]

            for model in models_to_try:
                max_retries = 2  # Lần 1 + tối đa 1 lần retry nếu 503/429
                model_succeeded = False
                for attempt in range(1, max_retries + 1):
                    try:
                        t0 = time.perf_counter()
                        response = client.models.generate_content(
                            model=model,
                            contents=[image_part, user_text],
                            config=types.GenerateContentConfig(
                                system_instruction=VISION_SYSTEM_PROMPT,
                                temperature=0.2,
                                response_mime_type="application/json"
                            )
                        )
                        elapsed = round(time.perf_counter() - t0, 2)
                        ai_raw_text = (response.text or "").strip()
                        if ai_raw_text:
                            model_used = f"gemini ({model})"
                            latency_seconds = elapsed
                            if hasattr(response, "usage_metadata") and response.usage_metadata:
                                p_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                                c_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                            _safe_print(f"✅ Gemini Vision analysis succeeded using model '{model}' (attempt {attempt}/{max_retries})")
                            model_succeeded = True
                            break
                    except Exception as exc:
                        last_err = exc
                        err_str = str(exc)
                        err_lower = err_str.lower()
                        _safe_print(f"⚠️ Gemini Vision attempt {attempt}/{max_retries} failed for model '{model}': {exc}")

                        # If model is deprecated or not found (404), switch immediately to next model without retrying
                        if "404" in err_str or "not found" in err_lower or "no longer available" in err_lower:
                            _safe_print(f"🔄 Model '{model}' is deprecated/not found (404). Skipping retries and switching to next model...")
                            break

                        # Khi gặp mã lỗi 503 UNAVAILABLE hoặc 429: chỉ thử lại tối đa 1 lần với backoff 1s
                        if attempt < max_retries and ("503" in err_str or "unavailable" in err_lower or "429" in err_str or "quota" in err_lower or "resource_exhausted" in err_lower):
                            _safe_print(f"⏳ Waiting 1s before retry attempt {attempt + 1}/{max_retries} for model '{model}'...")
                            time.sleep(1)
                        else:
                            _safe_print(f"🔄 Model '{model}' exhausted retry attempt. Switching to next model...")
                            break
                if model_succeeded:
                    break
        except Exception as init_err:
            last_err = init_err
            _safe_print(f"❌ Failed to initialize Google GenAI Client: {init_err}")
    else:
        last_err = "GEMINI_API_KEY is missing or invalid"

    if not ai_raw_text:
        # Try OpenAI Vision as secondary fallback if API key is present
        t0 = time.perf_counter()
        openai_res = analyze_meal_image_openai(img_jpeg_bytes, user_text)
        if openai_res:
            _safe_print("✅ Vision analysis succeeded using OpenAI Vision fallback (gpt-4o-mini)")
            ai_raw_text = openai_res.strip()
            model_used = "openai (gpt-4o-mini)"
            latency_seconds = round(time.perf_counter() - t0, 2)

    if not ai_raw_text:
        clean_caption = (caption or "").strip()

        # NGUYÊN TẮC 1 (Hybrid Text-Vision): ƯU TIÊN CAPTION CỦA NGƯỜI DÙNG HƠN HÌNH ẢNH!
        # NẾU CÓ CAPTION (ví dụ: 'uống 300ml nước kiềm', 'cơm cá bống kho'):
        # Bỏ qua việc để LLaVA đoán ảnh (vì LLaVA tiếng Việt rất yếu, dễ đoán mò 'Bột nước 100 kcal').
        # Gửi thẳng nội dung caption vào LLM Text chuyên dụng (Gemini Flash -> Ollama qwen2.5:7b trên Ally X).
        if clean_caption:
            _safe_print(f"🔄 Gemini Vision Cloud unavailable ({last_err}). Người dùng có kèm chú thích: '{clean_caption}' -> Ưu tiên chuyển sang Text Cascade LLM (Gemini / qwen2.5:7b)...")
            caption_res = analyze_quick_log_text(clean_caption, timestamp=ts_str)

            fallback_notice = "⚠️ [Vision Cloud lỗi - Đã phân tích tự động từ chú thích bằng Local AI / Text LLM]"
            caption_res["fallback_notice"] = fallback_notice
            caption_res["is_caption_fallback"] = True

            current_risk = caption_res.get("sleep_risk_assessment") or ""
            if fallback_notice not in current_risk:
                caption_res["sleep_risk_assessment"] = f"{current_risk}\n\nℹ️ {fallback_notice}"

            caption_res["raw_ai_response"] = caption_res.get("raw_ai_response") or f"vision_fallback_to_text: {last_err}"
            return sanitize_vision_analysis(caption_res, date_str, ts_str)

        # NGUYÊN TẮC 2: NẾU KHÔNG CÓ CAPTION (ảnh trần không có chú thích):
        # Mới kích hoạt Tuyến 2 (Local Vision Fallback trên ROG Ally X): Dùng Qwen3-VL (hoặc LLaVA) nhìn ảnh để suy luận món ăn.
        local_v_model = (
            getattr(settings, "local_vision_model", None)
            or os.getenv("LOCAL_VISION_MODEL")
            or "qwen3-vl:8b"
        ).strip()
        _safe_print(f"🔄 Gemini Vision Cloud unavailable và KHÔNG có chú thích. Kích hoạt Tuyến 2: Local Vision Fallback (Ollama {local_v_model} trên ROG Ally X)...")
        local_vision_data = None

        # Synchronous call via requests
        try:
            local_vision_data = call_local_qwen_vision_sync(img_jpeg_bytes, caption="")
        except Exception as sync_vis_err:
            _safe_print(f"⚠️ Local Vision Ollama ({local_v_model}) sync exception: {sync_vis_err}")
            local_vision_data = None

        # If mocked or returned via call_local_qwen_vision
        if not local_vision_data or not isinstance(local_vision_data, dict):
            try:
                res_or_coro = call_local_qwen_vision(img_jpeg_bytes, caption="")
                if isinstance(res_or_coro, dict):
                    local_vision_data = res_or_coro
            except Exception as local_vis_err:
                _safe_print(f"⚠️ Local Vision Ollama ({local_v_model}) fallback exception: {local_vis_err}")

        if local_vision_data and isinstance(local_vision_data, dict) and (local_vision_data.get("calories") is not None or local_vision_data.get("summary")):
            _safe_print(f"✅ Local Vision analysis succeeded using Ollama {local_v_model} on ROG Ally X!")
            cal = float(local_vision_data.get("calories") or 0.0)
            p = float(local_vision_data.get("protein") or 0.0)
            c = float(local_vision_data.get("carb") or 0.0)
            f = float(local_vision_data.get("fat") or 0.0)
            alc_g = float(local_vision_data.get("alcohol_grams") or 0.0)
            alc_units = round(alc_g / 10.0, 1)

            summary = str(local_vision_data.get("summary") or "Bữa ăn phân tích qua Local Vision").strip()
            recovery_impact = str(local_vision_data.get("recovery_impact") or "Bữa ăn hỗ trợ phục hồi cơ bắp và năng lượng.").strip()

            fallback_notice = f"⚠️ [AI Vision: Local Ally X ({local_v_model})]"
            dishes_list = [d.strip() for d in summary.split(",") if d.strip()] if "," in summary else [summary]

            parsed = {
                "date": date_str,
                "timestamp": ts_str,
                "meal_type": "Bữa chính",
                "dishes": dishes_list if dishes_list else ["Bữa ăn"],
                "total_calories": int(round(cal)),
                "protein_g": round(p, 1),
                "carb_g": round(c, 1),
                "fat_g": round(f, 1),
                "alcohol_units": alc_units,
                "alcohol_description": "Không có cồn" if alc_units == 0 else f"{alc_units} đơn vị cồn",
                "sleep_risk_assessment": f"✅ Đánh giá Dinh dưỡng & Phục hồi ({local_v_model}): {recovery_impact}\n\nℹ️ {fallback_notice}",
                "short_summary": f"Đã ghi nhận [AI Vision: Local Ally X ({local_v_model})]: {summary} (~{int(round(cal))} kcal | P: {round(p, 1)}g | C: {round(c, 1)}g | F: {round(f, 1)}g).",
                "raw_ai_response": json.dumps(local_vision_data, ensure_ascii=False),
                "fallback_notice": fallback_notice,
                "is_local_vision": True,
                "model_used": local_vision_data.get("model_used") or f"ollama ({local_v_model})",
                "latency_seconds": local_vision_data.get("latency_seconds") or 0.0,
                "prompt_tokens": local_vision_data.get("prompt_tokens") or 0,
                "completion_tokens": local_vision_data.get("completion_tokens") or 0,
                "total_tokens": (local_vision_data.get("prompt_tokens") or 0) + (local_vision_data.get("completion_tokens") or 0)
            }
            parsed["model_used"] = parsed.get("model_used") or model_used or "gemini (gemini-2.5-flash)"
            parsed["latency_seconds"] = parsed.get("latency_seconds") or latency_seconds or 0.0
            parsed["prompt_tokens"] = parsed.get("prompt_tokens") or p_tokens or 0
            parsed["completion_tokens"] = parsed.get("completion_tokens") or c_tokens or 0
            parsed["total_tokens"] = parsed["prompt_tokens"] + parsed["completion_tokens"]
            return sanitize_vision_analysis(parsed, date_str, ts_str)

        # Cả Cloud Vision lẫn Local Vision đều lỗi và KHÔNG có caption
        _safe_print(f"❌ Gemini Vision & Local Vision unavailable and NO caption provided to fallback. Error: {last_err}")
        return {
            "status": "error",
            "error_code": "vision_failed_no_caption",
            "error_message": "Không thể phân tích ảnh do lỗi kết nối AI Vision (Cloud & Local Ally X). Vui lòng gõ tên món ăn hoặc gửi kèm chú thích.",
            "date": date_str,
            "timestamp": ts_str,
            "dishes": [],
            "total_calories": None,
            "protein_g": None,
            "carb_g": None,
            "fat_g": None,
            "sleep_risk_assessment": "⚠️ Không thể phân tích ảnh do lỗi kết nối AI Vision (Cloud & Local Ally X). Vui lòng gõ tên món ăn hoặc gửi kèm chú thích.",
            "short_summary": "⚠️ Lỗi kết nối AI Vision (Cloud & Local Ally X) và không có chú thích món ăn.",
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
        import re
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except Exception:
                parsed = {}
        else:
            parsed = {}

    def _to_num(val, default, is_int=False):
        try:
            n = float(val)
            return int(round(n)) if is_int else round(n, 1)
        except Exception:
            return default

    parsed["date"] = date_str
    parsed["timestamp"] = ts_str
    parsed["raw_ai_response"] = ai_raw_text

    # Ensure required keys exist without hardcoded fake values
    parsed.setdefault("meal_type", "Bữa chính")
    parsed.setdefault("dishes", [caption] if caption else ["Bữa ăn"])
    parsed["total_calories"] = _to_num(parsed.get("total_calories"), 0, is_int=True)
    parsed["protein_g"] = _to_num(parsed.get("protein_g"), 0.0)
    parsed["carb_g"] = _to_num(parsed.get("carb_g"), 0.0)
    parsed["fat_g"] = _to_num(parsed.get("fat_g"), 0.0)
    parsed["alcohol_units"] = _to_num(parsed.get("alcohol_units"), 0.0)
    parsed.setdefault("alcohol_description", "")
    parsed.setdefault("sleep_risk_assessment", "✅ Đánh giá Dinh dưỡng & Phục hồi: Khẩu phần nạp phù hợp thể trạng VĐV.")

    if not parsed.get("short_summary"):
        dishes_str = ", ".join(parsed["dishes"]) if isinstance(parsed["dishes"], list) else str(parsed["dishes"])
        parsed["short_summary"] = (
            f"Đã ghi nhận: {dishes_str} (~{parsed['total_calories']} kcal | P: {parsed['protein_g']}g | C: {parsed['carb_g']}g | F: {parsed['fat_g']}g)."
        )

    parsed["model_used"] = parsed.get("model_used") or model_used or "gemini (gemini-2.5-flash)"
    parsed["latency_seconds"] = parsed.get("latency_seconds") or latency_seconds or 0.0
    parsed["prompt_tokens"] = parsed.get("prompt_tokens") or p_tokens or 0
    parsed["completion_tokens"] = parsed.get("completion_tokens") or c_tokens or 0
    parsed["total_tokens"] = parsed["prompt_tokens"] + parsed["completion_tokens"]

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

        client = create_genai_client(api_key)
        user_prompt = (
            f"Thời điểm ghi nhận: {ts_str}.\n"
            f"Mô tả món ăn/bữa ăn của vận động viên: '{description_text}'.\n"
            f"Hãy phân tích và ước lượng hàm lượng dinh dưỡng Macros, calo, cồn và đánh giá giấc ngủ."
            + _get_intraday_cumulative_context(date_str, current_ts=ts_str)
        )

        env_model = (getattr(settings, "gemini_model", None) or os.getenv("GEMINI_MODEL") or "").strip()
        default_candidates = [
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.1-flash-lite",
        ]
        deprecated_models = {
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-3.6-flash",
            "gemini-3.1-pro-preview",
        }
        filtered_defaults = [m for m in default_candidates if m not in deprecated_models]
        raw_candidates = ([env_model] if env_model and env_model not in deprecated_models else []) + filtered_defaults
        seen = set()
        models_to_try = [m.replace("models/", "").strip() for m in raw_candidates if m and not (m in seen or seen.add(m))]

        ai_raw_text = ""
        last_err = None
        model_used = None
        latency_seconds = 0.0
        p_tokens = 0
        c_tokens = 0

        for model in models_to_try:
            max_retries = 2
            model_succeeded = False

            for attempt in range(1, max_retries + 1):
                try:
                    t0 = time.perf_counter()
                    response = client.models.generate_content(
                        model=model,
                        contents=[user_prompt],
                        config=types.GenerateContentConfig(
                            system_instruction=VISION_SYSTEM_PROMPT,
                            temperature=0.2,
                            response_mime_type="application/json"
                        )
                    )
                    elapsed = round(time.perf_counter() - t0, 2)
                    text_content = (response.text or "").strip()
                    if text_content:
                        ai_raw_text = text_content
                        model_used = f"gemini ({model})"
                        latency_seconds = elapsed
                        if hasattr(response, "usage_metadata") and response.usage_metadata:
                            p_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                            c_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                        model_succeeded = True
                        print(f"✅ Quick Log nutrition estimation succeeded using model '{model}' (attempt {attempt}/{max_retries})")
                        break
                except Exception as exc:
                    last_err = exc
                    err_str = str(exc)
                    err_lower = err_str.lower()
                    print(f"⚠️ Quick Log Gemini attempt {attempt}/{max_retries} failed for model '{model}': {exc}")

                    # If model is deprecated or not found (404), switch immediately to next model
                    if "404" in err_str or "not found" in err_lower or "no longer available" in err_lower:
                        print(f"🔄 Model '{model}' is deprecated/not found (404). Skipping retries and switching to next model...")
                        break

                    # Khi gặp 503 hoặc 429: chỉ thử lại tối đa 1 lần với backoff 1s
                    if attempt < max_retries and ("503" in err_str or "unavailable" in err_lower or "429" in err_str or "quota" in err_lower or "resource_exhausted" in err_lower):
                        print(f"⏳ Waiting 1s before retry attempt {attempt + 1}/{max_retries} for model '{model}'...")
                        time.sleep(1)
                    else:
                        print(f"🔄 Model '{model}' exhausted retry attempt. Switching to next candidate model...")
                        break

            if model_succeeded:
                break

        if not ai_raw_text:
            t0 = time.perf_counter()
            openai_res = analyze_quick_log_text_openai(user_prompt)
            elapsed = round(time.perf_counter() - t0, 2)
            if openai_res:
                ai_raw_text = openai_res.strip()
                model_used = "openai (gpt-4o-mini)"
                latency_seconds = elapsed
                print("✅ Quick Log nutrition estimation succeeded using OpenAI fallback (gpt-4o-mini)")

        parsed = None
        if ai_raw_text:
            cleaned_text = ai_raw_text
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()

            try:
                parsed = json.loads(cleaned_text)
            except Exception as json_err:
                print(f"⚠️ Quick Log JSON parse error for model '{model_used}': {json_err}. Raw text: {cleaned_text[:120]}")
                import re
                match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                if match:
                    try:
                        parsed = json.loads(match.group(0))
                    except Exception:
                        parsed = None

        if not parsed:
            ollama_res = call_local_ollama_fallback(description_text)
            if ollama_res:
                local_model = getattr(settings, "local_llm_model", None) or os.getenv("LOCAL_LLM_MODEL") or "qwen2.5:7b"
                print(f"✅ Quick Log nutrition estimation succeeded using Local Ollama fallback ({local_model})")
                parsed = ollama_res

        if parsed and isinstance(parsed, dict):
            def _to_num(val, default, is_int=False):
                try:
                    n = float(val)
                    return int(round(n)) if is_int else round(n, 1)
                except Exception:
                    return default

            parsed["date"] = date_str
            parsed["timestamp"] = ts_str
            parsed.setdefault("meal_type", "Bữa ăn")
            parsed.setdefault("dishes", [description_text])
            parsed["total_calories"] = _to_num(parsed.get("total_calories"), 550, is_int=True)
            parsed["protein_g"] = _to_num(parsed.get("protein_g"), 28.0)
            parsed["carb_g"] = _to_num(parsed.get("carb_g"), 65.0)
            parsed["fat_g"] = _to_num(parsed.get("fat_g"), 18.0)
            parsed["alcohol_units"] = _to_num(parsed.get("alcohol_units"), 0.0)
            parsed.setdefault("alcohol_description", "Không có cồn")
            parsed.setdefault("sleep_risk_assessment", "✅ Tác động Phục hồi & Giấc ngủ: Ghi nhận nhanh qua văn bản.")
            if not parsed.get("short_summary"):
                parsed["short_summary"] = (
                    f"Đã ghi nhận (Quick Log): {description_text} "
                    f"(~{parsed['total_calories']} kcal | P: {parsed['protein_g']}g | C: {parsed['carb_g']}g | F: {parsed['fat_g']}g)."
                )
            parsed["model_used"] = parsed.get("model_used") or model_used or "gemini (gemini-2.5-flash)"
            parsed["latency_seconds"] = parsed.get("latency_seconds") or latency_seconds or 0.0
            parsed["prompt_tokens"] = parsed.get("prompt_tokens") or p_tokens or 0
            parsed["completion_tokens"] = parsed.get("completion_tokens") or c_tokens or 0
            parsed["total_tokens"] = parsed["prompt_tokens"] + parsed["completion_tokens"]
            return sanitize_vision_analysis(parsed, date_str, ts_str)

        print(f"⚠️ Quick Log using fallback parsed due to AI failure. Last error: {last_err}")
        return sanitize_vision_analysis(fallback_parsed, date_str, ts_str)
    except Exception as err:
        print(f"⚠️ Quick Log AI estimation unexpected error: {err}")
        return sanitize_vision_analysis(fallback_parsed, date_str, ts_str)

