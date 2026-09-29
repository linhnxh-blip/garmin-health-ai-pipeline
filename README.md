# 🏃‍♂️ Garmin Health AI Pipeline

**Garmin Health AI Pipeline** là một hệ sinh thái tự động hóa phân tích sinh lý học thể thao đa nguồn (Multi-Source Physiology & Precision Nutrition Pipeline) dành cho Vận động viên Đa môn (Multi-Sport Athlete & Marathoner). 

Hệ thống tích hợp dữ liệu sinh lý 24/7 từ Garmin Connect, chỉ số Omron VIVA, bóc tách Xét nghiệm máu (Medlatec & T-Matsuoka), SQLite DB (WAL mode), AI Engine (Google Gemini API with exponential backoff & fallback) cùng giao diện kép **Local Web Dashboard** nội bộ và **Telegram Bot Daemon**.

---

## 🏗️ Kiến Trúc Luồng Dữ Liệu (Data Flow Architecture)

```text
+-----------------------------------------------------------------------------------+
|                           1. MULTI-SOURCE INGESTION                              |
+-----------------------------------------------------------------------------------+
|  [Garmin Connect API]      [Omron VIVA / Scale]     [Medical Records (IMG/Scr)]   |
|   HRV, Sleep, RHR, SpO2      Weight, Fat%, Muscle%    Medlatec & T-Matsuoka Photos|
|           |                           |                             |             |
|           v                           v                             v             |
|    garth Client             CLI / Direct Ingest           Vision AI / Parsers     |
+-----------+---------------------------+-----------------------------+-------------+
            |                           |                             |
            +-------------------+-------+-----------------------------+
                                |
                                v
+-----------------------------------------------------------------------------------+
|                       2. PERSISTENCE LAYER (SQLite DB)                            |
|                          data/garmin_health.db (WAL Mode)                         |
|   - daily_metrics          - blood_tests              - nutrition_logs        |
|   - daily_reports (3 Ca)   - raw_garmin_data          - ai_reports            |
+-----------------------------------------------------------------------------------+
                                |
                                v
+-----------------------------------------------------------------------------------+
|                     3. ANALYTICS & PHYSIOLOGY AI ENGINE                           |
|   - Baseline Calculator (Rolling 180-Day Baseline & All-Time)                     |
|   - ACWR Calculator (Acute:Chronic Workload Ratio with Zero-Division Guard)       |
|   - Clinical Guardrails (Uric Acid 442 µmol/L, Achilles Protection, Atwater Math) |
|   - Intraday Prompt Engine (Separation of Concerns: Morning / Midday / Evening)    |
+-----------------------------------------------------------------------------------+
                                |
                                v
+-----------------------------------------------------------------------------------+
|                     4. DUAL-OUTPUT DELIVERY ARCHITECTURE                          |
|   - Telegram Card (Glanceable Summary < 250 words, 15-second operational read)    |
|   - Local Web Dashboard (FastAPI + Uvicorn: http://localhost:8000/report/...)     |
+-----------------------------------------------------------------------------------+
```

---

## ⚙️ Hướng Dẫn Cài Đặt & Thiết Lập Cấu Hình

### 1. Cài đặt Môi trường & Dependencies
```bash
# Clone repository
git clone <URL_REPO>
cd garmin-health-ai-pipeline

# Khởi tạo & kích hoạt môi trường ảo Python 3.11+
python -m venv venv
venv\Scripts\activate  # Trên Windows (cmd / powershell)
# source venv/bin/activate # Trên Linux / macOS

# Cài đặt thư viện phụ thuộc
pip install -r requirements.txt
```

### 2. Cấu hình File `.env`
Sao chép `.env.example` thành `.env` và khai báo các khóa API:
```bash
cp .env.example .env
```

Nội dung cấu hình `.env`:
```env
TELEGRAM_BOT_TOKEN="your_telegram_bot_token_here"
TELEGRAM_CHAT_ID="your_telegram_chat_id_here"
GEMINI_API_KEY="your_gemini_api_key_here"
GARMIN_EMAIL="your_garmin_email_here"
GARMIN_PASSWORD="your_garmin_password_here"
DB_PATH="data/garmin_health.db"
WEB_HOST="127.0.0.1"
WEB_PORT=8000
BASE_WEB_URL="http://localhost:8000"
```

---

## 🖥️ Bảng Tra Cứu Lệnh CLI Toàn Diện (`main.py`)

Tất cả tác vụ của hệ thống được quản lý qua CLI `main.py`:

### 📥 1. Nhóm Đồng bộ & Thu thập Dữ liệu (Ingestion & Sync)
| Lệnh CLI | Chức Năng / Mô Tả | Cú Pháp Ví Dụ |
| :--- | :--- | :--- |
| `sync-today` | Đồng bộ dữ liệu Garmin & Omron live hôm nay về SQLite. | `python main.py sync-today` |
| `sync-day` | Đồng bộ dữ liệu Garmin cho một ngày cụ thể. | `python main.py sync-day --date 2026-09-29` |
| `sync-range` | Kéo dữ liệu lịch sử N ngày liên tục để xây dựng baseline. | `python main.py sync-range --days 30` |
| `sync-browser` | Đồng bộ qua Browser Session Cookie (bỏ qua giới hạn 429 login). | `python main.py sync-browser --date 2026-09-29` |
| `sync-google-health` | Đồng bộ cân nặng & mỡ cơ thể từ Google Fit API. | `python main.py sync-google-health` |
| `log-weight` | Ghi nhận cân nặng Omron VIVA và đồng bộ Garmin Connect. | `python main.py log-weight 65.5 --fat 17.5 --muscle 37.2` |
| `process-garmin-zip` | Giải nén và nạp gói ZIP Garmin Export (FIT dynamics & wellness). | `python main.py process-garmin-zip --zip-path export.zip` |
| `import-apple-health` | Nạp file xuất dữ liệu sức khỏe từ Apple Health (export.zip). | `python main.py import-apple-health export.zip` |

### 🧠 2. Nhóm Phân tích & Sinh Báo cáo (Analytics & AI Engine)
| Lệnh CLI | Chức Năng / Mô Tả | Cú Pháp Ví Dụ |
| :--- | :--- | :--- |
| `analyze` | Chạy AI Engine tạo báo cáo 3 ca (`morning`, `midday`, `evening`). | `python main.py analyze --type midday` |
| `run-daily` | Quy trình hàng ngày: Sync live -> Phân tích -> Đẩy Telegram card. | `python main.py run-daily --type morning` |
| `evening-checkin` | Check-in 21:00: Bước chân, tải cơ học & nhắc nhở vệ sinh giấc ngủ. | `python main.py evening-checkin` |
| `analyze-achilles` | Phân tích động học HRM-Pro GCT Balance & rủi ro gân Achilles. | `python main.py analyze-achilles` |
| `analyze-image` | Phân tích ảnh bữa ăn trực tiếp qua Vision AI và lưu SQLite. | `python main.py analyze-image path/to/meal.jpg` |

### 📲 3. Nhóm Giao tiếp & Delivery (Telegram & Web Dashboard)
| Lệnh CLI | Chức Năng / Mô Tả | Cú Pháp Ví Dụ |
| :--- | :--- | :--- |
| `web` | Khởi chạy Local Web Dashboard server (FastAPI + Uvicorn). | `python main.py web` |
| `bot` | Chạy Telegram Bot Listener lắng nghe ảnh bữa ăn & lệnh chat 24/7. | `python main.py bot` |
| `send-report` | Gửi báo cáo Markdown đã sinh sẵn lên kênh Telegram. | `python main.py send-report --date 2026-09-29` |

### 🧹 4. Nhóm Quản trị & Tiện ích (Utilities & Maintenance)
| Lệnh CLI | Chức Năng / Mô Tả | Cú Pháp Ví Dụ |
| :--- | :--- | :--- |
| `init` | Khởi tạo cấu trúc bảng SQLite Schema & Indexes ban đầu. | `python main.py init` |
| `status` | Kiểm tra tổng số bản ghi và tình trạng cơ sở dữ liệu. | `python main.py status` |
| `cleanup-duplicates` | Dọn dẹp các bản ghi nhật ký ăn uống bị trùng lặp trong DB. | `python main.py cleanup-duplicates` |

---

## 🔄 Hướng Dẫn Vận Hành Thường Nhật (Daily Operating Workflow)

### Khởi chạy Tiện ích 1-Click (Windows):
Double-click file `run_all.bat` (hoặc `scripts/run_all.bat`) để tự động khởi chạy cả **Local Web Dashboard** (`http://localhost:8000`) và **Telegram Bot Listener** ở chế độ nền.

### Kịch bản 3 Khung giờ trong Ngày:
1. **Buổi Sáng (05:00 - 06:00):**
   - Thức dậy, cân Omron VIVA, chạy lệnh phân tích phiên sáng:
     ```bash
     python main.py analyze --type morning
     ```
   - Nhận thẻ **Telegram Morning Card** tóm tắt Sleep/HRV/Readiness và link tới bài phân tích đầy đủ trên Web Dashboard.

2. **Buổi Trưa (11:30 - 13:00):**
   - Chụp ảnh bữa ăn gửi trực tiếp vào Telegram Bot để ghi nhận tự động.
   - Chạy lệnh cập nhật báo cáo trưa sau bài chạy sáng:
     ```bash
     python main.py analyze --type midday
     ```
   - Báo cáo trưa tập trung đánh giá động học chạy HRM-Pro (GCT Balance L/R, Cadence 178-182 spm), hướng dẫn phục hồi chiều và tính toán quota protein còn lại (khóa tối <= 30g).

3. **Buổi Tối (20:30 - 21:30):**
   - Chạy check-in buổi tối hoặc tạo báo cáo tổng kết ngày:
     ```bash
     python main.py evening-checkin
     ```
   - Nhận thẻ nhắc nhở vệ sinh giấc ngủ (Magie Bisglycinate 300mg, nước kiềm Fujiwa, cắt thiết bị trước 21:00, đi ngủ đúng 21:30).

---

## 🧪 Kiểm Thử Hệ Thống (Pytest Verification)

Chạy bộ test suite tự động với Pytest (đảm bảo **100% PASSED**):
```bash
pytest tests/ -v
```

---

## 📚 Tài Liệu Tham Chiếu Kiến Trúc

- **[Tài liệu Kiến trúc & Thiết kế Hệ thống (ARCHITECTURE.md)](ARCHITECTURE.md)**: Chi tiết sơ đồ dữ liệu, SQLite Schema 6 bảng, quy tắc Separation of Concerns 3 phiên và Ràng buộc Y học Thể thao Lâm sàng.
