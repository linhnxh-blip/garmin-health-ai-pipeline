# 🩸 Sổ Tay Hướng Dẫn Quy Trình Nạp & Theo Dõi Xét Nghiệm Máu Định Kỳ
## (Garmin Health AI Pipeline — Medical Records Guide)

Để đảm bảo duy trì thể trạng đỉnh cao, phòng ngừa quá tải mạn tính và hạ đường huyết ban đêm, VĐV khuyến nghị thực hiện xét nghiệm máu định kỳ **4 tháng/lần** (3 lần/năm vào giữa chu kỳ huấn luyện và sau giải chạy lớn).

---

## 🚀 Quy Trình 3 Bước Thao Tác Chuẩn Khi Khám Định Kỳ

```
+-------------------+      +---------------------------------+      +-----------------------------------+
|  BUỚC 1: LẤY ẢNH  | ---> |   BƯỚC 2: THẢ VÀO THƯ MỤC INCOMING| ---> | BƯỚC 3: REVIEW TRÊN TERMINAL     |
| Chụp màn hình     |      | data/medical_records/incoming/  |      | python scripts/ingest_blood_test.py|
| Medlatec/Matsuoka |      |                                 |      | --review                          |
+-------------------+      +---------------------------------+      +-----------------------------------+
```

### 📸 Bước 1: Chụp Ảnh Màn Hình Phiếu Xét Nghiệm
Sau khi nhận kết quả từ cơ sở y tế:
- **Nếu là Medlatec:** Mở app Medlatec trên điện thoại, chụp màn hình đầy đủ các bảng kết quả (đảm bảo file ảnh lưu dạng `IMG_*.jpg` hoặc `IMG_*.png`).
- **Nếu là T-Matsuoka:** Mở trang web hoặc file PDF kết quả T-Matsuoka, chụp màn hình các trang chỉ số (đảm bảo file lưu dạng `Screenshot*.jpg` hoặc `Screenshot*.png`).

---

### 📂 Bước 2: Thả File Ảnh Vào Thư Mục Nhập
Copy toàn bộ các file ảnh đã chụp ở Bước 1 vào đúng thư mục chỉ định của dự án:
```bash
data/medical_records/incoming/
```
*(Lưu ý: Không đổi tên file gốc để Vision AI Parser nhận diện đúng tên cơ sở y tế Medlatec hay T-Matsuoka).*

---

### 🖥️ Bước 3: Chạy Lệnh Review Trực Tiếp Trên Terminal
Mở Terminal tại thư mục gốc của dự án và khởi chạy lệnh review tương tác:

```bash
python scripts/ingest_blood_test.py --review
```

#### Tiến Trình Tương Tác Human-in-the-Loop (HITL):
1. **Bóc tách tự động:** Gemini Vision AI và Parser chuyên biệt sẽ quét ảnh, bóc tách chỉ số và chuẩn hóa đơn vị.
2. **Hiển thị Bảng Review:** Bảng tổng hợp bộ 14 chỉ số cốt lõi (`CORE_SPORT_MARKERS`) sẽ hiện lên Terminal kèm trạng thái (`NORMAL`, `HIGH`, `LOW`) và đơn vị chuẩn.
3. **Phê duyệt Nhanh:**
   - Nhấn **`[ENTER]`** (hoặc gõ `y`): Để xác nhận toàn bộ dữ liệu chính xác 100% và commit ghi vào SQLite Database `garmin_health.db`.
   - Gõ `edit [mã_chỉ_số] [giá_trị_mới]` (ví dụ: `edit HGB 15.2`): Để sửa nhanh chỉ số bị đọc sai trước khi lưu DB.
4. **Tự động Dọn rác:** Sau khi ghi DB thành công, file ảnh thô trong `incoming/` sẽ tự động được di chuyển vào lưu trữ vết.

---

## 📊 Xem So Sánh Xu Hướng Biến Động Sau Khi Nạp
Sau khi đã nạp thành công dữ liệu đợt mới, bạn có thể chạy lệnh so sánh với đợt khám liền trước:

```bash
python scripts/ingest_blood_test.py --compare
```

Terminal sẽ xuất Báo cáo Xu hướng Y học Thể thao (ADA, AHA, EULAR, ACSM) chỉ rõ các chỉ số **Tốt lên (🟢)**, **Xấu đi (🔴)**, hoặc **Ổn định (⚪)** kèm khuyến nghị dinh dưỡng/tập luyện.

---

## 🧬 Giải Nghĩa Bộ 14 Chỉ Số Cốt Lõi (`CORE_SPORT_MARKERS`) Cho VĐV Chạy Bền

| STT | Mã Chỉ Số | Tên Tiếng Việt | Ngưỡng Tham Chiếu Chuẩn | Ý Nghĩa Sinh Lý Học Thể Thao & Vận Động |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **`HGB`** | Huyết sắc tố (Hemoglobin) | $13.5 - 18.0$ g/dL | Khả năng vận chuyển Oxy của máu. HGB cao giúp tăng $VO_2max$; HGB sụt giảm cảnh báo thiếu máu do tan máu vận động (foot-strike hemolysis). |
| 2 | **`HCT`** | Thể tích khối hồng cầu (Hematocrit) | $40.0 - 54.0$ % | Tỷ lệ thể tích hồng cầu trong máu. HCT cao tăng độ nhớt máu; HCT thấp làm giảm sức bền hô hấp. |
| 3 | **`RBC`** | Số lượng hồng cầu | $4.2 - 6.0$ Tera/L | Mật độ tế bào hồng cầu chở oxy đến cơ bắp khi chạy marathon. |
| 4 | **`WBC`** | Tổng số bạch cầu | $4.0 - 10.0$ Giga/L | Chỉ số miễn dịch. WBC $< 3.8$ cảnh báo suy giảm miễn dịch nghiêm trọng do Hội chứng Quá tải (Overtraining). |
| 5 | **`GLUCOSE`** | Đường huyết lúc đói | $3.9 - 6.4$ mmol/L | Nguồn năng lượng Glycogen dự trữ. Glucose $< 4.0$ cảnh báo rủi ro hạ đường huyết ban đêm. |
| 6 | **`HBA1C`** | Chỉ số đường huyết 3 tháng | $4.0 - 5.7$ % | Kiểm soát đường huyết dài hạn. Rất quan trọng để đánh giá độ nhạy Insulin của VĐV. |
| 7 | **`TRIGLYCERIDE`** | Mỡ máu Triglycerides | $0.4 - 1.7$ mmol/L | Dạng mỡ tự do lưu thông trong máu. Triglyceride thấp chứng tỏ khả năng đốt mỡ $FatMax$ rất tốt. |
| 8 | **`CHOLESTEROL`**| Cholesterol toàn phần | $3.6 - 5.2$ mmol/L | Tổng lượng mỡ máu. Cần đối chiếu cùng HDL-C và LDL-C. |
| 9 | **`LDL_C`** | Cholesterol xấu (LDL) | $< 3.4$ mmol/L | Nguy cơ xơ vữa động mạch. VĐV cần duy trì LDL-C thấp để tối ưu lưu thông mạch máu khi tim đập nhanh. |
| 10 | **`HDL_C`** | Cholesterol tốt (HDL) | $> 1.0$ mmol/L | Yếu tố bảo vệ tim mạch, dọn dẹp mỡ thừa trong lòng mạch. VĐV chạy bền thường có HDL-C cao ($> 1.3$). |
| 11 | **`URIC_ACID`** | Acid Uric | $200 - 420$ $\mu$mol/L | Sản phẩm chuyển hóa Purin. Uric Acid tăng cao sau Long Run cảnh báo thiếu nước cấp và dị hóa đạm cơ bắp. |
| 12 | **`CREATININE`** | Creatinine huyết thanh | $62 - 115$ $\mu$mol/L | Chức năng lọc của thận và tỷ lệ tổn thương tế bào cơ sau các bài tập thể lực cường độ cao. |
| 13 | **`ALT`** | Men gan Alanine Aminotransferase | $< 41$ U/L | Tình trạng tổn thương tế bào gan và mức độ vi viêm toàn thân. |
| 14 | **`AST`** | Men gan Aspartate Aminotransferase | $< 37$ U/L | Enzym có trong cả cơ tim, cơ xương và gan. AST tăng tạm thời sau các bài tập biến tốc (Intervals). |
