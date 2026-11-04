# 🎮 HƯỚNG DẪN TOÀN DIỆN: ĐÓNG GÓI DỰ ÁN LÊN GITLAB & THIẾT LẬP ASUS ROG ALLY X LÀM LOCAL SERVER 24/7 (WINDOWS 11)

Tài liệu này hướng dẫn chi tiết từng bước từ A đến Z để:
1. **Đóng gói mã nguồn sạch** của dự án `garmin-health-ai-pipeline` và đẩy lên **GitLab Repository** cá nhân.
2. **Trích xuất toàn bộ Cơ sở dữ liệu (Database)** cùng Garmin Session Tokens từ máy nguồn.
3. **Biến máy chơi game cầm tay ASUS ROG Ally X (Windows 11)** thành một **Local Server 24/7 siêu tiết kiệm điện (10W - 13W)**, chạy ngầm bền vững cả **Web Dashboard (`0.0.0.0:8000`)** lẫn **Telegram Bot AI**, truy cập mọi lúc mọi nơi từ MacBook, PC, iPhone/Android qua **Tailscale** hoặc mạng **LAN**.

---

## 🚀 CÁCH NHANH NHẤT KHI LÊN CÔNG TY (CHỈ CẦN GIT CLONE TỪ GITHUB)

Toàn bộ **Hướng dẫn**, **Source Code** và **Gói Database mới nhất (`backups/allyx_migration_bundle_latest.zip` & `backups/db_backup.sqlite3`)** đã được đẩy sẵn lên GitHub! Khi lên công ty, bạn **không cần copy thủ công qua USB hay mạng nội bộ nữa**, chỉ cần mở **PowerShell (Run as Administrator)** trên máy đích và chạy đúng 4 dòng lệnh sau:

```powershell
# 1. Clone toàn bộ Code + Hướng dẫn + Database từ GitHub về máy
New-Item -ItemType Directory -Path "C:\Servers" -Force
cd C:\Servers
git clone https://github.com/linhnxh-blip/garmin-health-ai-pipeline.git
cd C:\Servers\garmin-health-ai-pipeline

# 2. Chạy script tự động khôi phục Database từ gói backup có sẵn trong repo + cài đặt Server A-Z
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup_server.ps1 -RuntimeMode venv -ServiceManager nssm
```

> **⚠️ Duy nhất 1 việc cần làm sau khi chạy lệnh trên:** Mở file `.env` (`notepad .env`) để điền `TELEGRAM_BOT_TOKEN` và `GEMINI_API_KEY` của bạn vào (vì GitHub chặn đẩy API Key dạng văn bản rõ để tránh bị khóa key tự động), sau đó khởi động lại dịch vụ là chạy ngay!

---

## 📋 TỔNG QUAN BỘ FILE KỊCH BẢN ĐÃ ĐƯỢC TẠO SẴN

| Tên File | Vai trò & Chức năng | Chạy ở đâu? |
| :--- | :--- | :--- |
| `.gitignore` | Loại trừ tuyệt đối `.env`, `venv/`, `*.db`, `backups/`, `logs/`, `*token*`, `node_modules/`. | Máy nguồn & Đích |
| `export_and_push_gitlab.ps1` / `.sh` | Tự động khởi tạo Git, gỡ các file nhạy cảm khỏi cache, commit code sạch và push lên GitLab. | **Máy nguồn** |
| `dump_database.ps1` / `.sh` | Sao lưu an toàn SQLite (`sqlite3.backup`), PostgreSQL (`pg_dump`), hoặc MySQL (`mysqldump`) ra thư mục `backups/` kèm đóng gói `.zip`. | **Máy nguồn** |
| `restore_database.ps1` | Khôi phục tự động SQLite (`.sqlite3` / `.zip`), PostgreSQL (`pg_restore`), hoặc MySQL trên máy đích. | **ROG Ally X** |
| `setup_server.ps1` | **Script All-in-One trên ROG Ally X**: Clone code, tạo `.env`, restore DB, cài `venv`/`docker`, chống Sleep AC, mở Firewall và cài dịch vụ chạy ngầm 24/7. | **ROG Ally X** |
| `ecosystem.config.js` | Cấu hình quản lý tiến trình chạy ngầm 24/7 bằng **PM2** (chạy đồng thời Web Dashboard + Telegram Bot). | **ROG Ally X** |
| `Dockerfile` & `docker-compose.yml` | Cấu hình đóng gói Container (Docker Desktop / WSL2) với chế độ `restart: unless-stopped`. | **ROG Ally X** |

---

## PHẦN 1: THỰC HIỆN TRÊN MÁY NGUỒN (SOURCE MACHINE)

### Bước 1.1: Tạo Project mới trên GitLab
1. Đăng nhập vào [GitLab.com](https://gitlab.com) (hoặc GitLab Self-Hosted của bạn).
2. Nhấn **New project** $\rightarrow$ **Create blank project**.
3. Đặt tên dự án: `garmin-health-ai-pipeline`.
4. Chọn **Visibility Level**: `Private` (Bắt buộc để bảo mật).
5. **Bỏ chọn** mục *"Initialize repository with a README"* để tránh xung đột lịch sử commit $\rightarrow$ Nhấn **Create project**.
6. Sao chép địa chỉ URL của repo:
   - **Qua SSH**: `git@gitlab.com:<username>/garmin-health-ai-pipeline.git`
   - **Qua HTTPS kèm Personal Access Token (Khuyến nghị nếu chưa cài SSH Key)**:
     `https://oauth2:<GLPAT_TOKEN>@gitlab.com/<username>/garmin-health-ai-pipeline.git`

### Bước 1.2: Chạy Script đóng gói và đẩy mã nguồn sạch lên GitLab
Mở **PowerShell** tại thư mục gốc của dự án trên máy nguồn và chạy:

```powershell
# Cấp quyền thực thi script cho phiên PowerShell hiện tại
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Đẩy lên GitLab (Giữ nguyên remote 'origin' hoặc đặt tên remote là 'gitlab')
.\export_and_push_gitlab.ps1 -GitLabUrl "https://oauth2:<GLPAT_TOKEN>@gitlab.com/<username>/garmin-health-ai-pipeline.git"
```

> **💡 Lưu ý nếu dùng Git Bash / Linux / macOS:**
> ```bash
> chmod +x export_and_push_gitlab.sh
> ./export_and_push_gitlab.sh "git@gitlab.com:<username>/garmin-health-ai-pipeline.git"
> ```

### Bước 1.3: Sao lưu Cơ Sở Dữ Liệu (Database Export)
Vẫn trên máy nguồn, chạy script trích xuất Database ra thư mục `backups/`:

```powershell
# 1. Đối với SQLite (Mặc định của dự án - trích xuất data/garmin_health.db + nén gói Migration ZIP)
.\dump_database.ps1 -DbType sqlite

# 2. Nếu bạn có sử dụng PostgreSQL:
.\dump_database.ps1 -DbType postgres -DbUser postgres -DbName garmin_health

# 3. Nếu bạn có sử dụng MySQL / MariaDB:
.\dump_database.ps1 -DbType mysql -DbUser root -DbName garmin_health
```

Sau khi chạy xong, trong thư mục `backups/` sẽ xuất hiện:
- `backups\db_backup.sqlite3` (Bản sao SQLite nguyên vẹn).
- `backups\garmin_health_<timestamp>.db` (Bản lưu theo mốc thời gian).
- `backups\allyx_migration_bundle_latest.zip` (Gói nén trọn bộ gồm: Database + Garmin Session Tokens `data/.garmin_tokens` + các báo cáo cũ `data/reports`).

### Bước 1.4: Chuyển file Backup sang máy ASUS ROG Ally X
Vì thư mục `backups/` chứa dữ liệu sức khỏe cá nhân và không đẩy lên Git, bạn hãy chuyển file `backups\allyx_migration_bundle_latest.zip` (hoặc `backups\db_backup.sqlite3`) kèm file `.env` sang máy **ASUS ROG Ally X** bằng 1 trong 3 cách nhanh nhất:
- **Cách 1 (Tailscale Taildrop - Nhanh nhất):** Click chuột phải vào file `allyx_migration_bundle_latest.zip` $\rightarrow$ **Send with Tailscale** $\rightarrow$ Chọn máy **ROG Ally X**.
- **Cách 2 (Lệnh SCP qua mạng nội bộ/Tailscale):**
  ```powershell
  scp .\backups\allyx_migration_bundle_latest.zip <User_AllyX>@<IP_AllyX>:C:/Users/<User_AllyX>/Downloads/
  ```
- **Cách 3:** Chép qua USB hoặc thư mục Share SMB trong mạng LAN.

---

## PHẦN 2: THIẾT LẬP MÁY ĐÍCH ASUS ROG ALLY X (WINDOWS 11) LÀM SERVER 24/7

Trên máy **ASUS ROG Ally X**, hãy mở **PowerShell với quyền Administrator** (*Nhấn giữ biểu tượng Start $\rightarrow$ chọn Terminal (Admin) hoặc PowerShell (Admin)*).

### A. Clone Code & Khôi phục Database

#### Bước 2.1: Clone mã nguồn từ GitLab về `C:\Servers\garmin-health-ai-pipeline`
```powershell
# Tạo thư mục chứa các máy chủ trên ổ C:
New-Item -ItemType Directory -Path "C:\Servers" -Force
cd C:\Servers

# Clone dự án từ GitLab
git clone https://oauth2:<GLPAT_TOKEN>@gitlab.com/<username>/garmin-health-ai-pipeline.git
cd C:\Servers\garmin-health-ai-pipeline
```

#### Bước 2.2: Chép file Backup vào thư mục `backups\` và Khôi phục Database
Copy file `allyx_migration_bundle_latest.zip` (hoặc `db_backup.sqlite3`) mà bạn vừa gửi sang vào thư mục `C:\Servers\garmin-health-ai-pipeline\backups\`, sau đó chạy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Khôi phục cho SQLite (Hỗ trợ cả file .zip lẫn .sqlite3/.db)
.\restore_database.ps1 -DbType sqlite

# (Tùy chọn) Nếu khôi phục PostgreSQL:
# .\restore_database.ps1 -DbType postgres -BackupFile "backups\db_backup.dump" -DbUser postgres -DbName garmin_health

# (Tùy chọn) Nếu khôi phục MySQL:
# .\restore_database.ps1 -DbType mysql -BackupFile "backups\db_backup.sql" -DbUser root -DbName garmin_health
```

---

### B. Cấu Hình Biến Môi Trường (`.env`) & Môi Trường Chạy

#### Bước 2.3: Thiết lập file `.env` nội bộ trên ROG Ally X
```powershell
Copy-Item .env.example .env
notepad .env
```
Hãy điền đầy đủ thông tin API của bạn vào `.env`. Đặc biệt lưu ý cấu hình phần **Local Server** ở cuối file `.env`:
```ini
# Mở 0.0.0.0 để mọi thiết bị trong mạng LAN và Tailscale truy cập được
WEB_HOST="0.0.0.0"
WEB_PORT=8000
# Thay 100.x.y.z bằng địa chỉ Tailscale IPv4 của chiếc ROG Ally X
BASE_WEB_URL="http://100.x.y.z:8000"
```

#### Bước 2.4: Chọn 1 trong 2 Phương Án Môi Trường Chạy

##### 👉 Phương án 1 (KHUYẾN NGHỊ CHO ROG ALLY X): Chạy trực tiếp bằng Python Virtualenv (`venv`)
Phương án này tiêu tốn cực ít RAM (~80MB) và CPU (<1%), giúp ROG Ally X luôn mát lạnh ở mức TDP 10W:

```powershell
# Cách tự động hoàn toàn từ A-Z bằng 1 lệnh duy nhất:
.\setup_server.ps1 -RuntimeMode venv -ServiceManager nssm
```
*(Hoặc nếu muốn tự chạy từng lệnh thủ công):*
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

##### 👉 Phương án 2: Chạy bằng Docker Desktop / WSL2 (`docker-compose.yml`)
Nếu bạn muốn cô lập hoàn toàn trong Container:
```powershell
# Tự động build image và khởi chạy cả 2 container (garmin-web & garmin-bot) ở chế độ chạy ngầm tự khởi động lại:
docker compose up -d --build

# Kiểm tra trạng thái container & xem log:
docker compose ps
docker compose logs -f
```

---

### C. Cấu Hình ROG Ally X Làm Server Bền Vững & Chạy 24/7 Trong Nền

#### 1. Quản lý tiến trình ngầm (Auto-start on Boot & Auto-restart on Crash)

Bạn có thể chọn **NSSM (Windows Service)** hoặc **PM2** tùy sở thích:

##### Cách 1A: Dùng NSSM (Non-Sucking Service Manager) - Chuẩn Windows Service gốc (Khuyến nghị nhất)
NSSM biến Python Web Server và Telegram Bot thành dịch vụ hệ thống của Windows (chạy ngay khi bật nguồn máy tính, kể cả trước khi đăng nhập màn hình khóa):

```powershell
# 1. Cài đặt NSSM qua Winget (nếu chưa có)
winget install --id NSSM.NSSM -e

# 2. Biến cố định đường dẫn
$VenvPython = "C:\Servers\garmin-health-ai-pipeline\venv\Scripts\python.exe"
$ProjectDir = "C:\Servers\garmin-health-ai-pipeline"

# 3. Đăng ký Service 1: Web Dashboard Server (Port 8000)
nssm install GarminHealthWeb $VenvPython "`"$ProjectDir\main.py`" web --host 0.0.0.0 --port 8000"
nssm set GarminHealthWeb AppDirectory $ProjectDir
nssm set GarminHealthWeb AppStdout "$ProjectDir\logs\nssm_web_out.log"
nssm set GarminHealthWeb AppStderr "$ProjectDir\logs\nssm_web_err.log"
nssm set GarminHealthWeb AppExit Default Restart
nssm set GarminHealthWeb AppRestartDelay 5000
nssm set GarminHealthWeb Start SERVICE_AUTO_START
nssm start GarminHealthWeb

# 4. Đăng ký Service 2: Telegram Meal & AI Bot Listener
nssm install GarminHealthBot $VenvPython "`"$ProjectDir\main.py`" bot"
nssm set GarminHealthBot AppDirectory $ProjectDir
nssm set GarminHealthBot AppStdout "$ProjectDir\logs\nssm_bot_out.log"
nssm set GarminHealthBot AppStderr "$ProjectDir\logs\nssm_bot_err.log"
nssm set GarminHealthBot AppExit Default Restart
nssm set GarminHealthBot AppRestartDelay 5000
nssm set GarminHealthBot Start SERVICE_AUTO_START
nssm start GarminHealthBot
```
- **Kiểm tra trạng thái dịch vụ:** `Get-Service GarminHealth*`
- **Khởi động lại dịch vụ khi cập nhật code:** `Restart-Service GarminHealthWeb, GarminHealthBot`

##### Cách 1B: Dùng PM2 trên Windows (Sử dụng file `ecosystem.config.js` đã tạo sẵn)
Nếu máy ROG Ally X có cài sẵn Node.js:
```powershell
# 1. Cài đặt PM2 và công cụ tự khởi động cùng Windows
npm install -g pm2 pm2-windows-startup

# 2. Khởi chạy đồng thời cả Web Dashboard & Telegram Bot từ file cấu hình
cd C:\Servers\garmin-health-ai-pipeline
pm2 start ecosystem.config.js

# 3. Lưu danh sách tiến trình và đăng ký tự bật khi khởi động Windows
pm2 save
pm2-startup install

# Một số lệnh theo dõi hữu ích với PM2:
pm2 status
pm2 logs
pm2 monit
```

---

#### 2. Cấu hình Windows Power & Chế độ tản nhiệt/TDP tối ưu trên ASUS ROG Ally X

Để máy ROG Ally X cắm sạc chạy 24/7 năm này qua năm khác mà không bị nóng, không chai pin và không tự động ngủ (Sleep) làm mất kết nối Server:

##### A. Lệnh PowerShell chống Sleep / Hibernate tuyệt đối khi cắm nguồn (AC)
Chạy các lệnh sau trong **PowerShell (Admin)**:
```powershell
# 1. Không bao giờ vào chế độ Sleep (Standby) khi cắm sạc AC
powercfg /change standby-timeout-ac 0

# 2. Không bao giờ vào chế độ Ngủ đông (Hibernate) khi cắm sạc AC
powercfg /change hibernate-timeout-ac 0

# 3. Không tắt ổ cứng SSD
powercfg /change disk-timeout-ac 0

# 4. Tự động tắt màn hình cảm ứng của ROG Ally X sau 5 phút không chạm (Vừa bảo vệ màn hình, vừa giảm 3W điện)
powercfg /change monitor-timeout-ac 5
```

##### B. Cấu hình Armoury Crate SE & MyASUS trên ROG Ally X
1. **Bật chế độ Bảo vệ Pin (Battery Care Mode - Giới hạn sạc 80%):**
   - Mở ứng dụng **MyASUS** trên ROG Ally X $\rightarrow$ mục **Device Settings** $\rightarrow$ Bật **Battery Care Mode (80%)**. Khi đạt 80%, ROG Ally X sẽ dùng nguồn điện trực tiếp (Bypass Charging) từ củ sạc mà không nhồi vào pin, giúp máy mát và pin bền tuyệt đối khi cắm 24/7.
2. **Thiết lập Operating Mode (TDP) trong Armoury Crate SE / Command Center:**
   - Nhấn nút **Command Center** (nút hình tam giác bên trái màn hình) $\rightarrow$ Chuyển **Operating Mode** sang:
     - **Silent (10W)**: Quạt chạy cực êm (gần như không nghe thấy tiếng), CPU AMD Ryzen Z1 Extreme chỉ ăn ~7W - 10W điện khi chạy Python Server.
     - Hoặc tạo profile **Manual (SPL: 13W / SPPT: 15W / FPPT: 15W)** với biểu đồ quạt nâng nhẹ ở mức 30% từ 50°C để máy luôn duy trì nhiệt độ ~42°C - 48°C.
3. **Tắt đèn LED RGB quanh 2 cần Analog (Joystick Lighting):**
   - Trong **Armoury Crate SE** $\rightarrow$ **Lighting** $\rightarrow$ Chỉnh độ sáng về **0% (Off)** để không gây chói mắt ban đêm và tiết kiệm điện.

---

#### 3. Cấu hình Mạng & Truy cập từ xa (Tailscale & LAN Static IP + Firewall)

##### A. Mở cổng trên Windows Defender Firewall (PowerShell Admin)
```powershell
# Mở Port 8000 (TCP Inbound) cho phép các thiết bị trong mạng LAN và Tailscale truy cập Web Dashboard
New-NetFirewallRule -DisplayName "GarminHealthAI_Server_Port_8000" `
    -Direction Inbound `
    -LocalPort 8000 `
    -Protocol TCP `
    -Action Allow `
    -Profile Private,Domain,Public
```

##### B. Truy cập mọi lúc mọi nơi qua Tailscale (Khuyến nghị số 1)
1. Tải và cài đặt [Tailscale cho Windows](https://tailscale.com/download/windows) trên **ASUS ROG Ally X**, đăng nhập cùng tài khoản Tailscale với MacBook / PC / iPhone của bạn.
2. Trên biểu tượng Tailscale ở khay hệ thống (System Tray) của ROG Ally X, vào **Preferences** $\rightarrow$ tích chọn **Run unattended** (để Tailscale luôn kết nối kể cả khi máy khởi động lại).
3. Lấy địa chỉ IP Tailscale của ROG Ally X bằng lệnh:
   ```powershell
   tailscale ip -4
   # Ví dụ kết quả: 100.88.45.12
   ```
4. Cập nhật biến `BASE_WEB_URL="http://100.88.45.12:8000"` trong file `.env` trên ROG Ally X rồi khởi động lại dịch vụ (`Restart-Service GarminHealthWeb, GarminHealthBot`).
5. Giờ đây, khi báo cáo Garmin Health AI gửi về **Telegram** trên điện thoại hoặc MacBook của bạn, các đường link xem chi tiết biểu đồ/báo cáo sẽ mở trực tiếp địa chỉ `http://100.88.45.12:8000` dù bạn đang ở quán cà phê (dùng 4G/5G) hay ở nhà!

##### C. (Tùy chọn) Gán IP Tĩnh (Static LAN IP) cho Wi-Fi trên ROG Ally X
Nếu bạn muốn truy cập qua IP nội bộ cố định (ví dụ `192.168.1.200`):
```powershell
# Xem tên Card Wi-Fi và Default Gateway hiện tại
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null }

# Gán IP tĩnh (Thay thông số phù hợp với lớp mạng Router nhà bạn)
New-NetIPAddress -InterfaceAlias "Wi-Fi" -IPAddress 192.168.1.200 -PrefixLength 24 -DefaultGateway 192.168.1.1
Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses ("1.1.1.1", "8.8.8.8")
```

---

## 🔍 BƯỚC KIỂM TRA VẬN HÀNH CUỐI CÙNG (VERIFICATION CHECKLIST)

Sau khi hoàn tất cài đặt trên **ASUS ROG Ally X**, bạn có thể kiểm tra nhanh bằng các lệnh sau:

```powershell
# 1. Kiểm tra Web Dashboard API phản hồi tốt trên cổng 8000
Invoke-WebRequest -Uri "http://localhost:8000" -UseBasicParsing | Select-Object StatusCode

# 2. Kiểm tra chạy thử bộ kiểm thử (Pytest) trên máy chủ mới
.\venv\Scripts\python.exe -m pytest

# 3. Xem log thời gian thực của Telegram Bot và Web Server
Get-Content .\logs\nssm_bot_out.log -Tail 30 -Wait
```

