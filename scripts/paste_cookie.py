import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from src.ingestion.browser_session_client import fetch_and_store_daily_data_browser, parse_curl_or_cookies

COOKIE_FILE = BASE_DIR / "data" / "garmin_cookies.txt"

def main():
    print("=========================================================")
    print("   GARMIN BROWSER COOKIE / CURL PASTE & SYNC HELPER")
    print("=========================================================")
    print("👉 Hãy mở F12 (Network Tab) trên trình duyệt (trang connect.garmin.com),")
    print("   Copy 1 request bất kỳ (Copy as cURL hoặc Copy Cookie header) và dán bên dưới.")
    print("---------------------------------------------------------")
    print("Dán cURL / Cookie vào đây (bấm Enter 2 lần khi hoàn tất):")

    lines = []
    while True:
        try:
            line = input()
            if not line and lines:
                break
            lines.append(line)
        except (EOFError, KeyboardInterrupt):
            break

    raw_input = "\n".join(lines).strip()
    if not raw_input:
        print("❌ Chưa nhập cURL hoặc Cookie.")
        sys.exit(1)

    headers = parse_curl_or_cookies(raw_input)
    cookie_str = headers.get("Cookie")

    if not cookie_str:
        print("❌ Không tìm thấy Cookie hợp lệ trong nội dung đã dán.")
        sys.exit(1)

    # Save to data/garmin_cookies.txt
    COOKIE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_FILE.write_text(cookie_str, encoding="utf-8")
    print(f"✅ Đã lưu Cookie thành công vào: {COOKIE_FILE}")

    # Test sync today immediately
    today_str = time.strftime("%Y-%m-%d")
    print(f"\n🔄 Đang thử đồng bộ dữ liệu Garmin cho ngày hôm nay ({today_str})...")
    try:
        res = fetch_and_store_daily_data_browser(today_str, raw_curl_or_cookie=cookie_str)
        print(f"\n🎉 ĐỒNG BỘ THÀNH CÔNG CHO NGÀY {res.date}!")
        print(f"   - Điểm số giấc ngủ (Sleep Score): {res.sleep_score or 'N/A'}")
        print(f"   - HRV Ban đêm (HRV Overnight): {res.hrv_last_night or 'N/A'} ms")
        print(f"   - Nhịp tim nghỉ (Resting HR): {res.resting_heart_rate or 'N/A'} bpm")
        print(f"   - Mức độ Stress TB: {res.avg_stress_level or 'N/A'}")
        print(f"   - Tổng số bước: {res.total_steps or 'N/A'}")
    except Exception as err:
        print(f"❌ Lỗi đồng bộ: {err}")

if __name__ == "__main__":
    main()
