# 🛠️ Sổ Tay Vận Hành & Khắc Phục Sự Cố (System Runbook)
## `garmin-health-ai-pipeline`

Document này hướng dẫn chi tiết quy trình vận hành bảo trì, sao lưu dữ liệu và xử lý các sự cố thường gặp trong quá trình sử dụng hệ thống.

---

## 1. 🔄 Hướng Dẫn Vận Hành Hàng Ngày

### 1.1. Chạy Quy Trình Phân Tích Độc Lập Hàng Ngày
Mỗi buổi sáng sau khi thức dậy (sau khi Garmin đồng bộ nhịp tim & giấc ngủ đêm):
```bash
python main.py run-daily
```
*Tiến trình thực hiện:*
1. Tự động đồng bộ Garmin Connect API (HRV, Sleep, SpO2, Stress, ACWR).
2. Tự động kéo dữ liệu Omron VIVA (Cân nặng, % Mỡ, % Cơ).
3. Đánh giá Baseline 180 ngày & Xu hướng Máu mới nhất.
4. Sinh báo cáo y học thể thao với Gemini AI và phân phối 4 Thẻ tin nhắn về Telegram Chat.

### 1.2. Khởi Chạy Telegram Bot Listener 24/7
Để khởi chạy Bot lắng nghe ảnh chụp bữa ăn và lệnh điều khiển `/report`, `/sync`, `/status`:
```bash
python main.py bot
```
*(Khuyên dùng: Chạy lệnh này trên Server / PC chạy 24/7 hoặc qua tập lệnh background `start_bot_server.bat`).*

---

## 2. 🚨 Sổ Tay Khắc Phục Sự Cố Thường Gặp (Troubleshooting Guide)

### 2.1. Lỗi Hết Hạn Token Garmin Connect (`garth.exceptions.GarthHTTPError: 401 Unauthorized`)
- **Nguyên nhân:** Token phiên đăng nhập Garmin Connect lưu tại thư mục `.garminconnect/` bị hết hạn hoặc Garmin Cloud yêu cầu xác thực lại.
- **Cách khắc phục:**
  1. Xóa thư mục token cũ:
     ```bash
     rmdir /s /q .garminconnect
     ```
  2. Kiểm tra lại thông tin `GARMIN_EMAIL` và `GARMIN_PASSWORD` trong file `.env`.
  3. Thử lại lệnh đồng bộ:
     ```bash
     python main.py sync
     ```
     *Hệ thống sẽ tự động đăng nhập lại và tạo phiên token mới.*

---

### 2.2. Lỗi API Google Gemini (`google.genai.errors.APIError` hoặc `404 NOT_FOUND`)
- **Nguyên nhân:** Model AI cũ bị ngưng hỗ trợ (deprecated) hoặc API Key bị hết hạn/sai.
- **Cách khắc phục:**
  1. Mở file `.env` kiểm tra giá trị `GEMINI_API_KEY`.
  2. Kiểm tra kết nối Gemini AI qua lệnh Python nhanh:
     ```bash
     python -c "import os; from google import genai; client = genai.Client(api_key=os.getenv('GEMINI_API_KEY')); print(client.models.list())"
     ```
  3. Hệ thống đã tích hợp sẵn cơ chế **Fallback Tự Động**: Nếu model mặc định `gemini-2.5-flash` gặp sự cố, hệ thống sẽ tự động hạ cấp sang `gemini-1.5-flash` mà không làm gián đoạn tiến trình.

---

### 2.3. Lỗi Telegram Bot (`Can't parse entities` hoặc Message Too Long > 4096)
- **Nguyên nhân:** Nội dung báo cáo AI chứa các ký tự Markdown/HTML không hợp lệ hoặc dài quá giới hạn 4096 ký tự của Telegram API.
- **Cách khắc phục:**
  - Hệ thống đã được tích hợp sẵn 2 cơ chế bảo vệ:
    1. **Chunking Engine:** Tự động cắt đoạn báo cáo dài thành các phần nhỏ $< 4000$ ký tự.
    2. **HTML Safe Fallback:** Nếu Telegram từ chối định dạng HTML (`Can't parse entities`), bot sẽ tự động stripped tags và gửi lại dưới dạng Plain Text an toàn.
  - Nếu không nhận được tin nhắn, kiểm tra `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` trong `.env`.

---

### 2.4. Lỗi Trùng Lặp Tiến Trình Bot (`HTTP 409 Conflict: Terminated by other getUpdates request`)
- **Nguyên nhân:** Có 2 cửa sổ Terminal hoặc 2 tiến trình đang cùng chạy `python main.py bot` với một Telegram Bot Token.
- **Cách khắc phục:**
  1. Tắt tất cả các cửa sổ Terminal đang chạy bot.
  2. Kiểm tra tiến trình python đang chạy trên Task Manager / Terminal:
     ```powershell
     Get-Process python | Stop-Process -Force
     ```
  3. Khởi chạy lại đúng 1 instance duy nhất: `python main.py bot`.

---

## 3. 💾 Quy Trình Backup & Restore Cơ Sở Dữ Liệu SQLite

Toàn bộ dữ liệu sinh lý học, xét nghiệm máu và nhật ký dinh dưỡng nằm trong duy nhất file database `data/garmin_health.db`.

### 3.1. Quy Trình Sao Lưu (Backup)
Khuyên dùng thực hiện sao lưu hàng tuần hoặc trước khi nạp xét nghiệm mới:

1. **Sao lưu tự động qua script:**
   Chạy file batch hỗ trợ:
   ```cmd
   backup_now.bat
   ```
2. **Sao lưu thủ công:**
   Do cơ sở dữ liệu chạy ở chế độ **WAL Mode**, bạn nên copy cả 3 file (nếu có):
   - `data/garmin_health.db`
   - `data/garmin_health.db-wal` (nếu tồn tại)
   - `data/garmin_health.db-shm` (nếu tồn tại)
   Vào thư mục lưu trữ an toàn (ví dụ: `backups/garmin_health_2026-09-26.db`).

---

### 3.2. Quy Trình Phục Hồi (Restore)
Trong trường hợp cần khôi phục lại dữ liệu từ bản sao lưu:

1. Dừng toàn bộ các ứng dụng và Telegram Bot đang kết nối tới DB.
2. Xóa các file hiện tại:
   ```powershell
   Remove-Item data\garmin_health.db* -Force
   ```
3. Copy file bản sao lưu đè lại vào `data/garmin_health.db`.
4. Kiểm tra tính toàn vẹn dữ liệu bằng lệnh `status`:
   ```bash
   python main.py status
   ```
   *Terminal sẽ hiển thị lại tổng số bản ghi và xác nhận DB hoạt động bình thường.*
