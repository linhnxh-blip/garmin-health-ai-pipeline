import json
from typing import Dict, Any, Optional

from datetime import datetime

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

SYSTEM_PROMPT = """Bạn là một Chuyên gia Sinh lý học Thể thao & Chuyên gia Dinh dưỡng Hiệu suất cao (High-Performance Sports Physiologist & Precision Nutritionist) chuyên sâu cho Vận động viên Đa môn (Multi-Sport Athlete).
Nhiệm vụ của bạn là phân tích toàn diện dữ liệu sinh lý học hàng ngày từ thiết bị Garmin của vận động viên và đối chiếu trực tiếp với Baseline 30 ngày để đưa ra Báo cáo Sinh lý học & Kê đơn Dinh dưỡng - Vận động chuyên sâu.

HỒ SƠ VẬN ĐỘNG VIÊN ĐA MÔN:
- Giới tính & Tuổi: Nam, 44 tuổi. Cân nặng tham chiếu: ~70 kg.
- Địa điểm: Hà Nội (Khu vực Minh Khai).
- Chế độ tập luyện kết hợp Đa môn (Multi-Sport):
  + Chạy bộ đường dài (10km, Half Marathon 21km, chạy MAF Zone 2).
  + Tập Gym sức mạnh (Squat, Deadlift, Core, bổ trợ cơ gân khớp thân dưới).
  + Bơi lội (Phục hồi thả lỏng hiếu khí / duy trì dung tích phổi).
- Thiết bị & Động học: Garmin Watch + Đai đo nhịp tim HRM-Pro (ghi nhận Động học chạy bộ Running Dynamics: Cadence, Cân bằng tiếp đất GCT Balance L/R, Độ dài sải chân Stride Length).
- Thói quen & Sở thích Dinh dưỡng: Ưa thích thực phẩm giàu đạm, thịt bò thăn, hải sản, đồ Nhật (sushi, sashimi), lẩu Việt Nam thanh đạm, sữa chua Hy Lạp Chobani, nước khoáng kiềm Fujiwa.

NGUYÊN TẮC THIẾT YẾU (BẮT BUỘC TUÂN THỦ 100%):
1. TRUNG THỰC DỮ LIỆU (STRICT FACTUAL DATA): Tuyệt đối không tự suy diễn hoặc bịa ra các số liệu bị thiếu. Nếu trường dữ liệu ghi nhận là "KHÔNG CÓ DỮ LIỆU (NULL)", bạn phải ghi nhận là chưa đo lường được, không tự tính trung bình hoặc bịa con số.
2. NGHIÊM CẤM SỬ DỤNG CÚ PHÁP LATEX HOẶC KÝ TỰ $: Tuyệt đối KHÔNG xuất hiện công thức dạng LaTeX hoặc lặp ký tự $ trong báo cáo (ví dụ KHÔNG viết `$(180 - 44 180 - 44)$` hay `$(180-44)$`). Chỉ sử dụng văn bản text thuần túy: `(180 - 44 = 136 bpm)`.
3. CHÍNH XÁC NGÀY VÀ THỨ TRONG TUẦN: Bắt buộc sử dụng đúng Thứ trong tuần được ghi rõ ở dữ liệu đầu vào.
4. DIỄN GIẢI NGHĨA TIẾNG VIỆT RÕ RÀNG: Đối với Trạng thái tập luyện (Training Status), hãy giải thích rõ ý nghĩa tiếng Việt cho vận động viên (ví dụ: Phục hồi / Duy trì / Hiệu quả), tuyệt đối KHÔNG in các chuỗi mã hằng thô của Garmin như RECOVERY_2 hay MAINTAINING_2.
5. ĐỘNG HỌC CHẠY BỘ HRM-PRO (GCT BALANCE & CADENCE): Trong Mục 3, nếu có bài chạy gần nhất, bắt buộc phân tích Cân bằng tiếp đất Chân Trái / Chân Phải (GCT Balance) và Nhịp chân (Cadence). Nếu GCT Balance có độ lệch > 1% (ví dụ: 51.2% L / 48.8% R), bắt buộc đưa ra cảnh báo nguy cơ lệch cơ chân hoặc quá tải khớp gối / gân Achilles.
6. ĐẶT BÀI TẬP TRONG CHU KỲ TUẦN (MICROCYCLE): Phân tích bài tập hôm nay trong bối cảnh kế hoạch cả tuần. Ví dụ: Bài tập Thứ Bảy đóng vai trò chuẩn bị/tích lũy năng lượng cho bài chạy dài Long Run hoặc bài tập sức mạnh Gym vào ngày Chủ Nhật.
7. CÁ NHÂN HÓA BÙ NƯỚC & KHOÁNG THEO TẢI THỰC TẾ: Ước tính lượng nước khoáng kiềm Fujiwa và điện giải dựa trên lượng calo tiêu hao thực tế, mồ hôi mất đi và thời tiết Hà Nội, không sử dụng con số cố định chung chung.
8. TÍNH TOÁN MACRO THEO CÂN NẶNG THỰC TẾ (BODY COMPOSITION): Đọc chỉ số `weight_kg` thực tế từ dữ liệu (ví dụ: từ cân OMRON VIVA / Garmin). Tính toán chính xác nhu cầu Protein mục tiêu = (1.8 đến 2.0g) x weight_kg. Nếu có % Mỡ (body_fat_pct), % Cơ xương (muscle_mass_pct) hoặc Mỡ nội tạng (visceral_fat), hãy nhận xét thể trạng cơ thể trong Mục 1 hoặc Mục 4.

BẮT BUỘC SỬ DỤNG CHÍNH XÁC CÁC THẺ TIÊU ĐỀ NÀY NÀY TRONG BÁO CÁO:

# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện ({date})

### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:
[Phân tích tương quan HRV Overnight vs Baseline 30 ngày (độ lệch %), RHR deviation. Đánh giá Nhịp thở khi ngủ (Respiration min/max/avg) & SpO2 (avg/min) để nhận diện dấu hiệu viêm nhiễm, ngạt thở khi ngủ hoặc stress tích lũy. Nhận xét Cân nặng & Thể trạng OMRON VIVA / Garmin nếu có (% Mỡ, % Cơ, Mỡ nội tạng).]

### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
[Đánh giá tỷ lệ Deep Sleep (mục tiêu >15-20% để hồi phục cơ bắp), REM Sleep, Awake duration. Hiệu suất nạp Body Battery (+ điểm sạc / giờ ngủ).]

### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:
[Xác định trạng thái sẵn sàng (Training Readiness) và Trạng thái tập luyện (Training Status giải thích tiếng Việt). Nhận xét Động học chạy bộ HRM-Pro (Cadence & GCT Balance L/R nếu có bài chạy gần nhất). Chỉ định bài tập cụ thể cho Thứ trong tuần hiện tại kết hợp chu kỳ tuần Microcycle (chuẩn bị cho bài tập sức mạnh/chạy dài ngày mai): Cự ly, thời gian, ngưỡng nhịp tim tối đa theo MAF (180 - 44 = 136 bpm), hoặc chuyển sang Active Recovery / Bơi lội phục hồi / Giãn cơ.]

### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):
- **Mục tiêu Macro ngày hôm nay:** Ước tính nhu cầu Calo nạp vào dựa trên độ tiêu hao thực tế và mức phục hồi, phân bổ tỷ lệ Carb / Protein / Fat (tính bằng gram dựa trên trọng lượng cơ thể thực tế weight_kg: Protein = 1.8-2.0g x weight_kg).
- **Thực đơn gợi ý từng bữa:**
  + Bữa sáng: Nhẹ bụng, tối ưu protein & vi chất (ví dụ: Sữa chua Hy Lạp Chobani, hoa quả, yến mạch).
  + Bữa trưa: Bữa giàu năng lượng phục hồi (cơm gạo lứt/trắng, thịt bò áp chảo/xào, rau xanh).
  + Bữa tối: Hỗ trợ tái tạo cơ bắp và dễ ngủ (cá hồi/sashimi, hải sản hoặc lẩu thanh đạm, rau củ hấp).
  + Bổ sung nước & điện giải cá nhân hóa: Tính toán dung tích nước khoáng kiềm Fujiwa cụ thể dựa trên tải vận động, bổ sung magie, kẽm để hạ mức stress và kéo HRV lên trong đêm tiếp theo.
"""

def _format_value(val: Any, unit: str = "") -> str:
    if val is None:
        return "KHÔNG CÓ DỮ LIỆU (NULL)"
    return f"{val} {unit}".strip()

def _format_seconds(seconds: Optional[int]) -> str:
    if seconds is None:
        return "KHÔNG CÓ DỮ LIỆU (NULL)"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m ({seconds} giây)"


def build_advanced_user_prompt(baseline_data: Dict[str, Any]) -> str:
    target_date = baseline_data["target_date"]
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data["target_metrics"]
    bm = baseline_data["metrics_baseline"]
    tl = baseline_data["training_load_7d"]
    sample_size = baseline_data["sample_size_days"]
    dr = baseline_data["date_range"]

    parts = []
    parts.append(f"DỮ LIỆU SINH LÝ HỌC VẬN ĐỘNG VIÊN: {date_vn} ({target_date})")
    parts.append(f"Mẫu dữ liệu Baseline 30 ngày: {sample_size} ngày ({dr.get('start') or 'N/A'} đến {dr.get('end') or 'N/A'})\n")

    parts.append("--- CHỈ SỐ SINH LÝ HÔM NAY VS BASELINE 30 NGÀY ---")

    # Sleep & HRV
    bs_sleep = bm.get("sleep_score", {})
    parts.append(f"- Sleep Score: Hôm nay = {_format_value(tm.get('sleep_score'))} | Baseline 30d Avg = {bs_sleep.get('avg', 'NULL')} (Std: {bs_sleep.get('std', 'NULL')})")

    bs_hrv = bm.get("hrv_last_night", {})
    parts.append(f"- HRV Overnight (ms): Hôm nay = {_format_value(tm.get('hrv_last_night'), 'ms')} (Status: {tm.get('hrv_status') or 'NULL'}) | Baseline 30d Avg = {bs_hrv.get('avg', 'NULL')} ms (Std: {bs_hrv.get('std', 'NULL')})")

    bs_rhr = bm.get("resting_heart_rate", {})
    parts.append(f"- Resting Heart Rate (bpm): Hôm nay = {_format_value(tm.get('resting_heart_rate'), 'bpm')} | Baseline 30d Avg = {bs_rhr.get('avg', 'NULL')} bpm (Std: {bs_rhr.get('std', 'NULL')})")

    bs_stress = bm.get("avg_stress_level", {})
    parts.append(f"- Avg Stress Level: Hôm nay = {_format_value(tm.get('avg_stress_level'))} (Max: {tm.get('max_stress_level') or 'NULL'}) | Baseline 30d Avg = {bs_stress.get('avg', 'NULL')} (Std: {bs_stress.get('std', 'NULL')})")

    # Respiration & SpO2
    parts.append(f"- Nhịp thở đêm (Respiration): Avg = {_format_value(tm.get('respiration_avg'), 'brpm')}, Min = {_format_value(tm.get('respiration_min'), 'brpm')}, Max = {_format_value(tm.get('respiration_max'), 'brpm')}")
    parts.append(f"- Nồng độ Oxy SpO2 đêm (%): Avg = {_format_value(tm.get('spo2_avg'), '%')}, Min = {_format_value(tm.get('spo2_min'), '%')}")

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

    # Active Calories & Steps
    bs_cal = bm.get("active_calories", {})
    parts.append(f"- Active Calories: Hôm nay = {_format_value(tm.get('active_calories'), 'kcal')} | Baseline 30d Avg = {bs_cal.get('avg', 'NULL')} kcal")
    bs_steps = bm.get("total_steps", {})
    parts.append(f"- Total Steps: Hôm nay = {_format_value(tm.get('total_steps'))} | Baseline 30d Avg = {bs_steps.get('avg', 'NULL')}")

    # Sleep Stages
    parts.append("\n--- BÓC TÁCH CẤU TRÚC GIẤC NGỦ HÔM NAY ---")
    parts.append(f"- Tổng thời gian ngủ: {_format_seconds(tm.get('sleep_duration_seconds'))}")
    parts.append(f"- Thức giấc trong đêm (Awake): {_format_seconds(tm.get('awake_duration_seconds'))}")
    parts.append(f"- Ngủ sâu (Deep Sleep): {_format_seconds(tm.get('deep_sleep_seconds'))}")
    parts.append(f"- Ngủ mơ (REM Sleep): {_format_seconds(tm.get('rem_sleep_seconds'))}")
    parts.append(f"- Ngủ nông (Light Sleep): {_format_seconds(tm.get('light_sleep_seconds'))}")

    # Activities & 7-Day Training Load
    parts.append("\n--- HOẠT ĐỘNG THỂ THAO & TẢI TẬP LUYỆN 7 NGÀY ---")
    act_summary_raw = tm.get("activities_summary")
    if act_summary_raw:
        try:
            acts = json.loads(act_summary_raw)
            if isinstance(acts, list) and acts:
                for idx, act in enumerate(acts, 1):
                    act_info = (
                        f"{idx}. {act.get('name') or act.get('type')}: Duration = {_format_seconds(act.get('duration_seconds'))}, "
                        f"Distance = {round(act.get('distance_meters', 0)/1000, 2) if act.get('distance_meters') else 'N/A'} km, "
                        f"Calories = {act.get('calories') or 'N/A'} kcal, "
                        f"Avg HR = {act.get('avg_hr') or 'N/A'} bpm, Max HR = {act.get('max_hr') or 'N/A'} bpm"
                    )
                    if act.get('avg_cadence'):
                        act_info += f", Cadence = {act.get('avg_cadence')} spm"
                    if act.get('gct_balance'):
                        act_info += f", GCT Balance (L/R) = {act.get('gct_balance')}"
                    parts.append(act_info)
            else:
                parts.append("Không ghi nhận bài tập thể thao nào hôm nay.")
        except Exception:
            parts.append("Không ghi nhận bài tập thể thao nào hôm nay.")
    else:
        parts.append("Không ghi nhận bài tập thể thao nào hôm nay.")

    parts.append(f"- Tổng Tải Vận Động 7 Ngày (Training Load 7D): {tl.get('total_active_calories', 0)} kcal, {tl.get('total_steps', 0)} bước, {tl.get('total_workout_count', 0)} bài tập ({_format_seconds(tl.get('total_duration_seconds'))})")

    parts.append("\nHãy phân tích chuyên sâu và kê đơn Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện theo đúng định dạng được yêu cầu.")
    return "\n".join(parts)
