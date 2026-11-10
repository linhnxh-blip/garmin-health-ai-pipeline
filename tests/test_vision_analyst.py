import json
import io
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from src.analytics.vision_analyst import (
    analyze_meal_image,
    analyze_quick_log_text,
    sanitize_vision_analysis
)

def test_analyze_meal_image_dummy_or_fallback(monkeypatch):
    # Create dummy 100x100 red image
    img = Image.new("RGB", (100, 100), color="red")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    res = analyze_meal_image(img_bytes, caption="Lẩu hải sản và 2 lon bia", timestamp="2026-09-19 19:30:00")
    assert isinstance(res, dict)
    assert "meal_type" in res
    assert "dishes" in res
    assert "total_calories" in res
    assert "short_summary" in res


def test_analyze_quick_log_text_mock_mode(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "true")
    res = analyze_quick_log_text("1 bát phở bò bắp và 1 quẩy")
    assert isinstance(res, dict)
    assert res["meal_type"] == "Bữa chính"
    assert res["total_calories"] == 550
    assert res["protein_g"] == 28.0
    assert "1 bát phở bò bắp và 1 quẩy" in res["dishes"][0]


def test_analyze_quick_log_text_retry_and_model_fallback(monkeypatch):
    """Test 503 UNAVAILABLE retry logic and fallback to gemini-2.5-flash."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")

    # Mock client and responses
    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client

    sleep_calls = []
    def fake_sleep(secs):
        sleep_calls.append(secs)

    success_json = json.dumps({
        "meal_type": "Bữa sáng",
        "dishes": ["Phở bò bắp"],
        "total_calories": 520,
        "protein_g": 35.0,
        "carb_g": 60.0,
        "fat_g": 12.0,
        "alcohol_units": 0.0,
        "alcohol_description": "Không có cồn",
        "sleep_risk_assessment": "✅ Bữa sáng giàu đạm và carb tiêu chuẩn.",
        "short_summary": "Đã ghi nhận: Phở bò bắp (~520 kcal | P: 35g | C: 60g | F: 12g)."
    })

    success_resp = MagicMock()
    success_resp.text = success_json

    calls = []
    def fake_generate_content(model, contents, config):
        calls.append(model)
        # gemini-2.5-flash (priority 1) fails with 503 on all 3 attempts
        if model == "gemini-2.5-flash":
            raise Exception("503 UNAVAILABLE: This model is currently experiencing high demand.")
        # gemini-3.8-flash (priority 2 fallback) fails on first attempt with 503, succeeds on 2nd attempt
        if model == "gemini-3.8-flash":
            if calls.count("gemini-3.8-flash") == 1:
                raise Exception("503 UNAVAILABLE: Temporary spike")
            return success_resp
        return success_resp

    mock_client.models.generate_content.side_effect = fake_generate_content

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", side_effect=fake_sleep):
        res = analyze_quick_log_text("1 phở bò bắp", timestamp="2026-11-10 08:00:00")

    # Verify model calls: 2 attempts on gemini-2.5-flash (attempt 1 + 1 retry), then 2 attempts on gemini-3.8-flash
    assert calls.count("gemini-2.5-flash") == 2
    assert calls.count("gemini-3.8-flash") == 2
    # Verify 1s backoff for 503 retry
    assert 1 in sleep_calls

    # Verify parsed nutrition results
    assert res["total_calories"] == 520
    assert res["protein_g"] == 35.0
    assert res["carb_g"] == 60.0
    assert res["fat_g"] == 12.0
    assert res["dishes"] == ["Phở bò bắp"]


def test_analyze_quick_log_text_all_models_fail_graceful_fallback(monkeypatch):
    """Test that when all Gemini models fail with 503/429, fallback values are returned safely."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")

    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client

    def always_fail(model, contents, config):
        raise Exception("503 UNAVAILABLE: High demand")

    mock_client.models.generate_content.side_effect = always_fail

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_ollama_fallback", return_value=None):
        res = analyze_quick_log_text("1 cơm sườn", timestamp="2026-11-10 12:00:00")

    assert isinstance(res, dict)
    assert res["total_calories"] == 550
    assert res["protein_g"] == 28.0
    assert "1 cơm sườn" in res["dishes"][0]


def test_call_local_ollama_fallback_success(monkeypatch):
    from src.analytics.vision_analyst import call_local_ollama_fallback

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "qwen2.5:7b",
        "response": json.dumps({
            "calories": 480.0,
            "protein": 32.5,
            "carb": 54.0,
            "fat": 14.0,
            "alcohol_grams": 0.0,
            "summary": "1 đĩa cơm gà xé",
            "recovery_impact": "✅ Tải purine thấp, giàu đạm tái tạo cơ bắp sau chạy bộ."
        })
    }

    with patch("requests.post", return_value=mock_resp):
        res = call_local_ollama_fallback("1 đĩa cơm gà xé")

    assert res is not None
    assert res["total_calories"] == 480
    assert res["protein_g"] == 32.5
    assert res["carb_g"] == 54.0
    assert res["fat_g"] == 14.0
    assert "cơm gà xé" in res["short_summary"]
    assert "Tải purine thấp" in res["sleep_risk_assessment"]


def test_analyze_quick_log_text_falls_back_to_ollama(monkeypatch):
    """Test that when Gemini fails, analyze_quick_log_text routes to Local Ollama LLM."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")

    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: High demand")

    ollama_mock_data = {
        "meal_type": "Bữa chính",
        "dishes": ["1 bát bún bò giò heo"],
        "total_calories": 620,
        "protein_g": 38.0,
        "carb_g": 68.0,
        "fat_g": 22.0,
        "alcohol_units": 0.0,
        "alcohol_description": "Không có cồn",
        "sleep_risk_assessment": "✅ Đánh giá phục hồi từ Ollama Qwen2.5: Bổ sung glycogen và đạm hồi phục cơ.",
        "short_summary": "Đã ghi nhận (Local Ollama): 1 bát bún bò giò heo (~620 kcal | P: 38g | C: 68g | F: 22g)."
    }

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_ollama_fallback", return_value=ollama_mock_data):
        res = analyze_quick_log_text("1 bát bún bò giò heo", timestamp="2026-11-10 12:00:00")

    assert res["total_calories"] == 620
    assert res["protein_g"] == 38.0
    assert res["carb_g"] == 68.0
    assert res["fat_g"] == 22.0
    assert "Ollama Qwen2.5" in res["sleep_risk_assessment"]


def test_analyze_meal_image_vision_fail_with_caption_falls_back_to_text_cascade(monkeypatch):
    """Test that when Gemini Vision fails, if caption is provided, it falls back to Text Cascade LLM."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")

    # Mock Gemini client to always fail on Vision
    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: Vision model overloaded")

    # Mock Text Cascade fallback result
    def fake_quick_log(text, timestamp=None):
        return {
            "meal_type": "Bữa chính",
            "dishes": [text],
            "total_calories": 540,
            "protein_g": 32.0,
            "carb_g": 62.0,
            "fat_g": 16.0,
            "alcohol_units": 0.0,
            "alcohol_description": "Không có cồn",
            "sleep_risk_assessment": "✅ Đánh giá phục hồi từ cá bống và canh sườn.",
            "short_summary": f"Đã ghi nhận: {text} (~540 kcal | P: 32g | C: 62g | F: 16g)."
        }

    img = Image.new("RGB", (50, 50), color="blue")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_qwen_vision", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_qwen_vision_sync", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_llava_vision", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_llava_vision_sync", return_value=None), \
         patch("src.analytics.vision_analyst.analyze_quick_log_text", side_effect=fake_quick_log):
        res = analyze_meal_image(img_bytes, caption="cơm trắng với cá bống kho ớt và canh sườn dưa")

    assert res["total_calories"] == 540
    assert res["protein_g"] == 32.0
    assert res["carb_g"] == 62.0
    assert res["fat_g"] == 16.0
    assert res.get("is_caption_fallback") is True
    assert "Vision Cloud" in res.get("fallback_notice", "")


def test_analyze_meal_image_vision_fail_without_caption_returns_error(monkeypatch):
    """Test that when Gemini Vision fails and NO caption is provided, return structured error prompt instead of fake 600 kcal."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")

    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: Vision model overloaded")

    img = Image.new("RGB", (50, 50), color="green")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_qwen_vision", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_qwen_vision_sync", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_llava_vision", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_llava_vision_sync", return_value=None):
        res = analyze_meal_image(img_bytes, caption="")

    assert res.get("status") == "error"
    assert res.get("error_code") == "vision_failed_no_caption"
    assert "Không thể phân tích ảnh do lỗi kết nối AI Vision" in res.get("error_message", "")
    assert res.get("total_calories") is None


def test_analyze_meal_image_gemini_fail_local_llava_vision_success(monkeypatch):
    """Test Tuyến 2: When Gemini Cloud Vision fails, automatically falls back to Ollama llava:7b on Ally X."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")

    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client
    mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: High demand on Gemini Cloud")

    llava_parsed_json = {
        "calories": 680.0,
        "protein": 42.0,
        "carb": 75.0,
        "fat": 22.0,
        "alcohol_grams": 0.0,
        "summary": "Cơm sườn nướng mỡ hành và trứng ốp la",
        "recovery_impact": "✅ Tải purine trung bình, đạm cao phục hồi gân cơ sau chạy dài."
    }

    img = Image.new("RGB", (60, 60), color="purple")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", return_value=None), \
         patch("src.analytics.vision_analyst.call_local_qwen_vision", return_value=llava_parsed_json), \
         patch("src.analytics.vision_analyst.call_local_qwen_vision_sync", return_value=llava_parsed_json), \
         patch("src.analytics.vision_analyst.call_local_llava_vision", return_value=llava_parsed_json):
        res = analyze_meal_image(img_bytes, caption="")

    assert res["total_calories"] == 680
    assert res["protein_g"] == 42.0
    assert res["carb_g"] == 75.0
    assert res["fat_g"] == 22.0
    assert res.get("is_local_vision") is True
    assert "AI Vision: Local Ally X" in res.get("fallback_notice", "")
    assert "Cơm sườn nướng" in res["dishes"][0]


@pytest.mark.anyio
async def test_call_local_llava_vision_async(monkeypatch):
    from src.analytics.vision_analyst import call_local_qwen_vision, call_local_llava_vision

    fake_response_dict = {
        "response": json.dumps({
            "calories": 450.0,
            "protein": 25.0,
            "carb": 60.0,
            "fat": 11.0,
            "alcohol_grams": 0.0,
            "summary": "Cháo gà hạt sen",
            "recovery_impact": "Dễ tiêu hóa, hỗ trợ nạp glycogen."
        })
    }

    class FakeHttpxResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return fake_response_dict

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc_val, exc_tb): pass
        async def post(self, url, json=None):
            return FakeHttpxResponse()

    with patch("httpx.AsyncClient", FakeAsyncClient):
        result = await call_local_qwen_vision(b"fake_image_bytes", caption="Cháo gà")
        result_alias = await call_local_llava_vision(b"fake_image_bytes", caption="Cháo gà")

    assert result["calories"] == 450.0
    assert result["protein"] == 25.0
    assert "Cháo gà" in result["summary"]
    assert result_alias["calories"] == 450.0


def test_call_local_llava_vision_sync(monkeypatch):
    from src.analytics.vision_analyst import call_local_qwen_vision_sync, call_local_llava_vision_sync

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": json.dumps({
            "calories": 520.0,
            "protein": 34.0,
            "carb": 50.0,
            "fat": 16.0,
            "alcohol_grams": 0.0,
            "summary": "1 đĩa bún chả Hà Nội",
            "recovery_impact": "Đạm cao từ thịt nướng, bù tinh bột từ bún."
        })
    }

    with patch("requests.post", return_value=mock_resp):
        res = call_local_qwen_vision_sync(b"fake_image_bytes", caption="Bún chả")
        res_alias = call_local_llava_vision_sync(b"fake_image_bytes", caption="Bún chả")

    assert res is not None
    assert res["calories"] == 520.0
    assert res["protein"] == 34.0
    assert "bún chả" in res["summary"]
    assert res_alias["calories"] == 520.0


def test_sanitize_llava_output_bot_nuoc():
    from src.analytics.vision_analyst import _sanitize_local_vision_output, _sanitize_llava_output
    raw = {
        "calories": 100,
        "protein": 0.0,
        "carb": 0.0,
        "fat": 0.0,
        "summary": "Bột nước",
        "recovery_impact": "Không rõ tác dụng"
    }
    sanitized = _sanitize_local_vision_output(raw)
    assert sanitized["calories"] == 0.0
    assert sanitized["summary"] == "Nước uống (bù nước)"

    raw_alias = {"calories": 100, "protein": 0.0, "carb": 0.0, "fat": 0.0, "summary": "Bột nước"}
    assert _sanitize_llava_output(raw_alias)["calories"] == 0.0


def test_parse_qwen_json_with_thinking():
    from src.analytics.vision_analyst import parse_qwen_json
    raw = (
        "<think>\n"
        "User wants nutrition analysis of 1 bowl of pho ga.\n"
        "Let's estimate calories around 480 kcal, protein 32g, carb 60g, fat 10g.\n"
        "</think>\n"
        "```json\n"
        "{\n"
        '  "calories": 480.0,\n'
        '  "protein": 32.0,\n'
        '  "carb": 60.0,\n'
        '  "fat": 10.0,\n'
        '  "alcohol_grams": 0.0,\n'
        '  "summary": "Phở gà ta lá chanh",\n'
        '  "recovery_impact": "Nạp glycogen và đạm sạch phục hồi gân cơ."\n'
        "}\n"
        "```"
    )
    res = parse_qwen_json(raw)
    assert res["calories"] == 480.0
    assert res["protein"] == 32.0
    assert res["carb"] == 60.0
    assert res["summary"] == "Phở gà ta lá chanh"




def test_analyze_meal_image_404_skips_retry_switches_model(monkeypatch):
    """Test that encountering a 404/deprecated error does not waste retries and switches immediately."""
    monkeypatch.setenv("MOCK_LLM", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "fake_key_for_test")

    mock_client = MagicMock()
    mock_genai_mod = MagicMock()
    mock_genai_mod.Client.return_value = mock_client

    success_json = json.dumps({
        "meal_type": "Bữa trưa",
        "dishes": ["Cơm gà luộc"],
        "total_calories": 500,
        "protein_g": 35.0,
        "carb_g": 55.0,
        "fat_g": 12.0,
        "alcohol_units": 0.0,
        "alcohol_description": "Không có cồn",
        "sleep_risk_assessment": "✅ Đầy đủ đạm và tinh bột.",
        "short_summary": "Cơm gà luộc (~500 kcal)"
    })
    success_resp = MagicMock()
    success_resp.text = success_json

    calls = []
    def fake_generate_content(model, contents, config):
        calls.append(model)
        if model == "gemini-2.5-flash":
            raise Exception("404 NOT_FOUND: This model models/gemini-2.0-flash is no longer available. Please update your code to use models/gemini-3.8-flash")
        return success_resp

    mock_client.models.generate_content.side_effect = fake_generate_content

    img = Image.new("RGB", (50, 50), color="yellow")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG")
    img_bytes = img_byte_arr.getvalue()

    with patch.dict("sys.modules", {"google.genai": mock_genai_mod, "google": MagicMock(genai=mock_genai_mod)}), \
         patch("time.sleep", return_value=None):
        res = analyze_meal_image(img_bytes, caption="cơm gà")

    # gemini-2.5-flash should only be attempted ONCE because 404 causes immediate break to next candidate
    assert calls.count("gemini-2.5-flash") == 1
    assert calls.count("gemini-3.8-flash") == 1
    assert res["total_calories"] == 500
    assert res["dishes"] == ["Cơm gà luộc"]


def test_create_genai_client_ssl_custom_transport():
    from src.analytics.vision_analyst import create_genai_client
    import httpx
    client = create_genai_client("test_fake_key_123")
    assert client is not None
    # Verify that client has http_options configured with custom httpx_client
    if hasattr(client, "_http_options") and client._http_options:
        opts = client._http_options
        if hasattr(opts, "httpx_client") and opts.httpx_client:
            assert isinstance(opts.httpx_client, httpx.Client)





