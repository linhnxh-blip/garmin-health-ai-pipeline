import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
import requests

from config.settings import settings
try:
    from src.utils.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

# Base timeline offsets relative to race start time (04:00 AM)
DEFAULT_RACE_TIMELINE = [
    {
        "index": 1,
        "offset_minutes": -135,  # 01:45 AM
        "stage": "T-135m (Trước xuất phát 2h15m)",
        "km_mark": "Khởi động & Nạp năng lượng",
        "title": "🍌 Bữa sáng tinh bột sạch",
        "action": "3 lát bánh mì gối trắng + mật ong + 1 chuối chín + 250ml nước ấm. Đảm bảo rỗng đại tràng trước giờ xuất phát.",
        "biomechanics_note": "Ăn chậm nhai kỹ. Uống nước ấm để kích thích nhu động ruột làm rỗng đại tràng nhẹ nhàng.",
        "type": "BREAKFAST"
    },
    {
        "index": 2,
        "offset_minutes": -15,  # 03:45 AM
        "stage": "T-15m (Vùng xuất phát)",
        "km_mark": "Xuất phát",
        "title": "⚡ GEL 1 SiS Limone + 50ml nước lọc",
        "action": "Nạp GEL 1 SiS Limone + 50ml nước lọc. Khởi động nhẹ nhàng.",
        "biomechanics_note": "Rule 2 & Rule 3: Chạy sải bước ngắn tự nhiên, lướt sát đất. Tuyệt đối không ép dẻo hay rướn sải gây căng gân Achilles chân trái.",
        "type": "GEL"
    },
    {
        "index": 3,
        "offset_minutes": 50,  # 04:50 AM
        "stage": "Phút 50",
        "km_mark": "~Km 6",
        "title": "🍍 GEL 2 SiS Pineapple + 1-2 ngụm nước lọc",
        "action": "Nạp GEL 2 SiS Pineapple + 1-2 ngụm nước lọc.",
        "biomechanics_note": "Khóa nhịp tim Zone 2 (<136-140 bpm). Giữ guồng chân quay đều tự nhiên, lướt sát đất.",
        "type": "GEL"
    },
    {
        "index": 4,
        "offset_minutes": 85,  # 05:25 AM
        "stage": "Phút 85",
        "km_mark": "~Km 11",
        "title": "🧂 VIÊN MUỐI SỐ 1 + 2 ngụm NƯỚC LỌC",
        "action": "Uống 1 VIÊN MUỐI SỐ 1 + 2 ngụm NƯỚC LỌC (Không nuốt bằng nước điện giải).",
        "biomechanics_note": "Bù Natri chủ động, bảo vệ thận (Uric Acid nền 442 µmol/L). Chỉ dùng nước lọc tinh khiết để chiêu thuốc/viên muối.",
        "type": "SALT"
    },
    {
        "index": 5,
        "offset_minutes": 125,  # 06:05 AM
        "stage": "Phút 125",
        "km_mark": "~Km 16",
        "title": "🍋 GEL 3 SiS Limone + 1-2 ngụm nước lọc",
        "action": "Nạp GEL 3 SiS Limone + 1-2 ngụm nước lọc.",
        "biomechanics_note": "Duy trì nồng độ đường huyết ổn định. Thư giãn vai, thả lỏng cẳng tay.",
        "type": "GEL"
    },
    {
        "index": 6,
        "offset_minutes": 165,  # 06:45 AM
        "stage": "Phút 165",
        "km_mark": "~Km 21 (Half Marathon)",
        "title": "🧂 VIÊN MUỐI SỐ 2 + 2 ngụm NƯỚC LỌC",
        "action": "Uống 1 VIÊN MUỐI SỐ 2 + 2 ngụm NƯỚC LỌC.",
        "biomechanics_note": "Chống căng cứng bắp chuối, bảo vệ gân Achilles chân trái (GCT Balance tiệm cận 50.3% L). Tiếp tục giữ bước nhỏ lướt đất.",
        "type": "SALT"
    },
    {
        "index": 7,
        "offset_minutes": 205,  # 07:25 AM
        "stage": "Phút 205",
        "km_mark": "~Km 25",
        "title": "🍍 GEL 4 SiS Pineapple + 1-2 ngụm nước lọc",
        "action": "Nạp GEL 4 SiS Pineapple + 1-2 ngụm nước lọc.",
        "biomechanics_note": "Tiếp năng lượng vượt dốc. Thu ngắn sải chân khi lên dốc, không rướn thân trên.",
        "type": "GEL"
    },
    {
        "index": 8,
        "offset_minutes": 245,  # 08:05 AM
        "stage": "Phút 245",
        "km_mark": "~Km 30 (Mốc vượt tường)",
        "title": "🧂 VIÊN MUỐI SỐ 3 + 2 ngụm NƯỚC LỌC",
        "action": "Uống 1 VIÊN MUỐI SỐ 3 + 2 ngụm NƯỚC LỌC.",
        "biomechanics_note": "Mốc vượt tường 30km: Giữ guồng chân quay nhanh (Quick Turnover), bước ngắn lướt sát đất, tuyệt đối không rướn sải (Overstriding).",
        "type": "SALT"
    },
    {
        "index": 9,
        "offset_minutes": 275,  # 08:35 AM
        "stage": "Phút 275",
        "km_mark": "~Km 34",
        "title": "🍋 GEL 5 SiS Limone + 1-2 ngụm nước lọc",
        "action": "Nạp GEL 5 SiS Limone + 1-2 ngụm nước lọc.",
        "biomechanics_note": "Bơm Glycogen chống mệt mỏi hệ thần kinh trung ương. Tập trung thở sâu và giữ nhịp thở đều.",
        "type": "GEL"
    },
    {
        "index": 10,
        "offset_minutes": 305,  # 09:05 AM
        "stage": "Phút 305",
        "km_mark": "~Km 37.5",
        "title": "🧂 VIÊN MUỐI SỐ 4 + 2 ngụm NƯỚC LỌC",
        "action": "Uống 1 VIÊN MUỐI SỐ 4 + 2 ngụm NƯỚC LỌC.",
        "biomechanics_note": "Khóa điện giải chặng cuối chống chuột rút. Giữ vững tinh thần kỷ luật.",
        "type": "SALT"
    },
    {
        "index": 11,
        "offset_minutes": 325,  # 09:25 AM
        "stage": "Phút 325",
        "km_mark": "~Km 40",
        "title": "🏁 GEL 6 SiS Pineapple + 1 ngụm nước",
        "action": "Nạp GEL 6 SiS Pineapple + 1 ngụm nước lọc.",
        "biomechanics_note": "Chặng bứt phá 2km cuối về đích an toàn! Giữ dáng chạy thẳng, lướt sát đất tới cổng vạch đích.",
        "type": "GEL"
    }
]

class RaceNutritionPacer:
    """Real-time race day nutrition & biomechanics pacing reminder module for Full Marathon."""

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[Union[str, int]] = None):
        raw_token = str(bot_token or TELEGRAM_BOT_TOKEN or settings.telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN") or "")
        raw_chat = str(chat_id or TELEGRAM_CHAT_ID or settings.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID") or "")

        self.bot_token = raw_token.strip().strip('"').strip("'")
        self.chat_id = raw_chat.strip().strip('"').strip("'")

    def parse_start_time(self, start_time_str: str = "04:00") -> datetime:
        """Parse HH:MM start time into a today datetime object."""
        now = datetime.now()
        parts = start_time_str.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return now.replace(hour=h, minute=m, second=0, microsecond=0)

    def get_timeline(self, start_time_str: str = "04:00") -> List[Dict[str, Any]]:
        """Calculate exact timestamps for all 11 race nutrition events based on start_time_str."""
        start_dt = self.parse_start_time(start_time_str)
        items = []

        for base in DEFAULT_RACE_TIMELINE:
            item_dt = start_dt + timedelta(minutes=base["offset_minutes"])
            time_str = item_dt.strftime("%H:%M")
            item = dict(base)
            item["scheduled_time"] = time_str
            item["scheduled_datetime"] = item_dt
            items.append(item)

        return items

    def format_alert_message(self, item: Dict[str, Any], start_time_str: str = "04:00") -> str:
        """Format Telegram Markdown card for a specific race pacing alert item."""
        idx = item["index"]
        time_str = item["scheduled_time"]
        km_mark = item["km_mark"]
        title = item["title"]
        action = item["action"]
        bio_note = item["biomechanics_note"]

        msg = (
            f"🏃‍♂️ **RACE PACER — NHẮC DINH DƯỠNG & CƠ SINH HỌC FM 42KM**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ **[{time_str}] Nhắc nhở #{idx}/11 ({km_mark}):**\n\n"
            f"📌 **{title}**\n"
            f"👉 **Hành động:** {action}\n\n"
            f"💡 **Chỉ dẫn Cơ sinh học & Lâm sàng:**\n"
            f"• {bio_note}\n\n"
            f"👤 *VĐV 44t (64.9kg) | Target 5h30m (Pace 7:30-8:00) | Uric Acid 442 µmol/L | Achilles GCT 50.3% L*"
        )
        return msg

    def send_telegram_message(self, text: str) -> bool:
        """Send a single Markdown formatted message to Telegram chat."""
        if not self.bot_token or not self.chat_id:
            print("⚠️ Cannot send Telegram message: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
            return False

        # Convert chat_id if numeric
        if self.chat_id.lstrip("-").isdigit():
            target_chat: Union[int, str] = int(self.chat_id)
        else:
            target_chat = self.chat_id

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            res = requests.post(url, json=payload, timeout=(10, 30))
            if res.status_code == 200 and res.json().get("ok"):
                return True
            else:
                # Retry with plain text fallback if Markdown fails
                payload.pop("parse_mode", None)
                res_plain = requests.post(url, json=payload, timeout=(10, 30))
                return bool(res_plain.status_code == 200 and res_plain.json().get("ok"))
        except Exception as exc:
            print(f"❌ Telegram send error: {exc}")
            return False

    def send_alert(self, item: Dict[str, Any], start_time_str: str = "04:00") -> bool:
        """Format and send alert item via Telegram."""
        msg = self.format_alert_message(item, start_time_str)
        return self.send_telegram_message(msg)

    def send_test_alert(self, alert_index: int, start_time_str: str = "04:00") -> bool:
        """Send test alert for alert_index (1-indexed, 1..11)."""
        timeline = self.get_timeline(start_time_str)
        if alert_index < 1 or alert_index > len(timeline):
            print(f"❌ Invalid test-alert index: {alert_index}. Must be between 1 and {len(timeline)}.")
            return False

        target_item = timeline[alert_index - 1]
        print(f"🧪 Sending TEST ALERT #{alert_index} ([{target_item['scheduled_time']}] {target_item['title']}) to Telegram...")
        success = self.send_alert(target_item, start_time_str)
        if success:
            print(f"✅ Test alert #{alert_index} sent successfully!")
        else:
            print(f"❌ Failed to send test alert #{alert_index}.")
        return success

    def run_dry_run(self, start_time_str: str = "04:00"):
        """Print full race timeline to terminal without sending Telegram notifications."""
        timeline = self.get_timeline(start_time_str)
        print("=" * 80)
        print(f"🏁 TIMELINE NHẮC DINH DƯỠNG & CƠ SINH HỌC FULL MARATHON (GIỜ XUẤT PHÁT: {start_time_str})")
        print("=" * 80)
        print("Hồ sơ VĐV: Nam 44t | Cân nặng: 64.9 kg | Target: 5h30m (Pace 7:30 - 8:00)")
        print("Ràng buộc: Acid Uric 442 µmol/L (uống nước lọc tinh khiết) | Gân Achilles trái (GCT 50.3% L, bước ngắn lướt đất)")
        print("=" * 80)

        for item in timeline:
            print(f"\n⏰ [{item['scheduled_time']}] #{item['index']}/11 — {item['stage']} ({item['km_mark']})")
            print(f"   📌 Item : {item['title']}")
            print(f"   👉 Hành động : {item['action']}")
            print(f"   💡 Cơ sinh học : {item['biomechanics_note']}")

        print("\n" + "=" * 80)
        print(f"✅ Dry-run complete. Total 11 timeline alerts generated.")
        print("=" * 80)

    def start_pacer(self, start_time_str: str = "04:00", dry_run: bool = False, test_alert: Optional[int] = None):
        """Main entry point for race-pacer command."""
        if dry_run:
            self.run_dry_run(start_time_str)
            return

        if test_alert is not None:
            self.send_test_alert(test_alert, start_time_str)
            return

        # Live monitoring mode
        print(f"🚀 Starting Live Race Nutrition Pacer (Race Start: {start_time_str})...")
        timeline = self.get_timeline(start_time_str)
        self.run_dry_run(start_time_str)

        print("\n📡 Listening for scheduled alert times in real-time. Press Ctrl+C to exit.")
        sent_set = set()

        try:
            while True:
                now = datetime.now()
                for item in timeline:
                    idx = item["index"]
                    item_dt = item["scheduled_datetime"]
                    if idx not in sent_set and now >= item_dt:
                        print(f"⏰ Triggering scheduled alert #{idx} ({item['scheduled_time']})...")
                        res = self.send_alert(item, start_time_str)
                        if res:
                            print(f"✅ Alert #{idx} sent to Telegram!")
                        sent_set.add(idx)

                if len(sent_set) >= len(timeline):
                    print("🎉 All 11 race nutrition & biomechanics alerts sent! Race Pacer completed.")
                    break

                time.sleep(15)
        except KeyboardInterrupt:
            print("\n👋 Race Pacer daemon stopped by user.")
