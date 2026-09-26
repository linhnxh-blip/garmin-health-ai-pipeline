# 📖 Bảng Tra Cứu Bộ Lệnh (CLI & Telegram Bot Commands)

Tài liệu tổng hợp toàn bộ danh mục câu lệnh điều khiển hệ thống **Garmin Health AI Pipeline**, phân định rõ ràng giữa các lệnh CLI trong terminal và các lệnh điều khiển trên Telegram Bot.

---

## 💻 1. Danh Mục Lệnh CLI (Terminal / Shell)

Các lệnh được phân chia thành 2 nhóm chính: **Nhóm Đồng bộ (Sync-only)** và **Nhóm Phân tích & Vận hành (Action / Report)**.

### 🔄 Nhóm 1: Đồng bộ Dữ liệu (Sync-Only Commands)
*Không gọi Gemini AI, chỉ thực hiện kéo dữ liệu về lưu vào SQLite database.*

| Tên Lệnh CLI | Mục Đích Sử Dụng | Cú Pháp Thực Tế |
| :--- | :--- | :--- |
| `sync-today` | Kéo dữ liệu sinh lý hôm nay (Garmin, Omron, Sleep, HRV) vào DB mà không sinh báo cáo. | `python main.py sync-today` |
| `sync-day` | Đồng bộ dữ liệu của 1 ngày cụ thể trong quá khứ hoặc hiện tại. | `python main.py sync-day --date 2026-09-18` |
| `sync-range` | Kéo bù N ngày liên tiếp gần nhất để phục vụ tái tạo Baseline 30 ngày. | `python main.py sync-range --days 30` |
| `log-weight` | Ghi nhận cân nặng & tỷ lệ mỡ/cơ (từ cân OMRON VIVA) và đồng bộ lên Garmin Connect. | `python main.py log-weight 64.9 --fat 14.5 --muscle 48.2 --visceral 5` |
| `import-apple-health` | Import file dữ liệu xuất từ Apple Health (export.zip hoặc export.xml). | `python main.py import-apple-health data/export.zip` |
| `sync-google-health` | Đồng bộ dữ liệu cân nặng từ Google Fit REST API vào SQLite DB. | `python main.py sync-google-health` |

---

### 🧠 Nhóm 2: Phân Tích & Vận Hành (Action / Report Commands)
*Thực hiện phân tích sinh lý học, sinh báo cáo Gemini AI và gửi phát tin nhắn.*

| Tên Lệnh CLI | Mục Đích Sử Dụng | Cú Pháp Thực Tế |
| :--- | :--- | :--- |
| `run-daily` | Chuỗi hành động tự động mỗi sáng lúc 04:45 (sync -> analyze -> bắn 4 thẻ Telegram). | `python main.py run-daily` |
| `analyze` | Chạy AI phân tích sinh lý học từ dữ liệu DB đã có, xuất file journal Markdown. | `python main.py analyze --force --date 2026-09-19` |
| `bot` | Khởi chạy Telegram Bot listener 24/7 (nhận ảnh bữa ăn, lệnh /report, /sync, /status). | `python main.py bot` |
| `analyze-image` | Phân tích trực tiếp 1 ảnh bữa ăn cục bộ bằng Gemini Vision và ghi vào DB. | `python main.py analyze-image path/to/meal.jpg --caption "Ăn lúc 13h15"` |
| `status` | Kiểm tra tổng số bản ghi và tình trạng cơ sở dữ liệu SQLite. | `python main.py status` |
| `init` | Khởi tạo bảng dữ liệu SQLite ban đầu. | `python main.py init` |

---

## 📱 2. Danh Mục Lệnh Telegram Bot (Command Handlers)

Các lệnh thực thi trực tiếp bằng cách gõ vào khung chat với Telegram Bot.

| Lệnh Telegram | Mục Đích Sử Dụng | Phản Hồi Từ Bot |
| :--- | :--- | :--- |
| `/report` hoặc `/baocao` | Chạy bù kéo dữ liệu mới nhất, sinh phân tích và bắn 4 thẻ tin nhắn báo cáo về chat. | Phản hồi instant `"🔄 Đang kéo dữ liệu..."` -> Chạy ngầm -> Bắn 4 thẻ Message Cards. |
| `/sync` | Kéo dữ liệu Garmin & Omron mới nhất vào DB (không tạo báo cáo AI). | `"🔄 Đang đồng bộ..."` -> Phản hồi `"✅ Đã đồng bộ dữ liệu thành công!"`. |
| `/status` | Xem tóm tắt nhanh chỉ số sinh lý (HRV, RHR, Sleep, Weight) & dinh dưỡng nạp hôm nay. | Thẻ tóm tắt thông số giấc ngủ, bước chân, cân nặng Omron và tổng Calo/Protein đã log. |
| `/help` hoặc `/start` | Hiển thị menu hướng dẫn tất cả các lệnh được hỗ trợ và cách gửi ảnh bữa ăn. | Menu hướng dẫn định dạng Markdown hỗ trợ. |
| 📸 **Gửi ảnh đồ ăn** | Gửi ảnh bữa ăn kèm caption (ví dụ: *"Ăn xong lúc 13h15"*) để Gemini Vision phân tích. | Thẻ bóc tách Calo, Protein, Carbs, Fat, đơn vị cồn và giờ ăn lưu vào SQLite. |

---

## ⚙️ 3. Các Script Khởi Chạy Tự Động (`scripts/`)

| File Script | Công Dụng | Cách Thực Thi |
| :--- | :--- | :--- |
| `start_bot.bat` | Khởi động Telegram Bot listener 24/7 trên Windows. | `scripts\start_bot.bat` |
| `run_daily.bat` | Script chạy chuỗi vận hành hàng ngày (dùng cho Task Scheduler). | `scripts\run_daily.bat` |
| `setup_scheduler.bat` | Tự động đăng ký Windows Task Scheduler theo khung giờ trong `.env`. | `scripts\setup_scheduler.bat` |
