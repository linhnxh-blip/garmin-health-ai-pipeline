import pytest
from unittest.mock import MagicMock, patch

from config.settings import settings
from src.delivery.telegram_bot import (
    split_message_chunks,
    send_telegram_report,
    convert_markdown_to_telegram_html,
    send_multi_section_report
)
from src.analytics.prompt_engine import split_report_into_sections

def test_split_message_chunks():
    short_text = "Hello World"
    chunks = split_message_chunks(short_text, max_chars=100)
    assert len(chunks) == 1
    assert chunks[0] == "Hello World"

    lines = [f"Line {i} is a long line for testing chunking." for i in range(100)]
    long_text = "\n".join(lines)
    chunks = split_message_chunks(long_text, max_chars=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 200

def test_send_telegram_report_success(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake_bot_token")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345678")

    mock_post = MagicMock()
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 99}}
    mock_post.return_value = mock_resp

    with patch("requests.post", mock_post):
        res = send_telegram_report("Short Report Text", chat_id="12345678", bot_token="fake_bot_token")
        assert res is True
        assert mock_post.called

def test_send_telegram_report_fallback_on_markdown_error(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake_bot_token")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345678")

    # First call (Markdown) fails with 400 Bad Request, Second call (Plain Text) succeeds
    fail_resp = MagicMock()
    fail_resp.ok = False
    fail_resp.status_code = 400
    fail_resp.json.return_value = {"ok": False, "description": "Bad Request: can't parse entities"}

    success_resp = MagicMock()
    success_resp.ok = True
    success_resp.status_code = 200
    success_resp.json.return_value = {"ok": True}

    mock_post = MagicMock(side_effect=[fail_resp, success_resp])

    with patch("requests.post", mock_post):
        res = send_telegram_report("Report with bad _markdown_ syntax *", chat_id="12345678", bot_token="fake_bot_token")
        assert res is True
        assert mock_post.call_count == 2

def test_convert_markdown_to_telegram_html():
    raw_md = "# Title Header\n**Bold Text** and *Italic Text* with `code block` & <tag>"
    html_out = convert_markdown_to_telegram_html(raw_md)
    
    assert "<b>Title Header</b>" in html_out
    assert "<b>Bold Text</b>" in html_out
    assert "<i>Italic Text</i>" in html_out
    assert "<code>code block</code>" in html_out
    assert "&amp;" in html_out
    assert "&lt;tag&gt;" in html_out

def test_split_report_into_sections():
    sample_report = (
        "# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện (2026-09-19)\n\n"
        "===SECTION_BREAK===\n"
        "### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:\n"
        "Chỉ số HRV tốt.\n\n"
        "===SECTION_BREAK===\n"
        "### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:\n"
        "Deep Sleep đạt 20%.\n\n"
        "===SECTION_BREAK===\n"
        "### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:\n"
        "MAF Zone 2 45 phút.\n\n"
        "===SECTION_BREAK===\n"
        "### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa:\n"
        "Protein 130g."
    )

    sections = split_report_into_sections(sample_report)
    assert len(sections) == 4
    assert "# 🩺 Báo cáo Phân tích Sinh lý học" in sections[0]
    assert "🧠 1. Trạng thái Thần kinh" in sections[0]
    assert "💤 2. Bóc tách Cấu trúc" in sections[1]
    assert "🏃‍♂️ 3. Kê đơn Vận động" in sections[2]
    assert "🍱 4. Kế hoạch Dinh dưỡng" in sections[3]

def test_send_multi_section_report_success(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "fake_bot_token")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345678")

    sections = [
        "Card 1: <b>Header 1</b>",
        "Card 2: <b>Header 2</b>",
        "Card 3: <b>Header 3</b>",
        "Card 4: <b>Header 4</b>"
    ]

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"ok": True, "result": {"message_id": 100}}

    mock_post = MagicMock(return_value=mock_resp)

    with patch("requests.post", mock_post), patch("time.sleep", return_value=None):
        res = send_multi_section_report(sections, chat_id="12345678", bot_token="fake_bot_token")
        assert res is True
        assert mock_post.call_count == 4
        # Verify parse_mode was HTML
        for call_arg in mock_post.call_args_list:
            json_payload = call_arg.kwargs.get("json") or call_arg[1].get("json")
            assert json_payload["parse_mode"] == "HTML"

def test_process_command_message(monkeypatch):
    from src.delivery.telegram_bot import TelegramMealBot

    bot = TelegramMealBot(bot_token="fake_bot_token")
    mock_send = MagicMock()
    mock_async_report = MagicMock()
    mock_async_sync = MagicMock()
    monkeypatch.setattr(bot, "send_message", mock_send)
    monkeypatch.setattr(bot, "_run_report_async", mock_async_report)
    monkeypatch.setattr(bot, "_run_sync_async", mock_async_sync)

    # Test /start command
    msg_start = {"message_id": 1, "chat": {"id": 1022843967}, "text": "/start"}
    res_start = bot.process_command_message(msg_start)
    assert res_start["status"] == "success"
    assert res_start["command"] == "/start"
    assert mock_send.called

    mock_send.reset_mock()

    # Test /report command
    msg_report = {"message_id": 2, "chat": {"id": 1022843967}, "text": "/report"}
    res_report = bot.process_command_message(msg_report)
    assert res_report["status"] == "success"
    assert res_report["command"] == "/report"
    assert mock_send.called
    assert mock_async_report.called

    mock_send.reset_mock()

    # Test /sync command
    msg_sync = {"message_id": 3, "chat": {"id": 1022843967}, "text": "/sync"}
    res_sync = bot.process_command_message(msg_sync)
    assert res_sync["status"] == "success"
    assert res_sync["command"] == "/sync"
    assert mock_send.called
    assert mock_async_sync.called

    mock_send.reset_mock()

    # Test /status command
    msg_status = {"message_id": 4, "chat": {"id": 1022843967}, "text": "/status"}
    res_status = bot.process_command_message(msg_status)
    assert res_status["status"] == "success"
    assert res_status["command"] == "/status"
    assert mock_send.called


def test_get_meal_header():
    from src.delivery.telegram_bot import get_meal_header

    # 1. Alcohol
    h_alc = get_meal_header({"meal_type": "Bữa tối", "dishes": ["Lẩu hải sản", "2 lon bia"], "alcohol_units": 2.0})
    assert "🍻 **BÁO CÁO ĐỒ NHẬU & NỒNG ĐỘ CỒN**" in h_alc

    # 1b. Non-alcohol plain water (must NOT be labeled alcohol even if alcohol_description has 'cồn')
    h_water = get_meal_header({
        "meal_type": "Nước uống",
        "dishes": ["1 ly nước lọc ấm"],
        "total_calories": 0,
        "alcohol_units": 0.0,
        "alcohol_description": "Không có cồn"
    })
    assert "💧 **NHẬT KÝ NƯỚC UỐNG & BÙ NƯỚC**" in h_water

    # 2. Beverage / Juice
    h_juice = get_meal_header({"meal_type": "Thức uống", "dishes": ["Nước ép cần tây dứa"]})
    assert "🥤 **NHẬT KÝ THỨC UỐNG & VI CHẤT**" in h_juice

    # 3. Snack
    h_snack = get_meal_header({"meal_type": "Bữa phụ / Snack", "dishes": ["1 hũ sữa chua Hy Lạp"]})
    assert "🥗 **NHẬT KÝ BỮA PHỤ PHỤC HỒI**" in h_snack

    # 4. Main Meal
    h_main = get_meal_header({"meal_type": "Bữa trưa", "dishes": ["Cơm sườn đậu thịt"]})
    assert "🍽️ **NHẬT KÝ BỮA ĂN & MACRO**" in h_main


def test_format_sleep_risk():
    from src.delivery.telegram_bot import format_sleep_risk

    # Healthy
    r_healthy = format_sleep_risk({"sleep_risk_assessment": "✅ Tình trạng: Bữa ăn hoàn thành lúc 11:30, thời gian tiêu hóa tối ưu."})
    assert r_healthy.startswith("✅ **Đánh giá Dinh dưỡng & Phục hồi:**")
    assert "11:30" in r_healthy

    # Warning
    r_warning = format_sleep_risk({"sleep_risk_assessment": "⚠️ Rủi ro: Ăn lẩu dầu mỡ sát giờ ngủ lúc 20:30.", "alcohol_units": 1.5})
    assert r_warning.startswith("⚠️ **Cảnh báo Rủi ro Phục hồi:**")
    assert "20:30" in r_warning


def test_build_telegram_nutrition_reply(monkeypatch):
    from src.delivery.telegram_bot import build_telegram_nutrition_reply

    analysis = {
        "date": "2026-09-25",
        "meal_type": "Thức uống",
        "dishes": ["Nước ép cần tây dứa"],
        "total_calories": 120,
        "protein_g": 2.0,
        "carb_g": 28.0,
        "fat_g": 0.5,
        "alcohol_units": 0.0,
        "sleep_risk_assessment": "✅ Tác động Phục hồi & Giấc ngủ: Enzyme Bromelain từ dứa giúp kháng viêm gân Achilles, Nitrate tự nhiên hạ áp lực tuần hoàn.",
        "short_summary": "Đã ghi nhận: 1 ly Nước ép cần tây dứa (~120 kcal | P: 2g | C: 28g | F: 0.5g)."
    }

    reply = build_telegram_nutrition_reply(analysis)
    assert "🥤 **NHẬT KÝ THỨC UỐNG & VI CHẤT**" in reply
    assert "✅ **Đánh giá Dinh dưỡng & Phục hồi:**" in reply
    assert "Enzyme Bromelain" in reply
    assert "📊 **Tiến độ hôm nay:**" in reply
    assert "cho bữa tối" not in reply
    assert "P:" in reply and "C:" in reply and "F:" in reply

def test_process_command_log_standard(monkeypatch):
    from src.delivery.telegram_bot import TelegramMealBot

    bot = TelegramMealBot(bot_token="fake_bot_token")
    mock_send = MagicMock()
    mock_save = MagicMock(return_value=999)
    monkeypatch.setattr(bot, "send_message", mock_send)
    monkeypatch.setattr("src.delivery.telegram_bot.save_nutrition_log", mock_save)

    msg = {"message_id": 10, "chat": {"id": 12345}, "text": "/log_standard"}
    res = bot.process_command_message(msg)

    assert res["status"] == "success"
    assert res["command"] == "/log_standard"
    assert res.get("record_id") == 999
    assert mock_send.called


def test_process_command_quick_log(monkeypatch):
    from src.delivery.telegram_bot import TelegramMealBot

    bot = TelegramMealBot(bot_token="fake_bot_token")
    mock_send = MagicMock()
    mock_save = MagicMock(return_value=998)
    monkeypatch.setattr(bot, "send_message", mock_send)
    monkeypatch.setattr("src.delivery.telegram_bot.save_nutrition_log", mock_save)

    # 1. Prompt case when no text provided
    msg_empty = {"message_id": 11, "chat": {"id": 12345}, "text": "/quick_log"}
    res_empty = bot.process_command_message(msg_empty)
    assert res_empty["status"] == "prompt"

    # 2. Success case when text provided
    msg_text = {"message_id": 12, "chat": {"id": 12345}, "text": "/quick_log 1 phở bò bắp bữa sáng"}
    res_text = bot.process_command_message(msg_text)
    assert res_text["status"] == "success"
    assert res_text.get("record_id") == 998
    assert mock_send.called


