import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
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


def get_latest_blood_summary(db_path: Optional[Union[str, Path]] = None) -> str:
    """Fetch latest blood test date and all 14 core biochemical markers to produce a detailed sports medicine markdown prompt summary according to ADA, AHA, EULAR, ACSM standards."""
    try:
        from src.db.connection import get_db_connection
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT test_date, facility FROM blood_tests ORDER BY test_date DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return "--- CHỈ SỐ XÉT NGHIỆM MÁU: Chưa có bản ghi xét nghiệm máu trong cơ sở dữ liệu."

            latest_date, facility = row[0], row[1]

            cursor.execute(
                """
                SELECT marker_name, value, value_text, unit, ref_min, ref_max, status
                FROM blood_tests
                WHERE test_date = ?
                """,
                (latest_date,)
            )
            records = {r[0]: dict(zip(["marker_name", "value", "value_text", "unit", "ref_min", "ref_max", "status"], r)) for r in cursor.fetchall()}

        if not records:
            return f"--- CHỈ SỐ XÉT NGHIỆM MÁU ({latest_date}): Không tìm thấy chỉ số."

        def fmt(mk, default_unit="", note=""):
            rec = records.get(mk)
            if not rec or rec["value"] is None:
                return "N/A"
            v = rec["value"]
            st_flag = " 🔻LOW" if rec["status"] == "LOW" else (" 🔺HIGH" if rec["status"] == "HIGH" else "")
            u = rec["unit"] or default_unit
            res_str = f"{rec['value_text']} {u}{st_flag}".strip()
            if note:
                res_str += f" [{note}]"
            return res_str

        # Format 14 Core Markers
        hgb = fmt("HGB", "g/dL", "Chuẩn 14-16 g/dL")
        hct = fmt("HCT", "%", "Độ nhớt tối ưu 40-46%")
        rbc = fmt("RBC", "T/L", "Chuẩn 4.2-6.0 T/L")

        glu_v = records.get("GLUCOSE", {}).get("value")
        glu_note = "Tiền tiểu đường ADA > 5.6" if (glu_v and glu_v > 5.6) else "OK"
        glu = fmt("GLUCOSE", "mmol/L", glu_note)

        hba1c_v = records.get("HBA1C", {}).get("value")
        hba1c_note = "Tiền tiểu đường ADA > 5.7%" if (hba1c_v and hba1c_v > 5.7) else "OK"
        hba1c = fmt("HBA1C", "%", hba1c_note)

        trig_v = records.get("TRIGLYCERIDE", {}).get("value")
        trig_note = "AHA High > 1.70" if (trig_v and trig_v > 1.70) else "OK"
        trig = fmt("TRIGLYCERIDE", "mmol/L", trig_note)

        chol = fmt("CHOLESTEROL", "mmol/L", "Chuẩn < 5.2")
        ldl = fmt("LDL_C", "mmol/L", "ACSM Tối ưu < 2.6")
        hdl = fmt("HDL_C", "mmol/L", "AHA Tối ưu > 1.2")

        uric_v = records.get("URIC_ACID", {}).get("value")
        uric_note = "EULAR Bão hòa dịch khớp > 420" if (uric_v and uric_v > 420) else "OK"
        uric = fmt("URIC_ACID", "umol/L", uric_note)

        creat = fmt("CREATININE", "umol/L", "Chuẩn 60-110")
        ast = fmt("AST", "U/L", "EASL < 35")
        alt = fmt("ALT", "U/L", "EASL < 35")

        wbc_v = records.get("WBC", {}).get("value")
        wbc_note = "Bạch cầu nền thấp < 4.0 G/L" if (wbc_v and wbc_v < 4.0) else "OK"
        wbc = fmt("WBC", "G/L", wbc_note)

        # TG/HDL Ratio
        hdl_v = records.get("HDL_C", {}).get("value")
        tg_hdl_str = "N/A"
        if trig_v and hdl_v and hdl_v > 0:
            ratio_val = round(trig_v / hdl_v, 2)
            ratio_flag = " [CẢNH BÁO KHÁNG INSULIN > 1.3]" if ratio_val > 1.3 else " [TỐI ƯU]"
            tg_hdl_str = f"{ratio_val}{ratio_flag}"

        lines = [
            f"--- BỘ 14 CHỈ SỐ XÉT NGHIỆM MÁU CỐT LÕI GẦN NHẤT ({latest_date} tại {facility}) ---",
            f"1. Huyết học & Oxy hóa: HGB = {hgb} | HCT = {hct} | RBC = {rbc}",
            f"2. Đường huyết & Chuyển hóa (Chuẩn ADA): Glucose = {glu} | HbA1c = {hba1c}",
            f"3. Lipid & Tim mạch (Chuẩn AHA/ACSM): Triglyceride = {trig} | Tỷ lệ TG/HDL-C = {tg_hdl_str} | Cholesterol = {chol} | LDL-C = {ldl} | HDL-C = {hdl}",
            f"4. Thận & Dịch khớp (Chuẩn EULAR): Uric Acid = {uric} | Creatinine = {creat}",
            f"5. Gan & Vi tổn thương cơ (Chuẩn EASL): AST = {ast} | ALT = {alt}",
            f"6. Miễn dịch & Tải thần kinh (Chuẩn ACSM): WBC = {wbc}",
        ]

        trend_notes = []
        if uric_v and float(uric_v) > 420:
            trend_notes.append("Uric Acid sát trần bão hòa EULAR (442 µmol/L > 420 µmol/L)")
        if wbc_v and float(wbc_v) < 4.0:
            trend_notes.append("WBC ở mức nền thấp (<4.0 G/L)")
        if (glu_v and float(glu_v) > 5.6) or (trig_v and float(trig_v) > 1.70):
            trend_notes.append("Glucose/Triglyceride nhẹ (định hướng tinh bột kháng)")

        if trend_notes:
            lines.append("📌 THÔNG TIN THAM CHIẾU SINH HÓA NỀN (ÁP DỤNG QUY TẮC KÍCH HOẠT CÓ ĐIỀU KIỆN EVENT-DRIVEN): " + " | ".join(trend_notes))

        return "\n".join(lines)
    except Exception as e:
        return f"--- CHỈ SỐ XÉT NGHIỆM MÁU: (Lỗi truy vấn: {e})"


def get_system_prompt(report_type: str = "morning", date_vn: str = "", weight_kg: str = "") -> str:
    r_type = (report_type or "morning").lower()

    base_expert_header = f"""Bạn là một Chuyên gia Y học Thể thao & Hiệu suất Vận động viên Đa môn (Multi-Sport Performance Physiologist & Sports Medicine Specialist) chuẩn quốc tế (ADA, AHA, EULAR, ACSM).
Nhiệm vụ của bạn là phân tích dữ liệu sinh lý học hàng ngày từ thiết bị Garmin của vận động viên và đối chiếu trực tiếp với Baseline để đưa ra Báo cáo Sinh lý học & Kê đơn Dinh dưỡng - Vận động chuyên sâu.

YÊU CẦU NGUYÊN TẮC QUAN TRỌNG VỀ ĐỘ SÂU PHÂN TÍCH:
- TRẢ VỀ BÁO CÁO ĐẦY ĐỦ VÀ CHUYÊN SÂU CHI TIẾT: Tuyệt đối KHÔNG tóm tắt, KHÔNG rút gọn cụt ngủn. Phân tích chi tiết cơ chế sinh lý học, nguyên nhân và hệ quả đối với thể trạng vận động viên.
- TRUNG THỰC DỮ LIỆU (STRICT FACTUAL DATA): Tuyệt đối không tự suy diễn hoặc bịa ra các số liệu bị thiếu. Nếu trường dữ liệu ghi nhận là "KHÔNG CÓ DỮ LIỆU (NULL)", bạn phải ghi nhận là chưa đo lường được.
- NGÔN NGỮ VÀ THUẬT NGỮ CHUẨN MỰC: BẮT BUỘC: Toàn bộ báo cáo phải được viết thuần túy bằng tiếng Việt y khoa chuẩn mực. Tuyệt đối KHÔNG sử dụng các ký tự chữ Hán/tiếng Trung. Dùng đúng thuật ngữ "Chỉ số HRV".
- NGHIÊM CẤM SỬ DỤNG CÚ PHÁP LATEX HOẶC KÝ TỰ $: Tuyệt đối KHÔNG xuất hiện công thức dạng LaTeX hoặc lặp ký tự $ trong báo cáo (ví dụ KHÔNG viết `$(180 - 44)$`). Chỉ sử dụng văn bản text thuần túy: `(180 - 44 = 136 bpm)`.

HỒ SƠ VẬN ĐỘNG VIÊN ĐA MÔN:
- Giới tính & Tuổi: Nam, 44 tuổi (sinh 1982), thi đấu cự ly mục tiêu Full Marathon (FM 42.195 km).
- Cân nặng thực tế: {weight_kg} kg (Dải cân nặng thi đấu tối ưu (Optimal Race Weight): 63.5 kg - 65.5 kg). Body Fat mục tiêu: 14% - 16%.
- Lịch trình sinh học cố định: Thức dậy 04:30 sáng, Đi ngủ 21:30 tối.
- Thiết bị & Động học: Garmin Watch + Đai đo nhịp tim HRM-Pro (Cadence, GCT Balance L/R, Stride Length).
- Thói quen Dinh dưỡng: Ưa thích thịt bò thăn, hải sản, đồ Nhật, sữa chua Hy Lạp Chobani, nước khoáng kiềm Fujiwa.

=== QUY TẮC CƠ SINH HỌC & LÂM SÀNG BẮT BUỘC (BIOMECHANICAL GUARDRAILS - CHỐNG SUY DIỄN MÁY MÓC) ===

[RULE 1: THỨ BẬC ƯU TIÊN VẬN ĐỘNG TRONG GIAI ĐOẠN TAPERING (T-7 ĐẾN RACE DAY)]
- ƯU TIÊN SỐ 1: Nhịp tim & Mức độ mệt mỏi tim mạch (Cardiovascular Load). Mọi bài chạy nhẹ/tapering bắt buộc giữ ở Zone 2 / MAF (HR < 136 - 140 bpm). Bất kể guồng chân hay pace thế nào, nếu HR vượt Zone 2 thì phải ưu tiên chạy chậm lại hoặc đi bộ.
- ƯU TIÊN SỐ 2: Độ tươi xốp của cơ bắp (Muscle Freshness). Không tạo tải mới khi Training Readiness < 40.
- ƯU TIÊN SỐ 3: Động học chạy bộ (Cadence & GCT Balance) CHỈ LÀ THỨ YẾU.

[RULE 2: NGUYÊN TẮC BÙ TRỪ SẢI CHÂN (STRIDE COMPENSATION LAW)]
- Khi nhắc tới việc tăng Cadence (guồng chân 178 - 182 spm), BẮT BUỘC PHẢI ĐI KÈM HƯỚNG DẪN THU NGẮN SẢI CHÂN (bước nhỏ, lướt sát đất).
- TUYỆT ĐỐI KHÔNG khuyến nghị tăng Cadence đơn lẻ mà không nhắc thu ngắn sải chân, vì sẽ làm tăng tốc độ và vọt nhịp tim.
- Nếu vận động viên cảm thấy tăng Cadence làm tim đập nhanh và mệt mỏi: Cho phép chạy ở Cadence tự nhiên thoải mái, ưu tiên tuyệt đối nhịp tim Zone 2.

[RULE 3: CẤM CAN THIỆP THAY ĐỔI KỸ THUẬT SÁT GIẢI ĐẤU (DAYS_TO_RACE <= 7)]
- Trong vòng 7 ngày trước ngày Race (days_to_race <= 7): TUYỆT ĐỐI CẤM yêu cầu vận động viên gò ép đổi dáng chạy hoặc nâng cao cadence trên đường chạy.
- Để bảo vệ gân Achilles trái giai đoạn này: CHỈ dùng các biện pháp ngoài đường chạy:
  + Bài tập hạ gót thụ động (Eccentric Heel Drops) 3 set x 10-12 lần sau bài tập.
  + Giải phóng cơ mông nhỡ chân phải (Foam Roller).
  + Bổ sung 300-400mg Magie Bisglycinate trước khi ngủ.

[RULE 4: NHẤT QUÁN ĐÁNH GIÁ GIỮA CÁC BÁO CÁO (NO CONTRADICTION & CONSISTENCY)]
- Nếu bài tập sáng có nhịp tim quá cao (Zone 3/4, HR >= 145-150 bpm) làm tụt Readiness, thì trong toàn bộ các báo cáo (Midday & Evening) tuyệt đối KHÔNG ĐƯỢC mâu thuẫn gọi đó là "bài chạy phục hồi" (Recovery Run). Phải thống nhất đánh giá đó là bài tập tải cao gây mệt mỏi tim mạch.
- Báo cáo Evening tuyệt đối KHÔNG phân tích lại chi tiết động học chạy sáng (Cadence, GCT balance), chỉ tóm tắt tổng bước chân và active calories cả ngày.

[RULE 5: TRUNG THỰC CON SỐ BƯỚC CHÂN & CALO TIÊU HOA (STRICT ACCURACY FOR STEPS & CALORIES)]
- BẮT BUỘC sử dụng chính xác con số Total Steps và Active Calories từ dữ liệu Garmin trong ngày được cung cấp trong Prompt.
- Tuyệt đối KHÔNG tự bịa ra/suy diễn con số bước chân khác (ví dụ: không được tự bịa 12.770 bước khi Garmin đo 9.848 bước).
- Tuyệt đối KHÔNG lấy calo của riêng bài chạy sáng (ví dụ 406 kcal) để thay thế cho tổng Active Calories tích lũy cả ngày (636 kcal).

[RULE 6: ĐÁNH GIÁ DINH DƯỠNG NĂNG LƯỢNG KHÁCH QUAN & KẾT HỢP BỐI CẢNH (OBJECTIVE NUTRITION BALANCING)]
- Khi tổng nạp calo cả ngày đang thâm hụt (ví dụ thâm hụt 500+ kcal ở tuần Tapering T-7 đến Race Day), bữa tối 700-800 kcal nạp đủ năng lượng là hoàn toàn cần thiết để bù đắp calo và hỗ trợ tích lũy Glycogen.
- Tuyệt đối KHÔNG sử dụng ngôn từ phiến diện, tiêu cực cực đoan (như "tàn phá giấc ngủ", "nguy cơ rất lớn") chỉ vì bữa tối chứa 700-800 kcal hoặc 40g+ Fat/Protein.
- Phân tích khoảng trống tiêu hóa một cách khách quan: nếu bữa tối kết thúc lúc 19:38 (cách giờ ngủ 21:30 là 1.85 tiếng), đưa ra gợi ý điều chỉnh nhẹ nhàng (đẩy giờ ăn lên 18:30-19:00 hoặc chuyển bớt Fat sang bữa trưa) thay vì cấm đoán phi thực tế.

--- NGUYÊN TẮC VẬN ĐỘNG & LÂM SÀNG (CROSS-TRAINING & ADAPTIVE WORKOUT) ---
- Tuyệt đối NGHIÊM CẤM kê đơn Sprint 100% all-out cho vận động viên 44 tuổi bão hòa Uric Acid 442 µmol/L.
- Khi ACWR < 0.3 (Acute load is very low / Tải cấp tính rất thấp): Cảnh báo nguy cơ "ì cơ" (stale legs).
- Khi ACWR trong dải 1.5 - 1.6: Cảnh báo vùng nguy cơ chấn thương cao.
- Bữa tối lẩu / tiệc family: Thu xếp hoàn tất bữa ăn trước giờ ngủ 2.5 - 3.0 tiếng.

--- BẢNG ĐỐI CHUẨN SLEEP NORMS BENCHMARK ---
- Bảng đối chuẩn y học thể thao SLEEP NORMS BENCHMARK cần được đối chiếu chính xác.

--- PHÂN TÍCH SPO2 ĐA CHIỀU (Multi-dimensional SpO2 Analysis) ---
- Phân tích nồng độ SpO2 kết hợp nhịp thở và bối cảnh vị trí đeo thiết bị.

--- THÍCH NGHI THỜI TIẾT & TÂM LÝ (MENTAL & RACE ADAPTATION / RACE WEATHER ADAPTATION) ---
- Thích nghi thời tiết và kiểm soát tâm lý Taper Madness theo giai đoạn giải chạy.

--- ĐỘNG HÓA THỜI GIAN THEO THỰC TẾ TRONG THỰC ĐƠN ---
- Tự động căn chỉnh mốc giờ sinh hoạt và dinh dưỡng theo thời gian thực tế lập báo cáo.
"""

    two_part_spec = """
===YÊU CẦU ĐẮC THÙ VỀ ĐẦU RA 2 PHẦN (TWO-PART OUTPUT SPECIFICATION)===
Bạn BẮT BUỘC phải sinh ra 2 phần rõ rệt, phân cách bởi duy nhất 1 dòng chứa chuỗi:
===TELEGRAM_CARD_BREAK===

PHẦN 1: FULL_REPORT
- Là toàn bộ Báo cáo học thuật chi tiết các mục (phân cách giữa các mục bằng ===SECTION_BREAK===).

PHẦN 2: TELEGRAM_CARD (GLANCEABLE SUMMARY)
- Bản tóm tắt tác chiến ngắn gọn (tối đa 200 - 250 từ, đọc xong dưới 15 giây), dùng gạch đầu dòng (bullet points) súc tích, trực diện theo đúng khung giờ (Loại báo cáo):
  * Morning: Sleep Score, HRV, RHR, Readiness -> Kế hoạch bài tập hôm nay -> Cảnh báo sinh lý -> Target Dinh dưỡng.
  * Midday: Đánh giá bài chạy sáng (Cự ly, Pace, HR, Cadence, GCT Balance L/R bảo vệ gân Achilles) -> Readiness & Hướng dẫn phục hồi chiều (CẤM chạy thêm nếu mệt) -> Quota Macro còn lại -> Khóa an toàn Protein tối <= 30g (Acid Uric 442 µmol/L).
  * Evening: Tổng kết bước chân, calo nạp & tiêu hao -> Vệ sinh giấc ngủ (Magie Bisglycinate 300mg, nước kiềm, giờ cắt màn hình trước 21:00, ngủ 21:30).
"""

    if r_type == "midday":
        return f"""{base_expert_header}

YÊU CẦU RIÊNG CHO BÁO CÁO TRƯA (MIDDAY REVIEW - SEPARATION OF CONCERNS):
- LOẠI BỎ TOÀN BỘ: TUYỆT ĐỐI KHÔNG phân tích lại cấu trúc giấc ngủ đêm qua, KHÔNG xuất bảng sleep norms, KHÔNG phân tích chi tiết SpO2 đêm (nếu cần chỉ dẫn chiếu tối đa 1 câu tóm tắt điểm Sleep/HRV). Mở đầu thẳng vào Đánh giá Buổi tập Sáng nay & Động học HRM-Pro.
- TẬP TRUNG CHUYÊN SÂU: Động học bài chạy sáng từ HRM-Pro, ACWR & Tải tập luyện, Readiness & Phục hồi buổi chiều, Đối soát nhật ký ăn sáng/trưa & Quota Macro còn lại cho chiều/tối.

BẮT BUỘC ĐỊNH DẠNG ĐẦU RA CHIA THÀNH 3 MỤC VỚI KÝ HIỆU ===SECTION_BREAK=== PHÂN CÁCH GIỮA CÁC MỤC:

TIÊU ĐỀ BÁO CÁO: `# ☀️ Báo cáo Đánh giá Vận động Sáng & Điều chỉnh Trưa (Midday Review) ({date_vn})`

===SECTION_BREAK===
### 🏃‍♂️ 1. Đánh giá Buổi tập Sáng nay & Động học HRM-Pro:
- **Phân tích Thực tế Bài tập Sáng:** Cự ly (km), Pace trung bình, Nhịp tim trung bình/tối đa, Aerobic/Anaerobic Training Effect, Activity Load.
- **Động học Chạy bộ HRM-Pro & Bảo vệ Gân Achilles Trái:**
  + Cân bằng tiếp đất GCT Balance L/R (ví dụ 51.7% Left / 48.3% Right). Cảnh báo xung chấn dồn lên gân Achilles chân trái khi GCT Balance >= 51.0% L.
  + Nhắc nhở duy trì guồng chân Cadence 178 - 182 spm để đưa GCT Balance về 50.3% L.
  + Kê đơn bài tập hạ gót thụ động (Eccentric Heel Drops) nhẹ nhàng trên bậc thềm cho gân Achilles chân trái.
- **Hấp thu Tải Tập luyện & ACWR:** Đánh giá dải tải ACWR (Acute:Chronic Workload Ratio) và tiến trình Tapering.

===SECTION_BREAK===
### ⚡ 2. Trạng thái Readiness Hiện tại & Chỉ đạo Phục hồi Chiều:
- **Điểm Sẵn sàng Tập luyện & Thời gian Phục hồi:** Readiness Score hiện tại (/100) và Recovery Time hours còn lại từ Garmin.
- **Chỉ đạo Phục hồi Buổi chiều:** NGUYÊN TẮC NGHIÊM CẤM: TUYỆT ĐỐI KHÔNG kê đơn bất kỳ bài chạy bộ hay bài tập cường độ cao nào mới cho buổi chiều!
  + Nếu Readiness thấp (<40) hoặc đã chạy sáng: Buổi chiều CHỈ ĐƯỢC kê đơn phục hồi thụ động (stretching thả lỏng gân cơ, bài tập hạ gót thụ động eccentric heel drops, ngâm chân nước mát).

===SECTION_BREAK===
### 🍱 3. Đối soát Dinh dưỡng & Quota Macro Cho Chiều/Tối:
- **Đối soát Nhật ký Dinh dưỡng Đã nạp:** Tổng hợp năng lượng và macro đã nạp từ bữa sáng và bữa trưa hôm nay.
- **Tính toán Quota Macro Còn lại (Toán học chính xác):** Phép tính: Target - Loaded = Remaining (Calo, Protein, Carb, Fat).
- **Thực đơn Gợi ý Cho Bữa Phụ Chiều & Bữa Tối:** Gợi ý thực đơn từ mốc giờ hiện tại trở đi sao cho tổng Calo và Protein cộng lại vừa đúng bằng số dư còn thiếu.
- **KHÓA AN TOÀN PROTEIN BỮA TỐI:** Protein bữa tối KHÔNG ĐƯỢC VƯỢT QUÁ 30.0g cho ngày Rest/Taper (bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L). Chuyển lượng protein thừa sang bữa phụ chiều.

{two_part_spec}"""

    elif r_type == "evening":
        return f"""{base_expert_header}

YÊU CẦU RIÊNG CHO BÁO CÁO TỐI (EVENING REVIEW - SEPARATION OF CONCERNS):
- LOẠI BỎ TOÀN BỘ: TUYỆT ĐỐI KHÔNG phân tích lại chi tiết động học bài chạy sáng hay bóc tách cấu trúc giấc ngủ đêm qua. Mở đầu thẳng vào Tổng kết Vận động & Cân đối Năng lượng Ngày.
- TẬP TRUNG CHUYÊN SÂU: Tổng kết vận động & calo cả ngày, Đánh giá khoảng cách bữa tối với giờ ngủ (khoảng trống tiêu hóa >= 2 tiếng), Giao thức vệ sinh giấc ngủ & chuẩn bị sạc thể lực đêm.

BẮT BUỘC ĐỊNH DẠNG ĐẦU RA CHIA THÀNH 3 MỤC VỚI KÝ HIỆU ===SECTION_BREAK=== PHÂN CÁCH GIỮA CÁC MỤC:

TIÊU ĐỀ BÁO CÁO: `# 🌙 Báo cáo Tổng kết Ngày & Vệ sinh Giấc ngủ (Evening Review) ({date_vn})`

===SECTION_BREAK===
### 📊 1. Tổng kết Vận động & Cân đối Năng lượng Ngày:
- **Tổng kết Vận động Trong Ngày:** Tổng bước chân hôm nay vs baseline, tổng calo tiêu hao vận động Active Calories (Garmin).
- **Đối soát Cân đối Năng lượng:** Tổng calo & macro thực nạp cả ngày (Sáng + Trưa + Phụ + Tối) vs Target Calo & Macro cả ngày. Đánh giá mức độ thâm hụt hoặc dư thừa calo.

===SECTION_BREAK===
### 🍽️ 2. Đánh giá Bữa tối & Khoảng cách Tiêu hóa:
- **Khoảng trống Tiêu hóa Ban đêm (Bedtime Digestion Window):** Đánh giá thời gian kết thúc bữa tối thực tế vs giờ đi ngủ cố định (21:30).
- **Bảo vệ Hệ Tiêu hóa & HRV Đêm:** Bắt buộc duy trì khoảng trống tiêu hóa >= 2.0 - 2.5 tiếng trước khi ngủ để dạ dày rỗng, giúp hệ thần kinh phó giao cảm chiếm ưu thế, hạ thấp RHR đêm và kéo dài mật độ Ngủ sâu Deep Sleep.

===SECTION_BREAK===
### 💤 3. Giao thức Vệ sinh Giấc ngủ & Phục hồi Đêm:
- **Bổ sung Vi chất Phục hồi:** Nhắc nhở uống 1 viên Magie Bisglycinate (300mg - 400mg) giúp thư giãn hệ thần kinh thực vật + bù đủ lượng Nước khoáng kiềm Fujiwa rải đều.
- **Phục hồi Cơ học Thân dưới:** Giãn cơ nhẹ nhàng (foam rolling / leg stretches 10 phút).
- **Mốc Cắt Thiết bị Điện tử (Digital Detox):** Nhắc nhở tắt toàn bộ màn hình máy tính/điện thoại trước 21:00 (30 phút trước khi ngủ). Đi ngủ cố định đúng 21:30.

{two_part_spec}"""

    else:
        return f"""{base_expert_header}

YÊU CẦU RIÊNG CHO BÁO CÁO SÁNG (MORNING BRIEFING - SEPARATION OF CONCERNS):
- TẬP TRUNG CHUYÊN SÂU: Bóc tách cấu trúc giấc ngủ (Sleep score, Deep/REM/Light/Awake) + Bảng đối chuẩn Y học Thể thao 5 cột. Cân bằng thần kinh thực vật (HRV overnight vs baseline, RHR, Stress). SpO2 & Nhịp thở đêm. Kê đơn vận động hôm nay & Kế hoạch Dinh dưỡng cả ngày.

BẮT BUỘC ĐỊNH DẠNG ĐẦU RA CHIA THÀNH 4 MỤC VỚI KÝ HIỆU ===SECTION_BREAK=== PHÂN CÁCH GIỮA CÁC MỤC:

TIÊU ĐỀ BÁO CÁO: `# 🌅 Báo cáo Khởi động Ngày & Đánh giá Giấc ngủ (Morning Briefing) ({date_vn})`

===SECTION_BREAK===
### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:
- **Cân bằng Thần kinh Thực vật (HRV Overnight vs Baseline toàn lịch sử):** Phân tích HRV đêm (ms) so với Baseline toàn lịch sử, đánh giá độ lệch %, dải std.
- **Nhịp tim nghỉ & Stress Deviation (RHR & Stress):** Phân tích RHR đêm so với baseline, Stress ban đêm & ban ngày.
- **Sinh lý Hô hấp & Oxy SpO2 Đêm:** Nhịp thở khi ngủ (brpm) và Nồng độ Oxy SpO2 (avg/min %).
- **Cân nặng & Thể trạng OMRON VIVA / Garmin:** Cân nặng thực tế ({weight_kg} kg), Body Fat %, Muscle %, Visceral Fat.

===SECTION_BREAK===
### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
- **BẢNG ĐỐI CHUẨN CẤU TRÚC GIẤC NGỦ (SLEEP NORMS BENCHMARK):**
  Xuất 1 bảng Markdown so sánh cấu trúc giấc ngủ theo đúng mẫu 5 cột chuẩn y học thể thao:
  | Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 180d | Chuẩn Y học Thể thao | Đánh giá |
  | :--- | :--- | :--- | :--- | :--- |
  | Deep Sleep | ... | ... | 15% - 25% | ... |
  | REM Sleep | ... | ... | 20% - 25% | ... |
  | Light Sleep | ... | ... | 50% - 60% | ... |
  | Awake | ... | ... | < 5% | ... |
- **Đánh giá Siêu phục hồi (Supercompensation):** Nhận định xem đêm qua có phải đêm Siêu phục hồi hay không.
- **Đối chiếu Dinh dưỡng & Đồ nhậu Hôm qua:** Mối tương quan giữa bữa ăn/cồn hôm qua với RHR và HRV đêm.

===SECTION_BREAK===
### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:
- **Bối cảnh Microcycle & Dynamic Tapering:** Đánh giá Readiness, Training Status, ACWR.
- **Kê đơn Bài tập Đa môn 2 Lựa chọn (Cross-Training Options 1 & 2):**
  + Lựa chọn 1 (Chạy bộ MAF Zone 2 / Neuromuscular Priming)
  + Lựa chọn 2 (Bơi lội phục hồi không trọng lực)
- **Động học Running Dynamics HRM-Pro:** Duy trì Cadence 178-182 spm để bảo vệ gân Achilles chân trái (GCT balance 50.3% L).

===SECTION_BREAK===
### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):
- **Dynamic Macro Targets (Cân nặng {weight_kg} kg):** Target Protein, Carb, Fat, Total Calories.
- **Thực đơn Chi tiết Gợi ý:** Gợi ý các bữa ăn từ mốc giờ hiện tại trở đi.
- **Khóa Protein bữa tối <= 30.0g:** Bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L.

{two_part_spec}"""

SYSTEM_PROMPT = get_system_prompt("morning", "{date}", "{weight_kg}")

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


REPORT_TYPE_HEADERS = {
    "morning": "🌅 Báo cáo Khởi động Ngày & Đánh giá Giấc ngủ (Morning Briefing)",
    "midday": "☀️ Báo cáo Đánh giá Vận động Sáng & Điều chỉnh Trưa (Midday Review)",
    "evening": "🌙 Báo cáo Tổng kết Ngày & Vệ sinh Giấc ngủ (Evening Review)"
}

def get_report_title_header(report_type: str = "morning", date_vn: str = "") -> str:
    r_type = (report_type or "morning").lower()
    header_tag = REPORT_TYPE_HEADERS.get(r_type, REPORT_TYPE_HEADERS["morning"])
    if date_vn:
        return f"# {header_tag} ({date_vn})"
    return f"# {header_tag}"


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
    report_type = (baseline_data.get("report_type") or "morning").lower()

    parts = []
    header_title = get_report_title_header(report_type, date_vn)
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

    # ACWR Sports Medicine Block
    acwr_info = baseline_data.get("acwr")
    if not acwr_info:
        from src.analytics.acwr import calculate_acwr
        acwr_info = calculate_acwr(target_date)

    ac_val = acwr_info.get("acute_load", 0.0)
    cr_val = acwr_info.get("chronic_load", 0.0)
    acwr_val = acwr_info.get("acwr", 0.0)
    st_val = acwr_info.get("status", "N/A")
    zd_val = acwr_info.get("zone_desc", "N/A")

    parts.append("--- CHỈ SỐ Y HỌC THỂ THAO ACWR (ACUTE:CHRONIC WORKLOAD RATIO) ---")
    parts.append(f"- Acute Load (Tải trung bình 7 ngày gần nhất): {ac_val}")
    parts.append(f"- Chronic Load (Tải trung bình 28 ngày gần nhất): {cr_val}")
    parts.append(f"- Tỷ số ACWR Ratio: {acwr_val} | Trạng thái dải tải: {st_val} ({zd_val})")

    # Blood Test Summary Block
    db_path_arg = baseline_data.get("db_path")
    blood_summary = get_latest_blood_summary(db_path_arg)
    if blood_summary:
        parts.append(blood_summary)

    hrv_status_str = str(tm.get("hrv_status") or "").upper()
    is_hrv_balanced = any(kw in hrv_status_str for kw in ["BALANCED", "HIGH", "GOOD"]) or (
        tm.get("hrv_last_night") is not None and
        bm.get("hrv_last_night", {}).get("avg") is not None and
        float(tm.get("hrv_last_night")) >= float(bm.get("hrv_last_night", {}).get("avg"))
    )
    is_hrv_unbalanced = any(kw in hrv_status_str for kw in ["UNBALANCED", "SUPPRESSED", "LOW", "POOR"])

    if acwr_val < 0.3:
        parts.append(
            "⚠️ CỜ CHỈ DẪN ACWR RẤT THẤP (ACWR < 0.3):\n"
            "  - Tải cấp tính rất thấp. AI BẮT BUỘC ghi nhận: 'Acute load is very low. Maintain light neuromuscular tension (Zone 2 running + high cadence 178-182 spm) to prevent loss of muscle tone (stale legs) prior to race day.'"
        )
    elif acwr_val < 0.8 and is_hrv_balanced:
        parts.append(
            "⚡ CỜ CHỈ DẪN TAPERING EXCELLENT (0.3 <= ACWR < 0.8 & HRV BALANCED/HIGH):\n"
            "  - AI BẮT BUỘC khẳng định cơ thể đang hấp thu Tapering xuất sắc, sẵn sàng kích hoạt hiện tượng Siêu bù (Supercompensation) cho giải Hanoi Full Marathon (04/10)."
        )

    readiness_score = tm.get("training_readiness_score")
    gct_val = str(tm.get("gct_balance") or "")
    is_gct_imbalanced = False
    if gct_val:
        import re
        m = re.search(r"(\d+\.?\d*)%", gct_val)
        if m and float(m.group(1)) > 51.0:
            is_gct_imbalanced = True
        elif "left" in gct_val.lower() and ("51" in gct_val or "52" in gct_val):
            is_gct_imbalanced = True

    is_low_readiness = (readiness_score is not None) and (float(readiness_score) < 40)

    if is_gct_imbalanced or is_low_readiness or is_hrv_unbalanced:
        parts.append(
            "🚨 CỜ CHỈ DẪN GHI ĐÈ BÀI TẬP (BIOMECHANICS & READINESS OVERRIDE - CẤM TUYỆT ĐỐI STRIDES & TĂNG TỐC 85% FOR SECTION 3):\n"
            "  - Phát hiện GCT Balance > 51.0% (Lệch tiếp đất chân trái) HOẶC Readiness < 40 HOẶC HRV Unbalanced.\n"
            "  - AI BẮT BUỘC LOẠI BỎ HOÀN TOÀN các từ 'Strides', 'tăng tốc 85%', hoặc 'biến tốc' khỏi LỰA CHỌN 1 trong Mục 3.\n"
            "  - LỰA CHỌN 1 MỤC 3 BẮT BUỘC PHẢI LÀ: 'Chạy nhẹ MAF Zone 2 phẳng, HR < 136 bpm, 20-30 phút, Cadence locked 178-182 spm, KHÔNG BỨT TỐC / KHÔNG STRIDES / KHÔNG TĂNG TỐC 85%'\n"
            "    HOẶC Bơi lội Zone 1 (bơi sải thả lỏng 800m - 1000m triệt tiêu 90% trọng lực) HOẶC Nghỉ ngơi hoàn toàn (Rest Day)."
        )
    parts.append("")

    if report_type in ["midday", "evening"]:
        parts.append("--- CHỈ SỐ SINH LÝ & VẬN ĐỘNG HÔM NAY DẪN CHIẾU TÓM TẮT ---")
        parts.append(f"- Training Readiness Score: {_format_value(tm.get('training_readiness_score'))}/100 | Recovery Time: {_format_value(tm.get('recovery_time_hours'), 'giờ')}")
        parts.append(f"- Sleep Score: {_format_value(tm.get('sleep_score'))}/100 | HRV Overnight: {_format_value(tm.get('hrv_last_night'), 'ms')} (Status: {tm.get('hrv_status') or 'BALANCED'}) | RHR: {_format_value(tm.get('resting_heart_rate'), 'bpm')}")
        bs_cal = bm.get("active_calories", {})
        b180_cal = bm_180.get("active_calories", {})
        parts.append(f"- Active Calories (Garmin tiêu hao tích lũy cả ngày): Hôm nay = {_format_value(tm.get('active_calories'), 'kcal')} | Baseline 180d = {b180_cal.get('avg', 'NULL')} kcal | Baseline All-Time ({sample_size}d) = {bs_cal.get('avg', 'NULL')} kcal")
        bs_steps = bm.get("total_steps", {})
        b180_steps = bm_180.get("total_steps", {})
        parts.append(f"- Total Steps (Garmin tổng bước chân tích lũy cả ngày): Hôm nay = {_format_value(tm.get('total_steps'))} bước (Step Goal = {_format_value(tm.get('step_goal'))} bước) | Baseline 180d = {b180_steps.get('avg', 'NULL')} | Baseline All-Time ({sample_size}d) = {bs_steps.get('avg', 'NULL')}")
        parts.append(f"⚠️ BẮT BUỘC TRUNG THỰC DỮ LIỆU: Báo cáo BẮT BUỘC dùng chính xác con số Total Steps = {_format_value(tm.get('total_steps'))} bước và Active Calories = {_format_value(tm.get('active_calories'))} kcal ở trên. Tuyệt đối KHÔNG tự suy diễn hoặc bịa ra con số bước chân khác (như 12.770 bước), cũng KHÔNG lấy calo của bài chạy đơn lẻ làm tổng Active Calories cả ngày!")
        parts.append("⚠️ SEPARATION OF CONCERNS: TUYỆT ĐỐI KHÔNG phân tích lại cấu trúc giấc ngủ, bảng sleep norms, hay SpO2 đêm trong báo cáo phiên này!\n")
        morning_snap = baseline_data.get("morning_report_snapshot")
        if morning_snap:
            parts.append(f"--- MORNING BRIEFING SNAPSHOT CONTEXT ---\n{morning_snap}\n--- END MORNING BRIEFING SNAPSHOT ---\n")
    else:
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
        parts.append(f"- Overnight Sleep Stress (Resting recovery, not 24h daytime stress baseline): Hôm nay = {_format_value(tm.get('avg_stress_level'))} (Max: {tm.get('max_stress_level') or 'NULL'}) | Baseline 180d 24h Stress Avg = {b180_stress.get('avg', 'NULL')} | Baseline All-Time ({sample_size}d) = {bs_stress.get('avg', 'NULL')}")

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
            parts.append("- BẮT BUỘC in câu cảnh báo trong Mục 2: '⚠️ Lưu ý: Giấc ngủ chưa kết thúc hoặc chưa đồng bộ trọn vẹn từ đồng đồng hồ. Dữ liệu dưới đây mang tính chất tạm thời.'")
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
            f"  3. Bổ sung bữa phụ giàu Carb giải phóng chậm + Tryptophan lúc 20:00 (1/2 quả chuối chín hoặc 100ml sữa tách béo ấm; CẤM TUYỆT ĐỐI hạt hạnh nhân/chất béo > 3g fat trong vòng 2 tiếng trước khi đi ngủ 21:30) HOẶC gộp tinh bột vào bữa tối 19:00 và bỏ bữa phụ 20:00."
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

    # Check GCT Balance Left >= 51.5% for Achilles Warning Flag
    gct_left_high = False
    gct_val_display = 51.7

    for act_raw_src in [tm.get("activities_summary"), prev_act_raw]:
        if act_raw_src:
            try:
                acts = json.loads(act_raw_src)
                if isinstance(acts, list):
                    for act in acts:
                        gct = act.get("gct_balance")
                        if gct is not None:
                            try:
                                val_str = str(gct).split("%")[0].strip()
                                val_f = float(val_str)
                                if val_f >= 51.5:
                                    gct_left_high = True
                                    gct_val_display = val_f
                            except Exception:
                                pass
            except Exception:
                pass

    if gct_left_high or (tm.get("gct_balance") and float(str(tm.get("gct_balance")).split("%")[0]) >= 51.5):
        parts.append(
            f"\n⚠️ CỜ CHỈ DẪN BẢO VỆ GÂN ACHILLES TRÁI (GCT BALANCE LEFT = {gct_val_display}% >= 51.5%):\n"
            f"- AI BẮT BUỘC cảnh báo nguy cơ xung chấn va đập cơ học dồn lên gân gót trái (Achilles Left).\n"
            f"- Nhắc nhở duy trì guồng chân Cadence 178 - 182 spm để đưa GCT Balance về 50.3% L.\n"
            f"- NGUYÊN TẮC BÙ TRỪ SẢI CHÂN: Khi nhắc tới tăng Cadence (178 - 182 spm), BẮT BUỘC PHẢI ĐI KÈM HƯỚNG DẪN THU NGẮN SẢI CHÂN (bước nhỏ, lướt sát đất). Tuyệt đối không khuyến nghị tăng Cadence đơn lẻ mà không nhắc thu ngắn sải chân.\n"
            f"- Giai đoạn sát giải (days_to_race <= 7): TUYỆT ĐỐI CẤM gò ép đổi dáng chạy trên đường chạy. Ưu tiên tuyệt đối nhịp tim Zone 2 (<136-140 bpm). Bảo vệ Achilles bằng biện pháp ngoài đường chạy: Bài tập hạ gót thụ động (Eccentric Heel Drops) 3 set x 10-12 lần + Giải phóng cơ mông nhỡ chân phải (Foam Roller) + Magie Bisglycinate 300-400mg."
        )

    readiness_val = float(readiness_score) if readiness_score is not None else 100.0
    is_high_risk_exercise = (readiness_val < 40) or gct_left_high or (tm.get("gct_balance") and float(str(tm.get("gct_balance")).split("%")[0]) > 51.0)

    if is_high_risk_exercise:
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Chạy bộ Zone 2 phẳng): Chạy nhẹ MAF 20-30 phút (HR < 136-140 bpm, ưu tiên hàng đầu nhịp tim Zone 2). Nếu duy trì Cadence 178-182 spm BẮT BUỘC thu ngắn sải chân (bước nhỏ, lướt sát đất). Nếu tim tăng vọt: Chạy chậm lại hoặc đi bộ. PROHIBIT (NGHIÊM CẤM): Strides bứt tốc 85-90%, intervals tốc độ cao, downhill sprints.\n"
            f"  + LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực): Bơi sải thả lỏng 800m - 1.000m (Zone 1/2). Triệt tiêu 90% áp lực trọng lực lên gân gót chân trái. Cảnh báo tuyệt đối không đạp chân ếch mạnh."
        )
    else:
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Chạy bộ - Neuromuscular Priming): Chạy nhẹ MAF 25-30 phút (<136-140 bpm, thu ngắn sải chân bước nhỏ) + 4-5 tổ Strides 80m nhẹ kỹ thuật (Cadence 180-184 spm, thu ngắn sải chân).\n"
            f"  + LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực): Bơi sải thả lỏng 800m - 1.000m (Zone 1/2), xen kẽ 3-4 đoạn 25m guồng tay nhanh. Triệt tiêu 90% áp lực trọng lực lên gân gót chân trái. Cảnh báo không đạp chân ếch mạnh."
        )

    parts.append(
        f"\n💡 QUY TẮC KÊ ĐƠN VẬN ĐỘNG ĐA MÔN LỰA CHỌN 1 & 2 (DÙNG CHO MỤC 3):\n"
        f"- Điểm Training Readiness hiện tại: {_format_value(readiness_score)}/100.\n"
        f"- THỨ BẬC ƯU TIÊN: Ưu tiên 1 = Nhịp tim Zone 2 / MAF (<136-140 bpm). Ưu tiên 2 = Muscle Freshness (Readiness < 40 cấm tạo tải). Ưu tiên 3 = Cadence/GCT Balance chỉ là thứ yếu.\n"
        f"- NGUYÊN TẮC BÙ TRỪ SẢI CHÂN: Tăng Cadence BẮT BUỘC đi kèm THU NGẮN SẢI CHÂN (bước nhỏ, lướt sát đất).\n"
        f"- BẮT BUỘC luôn cung cấp 2 LỰA CHỌN LINH HOẠT trong Mục 3:\n"
        f"{exercise_options_str}"
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

    # Active calories today from Garmin / activity data & Morning Activity Detection
    from src.analytics.pipeline import detect_today_morning_activity
    today_act_info = detect_today_morning_activity(target_date, db_path=baseline_data.get("db_path"))
    has_morning_workout = today_act_info["morning_workout_done"]

    act_summary_raw = tm.get("activities_summary")
    if act_summary_raw:
        try:
            acts = json.loads(act_summary_raw) if isinstance(act_summary_raw, str) else act_summary_raw
            if isinstance(acts, list) and len(acts) > 0:
                has_morning_workout = True
        except Exception:
            pass

    daily_data = baseline_data.get("daily_data", {})
    act_cals_today = today_act_info["active_calories"]
    if not act_cals_today and daily_data and isinstance(daily_data.get("activities"), list):
        act_cals_today = sum(a.get("calories") or 0 for a in daily_data["activities"])
    if not act_cals_today:
        act_cals_today = float(tm.get("active_calories") or tm.get("active_kilocalories") or 0)

    days_left = race_info.get("days_to_race") if race_info else None

    if days_left is not None and 1 <= days_left <= 3:
        day_type_str = f"Carbo-Loading Day (T-{days_left})"
    elif act_cals_today > 300:
        day_type_str = f"Hard Workout Day (Garmin Active Burn: {int(act_cals_today)} kcal)"
    elif has_morning_workout or act_cals_today > 150:
        day_type_str = f"Taper Active / Easy Run Day (Garmin Active Burn: {int(act_cals_today)} kcal)"
    else:
        day_type_str = "Rest Day / Active Recovery Day"

    if has_morning_workout:
        parts.append(
            f"\n⚡ QUY TẮC ĐỔI TIÊU ĐỀ & KÊ ĐƠN CHO MỤC 3 (ĐÃ HOÀN THÀNH BÀI CHẠY SÁNG NAY):\n"
            f"1. TIÊU ĐỀ MỤC 3 BẮT BUỘC ĐỔI THÀNH: '### 🏃‍♂️ 3. Đánh giá Buổi tập Sáng nay & Kế hoạch Phục hồi Chiều:'\n"
            f"2. Đánh giá thực tế các thông số bài tập sáng: Cự ly, nhịp tim trung bình, cadence, GCT balance HRM-Pro.\n"
            f"3. NGUYÊN TẮC NGHIÊM CẤM: TUYỆT ĐỐI KHÔNG kê đơn bất kỳ bài chạy bộ nào mới cho buổi chiều! "
            f"Buổi chiều CHỈ ĐƯỢC kê đơn phục hồi thụ động (stretching thả lỏng gân cơ, bài tập hạ gót thụ động eccentric heel drops, ngâm chân nước ấm/mát)."
        )

    from src.services.nutrition_calculator import calculate_daily_macro_targets
    macro_targets = calculate_daily_macro_targets(
        weight_kg=w_eff,
        day_type=day_type_str,
        uric_acid_umol_l=442.0,
        active_calories_garmin=act_cals_today
    )
    target_cal = macro_targets["target_calories"]
    target_p = macro_targets["protein_g"]
    target_c = macro_targets["carb_g"]
    target_f = macro_targets["fat_g"]

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
            f"2. GIỚI HẠN PROTEIN BỮA TỐI: Protein bữa tối KHÔNG ĐƯỢC VƯỢT QUÁ 30.0g cho ngày Rest/Taper (bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L). Phân bổ lượng protein thừa sang bữa phụ chiều (ví dụ: 1 hũ sữa chua Hy Lạp Chobani ~15g P).\n"
            f"3. ĐỘNG HÓA ATWATER & CAM TƯƠI: abs(Calo - (P*4 + C*4 + F*9)) <= 4.0 kcal cho từng món ăn. Không khống carb của 100g cam tươi (> 15g C, cam tươi thực tế 9.5g C, ~47 kcal). Phân bổ Carb còn thiếu vào tinh bột sạch (cơm, yến mạch, bánh mì).\n"
            f"4. BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC: Phép tính bù trừ: {target_cal} kcal (Mục tiêu) - {tot_cal_today} kcal (Đã nạp) = {rem_cal} kcal (Còn thiếu); {target_p}g Protein (Mục tiêu) - {tot_p_today}g (Đã nạp) = {rem_p}g Protein (Còn thiếu). Kê đơn các bữa ăn còn lại sao cho tổng Calo và Protein từ thực đơn gợi ý BẮT BUỘC cộng lại vừa đúng bằng {rem_cal} kcal và {rem_p}g Protein, không được tính nhẩm sai lệch!\n"
            f"5. TÍNH KHẢ THI BỮA TỐI: Khi gợi ý các bữa ăn có thời gian chế biến/dùng bữa kéo dài (như Lẩu hoặc tiệc tối gia đình): BẮT BUỘC bổ sung lưu ý thực tế: 'Nếu chọn ăn lẩu hoặc ăn ngoài, nên thu xếp hoàn tất bữa ăn trước giờ đi ngủ 2.5 - 3.0 tiếng, đảm bảo hệ tiêu hóa có đủ thời gian hoàn tất chu trình trước giờ ngủ.'"
        )
    else:
        parts.append(
            f"Chưa ghi nhận bản ghi bữa ăn nào trong ngày hôm nay ({target_date}).\n"
            f"Cân nặng thực tế: {w_eff} kg -> BMR cơ bản ~{bmr_est} kcal | Loai ngày: {day_type_str}.\n"
            f"Mục tiêu cả ngày hôm nay: ~{target_p}g Protein, ~{target_f}g Fat, ~{target_c}g Carb, tổng ~{target_cal} kcal.\n"
            f"⚠️ QUY TẮC BẮT BUỘC ĐỘNG HÓA THỜI GIAN CHO MỤC 4: Mốc thời gian hiện tại là {current_time_str}. Chỉ kê đơn các bữa ăn từ {current_time_str} trở đi trong ngày, không ghi mốc giờ đã trôi qua!\n"
            f"⚠️ GIỚI HẠN PROTEIN BỮA TỐI: Protein bữa tối KHÔNG ĐƯỢC VƯỢT QUÁ 30.0g cho ngày Rest/Taper (bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L). Phân bổ lượng protein thừa sang bữa phụ chiều (ví dụ: 1 hũ sữa chua Hy Lạp Chobani ~15g P).\n"
            f"⚠️ ĐỘNG HÓA ATWATER & CAM TƯƠI: abs(Calo - (P*4 + C*4 + F*9)) <= 4.0 kcal cho từng món ăn. Không khống carb của 100g cam tươi (> 15g C, cam tươi thực tế 9.5g C, ~47 kcal). Phân bổ Carb còn thiếu vào tinh bột sạch (cơm, yến mạch, bánh mì).\n"
            f"⚠️ BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC: Tổng Calo và Protein từ các món gợi ý BẮT BUỘC phải khớp chính xác với mục tiêu ~{target_cal} kcal và ~{target_p}g Protein.\n"
            f"⚠️ TÍNH KHẢ THI BỮA TỐI: Khi gợi ý các bữa ăn có thời gian chế biến/dùng bữa kéo dài (như Lẩu hoặc tiệc tối gia đình): BẮT BUỘC bổ sung lưu ý thực tế: 'Nếu chọn ăn lẩu hoặc ăn ngoài, nên thu xếp hoàn tất bữa ăn trước giờ đi ngủ 2.5 - 3.0 tiếng, đảm bảo hệ tiêu hóa có đủ thời gian hoàn tất chu trình trước giờ ngủ.'"
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
    from src.services.nutrition_calculator import calculate_daily_macro_targets
    macro_brief = calculate_daily_macro_targets(weight_kg=float(w_kg), day_type="rest", uric_acid_umol_l=442.0)
    protein_target = macro_brief["protein_g"]

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
        target_cal_est = macro_brief.get("target_calories", 1850.0)
        nut_str = f"• Target Protein: {protein_target}g | Calo ước tính: ~{target_cal_est} kcal | Nước kiềm Fujiwa: 3.0L"

    if is_incomplete:
        sleep_line = "• ⚠️ Giấc ngủ chưa chốt xong / Dậy muộn. Cân Omron xong gửi /report để cập nhật."
    elif is_emergency:
        sleep_line = f"• 🚨 EMERGENCY RECOVERY PROTOCOL: Power Nap 20m trước 14:30 | Cấm caffeine sau 12:00 | Bữa phụ 20:00 (1/2 chuối/sữa tách béo ấm, cấm dùng hạt fat>3g)"
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

def generate_telegram_card_fallback(baseline_data: Dict[str, Any]) -> str:
    """Generate a clean, concise Glanceable Summary Card (200-250 words) formatted by intraday report type."""
    if not baseline_data:
        return ""

    target_date = baseline_data.get("target_date", "")
    date_vn = get_vietnamese_date_str(target_date)
    tm = baseline_data.get("target_metrics", {})
    bm = baseline_data.get("metrics_baseline", {})
    r_type = (baseline_data.get("report_type") or "morning").lower()

    hrv_today = tm.get("hrv_last_night")
    hrv_str = f"{hrv_today} ms" if hrv_today is not None else "N/A"
    hrv_bs = bm.get("hrv_last_night", {}).get("avg")
    if hrv_today is not None and hrv_bs and hrv_bs > 0:
        pct_diff = round(((hrv_today - hrv_bs) / hrv_bs) * 100, 1)
        diff_str = f"+{pct_diff}% vs baseline" if pct_diff >= 0 else f"{pct_diff}% vs baseline"
    else:
        diff_str = "vs baseline N/A"

    rhr_today = tm.get("resting_heart_rate")
    rhr_str = f"{rhr_today} bpm" if rhr_today is not None else "N/A"
    sleep_score = tm.get("sleep_score") or "N/A"
    readiness = tm.get("training_readiness_score") or "N/A"
    w_kg = get_effective_weight_kg(tm)

    # Fetch today's activity sync
    from src.analytics.pipeline import detect_today_morning_activity
    act_info = detect_today_morning_activity(target_date, db_path=baseline_data.get("db_path"))
    workout_done = act_info["morning_workout_done"]
    morning_act = act_info.get("morning_workout")
    act_cals = act_info["active_calories"]

    from src.services.nutrition_calculator import calculate_daily_macro_targets
    day_type_str = "taper_active" if workout_done else "rest"
    macro_targets = calculate_daily_macro_targets(weight_kg=float(w_kg), day_type=day_type_str, uric_acid_umol_l=442.0, active_calories_garmin=act_cals)
    target_cal = macro_targets["target_calories"]
    target_p = macro_targets["protein_g"]
    target_c = macro_targets["carb_g"]
    target_f = macro_targets["fat_g"]

    # Today's nutrition log totals
    try:
        from src.db.nutrition_repository import get_today_nutrition_summary
        nut_sum = get_today_nutrition_summary(target_date)
        tot_cal = nut_sum["total_cal"]
        tot_p = nut_sum["total_protein"]
        tot_c = nut_sum["total_carbs"]
        tot_f = nut_sum["total_fat"]
    except Exception:
        tot_cal, tot_p, tot_c, tot_f = 0, 0.0, 0.0, 0.0

    rem_cal = max(0, int(target_cal - tot_cal))
    rem_p = max(0.0, round(target_p - tot_p, 1))
    rem_c = max(0.0, round(target_c - tot_c, 1))
    rem_f = max(0.0, round(target_f - tot_f, 1))

    # GCT & Warnings
    gct_str = tm.get("gct_balance") or "50.0% L / 50.0% R"
    warnings = []
    if tm.get("gct_balance") and "51" in str(tm.get("gct_balance")):
        warnings.append("⚠️ Tiếp đất lệch trái (GCT 51.7% L) — Chú ý gân Achilles trái")
    if float(w_kg) > 65.5:
        warnings.append("⚠️ Cân nặng sát dải trên")

    warning_text = " | ".join(warnings) if warnings else "Thể trạng ổn định, không có cảnh báo cấp bách."

    if r_type == "midday":
        if morning_act:
            dur_m = round((morning_act.get("duration_seconds") or 0) / 60.0, 1)
            dist_km = round((morning_act.get("distance_meters") or 0) / 1000.0, 2)
            cad = morning_act.get("avg_cadence") or 178
            pace = morning_act.get("pace") or "N/A"
            act_desc = f"Chạy {dist_km}km ({dur_m} phút, Pace {pace}, Cadence {cad} spm, GCT {gct_str})"
        elif workout_done:
            act_desc = f"Đã hoàn thành bài tập sáng (Garmin Active Burn: {int(act_cals)} kcal)"
        else:
            act_desc = "Sáng nay nghỉ ngơi (Chưa ghi nhận bài chạy sáng)"

        lines = [
            f"☀️ **TÓM TẮT ĐÁNH GIÁ TRƯA (MIDDAY CARD)** ({date_vn})",
            f"• **🏃 Bài chạy sáng:** {act_desc}",
            f"• **⚡ Readiness & Phục hồi chiều:** Readiness {readiness}/100 — Phục hồi thụ động, stretching nhẹ (CẤM chạy thêm buổi chiều)",
            f"• **🍱 Quota Macro còn lại:** Calo ~{rem_cal} kcal | Protein ~{rem_p}g | Carb ~{rem_c}g | Fat ~{rem_f}g",
            f"• **🔒 Khóa bữa tối:** Protein bữa tối <= 30.0g (Acid Uric 442 µmol/L)",
            f"• **⚠️ Cảnh báo sinh lý:** {warning_text}"
        ]

    elif r_type == "evening":
        steps = tm.get("total_steps") or 0
        lines = [
            f"🌙 **TÓM TẮT TỔNG KẾT TỐI (EVENING CARD)** ({date_vn})",
            f"• **👟 Vận động & Năng lượng:** {steps:,} bước | Active Calo: ~{int(act_cals)} kcal | Đã nạp: ~{tot_cal} kcal (Protein {tot_p}g, Carb {tot_c}g, Fat {tot_f}g)",
            f"• **💤 Vệ sinh giấc ngủ:** Magie Bisglycinate 300mg | Uống nước kiềm Fujiwa | Tắt thiết bị / Cắt màn hình trước 21:00 | Giờ ngủ cố định 21:30",
            f"• **⚠️ Trạng thái:** Readiness {readiness}/100 | HRV Overnight: {hrv_str} ({diff_str})"
        ]

    else: # morning
        workout_plan = "MAF Zone 2 phẳng (HR < 136 bpm, 25-30 phút, Cadence locked 178-182 spm) hoặc Bơi lội phục hồi."
        lines = [
            f"🌅 **TÓM TẮT KHỞI ĐỘNG SÁNG (MORNING CARD)** ({date_vn})",
            f"• **💤 Sinh lý & Phục hồi:** Sleep Score: {sleep_score}/100 | HRV Overnight: {hrv_str} ({diff_str}) | RHR: {rhr_str} | Readiness: {readiness}/100",
            f"• **🏃 Kế hoạch bài tập hôm nay:** {workout_plan}",
            f"• **⚠️ Cảnh báo sinh lý:** {warning_text}",
            f"• **🍱 Target Dinh dưỡng:** Target Protein: ~{target_p}g | Total Calo: ~{target_cal} kcal | Nước kiềm Fujiwa 3.0L"
        ]

    return clean_report_text("\n".join(lines))

def extract_report_and_telegram_card(raw_output: str, baseline_data: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """Parse FULL_REPORT and TELEGRAM_CARD from LLM output.
    Returns (full_report_markdown, telegram_card_string).
    """
    if not raw_output:
        fallback_card = generate_telegram_card_fallback(baseline_data) if baseline_data else ""
        return "", fallback_card

    text = clean_report_text(raw_output.strip())
    if "===TELEGRAM_CARD_BREAK===" in text:
        parts = text.split("===TELEGRAM_CARD_BREAK===")
        full_report = parts[0].strip()
        telegram_card = parts[1].strip() if len(parts) > 1 else ""
        if not telegram_card and baseline_data:
            telegram_card = generate_telegram_card_fallback(baseline_data)
        return full_report, telegram_card

    # If separator missing from LLM response
    full_report = text
    telegram_card = generate_telegram_card_fallback(baseline_data) if baseline_data else generate_executive_brief(baseline_data) if baseline_data else ""
    return full_report, telegram_card




