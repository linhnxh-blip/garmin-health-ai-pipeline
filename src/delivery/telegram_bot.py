import os
import re
import html
import time
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from datetime import datetime

from config.settings import settings, BASE_DIR
from src.db.connection import init_db
from src.db.nutrition_repository import save_nutrition_log
from src.analytics.vision_analyst import analyze_meal_image
from src.analytics.prompt_engine import clean_report_text

IMAGE_STORE_DIR = BASE_DIR / "data" / "nutrition_images"

class TelegramMealBot:
    def __init__(self, bot_token: Optional[str] = None):
        self.bot_token = bot_token or settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in environment or settings!")
        
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        IMAGE_STORE_DIR.mkdir(parents=True, exist_ok=True)
        init_db()

    def get_file_bytes(self, file_id: str, destination_path: Optional[Path] = None) -> tuple[bytes, str]:
        """Fetch image bytes and file extension from Telegram Bot API with stream chunking & timeout (15, 60)."""
        res = requests.get(f"{self.base_url}/getFile", params={"file_id": file_id}, timeout=(15, 60))
        res.raise_for_status()
        data = res.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram getFile failed: {data}")
        
        file_path = data["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        
        chunks = []
        with requests.get(download_url, stream=True, timeout=(15, 60)) as img_res:
            img_res.raise_for_status()
            if destination_path:
                with open(destination_path, "wb") as f:
                    for chunk in img_res.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            chunks.append(chunk)
            else:
                for chunk in img_res.iter_content(chunk_size=8192):
                    if chunk:
                        chunks.append(chunk)

        img_bytes = b"".join(chunks)
        ext = Path(file_path).suffix or ".jpg"
        return img_bytes, ext

    def send_message(self, chat_id: Union[int, str], text: str, reply_to_message_id: Optional[int] = None) -> Dict[str, Any]:
        """Send message back to user on Telegram with timeout (15, 60), retry loop, and plain text fallback."""
        text = clean_report_text(text)
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                res = requests.post(url, json=payload, timeout=(15, 60))
                data = res.json() if res.content else {}

                # If Telegram rejected Markdown parse mode, retry immediately with Plain Text
                if not res.ok or not data.get("ok"):
                    desc = str(data.get("description") or "").lower()
                    if any(kw in desc for kw in ["can't parse", "parse", "markdown", "entity"]):
                        print(f"⚠️ Telegram Markdown parsing failed ({desc}). Retrying with Plain Text fallback...")
                        payload_plain = dict(payload)
                        payload_plain.pop("parse_mode", None)
                        res_plain = requests.post(url, json=payload_plain, timeout=(15, 60))
                        return res_plain.json() if res_plain.content else {"ok": False}

                return data
            except (requests.exceptions.RequestException, ConnectionResetError, Exception) as err:
                print(f"⚠️ Network error sending Telegram message (attempt {attempt}/{max_retries}): {err}")
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
                else:
                    return {"ok": False, "error": str(err)}
        return {"ok": False}

    def process_photo_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process an incoming photo message from Telegram, perform Vision AI analysis, save to SQLite, and reply."""
        message_id = message.get("message_id")
        chat_id = message.get("chat", {}).get("id")
        caption = message.get("caption") or ""
        msg_date_ts = message.get("date")

        if msg_date_ts:
            msg_dt = datetime.fromtimestamp(msg_date_ts)
        else:
            msg_dt = datetime.now()

        date_str = msg_dt.strftime("%Y-%m-%d")
        timestamp_str = msg_dt.strftime("%Y-%m-%d %H:%M:%S")

        photos = message.get("photo", [])
        if not photos:
            return {"status": "ignored", "reason": "no_photo"}

        # Get highest resolution photo (last in array)
        highest_res_photo = photos[-1]
        file_id = highest_res_photo["file_id"]

        print(f"📸 Received photo message ID {message_id} from chat {chat_id} (caption: '{caption}'). Downloading...")

        filename = f"{msg_dt.strftime('%Y-%m-%d_%H%M%S')}_{file_id[:8]}.jpg"
        saved_path = IMAGE_STORE_DIR / filename

        # 1. Download file bytes with stream chunking & timeout=(15, 60) directly to disk
        try:
            img_bytes, ext = self.get_file_bytes(file_id, destination_path=saved_path)
            if ext and ext != ".jpg":
                actual_path = saved_path.with_suffix(ext)
                saved_path.rename(actual_path)
                saved_path = actual_path
        except requests.exceptions.RequestException as e:
            print(f"❌ Download failed (RequestException): {e}")
            if chat_id:
                try:
                    self.send_message(
                        chat_id,
                        "⚠️ Kết nối mạng tới máy chủ Telegram bị nghẽn (Timeout khi tải ảnh). Bạn vui lòng gửi lại ảnh giúp mình nhé!",
                        reply_to_message_id=message_id
                    )
                except Exception as send_err:
                    print(f"⚠️ Failed to send error reply: {send_err}")
            return {"status": "error", "reason": f"download_failed: {e}"}
        except Exception as e:
            print(f"❌ Download failed (General Exception): {e}")
            if chat_id:
                try:
                    self.send_message(
                        chat_id,
                        "⚠️ Kết nối mạng tới máy chủ Telegram bị nghẽn (Timeout khi tải ảnh). Bạn vui lòng gửi lại ảnh giúp mình nhé!",
                        reply_to_message_id=message_id
                    )
                except Exception as send_err:
                    print(f"⚠️ Failed to send error reply: {send_err}")
            return {"status": "error", "reason": f"download_failed: {e}"}

        print(f"💾 Saved meal image to '{saved_path}'. Analyzing with Gemini Vision...")

        # 3. Analyze with Gemini Vision API with try...except handling
        try:
            analysis = analyze_meal_image(
                image_input=img_bytes,
                caption=caption,
                timestamp=timestamp_str
            )
        except Exception as err:
            print(f"❌ Gemini Vision API analysis failed: {err}")
            if chat_id:
                try:
                    self.send_message(
                        chat_id,
                        f"⚠️ Lỗi khi phân tích hình ảnh bằng AI: {err}. Vui lòng thử lại sau ít phút!",
                        reply_to_message_id=message_id
                    )
                except Exception as send_err:
                    print(f"⚠️ Failed to send error reply: {send_err}")
            return {"status": "error", "reason": f"vision_failed: {err}"}

        # Check if Vision failed and no caption was provided to fallback
        if analysis.get("status") == "error" or analysis.get("error_code") == "vision_failed_no_caption":
            err_msg = analysis.get("error_message") or "⚠️ Không thể phân tích ảnh do lỗi kết nối AI Vision. Vui lòng gõ tên món ăn hoặc gửi kèm chú thích."
            print(f"⚠️ Image analysis stopped without saving: {err_msg}")
            if chat_id:
                try:
                    self.send_message(chat_id, err_msg, reply_to_message_id=message_id)
                except Exception as send_err:
                    print(f"⚠️ Failed to send error reply: {send_err}")
            return {"status": "error", "reason": "vision_failed_no_caption", "message": err_msg}

        analysis["image_path"] = str(saved_path)

        # 4. Save to SQLite DB
        record_id = save_nutrition_log(analysis)
        print(f"✅ Nutrition log saved to SQLite (ID: {record_id}).")

        # 5. Build rich dynamic response message for Telegram user
        reply_text = build_telegram_nutrition_reply(analysis)

        if chat_id:
            try:
                self.send_message(chat_id, reply_text, reply_to_message_id=message_id)
            except Exception as err:
                print(f"⚠️ Failed to send Telegram reply: {err}")

        return {
            "status": "success",
            "record_id": record_id,
            "analysis": analysis,
            "reply_text": reply_text
        }

    def process_chat_message(self, message: Dict[str, Any], override_text: Optional[str] = None) -> Dict[str, Any]:
        """Process natural conversational text messages using AI Sports Physiologist & Coach cascade."""
        message_id = message.get("message_id")
        chat_id = message.get("chat", {}).get("id")
        text = override_text or (message.get("text") or "").strip()

        if not text:
            return {"status": "ignored", "reason": "empty_text"}

        print(f"💬 Received chat query from chat {chat_id}: '{text[:60]}...'")

        # Send typing action so the user immediately knows the AI is processing
        if chat_id:
            try:
                requests.post(
                    f"{self.base_url}/sendChatAction",
                    json={"chat_id": chat_id, "action": "typing"},
                    timeout=(5, 10)
                )
            except Exception:
                pass

        try:
            from src.analytics.chat_advisor import ask_chat_advisor
            res = ask_chat_advisor(text, chat_id=chat_id)
            reply_text = res.get("reply_text") or "Chào bạn! Mình có thể hỗ trợ gì cho bạn về sức khỏe và tập luyện hôm nay?"
        except Exception as chat_err:
            print(f"❌ Error in chat advisor execution: {chat_err}")
            reply_text = f"⚠️ Rất tiếc, đã xảy ra lỗi khi kết nối AI để trả lời: {chat_err}."

        if chat_id:
            try:
                self.send_message(chat_id, reply_text, reply_to_message_id=message_id)
            except Exception as err:
                print(f"⚠️ Failed to send Telegram chat reply: {err}")

        return {
            "status": "success",
            "query": text,
            "reply": reply_text,
            "model_used": res.get("model_used") if 'res' in locals() else None,
            "latency_seconds": res.get("latency_seconds") if 'res' in locals() else None
        }

    def _run_report_async(self, chat_id: Union[int, str]):
        """Run daily sync, baseline computation, LLM report generation, and Telegram card delivery asynchronously."""
        import threading
        from datetime import datetime
        from src.ingestion.collector import fetch_and_store_daily_data
        from src.analytics.baseline import calculate_baseline
        from src.analytics.llm_analyst import generate_health_analysis
        from src.analytics.report_manager import save_report_to_db, export_report_to_file
        from src.analytics.prompt_engine import split_report_into_sections

        def worker():
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                print(f"🔄 Async /report background execution started for date {today_str} (chat_id: {chat_id})...")
                # 1. Sync live data for today
                try:
                    fetch_and_store_daily_data(today_str)
                except Exception as e:
                    print(f"⚠️ Warning: Live sync during /report encountered error: {e}")

                # 2. Compute baseline & generate AI report
                baseline_data = calculate_baseline(today_str, days=30)
                analysis_res = generate_health_analysis(baseline_data, dry_run=False)

                # 3. Save report to DB & File
                save_report_to_db(
                    date=today_str,
                    report_markdown=analysis_res["report_markdown"],
                    raw_prompt=analysis_res["raw_prompt"],
                    model_used=analysis_res["model_used"],
                    status="SUCCESS",
                    prompt_tokens=analysis_res.get("prompt_tokens", 0),
                    completion_tokens=analysis_res.get("completion_tokens", 0)
                )
                export_report_to_file(today_str, analysis_res["report_markdown"])

                # 4. Deliver Glanceable Summary Telegram Card
                from src.analytics.prompt_engine import generate_telegram_card_fallback, format_ai_metadata_footer
                card_text = analysis_res.get("telegram_card")
                if not card_text:
                    card_text = generate_telegram_card_fallback(baseline_data)
                r_type = (baseline_data.get("report_type") or "morning").lower()
                report_link = f"{settings.base_web_url}/report/{today_str}/{r_type}"
                ai_footer = format_ai_metadata_footer(
                    model_used=analysis_res.get("model_used"),
                    latency_seconds=analysis_res.get("latency_seconds"),
                    prompt_tokens=analysis_res.get("prompt_tokens"),
                    completion_tokens=analysis_res.get("completion_tokens"),
                    for_telegram=True
                )
                telegram_msg = f"{card_text}\n\n📄 Xem phân tích chi tiết: {report_link}\n{ai_footer}"
                send_multi_section_report([telegram_msg], chat_id=chat_id, bot_token=self.bot_token)
                print(f"🎉 Async /report completed successfully for chat_id: {chat_id}")
            except Exception as exc:
                print(f"❌ Async /report execution failed: {exc}")
                try:
                    self.send_message(chat_id, f"❌ Rất tiếc, đã xảy ra lỗi khi tạo lại báo cáo: {exc}")
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _run_sync_async(self, chat_id: Union[int, str]):
        """Run sync-today in a background thread and inform user when complete."""
        import threading
        from datetime import datetime
        from src.ingestion.collector import fetch_and_store_daily_data

        def worker():
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                print(f"🔄 Async /sync started for date {today_str} (chat_id: {chat_id})...")
                fetch_and_store_daily_data(today_str)
                self.send_message(chat_id, "✅ Đã đồng bộ dữ liệu Garmin/Omron mới nhất thành công!")
            except Exception as exc:
                print(f"❌ Async /sync execution failed: {exc}")
                try:
                    self.send_message(chat_id, f"❌ Lỗi khi đồng bộ dữ liệu: {exc}")
                except Exception:
                    pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def process_command_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Process command text messages like /start, /help, /sync, /report, /baocao, /status."""
        message_id = message.get("message_id")
        chat_id = message.get("chat", {}).get("id")
        text = (message.get("text") or "").strip()
        cmd = text.split()[0].lower() if text else ""

        print(f"💬 Received command message '{text}' from chat {chat_id}")

        if cmd in ["/start", "/help"]:
            reply = (
                "👋 **GARMIN HEALTH AI BOT - MENU HƯỚNG DẪN**\n\n"
                "📌 **Danh mục lệnh điều khiển:**\n"
                "• `/report` | `/baocao`: Phân tích lại & bắn 4 thẻ báo cáo hoàn chỉnh mới nhất.\n"
                "• `/sync`: Kéo dữ liệu Garmin/Omron mới nhất vào DB (không tạo báo cáo).\n"
                "• `/status`: Trả về tóm tắt nhanh chỉ số sinh lý & dinh dưỡng hôm nay.\n"
                "• `/retry_last`: Tự động phân tích lại bữa ăn gần nhất bị lỗi hoặc calo mặc định.\n"
                "• `/log_standard`: Nạp nhanh ước lượng chuẩn Rest Day (2,150 kcal / 122g Protein).\n"
                "• `/quick_log [mô tả]`: Ghi nhanh bữa ăn qua văn bản (VD: `/quick_log 1 phở bò bắp`).\n"
                "• `/chat [câu hỏi]`: Trò chuyện trực tiếp với Trợ lý AI Sinh lý học & Phục hồi.\n"
                "• `/help`: Hiển thị menu hướng dẫn này.\n\n"
                "💬 **Trò chuyện tự nhiên**: Bạn có thể nhắn tin trực tiếp bất kỳ câu hỏi nào (không cần gõ lệnh), AI sẽ tự động phân tích dựa trên dữ liệu Garmin hôm nay để trả lời bạn ngay!\n\n"
                "📸 **Gửi ảnh bữa ăn**: Chụp ảnh bữa ăn kèm chú thích để tự động bóc tách Macros & Calo vào DB."
            )
            if chat_id:
                self.send_message(chat_id, reply, reply_to_message_id=message_id)
            return {"status": "success", "command": cmd, "reply": reply}

        if cmd in ["/chat", "/hoi", "/ask"]:
            parts_txt = text.split(maxsplit=1)
            query = parts_txt[1].strip() if len(parts_txt) > 1 else ""
            if not query:
                msg_prompt = "💬 Bạn muốn hỏi gì về sức khỏe, bài tập, giấc ngủ hoặc dinh dưỡng hôm nay? Hãy gõ câu hỏi của bạn nhé!"
                if chat_id:
                    self.send_message(chat_id, msg_prompt, reply_to_message_id=message_id)
                return {"status": "prompt", "command": cmd, "reply": msg_prompt}
            return self.process_chat_message(message, override_text=query)

        if cmd in ["/log_standard", "/logstandard"]:
            now_dt = datetime.now()
            date_str = now_dt.strftime("%Y-%m-%d")
            ts_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

            from src.analytics.prompt_engine import get_effective_weight_kg
            from src.services.nutrition_calculator import calculate_daily_macro_targets
            eff_w = get_effective_weight_kg({"weight_kg": 65.6})
            macro_res = calculate_daily_macro_targets(weight_kg=eff_w, day_type="rest", uric_acid_umol_l=442.0)
            target_cal = macro_res["target_calories"]
            target_p = macro_res["protein_g"]
            target_c = macro_res["carb_g"]
            target_f = macro_res["fat_g"]

            analysis = {
                "date": date_str,
                "timestamp": ts_str,
                "meal_type": "daily_estimate",
                "dishes": [f"Bữa ăn tiêu chuẩn Rest Day (~{target_cal} kcal, {target_p}g Protein)"],
                "total_calories": target_cal,
                "protein_g": target_p,
                "carb_g": target_c,
                "fat_g": target_f,
                "alcohol_units": 0.0,
                "alcohol_description": "Không có cồn",
                "sleep_risk_assessment": "✅ Tác động Phục hồi & Giấc ngủ: Khẩu phần tiêu chuẩn hoàn tất trước 19:00, tối ưu cho phục hồi.",
                "short_summary": f"Đã nạp ước lượng chuẩn Rest Day (~{target_cal} kcal, {target_p}g Protein)."
            }
            record_id = save_nutrition_log(analysis)
            reply_text = build_telegram_nutrition_reply(analysis)
            if chat_id:
                self.send_message(chat_id, reply_text, reply_to_message_id=message_id)
            return {"status": "success", "command": cmd, "record_id": record_id, "reply": reply_text}

        if cmd in ["/quick_log", "/quicklog", "/log"]:
            parts_txt = text.split(maxsplit=1)
            log_desc = parts_txt[1].strip() if len(parts_txt) > 1 else ""

            if not log_desc:
                msg_prompt = (
                    "✍️ *HƯỚNG DẪN DÙNG LỆNH /QUICK_LOG:*\n\n"
                    "Vui lòng gõ kèm mô tả món ăn. Ví dụ:\n"
                    "`/quick_log 1 phở bò bắp bữa sáng và 1 cơm tấm sườn chả bữa trưa`\n\n"
                    "Hoặc gõ `/log_standard` để nạp ngay ước lượng chuẩn Rest Day (2,150 kcal, 122g P)."
                )
                if chat_id:
                    self.send_message(chat_id, msg_prompt, reply_to_message_id=message_id)
                return {"status": "prompt", "command": cmd, "reply": msg_prompt}

            try:
                from src.analytics.vision_analyst import analyze_quick_log_text
                analysis = analyze_quick_log_text(log_desc)
                record_id = save_nutrition_log(analysis)
                reply_text = build_telegram_nutrition_reply(analysis)

                if chat_id:
                    self.send_message(chat_id, reply_text, reply_to_message_id=message_id)
                return {"status": "success", "command": cmd, "record_id": record_id, "reply": reply_text}
            except Exception as cmd_err:
                print(f"❌ Error in /quick_log command handler: {cmd_err}")
                err_msg = f"⚠️ Lỗi xử lý /quick_log: {cmd_err}. Vui lòng thử lại hoặc gõ /log_standard."
                if chat_id:
                    self.send_message(chat_id, err_msg, reply_to_message_id=message_id)
                return {"status": "error", "command": cmd, "error": str(cmd_err)}

        if cmd in ["/sync"]:
            ack_msg = "🔄 Đang đồng bộ dữ liệu mới nhất từ Garmin/Omron..."
            if chat_id:
                self.send_message(chat_id, ack_msg, reply_to_message_id=message_id)
                self._run_sync_async(chat_id)
            return {"status": "success", "command": cmd, "async": True, "ack": ack_msg}

        if cmd in ["/status"]:
            status_text = get_today_status_summary()
            if chat_id:
                self.send_message(chat_id, status_text, reply_to_message_id=message_id)
            return {"status": "success", "command": cmd, "reply": status_text}

        if cmd in ["/report", "/baocao"]:
            ack_msg = "🔄 Đang kéo dữ liệu mới nhất từ Garmin/Omron và phân tích lại..."
            if chat_id:
                self.send_message(chat_id, ack_msg, reply_to_message_id=message_id)
                self._run_report_async(chat_id)
            return {"status": "success", "command": cmd, "async": True, "ack": ack_msg}

        if cmd in ["/retry_last", "/retry", "/reanalyze"]:
            from src.db.connection import get_db_connection
            from src.analytics.vision_analyst import analyze_meal_image, analyze_quick_log_text
            import os
            import json
            import sqlite3

            print(f"🔄 Executing /retry_last requested by chat {chat_id}...")
            # 1. Query candidate record that failed or has default values
            with get_db_connection() as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute("""
                    SELECT * FROM nutrition_logs 
                    WHERE (
                        (total_calories = 600 AND protein_g = 30.0 AND carb_g = 50.0 AND fat_g = 20.0)
                        OR sleep_risk_assessment LIKE '%Tạm thời không thể kết nối%'
                        OR sleep_risk_assessment LIKE '%Không thể phân tích ảnh%'
                        OR sleep_risk_assessment LIKE '%lỗi kết nối%'
                        OR raw_ai_response LIKE '%404%'
                        OR raw_ai_response LIKE '%503%'
                        OR raw_ai_response LIKE '%UNAVAILABLE%'
                        OR total_calories IS NULL
                        OR total_calories = 0
                    )
                    ORDER BY id DESC LIMIT 1
                """)
                row = c.fetchone()
                if not row:
                    # Fallback to the most recent record with an image
                    c.execute("SELECT * FROM nutrition_logs WHERE image_path IS NOT NULL AND image_path != '' ORDER BY id DESC LIMIT 1")
                    row = c.fetchone()
                if not row:
                    # Fallback to absolute latest meal
                    c.execute("SELECT * FROM nutrition_logs ORDER BY id DESC LIMIT 1")
                    row = c.fetchone()

            if not row:
                no_meal_msg = "ℹ️ Không tìm thấy bữa ăn nào trong hệ thống để phân tích lại."
                if chat_id:
                    self.send_message(chat_id, no_meal_msg, reply_to_message_id=message_id)
                return {"status": "error", "command": cmd, "reason": "no_record_found"}

            rec = dict(row)
            rec_id = rec.get("id")
            raw_dishes = rec.get("dishes")
            caption_text = ""
            if raw_dishes:
                try:
                    parsed_d = json.loads(raw_dishes)
                    caption_text = ", ".join(parsed_d) if isinstance(parsed_d, list) else str(parsed_d)
                except Exception:
                    caption_text = str(raw_dishes).strip("[]'\"")

            img_path = rec.get("image_path")
            ts = rec.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            ack_text = f"🔄 Đang phân tích lại bữa ăn gần nhất (ID: {rec_id} - '{caption_text or 'Ảnh bữa ăn'}')..."
            if chat_id:
                self.send_message(chat_id, ack_text, reply_to_message_id=message_id)

            new_analysis = None
            if img_path and os.path.exists(img_path):
                try:
                    with open(img_path, "rb") as f:
                        img_bytes = f.read()
                    new_analysis = analyze_meal_image(img_bytes, caption=caption_text, timestamp=ts)
                except Exception as img_err:
                    print(f"⚠️ Reanalyzing image failed: {img_err}")

            if not new_analysis or new_analysis.get("status") == "error":
                if caption_text:
                    try:
                        new_analysis = analyze_quick_log_text(caption_text, timestamp=ts)
                    except Exception as txt_err:
                        print(f"⚠️ Quick log text fallback failed: {txt_err}")

            if not new_analysis or new_analysis.get("status") == "error":
                fail_msg = f"❌ Không thể phân tích lại bữa ăn ID {rec_id} do lỗi kết nối AI. Vui lòng thử lại sau ít phút!"
                if chat_id:
                    self.send_message(chat_id, fail_msg, reply_to_message_id=message_id)
                return {"status": "error", "command": cmd, "record_id": rec_id}

            # Update DB
            cal = new_analysis.get("total_calories")
            p = new_analysis.get("protein_g")
            c_val = new_analysis.get("carb_g")
            f_val = new_analysis.get("fat_g")
            alc_u = new_analysis.get("alcohol_units", 0.0)
            alc_desc = new_analysis.get("alcohol_description", "Không có cồn")
            risk = new_analysis.get("sleep_risk_assessment", "")
            summary = new_analysis.get("short_summary", "")
            raw_ai = new_analysis.get("raw_ai_response", "")
            dishes_json = json.dumps(new_analysis.get("dishes", [caption_text]), ensure_ascii=False)

            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("""
                    UPDATE nutrition_logs
                    SET total_calories = ?,
                        protein_g = ?,
                        carb_g = ?,
                        fat_g = ?,
                        alcohol_units = ?,
                        alcohol_description = ?,
                        sleep_risk_assessment = ?,
                        short_summary = ?,
                        raw_ai_response = ?,
                        dishes = ?
                    WHERE id = ?
                """, (cal, p, c_val, f_val, alc_u, alc_desc, risk, summary, raw_ai, dishes_json, rec_id))
                conn.commit()

            reply_text = build_telegram_nutrition_reply(new_analysis)
            full_reply = f"🔄 **KẾT QUẢ PHÂN TÍCH LẠI BỮA ĂN (ID: {rec_id}):**\n\n{reply_text}"
            if chat_id:
                self.send_message(chat_id, full_reply, reply_to_message_id=message_id)
            return {"status": "success", "command": cmd, "record_id": rec_id, "reply": full_reply}

        return {"status": "ignored", "reason": "unknown_command"}

    def poll_updates(self, once: bool = False, poll_interval: float = 2.0):
        """Long-polling listener loop to receive messages from Telegram with connection reset resilience."""
        print(f"🤖 Starting Telegram Meal Bot Listener (Token: {self.bot_token[:6]}...)...")
        offset = 0

        while True:
            try:
                params = {"offset": offset, "timeout": 20}
                res = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=(15, 60))
                res.raise_for_status()
                data = res.json()

                if data.get("ok"):
                    updates = data.get("result", [])
                    for update in updates:
                        offset = update["update_id"] + 1
                        msg = update.get("message")
                        if msg:
                            text = (msg.get("text") or "").strip()
                            if text.startswith("/"):
                                self.process_command_message(msg)
                            elif "photo" in msg:
                                self.process_photo_message(msg)
                            elif text:
                                self.process_chat_message(msg)

                if once:
                    print("🏁 Finished single update poll (--once). Exiting listener.")
                    break

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, ConnectionResetError) as conn_err:
                print(f"🔄 Connection drop during Telegram long-polling ({conn_err}). Reconnecting in {poll_interval}s...")
                if once:
                    break
                time.sleep(poll_interval)
            except Exception as exc:
                print(f"⚠️ Telegram Bot polling error: {exc}")
                if once:
                    break
                time.sleep(poll_interval)

            time.sleep(0.5)

def get_today_status_summary() -> str:
    """Fetch quick status summary of today's health metrics and nutrition logs from SQLite."""
    from datetime import datetime
    from src.db.connection import get_db_connection
    from src.db.nutrition_repository import get_nutrition_logs_by_date, get_today_nutrition_summary
    from src.analytics.prompt_engine import get_effective_weight_kg, _format_seconds

    today_str = datetime.now().strftime("%Y-%m-%d")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT sleep_score, deep_sleep_seconds, hrv_last_night, resting_heart_rate, weight_kg, total_steps, active_calories FROM daily_metrics WHERE date = ?", (today_str,))
        row = cursor.fetchone()

    summary = get_today_nutrition_summary(today_str)
    tot_cal = summary["total_cal"]
    tot_p = summary["total_protein"]
    tot_c = summary["total_carbs"]
    tot_f = summary["total_fat"]

    nut_logs = get_nutrition_logs_by_date(today_str)
    meal_count = len(nut_logs)

    if row:
        sleep_score, deep_sec, hrv, rhr, weight, steps, active_cal = row
        sleep_str = f"{sleep_score}/100 (Deep: {_format_seconds(deep_sec)})" if sleep_score is not None else "⚠️ Chưa chốt giấc ngủ"
        hrv_str = f"{hrv} ms" if hrv is not None else "N/A"
        rhr_str = f"{rhr} bpm" if rhr is not None else "N/A"
        steps_str = f"{steps:,}" if steps is not None else "0"
    else:
        sleep_str = "⚠️ Chưa có dữ liệu hôm nay"
        hrv_str = "N/A"
        rhr_str = "N/A"
        steps_str = "0"

    w_eff = get_effective_weight_kg({"weight_kg": row[4] if row else None})

    lines = [
        f"📊 **TRẠNG THÁI HÔM NAY ({today_str})**",
        "",
        f"💤 **Giấc ngủ**: {sleep_str}",
        f"❤️ **HRV Overnight**: {hrv_str} | **RHR**: {rhr_str}",
        f"⚖️ **Cân nặng OMRON**: {w_eff} kg",
        f"👟 **Bước chân**: {steps_str} bước",
        "",
        f"🍱 **Dinh dưỡng đã log**: {meal_count} bữa ăn",
        f"• Năng lượng: ~{tot_cal} kcal",
        f"• Macros: Protein {tot_p}g | Carb {tot_c}g | Fat {tot_f}g",
        "",
        "💡 *Gửi lệnh `/report` để cập nhật báo cáo 4 thẻ hoàn chỉnh.*"
    ]
    return "\n".join(lines)

def process_single_image_file(image_path: str, caption: Optional[str] = None) -> Dict[str, Any]:
    """Helper function to analyze a local image file directly without Telegram API."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found at '{image_path}'")

    img_bytes = path.read_bytes()
    analysis = analyze_meal_image(img_bytes, caption=caption)
    if analysis.get("status") == "error":
        return analysis

    analysis["image_path"] = str(path.resolve())
    
    init_db()
    record_id = save_nutrition_log(analysis)
    analysis["record_id"] = record_id
    return analysis

def split_message_chunks(text: str, max_chars: int = 4000) -> list[str]:
    """Split a long text string into chunks <= max_chars, preferably at line breaks."""
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    lines = text.split("\n")
    current_chunk = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1
        if current_len + line_len > max_chars:
            if current_chunk:
                chunks.append("\n".join(current_chunk).strip())
                current_chunk = []
                current_len = 0
            while len(line) > max_chars:
                chunks.append(line[:max_chars])
                line = line[max_chars:]
                line_len = len(line) + 1
        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk).strip())

    return [c for c in chunks if c]

def send_telegram_report(
    report_text: str,
    chat_id: Optional[Union[str, int]] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send health analysis report to Telegram user.
    Handles message chunking (>4000 chars) and automatic Markdown to Plain Text fallback mechanism.
    """
    raw_token = str(bot_token or settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "")
    raw_chat = str(chat_id or settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID") or "")

    token = raw_token.strip().strip('"').strip("'")
    target_chat_str = raw_chat.strip().strip('"').strip("'")

    if not token or not target_chat_str:
        print("⚠️ Cannot send Telegram report: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env / settings.")
        return False

    # Convert numeric chat_id to int for Telegram API compatibility
    if target_chat_str.lstrip("-").isdigit():
        target_chat_id: Union[int, str] = int(target_chat_str)
    else:
        target_chat_id = target_chat_str

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = split_message_chunks(report_text, max_chars=4000)
    total_chunks = len(chunks)

    print(f"📤 Preparing to send report to Telegram chat '{target_chat_id}' ({total_chunks} part(s))...")

    all_success = True

    for idx, chunk in enumerate(chunks, 1):
        payload = {
            "chat_id": target_chat_id,
            "text": chunk,
            "parse_mode": "Markdown"
        }

        try:
            res = requests.post(url, json=payload, timeout=(15, 60))
            res_json = res.json() if res.status_code == 200 or res.content else {}

            if not res.ok or not res_json.get("ok"):
                err_desc = res_json.get("description") or f"HTTP {res.status_code}"
                if "chat not found" in err_desc.lower():
                    print(f"⚠️ Telegram notice for part {idx}/{total_chunks}: {err_desc}.")
                    print(f"💡 Hướng dẫn: Vui lòng mở Telegram, tìm kiếm Bot và ấn nút /start (hoặc gửi 1 tin nhắn bất kỳ cho Bot) để kích hoạt quyền gửi tin nhắn.")
                else:
                    print(f"⚠️ Telegram Markdown send failed for part {idx}/{total_chunks}: {err_desc}. Falling back to plain text...")

                # Fallback to plain text sending
                payload_fallback = {
                    "chat_id": target_chat_id,
                    "text": chunk
                }
                fallback_res = requests.post(url, json=payload_fallback, timeout=(15, 60))
                fb_json = fallback_res.json() if fallback_res.status_code == 200 or fallback_res.content else {}

                if fallback_res.ok and fb_json.get("ok"):
                    print(f"✅ Sent part {idx}/{total_chunks} via Plain Text fallback successfully.")
                else:
                    if "chat not found" in str(fb_json).lower():
                        print(f"❌ Không thể gửi tin nhắn tới Chat ID '{target_chat_id}'. Hãy đảm bảo bạn đã bấm /start với Bot trên Telegram.")
                    else:
                        print(f"❌ Failed to send part {idx}/{total_chunks} even with plain text: {fb_json}")
                    all_success = False
            else:
                print(f"✅ Sent part {idx}/{total_chunks} via Markdown successfully.")

        except Exception as exc:
            print(f"❌ Network/API exception sending part {idx}/{total_chunks}: {exc}")
            all_success = False

    return all_success

def send_executive_brief_with_telegraph(
    quick_brief: str,
    telegraph_url: str,
    chat_id: Optional[Union[str, int]] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send Executive Brief to Telegram user with Inline Keyboard button pointing to Telegraph page."""
    raw_token = str(bot_token or settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "")
    raw_chat = str(chat_id or settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID") or "")

    token = raw_token.strip().strip('"').strip("'")
    target_chat_str = raw_chat.strip().strip('"').strip("'")

    if not token or not target_chat_str:
        print("⚠️ Cannot send Telegram Executive Brief: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
        return False

    if target_chat_str.lstrip("-").isdigit():
        target_chat_id: Union[int, str] = int(target_chat_str)
    else:
        target_chat_id = target_chat_str

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "📖 Xem Phân Tích Đầy Đủ (Telegraph)",
                    "url": telegraph_url
                }
            ]
        ]
    }

    payload = {
        "chat_id": target_chat_id,
        "text": quick_brief,
        "reply_markup": reply_markup
    }

    try:
        res = requests.post(url, json=payload, timeout=(15, 60))
        res_json = res.json() if res.status_code == 200 or res.content else {}
        if res.ok and res_json.get("ok"):
            print(f"✅ Executive Brief & Telegraph button sent to Telegram chat '{target_chat_id}' successfully!")
            return True
        else:
            err_desc = res_json.get("description") or f"HTTP {res.status_code}"
            print(f"⚠️ Telegram Inline Button send failed ({err_desc}).")
            if "chat not found" in err_desc.lower():
                print(f"💡 Hướng dẫn: Vui lòng mở Telegram, tìm kiếm Bot và ấn nút /start để kích hoạt quyền gửi tin nhắn.")
            return False
    except Exception as exc:
        print(f"❌ Exception sending Telegram Executive Brief: {exc}")
        return False

def convert_markdown_to_telegram_html(text: str) -> str:
    """Convert standard Markdown formatting to Telegram HTML tags (<b>, <i>, <code>)."""
    if not text:
        return ""

    # 1. Escape HTML special characters <, >, &
    escaped = html.escape(text)

    # 2. Convert headers # Title / ### Header to bold
    escaped = re.sub(r"^#+\s*(.*)$", r"<b>\1</b>", escaped, flags=re.MULTILINE)

    # 3. Convert **bold** to <b>bold</b>
    escaped = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)

    # 4. Convert *italic* or _italic_ to <i>italic</i>
    escaped = re.sub(r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)", r"<i>\1</i>", escaped)

    # 5. Convert `code` to <code>code</code>
    escaped = re.sub(r"`(.*?)`", r"<code>\1</code>", escaped)

    return escaped

def send_multi_section_report(
    sections: Union[List[str], str],
    chat_id: Optional[Union[str, int]] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send a report split into sequential HTML Message Cards to Telegram with 0.5s delay between messages.
    Automatically handles ===SECTION_BREAK=== splitting, sub-chunking cards > 4000 chars, and Plain Text fallback.
    """
    raw_token = str(bot_token or settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "")
    raw_chat = str(chat_id or settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID") or "")

    token = raw_token.strip().strip('"').strip("'")
    target_chat_str = raw_chat.strip().strip('"').strip("'")

    if not token or not target_chat_str:
        print("⚠️ Cannot send multi-section report: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
        return False

    if target_chat_str.lstrip("-").isdigit():
        target_chat_id: Union[int, str] = int(target_chat_str)
    else:
        target_chat_id = target_chat_str

    # If a single report string was passed, split by ===SECTION_BREAK=== or section headers
    if isinstance(sections, str):
        from src.analytics.prompt_engine import split_report_into_sections
        card_sections = split_report_into_sections(sections)
    else:
        card_sections = sections

    # Ensure no single card exceeds 3900 characters (Telegram max is 4096)
    final_cards = []
    for sec in card_sections:
        if len(sec) > 3900:
            chunks = split_message_chunks(sec, max_chars=3900)
            final_cards.extend(chunks)
        else:
            final_cards.append(sec)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    total = len(final_cards)

    print(f"📲 Preparing to send {total} Message Cards sequentially to Telegram chat '{target_chat_id}'...")

    all_success = True

    for idx, sec in enumerate(final_cards, 1):
        html_text = convert_markdown_to_telegram_html(sec)

        payload = {
            "chat_id": target_chat_id,
            "text": html_text,
            "parse_mode": "HTML"
        }

        try:
            res = requests.post(url, json=payload, timeout=(15, 60))
            res_json = res.json() if res.status_code == 200 or res.content else {}

            if not res.ok or not res_json.get("ok"):
                err_desc = res_json.get("description") or f"HTTP {res.status_code}"
                if "chat not found" in err_desc.lower():
                    print(f"⚠️ Telegram notice for Card {idx}/{total}: {err_desc}.")
                    print("💡 Hướng dẫn: Vui lòng mở Telegram, tìm kiếm Bot và ấn nút /start để kích hoạt quyền gửi tin nhắn.")
                else:
                    print(f"⚠️ Telegram HTML send failed for Card {idx}/{total}: {err_desc}. Falling back to plain text...")

                # Fallback to plain text
                payload_fallback = {
                    "chat_id": target_chat_id,
                    "text": sec
                }
                fallback_res = requests.post(url, json=payload_fallback, timeout=(15, 60))
                fb_json = fallback_res.json() if fallback_res.status_code == 200 or fallback_res.content else {}

                if fallback_res.ok and fb_json.get("ok"):
                    print(f"✅ Card {idx}/{total} sent via Plain Text fallback successfully.")
                else:
                    if "chat not found" in str(fb_json).lower():
                        print(f"❌ Không thể gửi tin nhắn tới Chat ID '{target_chat_id}'. Đảm bảo đã ấn /start với Bot.")
                    else:
                        print(f"❌ Failed to send Card {idx}/{total} even with plain text: {fb_json}")
                    all_success = False
            else:
                print(f"✅ Card {idx}/{total} sent via HTML successfully!")

        except Exception as exc:
            print(f"❌ Exception sending Card {idx}/{total}: {exc}")
            all_success = False

        if idx < total:
            time.sleep(0.5)

    return all_success

def send_telegram_report(
    report_text: str,
    chat_id: Optional[Union[str, int]] = None,
    bot_token: Optional[str] = None
) -> bool:
    """Send health analysis report split into sequential Telegram Message Cards."""
    return send_multi_section_report(sections=report_text, chat_id=chat_id, bot_token=bot_token)


def get_meal_header(analysis: Dict[str, Any]) -> str:
    """Determine dynamic Telegram header based on intake type, dishes, and alcohol content."""
    meal_type = str(analysis.get("meal_type") or "").lower()
    dishes_list = analysis.get("dishes") or []
    if isinstance(dishes_list, list):
        item_name = " ".join(str(d) for d in dishes_list).lower()
    else:
        item_name = str(dishes_list).lower()
    summary = str(analysis.get("short_summary") or "").lower()
    combined_text = f"{meal_type} {item_name} {summary}"

    calories = int(analysis.get("total_calories") or 0)
    alcohol_units = float(analysis.get("alcohol_units") or 0.0)

    # 1. Alcohol / Drinking session (ONLY if alcohol_units > 0 or explicit alcoholic drink names)
    if alcohol_units > 0 or any(kw in item_name for kw in ["bia", "rượu", "cocktail", "soju", "whisky", "vodka"]):
        return "🍻 **BÁO CÁO ĐỒ NHẬU & NỒNG ĐỘ CỒN**"

    # 2. Plain water / Hydration (calories == 0 or plain water)
    is_plain_water = (
        ("nước" in item_name and "ép" not in item_name and "ngọt" not in item_name and calories == 0)
        or any(kw in combined_text for kw in ["nước lọc", "nước ấm", "nước lặt", "nước suối", "nước khoáng"])
    )
    if is_plain_water and calories < 30:
        return "💧 **NHẬT KÝ NƯỚC UỐNG & BÙ NƯỚC**"

    # 3. Juices, Smoothies & Functional Beverages
    is_drink = (
        "nước ép" in item_name
        or "sinh tố" in item_name
        or any(kw in combined_text for kw in ["juice", "smoothie", "nước dừa", "cà phê", "trà", "kombucha"])
        or any(kw in meal_type for kw in ["thức uống", "đồ uống", "nước ép", "sinh tố"])
    )
    if is_drink:
        return "🥤 **NHẬT KÝ THỨC UỐNG & VI CHẤT**"

    # 4. Side meal / Snack
    is_snack = (
        meal_type in ["snack", "bữa phụ", "ăn nhẹ", "tráng miệng", "bữa xế"]
        or any(kw in meal_type for kw in ["phụ", "snack", "xế", "tráng miệng", "ăn nhẹ"])
        or any(kw in combined_text for kw in ["bữa phụ", "snack", "sữa chua", "bánh", "trái cây", "ăn nhẹ", "tráng miệng", "bữa xế"])
    )
    if is_snack:
        return "🥗 **NHẬT KÝ BỮA PHỤ PHỤC HỒI**"

    # 5. Main meal (Breakfast / Lunch / Dinner)
    return "🍽️ **NHẬT KÝ BỮA ĂN & MACRO**"


def format_sleep_risk(analysis: Dict[str, Any]) -> str:
    """Format sleep risk / recovery impact section without false warnings.
    Purges oatmeal / modern western grains and debounces rapid consecutive meal logs (< 5 min).
    """
    raw_risk = (analysis.get("sleep_risk_assessment") or "").strip()
    if not raw_risk:
        return ""

    if "Gemini" in raw_risk or "AI Studio" in raw_risk or "Unauthenticated" in raw_risk or "Quota" in raw_risk:
        return raw_risk

    # 1. Purge modern western grains (oatmeal, quinoa, whole wheat bread)
    raw_risk = re.sub(r'\b(?:yến mạch|oatmeal)\b', 'khoai lang hấp', raw_risk, flags=re.IGNORECASE)
    raw_risk = re.sub(r'\bbánh mì nguyên cám\b', 'chuối tiêu chín', raw_risk, flags=re.IGNORECASE)
    raw_risk = re.sub(r'\bquinoa\b', 'cơm trắng', raw_risk, flags=re.IGNORECASE)

    # 2. Debounce rapid consecutive logs (< 5 minutes from previous meal today)
    date_str = analysis.get("date") or datetime.now().strftime("%Y-%m-%d")
    curr_ts = analysis.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        from src.db.nutrition_repository import get_nutrition_logs_by_date
        logs = get_nutrition_logs_by_date(date_str)
        prev_log = None
        if logs:
            for l in reversed(logs):
                l_ts = str(l.get("timestamp") or "")
                if l_ts != curr_ts:
                    prev_log = l
                    break
            if not prev_log and len(logs) >= 2:
                prev_log = logs[-2]

        if prev_log:
            prev_ts = str(prev_log.get("timestamp") or "")
            t_fmt = "%Y-%m-%d %H:%M:%S"
            c_dt = datetime.strptime(curr_ts, t_fmt) if len(curr_ts) >= 19 else datetime.now()
            p_dt = datetime.strptime(prev_ts, t_fmt) if len(prev_ts) >= 19 else None
            if p_dt and 0 <= (c_dt - p_dt).total_seconds() <= 300:
                # Consecutive log within 5 minutes: strip redundant macro warning paragraphs
                macro_warning_patterns = [
                    r'Tuy nhiên,?\s*(?:bữa ăn|tổng lượng Carbohydrate)[^.]*?(?:nên bổ sung|cần bổ sung)[^.]*\.?',
                    r'Tuy nhiên,?\s*bữa ăn hiện tại đang hoàn toàn thiếu Carbohydrate[^.]*\.?',
                    r'VĐV nên bổ sung thêm nguồn Carb[^.]*\.?',
                    r'bạn nên bổ sung thêm nguồn Carb[^.]*\.?'
                ]
                for pat in macro_warning_patterns:
                    raw_risk = re.sub(pat, '', raw_risk, flags=re.IGNORECASE).strip()
                if not raw_risk or raw_risk in [".", "✅", "⚠️"]:
                    prev_dish = ", ".join(prev_log.get("dishes") or []) if isinstance(prev_log.get("dishes"), list) else str(prev_log.get("dishes") or "")
                    raw_risk = f"Thức uống/món ăn bổ sung ngay trong bữa ăn ({prev_dish}), hỗ trợ bù nước và vi chất lành mạnh."
    except Exception:
        pass

    is_healthy = (
        raw_risk.startswith("✅")
        or "tối ưu" in raw_risk.lower()
        or "lành mạnh" in raw_risk.lower()
        or "hoàn toàn không" in raw_risk.lower()
        or "phù hợp" in raw_risk.lower()
        or "cân bằng" in raw_risk.lower()
    )
    is_warning = (
        raw_risk.startswith("⚠️")
        or "cảnh báo" in raw_risk.lower()
        or "rủi ro" in raw_risk.lower()
        or float(analysis.get("alcohol_units") or 0) > 0
    )

    clean_text = raw_risk
    prefixes = [
        "✅ Tình trạng:",
        "✅ Tác động Phục hồi & Giấc ngủ:",
        "✅ Đánh giá Dinh dưỡng & Phục hồi:",
        "✅ Đánh giá Dinh dưỡng:",
        "✅",
        "⚠️ Cảnh báo Rủi ro Phục hồi:",
        "⚠️ Rủi ro:",
        "⚠️"
    ]
    for prefix in prefixes:
        if clean_text.startswith(prefix):
            clean_text = clean_text[len(prefix):].strip()

    if is_healthy and not is_warning:
        return f"✅ **Đánh giá Dinh dưỡng & Phục hồi:** {clean_text}"
    else:
        return f"⚠️ **Cảnh báo Rủi ro Phục hồi:** {clean_text}"


def format_daily_progress(logged: dict, target: dict) -> str:
    # Compute deltas
    cal_logged = float(logged["cal"] if "cal" in logged else logged.get("total_cal", 0.0))
    p_logged = float(logged["p"] if "p" in logged else logged.get("total_protein", logged.get("protein_g", 0.0)))
    c_logged = float(logged["c"] if "c" in logged else logged.get("total_carbs", logged.get("carb_g", 0.0)))
    f_logged = float(logged["f"] if "f" in logged else logged.get("total_fat", logged.get("fat_g", 0.0)))

    cal_target = float(target["cal"] if "cal" in target else target.get("target_calories", target.get("total_cal", 0.0)))
    p_target = float(target["p"] if "p" in target else target.get("protein_g", target.get("total_protein", 0.0)))
    c_target = float(target["c"] if "c" in target else target.get("carb_g", target.get("total_carbs", 0.0)))
    f_target = float(target["f"] if "f" in target else target.get("fat_g", target.get("total_fat", 0.0)))

    cal_diff = round(cal_logged - cal_target, 1)
    p_diff = round(p_logged - p_target, 1)
    c_diff = round(c_logged - c_target, 1)
    f_diff = round(f_logged - f_target, 1)

    def format_stat(val_logged, val_target, diff, unit="g"):
        pct = round((val_logged / val_target) * 100, 0) if val_target > 0 else 0
        if diff > 5:
            return f"{val_logged:.1f}/{val_target:.1f}{unit} (Thừa +{diff:.1f}{unit} | {pct:.0f}%) ⚠️"
        elif diff < -5:
            return f"{val_logged:.1f}/{val_target:.1f}{unit} (Còn thiếu {abs(diff):.1f}{unit} | {pct:.0f}%)"
        else:
            return f"{val_logged:.1f}/{val_target:.1f}{unit} (Chuẩn đạt mục tiêu | 100%) ✅"

    return (
        f"📊 TIẾN ĐỘ HÔM NAY (ĐÃ NẠP / MỤC TIÊU):\n"
        f"• Năng lượng: {format_stat(cal_logged, cal_target, cal_diff, ' kcal')}\n"
        f"• Protein:    {format_stat(p_logged, p_target, p_diff)}\n"
        f"• Carb:       {format_stat(c_logged, c_target, c_diff)}\n"
        f"• Fat:        {format_stat(f_logged, f_target, f_diff)}"
    )


def calculate_live_progress(date_str: Optional[str] = None, db_path: Optional[Path] = None) -> str:
    """Calculate total calories and macros logged today and dynamic comparison vs daily target."""
    from src.db.nutrition_repository import get_remaining_nutrition_quota

    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    quota = get_remaining_nutrition_quota(user_date=target_date, db_path=db_path)

    logged = {
        "cal": quota["logged"]["total_cal"],
        "p": quota["logged"]["total_protein"],
        "c": quota["logged"]["total_carbs"],
        "f": quota["logged"]["total_fat"],
    }
    target = {
        "cal": quota["target"]["target_calories"],
        "p": quota["target"]["protein_g"],
        "c": quota["target"]["carb_g"],
        "f": quota["target"]["fat_g"],
    }

    return format_daily_progress(logged, target)



def build_telegram_nutrition_reply(analysis: Dict[str, Any]) -> str:
    """Build structured, clean Telegram message response for meal/drink image analysis."""
    header = get_meal_header(analysis)
    short_summary = analysis.get("short_summary") or "Đã ghi nhận bữa ăn thành công!"

    clean_summary = short_summary
    for title in [
        "🍽️ BÁO CÁO DINH DƯỠNG & ĐỒ NHẬU",
        "🍽️ BÁO CÁO BỮA ĂN & MACRO",
        "🍽️ NHẬT KÝ BỮA ĂN & MACRO",
        "🍻 BÁO CÁO ĐỒ NHẬU & NỒNG ĐỘ CỒN",
        "🥤 NHẬT KÝ THỨC UỐNG & VI CHẤT",
        "💧 NHẬT KÝ NƯỚC UỐNG & BÙ NƯỚC",
        "🥗 NHẬT KÝ BỮA PHỤ PHỤC HỒI"
    ]:
        clean_summary = clean_summary.replace(title, "").strip()

    fallback_notice = analysis.get("fallback_notice")
    if fallback_notice and fallback_notice not in clean_summary:
        clean_summary = f"{fallback_notice}\n\n{clean_summary}"

    risk_section = format_sleep_risk(analysis)

    date_str = analysis.get("date") or datetime.now().strftime("%Y-%m-%d")
    progress_section = calculate_live_progress(date_str)

    from src.analytics.prompt_engine import format_ai_metadata_footer
    ai_footer = format_ai_metadata_footer(
        model_used=analysis.get("model_used"),
        latency_seconds=analysis.get("latency_seconds"),
        prompt_tokens=analysis.get("prompt_tokens"),
        completion_tokens=analysis.get("completion_tokens"),
        for_telegram=True
    )

    parts = [header, "", clean_summary]
    if risk_section:
        parts.extend(["", risk_section])
    parts.extend(["", progress_section])
    if ai_footer:
        parts.extend(["", ai_footer])

    return "\n".join(parts)



