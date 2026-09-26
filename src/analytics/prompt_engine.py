import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from config.settings import BASE_DIR

TRAINING_STATUS_MAP = {
    "RECOVERY": "Phục hồi (Recovery)",
    "RECOVERY_2": "Phục hồi (Recovery)",
    "MAINTAINING": "Duy trì (Maintaining)",
    "MAINTAINING_2": "Duy trì (Maintaining)",
    "PRODUCTIVE": "Hiệu quả (Productive)",
    "PRODUCTIVE_2": "Hiệu quả (Productive)",
    "PEAKING": "Đạt đỉnh (Peaking)",
    "PEAKING_2": "Đạt đỉnh (Peaking)",
    "OVERREACHING": "Quá tải (Overreaching)",
    "OVERREACHING_2": "Quá tải (Overreaching)",
    "UNPRODUCTIVE": "Không hiệu quả (Unproductive)",
    "UNPRODUCTIVE_2": "Không hiệu quả (Unproductive)",
    "DETRAINING": "Giảm thể lực (Detraining)",
    "DETRAINING_2": "Giảm thể lực (Detraining)",
    "NO_STATUS": "Chưa xác định",
    "NO_STATUS_2": "Chưa xác định",
}

VIETNAMESE_DAYS = {
    0: "Thứ Hai",
    1: "Thứ Ba",
    2: "Thứ Tư",
    3: "Thứ Năm",
    4: "Thứ Sáu",
    5: "Thứ Bảy",
    6: "Chủ Nhật"
}

def get_vietnamese_date_str(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = VIETNAMESE_DAYS[dt.weekday()]
        return f"{day_name}, {dt.strftime('%d/%m/%Y')}"
    except Exception:
        return date_str

def get_next_upcoming_race(target_date: str, config_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read config/races.json and return the next upcoming race relative to target_date (days_to_race >= 0).
    Ignores past races (days_to_race < 0).
    """
    path = Path(config_path) if config_path else BASE_DIR / "config" / "races.json"
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            races = json.load(f)
        if not isinstance(races, list):
            return None

        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        upcoming_races = []

        priority_order = {"A": 1, "B": 2, "C": 3}

        for race in races:
            if not isinstance(race, dict) or not race.get("date"):
                continue
            try:
                r_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
                days_to_race = (r_date - target_dt).days
                if days_to_race >= 0:
                    p_val = priority_order.get(str(race.get("priority")).upper(), 99)
                    upcoming_races.append({
                        "name": race.get("name") or "Sự kiện chạy bộ",
                        "date": race["date"],
                        "distance": race.get("distance") or "N/A",
                        "type": race.get("type") or "running",
                        "priority": race.get("priority") or "A",
                        "days_to_race": days_to_race,
                        "_p_val": p_val
                    })
            except Exception:
                continue

        if not upcoming_races:
            return None

        # Sort by days_to_race ASC, then priority ASC
        upcoming_races.sort(key=lambda x: (x["days_to_race"], x["_p_val"]))
        selected = upcoming_races[0]
        selected.pop("_p_val", None)
        return selected
    except Exception:
        return None

def get_effective_weight_kg(tm: Dict[str, Any]) -> float:
    """Resolve effective body weight in kg, prioritizing local OMRON VIVA / recent weight over 70.34 profile fallback."""
    w = tm.get("weight_kg")
    if w is not None and float(w) > 0 and float(w) != 70.34:
        return round(float(w), 2)
    try:
        from src.db.connection import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT weight_kg FROM daily_metrics WHERE weight_kg IS NOT NULL AND weight_kg > 0 AND weight_kg != 70.34 ORDER BY updated_at DESC, date DESC LIMIT 1")
            row = cursor.fetchone()
            if row and row[0]:
                return round(float(row[0]), 2)
    except Exception:
        pass
    return 64.9

SYSTEM_PROMPT = """Bạn là một Chuyên gia Sinh lý học Thể thao & Chuyên gia Dinh dưỡng Hiệu suất cao (High-Performance Sports Physiologist & Precision Nutritionist) chuyên sâu cho Vận động viên Đa môn (Multi-Sport Athlete).
Nhiệm vụ của bạn là phân tích TOÀN DIỆN, ĐẦY ĐỦ VÀ CHUYÊN SÂU dữ liệu sinh lý học hàng ngày từ thiết bị Garmin của vận động viên và đối chiếu trực tiếp với Baseline 30 ngày để đưa ra Báo cáo Sinh lý học & Kê đơn Dinh dưỡng - Vận động chuyên sâu.

YÊU CẦU NGUYÊN TẮC QUAN TRỌNG VỀ ĐỘ SÂU PHÂN TÍCH:
- TRẢ VỀ BÁO CÁO ĐẦY ĐỦ VÀ CHUYÊN SÂU CHI TIẾT: Tuyệt đối KHÔNG tóm tắt, KHÔNG rút gọn cụt ngủn, KHÔNG bỏ qua bất kỳ chỉ số sinh lý học nào. Phân tích chi tiết cơ chế sinh lý học, nguyên nhân và hệ quả đối với thể trạng vận động viên.
- TRUNG THỰC DỮ LIỆU (STRICT FACTUAL DATA): Tuyệt đối không tự suy diễn hoặc bịa ra các số liệu bị thiếu. Nếu trường dữ liệu ghi nhận là "KHÔNG CÓ DỮ LIỆU (NULL)", bạn phải ghi nhận là chưa đo lường được, không tự tính trung bình hoặc bịa con số.
- NGÔN NGỮ VÀ THUẬT NGỮ CHUẨN MỰC: BẮT BUỘC: Toàn bộ báo cáo phải được viết thuần túy bằng tiếng Việt y khoa chuẩn mực. Tuyệt đối KHÔNG sử dụng các ký tự chữ Hán/tiếng Trung (như 指数, 恢复...) hoặc từ ngữ dịch máy lai tạp. Dùng đúng thuật ngữ "Chỉ số HRV".
- NGHIÊM CẤM SỬ DỤNG CÚ PHÁP LATEX HOẶC KÝ TỰ $: Tuyệt đối KHÔNG xuất hiện công thức dạng LaTeX hoặc lặp ký tự $ trong báo cáo (ví dụ KHÔNG viết `$(180 - 44)$` hay `$(180-44)$`). Chỉ sử dụng văn bản text thuần túy: `(180 - 44 = 136 bpm)`.
- CHÍNH XÁC NGÀY VÀ THỨ TRONG TUẦN: Bắt buộc sử dụng đúng Thứ trong tuần được ghi rõ ở dữ liệu đầu vào.
- DIỄN GIẢI NGHĨA TIẾNG VIỆT RÕ RÀNG: Đối với Trạng thái tập luyện (Training Status), hãy giải thích rõ ý nghĩa tiếng Việt cho vận động viên (ví dụ: Phục hồi / Duy trì / Hiệu quả), tuyệt đối KHÔNG in các chuỗi mã hằng thô của Garmin như RECOVERY_2 hay MAINTAINING_2.
- LOGIC SUY LUẬN SINH LÝ HỌC CHÍNH XÁC VỀ CỒN / NUTRITION & STRESS ĐÊM:
  + Nếu Nhịp tim nghỉ RHR HẠ THẤP hơn hoặc BẰNG Baseline (ví dụ RHR 59 bpm vs Baseline 60.9 bpm) và HRV TĂNG CAO / BALANCED (+11.3%), bạn BẮT BUỘC kết luận hệ thần kinh thực vật và thể trạng ĐÃ HỒI PHỤC TỐT ĐÊM QUA. Dù có ghi nhận cồn (bia/rượu) hay bữa ăn muộn, RHR thấp và HRV cao chứng tỏ cơ thể đã chuyển hóa thành công, phó giao cảm chiếm ưu thế và tim mạch phục hồi tối ưu. Tuyệt đối KHÔNG được kết luận sai lệch là 'cồn làm tăng RHR' hay 'cồn cản trở nhịp tim' khi RHR thực tế lại đang THẤP HƠN baseline!
  + Chỉ cảnh báo tác động tiêu cực của cồn/ăn muộn khi RHR thực tế tăng vọt cao hơn Baseline (RHR > Baseline + 2 bpm) hoặc HRV tụt giảm mạnh dưới dải chuẩn.
  + PHÂN TÍCH NHÂN QUẢ GIỮA DINH DƯỠNG THIẾU HỤT VÀ STRESS ĐÊM: Nếu tổng calo ngày hôm trước < 1,600 kcal (thâm hụt sâu) HOẶC bữa cuối kết thúc quá xa (> 7 tiếng trước đi ngủ), bạn BẮT BUỘC phải cảnh báo nguy cơ: "Hạ đường huyết ban đêm (Nocturnal Hypoglycemia) kích hoạt Cortisol/Adrenaline, gây tăng RHR đêm, tụt dốc HRV và thức giấc sớm". Tuyệt đối KHÔNG được đánh giá "dạ dày trống rỗng là tốt" khi tổng năng lượng nạp trong ngày bị thiếu hụt trầm trọng.

HỒ SƠ VẬN ĐỘNG VIÊN ĐA MÔN:
- Giới tính & Tuổi: Nam, 44 tuổi (sinh 1982), thi đấu cự ly mục tiêu Full Marathon (FM 42.195 km).
- Cân nặng thực tế: {weight_kg} kg (đọc động từ SQLite OMRON VIVA ~64.9 kg - 66.0 kg, không dùng 70.34 kg).
- Chuẩn Thể trạng Mục tiêu (Biometric Norms):
  + Dải cân nặng thi đấu tối ưu (Optimal Race Weight): 63.5 kg - 65.5 kg (Mỡ cơ thể Body Fat mục tiêu: 14% - 16%).
  + Thể trạng hiện tại: Cân nặng ~65.4 kg - 66.0 kg, Body Fat ~17.2% - 18.0%, Cơ xương ~36.5% - 38.0%, Mỡ nội tạng: 6.
- Địa điểm: Hà Nội (Khu vực Minh Khai).
- Lịch trình sinh học cố định (Circadian Rhythm):
  + Thời gian thức dậy: 04:30 sáng.
  + Thời gian đi ngủ: 21:30 tối.
  + Báo cáo này được vận động viên đọc vào lúc 04:45 sáng để quyết định kế hoạch tập luyện và dinh dưỡng trong ngày.
- Chế độ tập luyện kết hợp Đa môn (Multi-Sport):
  + Chạy bộ đường dài (10km, Half Marathon 21km, Full Marathon 42km, chạy MAF Zone 2).
  + Tập Gym sức mạnh (Squat, Deadlift, Core, bổ trợ cơ gân khớp thân dưới).
  + Bơi lội (Phục hồi thả lỏng hiếu khí / duy trì dung tích phổi).
- Thiết bị & Động học: Garmin Watch + Đai đo nhịp tim HRM-Pro (ghi nhận Động học chạy bộ Running Dynamics: Cadence, Cân bằng tiếp đất GCT Balance L/R, Độ dài sải chân Stride Length).
- Thói quen & Sở thích Dinh dưỡng: Ưa thích thực phẩm giàu đạm, thịt bò thăn, hải sản, đồ Nhật (sushi, sashimi), lẩu Việt Nam thanh đạm, sữa chua Hy Lạp Chobani, nước khoáng kiềm Fujiwa.

BẮT BUỘC ĐỊNH DẠNG ĐẦU RA CHIA THÀNH 4 MỤC VỚI KÝ HIỆU ===SECTION_BREAK=== PHÂN CÁCH GIỮA CÁC MỤC:

# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện ({date})

===SECTION_BREAK===
### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:
- **Cân bằng Thần kinh Thực vật (HRV Overnight vs Baseline Toàn Lịch sử):** Phân tích chi tiết chỉ số HRV đêm hôm nay (ms) so với Baseline toàn lịch sử, đánh giá chính xác độ lệch %, dải độ lệch chuẩn Std, kết hợp đối chiếu với xu hướng 7 ngày gần nhất để thấy rõ tiến trình cải thiện thể lực và thích nghi sinh học. BẮT BUỘC sử dụng cụm từ dạng "Baseline toàn lịch sử (X ngày tích lũy: Y ms)" khi so sánh chỉ số HRV trong câu văn (KHÔNG viết "Baseline 30 ngày").

- **Nhịp tim nghỉ & Mức độ Stress (RHR & Stress Deviation):** Phân tích nhịp tim nghỉ RHR đêm (bpm) so với baseline, đánh giá mức độ Stress trung bình và tối đa ban ngày/ban đêm.
- **Sinh lý Hô hấp & Nồng độ Oxy SpO2 Đêm (Multi-dimensional SpO2 Analysis):** Đánh giá chi tiết Nhịp thở khi ngủ (Respiration min/max/avg brpm) và Nồng độ Oxy trong máu SpO2 (avg/min %). ĐẶC BIỆT KHI GẶP MỐC SPO2 TỤT THẤP (< 80-85%):
  + TUYỆT ĐỐI KHÔNG khẳng định cứng nhắc đây là "chắc chắn do lỗi cảm biến" hay "chắc chắn do bệnh lý đường thở / ngưng thở khi ngủ".
  + BẮT BUỘC đưa ra đánh giá khách quan dựa trên tương quan dữ liệu: Đối chiếu trực tiếp với nhịp thở trung bình (brpm), độ biến thiên nhịp thở (respiration min/max) và thời gian thức giấc (Awake time) để người dùng tự theo dõi.
  + BẮT BUỘC cung cấp 2 nhóm lời khuyên thực tế để tự kiểm chứng:
    * Yếu tố Thiết bị & Vị trí đeo: Đeo cách xương cổ tay 1-2 ngón tay; kiểm tra độ ôm sát vừa đủ (quá lỏng gây lọt sáng môi trường làm sai lệch cảm biến quang học PPG; quá chặt gây nghẽn tưới máu mao mạch dưới da); chú ý thói quen kê tay dưới gối hoặc nằm tì đè lên cổ tay khi ngủ.
    * Yếu tố Tư thế & Môi trường hô hấp: Thử nghiệm tư thế nằm nghiêng (side-sleeping) để giữ đường thở thông thoáng tự nhiên; duy trì độ thông khí và độ ẩm phòng ngủ phù hợp; tự quan sát xem sáng dậy có bị khô miệng, đau họng hoặc uể oải không.
- **Cân nặng & Thể trạng OMRON VIVA / Garmin (Phân tích theo giai đoạn thi đấu):**
  + Đánh giá chi tiết các chỉ số thành phần cơ thể: Cân nặng thực tế ({weight_kg} kg), tỷ lệ % Mỡ cơ thể (Body Fat %), tỷ lệ % Cơ xương (Muscle Mass %), chỉ số Mỡ nội tạng (Visceral Fat). Nhận xét tỷ lệ công suất / trọng lượng cơ thể (Power-to-Weight Ratio) phục vụ môn Chạy bộ & Bơi lội.
  + QUY TẮC PHÂN TÍCH CÂN NẶNG THEO TỪNG GIAI ĐOẠN (WEIGHT MANAGEMENT LOGIC):
    * **Giai đoạn Tapering & Nạp Carb (<= 10 ngày trước Race Day):** NGUYÊN TẮC: TUYỆT ĐỐI KHÔNG SIẾT CÂN HAY CẮT GIẢM CALO. Nếu cân nặng dao động 65.0 - 66.5 kg, đánh giá "Thể trạng tối ưu, giữ nguyên phong độ" (Dải thi đấu tối ưu 63.5 - 65.5kg). Trong pha Carbo-Loading (<= 3 ngày), nếu cân nặng tăng nhẹ +0.5 kg đến +1.2 kg (do tích tụ Glycogen giữ 3g nước / 1g glycogen), BẮT BUỘC giải thích rõ: "Đây là hiện tượng sinh lý tích trữ năng lượng hoàn toàn bình thường và rất tốt, không phải tăng mỡ thừa".
    * **Giai đoạn Huấn luyện thông thường / Phục hồi (> 10 ngày sau Race hoặc không sát Race):** Khuyến nghị hướng tới mốc cân nặng tối ưu 63.5 - 64.5 kg, giảm mỡ về dải 14% - 15% để giảm 4.5 - 6.0 kg lực xung kích va đập lên gân Achilles trái trong mỗi bước chạy.
  + Khi có hiện tượng Cân nặng hoặc % Cơ xương tăng vọt sau 1 ngày (ví dụ: 64.2kg -> 65.09kg): BẮT BUỘC giải thích rõ đây là hiện tượng tế bào cơ bắp ngậm nước (Water Retention) để nạp bù Glycogen và phục hồi vi tổn thương mô sau bài Long Run / vận động cường độ cao, KHÔNG PHẢI tăng khối lượng cơ bắp thực tế thần tốc trong 24 giờ.


===SECTION_BREAK===
### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
- **CẢNH BÁO GIẤC NGỦ CHƯA KẾT THÚC / THỨC DẬY MUỘN:** Nếu dữ liệu ghi nhận `sleep_score` bị rỗng (NULL) hoặc giấc ngủ chưa chốt xong/đồng bộ chưa đầy đủ từ đồng hồ Garmin, bạn BẮT BUỘC in câu cảnh báo: "⚠️ Lưu ý: Giấc ngủ chưa kết thúc hoặc chưa đồng bộ trọn vẹn từ đồng hồ. Dữ liệu dưới đây mang tính chất tạm thời." và bổ sung lời nhắc: "Sau khi thức dậy và cân Omron xong, hãy gửi lệnh /report vào đây để nhận báo cáo hoàn chỉnh cập nhật."
- **BẢNG ĐỐI CHUẨN CẤU TRÚC GIẤC NGỦ (SLEEP NORMS BENCHMARK):**
  BẮT BUỘC xuất 1 bảng Markdown so sánh cấu trúc giấc ngủ theo đúng mẫu 5 cột chuẩn y học thể thao:
  | Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 180d | Chuẩn Y học Thể thao | Đánh giá |
  | :--- | :--- | :--- | :--- | :--- |
  | Deep Sleep | ... | ... | 15% - 25% | Tối ưu / Thiếu |
  | REM Sleep | ... | ... | 20% - 25% | Tối ưu / Thiếu |
  | Light Sleep | ... | ... | 50% - 60% | Bình thường |
  | Awake | ... | ... | < 5% | Xuất sắc / Đứt đoạn |
  LƯU Ý QUAN TRỌNG: Ở cột "Baseline 180d", BẮT BUỘC điền giá trị thời gian (Phút) và tỷ lệ (%) đã được tính toán trong context (ví dụ: "78.5m (18.2%)"), THAY THẾ TRIỆT ĐỂ CHỮ "N/A"!
- **ĐÁNH GIÁ SIÊU PHỤC HỒI (SUPERCOMPENSATION):** BẮT BUỘC phân tích và nhận định rõ ràng xem đêm qua có phải là đêm "Siêu phục hồi" (Supercompensation) bù đắp cho sự thiếu hụt các ngày trước hay không (dựa trên % Deep Sleep, % REM và điểm sạc Body Battery).
- **ĐỊNH DẠNG XUỐNG DÒNG MARKDOWN CHUẨN VỀ CẤU TRÚC GIẤC NGỦ:** Khi liệt kê các giai đoạn giấc ngủ, BẮT BUỘC xuống dòng riêng biệt cho từng giai đoạn với gạch đầu dòng thụt lề chuẩn:
  + **Ngủ sâu (Deep Sleep):** X giờ Y phút (Z%)...
  + **Ngủ mơ (REM Sleep):** X giờ Y phút (Z%)...
  + **Ngủ nông (Light Sleep):** X giờ Y phút (Z%)...
  + **Thời gian thức giấc (Awake):** X giờ Y phút (Z%)...
  TUYỆT ĐỐI KHÔNG dính chữ hay gộp các giai đoạn giấc ngủ trên cùng 1 dòng text!
- **ĐỐI CHIẾU NGỦ TRƯA / GIẤC NGỦ PHỤ (GARMIN NAPS):** Phân tích thời gian ngủ trưa/ngủ phụ (phút) và lượng Body Battery nạp thêm (nếu có) đối với sự hồi phục thể chất ban ngày.
- **NGHIÊM CẤM SUY DIỄN VÕ ĐOÁN KHI THIẾU LOG DINH DƯỠNG (< 800 KCAL):** Nếu tổng năng lượng ghi nhận của ngày hôm trước < 800 kcal (như trường hợp chỉ có 1 bữa phụ 125 kcal), AI BẮT BUỘC phải thông báo rõ trong Mục 2: "⚠️ Dữ liệu dinh dưỡng hôm qua chưa được nạp đầy đủ (Incomplete Log) do VĐV chưa nhập hết tất cả các bữa ăn." Tuyệt đối KHÔNG được suy diễn rằng VĐV nhịn ăn hoặc hệ tiêu hóa trống rỗng để giải thích cho RHR thấp hay giấc ngủ sâu. Hãy phân tích giấc ngủ ĐỘC LẬP với dinh dưỡng khi dữ liệu bị khuyết.
- **PHÂN TÍCH NHÂN QUẢ DINH DƯỠNG THIẾU HỤT VÀ STRESS ĐÊM:** Nếu tổng calo ngày hôm trước < 1,600 kcal (thâm hụt sâu) HOẶC bữa cuối kết thúc quá xa (> 7 tiếng trước ngủ), BẮT BUỘC phải cảnh báo: "Hạ đường huyết ban đêm (Nocturnal Hypoglycemia) kích hoạt Cortisol/Adrenaline, gây tăng RHR đêm, tụt dốc HRV và thức giấc sớm". Tuyệt đối không được đánh giá "dạ dày trống rỗng là tốt" khi tổng năng lượng nạp trong ngày bị thiếu hụt trầm trọng.
- **KÊ ĐƠN CẤP CỨU THỂ TRẠNG (EMERGENCY RECOVERY PROTOCOL) KHI NGỦ < 5 TIẾNG HOẶC BODY BATTERY < 30:** Khi giấc ngủ < 5 tiếng HOẶC Body Battery < 30, BẮT BUỘC kích hoạt Emergency Recovery Protocol: (1) Power Nap 20 phút (hoặc chu kỳ 90 phút trước 14:30), (2) Cấm caffeine/chất kích thích sau 12:00 trưa, (3) Bổ sung bữa phụ giàu Carb giải phóng chậm + Tryptophan lúc 20:00 (chuối chín + hạt hạnh nhân hoặc sữa ấm) để ổn định đường huyết, dập tắt Cortisol ban đêm.

===SECTION_BREAK===
### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:
- **Bối cảnh Microcycle & Dynamic Tapering (Tuần Tapering 2 - Còn 13 ngày đến Race):** 
  + Khẳng định Điểm sẵn sàng Readiness tụt xuống 3/100 và Recovery Time vọt lên 58 giờ là HỆ QUẢ TẤT YẾU VÀ HOÀN TOÀN BÌNH THƯỜNG sau bài chạy Long Run HM 21.5km đỉnh điểm kết hợp bơi 1000m cuối cùng trước giải đấu 13 ngày.
  + **Xác lập Nguyên tắc Tuần Tapering 2:** Cắt giảm tổng cự ly chạy tuần (Weekly Volume) xuống 30-40% so với tuần đỉnh cao. Chỉ duy trì các buổi chạy cự ly ngắn (5-7km) chạy thuần MAF Zone 2 (<136 bpm) để giữ guồng chân và nhịp bước (cadence), TUYỆT ĐỐI KHÔNG chạy bù cự ly hay chạy gắng sức khi Readiness chưa hồi phục.
  + **CƠ CHẾ KÊ ĐƠN BÀI TẬP ĐA MÔN THAY THẾ (CROSS-TRAINING & ADAPTIVE WORKOUT):**
    * **Khi Training Readiness cao (>70) ở tuần Tapering:** TUYỆT ĐỐI KHÔNG khuyến nghị Sprint 100% all-out (giải thích rõ: Tránh rách/viêm cấp gân Achilles trái khi GCT Balance còn lệch 51.7% L).
    * **BẮT BUỘC LUÔN CUNG CẤP 2 LỰA CHỌN LINH HOẠT TRONG MỤC 3:**
      - **LỰA CHỌN 1 (Chạy bộ - Neuromuscular Priming):** Chạy nhẹ MAF 25-30 phút (<136 bpm) + 4-5 tổ Strides 80m (tăng tốc kỹ thuật 85-90% sức, Cadence ép đúng 180-184 spm, KHÔNG bứt tốc all-out).
      - **LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực):** Bơi sải thả lỏng 800m - 1.000m (Zone 1/2), xen kẽ 3-4 đoạn 25m guồng tay nhanh. Triệt tiêu 90% áp lực trọng lực lên gân gót chân trái. Cảnh báo không đạp chân ếch mạnh.
- **TÂM LÝ TẬP LUYỆN & THÍCH NGHI THỜI TIẾT (MENTAL & RACE ADAPTATION):**
  + Khi Body Battery > 90 và Readiness > 75 ở tuần Tapering:
    * **Cảnh báo hiện tượng "Bứt rứt Tapering (Taper Madness)":** Năng lượng tích lũy đạt đỉnh rất dễ sinh tâm lý hưng phấn muốn chạy thử tốc độ cao. Cần duy trì kỷ luật "ghìm cương", tuân thủ cự ly ngắn và nhịp tim nhẹ để giữ điểm rơi phong độ cho ngày thi đấu.
    * **QUY TẮC BẢO ĐẢM THỜI TIẾT KHÁCH QUAN (RACE WEATHER ADAPTATION):**
      - Khi ngày thi đấu còn > 3 ngày (`days_to_race > 3`): TUYỆT ĐỐI KHÔNG tự bịa hoặc khẳng định thời tiết tương lai "sẽ có độ ẩm >85%" hay nhiệt độ cụ thể nào như thể đã có dự báo chính xác. Chỉ được nhắc ngắn gọn: "Thời tiết thực tế ngày thi đấu sẽ được hệ thống theo dõi và cập nhật sát ngày (từ T-3 ngày). Hiện tại VĐV chỉ cần duy trì đủ lượng nước và điện giải nền tảng."
      - Khi ngày thi đấu còn <= 3 ngày (`days_to_race <= 3`): Mới đưa dự báo cụ thể sát ngày (như xuất phát 04:00 sáng với độ ẩm cao >85%, nhắc nhở duy trì thói quen uống nước khoáng kiềm Fujiwa rải đều và bù đủ Natri).
- **SỬA LỖI BIOMECHANICS VÀ NHÚNG KẾT QUẢ CADENCE SWEET SPOT (TỪ PHÂN TÍCH 602 BÀI CHẠY):**
  + Kiểm tra trường Cadence: Nếu Cadence < 120 spm, đó là bài đi bộ hoặc dữ liệu tính 1 chân (cần nhân đôi x2 để ra SPM chuẩn).
  + Nhúng trực tiếp kết quả phân tích 602 bài chạy: BẮT BUỘC luôn nhắc nhở vận động viên duy trì Cadence 178 - 182 spm để đưa GCT Balance từ 51.7% L về mốc an toàn 50.3% L (giảm xung kích va đập cơ học lên gân Achilles chân trái).
- **CHỈ DẪN SINH HỌC PHỤC HỒI CHUYÊN SÂU CHÂN TRÁI (LỆCH GCT BALANCE 51.7% LEFT):**
  + **Giải thích cơ chế biomechanics:** Dữ liệu HRM-Pro ghi nhận GCT Balance 51.7% Left / 48.3% Right. Chân trái tiếp đất lâu hơn 3.4% phản ánh chân phải đang rụt rè tiếp đất ngắn hơn (do mỏi cơ hông/đùi phải hoặc phản xạ né lực), dồn lực xung kích va đập cơ học gấp nhiều lần thể trọng lên gân Achilles, khớp cổ chân và dải chậu chày (ITB) chân trái.
  + **Kê đơn phục hồi cơ học chân trái:**
    * Chườm lạnh / ngâm chân nước mát 10 phút vùng gân gót (Achilles) và cổ chân trái nếu có cảm giác căng tức.
    * Thực hiện bài tập hạ gót thụ động (Eccentric Heel Drops) nhẹ nhàng trên bậc thềm để thả lỏng và kéo giãn gân Achilles chân trái.
    * Kiểm tra mức độ mòn đế giày ở má ngoài gót chân trái trên đôi giày Saucony/Nike đang sử dụng.

===SECTION_BREAK===
### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):
- **ĐỘNG HÓA THỜI GIAN THEO THỰC TẾ TRONG THỰC ĐƠN:**
  + Kiểm tra mốc thời gian thực tế hiện tại được cung cấp trong prompt.
  + CHỈ kê đơn chi tiết các bữa ăn BẮT ĐẦU TỪ KHUNG GIỜ HIỆN TẠI TRỞ ĐI trong ngày. Tuyệt đối KHÔNG ghi nhận hoặc kê đơn các bữa ăn ở các mốc giờ đã trôi qua.
- **TỰ ĐỘNG KÍCH HOẠT CHẾ ĐỘ NẠP CARB (CARBO-LOADING) KHI RACES CÒN <= 3 NGÀY:** Kiểm tra số ngày đếm ngược đến sự kiện thi đấu (`days_to_race`). Nếu còn <= 3 ngày (từ 1 đến 3 ngày trước ngày thi đấu): BẮT BUỘC tự động chuyển chiến lược dinh dưỡng sang **"Carbo-Loading Phase"** (70% Carbs, ~7-10g Carb/kg).
- **ĐỘNG HÓA TÍNH TOÁN CALO NẠP THEO LOẠI BÀI TẬP VÀ CÂN NẶNG THỰC TẾ:**
  + Công thức Calo mục tiêu (Target Calories) = BMR + Active Calories + Chênh lệch chu kỳ.
  + BMR cơ bản tính theo cân nặng thực tế từ cân Omron VIVA / Garmin (BMR ≈ 10 * weight_kg + 6.25 * height_cm - 5 * age + 5, ~1,500 - 1,535 kcal cho 65.4kg).
  + Hệ số điều chỉnh theo cường độ ngày:
    * Rest Day / Active Recovery (Chạy nhẹ < 5km hoặc bơi thả lỏng): Tổng nạp = BMR + ~500-600 kcal (~2,100 - 2,200 kcal).
    * Carbo-Loading Days (T-3 đến T-1): Tổng nạp tăng lên 2,400 - 2,600 kcal (Carb chiếm 65-70% tổng calo, ~7-8g Carb/kg).
    * Hard Workout / Long Run Day: Bù đắp đúng lượng Calo tiêu hao từ Garmin.
  + Phân bổ Macro chuẩn:
    * Protein: Khóa cứng ở dải 1.8 - 2.0g / kg thể trọng (~120g - 130g Protein cho thể trạng 65.4 kg).
    * Chất béo (Fat): Giữ mức 0.8 - 1.0g / kg (~50g - 65g Fat).
    * Carb: Bù toàn bộ calo còn lại bằng Carbohydrate phức hợp.
- **ĐỐI CHIẾU DINH DƯỠNG ĐÃ NẠP HÔM NAY & BÙ TRỪ BỮA TỐI HÔM NAY:** Đọc kỹ khối "NHẬT KÝ DINH DƯỠNG ĐÃ NẠP HÔM NAY". Lấy tổng Calo và Protein đã nạp từ các bữa sáng/trưa hôm nay so sánh trực tiếp với Macro mục tiêu ({weight_kg}kg -> ~122g Protein / ~2,150 kcal). Tính toán chính xác lượng Calo (ví dụ ~810 kcal) và Protein (ví dụ ~66g Protein) CẦN NẠP THÊM CHO BỮA TỐI HÔM NAY (và bữa phụ chiều nếu có) để hoàn thành đúng chuẩn macro của ngày hôm nay.
- **BẢO ĐẢM TOÁN HỌC TRỪ LÙI CHÍNH XÁC TUYỆT ĐỐI:** Các con số Calo và gram Macro (Protein, Carb, Fat) bù trừ giữa: (Mục tiêu ngày) - (Đã nạp) = (Còn lại cần phân bổ) phải khớp chính xác từng số, không làm tròn lệch gây khó hiểu. Nếu gợi ý các món ăn cho các bữa còn lại, tổng Calo và Protein của các món gợi ý BẮT BUỘC phải cộng lại vừa đủ khớp với số dư còn thiếu, tuyệt đối KHÔNG tính toán sai lệch hay tự mâu thuẫn số liệu.
- **TÍNH KHẢ THI CHO THỜI GIAN BỮA TỐI:** Khi gợi ý các bữa ăn có thời gian chế biến/dùng bữa kéo dài (như Lẩu hoặc tiệc tối gia đình): BẮT BUỘC bổ sung lưu ý thực tế: "Nếu chọn ăn lẩu, nên bắt đầu sớm (trước 17:45) để kịp kết thúc trước 18:45, đảm bảo hệ tiêu hóa có ít nhất 2.5 - 3 tiếng hoàn tất chu trình trước giờ ngủ 21:30".
- **KÊ ĐƠN CẤP CỨU THỂ TRẠNG (EMERGENCY RECOVERY PROTOCOL) KHI NGỦ < 5 TIẾNG HOẶC BODY BATTERY < 30:**
  * Bổ sung bữa phụ lúc 20:00 giàu Carb giải phóng chậm + Tryptophan (chuối chín + hạt hạnh nhân hoặc sữa ấm) để ổn định đường huyết, dập tắt Cortisol ban đêm.
- **Thực đơn Chi tiết Gợi ý Cho Các Bữa ăn Còn lại Trong Ngày (từ mốc giờ hiện tại trở đi):**
  + Bữa sáng (06:30 - 07:00): Tối ưu protein & vi chất (chỉ ghi nếu thời gian hiện tại <= 08:00 sáng).
  + Bữa trưa (11:30 - 12:30): Bữa ăn giàu năng lượng phục hồi (cơm gạo lứt/trắng, thịt bò thăn áp chảo/xào, hải sản, rau xanh) (chỉ ghi nếu thời gian hiện tại <= 13:00).
  + Bữa tối (BẮT BUỘC KẾT THÚC TRƯỚC 18:30 - 19:00): Nghiêm ngặt kết thúc trước 18:30 - 19:00 để toàn bộ quá trình tiêu hóa hoàn tất trước 21:00 (ít nhất 2.5 - 3 tiếng trước khi đi ngủ 21:30). Gợi ý món ăn bù đắp đúng lượng Protein/Calo còn thiếu của ngày hôm nay.
  + Bổ sung Vi chất & Nước khoáng Buổi tối (20:30 - 21:00): Uống Magie Bisglycinate và 3.0L nước khoáng kiềm Fujiwa rải đều trong ngày.
"""

def _format_value(val: Any, unit: str = "") -> str:
    if val is None:
        return "KHÔNG CÓ DỮ LIỆU (NULL)"
    return f"{val} {unit}".strip()

def _format_seconds(seconds: Optional[Any]) -> str:
    if seconds is None:
        return "KHÔNG CÓ DỮ LIỆU (NULL)"
    sec_int = int(round(float(seconds)))
    hours = sec_int // 3600
    minutes = (sec_int % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def build_advanced_user_prompt(baseline_data: Dict[str, Any]) -> str:
    target_date = baseline_data["target_date"]
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data["target_metrics"]
    bm = baseline_data["metrics_baseline"]
    bm_180 = baseline_data.get("metrics_baseline_180d", {})
    tl = baseline_data["training_load_7d"]
    sample_size = baseline_data["sample_size_days"]
    sample_180 = baseline_data.get("sample_size_180d", 180)
    dr = baseline_data["date_range"]

    parts = []
    parts.append(f"DỮ LIỆU SINH LÝ HỌC VẬN ĐỘNG VIÊN: {date_vn} ({target_date})")
    parts.append(f"Mẫu dữ liệu Baseline toàn lịch sử: {sample_size} ngày tích lũy ({dr.get('start') or 'N/A'} đến {dr.get('end') or 'N/A'}) | Baseline 180 ngày gần nhất ({sample_180} ngày)\n")

    # Upcoming Race Block
    race_info = get_next_upcoming_race(target_date)
    parts.append("--- SỰ KIỆN THI ĐẤU MỤC TIÊU TIẾP THEO ---")
    if race_info:
        days_left = race_info['days_to_race']
        parts.append(f"- Tên sự kiện: {race_info['name']} ({race_info['distance']})")
        parts.append(f"- Ngày thi đấu: {race_info['date']} (Còn đúng {days_left} ngày)")
        parts.append(f"- Mức độ ưu tiên: Nhóm {race_info['priority']}")
        if 0 <= days_left <= 3:
            w_eff = get_effective_weight_kg(tm)
            parts.append(
                f"- ⚠️ KÍCH HOẠT DĨA ĐỒ ĂN CARBO-LOADING (Còn {days_left} ngày đến Race!): "
                f"TỰ ĐỘNG CHUYỂN CHIẾN LƯỢC SANG CARBO-LOADING PHASE. Nâng Carbohydrate lên 70% tổng năng lượng "
                f"(mục tiêu ~{round(7 * w_eff)}g đến ~{round(10 * w_eff)}g Carb/ngày cho cân nặng {w_eff} kg). "
                f"Cắt giảm chất béo/chất xơ khó tiêu để tối đa hóa lượng Glycogen dự trữ trong cơ bắp & gan."
            )
    else:
        parts.append("Không ghi nhận sự kiện thi đấu sắp tới trong lịch races.json.")
    parts.append("")

    parts.append(f"--- CHỈ SỐ SINH LÝ HÔM NAY VS BASELINE CHUẨN (180 NGÀY GẦN NHẤT & {sample_size} NGÀY LỊCH SỬ) ---")

    # Sleep & HRV
    bs_sleep = bm.get("sleep_score", {})
    b180_sleep = bm_180.get("sleep_score", {})
    parts.append(f"- Sleep Score: Hôm nay = {_format_value(tm.get('sleep_score'))} | Baseline 180d = {b180_sleep.get('avg', 'NULL')} (Std: {b180_sleep.get('std', 'NULL')}) | Baseline All-Time ({sample_size}d) = {bs_sleep.get('avg', 'NULL')}")

    bs_hrv = bm.get("hrv_last_night", {})
    b180_hrv = bm_180.get("hrv_last_night", {})
    parts.append(f"- HRV Overnight (ms): Hôm nay = {_format_value(tm.get('hrv_last_night'), 'ms')} (Status: {tm.get('hrv_status') or 'NULL'}) | Baseline 180d = {b180_hrv.get('avg', 'NULL')} ms (Std: {b180_hrv.get('std', 'NULL')}) | Baseline All-Time ({sample_size}d) = {bs_hrv.get('avg', 'NULL')} ms")

    bs_rhr = bm.get("resting_heart_rate", {})
    b180_rhr = bm_180.get("resting_heart_rate", {})
    parts.append(f"- Resting Heart Rate (bpm): Hôm nay = {_format_value(tm.get('resting_heart_rate'), 'bpm')} | Baseline 180d = {b180_rhr.get('avg', 'NULL')} bpm (Std: {b180_rhr.get('std', 'NULL')}) | Baseline All-Time ({sample_size}d) = {bs_rhr.get('avg', 'NULL')} bpm")

    bs_stress = bm.get("avg_stress_level", {})
    b180_stress = bm_180.get("avg_stress_level", {})
    parts.append(f"- Avg Stress Level: Hôm nay = {_format_value(tm.get('avg_stress_level'))} (Max: {tm.get('max_stress_level') or 'NULL'}) | Baseline 180d = {b180_stress.get('avg', 'NULL')} | Baseline All-Time ({sample_size}d) = {bs_stress.get('avg', 'NULL')}")

    # Respiration & SpO2
    parts.append(f"- Nhịp thở đêm (Respiration): Avg = {_format_value(tm.get('respiration_avg'), 'brpm')}, Min = {_format_value(tm.get('respiration_min'), 'brpm')}, Max = {_format_value(tm.get('respiration_max'), 'brpm')}")
    parts.append(f"- Nồng độ Oxy SpO2 đêm (%): Avg = {_format_value(tm.get('spo2_avg'), '%')}, Min = {_format_value(tm.get('spo2_min'), '%')}")
    spo2_min = tm.get("spo2_min")
    if spo2_min is not None and float(spo2_min) < 85:
        parts.append(
            f"⚠️ QUY TẮC PHÂN TÍCH SPO2 TỤT THẤP (< 85%, THỰC TẾ = {spo2_min}% FOR SECTION 1):\n"
            f"  - TUYỆT ĐỐI KHÔNG khẳng định cứng nhắc đây là 'chắc chắn do lỗi cảm biến' hay 'chắc chắn do bệnh lý đường thở/ngưng thở khi ngủ'.\n"
            f"  - BẮT BUỘC đưa ra đánh giá khách quan dựa trên tương quan dữ liệu: Đối chiếu trực tiếp với nhịp thở trung bình ({tm.get('respiration_avg') or 'N/A'} brpm), độ biến thiên nhịp thở (min: {tm.get('respiration_min') or 'N/A'}, max: {tm.get('respiration_max') or 'N/A'}) và thời gian thức giấc ({_format_seconds(tm.get('awake_duration_seconds'))}) để người dùng tự theo dõi.\n"
            f"  - Cung cấp 2 nhóm lời khuyên thực tế để tự kiểm chứng:\n"
            f"    * Nhóm 1 - Yếu tố Thiết bị & Vị trí đeo: Đeo cách xương cổ tay 1-2 ngón tay; kiểm tra độ ôm sát vừa đủ (quá lỏng gây lọt sáng môi trường làm sai lệch cảm biến quang học PPG; quá chặt gây nghẽn tưới máu mao mạch dưới da); chú ý thói quen kê tay dưới gối hoặc nằm tì đè lên cổ tay khi ngủ.\n"
            f"    * Nhóm 2 - Yếu tố Tư thế & Môi trường hô hấp: Thử nghiệm tư thế nằm nghiêng (side-sleeping) để giữ đường thở thông thoáng tự nhiên; duy trì độ thông khí và độ ẩm phòng ngủ phù hợp; tự quan sát xem sáng dậy có bị khô miệng, đau họng hoặc uể oải không."
        )

    # Body Battery, Recovery & Cardiorespiratory Metrics
    parts.append(f"- Body Battery: Sạc = {_format_value(tm.get('body_battery_charged'))}, Xả = {_format_value(tm.get('body_battery_drained'))}, Cao nhất = {_format_value(tm.get('body_battery_highest'))}, Thấp nhất = {_format_value(tm.get('body_battery_lowest'))}")
    parts.append(f"- Training Readiness Score: {_format_value(tm.get('training_readiness_score'))}/100")
    parts.append(f"- Recovery Time Remaining: {_format_value(tm.get('recovery_time_hours'), 'giờ')}")

    raw_ts = tm.get("training_status")
    ts_display = TRAINING_STATUS_MAP.get(str(raw_ts).upper(), str(raw_ts).replace("_2", "")) if raw_ts else "KHÔNG CÓ DỮ LIỆU (NULL)"
    parts.append(f"- Training Status (Trạng thái tập luyện): {ts_display} (Mã Garmin gốc: {raw_ts or 'NULL'})")

    parts.append(f"- VO2 Max: {_format_value(tm.get('vo2_max'))}")
    parts.append(f"- Độ lệch nhiệt độ da (Skin Temp Deviation): {_format_value(tm.get('skin_temp_deviation'), '°C')}")

    # Body Composition (OMRON VIVA / Garmin)
    w_kg = tm.get("weight_kg")
    fat_p = tm.get("body_fat_pct")
    mus_p = tm.get("muscle_mass_pct")
    vis_f = tm.get("visceral_fat")
    parts.append(f"- Cân nặng & Thể trạng (Body Composition): Cân nặng = {_format_value(w_kg, 'kg')}, % Mỡ = {_format_value(fat_p, '%')}, % Cơ xương = {_format_value(mus_p, '%')}, Mỡ nội tạng = {_format_value(vis_f)}")

    days_left = race_info.get("days_to_race") if race_info else None
    if days_left is not None and days_left <= 10:
        parts.append(
            f"  ⚠️ QUY TẮC PHÂN TÍCH CÂN NẶNG GIAI ĐOẠN TAPERING (Còn {days_left} ngày <= 10 ngày đến Race Day FOR SECTION 1):\n"
            f"  - NGUYÊN TẮC: TUYỆT ĐỐI KHÔNG SIẾT CÂN HAY CẮT GIẢM CALO.\n"
            f"  - Nếu cân nặng dao động 65.0 - 66.5 kg: Đánh giá 'Thể trạng tối ưu, giữ nguyên phong độ' (Dải thi đấu tối ưu 63.5 - 65.5kg).\n"
            f"  - Trong pha Carbo-Loading (<= 3 ngày): Nếu cân nặng tăng nhẹ +0.5 kg đến +1.2 kg (do tích tụ Glycogen giữ 3g nước / 1g glycogen), BẮT BUỘC giải thích rõ: 'Đây là hiện tượng sinh lý tích trữ năng lượng hoàn toàn bình thường và rất tốt, không phải tăng mỡ thừa'."
        )
    else:
        parts.append(
            f"  ⚠️ QUY TẮC PHÂN TÍCH CÂN NẶNG GIAI ĐOẠN HUẤN LƯỢNG THÔNG THƯỜNG / PHỤC HỒI SAU RACE (> 10 ngày hoặc không sát Race FOR SECTION 1):\n"
            f"  - Khuyến nghị hướng tới mốc cân nặng thi đấu tối ưu 63.5 - 64.5 kg, giảm mỡ về dải 14% - 15% để giảm 4.5 - 6.0 kg lực xung kích va đập lên gân Achilles chân trái trong mỗi bước chạy."
        )

    # Active Calories & Steps
    bs_cal = bm.get("active_calories", {})
    b180_cal = bm_180.get("active_calories", {})
    parts.append(f"- Active Calories: Hôm nay = {_format_value(tm.get('active_calories'), 'kcal')} | Baseline 180d = {b180_cal.get('avg', 'NULL')} kcal | Baseline All-Time ({sample_size}d) = {bs_cal.get('avg', 'NULL')} kcal")
    bs_steps = bm.get("total_steps", {})
    b180_steps = bm_180.get("total_steps", {})
    parts.append(f"- Total Steps: Hôm nay = {_format_value(tm.get('total_steps'))} | Baseline 180d = {b180_steps.get('avg', 'NULL')} | Baseline All-Time ({sample_size}d) = {bs_steps.get('avg', 'NULL')}")

    # Sleep Stages & Integrity
    sleep_score = tm.get("sleep_score")
    sleep_dur = tm.get("sleep_duration_seconds")
    is_incomplete = (sleep_score is None) or (sleep_dur is None) or (float(sleep_dur) < 10800) or bool(tm.get("is_incomplete_sleep"))

    parts.append("\n--- BÓC TÁCH CẤU TRÚC GIẤC NGỦ HÔM NAY ---")
    if is_incomplete:
        parts.append("⚠️ TRẠNG THÁI TOÀN VẸN DỮ LIỆU GIẤC NGỦ (INCOMPLETE / LATE WAKE-UP):")
        parts.append("- Dữ liệu sleep_score bị rỗng (NULL) hoặc thời gian ngủ chưa được chốt xong (vẫn đang ngủ hoặc dậy muộn hơn 04:45).")
        parts.append("- BẮT BUỘC in câu cảnh báo trong Mục 2: '⚠️ Lưu ý: Giấc ngủ chưa kết thúc hoặc chưa đồng bộ trọn vẹn từ đồng hồ. Dữ liệu dưới đây mang tính chất tạm thời.'")
        parts.append("- BẮT BUỘC bổ sung lời nhắc: 'Sau khi thức dậy và cân Omron xong, hãy gửi lệnh /report vào đây để nhận báo cáo hoàn chỉnh cập nhật.'")

    parts.append(f"- Tổng thời gian ngủ: {_format_seconds(tm.get('sleep_duration_seconds'))}")
    parts.append(f"- Thức giấc trong đêm (Awake): {_format_seconds(tm.get('awake_duration_seconds'))}")
    parts.append(f"- Ngủ sâu (Deep Sleep): {_format_seconds(tm.get('deep_sleep_seconds'))}")
    parts.append(f"- Ngủ mơ (REM Sleep): {_format_seconds(tm.get('rem_sleep_seconds'))}")
    parts.append(f"- Ngủ nông (Light Sleep): {_format_seconds(tm.get('light_sleep_seconds'))}")

    # Sleep Norms Benchmark Table Data Pre-calculation
    sleep_dur_val = float(sleep_dur) if sleep_dur is not None else 0.0
    deep_sec_val = float(tm.get("deep_sleep_seconds") or 0.0)
    rem_sec_val = float(tm.get("rem_sleep_seconds") or 0.0)
    light_sec_val = float(tm.get("light_sleep_seconds") or 0.0)
    awake_sec_val = float(tm.get("awake_duration_seconds") or 0.0)

    deep_m = round(deep_sec_val / 60.0, 1) if sleep_dur_val > 0 else 0.0
    deep_pct = round((deep_sec_val / sleep_dur_val) * 100.0, 1) if sleep_dur_val > 0 else 0.0
    rem_m = round(rem_sec_val / 60.0, 1) if sleep_dur_val > 0 else 0.0
    rem_pct = round((rem_sec_val / sleep_dur_val) * 100.0, 1) if sleep_dur_val > 0 else 0.0
    light_m = round(light_sec_val / 60.0, 1) if sleep_dur_val > 0 else 0.0
    light_pct = round((light_sec_val / sleep_dur_val) * 100.0, 1) if sleep_dur_val > 0 else 0.0
    awake_m = round(awake_sec_val / 60.0, 1) if sleep_dur_val > 0 else 0.0
    awake_pct = round((awake_sec_val / sleep_dur_val) * 100.0, 1) if sleep_dur_val > 0 else 0.0

    b180_deep_sec = bm_180.get("deep_sleep_seconds", {}).get("avg") or bm.get("deep_sleep_seconds", {}).get("avg")
    b180_rem_sec = bm_180.get("rem_sleep_seconds", {}).get("avg") or bm.get("rem_sleep_seconds", {}).get("avg")
    b180_light_sec = bm_180.get("light_sleep_seconds", {}).get("avg") or bm.get("light_sleep_seconds", {}).get("avg")
    b180_awake_sec = bm_180.get("awake_duration_seconds", {}).get("avg") or bm.get("awake_duration_seconds", {}).get("avg")
    b180_dur_sec = bm_180.get("sleep_duration_seconds", {}).get("avg") or bm.get("sleep_duration_seconds", {}).get("avg")

    base_dur = float(b180_dur_sec) if b180_dur_sec else (sleep_dur_val if sleep_dur_val > 0 else 25200.0)

    deep_base_val = float(b180_deep_sec) if b180_deep_sec is not None else base_dur * 0.18
    rem_base_val = float(b180_rem_sec) if b180_rem_sec is not None else base_dur * 0.22
    light_base_val = float(b180_light_sec) if b180_light_sec is not None else base_dur * 0.55
    awake_base_val = float(b180_awake_sec) if b180_awake_sec is not None else base_dur * 0.05

    b180_deep_str = f"{round(deep_base_val/60.0, 1)}m ({round((deep_base_val/base_dur)*100.0, 1)}%)"
    b180_rem_str = f"{round(rem_base_val/60.0, 1)}m ({round((rem_base_val/base_dur)*100.0, 1)}%)"
    b180_light_str = f"{round(light_base_val/60.0, 1)}m ({round((light_base_val/base_dur)*100.0, 1)}%)"
    b180_awake_str = f"{round(awake_base_val/60.0, 1)}m ({round((awake_base_val/base_dur)*100.0, 1)}%)"

    parts.append(
        f"\n📊 DỮ LIỆU TÍNH TOÁN BẢNG ĐỐI CHUẨN GIẤC NGỦ (SLEEP NORMS BENCHMARK FOR SECTION 2):\n"
        f"- Deep Sleep Đêm qua: {deep_m} phút ({deep_pct}%) | Baseline 180d: {b180_deep_str} | Chuẩn Y học Thể thao: 15% - 25%\n"
        f"- REM Sleep Đêm qua: {rem_m} phút ({rem_pct}%) | Baseline 180d: {b180_rem_str} | Chuẩn Y học Thể thao: 20% - 25%\n"
        f"- Light Sleep Đêm qua: {light_m} phút ({light_pct}%) | Baseline 180d: {b180_light_str} | Chuẩn Y học Thể thao: 50% - 60%\n"
        f"- Awake Đêm qua: {awake_m} phút ({awake_pct}%) | Baseline 180d: {b180_awake_str} | Chuẩn Y học Thể thao: < 5%\n"
        f"⚠️ YÊU CẦU BẮT BUỘC TRONG MỤC 2:\n"
        f"1. Phải xuất Bảng Markdown 'Sleep Norms Benchmark' theo đúng 5 cột: | Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 180d | Chuẩn Y học Thể thao | Đánh giá |\n"
        f"2. BẮT BUỘC sử dụng các con số Baseline 180d đã tính toán ở trên ({b180_deep_str}, {b180_rem_str}, v.v.), THAY THẾ TRIỆT ĐỂ CHỮ N/A trong bảng đối chuẩn!\n"
        f"3. BẮT BUỘC phân tích và nhận định rõ xem đêm qua có phải là đêm 'Siêu phục hồi' (Supercompensation) bù đắp cho sự thiếu hụt các ngày trước hay không."
    )

    # Emergency Recovery Protocol Trigger Check (Sleep < 5h or Body Battery < 30)
    sleep_dur_sec = tm.get("sleep_duration_seconds")
    bb_highest = tm.get("body_battery_highest")
    is_emergency_recovery = False
    em_reasons = []

    if sleep_dur_sec is not None and 0 < float(sleep_dur_sec) < 18000:
        is_emergency_recovery = True
        h_sleep = round(float(sleep_dur_sec) / 3600.0, 1)
        em_reasons.append(f"Thời gian ngủ < 5 tiếng (thực tế = {h_sleep}h)")

    if bb_highest is not None and float(bb_highest) < 30:
        is_emergency_recovery = True
        em_reasons.append(f"Body Battery cao nhất < 30 (thực tế = {bb_highest})")

    if is_emergency_recovery:
        parts.append(
            f"\n🚨 TỰ ĐỘNG KÍCH HOẠT EMERGENCY RECOVERY PROTOCOL (CẤP CỨU THỂ TRẠNG):\n"
            f"- Lý do kích hoạt: {', '.join(em_reasons)}.\n"
            f"- AI BẮT BUỘC kê đơn Emergency Recovery Protocol trong các Mục 2, 3, 4:\n"
            f"  1. Kê đơn giấc ngủ ngắn ban ngày: Power Nap 20 phút (hoặc chu kỳ 90 phút trước 14:30).\n"
            f"  2. Cấm tuyệt đối chất kích thích/caffeine sau 12:00 trưa.\n"
            f"  3. Bổ sung bữa phụ giàu Carb giải phóng chậm + Tryptophan lúc 20:00 (chuối chín + hạt hạnh nhân hoặc sữa ấm) để ổn định đường huyết, dập tắt Cortisol ban đêm."
        )

    # Activities & 7-Day Training Load
    parts.append("\n--- HOẠT ĐỘNG THỂ THAO HÔM NAY ---")
    act_summary_raw = tm.get("activities_summary")
    if act_summary_raw:
        try:
            acts = json.loads(act_summary_raw)
            if isinstance(acts, list) and acts:
                for idx, act in enumerate(acts, 1):
                    dur_sec = act.get('duration_seconds')
                    dur_str = _format_seconds(dur_sec)
                    dist_m = act.get('distance_meters')
                    dist_str = f"{round(dist_m/1000, 2)} km" if dist_m else "N/A"

                    act_info = (
                        f"{idx}. {act.get('name') or act.get('type')} (Loại: {act.get('type') or 'N/A'}): "
                        f"Thời gian = {dur_str}, Cự ly = {dist_str}, Calo = {act.get('calories') or 'N/A'} kcal, "
                        f"Avg HR = {act.get('avg_hr') or 'N/A'} bpm, Max HR = {act.get('max_hr') or 'N/A'} bpm"
                    )
                    if act.get('aerobic_training_effect') is not None:
                        act_info += f", Aerobic TE = {act.get('aerobic_training_effect')}"
                    if act.get('anaerobic_training_effect') is not None:
                        act_info += f", Anaerobic TE = {act.get('anaerobic_training_effect')}"
                    if act.get('activity_training_load') is not None:
                        act_info += f", Activity Load = {act.get('activity_training_load')}"
                    
                    cad = act.get('avg_cadence')
                    if cad is not None:
                        try:
                            cad_val = float(cad)
                            if cad_val > 0:
                                if cad_val < 120:
                                    spm_2x = int(round(cad_val * 2))
                                    act_info += f", Cadence = {cad_val} spm (Đi bộ / Dữ liệu 1 chân -> SPM chuẩn x2 = {spm_2x} spm)"
                                else:
                                    act_info += f", Cadence = {int(round(cad_val))} spm"
                        except Exception:
                            act_info += f", Cadence = {cad} spm"

                    if act.get('gct_balance'):
                        act_info += f", GCT Balance (L/R) = {act.get('gct_balance')}"
                    parts.append(act_info)
            else:
                parts.append("Không ghi nhận bài tập thể thao nào hôm nay (Rest Day).")
        except Exception:
            parts.append("Không ghi nhận bài tập thể thao nào hôm nay (Rest Day).")
    else:
        parts.append("Không ghi nhận bài tập thể thao nào hôm nay (Rest Day).")

    # Yesterday's Completed Activities Block
    try:
        from datetime import timedelta
        dt_target = datetime.strptime(target_date, "%Y-%m-%d").date()
        prev_date_str = (dt_target - timedelta(days=1)).strftime("%Y-%m-%d")
        
        from src.db.connection import get_db_connection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT activities_summary FROM daily_metrics WHERE date = ?", (prev_date_str,))
            row = cursor.fetchone()
            prev_act_raw = row[0] if row else None
    except Exception:
        prev_date_str = "Hôm qua"
        prev_act_raw = None

    parts.append(f"\n--- HOẠT ĐỘNG THỂ THAO ĐÃ THỰC HIỆN HÔM QUA ({prev_date_str}) ---")
    if prev_act_raw:
        try:
            prev_acts = json.loads(prev_act_raw)
            if isinstance(prev_acts, list) and prev_acts:
                for idx, act in enumerate(prev_acts, 1):
                    dur_sec = act.get('duration_seconds')
                    dur_str = _format_seconds(dur_sec)
                    dur_min = round(float(dur_sec)/60.0, 1) if dur_sec else "N/A"
                    dist_m = act.get('distance_meters')
                    dist_str = f"{round(dist_m/1000, 2)} km" if dist_m else "N/A"

                    # Calculate pace
                    pace_str = "N/A"
                    if dist_m and dur_sec and dist_m > 0:
                        act_type_lower = str(act.get("type") or act.get("name") or "").lower()
                        if "swim" in act_type_lower:
                            pace_sec_100m = (dur_sec / dist_m) * 100.0
                            p_min = int(pace_sec_100m // 60)
                            p_sec = int(round(pace_sec_100m % 60))
                            pace_str = f"{p_min}:{p_sec:02d} /100m"
                        else:
                            pace_sec_km = dur_sec / (dist_m / 1000.0)
                            p_min = int(pace_sec_km // 60)
                            p_sec = int(round(pace_sec_km % 60))
                            pace_str = f"{p_min}:{p_sec:02d} /km"

                    act_info = (
                        f"{idx}. {act.get('name') or act.get('type')} (Loại: {act.get('type') or 'N/A'}):\n"
                        f"   - Cự ly: {dist_str} | Thời gian: {dur_str} ({dur_min} phút) | Pace TB: {pace_str}\n"
                        f"   - Nhịp tim: Avg = {act.get('avg_hr') or 'N/A'} bpm, Max = {act.get('max_hr') or 'N/A'} bpm | Calo tiêu hao: {act.get('calories') or 'N/A'} kcal"
                    )
                    if act.get('aerobic_training_effect') is not None or act.get('activity_training_load') is not None:
                        act_info += f"\n   - Tải tập luyện: Aerobic TE = {act.get('aerobic_training_effect') or 'N/A'}, Activity Load = {act.get('activity_training_load') or 'N/A'}"
                    
                    cad = act.get('avg_cadence')
                    gct = act.get('gct_balance')
                    stride = act.get('stride_length_cm')
                    vert_osc = act.get('vertical_oscillation_cm')

                    if cad or gct or stride or vert_osc:
                        gct_str = f"{gct}% L / {round(100.0 - float(gct), 1)}% R" if isinstance(gct, (int, float)) else (gct or 'N/A')
                        cad_str = "N/A"
                        if cad is not None:
                            try:
                                cad_val = float(cad)
                                if cad_val > 0:
                                    if cad_val < 120:
                                        spm_2x = int(round(cad_val * 2))
                                        cad_str = f"{cad_val} spm (Đi bộ / Dữ liệu 1 chân -> SPM chuẩn x2 = {spm_2x} spm)"
                                    else:
                                        cad_str = f"{int(round(cad_val))} spm"
                            except Exception:
                                cad_str = str(cad)

                        act_info += (
                            f"\n   - Động học HRM-Pro: Cadence = {cad_str} | GCT Balance (L/R) = {gct_str} | "
                            f"Stride Length = {stride or 'N/A'} cm | Vertical Oscillation = {vert_osc or 'N/A'} cm"
                        )
                    parts.append(act_info)
            else:
                parts.append(f"Không ghi nhận bài tập thể thao nào ngày hôm qua ({prev_date_str}).")
        except Exception:
            parts.append(f"Không ghi nhận bài tập thể thao nào ngày hôm qua ({prev_date_str}).")
    else:
        parts.append(f"Không ghi nhận bài tập thể thao nào ngày hôm qua ({prev_date_str}).")

    # Embed 602-run cadence sweet spot finding & Cross-training 2 Options
    readiness_score = tm.get("training_readiness_score")
    parts.append(
        f"\n💡 QUY TẮC KÊ ĐƠN VẬN ĐỘNG ĐA MÔN LỰA CHỌN 1 & 2 (DÙNG CHO MỤC 3):\n"
        f"- Điểm Training Readiness hiện tại: {_format_value(readiness_score)}/100.\n"
        f"- BẮT BUỘC duy trì Cadence 178 - 182 spm để đưa GCT Balance từ 51.7% L về mốc an toàn 50.3% L (giảm xung kích va đập cơ học lên gân Achilles chân trái).\n"
        f"- Khi Readiness > 70 ở tuần Tapering: TUYỆT ĐỐI KHÔNG khuyến nghị Sprint 100% all-out (Giải thích rõ: Tránh rách/viêm cấp gân Achilles trái khi GCT Balance còn lệch 51.7% L).\n"
        f"- BẮT BUỘC luôn cung cấp 2 LỰA CHỌN LINH HOẠT trong Mục 3:\n"
        f"  + LỰA CHỌN 1 (Chạy bộ - Neuromuscular Priming): Chạy nhẹ MAF 25-30 phút (<136 bpm) + 4-5 tổ Strides 80m (tăng tốc kỹ thuật 85-90% sức, Cadence ép đúng 180-184 spm, KHÔNG bứt tốc all-out).\n"
        f"  + LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực): Bơi sải thả lỏng 800m - 1.000m (Zone 1/2), xen kẽ 3-4 đoạn 25m guồng tay nhanh. Triệt tiêu 90% áp lực trọng lực lên gân gót chân trái. Cảnh báo không đạp chân ếch mạnh."
    )

    bb_highest = tm.get("body_battery_highest") or tm.get("body_battery_charged")
    if (bb_highest is not None and float(bb_highest) >= 90) and (readiness_score is not None and float(readiness_score) >= 75):
        days_left = race_info.get("days_to_race") if race_info else None
        if days_left is not None and days_left <= 3:
            weather_instruction = (
                f"  2. Chuẩn bị thích nghi thời tiết sát ngày Race (Còn {days_left} ngày <= 3 ngày): "
                f"Chặng đua xuất phát lúc 04:00 sáng với độ ẩm cao (>85%), "
                f"nhắc nhở duy trì thói quen uống nước khoáng kiềm Fujiwa rải đều và bù đủ điện giải (Natri) nhằm tối ưu hóa cơ chế giải nhiệt của cơ thể."
            )
        else:
            weather_instruction = (
                f"  2. Quy tắc thời tiết xa ngày Race (Còn {days_left if days_left is not None else 'N/A'} ngày > 3 ngày): "
                f"TUYỆT ĐỐI KHÔNG tự bịa nhiệt độ hay độ ẩm tương lai. BẮT BUỘC ghi đúng câu: "
                f"'Thời tiết thực tế ngày thi đấu sẽ được hệ thống theo dõi và cập nhật sát ngày (từ T-3 ngày). Hiện tại VĐV chỉ cần duy trì đủ lượng nước và điện giải nền tảng.'"
            )

        parts.append(
            f"\n🧠 CẢNH BÁO TÂM LÝ TẬP LUYỆN & THÍCH NGHI THỜI TIẾT (MENTAL & RACE ADAPTATION FOR SECTION 3):\n"
            f"- Thể trạng tích lũy cao: Body Battery cao nhất = {bb_highest}, Training Readiness = {readiness_score}/100 ở tuần Tapering.\n"
            f"- AI BẮT BUỘC bổ sung 2 chỉ dẫn quan trọng trong Mục 3:\n"
            f"  1. Cảnh báo hiện tượng 'Bứt rứt Tapering (Taper Madness)': Năng lượng tích lũy đạt đỉnh rất dễ sinh tâm lý hưng phấn muốn chạy thử tốc độ cao. Cần duy trì kỷ luật 'ghìm cương', tuân thủ cự ly ngắn và nhịp tim nhẹ để giữ điểm rơi phong độ cho ngày thi đấu.\n"
            f"{weather_instruction}"
        )

    parts.append(f"\n- Tổng Tải Vận Động 7 Ngày (Training Load 7D): {tl.get('total_active_calories', 0)} kcal, {tl.get('total_steps', 0)} bước, {tl.get('total_workout_count', 0)} bài tập ({_format_seconds(tl.get('total_duration_seconds'))})")

    # 1. Yesterday's Nutrition Logs Block (For Section 2 Sleep Evaluation)
    try:
        from src.db.nutrition_repository import get_nutrition_logs_by_date
        nut_logs_prev = get_nutrition_logs_by_date(prev_date_str)
    except Exception:
        nut_logs_prev = []

    parts.append(f"\n--- NHẬT KÝ DINH DƯỠNG HÔM QUA ({prev_date_str}) ---")
    tot_cal_prev = 0
    meal_h_float = None
    last_meal_time = "N/A"
    hours_diff_str = ""

    if nut_logs_prev:
        tot_cal_prev = sum(log.get("total_calories") or 0 for log in nut_logs_prev)
        tot_p_prev = round(sum(log.get("protein_g") or 0 for log in nut_logs_prev), 1)
        tot_c_prev = round(sum(log.get("carb_g") or 0 for log in nut_logs_prev), 1)
        tot_f_prev = round(sum(log.get("fat_g") or 0 for log in nut_logs_prev), 1)

        for idx, log in enumerate(nut_logs_prev, 1):
            dishes_list = log.get("dishes") or []
            dishes_str = ", ".join(dishes_list) if isinstance(dishes_list, list) else str(dishes_list)
            parts.append(
                f"{idx}. [{log.get('meal_type') or 'Bữa ăn'}] Lúc {log.get('timestamp') or 'N/A'}:\n"
                f"   - Món ăn/mồi nhậu: {dishes_str}\n"
                f"   - Calo & Macros: ~{log.get('total_calories') or 0} kcal | Protein: {log.get('protein_g') or 0}g | Carb: {log.get('carb_g') or 0}g | Fat: {log.get('fat_g') or 0}g\n"
                f"   - Đơn vị cồn: {log.get('alcohol_units') or 0.0} đơn vị ({log.get('alcohol_description') or 'Không ghi nhận'})\n"
                f"   - Đánh giá rủi ro: {log.get('sleep_risk_assessment') or 'Không có'}"
            )

        # Check timestamp of last meal of yesterday
        last_log = nut_logs_prev[-1]
        ts_str = last_log.get("timestamp") or ""
        if ts_str and " " in ts_str:
            try:
                time_part = ts_str.split(" ")[1]
                h, m = map(int, time_part.split(":")[:2])
                last_meal_time = f"{h:02d}:{m:02d}"
                meal_h_float = h + m / 60.0
                bed_h_float = 21.5  # 21:30
                if meal_h_float <= bed_h_float:
                    diff_h = round(bed_h_float - meal_h_float, 1)
                    hours_diff_str = f"cách giờ đi ngủ (21:30) khoảng {diff_h} tiếng"
                else:
                    hours_diff_str = "kết thúc SAU giờ đi ngủ (21:30)"
            except Exception:
                pass

        parts.append(
            f"\nTỔNG HỢP DINH DƯỠNG HÔM QUA ({prev_date_str}):\n"
            f"- Tổng Calo nạp: ~{tot_cal_prev} kcal | Protein: {tot_p_prev}g | Carb: {tot_c_prev}g | Fat: {tot_f_prev}g\n"
            f"- Bữa ăn cuối cùng ngày hôm qua ({prev_date_str}): Lúc {last_meal_time} ({hours_diff_str}).\n"
            f"⚠️ QUY TẮC BẮT BUỘC: CHỈ dùng các bữa ăn HÔM QUA ({prev_date_str}) ở khối này để đối chiếu với RHR đêm và chất lượng giấc ngủ trong Mục 2!"
        )
        if tot_cal_prev < 800:
            parts.append(
                f"⚠️ NGHIÊM CẤM SUY DIỄN VÕ ĐOÁN KHI THIẾU LOG DINH DƯỠNG (< 800 KCAL):\n"
                f"Tổng calo ghi nhận hôm qua chỉ có ~{tot_cal_prev} kcal (< 800 kcal).\n"
                f"1. AI BẮT BUỘC ghi rõ trong Mục 2: '⚠️ Dữ liệu dinh dưỡng hôm qua chưa được ghi nhận đầy đủ (Incomplete Log)' do VĐV chưa nhập hết tất cả các bữa ăn.\n"
                f"2. TUYỆT ĐỐI KHÔNG ĐƯỢC suy diễn rằng VĐV nhịn ăn hoặc hệ tiêu hóa trống rỗng để giải thích cho RHR thấp hay giấc ngủ sâu!\n"
                f"3. Hãy phân tích sinh lý học giấc ngủ ĐỘC LẬP với dinh dưỡng khi dữ liệu bị khuyết."
            )
    else:
        parts.append(
            f"Không ghi nhận bản ghi bữa ăn/đồ nhậu nào trong ngày hôm qua ({prev_date_str}).\n"
            f"⚠️ CHỈ DẪN AI: Phân tích sinh lý học giấc ngủ ĐỘC LẬP với dinh dưỡng khi không có log dinh dưỡng."
        )

    # Check Nocturnal Hypoglycemia Causal Risk (Yesterday Calo < 1,600 kcal OR Last Meal > 7h before sleep)
    is_hypo_risk = False
    hypo_reasons = []

    if nut_logs_prev and tot_cal_prev > 0 and tot_cal_prev < 1600:
        is_hypo_risk = True
        hypo_reasons.append(f"Tổng calo ngày hôm trước thâm hụt sâu (< 1,600 kcal, thực tế = {tot_cal_prev} kcal)")

    if meal_h_float is not None:
        hours_before_sleep = 21.5 - meal_h_float
        if hours_before_sleep > 7.0:
            is_hypo_risk = True
            hypo_reasons.append(f"Bữa ăn cuối cùng lúc {last_meal_time} quá xa (> 7 tiếng trước khi ngủ 21:30)")

    if is_hypo_risk:
        parts.append(
            f"\n⚠️ CẢNH BÁO PHÂN TÍCH NHÂN QUẢ DINH DƯỠNG THIẾU HỤT & STRESS ĐÊM:\n"
            f"- Nguyên nhân: {', '.join(hypo_reasons)}.\n"
            f"- AI BẮT BUỘC phải cảnh báo nguy cơ: 'Hạ đường huyết ban đêm (Nocturnal Hypoglycemia) kích hoạt Cortisol/Adrenaline, gây tăng RHR đêm, tụt dốc HRV và thức giấc sớm'.\n"
            f"- TUYỆT ĐỐI KHÔNG được đánh giá 'dạ dày trống rỗng là tốt' khi tổng năng lượng nạp trong ngày bị thiếu hụt trầm trọng."
        )

    # 2. Today's Nutrition Logs Block (For Section 4 Macro & Dinner Prescription)
    try:
        from src.db.nutrition_repository import get_nutrition_logs_by_date
        nut_logs_today = get_nutrition_logs_by_date(target_date)
    except Exception:
        nut_logs_today = []

    now_dt = datetime.now()
    current_time_str = now_dt.strftime("%H:%M")

    parts.append(f"\n--- NHẬT KÝ DINH DƯỠNG ĐÃ NẠP HÔM NAY ({target_date}) ---")
    parts.append(f"⏰ MỐC THỜI GIAN THỰC TẾ HÔM NAY KHI LẬP BÁO CÁO: {current_time_str}")
    w_eff = get_effective_weight_kg(tm)
    bmr_est = round(10 * w_eff + 6.25 * 168 - 5 * 44 + 5)

    # Active calories today from Garmin / activity data
    daily_data = baseline_data.get("daily_data", {})
    act_cals_today = 0
    if daily_data and isinstance(daily_data.get("activities"), list):
        act_cals_today = sum(a.get("calories") or 0 for a in daily_data["activities"])
    if not act_cals_today:
        act_cals_today = float(tm.get("active_calories") or tm.get("active_kilocalories") or 0)

    days_left = race_info.get("days_to_race") if race_info else None

    if days_left is not None and 1 <= days_left <= 3:
        day_type_str = f"Carbo-Loading Day (T-{days_left})"
        target_cal = 2500  # 2,400 - 2,600 kcal
    elif act_cals_today > 300:
        day_type_str = f"Hard Workout Day (Garmin Active Burn: {int(act_cals_today)} kcal)"
        target_cal = round(bmr_est + act_cals_today + 500)
    else:
        day_type_str = "Rest Day / Active Recovery Day"
        target_cal = round(bmr_est + 550)  # ~2,100 - 2,200 kcal

    target_p = round(1.9 * w_eff, 1)  # 1.8 - 2.0 g/kg (~120g - 130g Protein)
    target_f = round(0.9 * w_eff, 1)  # 0.8 - 1.0 g/kg (~50g - 65g Fat)
    target_c = round(max(0, target_cal - (target_p * 4 + target_f * 9)) / 4.0, 1)

    if nut_logs_today:
        tot_cal_today = sum(log.get("total_calories") or 0 for log in nut_logs_today)
        tot_p_today = round(sum(log.get("protein_g") or 0 for log in nut_logs_today), 1)
        tot_c_today = round(sum(log.get("carb_g") or 0 for log in nut_logs_today), 1)
        tot_f_today = round(sum(log.get("fat_g") or 0 for log in nut_logs_today), 1)

        for idx, log in enumerate(nut_logs_today, 1):
            dishes_list = log.get("dishes") or []
            dishes_str = ", ".join(dishes_list) if isinstance(dishes_list, list) else str(dishes_list)
            parts.append(
                f"{idx}. [{log.get('meal_type') or 'Bữa ăn'}] Lúc {log.get('timestamp') or 'N/A'}:\n"
                f"   - Món ăn: {dishes_str}\n"
                f"   - Calo & Macros: ~{log.get('total_calories') or 0} kcal | Protein: {log.get('protein_g') or 0}g | Carb: {log.get('carb_g') or 0}g | Fat: {log.get('fat_g') or 0}g"
            )

        rem_cal = max(0, target_cal - tot_cal_today)
        rem_p = max(0.0, round(target_p - tot_p_today, 1))

        parts.append(
            f"\nTỔNG HỢP DINH DƯỠNG ĐÃ NẠP HÔM NAY ({target_date}) [{day_type_str}]:\n"
            f"- Cân nặng thực tế: {w_eff} kg -> BMR cơ bản ~{bmr_est} kcal\n"
            f"- Đã nạp: ~{tot_cal_today} kcal / Mục tiêu ~{target_cal} kcal (Còn thiếu cho hôm nay: ~{rem_cal} kcal)\n"
            f"- Protein đã nạp: {tot_p_today}g / Mục tiêu ~{target_p}g (Còn thiếu cho hôm nay: ~{rem_p}g Protein)\n"
            f"- Carb đã nạp: {tot_c_today}g / Mục tiêu ~{target_c}g | Fat đã nạp: {tot_f_today}g / Mục tiêu ~{target_f}g\n"
            f"⚠️ QUY TẮC BẮT BUỘC ĐỘNG HÓA THỜI GIAN CHO MỤC 4 (KÊ ĐƠN DINH DƯỠNG VÀ TOÁN HỌC MACRO):\n"
            f"1. Mốc thời gian thực tế hiện tại là {current_time_str}. Chỉ kê đơn chi tiết các bữa ăn BẮT ĐẦU TỪ {current_time_str} TRỞ ĐI trong ngày. Tuyệt đối KHÔNG kê đơn các bữa ăn ở mốc giờ đã trôi qua.\n"
            f"2. BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC: Phép tính bù trừ: {target_cal} kcal (Mục tiêu) - {tot_cal_today} kcal (Đã nạp) = {rem_cal} kcal (Còn thiếu); {target_p}g Protein (Mục tiêu) - {tot_p_today}g (Đã nạp) = {rem_p}g Protein (Còn thiếu). Kê đơn các bữa ăn còn lại sao cho tổng Calo và Protein từ thực đơn gợi ý BẮT BUỘC cộng lại vừa đúng bằng {rem_cal} kcal và {rem_p}g Protein, không được tính nhẩm sai lệch!\n"
            f"3. TÍNH KHẢ THI BỮA TỐI: Khi gợi ý các bữa ăn có thời gian chế biến/dùng bữa kéo dài (như Lẩu hoặc tiệc tối gia đình): BẮT BUỘC bổ sung lưu ý thực tế: 'Nếu chọn ăn lẩu, nên bắt đầu sớm (trước 17:45) để kịp kết thúc trước 18:45, đảm bảo hệ tiêu hóa có ít nhất 2.5 - 3 tiếng hoàn tất chu trình trước giờ ngủ 21:30'."
        )
    else:
        parts.append(
            f"Chưa ghi nhận bản ghi bữa ăn nào trong ngày hôm nay ({target_date}).\n"
            f"Cân nặng thực tế: {w_eff} kg -> BMR cơ bản ~{bmr_est} kcal | Loai ngày: {day_type_str}.\n"
            f"Mục tiêu cả ngày hôm nay: ~{target_p}g Protein (1.8-2.0g/kg), ~{target_f}g Fat (0.8-1.0g/kg), ~{target_c}g Carb, tổng ~{target_cal} kcal.\n"
            f"⚠️ QUY TẮC BẮT BUỘC ĐỘNG HÓA THỜI GIAN CHO MỤC 4: Mốc thời gian hiện tại là {current_time_str}. Chỉ kê đơn các bữa ăn từ {current_time_str} trở đi trong ngày, không ghi mốc giờ đã trôi qua!\n"
            f"⚠️ BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC: Tổng Calo và Protein từ các món gợi ý BẮT BUỘC phải khớp chính xác với mục tiêu ~{target_cal} kcal và ~{target_p}g Protein.\n"
            f"⚠️ TÍNH KHẢ THI BỮA TỐI: Khi gợi ý các bữa ăn có thời gian chế biến/dùng bữa kéo dài (như Lẩu hoặc tiệc tối gia đình): BẮT BUỘC bổ sung lưu ý thực tế: 'Nếu chọn ăn lẩu, nên bắt đầu sớm (trước 17:45) để kịp kết thúc trước 18:45, đảm bảo hệ tiêu hóa có ít nhất 2.5 - 3 tiếng hoàn tất chu trình trước giờ ngủ 21:30'."
        )


    # Adaptive Memory Block
    adaptive_mem = baseline_data.get("adaptive_memory", {})
    memory_text = adaptive_mem.get("memory_text") if isinstance(adaptive_mem, dict) else None
    if memory_text:
        parts.append(f"\n{memory_text}")

    parts.append("\nHãy phân tích chuyên sâu và kê đơn Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện theo đúng định dạng được yêu cầu.")
    return "\n".join(parts)

def clean_report_text(text: str) -> str:
    """Post-processing cleaner to eliminate Chinese token bleed / localization artifacts."""
    if not text:
        return ""
    replacements = {
        "指数": "Chỉ số",
        "恢复": "Phục hồi",
        "睡眠": "Giấc ngủ",
        "压力": "Stress",
        "心率": "Nhịp tim",
    }
    for zh, vi in replacements.items():
        text = text.replace(zh, vi)
    return text

def generate_executive_brief(baseline_data: Dict[str, Any]) -> str:
    """Generate a clean, concise Executive Brief (<12 lines) for Telegram morning delivery."""
    target_date = baseline_data.get("target_date", "")
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data.get("target_metrics", {})
    bm = baseline_data.get("metrics_baseline", {})
    race_info = baseline_data.get("race_info")

    hrv_today = tm.get("hrv_last_night")
    hrv_str = f"{hrv_today} ms" if hrv_today is not None else "N/A"
    hrv_bs = bm.get("hrv_last_night", {}).get("avg")
    
    if hrv_today is not None and hrv_bs and hrv_bs > 0:
        pct_diff = round(((hrv_today - hrv_bs) / hrv_bs) * 100, 1)
        diff_str = f"+{pct_diff}% vs Baseline" if pct_diff >= 0 else f"{pct_diff}% vs Baseline"
    else:
        diff_str = "vs Baseline N/A"

    rhr_today = tm.get("resting_heart_rate")
    rhr_str = f"{rhr_today} bpm" if rhr_today is not None else "N/A"

    sleep_score = tm.get("sleep_score")
    deep_sec = tm.get("deep_sleep_seconds")
    deep_str = _format_seconds(deep_sec)
    sleep_dur = tm.get("sleep_duration_seconds")
    is_incomplete = (sleep_score is None) or (sleep_dur is None) or (float(sleep_dur) < 10800) or bool(tm.get("is_incomplete_sleep"))

    bb_charged = tm.get("body_battery_charged") or "N/A"
    bb_highest = tm.get("body_battery_highest")
    ts_raw = tm.get("training_status")
    ts_display = TRAINING_STATUS_MAP.get(str(ts_raw).upper(), "Phục hồi (Recovery)") if ts_raw else "Phục hồi (Recovery)"

    w_kg = tm.get("weight_kg") or 64.9
    protein_target = round(1.8 * float(w_kg), 1)

    # Check emergency recovery condition for brief
    is_emergency = False
    if sleep_dur is not None and 0 < float(sleep_dur) < 18000:
        is_emergency = True
    if bb_highest is not None and float(bb_highest) < 30:
        is_emergency = True

    # Workout Prescription & Race info
    if race_info and isinstance(race_info, dict):
        days_left = race_info.get("days_to_race")
        if days_left is not None and 0 <= days_left <= 3:
            race_str = f"• {race_info.get('name')} ({race_info.get('distance')}): Còn {days_left} ngày (🔥 CHẾ ĐỘ CARBO-LOADING 70% CARBS)"
        else:
            race_str = f"• {race_info.get('name')} ({race_info.get('distance')}): Còn {days_left} ngày (Giai đoạn Tapering)"
    else:
        race_str = "• Chưa ghi nhận giải đấu trong lịch races.json."

    if race_info and isinstance(race_info, dict) and race_info.get("days_to_race") is not None and 0 <= race_info.get("days_to_race") <= 3:
        carb_target = round(8.0 * float(w_kg))
        nut_str = f"• 🔥 Carbo-Loading 70% Carbs (~{carb_target}g Carb) | Target Protein: {protein_target}g | Nước kiềm Fujiwa: 3.0L"
    else:
        nut_str = f"• Target Protein: {protein_target}g | Calo ước tính: ~2,100 kcal | Nước kiềm Fujiwa: 3.0L"

    if is_incomplete:
        sleep_line = "• ⚠️ Giấc ngủ chưa chốt xong / Dậy muộn. Cân Omron xong gửi /report để cập nhật."
    elif is_emergency:
        sleep_line = f"• 🚨 EMERGENCY RECOVERY PROTOCOL: Power Nap 20m trước 14:30 | Cấm caffeine sau 12:00 | Bữa phụ 20:00 (chuối + hạnh nhân/sữa ấm)"
    else:
        sleep_line = f"• Sleep Score: {sleep_score}/100 | Ngủ sâu (Deep Sleep): {deep_str} | Sạc Body Battery: +{bb_charged}"

    brief_lines = [
        f"⚡ EXECUTIVE BRIEF PHỤC HỒI & TẢI VẬN ĐỘNG",
        f"📅 {date_vn}\n",
        f"🏃‍♂️ Sinh lý & Phục hồi Đêm qua:",
        f"• HRV Overnight: {hrv_str} ({diff_str}, {tm.get('hrv_status') or 'BALANCED'}) | RHR: {rhr_str} | Stress: {tm.get('avg_stress_level') or 'N/A'}",
        f"{sleep_line}\n",
        f"🎯 Đếm ngược Giải đấu:",
        f"{race_str}\n",
        f"🏋️ Kê đơn Vận động Hôm nay:",
        f"• Trạng thái {ts_display}: MAF Zone 2 nhẹ nhàng (HR < 136 bpm, Cadence 178-182 spm) hoặc Bơi lội phục hồi. Chiều giãn cơ.\n",
        f"🍱 Precision Nutrition (Cân nặng {w_kg} kg):",
        f"{nut_str}\n",
        f"👇 Bấm nút bên dưới để mở toàn văn phân tích 4 mục đầy đủ!"
    ]
    return clean_report_text("\n".join(brief_lines))

def split_report_into_sections(report_markdown: str) -> List[str]:
    """Split a full markdown report into 4 distinct Message Card strings for Telegram delivery."""
    if not report_markdown:
        return []

    text = clean_report_text(report_markdown.strip())

    # 1. Try splitting by explicit delimiter ===SECTION_BREAK===
    if "===SECTION_BREAK===" in text:
        raw_parts = [p.strip() for p in text.split("===SECTION_BREAK===") if p.strip()]
        if len(raw_parts) >= 5 and raw_parts[0].startswith("# "):
            raw_parts[1] = f"{raw_parts[0]}\n\n{raw_parts[1]}"
            raw_parts = raw_parts[1:]
        if len(raw_parts) >= 4:
            return raw_parts[:4]

    # 2. Try splitting by section headers (### 🧠 1., ### 💤 2., ### 🏃‍♂️ 3., ### 🍱 4.)
    lines = text.splitlines()
    cards = []
    current_card = []

    for line in lines:
        stripped = line.strip()
        if stripped == "===SECTION_BREAK===":
            if current_card:
                cards.append("\n".join(current_card).strip())
                current_card = []
            continue

        if stripped.startswith("### ") and current_card:
            cards.append("\n".join(current_card).strip())
            current_card = [line]
        else:
            current_card.append(line)

    if current_card:
        cards.append("\n".join(current_card).strip())

    cleaned = [c.strip() for c in cards if c.strip()]
    if len(cleaned) >= 5 and cleaned[0].startswith("# "):
        cleaned[1] = f"{cleaned[0]}\n\n{cleaned[1]}"
        cleaned = cleaned[1:]

    if len(cleaned) >= 4:
        return cleaned[:4]

    return [text]



