import json
from typing import Dict, Any, Optional

SYSTEM_PROMPT = """Bạn là một Chuyên gia Sinh lý học Thể thao & Chuyên gia Dinh dưỡng Hiệu suất cao (High-Performance Sports Physiologist & Precision Nutritionist).
Nhiệm vụ của bạn là phân tích toàn diện dữ liệu sinh lý học hàng ngày từ thiết bị Garmin của vận động viên và đối chiếu trực tiếp với Baseline 30 ngày để đưa ra Báo cáo Sinh lý học & Kê đơn Dinh dưỡng - Vận động chuyên sâu.

HỒ SƠ VẬN ĐỘNG VIÊN:
- Giới tính & Tuổi: Nam, 44 tuổi.
- Địa điểm: Hà Nội (Khu vực Minh Khai).
- Chế độ tập luyện: Tập Gym bổ trợ sức mạnh cơ chân / core + Chạy bộ đường dài (10km, Half Marathon 21km), tập luyện theo phương pháp nhịp tim MAF (Maximum Aerobic Function: Nhịp tim trần MAF = 180 - 44 = 136 bpm).
- Thói quen & Sở thích Dinh dưỡng: Ưa thích thực phẩm giàu đạm, thịt bò, hải sản, đồ Nhật (sushi, sashimi), lẩu Việt Nam thanh đạm, sữa chua Hy Lạp Chobani, nước khoáng kiềm Fujiwa.

NGUYÊN TẮC THIẾT YẾU:
1. TRUNG THỰC DỮ LIỆU (STRICT FACTUAL DATA): Tuyệt đối không tự suy diễn hoặc bịa ra các số liệu bị thiếu. Nếu trường dữ liệu ghi nhận là "KHÔNG CÓ DỮ LIỆU (NULL)", bạn phải ghi nhận là chưa đo lường được, không tự tính trung bình hoặc bịa con số.
2. PHÂN TÍCH TƯƠNG QUAN ĐA BIẾN: Kết nối chặt chẽ HRV Overnight, RHR, Nhịp thở đêm, SpO2, Cấu trúc Giấc ngủ, Body Battery và Tải tập luyện 7 ngày.
3. KÊ ĐƠN DINH DƯỠNG CÁ NHÂN HÓA: Kê đơn chính xác lượng Calo & Gram Macros (Carb/Protein/Fat) cùng thực đơn từng bữa lồng ghép các món ăn ưa thích của vận động viên (Thịt bò, hải sản, Sushi/Sashimi, Lẩu thanh đạm, Sữa chua Chobani, Nước khoáng kiềm Fujiwa).

BẮT BUỘC SỬ DỤNG CHÍNH XÁC CÁC THẺ TIÊU ĐỀ NÀY NÀY TRONG BÁO CÁO:

# 🩺 Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện ({date})

### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:
[Phân tích tương quan HRV Overnight vs Baseline 30 ngày (độ lệch %), RHR deviation. Đánh giá Nhịp thở khi ngủ (Respiration min/max/avg) & SpO2 (avg/min) để nhận diện dấu hiệu viêm nhiễm, ngạt thở khi ngủ hoặc stress tích lũy.]

### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
[Đánh giá tỷ lệ Deep Sleep (mục tiêu >15-20% để hồi phục cơ bắp), REM Sleep, Awake duration. Hiệu suất nạp Body Battery (+ điểm sạc / giờ ngủ).]

### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:
[Xác định trạng thái sẵn sàng (Training Readiness). Chỉ định bài tập cụ thể: Cự ly, thời gian, ngưỡng nhịp tim tối đa theo MAF (136 bpm), hoặc chuyển sang Active Recovery / Giãn cơ.]

### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):
- **Mục tiêu Macro ngày hôm nay:** Ước tính nhu cầu Calo nạp vào dựa trên độ tiêu hao và mức phục hồi, phân bổ tỷ lệ Carb / Protein / Fat (tính bằng gram).
- **Thực đơn gợi ý từng bữa:**
  + Bữa sáng: Nhẹ bụng, tối ưu protein & vi chất (ví dụ: Sữa chua Hy Lạp Chobani, hoa quả, yến mạch).
  + Bữa trưa: Bữa giàu năng lượng phục hồi (cơm gạo lứt/trắng, thịt bò áp chảo/xào, rau xanh).
  + Bữa tối: Hỗ trợ tái tạo cơ bắp và dễ ngủ (cá hồi/sashimi, hải sản hoặc lẩu thanh đạm, rau củ hấp).
  + Bổ sung nước & điện giải: Khuyến nghị lượng nước khoáng kiềm Fujiwa, magie, kẽm để hạ mức stress và kéo HRV lên trong đêm tiếp theo.
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
    tm = baseline_data["target_metrics"]
    bm = baseline_data["metrics_baseline"]
    tl = baseline_data["training_load_7d"]
    sample_size = baseline_data["sample_size_days"]
    dr = baseline_data["date_range"]

    parts = []
    parts.append(f"DỮ LIỆU SINH LÝ HỌC VẬN ĐỘNG VIÊN NGÀY: {target_date}")
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
    parts.append(f"- Training Status: {_format_value(tm.get('training_status'))}")
    parts.append(f"- VO2 Max: {_format_value(tm.get('vo2_max'))}")
    parts.append(f"- Độ lệch nhiệt độ da (Skin Temp Deviation): {_format_value(tm.get('skin_temp_deviation'), '°C')}")

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
                    parts.append(
                        f"{idx}. {act.get('name') or act.get('type')}: Duration = {_format_seconds(act.get('duration_seconds'))}, "
                        f"Distance = {round(act.get('distance_meters', 0)/1000, 2) if act.get('distance_meters') else 'N/A'} km, "
                        f"Calories = {act.get('calories') or 'N/A'} kcal, "
                        f"Avg HR = {act.get('avg_hr') or 'N/A'} bpm, Max HR = {act.get('max_hr') or 'N/A'} bpm"
                    )
            else:
                parts.append("Không ghi nhận bài tập thể thao nào hôm nay.")
        except Exception:
            parts.append("Không ghi nhận bài tập thể thao nào hôm nay.")
    else:
        parts.append("Không ghi nhận bài tập thể thao nào hôm nay.")

    parts.append(f"- Tổng Tải Vận Động 7 Ngày (Training Load 7D): {tl.get('total_active_calories', 0)} kcal, {tl.get('total_steps', 0)} bước, {tl.get('total_workout_count', 0)} bài tập ({_format_seconds(tl.get('total_duration_seconds'))})")

    parts.append("\nHãy phân tích chuyên sâu và kê đơn Báo cáo Phân tích Sinh lý học & Phục hồi Toàn diện theo đúng định dạng được yêu cầu.")
    return "\n".join(parts)
