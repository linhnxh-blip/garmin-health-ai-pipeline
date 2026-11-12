import pytest
from unittest.mock import MagicMock, patch

from config.settings import settings
from src.delivery.telegram_bot import (
    TelegramMealBot,
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
    assert "📊 TIẾN ĐỘ HÔM NAY" in reply
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


def test_format_daily_progress():
    from src.delivery.telegram_bot import format_daily_progress
    from src.services.nutrition_service import format_daily_progress as format_daily_progress_svc

    logged = {"cal": 2200.0, "p": 120.0, "c": 193.0, "f": 95.8}
    target = {"cal": 2150.0, "p": 120.0, "c": 241.0, "f": 49.3}

    res = format_daily_progress(logged, target)
    assert "📊 TIẾN ĐỘ HÔM NAY (ĐÃ NẠP / MỤC TIÊU):" in res
    assert "Năng lượng: 2200.0/2150.0 kcal (Thừa +50.0 kcal | 102%) ⚠️" in res
    assert "Protein:    120.0/120.0g (Chuẩn đạt mục tiêu | 100%) ✅" in res
    assert "Carb:       193.0/241.0g (Còn thiếu 48.0g | 80%)" in res
    assert "Fat:        95.8/49.3g (Thừa +46.5g | 194%) ⚠️" in res

    # Check that service import matches exactly
    res_svc = format_daily_progress_svc(logged, target)
    assert res == res_svc


def test_process_photo_message_no_caption_error(monkeypatch, tmp_path):
    from src.delivery.telegram_bot import TelegramMealBot

    bot = TelegramMealBot(bot_token="fake_bot_token")
    mock_send = MagicMock()
    mock_save = MagicMock()
    monkeypatch.setattr(bot, "send_message", mock_send)
    monkeypatch.setattr("src.delivery.telegram_bot.save_nutrition_log", mock_save)

    # Mock download file bytes (img_bytes, ext)
    monkeypatch.setattr(bot, "get_file_bytes", lambda fid, destination_path=None: (b"fake_jpeg", ".jpg"))

    # Mock analyze_meal_image to return error when vision fails without caption
    monkeypatch.setattr("src.delivery.telegram_bot.analyze_meal_image", lambda **kwargs: {
        "status": "error",
        "error_code": "vision_failed_no_caption",
        "error_message": "Không thể phân tích ảnh do lỗi kết nối AI Vision. Vui lòng gõ tên món ăn hoặc gửi kèm chú thích."
    })

    msg = {
        "message_id": 13,
        "chat": {"id": 12345},
        "photo": [{"file_id": "file_123"}]
    }
    res = bot.process_photo_message(msg)

    assert res["status"] == "error"
    assert res["reason"] == "vision_failed_no_caption"
    # Verify save_nutrition_log was NOT called (no fake 600 kcal saved)
    assert not mock_save.called
    # Verify error message sent to user
    assert mock_send.called
    args = mock_send.call_args[0]
    assert "Không thể phân tích ảnh do lỗi kết nối AI Vision" in args[1]


def test_process_photo_message_with_caption_fallback(monkeypatch):
    from src.delivery.telegram_bot import TelegramMealBot

    bot = TelegramMealBot(bot_token="fake_bot_token")
    mock_send = MagicMock()
    mock_save = MagicMock(return_value=1001)
    monkeypatch.setattr(bot, "send_message", mock_send)
    monkeypatch.setattr("src.delivery.telegram_bot.save_nutrition_log", mock_save)

    monkeypatch.setattr(bot, "get_file_bytes", lambda fid, destination_path=None: (b"fake_jpeg", ".jpg"))

    # Mock analyze_meal_image to return text-cascade fallback when caption provided
    monkeypatch.setattr("src.delivery.telegram_bot.analyze_meal_image", lambda **kwargs: {
        "date": "2026-11-10",
        "timestamp": "2026-11-10 12:00:00",
        "meal_type": "Bữa chính",
        "dishes": ["Cơm sườn bì chả"],
        "total_calories": 720,
        "protein_g": 38.0,
        "carb_g": 75.0,
        "fat_g": 24.0,
        "alcohol_units": 0.0,
        "short_summary": "Đã ghi nhận: Cơm sườn bì chả (~720 kcal | P: 38g | C: 75g | F: 24g).",
        "fallback_notice": "⚠️ [Vision Cloud lỗi - Đã phân tích tự động từ chú thích bằng Local AI / Text LLM]",
        "is_caption_fallback": True
    })

    msg = {
        "message_id": 14,
        "chat": {"id": 12345},
        "caption": "cơm sườn bì chả",
        "photo": [{"file_id": "file_456"}]
    }
    res = bot.process_photo_message(msg)

    assert res["status"] == "success"
    assert res["record_id"] == 1001
    assert mock_save.called
    saved_analysis = mock_save.call_args[0][0]
    assert saved_analysis["total_calories"] == 720
    assert saved_analysis["protein_g"] == 38.0
    assert mock_send.called
    reply_sent = mock_send.call_args[0][1]
    assert "Vision Cloud lỗi" in reply_sent
    assert "Cơm sườn bì chả" in reply_sent


def test_process_command_retry_last(monkeypatch, tmp_path):
    import sqlite3
    db_file = tmp_path / "test_retry.db"
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE nutrition_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            timestamp DATETIME,
            meal_type TEXT,
            dishes TEXT,
            total_calories INTEGER,
            protein_g REAL,
            carb_g REAL,
            fat_g REAL,
            alcohol_units REAL,
            alcohol_description TEXT,
            sleep_risk_assessment TEXT,
            short_summary TEXT,
            image_path TEXT,
            raw_ai_response TEXT,
            created_at DATETIME
        )
    """)
    # Insert a record that had default 600 kcal
    c.execute("""
        INSERT INTO nutrition_logs (
            id, date, timestamp, meal_type, dishes, total_calories,
            protein_g, carb_g, fat_g, alcohol_units, alcohol_description,
            sleep_risk_assessment, short_summary, image_path, raw_ai_response
        ) VALUES (
            201, '2026-11-10', '2026-11-10 12:00:00', 'Bữa chính',
            '["bún bò Huế"]', 600, 30.0, 50.0, 20.0, 0.0, 'Không có cồn',
            '⚠️ Tạm thời không thể kết nối AI Vision.', 'Đã ghi nhận mặc định',
            '', '503 UNAVAILABLE'
        )
    """)
    conn.commit()
    conn.close()

    from contextlib import contextmanager
    @contextmanager
    def fake_db_conn(db_path=None):
        cn = sqlite3.connect(db_file)
        cn.row_factory = sqlite3.Row
        try:
            yield cn
        finally:
            cn.close()

    monkeypatch.setattr("src.db.connection.get_db_connection", fake_db_conn)

    # Mock analyze_quick_log_text
    monkeypatch.setattr("src.analytics.vision_analyst.analyze_quick_log_text", lambda text, **kw: {
        "date": "2026-11-10",
        "timestamp": "2026-11-10 12:00:00",
        "meal_type": "Bữa chính",
        "dishes": ["bún bò Huế"],
        "total_calories": 650,
        "protein_g": 38.0,
        "carb_g": 70.0,
        "fat_g": 22.0,
        "alcohol_units": 0.0,
        "alcohol_description": "Không có cồn",
        "sleep_risk_assessment": "✅ Đầy đủ đạm và tinh bột phục hồi cơ bắp.",
        "short_summary": "Đã ghi nhận: bún bò Huế (~650 kcal | P: 38g | C: 70g | F: 22g)."
    })

    bot = TelegramMealBot(bot_token="fake_token")
    mock_send = MagicMock()
    monkeypatch.setattr(bot, "send_message", mock_send)

    msg = {
        "message_id": 50,
        "chat": {"id": 123456},
        "text": "/retry_last"
    }
    res = bot.process_command_message(msg)

    assert res["status"] == "success"
    assert res["command"] == "/retry_last"
    assert res["record_id"] == 201

    # Verify updated record in DB
    verify_conn = sqlite3.connect(db_file)
    verify_conn.row_factory = sqlite3.Row
    vc = verify_conn.cursor()
    vc.execute("SELECT * FROM nutrition_logs WHERE id = 201")
    updated_rec = dict(vc.fetchone())
    verify_conn.close()

    assert updated_rec["total_calories"] == 650
    assert updated_rec["protein_g"] == 38.0
    assert updated_rec["carb_g"] == 70.0
    assert updated_rec["fat_g"] == 22.0
    assert mock_send.call_count >= 1


def test_process_chat_message(monkeypatch):
    bot = TelegramMealBot(bot_token="fake_token")
    mock_send = MagicMock()
    monkeypatch.setattr(bot, "send_message", mock_send)

    mock_advisor = MagicMock(return_value={
        "reply_text": "Hôm nay bạn nên nghỉ ngơi hoàn toàn (Rest Day) vì ACWR đang là 1.40.\n\n🤖 AI Engine: Google Gemini 2.5 Flash (Cloud) | ⏱️ 1.20s | 🪙 650 tokens",
        "model_used": "gemini (gemini-2.5-flash)",
        "latency_seconds": 1.20
    })
    monkeypatch.setattr("src.analytics.chat_advisor.ask_chat_advisor", mock_advisor)

    msg = {
        "message_id": 999,
        "chat": {"id": 1022843967},
        "text": "Hôm nay tôi có nên chạy bộ không?"
    }

    res = bot.process_chat_message(msg)

    assert res["status"] == "success"
    assert "Hôm nay bạn nên nghỉ ngơi" in res["reply"]
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    assert args[0] == 1022843967
    assert "ACWR đang là 1.40" in args[1]
    assert kwargs.get("reply_to_message_id") == 999


def test_process_command_chat_explicit(monkeypatch):
    bot = TelegramMealBot(bot_token="fake_token")
    mock_send = MagicMock()
    monkeypatch.setattr(bot, "send_message", mock_send)

    mock_chat = MagicMock(return_value={"status": "success", "reply": "Tư vấn dinh dưỡng từ AI"})
    monkeypatch.setattr(bot, "process_chat_message", mock_chat)

    msg = {
        "message_id": 888,
        "chat": {"id": 1022843967},
        "text": "/chat Bữa tối nên ăn món gì?"
    }

    res = bot.process_command_message(msg)
    assert res["status"] == "success"
    mock_chat.assert_called_once_with(msg, override_text="Bữa tối nên ăn món gì?")


def test_poll_updates_routes_to_process_chat(monkeypatch):
    bot = TelegramMealBot(bot_token="fake_token")

    mock_chat = MagicMock(return_value={"status": "success"})
    monkeypatch.setattr(bot, "process_chat_message", mock_chat)

    mock_get = MagicMock()
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "ok": True,
        "result": [
            {
                "update_id": 1,
                "message": {
                    "message_id": 101,
                    "chat": {"id": 12345},
                    "text": "Đêm qua tôi ngủ có sâu không?"
                }
            }
        ]
    }
    mock_get.return_value = mock_resp

    with patch("requests.get", mock_get):
        bot.poll_updates(once=True)

    mock_chat.assert_called_once()
    called_msg = mock_chat.call_args[0][0]
    assert called_msg["text"] == "Đêm qua tôi ngủ có sâu không?"






