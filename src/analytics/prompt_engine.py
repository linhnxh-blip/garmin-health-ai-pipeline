import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime

from config.settings import BASE_DIR
from src.analytics.periodization import TrainingPhase
from src.analytics.nutrition_engine import generate_lean_menu

TRAINING_STATUS_MAP = {
    "RECOVERY": "Phục hồi (Recovery)",
    "RECOVERY_2": "Phục hồi (Recovery)",
    "MAINTAINING": "Duy trì (Maintaining)",
    "MAINTAINING_2": "Duy trì (Maintaining)",
    "MAINTAINING_3": "Duy trì (Maintaining)",
    "MAINTAINING_4": "Duy trì (Maintaining)",
    "PRODUCTIVE": "Hiệu quả (Productive)",
    "PRODUCTIVE_2": "Hiệu quả (Productive)",
    "PRODUCTIVE_3": "Hiệu quả (Productive)",
    "PRODUCTIVE_4": "Hiệu quả (Productive)",
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

def format_training_status(raw_status: Optional[Any]) -> str:
    """Format Garmin raw training status into human-readable Vietnamese clinical term.
    Strips numeric suffixes (e.g. MAINTAINING_4 -> MAINTAINING -> Duy trì (Maintaining)).
    """
    if not raw_status:
        return "Chưa xác định"
    raw_str = str(raw_status).strip().upper()
    base_key = re.sub(r'_\d+$', '', raw_str)
    return TRAINING_STATUS_MAP.get(
        base_key,
        TRAINING_STATUS_MAP.get(
            raw_str,
            "Duy trì (Maintaining)" if "MAINTAIN" in raw_str else ("Phục hồi (Recovery)" if "RECOV" in raw_str else base_key)
        )
    )

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

def get_race_context(target_date: str, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Read config/races.json and return complete race context relative to target_date.
    Integrates TrainingPhase state machine from src.analytics.periodization.
    """
    from src.analytics.periodization import detect_current_phase, TrainingPhase
    path = Path(config_path) if config_path else BASE_DIR / "config" / "races.json"
    
    phase_enum = detect_current_phase(target_date, config_path=path)

    default_res = {
        "upcoming": None,
        "recent_completed": None,
        "phase": phase_enum.value,
        "days_to_race": None,
        "days_since_race": None,
        "race_info": None,
        "taper_strict_mode": False
    }
    if not path.exists():
        return default_res

    try:
        with open(path, "r", encoding="utf-8") as f:
            races = json.load(f)
        if not isinstance(races, list):
            return default_res

        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        upcoming_races = []
        recent_races = []
        priority_order = {"A": 1, "B": 2, "C": 3}

        for race in races:
            if not isinstance(race, dict) or not race.get("date"):
                continue
            try:
                r_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
                delta_days = (r_date - target_dt).days
                p_val = priority_order.get(str(race.get("priority")).upper(), 99)
                race_entry = {
                    "name": race.get("name") or "Sự kiện chạy bộ",
                    "date": race["date"],
                    "distance": race.get("distance") or "N/A",
                    "type": race.get("type") or "running",
                    "priority": race.get("priority") or "A",
                }
                if delta_days >= 0:
                    upcoming_races.append({**race_entry, "days_to_race": delta_days, "_p_val": p_val})
                else:
                    days_since = abs(delta_days)
                    if days_since <= 21:
                        recent_races.append({**race_entry, "days_since_race": days_since, "_p_val": p_val})
            except Exception:
                continue

        upcoming = None
        if upcoming_races:
            upcoming_races.sort(key=lambda x: (x["days_to_race"], x["_p_val"]))
            upcoming = upcoming_races[0]
            upcoming.pop("_p_val", None)

        recent_completed = None
        if recent_races:
            recent_races.sort(key=lambda x: (x["days_since_race"], x["_p_val"]))
            recent_completed = recent_races[0]
            recent_completed.pop("_p_val", None)

        phase_str = phase_enum.value
        days_to_race = None
        days_since_race = None
        race_info = None

        if phase_enum in (TrainingPhase.POST_RACE_ACUTE, TrainingPhase.POST_RACE_RECOVERY) or recent_completed:
            if recent_completed:
                days_since_race = recent_completed["days_since_race"]
                race_info = recent_completed
            else:
                days_since_race = 3
            taper_strict_mode = False
        elif upcoming:
            days_to_race = upcoming["days_to_race"]
            race_info = upcoming
            taper_strict_mode = (days_to_race <= 10 and phase_str in ("TAPERING", "CARBO_LOADING"))

        return {
            "upcoming": upcoming,
            "recent_completed": recent_completed,
            "phase": phase_str,
            "days_to_race": days_to_race,
            "days_since_race": days_since_race,
            "race_info": race_info,
            "taper_strict_mode": taper_strict_mode
        }
    except Exception:
        return default_res


def get_next_upcoming_race(target_date: str, config_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read config/races.json and return the next upcoming race relative to target_date (days_to_race >= 0).
    Ignores past races (days_to_race < 0).
    """
    return get_race_context(target_date, config_path=config_path)["upcoming"]

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


def get_system_prompt(
    report_type: str = "morning",
    date_vn: str = "",
    weight_kg: str = "",
    phase: Optional[Union[str, TrainingPhase]] = None,
    days_since: Optional[int] = None,
    target_date: Optional[str] = None
) -> str:
    from src.analytics.periodization import TrainingPhase
    r_type = (report_type or "morning").lower()

    p_str = ""
    if phase is not None:
        p_str = phase.value if hasattr(phase, "value") else str(phase).upper()
    elif target_date:
        try:
            ctx = get_race_context(target_date)
            p_str = ctx.get("phase", "")
            if days_since is None:
                days_since = ctx.get("days_since_race")
        except Exception:
            pass
    elif date_vn and date_vn != "{date}":
        import re
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_vn)
        if m:
            d, mo, y = m.groups()
            t_d = f"{y}-{int(mo):02d}-{int(d):02d}"
            try:
                ctx = get_race_context(t_d)
                p_str = ctx.get("phase", "")
                if days_since is None:
                    days_since = ctx.get("days_since_race")
            except Exception:
                pass

    is_post_acute = p_str in (
        "POST_RACE_ACUTE",
        TrainingPhase.POST_RACE_ACUTE.value
    )
    is_post_recovery = p_str in (
        "POST_RACE_RECOVERY",
        TrainingPhase.POST_RACE_RECOVERY.value
    )
    is_post_race = is_post_acute or is_post_recovery
    d_since_val = days_since if days_since is not None else (3 if is_post_acute else 8)

    base_expert_header = f"""Bạn là một Chuyên gia Y học Thể thao & Hiệu suất Vận động viên Đa môn (Multi-Sport Performance Physiologist & Sports Medicine Specialist) chuẩn quốc tế (ADA, AHA, EULAR, ACSM).
Nhiệm vụ của bạn là phân tích dữ liệu sinh lý học hàng ngày từ thiết bị Garmin của vận động viên và đối chiếu trực tiếp với Baseline để đưa ra Báo cáo Sinh lý học & Kê đơn Dinh dưỡng - Vận động chuyên sâu.

YÊU CẦU NGUYÊN TẮC QUAN TRỌNG VỀ ĐỘ SÂU PHÂN TÍCH:
- TRẢ VỀ BÁO CÁO ĐẦY ĐỦ VÀ CHUYÊN SÂU CHI TIẾT: Tuyệt đối KHÔNG tóm tắt, KHÔNG rút gọn cụt ngủn. Phân tích chi tiết cơ chế sinh lý học, nguyên nhân và hệ quả đối với thể trạng vận động viên.
- TRUNG THỰC DỮ LIỆU (STRICT FACTUAL DATA): Tuyệt đối không tự suy diễn hoặc bịa ra các số liệu bị thiếu. Nếu trường dữ liệu ghi nhận là "KHÔNG CÓ DỮ LIỆU (NULL)", bạn phải ghi nhận là chưa đo lường được.
- NGÔN NGỮ VÀ THUẬT NGỮ CHUẨN MỰC: BẮT BUỘC: Toàn bộ báo cáo phải được viết thuần túy bằng tiếng Việt y khoa chuẩn mực. Tuyệt đối KHÔNG sử dụng các ký tự chữ Hán/tiếng Trung. Dùng đúng thuật ngữ "Chỉ số HRV".
- NGHIÊM CẤM SỬ DỤNG CÚ PHÁP LATEX HOẶC KÝ TỰ $: Tuyệt đối KHÔNG xuất hiện công thức dạng LaTeX hoặc lặp ký tự $ trong báo cáo (ví dụ KHÔNG viết `$(180 - 44)$`). Chỉ sử dụng văn bản text thuần túy: `(180 - 44 = 136 bpm)`.

HỒ SƠ VẬN ĐỘNG VIÊN ĐA MÔN:
- Giới tính & Tuổi: Nam, 44 tuổi (sinh 1982), thi đấu cự ly mục tiêu Full Marathon (FM 42.195 km).
- Thể trạng mục tiêu (Omron Viva): Cân nặng mục tiêu {weight_kg} kg (Dải thi đấu tối ưu: 64.0 kg - 65.0 kg, Trung vị 64.5 kg). Body Fat mục tiêu 14.0% - 16.5% (Chuẩn Omron Nam 40-59t: Bình thường < 21.9%), Cơ xương 38.5% - 40.5% (Chuẩn Omron: Bình thường < 39.1%), Mỡ nội tạng an toàn <= 9.
- Lịch trình sinh học cố định: Thức dậy 04:30 sáng, Đi ngủ 21:30 tối.
- Thiết bị & Động học: Garmin Watch + Đai đo nhịp tim HRM-Pro (Cadence, GCT Balance L/R, Stride Length).
- Ràng buộc lâm sàng & Sinh hóa: Uric Acid nền 442 µmol/L (EULAR saturation 420 µmol/L). KHÓA TRẦN PROTEIN CẢ NGÀY TUYỆT ĐỐI <= 85.0g (~1.30 - 1.35 g/kg cho thể trạng 64-65kg). TUYỆT ĐỐI CẤM kê đơn Protein tổng ngày vượt quá 85g. Khóa Protein bữa tối <= min(28.0g if is_post_race else 30.0g, quota_protein_con_lai).
- Thói quen Dinh dưỡng: Ưa thích đạm trắng nạc (ức gà, cá nạc, cá hồi, đậu phụ sốt nhẹ, trứng gà; hạn chế hải sản/tôm vào bữa tối), sữa chua Hy Lạp Chobani, nước khoáng kiềm Fujiwa.
- RÀNG BUỘC URIC ACID LÂM SÀNG (>= 420 µmol/L): TUYỆT ĐỐI KHÔNG gợi ý "Phở bò", thịt bò, thịt đỏ dưới mọi hình thức (nhất là sau các bữa tiệc có cồn/purin) hay hải sản (sò, ốc, tôm hùm, tôm cua ban đêm). Bữa tối TUYỆT ĐỐI CẤM tôm/hải sản do nguy cơ kết tinh tinh thể urate khi ngủ. Chỉ gợi ý đạm trắng thanh đạm ít purin: Đậu phụ non, ức gà nạc, cá nạc, trứng luộc.

=== QUY TẮC CƠ SINH HỌC & LÂM SÀNG BẮT BUỘC (BIOMECHANICAL GUARDRAILS - CHỐNG SUY DIỄN MÁY MÓC) ===

[RULE 1: THỨ BẬC ƯU TIÊN VẬN ĐỘNG TRONG GIAI ĐOẠN TAPERING (T-7 ĐẾN RACE DAY)]
- ƯU TIÊN SỐ 1: Nhịp tim & Mức độ mệt mỏi tim mạch (Cardiovascular Load). Mọi bài chạy nhẹ/tapering bắt buộc giữ ở Zone 2 / MAF (HR < 136 - 140 bpm). Bất kể guồng chân hay pace thế nào, nếu HR vượt Zone 2 thì phải ưu tiên chạy chậm lại hoặc đi bộ.
- ƯU TIÊN SỐ 2: Độ tươi xốp của cơ bắp (Muscle Freshness). Không tạo tải mới khi Training Readiness < 40.
- ƯU TIÊN SỐ 3: Động học chạy bộ (Cadence & GCT Balance) CHỈ LÀ THỨ YẾU.

[RULE 2: NGUYÊN TẮC BÙ TRỪ SẢI CHÂN (STRIDE COMPENSATION LAW)]
- Khi nhắc tới việc tăng Cadence (guồng chân 178 - 182 spm), BẮT BUỘC PHẢI ĐI KÈM HƯỚNG DẪN THU NGẮN SẢI CHÂN (bước nhỏ, lướt sát đất).
- TUYỆT ĐỐI KHÔNG khuyến nghị tăng Cadence đơn lẻ mà không nhắc thu ngắn sải chân, vì sẽ làm tăng tốc độ và vọt nhịp tim.
- Nếu vận động viên cảm thấy tăng Cadence làm tim đập nhanh và mệt mỏi: Cho phép chạy ở Cadence tự nhiên thoải mái, ưu tiên tuyệt đối nhịp tim Zone 2.

[RULE 3: QUY TẮC CƠ SINH HỌC & BÀI TẬP SÁT GIẢI (DAYS_TO_RACE <= 7 HOẶC T-1/T-2)]
- Trong điều kiện days_to_race <= 7 hoặc hôm nay là T-1/T-2:
  + TUYỆT ĐỐI KHÔNG gợi ý chạy bứt tốc, Strides, Interval hay bất kỳ bài tập tăng tốc nào. Chỉ cho phép Shakeout Run nhẹ nhàng 15-20 phút Zone 1/2 (HR < 135 bpm).
  + TUYỆT ĐỐI KHÔNG đưa ra khuyến nghị "hướng tới Cadence 178-182 spm". Bắt buộc chỉ dẫn: "Chạy sải bước ngắn tự nhiên, lướt sát đất".
- BÀI TẬP XẢ TẢI GÂN ACHILLES TRÁI NGOÀI ĐƯỜNG CHẠY:
  + NẾU TRAINING READINESS < 30 (cơ thể kiệt sức/thiếu ngủ): TUYỆT ĐỐI CẤM kê đơn bài tập "Eccentric Heel Drops" (hạ gót trên mép bậc thang) vì tải kéo giãn động này có thể làm tổn thương sợi collagen gân gót khi cơ bắp đang mệt mỏi! CHỈ ĐƯỢC CHỈ ĐỊNH: Bài tập đẳng trường giữ tĩnh "Isometric Holds" trên mặt phẳng (đứng 2 chân nhón nhẹ 2-3cm giữ tĩnh 30s) hoặc nghỉ ngơi thụ động hoàn toàn (gác chân lên tường 10-15 phút).
  + NẾU TRAINING READINESS >= 30: Bài tập hạ gót thụ động "Eccentric Heel Drops" (3 set x 10-12 lần mép bậc thang) là BẮT BUỘC chỉ định ngoài đường chạy để xả tải gân Achilles trái theo Rule 3 (kết hợp 3 set đẳng trường tĩnh Isometric Holds đứng 2 chân nhón nhẹ gót 2-3 cm giữ tĩnh 30-45 giây, Foam Roller giải phóng cơ mông nhỡ chân phải và bổ sung 300-400mg Magie Bisglycinate trước khi ngủ).

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

[RULE 7: CHẾ ĐỘ CARBO-LOADING T-2 / T-1 (LOW-RESIDUE DIET & BẢO VỆ TIÊU HÓA KHI URIC ACID NỀN >= 420 µmol/L)]
- Khống chế tổng Calo ngày duy trì trong dải ~1.950 - 2.050 kcal (Carb ~320 - 340g, Fat <= 35g, Protein <= 85.0g).
- CHẾ ĐỘ LOW-RESIDUE (ÍT CHẤT XƠ KHÔNG TAN) VÀ THỰC ĐƠN T-1 RACE:
  + TUYỆT ĐỐI KHÔNG gợi ý "Phở bò", thịt bò, thịt đỏ dưới mọi hình thức (nhất là sau các bữa tiệc có cồn/purin).
  + Thực đơn sáng T-1 BẮT BUỘC chỉ định: Tinh bột tinh chế hấp thu nhanh ít béo (Phở gà nước trong / Bánh mì gối trắng quết mật ong / Xôi trắng ruốc nạc).
  + Bữa tối T-1: TUYỆT ĐỐI KHÔNG gợi ý "Cháo loãng" làm tụt đường huyết ban đêm. Bắt buộc gợi ý Cơm trắng (1.5 - 2 bát) kết hợp ức gà luộc/tôm hấp, cắt bỏ hoàn toàn rau củ nhiều xơ để làm rỗng đại tràng (Low-Residue) trước giờ xuất phát rạng sáng mai.
  + TUYỆT ĐỐI LOẠI BỎ: Rau ngót, rau muống, súp lơ, ngô, các loại hạt thô, đậu đỗ, đồ cay nóng, thức ăn nhiều dầu mỡ, yến mạch cán vỡ, gạo lứt, ngũ cốc nguyên cám.
  + ƯU TIÊN: Cơm trắng mềm, bánh phở, bánh mì gối trắng quết mật ong, chuối tiêu chín, khoai tây/khoai lang bỏ vỏ luộc mềm, canh bí đao/bí xanh/canh bầu (bỏ vỏ, bỏ ruột).
- KHỐNG CHẾ PROTEIN & CHẤT BÉO BỮA CHÍNH:
  + Giới hạn Protein mỗi bữa chính: TỐI ĐA 20 - 25g Protein.
  + Chất béo (Fat): Giữ ở mức thấp (< 15% tổng năng lượng), chế biến hoàn toàn dạng hấp/luộc/áp chảo không dầu mỡ.
- RÀNG BUỘC SỮA CHUA CHOBANI: KHÔNG gợi ý sữa chua Hy Lạp Chobani vào bữa chiều/tối nếu tổng lượng đạm tích lũy trong ngày đã đạt >= 55g.
- KIỂM TRA CHÉO CALO THEO CÔNG THỨC ATWATER:
  Total Calo = (Protein * 4) + (Carb * 4) + (Fat * 9) (dung sai tối đa ±5 kcal). Tính Protein từ cả nguồn thực vật (cơm trắng ~2.5g P/100g ~ 3g P/bát vừa) và động vật (tôm chín ~24g P/100g, ức gà chín ~30g P/100g). Tuyệt đối không tính trùng lặp.

[RULE 8: CẤU HÌNH & NGUYÊN TẮC GIAI ĐOẠN PHỤC HỒI SAU RACE (POST_RACE_RECOVERY - REVERSE TAPER D+8 ĐẾN D+14)]
- Khi current_date > race_date (hoặc ngày thi đấu 04/10/2026 đã diễn ra):
  + TỰ ĐỘNG CHUYỂN PHASE SANG POST_RACE_RECOVERY HOẶC POST_RACE_ACUTE.
  + VÔ HIỆU HÓA TOÀN BỘ cờ TAPER_STRICT_MODE và các Rule Tapering (Rule 1, Rule 2, Rule 3 sát giải).
  + XÓA BỎ VĨNH VIỄN CÁC TỪ KHÓA LỆCH PHA TRONG TIÊU ĐỀ & NỘI DUNG:
    * Tìm và xóa bỏ hoàn toàn cụm từ "Dynamic Tapering", "Tapering", "chuẩn bị glycogen", "kích hoạt thần kinh cơ", "Strides" ở Mục 3 và trong toàn bộ báo cáo!
    * Thay đổi tiêu đề Mục 3 thành: "🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{days_since}):"
    * Đảm bảo LLM không bao giờ nhầm lẫn giữa phục hồi sau giải (Post-Race) với giảm tải trước giải (Tapering).
- KÊ ĐƠN VẬN ĐỘNG GIAI ĐOẠN POST_RACE_RECOVERY (D+8 ĐẾN D+14 - REVERSE TAPER):
  + ĐIỀU KIỆN ĐỂ MỞ CỬA CHẠY THỬ (SHAKEOUT RUN):
    * training_readiness >= 65
    * recovery_time_hours <= 6
    * hrv_status == "BALANCED"
  + NẾU ĐẠT ĐỦ ĐIỀU KIỆN TRÊN:
    * Lựa chọn 1 (Shakeout Run nhẹ nhàng): Cho phép chạy thử thích ứng 2.0 km - 3.0 km (tối đa 15 - 20 phút).
      - RÀNG BUỘC CỨNG: Khống chế nhịp tim chặt chẽ ở Zone 1 / Low Zone 2 (<= 135 bpm).
      - Chạy guồng chân ngắn, tiếp đất êm, không sải dài.
      - NGUYÊN TẮC: Nếu chân trái hoặc bắp chuối có bất kỳ cảm giác gợn/thốn nào -> DỪNG NGAY LẬP TỨC và chuyển sang đi bộ.
    * Lựa chọn 2 (Phục hồi không trọng lực): Bơi sải nhẹ nhàng 500m - 700m Zone 1 HOẶC Nghỉ hoàn toàn nếu cảm thấy cơ thể còn mỏi.
  + NẾU KHÔNG ĐẠT ĐIỀU KIỆN (Readiness < 65 hoặc Recovery Time > 6h hoặc HRV không Balanced):
    * Kê đơn nghỉ ngơi hoàn toàn (Complete Rest Day) hoặc chỉ đi bộ 15 phút.
  + TIẾP TỤC DUY TRÌ BẢO VỆ GÂN ACHILLES & ACID URIC:
    * Giữ nguyên các bài tập tĩnh bổ trợ: Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set).
    * Giữ nguyên trần Protein bữa tối: <= 28.0g cho nền Acid Uric 442 µmol/L.
    * Giữ nguyên định dạng thực đơn dân dã, bát/đĩa, loại bỏ yến mạch thô và cân đong tiểu ly.
  + CẤM KÊ CÁC BÀI TẬP: Strides, Tempo, Interval, bứt tốc, biến tốc hay gò ép sải chân / guồng chân cadence.
- CẤU HÌNH MACRO DINH DƯỠNG POST-RACE & THỰC ĐƠN THỰC CHIẾN DÂN DÃ:
  + Chấm dứt hoàn toàn chế độ Carbo-loading. Giảm tỷ lệ Carb về mức bình thường (45-50% TDEE, ~3.5 - 3.8 g/kg).
  + Nâng hạn mức Protein lên dải phục hồi mô cơ: ~1.4 - 1.5 g/kg (~90 - 100g/ngày), ưu tiên đạm trắng dễ tiêu hóa (ức gà nạc, cá nạc, cá hồi, trứng, đậu phụ). Khóa trần Protein bữa tối <= 28.0g (Bảo vệ Acid Uric 442 µmol/L).
  + Thêm chỉ dẫn dinh dưỡng làm dịu đường tiêu hóa: Tránh thực phẩm kích thích co thắt đại tràng (chua cay, đường đơn đậm đặc, dầu mỡ).
  + CẤM: Tuyệt đối không gợi ý "Yến mạch cán vỡ" hay ngũ cốc thô trong pha phục hồi ruột nhạy cảm. Không viết theo kiểu cân đong tiểu ly phi thực tế (như "180g gạo chín", "40g thịt thăn").
  + QUY CHUẨN MÓN ĂN THỰC TẾ (Định lượng theo bát/đĩa thông thường):
    * Bữa sáng: 1 Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ + hành hoa thái nhỏ + 1 quả trứng gà luộc chín tới (HOẶC: 1 Bát phở gà nạc nước trong: bỏ da, không váng mỡ, không quẩy).
    * Bữa trưa: 1.5 bát con cơm trắng mềm. Đạm nạc: 1 lạng ức gà luộc HOẶC 1 khúc cá nạc hấp/áp chảo ít dầu HOẶC 1 lạng tôm hấp bóc vỏ. Kèm 1 bát canh bí đao/mồng tơi/bầu nấu thịt nạc băm (nước trong).
    * Bữa xế chiều (Đơn giản cho người đi làm): 1 quả chuối tiêu chín (~110g) HOẶC 1 quả táo tây + 1 hộp sữa chua Chobani/ít béo.
    * Bữa tối (Tuân thủ trần Protein <= 28.0g, thanh đạm, thấp purin): 1 bát con cơm trắng mềm (~130-150g, ~38-40g Carb) + Đậu phụ non sốt cà chua nhạt (1 bìa) + Ức gà nạc áp chảo / thịt nạc thăn băm (hoặc 1 quả trứng gà luộc, TUYỆT ĐỐI CẤM tôm/hải sản tối để ngừa lắng đọng Acid Uric) + Canh rau luộc nước trong.
  + BẢO TOÀN TÍNH TOÁN ATWATER DETERMINISTIC: Giữ nguyên tổng Calo, Protein, Carb, Fat tính chuẩn theo cân nặng. LLM chỉ được phép phân bổ các món ăn dân dã, thực tế ở trên để khớp với khung Macro này mà không tự ý sửa số gram tổng.

[RULE 9: GIAI ĐOẠN HỒI PHỤC CẤP POST_RACE_ACUTE (D+1 ĐẾN D+7 SAU RACE) & CẢNH BÁO DA LIỄU VÙNG CÙNG CỤT & MACRO DETERMINISTIC]
- Khi phase == POST_RACE_ACUTE (từ D+1 đến D+7 sau giải Full Marathon 04/10/2026):
  + XÓA BỎ VĨNH VIỄN CÁC TỪ KHÓA LỆCH PHA TRONG TIÊU ĐỀ & NỘI DUNG:
    * Tìm và xóa bỏ hoàn toàn cụm từ "Dynamic Tapering", "Tapering", "Nạp Glycogen", "Bơm Carb", "Kích hoạt thần kinh cơ", "Strides 80m", "Cadence 178-182 spm", "Pace 7:30-8:00", "chuẩn bị glycogen", "Strides" ở Mục 3 và trong toàn bộ báo cáo.
    * Thay đổi tiêu đề Mục 3 thành: "🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{days_since}):"
    * Đảm bảo LLM không bao giờ nhầm lẫn giữa phục hồi sau giải (Post-Race) với giảm tải trước giải (Tapering).
  + KÊ ĐƠN VẬN ĐỘNG CỨNG POST_RACE_ACUTE (D+1 ĐẾN D+7): CẤM CHẠY HOÀN TOÀN. "NGHỈ CHẠY HOÀN TOÀN (Full Rest) hoặc chỉ đi bộ nhẹ nhàng 15-20 phút / bơi nhẹ. CẤM mọi hình thức chạy bộ, strides, tempo, bứt tốc hoặc ép dẻo kéo giãn giật cục bắp chuối và gân Achilles. Bổ sung bài tập tĩnh Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set) để bảo vệ gân Achilles."
- THỰC ĐƠN DINH DƯỠNG PHỤC HỒI RUỘT & BẢO TOÀN ATWATER DETERMINISTIC:
  + CẤM TUYỆT ĐỐI: Không gợi ý "Yến mạch cán vỡ" hay ngũ cốc thô trong pha phục hồi ruột nhạy cảm. Không viết theo kiểu cân đong tiểu ly phi thực tế ("180g gạo chín", "40g thịt thăn").
  + Phân bổ thực đơn thực tế theo bát/đĩa: Bữa sáng cháo gạo trắng thịt nạc trứng luộc / phở gà nạc nước trong; Bữa trưa 1.5 bát cơm mềm + 1 lạng ức gà/cá nạc/tôm hấp + canh bí đao/mồng tơi nước trong; Bữa xế chiều chuối tiêu chín (~110g)/táo tây + sữa chua Chobani/ít béo; Bữa tối cơm mềm (~38-40g Carb) + đậu phụ non sốt cà chua nhạt + ức gà nạc/thịt nạc thăn (TUYỆT ĐỐI CẤM tôm/hải sản bữa tối, Khóa Protein tối <= 28.0g, Acid Uric 442 µmol/L).
- QUY TẮC LÂM SÀNG DA LIỄU & VÙNG CÙNG CỤT:
  + Đối với nốt sẩn viêm nang lông vùng nếp mông / sát xương cụt: Giữ khô thoáng tuyệt đối, không mặc đồ bó chật, tránh ngồi tỳ đè ngửa người ra sau, chấm Povidone-Iodine 10% tại chỗ. Tuyệt đối không cào gãi, không tự nặn.
- CƠ CHẾ TIÊM NGỮ CẢNH DINH DƯỠNG (DETERMINISTIC MACRO INJECTION):
  + BẮT BUỘC sử dụng chính xác 100% các con số Macro được hệ thống tính toán sẵn. KHÔNG ĐƯỢC PHÉP tự ý tính lại hoặc thay đổi bất kỳ số gram nào.

[RULE 10: ĐỐI SOÁT DINH DƯỠNG THÔNG MINH - INCOMPLETE NUTRITION LOG SHIELD]
- Nếu tổng calo nạp vào ghi nhận trong CSDDL < 1,300 kcal (trong khi người dùng vẫn đi làm, sinh hoạt đủ 3 bữa):
  + BẮT BUỘC ĐẶT CẢNH BÁO: Gán cờ INCOMPLETE_NUTRITION_LOG = True.
  + CẤM TUYỆT ĐỐI LLM kết luận là "thâm hụt năng lượng" hay khuyên người dùng "ăn thêm bữa nhẹ trước khi ngủ" hay "ăn đêm".
  + HƯỚNG XỬ LÝ LÂM SÀNG: Nhắc nhở người dùng: "Nhật ký dinh dưỡng dường như thiếu bữa trưa. Nếu đã nạp đủ trưa nay, KHÔNG ăn thêm bất kỳ thứ gì sau 18:00 để giữ dạ dày rỗng, bảo vệ HRV đêm và hạ RHR."

[RULE 11: LOGIC LÂM SÀNG TẢI VẬN ĐỘNG THEO PHA - CLINICAL LOAD OVERRIDE]
- Khi phase == POST_RACE_ACUTE (D+1 đến D+7) VÀ (total_steps > 9000 hoặc có bài chạy sáng):
  + NGHIÊM CẤM: Không được khen ngợi "vận động tích lũy tốt", không so sánh máy móc với baseline 30 ngày.
  + CHỈ ĐỊNH LÂM SÀNG BẮT BUỘC:
    * Cảnh báo quá tải cơ học: Số bước chân cao (>9,000 bước) tạo áp lực xung kích lớn lên sợi cơ bắp chuối và gân Achilles chân trái (vốn đang hồi phục sau sự cố chuột rút Km 26).
    * Kê đơn bắt buộc: Nằm ngửa gác chân cao vào tường (Legs up the wall) 10-15 phút để hồi lưu máu tĩnh mạch. Nghỉ ngơi hoàn toàn, cất giày vào tủ.
- Khi phase == POST_RACE_RECOVERY (D+8 đến D+21) VÀ (total_steps > 9000 hoặc có tải vận động cao ~13.000 bước):
  + Pha chu kỳ BẮT BUỘC hiển thị đúng: POST_RACE_RECOVERY (Giai đoạn Hồi phục Thích ứng D+{days_since}), TUYỆT ĐỐI KHÔNG gọi là POST_RACE_ACUTE.
  + ĐÁNH GIÁ TẢI CƠ HỌC: Khối lượng vận động lớn tích lũy trong ngày (ví dụ ~13.000 bước) tạo tải trọng cơ học và kích thích thần kinh đáng kể lên gân Achilles và hệ cơ bắp chân.
  + KHUYẾN NGHỊ VẬN ĐỘNG: Yêu cầu nghỉ ngơi ngày mai (Rest Day) để cơ thể hấp thu 13.000 bước hôm nay. TUYỆT ĐỐI KHÔNG dùng từ ngữ cấm đoán cực đoan như "nghỉ đến hết tuần" hay "cất giày vào tủ cả tuần". Thay vào đó, hướng dẫn tiếp tục theo dõi phản hồi sinh học qua HRV và Readiness mỗi sáng để quyết định bài tập tiếp theo (mở cửa Shakeout Run 2-3km nếu đạt đủ 3 điều kiện: Readiness >= 65, Recovery Time <= 6h, HRV Balanced). Buổi tối thực hiện nằm ngửa gác chân cao vào tường (Legs up the wall) 10-15 phút.

[RULE 12: CHĂM SÓC RUỘT & DA LIỄU BAN TỐI (RUNNER'S GUT & COCCYX CARE)]
- Tình trạng nếp mông / xương cụt: Sau vận động & mồ hôi, nhắc nhở vệ sinh khô ráo, chấm Povidone-Iodine 10%, mặc đồ ngủ cotton rộng rãi, tránh ngồi tỳ đè mông ngửa ra sau.
- Tình trạng ruột sau giải chạy (Runner's Gut): Rà soát xem phản xạ mót đi ngoài sau ăn đã giảm chưa. Nhắc nhở duy trì nước ấm/nước khoáng kiềm, kiêng hoàn toàn đồ ăn đêm.

--- NGUYÊN TẮC VẬN ĐỘNG & LÂM SÀNG (CROSS-TRAINING & ADAPTIVE WORKOUT) ---
- Tuyệt đối NGHIÊM CẤM kê đơn Sprint 100% all-out cho vận động viên 44 tuổi bão hòa Uric Acid 442 µmol/L.
- Khi ACWR < 0.3 (Acute load is very low / Tải cấp tính rất thấp): Cảnh báo nguy cơ "ì cơ" (stale legs), chạy nhẹ Zone 2 bước chân tự nhiên.
- Khi ACWR trong dải 1.5 - 1.6: Cảnh báo vùng nguy cơ chấn thương cao.
- Bữa tối lẩu / tiệc family: Thu xếp hoàn tất bữa ăn trước giờ ngủ 2.5 - 3.0 tiếng.

--- BẢNG ĐỐI CHUẨN SLEEP NORMS BENCHMARK & HỘI CHỨNG CỒN (ALCOHOL / REM DROP) ---
- Bảng đối chuẩn y học thể thao SLEEP NORMS BENCHMARK BẮT BUỘC xuất theo chuẩn Markdown 5 cột sát lề trái (không thụt lề), có dòng trống bao quanh để HTML parser render bảng hoàn chỉnh.
- RÀNG BUỘC KHỚP SỐ HỌC GIẤC NGỦ (DETERMINISTIC SLEEP TIME): Tổng thời gian ngủ (Total Sleep Time) trong văn bản BẮT BUỘC phải bằng chính xác tổng số phút của (Deep Sleep + REM Sleep + Light Sleep) quy đổi ra giờ và phút. Tuyệt đối không làm tròn lệch phút so với bảng số liệu. (Ví dụ: Deep 105m + REM 28m + Light 276m = 409m = 6 giờ 49 phút).
- Tổng thời gian trên giường (Total Bed Time) = Deep + REM + Light + Awake.
- Khi REM Sleep < 5.0% hoặc 0 phút (hoặc giảm >= 50% so với baseline 30d): BẮT BUỘC kích hoạt logic chẩn đoán "Hội chứng Cồn / Ức chế REM" (Alcohol-induced REM suppression) hoặc "Kiệt quệ thần kinh trung ương cấp" (Acute CNS Exhaustion). Tuyệt đối NGHIÊM CẤM kết luận là dạ dày rỗng lý tưởng khi dữ liệu bữa tối bị thiếu hoặc log chưa đầy đủ.

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
  * Evening: Tổng kết bước chân & Cảnh báo tải vận động (nếu POST_RACE_ACUTE: cất giày vào tủ; nếu POST_RACE_RECOVERY & bước cao ~13k: nghỉ ngày mai để hấp thu tải, theo dõi HRV & Readiness mỗi sáng, không cấm cực đoan) -> Dinh dưỡng & Cảnh báo log thiếu trưa -> Xả tải gân gót & Chăm sóc da liễu mông -> Giao thức thực hiện ngay trước khi lên giường (Magie Bisglycinate 300-400mg, gác chân 10-15m, tắt màn hình, ngủ ngay).
"""

    taper_midday_note = (
        "Đánh giá dải tải ACWR (Acute:Chronic Workload Ratio) và tiến trình Phục hồi Hậu Marathon (nhãn dải tải là POST_RACE_RECOVERY hoặc ACUTE_REST_RECOVERY. Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY hay bất kỳ từ khóa nào chứa TAPERING)."
        if is_post_race else
        "Đánh giá dải tải ACWR (Acute:Chronic Workload Ratio) và tiến trình Tapering."
    )
    dinner_midday_note = (
        "Protein bữa tối KHÔNG ĐƯỢC VƯỢT QUÁ 28.0g cho pha Hậu Marathon (bảo vệ Acid Uric 442 µmol/L). Số protein ở dòng chi tiết món ăn bữa tối PHẢI BẰNG CHÍNH XÁC con số trần này (tối đa 28.0g), phần protein dư còn lại phân bổ vào bữa phụ chiều."
        if is_post_race else
        "Protein bữa tối KHÔNG ĐƯỢC VƯỢT QUÁ 30.0g cho ngày Rest/Taper (bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L). Số protein ở dòng chi tiết món ăn bữa tối PHẢI BẰNG CHÍNH XÁC con số trần này (tối đa 30.0g), phần protein dư còn lại phân bổ vào bữa phụ chiều."
    )

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
  + KHÓA AN TOÀN GÂN ACHILLES THEO READINESS:
    * Nếu Training Readiness < 30 (cơ thể kiệt sức/thiếu ngủ): TUYỆT ĐỐI CẤM kê đơn bài tập "Eccentric Heel Drops" (hạ gót trên mép bậc thang) vì tải kéo giãn động này có thể làm tổn thương sợi collagen gân gót khi cơ bắp đang mệt mỏi! CHỈ ĐƯỢC CHỈ ĐỊNH: Bài tập đẳng trường giữ tĩnh "Isometric Holds" trên mặt phẳng (đứng 2 chân nhón nhẹ gót 2-3 cm, giữ tĩnh 30-45 giây x 3 set) để giảm ức chế đau thần kinh gân mà không tạo mỏi cơ, HOẶC phục hồi thụ động hoàn toàn (nằm ngửa gác chân cao lên tường Legs up the wall 10-15 phút).
    * Nếu Training Readiness >= 30: Kê đơn bài tập đẳng trường tĩnh Isometric Holds (đứng 2 chân nhón nhẹ gót 2-3 cm, giữ tĩnh 30-45s x 3 set) để giảm ức chế đau thần kinh gân mà không tạo mỏi cơ bắp chân.
- **Hấp thu Tải Tập luyện & ACWR:** {taper_midday_note}

===SECTION_BREAK===
### ⚡ 2. Trạng thái Readiness Hiện tại & Chỉ đạo Phục hồi Chiều:
- **Điểm Sẵn sàng Tập luyện & Thời gian Phục hồi:** Readiness Score hiện tại (/100) và Recovery Time hours còn lại từ Garmin.
- **Chỉ đạo Phục hồi Buổi chiều:** NGUYÊN TẮC NGHIÊM CẤM: TUYỆT ĐỐI KHÔNG kê đơn bất kỳ bài chạy bộ hay bài tập cường độ cao nào mới cho buổi chiều!
  + Nếu Readiness thấp (<40, đặc biệt < 30) hoặc đã chạy sáng: Buổi chiều CHỈ ĐƯỢC kê đơn phục hồi thụ động (stretching thả lỏng gân cơ nhẹ nhàng, bài tập đẳng trường tĩnh isometric holds trên mặt phẳng, nằm ngửa gác chân lên tường 10-15 phút, ngâm chân nước ấm/mát). CẤM các bài tập kéo giãn động nặng lên gân gót như Eccentric Heel Drops khi Readiness < 30.

===SECTION_BREAK===
### 🍱 3. Đối soát Dinh dưỡng & Quota Macro Cho Chiều/Tối:
- **Đối soát Nhật ký Dinh dưỡng Đã nạp:** Tổng hợp năng lượng và macro đã nạp từ bữa sáng và bữa trưa hôm nay.
- **Cảnh báo Tải Purine Bữa trưa & Kiềm hóa Nước tiểu:** Nếu bữa trưa chứa thịt bò, sườn heo, cá hồi/hải sản dồn dập hoặc đạm trưa cao (khi Acid Uric 442 µmol/L), BẮT BUỘC cảnh báo quá tải purine và chỉ định Giao thức Kiềm hóa (Alkaline Hydration Protocol): uống ngay 350-400ml nước khoáng kiềm Fujiwa pH 8.5-9.0, tổng chiều/tối bù 1.5-2.0L nước, tối cấm tiệt purine.
- **Tính toán Quota Macro Còn lại (Toán học Chính xác & Y học Thể thao):**
  + Phép tính: Target - Loaded = Remaining (Calo, Protein, Carb, Fat).
  + Trạng thái Fat: Báo cáo trung thực. Nếu đã vượt thì ghi rõ trạng thái EXCEEDED và số gram vượt (+X.Xg Fat).
- **Thực đơn Kê đơn Cho Bữa Phụ Chiều & Bữa Tối (CLINICAL GUARDS):**
  + **Khóa Protein Bữa tối (Clinical Guard 1):** Bữa tối nhận CHUẨN XÁC lượng Protein = min(28.0g cho hậu marathon, Protein còn thiếu). TUYỆT ĐỐI KHÔNG để số protein ở dòng thực đơn bữa tối vượt quá 28.0g (ví dụ không được viết 31.0g)! Nếu tổng Protein đã nạp cả ngày >= 80.0g: trần bữa tối KHÓA CỨNG Ở MỨC <= 15.0g (Bữa tối siêu nhẹ, thanh đạm bảo vệ thận & Uric Acid 442 µmol/L).
  + Bữa phụ chiều nhận đúng số Protein dư còn lại = (Protein còn thiếu - Protein bữa tối) (ví dụ: chuối tiêu chín (~110g) / táo tây + sữa chua Chobani/ít béo / sữa hạt / trứng luộc). Tổng cộng hai bữa khớp chính xác 100% với Protein còn thiếu.
  + **Khóa Trần Carb Bữa tối & Chống Carb-Dumping (Clinical Guard 2):** Khóa trần Carb bữa tối tối đa 60 - 70g Carb (tương đương 1 - 1.5 bát con cơm trắng mềm). TUYỆT ĐỐI CẤM dồn ép toàn bộ Carb còn thiếu (như 150 - 170g Carb) vào bữa tối gây tăng đường huyết phản ứng, tăng nhịp tim nghỉ đêm và phá hỏng giấc ngủ. Lượng Carb chưa nạp đủ ban ngày được đánh dấu là 'Chưa nạp trong khung giờ hoạt động (bỏ qua)', KHÔNG dồn/dump vào ban đêm.
  + **Sàn Chất béo Tự nhiên & Chống Ảo giác Zero-Fat (Clinical Guard 3):** TUYỆT ĐỐI KHÔNG gán 0.0g Fat cho các món chứa đạm thực vật hoặc động vật (đậu phụ non, trứng gà, thịt gà/heo nạc đều có 4-7g natural fat). Nếu Fat đã nạp đủ/vượt hạn mức, hướng dẫn chế biến hấp/luộc không dầu mỡ, nhưng ghi nhận trung thực lượng chất béo nội tại tự nhiên (~5-7g Fat), TUYỆT ĐỐI KHÔNG ép về 0.0g Fat.
- **KHÓA AN TOÀN PROTEIN BỮA TỐI:** {dinner_midday_note}
- **LOẠI BỎ FOOTER CŨ:** TUYỆT ĐỐI KHÔNG in ghi chú '💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse).' vào cuối báo cáo!

{two_part_spec}"""

    elif r_type == "evening":
        if is_post_recovery:
            phase_desc = f"POST_RACE_RECOVERY (Giai đoạn Hồi phục Thích ứng D+{d_since_val})"
            load_guidance = f"""- ĐỒNG BỘ CHÍNH XÁC PHA CHU KỲ: Hôm nay (D+{d_since_val}) BẮT BUỘC hiển thị đúng: `{phase_desc}`, TUYỆT ĐỐI KHÔNG gọi là `POST_RACE_ACUTE`.
- ĐÁNH GIÁ TẢI THỰC TẾ & KHUYẾN NGHỊ VẬN ĐỘNG:
  + Phân tích tổng bước chân & active calories.
  + Định hướng vận động ngày mai rõ ràng, mạch lạc, không mâu thuẫn: Ưu tiên Nghỉ ngơi (Rest Day) hoặc đi bộ thả lỏng do đã tích lũy khối lượng vận động và bước chân lớn hôm nay. CHỈ chạy thử 2km nếu sáng mai Readiness >= 68 và Recovery Time <= 4h.
  + Chỉ định xả tải cơ học ban tối: Nằm ngửa gác chân cao vào tường (Legs up the wall) 10-15 phút để thúc đẩy máu tĩnh mạch hồi lưu về tim."""
        elif is_post_acute:
            phase_desc = f"POST_RACE_ACUTE (Giai đoạn Hồi phục Cấp D+{d_since_val})"
            load_guidance = f"""- ĐỒNG BỘ CHÍNH XÁC PHA CHU KỲ: BẮT BUỘC hiển thị đúng `{phase_desc}`.
- ÁP DỤNG RULE 11 NẾU POST_RACE_ACUTE VÀ STEPS > 9000 (HOẶC CHẠY SÁNG): Cảnh báo quá tải xung kích lên sợi cơ bắp chuối và gân Achilles chân trái (hồi phục chuột rút Km 26). CẤM khen ngợi vận động tích lũy tốt. Chỉ định nằm ngửa gác chân cao vào tường (Legs up the wall) 10-15 phút để hồi lưu máu tĩnh mạch. Nghỉ ngơi hoàn toàn, cất giày vào tủ."""
        else:
            load_guidance = """- Phân tích tổng bước chân & active calories cả ngày.
- Đánh giá mức độ hoàn thành mục tiêu vận động và kế hoạch phục hồi ban tối."""

        return f"""{base_expert_header}

YÊU CẦU RIÊNG CHO BÁO CÁO TỐI (EVENING REVIEW - SEPARATION OF CONCERNS & NON-BOILERPLATE CHECKLIST):
- BỎ HẲN VĂN PHONG VĂN MẪU SÁO RỖNG: KHÔNG chép lại định nghĩa y khoa về Magie Bisglycinate hay Melatonin dài dòng. Format ngắn gọn, sắc sảo, đi thẳng vào checklist hành động buổi tối.
- LOẠI BỎ TOÀN BỘ: TUYỆT ĐỐI KHÔNG phân tích lại chi tiết động học bài chạy sáng hay bóc tách cấu trúc giấc ngủ đêm qua. Mở đầu thẳng vào Đánh giá Tải Thực tế & Cảnh báo Quá tải Thân dưới.

BẮT BUỘC ĐỊNH DẠNG ĐẦU RA CHIA THÀNH 4 MỤC VỚI KÝ HIỆU ===SECTION_BREAK=== PHÂN CÁCH GIỮA CÁC MỤC:

TIÊU ĐỀ BÁO CÁO: `# 🌙 Báo cáo Tổng kết Ngày & Giao thức Phục hồi Tối (Evening Review) ({date_vn})`

===SECTION_BREAK===
### 🏃‍♂️ 1. Đánh giá Tải Thực tế & Cảnh báo Quá tải Thân dưới:
{load_guidance}

===SECTION_BREAK===
### 🍽️ 2. Rà soát Dạ dày & Chốt sổ Dinh dưỡng:
- BÁM SÁT 100% NHẬT KÝ THỰC TẾ (NO FICTION): Liệt kê chính xác tên món ăn, Protein và Fat của bữa tối đã nạp trong nutrition_logs. TUYỆT ĐỐI KHÔNG bịa đặt món ăn giả định (như đậu phụ non, sốt cà chua, yến mạch) nếu nhật ký không có.
- CẢNH BÁO TIÊU HÓA ĐÊM: Đánh giá lượng mỡ (Fat) và nước ngọt/nước ép sát giờ ngủ sẽ kéo dài thời gian làm rỗng dạ dày, tăng RHR đêm và gây thức giấc tiểu đêm. Không ăn/uống thêm bất cứ thứ gì từ bây giờ.
- TOÁN HỌC MACRO & SO SÁNH MỤC TIÊU: So sánh Đã nạp cả ngày vs Mục tiêu. Nếu thừa đạm, ghi rõ: "Đã nạp cả ngày: ...g / Mục tiêu: ...g (Thừa +...g Protein, bữa tối vượt trần đạm an toàn)". TUYỆT ĐỐI CẤM in chuỗi "trần Protein <= 0.0g".

===SECTION_BREAK===
### 🩹 3. Xả Tải Gân Gót & Chăm sóc Da liễu Tại chỗ:
- Giãn cơ nhẹ nhàng & co bóp xả tải gân gót Achilles.
- Chăm sóc da liễu nếp mông / sát xương cụt: Vệ sinh sạch sẽ khô ráo, chấm Povidone-Iodine 10%, mặc đồ ngủ cotton rộng rãi, tránh ngồi tỳ đè ngửa mông ra sau.

===SECTION_BREAK===
### 💤 4. Giao thức Thực hiện Ngay Trước Khi Lên Giường (Immediate Pre-Sleep Protocol):
- Đi thẳng vào 4 bước hành động thực hiện ngay lập tức (KHÔNG liệt kê mốc giờ cố định trong quá khứ như 20:30, 21:00, 21:30 khi báo cáo chạy sau 21:00; KHÔNG chép định nghĩa y học dài dòng):
  + **Bước 1 (Uống vi chất & bù nước):** Uống ngay 1 viên Magie Bisglycinate (300-400mg) với một lượng nhỏ nước khoáng kiềm ấm.
  + **Bước 2 (Xả tải cơ học):** Nằm ngửa gác chân lên tường (Legs up the wall) 10-15 phút.
  + **Bước 3 (Ngắt thiết bị):** Tắt màn hình điện thoại/máy tính ngay lập tức, hạ sáng phòng ngủ.
  + **Bước 4 (Đi ngủ):** Lên giường nghỉ ngơi ngay để đảm bảo đủ chu kỳ ngủ sâu và tối ưu hóa thời gian phục hồi cơ bắp.

{two_part_spec}"""

    else:
        if is_post_race:
            if is_post_acute:
                sec3_block = f"""### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{d_since_val}):
- **Bối cảnh Microcycle & Hồi phục Thể thao (Post-Race Acute D+1 đến D+7):** Đánh giá các chỉ số sinh lý (Readiness, Training Status, ACWR) trong giai đoạn phục hồi cấp tính.
- **Kê đơn Vận động Cứng Post-Race Acute (D+1 đến D+7):** CẤM CHẠY HOÀN TOÀN (chỉ đi bộ nhẹ hoặc bơi nhẹ).
  + Lựa chọn 1 (Active Recovery: Đi bộ nhẹ nhàng 15-20 phút / Bơi lội thả lỏng Zone 1 thư giãn triệt tiêu 90% trọng lực / Foam roller nhẹ nhàng giải phóng bắp chuối & cơ mông).
  + Lựa chọn 2 (Nghỉ ngơi hoàn toàn - Complete Rest Day để hệ cơ bắp vi tổn thương sau giải FM tự tái tạo).
- **Bảo vệ Gân Achilles & Cơ bắp Hậu Marathon:** Giữ nguyên các bài tập tĩnh bổ trợ Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set). CẤM mọi hình thức chạy bộ, strides, tempo, bứt tốc, biến tốc hay ép dẻo kéo giãn giật cục bắp chuối và gân Achilles."""
            else:
                sec3_block = f"""### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{d_since_val}):
- **Bối cảnh Microcycle & Phục hồi Thích ứng (Giai đoạn Hồi phục D+{d_since_val}):** Đánh giá các chỉ số sinh lý (Readiness, Training Status, ACWR, HRV) trong pha phục hồi thích ứng sau giải đấu.
- **Quy tắc Kê đơn Vận động Có Điều kiện (Reverse Taper & Dynamic Volume Recovery):**
  + **Đánh giá Lâm sàng Điều kiện Vận động & Bộ lọc Chất lượng Giấc ngủ (Sleep Quality Cross-Check):**
    * KHÓA CỨNG THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG): Nếu thời gian ngủ đêm qua < 5 tiếng (< 18.000 giây), BẤT KỂ ĐIỂM SẴN SÀNG READINESS LÀ BAO NHIÊU (kể cả Readiness >= 65):
      CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG): Bất kể điểm Training Readiness là bao nhiêu, phản xạ thần kinh cơ và độ nhạy cảm thụ bản thể đang bị suy giảm nghiêm trọng. NGHIÊM CẤM TUYỆT ĐỐI chạy bộ (kể cả shakeout run 2-3km) để bảo vệ gân Achilles trái. HÔM NAY BẮT BUỘC: Nghỉ ngơi hoàn toàn (Rest Day) HOẶC bơi sải thả lỏng không trọng lực 500m Zone 1.
    * BỘ LỌC SLEEP DEFICIT (Deep Sleep < 10% HOẶC REM Sleep < 15%):
      Nếu Deep Sleep < 10% hoặc REM < 15%: Ngay cả khi Readiness >= 65 và Recovery Time <= 6h, cấu trúc giấc ngủ chưa tái tạo sâu mô cơ/thần kinh. Chuyển sang diện ƯU TIÊN VẬN ĐỘNG PHỤC HỒI (OPTIONAL ACTIVE RECOVERY):
      Ưu tiên hàng đầu: Đi bộ thả lỏng 15-20 phút hoặc bơi nhẹ 500m Zone 1 thay vì chạy. Tạm hoãn chạy để cơ thể hoàn tất tái tạo collagen.
    * TUYỆT ĐỐI CẤM in cú pháp logic hay biến code kiểu developer (CẤM in `training_readiness >= 65`, `recovery_time_hours <= 6`, `hrv_status == BALANCED`).
    * BẮT BUỘC DIỄN ĐẠT BẰNG VĂN PHONG LÂM SÀNG TỰ NHIÊN, SẮC BÉN:
      - Nếu THIẾU NGỦ < 5 TIẾNG: Diễn đạt rõ ràng cảnh báo thiếu ngủ cấp tính, cấm tuyệt đối chạy bộ, chỉ định nghỉ ngơi hoàn toàn hoặc bơi thả lỏng không trọng lực.
      - Nếu CHƯA ĐẠT điều kiện (Recovery Time > 6h hoặc Readiness < 65 hoặc HRV không Balanced): Diễn đạt rõ ràng theo mẫu:
        "Trạng thái thể lực ghi nhận mức Sẵn sàng [X]/100 và HRV Cân bằng. Tuy nhiên, thời gian hồi phục mô liên kết (Recovery Time) vẫn còn [Y] giờ sau khối lượng vận động ngày hôm qua. Do chưa đạt mốc an toàn sinh học (<= 6 giờ), quy tắc phục hồi yêu cầu tiếp tục tạm hoãn bài chạy thử (Shakeout Run) trong hôm nay để gân gót hoàn tất tái tạo collagen."
      - Nếu CÓ CẢNH BÁO SLEEP DEFICIT (Deep Sleep < 10% hoặc REM < 15%): Diễn đạt rõ ràng: "Mặc dù chỉ số Sẵn sàng Readiness [X]/100 và Recovery Time [Y]h đạt chuẩn, nhưng tỷ lệ Deep Sleep [D]% (<10%) / REM [R]% (<15%) phản ánh quá trình phục hồi sâu cơ bắp và thần kinh chưa hoàn tất. Ưu tiên hàng đầu hôm nay là đi bộ thả lỏng 15-20 phút hoặc bơi nhẹ 500m thay vì chạy bộ."
      - Nếu ĐÃ ĐẠT ĐỦ ĐIỀU KIỆN (Readiness >= 65, Recovery Time <= 6h, HRV Cân bằng, VÀ Ngủ đủ >= 5 tiếng, Deep Sleep >= 10%, REM >= 15%): Khẳng định cơ thể đã sẵn sàng cho bài chạy thử thích ứng nhẹ nhàng theo nấc tăng tiến:
        * Tuần 2 (D+8 đến D+14): Shakeout Run 2.0 - 3.0 km, Zone 1/Low Zone 2, HR <= 135 bpm, tiếp đất êm, dừng lại ngay nếu bắp chuối/gân gót có cảm giác thốn/gợn.
        * Tuần 3 (D+15 đến D+21): Chạy phục hồi thích ứng tăng tiến 3.5 - 5.0 km, Zone 2, HR <= 135-138 bpm, 25-35 phút, sải ngắn tự nhiên tiếp đất êm.
        * Tuần 4+ (D+22+): Chạy hiếu khí nền tảng MAF Zone 2 5.0 - 7.0 km, HR <= 136 bpm, 35-50 phút.
  + **Lựa chọn 1 (Active Recovery / Vận động phục hồi thích ứng):** Đi bộ nhẹ nhàng 15-20 phút hoặc bơi thả lỏng thư giãn Zone 1 nếu chưa đạt điều kiện chạy hoặc nếu có Sleep Deficit (hoặc Shakeout Run 2-3km nhẹ nhàng / Chạy thích ứng 3.5-5.0km nếu đã đạt điều kiện an toàn, CẤM chạy nếu thiếu ngủ < 5 tiếng).
  + **Lựa chọn 2 (Nghỉ ngơi hoàn toàn - Complete Rest):** Nghỉ ngơi trọn vẹn (Rest Day) hoặc vận động không trọng lực để cơ thể và gân gót hoàn tất tái tạo collagen.
- **Bảo vệ Gân Achilles & Cơ bắp Hậu Marathon:** Giữ nguyên các bài tập tĩnh bổ trợ Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set). Tuyệt đối CẤM các bài tập tốc độ: Strides, Tempo, Interval, bứt tốc, biến tốc."""

            sec4_block = f"""### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):
- **Dynamic Macro Targets (Cân nặng {weight_kg} kg):** Nhu cầu năng lượng và các chất dinh dưỡng đa lượng được phân bổ chuẩn xác cho ngày hồi phục:
  * Tổng Calo: ...
  * Protein Target: ...
  * Carbohydrate Target: ...
  * Fat Target: ...
  * Trần Protein Bữa tối (Dinner Cap): <= 28.0g
- **Thực đơn Thực tế Dân dã (Bỏ cân đong tiểu ly, không ngũ cốc thô):** Gợi ý các bữa ăn từ mốc giờ hiện tại trở đi theo định lượng bát/đĩa thông thường:
  + Bữa sáng: 1 Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ + hành hoa thái nhỏ + 1 quả trứng gà luộc chín tới (HOẶC: 1 Bát phở gà nạc nước trong: bỏ da, không váng mỡ, không quẩy).
  + Bữa trưa: 1.5 bát con cơm trắng mềm. Đạm nạc: 1 lạng ức gà luộc HOẶC 1 khúc cá nạc hấp/áp chảo ít dầu HOẶC 1 lạng tôm hấp bóc vỏ. Kèm 1 bát canh bí đao/mồng tơi/bầu nấu thịt nạc băm (nước trong).
  + Bữa xế chiều (Đơn giản cho người đi làm): 1 quả chuối tiêu chín (~110g) HOẶC 1 quả táo tây + 1 hộp sữa chua Chobani/ít béo.
  + Bữa tối (Tuân thủ trần Protein <= 28.0g, thanh đạm, thấp purin): 1 bát con cơm trắng mềm (~130-150g, ~38-40g Carb) + Đậu phụ non sốt cà chua nhạt (1 bìa) + Ức gà nạc áp chảo / thịt nạc thăn băm (hoặc 1 quả trứng luộc, TUYỆT ĐỐI CẤM tôm/hải sản tối) + Canh rau luộc nước trong.
- **Khóa Protein bữa tối <= 28.0g:** Bảo vệ Acid Uric 442 µmol/L và thận, giữ dạ dày rỗng trước 21:30 để hạ RHR & bảo vệ HRV đêm.
- **Khóa Trung thực Chất béo & Bổ sung Chất béo Sạch Tường minh (Explicit Healthy Fat Allocation):**
  * TUYỆT ĐỐI CẤM thổi phồng Fat trong các món thanh đạm/luộc/áp chảo không dầu (như ức gà không dầu, đậu phụ non, canh rau luộc) để ép khớp calo. 100g đậu phụ non (~4.8g Fat) + 70g ức gà không dầu (~2.5g Fat) + canh rau luộc chỉ chứa ~6-8g Fat (tối đa 10.0g Fat). Khai báo 20-22g Fat cho bữa tối này là lỗi ảo giác phi sinh học (Fat hallucination)! TUYỆT ĐỐI KHÔNG giả định mỡ tự có vô hình trong thịt nạc/đồ luộc để bù khống calo.
  * Khi thực đơn thuần đạm nạc/luộc/hấp khiến lượng chất béo tự nhiên thấp hơn mục tiêu Fat (> 15g): BẮT BUỘC phải kê đơn bổ sung nguồn chất béo sạch, thân thiện hệ tiêu hóa một cách tường minh vào các bữa ăn:
    - Bữa sáng: "Dùng 1 thìa nhỏ dầu thực vật/dầu phi hành thơm nấu cháo" (+5g Fat).
    - Bữa trưa: "Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc" (+5g Fat).
    - Bữa tối: "Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc" (+5g Fat).
  * Đảm bảo tổng chất béo toàn bộ thực đơn Sum(Dish Fat) khớp với Daily Target Fat trong biên độ ±3g.
- **💬 Thăm khám Thực tế Đầu ngày:** Bạn hãy kiểm tra nhanh tình trạng nốt viêm xương cụt (đã se miệng khô ráo chưa) và bắp chuối trái xem có còn cảm giác căng cứng khi bước lên cầu thang sáng nay hay không nhé.
- 💡 **Lưu ý:** Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."""
        else:
            sec3_block = """### 🏃‍♂️ 3. Kê đơn Vận động & Tải Tập luyện Hôm nay:
- **Bối cảnh Microcycle & Dynamic Tapering:** Đánh giá Readiness, Training Status, ACWR.
- **Kê đơn Bài tập Đa môn 2 Lựa chọn (Cross-Training Options 1 & 2):**
  + Lựa chọn 1 (Chạy bộ MAF Zone 2 / Neuromuscular Priming)
  + Lựa chọn 2 (Bơi lội phục hồi không trọng lực)
- **Động học Running Dynamics HRM-Pro:** Duy trì Cadence 178-182 spm để bảo vệ gân Achilles chân trái (GCT balance 50.3% L)."""

            sec4_block = f"""### 🍱 4. Kế hoạch Dinh dưỡng & Thực đơn Cá nhân hóa (Precision Nutrition):
- **Dynamic Macro Targets (Cân nặng {weight_kg} kg):** Nhu cầu năng lượng và các chất dinh dưỡng đa lượng được phân bổ chuẩn xác.
- **Thực đơn Chi tiết Gợi ý:** Gợi ý các bữa ăn từ mốc giờ hiện tại trở đi.
- **Khóa Protein bữa tối <= 30.0g:** Bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L.
- **Khóa Trung thực Chất béo & Bổ sung Chất béo Sạch Tường minh (Explicit Healthy Fat Allocation):** Không thổi phồng chất béo trong đồ luộc/không dầu; bổ sung dầu olive/dầu mè tường minh (+5g Fat mỗi bữa) nếu lượng chất béo tự nhiên thiếu hụt > 15g so với target; đảm bảo Sum(Dish Fat) khớp với Daily Target Fat trong biên độ ±3g.
- **💬 Thăm khám Thực tế Đầu ngày:** Bạn hãy kiểm tra nhanh tình trạng nốt viêm xương cụt (đã se miệng khô ráo chưa) và bắp chuối trái xem có còn cảm giác căng cứng khi bước lên cầu thang sáng nay hay không nhé.
- 💡 **Lưu ý:** Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."""

        return f"""{base_expert_header}

YÊU CẦU RIÊNG CHO BÁO CÁO SÁNG (MORNING BRIEFING - SEPARATION OF CONCERNS):
- TẬP TRUNG CHUYÊN SÂU: Bóc tách cấu trúc giấc ngủ (Sleep score, Deep/REM/Light/Awake) + Bảng đối chuẩn Y học Thể thao 5 cột. Cân bằng thần kinh thực vật (HRV overnight vs baseline, RHR, Stress). SpO2 & Nhịp thở đêm. Kê đơn vận động hôm nay & Kế hoạch Dinh dưỡng cả ngày.

QUY TẮC ĐỊNH DẠNG HỆ THỐNG (CHỈ DẪN NỘI BỘ - TUYỆT ĐỐI CẤM IN CÁC DÒNG NÀY RA BÁO CÁO):
1. Bảng Markdown PHẢI viết sát lề trái (không thụt lề đầu dòng), có 1 dòng trống trước và sau bảng để render HTML hoàn hảo trên Web Dashboard. TUYỆT ĐỐI CẤM in câu 'Quy tắc Bảng Markdown: Bảng Markdown PHẢI viết sát lề...' ra báo cáo.
2. TUYỆT ĐỐI CẤM in các câu chỉ dẫn meta như: 'Tuyệt đối không nhầm lẫn giữa phục hồi sau giải với giảm tải trước giải...', 'Sử dụng chính xác 100% mục tiêu Macro Deterministic...' Toàn bộ các yêu cầu này là LUẬT HỆ THỐNG để định hình văn bản, không được phép xuất hiện trong nội dung trả về cho người dùng.
3. TUYỆT ĐỐI CẤM in nguyên xi cú pháp biến logic hoặc mã code kiểu developer ra màn hình (như: training_readiness >= 65, recovery_time_hours <= 6, MAINTAINING_4). Mọi điều kiện vận động BẮT BUỘC diễn đạt bằng văn phong lâm sàng y học thể thao tự nhiên, sắc bén.

BẮT BUỘC ĐỊNH DẠNG ĐẦU RA CHIA THÀNH 4 MỤC VỚI KÝ HIỆU ===SECTION_BREAK=== PHÂN CÁCH GIỮA CÁC MỤC:

TIÊU ĐỀ BÁO CÁO: `# 🌅 Báo cáo Khởi động Ngày & Đánh giá Giấc ngủ (Morning Briefing) ({date_vn})`

===SECTION_BREAK===
### 🧠 1. Trạng thái Thần kinh Thực vật & Hô hấp Đêm:
- **Cân bằng Thần kinh Thực vật (HRV Overnight vs Baseline 30 ngày):** Phân tích HRV đêm (ms) so với Baseline 30 ngày, đánh giá độ lệch %, dải std.
- **Nhịp tim nghỉ & Stress Deviation (RHR & Stress):** Phân tích RHR đêm so với baseline, Stress ban đêm & ban ngày.
- **Sinh lý Hô hấp & Oxy SpO2 Đêm:** Nhịp thở khi ngủ (brpm) và Nồng độ Oxy SpO2 (avg/min %).
- **Cân nặng & Thể trạng OMRON VIVA / Garmin:** Cân nặng thực tế ({weight_kg} kg), Body Fat %, Muscle %, Visceral Fat.

===SECTION_BREAK===
### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
- **BẢNG ĐỐI CHUẨN CẤU TRÚC GIẤC NGỦ (SLEEP NORMS BENCHMARK):**

| Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |
| :--- | :--- | :--- | :--- | :--- |
| Deep Sleep | ... | ... | 15% - 25% | ... |
| REM Sleep | ... | ... | 20% - 25% | ... |
| Light Sleep | ... | ... | 50% - 60% | ... |
| Awake | ... | ... | < 5% | ... |

- **Đánh giá Siêu phục hồi (Supercompensation) & Tái tạo Chậm:**
  * RÀNG BUỘC KHỚP SỐ HỌC GIẤC NGỦ (DETERMINISTIC SLEEP TIME): Tổng thời gian ngủ (Total Sleep Time) trong văn bản BẮT BUỘC phải bằng chính xác tổng số phút của (Deep Sleep + REM Sleep + Light Sleep) quy đổi ra giờ và phút. Tuyệt đối không làm tròn lệch phút so với bảng số liệu. (Ví dụ: Deep 105m + REM 28m + Light 276m = 409m = 6 giờ 49 phút).
  * KHI THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG): TUYỆT ĐỐI TRÁNH ca ngợi thời lượng Deep Sleep cao là "Siêu phục hồi xuất sắc" (Supercompensation). Phải định danh chính xác theo y học giấc ngủ: "Cơ thể phải nén sóng não chậm (Deep Sleep Rebound) để cấp cứu tổn thương tế bào do thời gian ngủ bị cắt ngắn nghiêm trọng." Trong bảng đối chuẩn 'Sleep Norms Benchmark', cột Đánh giá của dòng Deep Sleep ghi: "Nén sóng chậm cấp cứu (Deep Sleep Rebound do thiếu ngủ)".
  * KHI NGỦ ĐỦ (>= 6-7 tiếng): Mới nhận định đêm qua có phải là đêm Siêu phục hồi (Supercompensation) hay không.
- **Đối chiếu Dinh dưỡng & Đồ nhậu Hôm qua (Hội chứng Cồn & Mất pha REM):** Mối tương quan giữa bữa ăn/cồn hôm qua với RHR, Stress và HRV đêm:
  * Bỏ các đoạn diễn giải lý thuyết dài dòng thừa thãi (như 'ức chế acetylcholine', 'dọn dẹp bộ nhớ vận động').
  * Giữ phần đánh giá ngắn gọn, trực diện: Bữa tối kết thúc sớm, không cồn giúp dạ dày rỗng giải phóng áp lực tiêu hóa, trực tiếp hạ Stress đêm và kéo dài thời lượng REM tối ưu. Ví dụ: 'Bữa tối hôm qua kết thúc sớm lúc [giờ], không sử dụng đồ uống có cồn. Dạ dày rỗng giúp giải phóng hoàn toàn áp lực tiêu hóa, trực tiếp đưa Stress đêm hạ xuống [X] và kéo dài thời lượng ngủ REM lên [Y] phút xuất sắc.'
  * Nếu có ghi nhận cồn: Khẳng định cồn làm giảm chất lượng phục hồi, tăng stress tim mạch và phá vỡ cấu trúc ngủ REM.
  * Nếu REM sụt giảm nghiêm trọng (< 5.0% hoặc 0 phút): TUYỆT ĐỐI NGHIÊM CẤM kết luận rằng dạ dày rỗng lý tưởng hay phục hồi tốt; BẮT BUỘC kích hoạt cảnh báo lâm sàng nghi vấn cồn/tiệc muộn chưa ghi nhận hoặc kiệt quệ thần kinh trung ương cấp (Acute CNS Exhaustion).

===SECTION_BREAK===
{sec3_block}

===SECTION_BREAK===
{sec4_block}

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
    tm = baseline_data.get("target_metrics") or {}
    bm = baseline_data.get("metrics_baseline") or {}
    bm_180 = baseline_data.get("metrics_baseline_180d", {})
    tl = baseline_data.get("training_load_7d") or {}
    sample_size = baseline_data.get("sample_size_days", 30)
    sample_180 = baseline_data.get("sample_size_180d", 180)
    dr = baseline_data.get("date_range") or {}
    report_type = (baseline_data.get("report_type") or "morning").lower()

    # Sleep Guardrail Check (Strict Sleep Duration Exercise Guardrail)
    sleep_dur_sec = tm.get("sleep_duration_seconds")
    total_sleep_hours = (float(sleep_dur_sec) / 3600.0) if (sleep_dur_sec is not None and float(sleep_dur_sec) > 0) else None
    allow_running = True
    mandatory_exercise_directive = ""

    if total_sleep_hours is not None and total_sleep_hours < 5.0:
        # HARD LOCK on running workouts
        allow_running = False
        mandatory_exercise_directive = (
            "CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG): Bất kể điểm Training Readiness là bao nhiêu, "
            "phản xạ thần kinh cơ và độ nhạy cảm thụ bản thể đang bị suy giảm nghiêm trọng. "
            "NGHIÊM CẤM TUYỆT ĐỐI chạy bộ (kể cả shakeout run 2-3km) để bảo vệ gân Achilles trái. "
            "HÔM NAY BẮT BUỘC: Nghỉ ngơi hoàn toàn (Rest Day) HOẶC bơi sải thả lỏng không trọng lực 500m Zone 1."
        )

    parts = []
    header_title = get_report_title_header(report_type, date_vn)
    parts.append(f"DỮ LIỆU SINH LÝ HỌC VẬN ĐỘNG VIÊN: {date_vn} ({target_date})")
    parts.append(f"Mẫu dữ liệu Baseline 30 ngày gần nhất: {sample_size} ngày ({dr.get('start') or 'N/A'} đến {dr.get('end') or 'N/A'})\n")

    # Negative Constraints (Strict Negative Ingredient Filter)
    negative_constraints = baseline_data.get("negative_constraints") or []
    if isinstance(negative_constraints, str):
        negative_constraints = [negative_constraints]
    user_prefs = baseline_data.get("user_preferences") or {}
    pref_neg = user_prefs.get("negative_constraints") or user_prefs.get("excluded_foods") or []
    if isinstance(pref_neg, str):
        pref_neg = [pref_neg]
    all_neg_constraints = [str(c).lower() for c in (list(negative_constraints) + list(pref_neg))]
    has_no_sweet_potato = any("khoai lang" in c or "khoai" in c for c in all_neg_constraints)

    if has_no_sweet_potato:
        snack_example_str = "1 quả chuối tiêu chín hoặc 1 lát bánh mì mềm kèm sữa chua ít béo"
        snack_alloc_label = "chuối tiêu chín hoặc bánh mì mềm + sữa chua ít béo"
        parts.append(
            "\n🚫 RÀNG BUỘC KIÊNG KỴ DINH DƯỠNG (STRICT NEGATIVE INGREDIENT FILTER):\n"
            "- Người dùng có ràng buộc kiêng cữ khoai lang ('không khoai lang'). "
            "TUYỆT ĐỐI CẤM gợi ý khoai lang/khoai lang hấp dưới mọi hình thức cho bất kỳ bữa ăn nào. "
            "Thay thế bằng: 1 quả chuối tiêu chín hoặc 1 lát bánh mì mềm kèm sữa chua ít béo.\n"
        )
    else:
        snack_example_str = "1 quả chuối tiêu chín (~110g) HOẶC 1 quả táo tây + 1 hộp sữa chua Chobani/ít béo"
        snack_alloc_label = "chuối tiêu chín (~110g)/táo tây + sữa chua Chobani/ít béo"

    # Upcoming / Recent Race Block
    race_ctx = get_race_context(target_date)
    phase = race_ctx["phase"]
    days_left = race_ctx["days_to_race"]
    days_since = race_ctx["days_since_race"]
    race_info = race_ctx["race_info"]

    from src.analytics.nutrition_engine import calculate_daily_macros, get_post_race_digestive_guidelines
    w_eff = get_effective_weight_kg(tm)
    macro_dict = calculate_daily_macros(
        weight_kg=w_eff,
        phase=phase,
        uric_acid_level=442.0,
        active_calories_garmin=float(tm.get("active_calories") or 0.0),
        days_since_race=days_since,
        days_to_race=days_left
    )

    parts.append(
        f"\n📊 BẢNG MỤC TIÊU MACRO CỨNG ĐƯỢC HỆ THỐNG TÍNH TOÁN THEO Y HỌC THỂ THAO (DETERMINISTIC MACROS):\n"
        f"- Tổng Calo: {macro_dict['target_calories']} kcal\n"
        f"- Protein Target: {macro_dict['protein_g']}g\n"
        f"- Carbohydrate Target: {macro_dict['carb_g']}g\n"
        f"- Fat Target: {macro_dict['fat_g']}g\n"
        f"- Trần Protein Bữa tối (Dinner Cap): {macro_dict['dinner_protein_cap']}g\n"
        f"⚠️ CHỈ THỊ DÀNH CHO LLM: Sử dụng chính xác 100% các con số Macro được cung cấp ở trên cho Mục 4. KHÔNG ĐƯỢC PHÉP tự ý tính lại hoặc thay đổi bất kỳ số gram nào.\n"
        f"⚠️ NGUYÊN TẮC BẢO VỆ TÍNH TRUNG THỰC CỦA CHẤT BÉO & NGUYÊN LIỆU (FAT INTEGRITY GUARDRAIL):\n"
        f"  * TUYỆT ĐỐI CẤM khai khống hoặc thổi phồng lượng chất béo (Fat) trong các món luộc/áp chảo không dầu/thanh đạm (như ức gà không dầu, đậu phụ non, canh rau luộc) để ép khớp mục tiêu Calo hoặc Atwater.\n"
        f"  * Định lượng thực tế: 100g đậu phụ non (~4.8g Fat) + 70g ức gà không dầu (~2.5g Fat) + canh rau luộc chỉ chứa ~6-8g Fat (tối đa 10.0g Fat). Khai báo 20-22g Fat cho bữa tối này là lỗi ảo giác phi sinh học (Fat hallucination)!\n"
        f"  * Nếu lượng Calo hoặc Fat bữa tối còn thiếu so với target: BẮT BUỘC bổ sung nguồn chất béo sạch tường minh (ví dụ: 'thêm 1 thìa cà phê 5ml dầu olive trộn canh/rau' = 45 kcal / 5g fat, hoặc 'thêm 2 thìa cà phê 10ml dầu olive' = 90 kcal / 10g fat), TUYỆT ĐỐI KHÔNG gán mỡ vô hình vào đồ luộc!"
    )

    parts.append(
        f"\n🩺 QUY TẮC LÂM SÀNG DA LIỄU & VÙNG CÙNG CỤT (DERMATOLOGY SACRAL GUARDRAIL):\n"
        f"- Đối với nốt sẩn viêm nang lông vùng nếp mông / sát xương cụt: Giữ khô thoáng tuyệt đối, không mặc đồ bó chật, tránh ngồi tỳ đè ngửa người ra sau, chấm Povidone-Iodine 10% tại chỗ. Tuyệt đối không cào gãi, không tự nặn."
    )

    if phase == "POST_RACE_ACUTE":
        d_val = days_since or 3
        parts.append("--- SỰ KIỆN THI ĐẤU & GIAI ĐOẠN HỒI PHỤC CẤP SAU RACE (POST-RACE ACUTE PHASE) ---")
        parts.append(f"- Tên sự kiện: {race_info['name'] if race_info else 'Hanoi Full Marathon'} ({race_info['distance'] if race_info else '42.195km'})")
        parts.append(f"- Ngày thi đấu: {race_info['date'] if race_info else '2026-10-04'} (ĐÃ KẾT THÚC - Đã qua đúng {d_val} ngày)")
        parts.append(f"- Trạng thái Pipeline: TỰ ĐỘNG CHUYỂN PHASE SANG POST_RACE_ACUTE.")
        parts.append(
            f"- 🛑 VÔ HIỆU HÓA TOÀN BỘ cờ TAPER_STRICT_MODE và các Rule Tapering (Rule 1, Rule 2, Rule 3 sát giải).\n"
            f"- 🛑 XÓA BỎ BẮT BUỘC CÁC TỪ KHÓA LỆCH PHA: 'Dynamic Tapering', 'Tapering', 'Nạp Glycogen', 'Bơm Carb', 'Kích hoạt thần kinh cơ', 'Strides 80m', 'Cadence 178-182 spm', 'Pace 7:30-8:00', 'chuẩn bị glycogen', 'Strides'. Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY hay bất kỳ từ khóa nào chứa TAPERING trong phân tích ACWR (Đổi nhãn thành POST_RACE_RECOVERY hoặc ACUTE_REST_RECOVERY). Tuyệt đối KHÔNG nhầm lẫn giữa phục hồi sau giải (Post-Race) với giảm tải trước giải (Tapering).\n"
            f"- 🏷️ QUY ĐỊNH TIÊU ĐỀ MỤC 3: Tiêu đề Mục 3 BẮT BUỘC là: '### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{d_val}):'.\n"
            f"- 🏃 KÊ ĐƠN VẬN ĐỘNG CỨNG POST-RACE ACUTE (D+1 ĐẾN D+7): CẤM CHẠY HOÀN TOÀN. NGHỈ CHẠY HOÀN TOÀN (Full Rest) hoặc chỉ đi bộ nhẹ nhàng 15-20 phút / bơi nhẹ. CẤM mọi hình thức chạy bộ, strides, tempo, bứt tốc hoặc ép dẻo kéo giãn giật cục bắp chuối và gân Achilles. Bổ sung bài tập tĩnh Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set) để bảo vệ gân Achilles.\n"
            f"- 🍽️ CẤU HÌNH MACRO POST-RACE ACUTE (DETERMINISTIC): Protein 1.45 g/kg ({macro_dict['protein_g']}g), Carb 3.0 g/kg ({macro_dict['carb_g']}g, CHẤM DỨT CARBO-LOADING!), Fat 0.8 g/kg ({macro_dict['fat_g']}g), Trần Bữa tối: {macro_dict['dinner_protein_cap']}g (Khóa Protein tối <= 28.0g bảo vệ Acid Uric 442 µmol/L).\n"
            f"- {get_post_race_digestive_guidelines()}"
        )
        if report_type == "evening":
            parts.append(
                f"- 🌙 QUY ĐỊNH BÁO CÁO TỐI (EVENING REVIEW - POST_RACE_ACUTE D+{d_val}):\n"
                f"  + Phase hiện tại BẮT BUỘC hiển thị: POST_RACE_ACUTE (Giai đoạn Hồi phục Cấp D+{d_val}).\n"
                f"  + Về vận động: Nếu số bước chân > 9000 hoặc có bài chạy sáng, cảnh báo quá tải xung kích, yêu cầu nằm ngửa gác chân cao vào tường (Legs up the wall) 10-15 phút, nghỉ ngơi hoàn toàn cất giày vào tủ."
            )
    elif phase == "POST_RACE_RECOVERY" and race_info:
        d_val = days_since or 8
        parts.append("--- SỰ KIỆN THI ĐẤU & GIAI ĐOẠN PHỤC HỒI SAU RACE (POST-RACE RECOVERY PHASE) ---")
        parts.append(f"- Tên sự kiện: {race_info['name']} ({race_info['distance']})")
        parts.append(f"- Ngày thi đấu: {race_info['date']} (ĐÃ KẾT THÚC - Đã qua đúng {d_val} ngày)")
        parts.append(f"- Trạng thái Pipeline: TỰ ĐỘNG CHUYỂN PHASE SANG POST_RACE_RECOVERY.")

        if not allow_running:
            post_race_exercise_directive = (
                f"- 🛑 KHÓA AN TOÀN DO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG):\n"
                f"  + {mandatory_exercise_directive}\n"
                f"  + Lựa chọn 1: Nghỉ ngơi hoàn toàn (Rest Day). Lựa chọn 2: Bơi sải thả lỏng không trọng lực 500m Zone 1."
            )
        else:
            post_race_exercise_directive = (
                f"- 🏃 KÊ ĐƠN VẬN ĐỘNG POST_RACE_RECOVERY (D+{d_val} - REVERSE TAPER & DYNAMIC RECOVERY):\n"
                f"  + ĐIỀU KIỆN ĐỂ MỞ CỬA CHẠY THỬ (SHAKEOUT RUN): sleep_duration >= 5.0h, training_readiness >= 65, recovery_time_hours <= 6, hrv_status == 'BALANCED'.\n"
                f"  + BỘ LỌC SLEEP DEFICIT: Nếu Deep Sleep < 10% hoặc REM < 15%, chuyển sang diện OPTIONAL ACTIVE RECOVERY: Ưu tiên đi bộ thả lỏng 15-20 phút hoặc bơi nhẹ 500m Zone 1 thay vì chạy.\n"
                f"  + NẾU ĐẠT ĐỦ ĐIỀU KIỆN AN TOÀN TOÀN DIỆN (Readiness >= 65, Recovery <= 6h, HRV Balanced, Ngủ đủ >= 5h, Deep >= 10%, REM >= 15%):\n"
                f"    * Lựa chọn 1: Cho phép chạy thử thích ứng 2.0 km - 3.0 km (tối đa 15 - 20 phút) ở Tuần 2 (D+8..14), 3.5 km - 5.0 km ở Tuần 3 (D+15..21), hoặc 5.0 km - 7.0 km ở Tuần 4+ (D+22+). Ràng buộc cứng: Khống chế nhịp tim chặt chẽ ở Zone 1 / Low Zone 2 (<= 135 bpm). Chạy guồng chân ngắn, tiếp đất êm, không sải dài. Nguyên tắc: Nếu chân trái hoặc bắp chuối có bất kỳ cảm giác gợn/thốn nào -> DỪNG NGAY LẬP TỨC và chuyển sang đi bộ.\n"
                f"    * Lựa chọn 2 (Phục hồi không trọng lực): Bơi sải nhẹ nhàng 500m - 700m Zone 1 HOẶC Nghỉ hoàn toàn nếu cảm thấy cơ thể còn mỏi.\n"
                f"  + NẾU KHÔNG ĐẠT ĐIỀU KIỆN (Readiness < 65 hoặc Recovery Time > 6h hoặc HRV không Balanced): Kê đơn nghỉ ngơi hoàn toàn hoặc chỉ đi bộ 15 phút.\n"
                f"  + BẢO VỆ GÂN ACHILLES & ACID URIC: Giữ nguyên các bài tập tĩnh bổ trợ Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set). CẤM các bài tập tốc độ: Strides, Tempo, Interval, bứt tốc, biến tốc."
            )

        parts.append(
            f"- 🛑 VÔ HIỆU HÓA TOÀN BỘ cờ TAPER_STRICT_MODE và các Rule Tapering (Rule 1, Rule 2, Rule 3 sát giải).\n"
            f"- 🛑 XÓA BỎ BẮT BUỘC CÁC TỪ KHÓA LỆCH PHA: 'Dynamic Tapering', 'Tapering', 'chuẩn bị glycogen', 'kích hoạt thần kinh cơ', 'Strides' trong toàn bộ báo cáo! Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY hay bất kỳ từ khóa nào chứa TAPERING trong phân tích ACWR (Đổi nhãn thành POST_RACE_RECOVERY hoặc ACUTE_REST_RECOVERY). Tuyệt đối KHÔNG nhầm lẫn giữa phục hồi sau giải (Post-Race) với giảm tải trước giải (Tapering).\n"
            f"- 🏷️ QUY ĐỊNH TIÊU ĐỀ MỤC 3: Tiêu đề Mục 3 BẮT BUỘC là: '### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{d_val}):'.\n"
            f"- 🍽️ CẤU HÌNH MACRO POST-RACE NUTRITION (DETERMINISTIC): Chấm dứt chế độ Carbo-loading. Giảm tỷ lệ Carb về mức bình thường ({macro_dict['carb_g']}g, 45-50% TDEE). "
            f"Nâng hạn mức Protein lên dải phục hồi mô cơ ({macro_dict['protein_g']}g, ~1.4 - 1.5 g/kg), ưu tiên đạm trắng dễ tiêu hóa (ức gà nạc, cá, trứng, đậu phụ). Khóa trần Protein bữa tối <= {macro_dict['dinner_protein_cap']}g (bảo vệ Acid Uric 442 µmol/L).\n"
            f"- {get_post_race_digestive_guidelines()}\n"
            f"{post_race_exercise_directive}"
        )
        if report_type == "evening":
            parts.append(
                f"- 🌙 QUY ĐỊNH BÁO CÁO TỐI (EVENING REVIEW - POST_RACE_RECOVERY D+{d_val}):\n"
                f"  + Phase hiện tại BẮT BUỘC hiển thị: POST_RACE_RECOVERY (Giai đoạn Hồi phục Thích ứng D+{d_val}), TUYỆT ĐỐI KHÔNG gọi là POST_RACE_ACUTE.\n"
                f"  + Về vận động: Nếu số bước chân cao (>9,000 bước, đặc biệt ~13.000 bước như hôm nay), yêu cầu nghỉ ngơi ngày mai (Rest Day) để hấp thu khối lượng vận động hôm nay. TUYỆT ĐỐI KHÔNG dùng từ ngữ cấm đoán cực đoan như 'nghỉ đến hết tuần' hay 'cất giày vào tủ cả tuần', mà tiếp tục theo dõi phản hồi sinh học qua HRV và Readiness mỗi sáng (mở cửa Shakeout Run khi đủ điều kiện: Readiness >= 65, Recovery Time <= 6h, HRV Balanced)."
            )
    elif race_info and days_left is not None:
        parts.append("--- SỰ KIỆN THI ĐẤU MỤC TIÊU TIẾP THEO ---")
        parts.append(f"- Tên sự kiện: {race_info['name']} ({race_info['distance']})")
        parts.append(f"- Ngày thi đấu: {race_info['date']} (Còn đúng {days_left} ngày)")
        parts.append(f"- Mức độ ưu tiên: Nhóm {race_info['priority']}")
        if 0 <= days_left <= 3:
            w_eff = get_effective_weight_kg(tm)
            if days_left == 1:
                carb_mult_str = "Carb ~330 - 340g (Protein <= 85.0g, Fat <= 35g)"
                carb_target_str = "~320 - 340g Carb/ngày"
            else:
                carb_mult_str = "Carb ~320 - 340g (Protein <= 85.0g, Fat <= 35g)"
                carb_target_str = "~320 - 340g Carb/ngày"

            parts.append(
                f"- ⚠️ KÍCH HOẠT DĨA ĐỒ ĂN CARBO-LOADING (Còn {days_left} ngày đến Race!): "
                f"TỰ ĐỘNG CHUYỂN CHIẾN LƯỢC SANG CARBO-LOADING PHASE CHO RUNNER PHONG TRÀO (70% tổng năng lượng, {carb_mult_str}). "
                f"Mục tiêu Carbohydrate: {carb_target_str} cho cân nặng {w_eff} kg (Protein khóa trần <= 85.0g cho Uric Acid 442 µmol/L). "
                f"Target Calo ngày Tapering T-2/T-1: Khống chế trong dải ~1.950 - 2.050 kcal (Carb ~320-340g, Fat <= 35g). "
                f"THỰC ĐƠN LOW-RESIDUE DIET (LÀM RỖNG ĐẠI TRÀNG): TUYỆT ĐỐI CẤM kê các loại tinh bột nhiều xơ thô ráp như 'Yến mạch cán vỡ', 'gạo lứt', ngũ cốc nguyên cám trong 2 ngày T-2 và T-1. "
                f"RÀNG BUỘC URIC ACID NỀN >= 420 µmol/L & T-1 RACE: TUYỆT ĐỐI KHÔNG gợi ý 'Phở bò', thịt bò, thịt đỏ dưới mọi hình thức (nhất là sau các bữa tiệc có cồn/purin). "
                f"Thực đơn sáng T-1 BẮT BUỘC chỉ định: Tinh bột tinh chế hấp thu nhanh ít béo (Phở gà nước trong / Bánh mì gối trắng quết mật ong / Xôi trắng ruốc nạc). "
                f"Bữa tối T-1: KHÔNG gợi ý 'Cháo loãng' làm tụt đường huyết ban đêm. Bắt buộc gợi ý Cơm trắng (1.5 - 2 bát) kết hợp ức gà luộc/tôm hấp, cắt bỏ hoàn toàn rau củ nhiều xơ để làm rỗng đại tràng (Low-Residue) trước giờ xuất phát rạng sáng mai."
            )
    else:
        parts.append("--- SỰ KIỆN THI ĐẤU MỤC TIÊU TIẾP THEO ---")
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

    is_post_race_cur = phase in ("POST_RACE_ACUTE", "POST_RACE_RECOVERY")
    if is_post_race_cur:
        if "TAPERING" in str(st_val).upper():
            st_val = "POST_RACE_RECOVERY"
        if "TAPERING" in str(zd_val).upper() or "RACE DAY" in str(zd_val).upper():
            zd_val = "Rất an toàn, cơ bắp và hệ thần kinh đang phục hồi sâu hậu giải đấu"

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
        if is_post_race_cur:
            parts.append(
                "⚠️ CỜ CHỈ DẪN ACWR RẤT THẤP HẬU MARATHON (ACWR < 0.3):\n"
                "  - Tải cấp tính ở mức thấp sau giải đấu (nhãn dải tải là POST_RACE_RECOVERY hoặc ACUTE_REST_RECOVERY. Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY hay bất kỳ từ khóa nào chứa TAPERING).\n"
                "  - Khuyến nghị nghỉ ngơi hoàn toàn hoặc phục hồi thụ động, không tăng tải đột ngột."
            )
        else:
            parts.append(
                "⚠️ CỜ CHỈ DẪN ACWR RẤT THẤP (ACWR < 0.3):\n"
                "  - Tải cấp tính ở mức thấp. Khuyến nghị chạy thả lỏng Zone 2 (< 136-140 bpm), bước chân tự nhiên thoải mái để duy trì độ tươi xốp cơ bắp trước ngày race."
            )
    elif acwr_val < 0.8:
        if is_post_race_cur:
            parts.append(
                "⚡ CỜ CHỈ DẪN PHỤC HỒI HẬU MARATHON (0.3 <= ACWR < 0.8):\n"
                "  - AI BẮT BUỘC khẳng định cơ thể đang hấp thu phục hồi hậu marathon rất tốt, hệ tim mạch và thần kinh tự chủ đang tái thiết lập cân bằng.\n"
                "  - Nhãn hiển thị dải tải bắt buộc là: POST_RACE_RECOVERY hoặc ACUTE_REST_RECOVERY. Tuyệt đối CẤM hiển thị nhãn TAPERING_DEEP_RECOVERY hay bất kỳ từ khóa nào chứa TAPERING."
            )
        elif is_hrv_balanced:
            parts.append(
                "⚡ CỜ CHỈ DẪN TAPERING EXCELLENT (0.3 <= ACWR < 0.8 & HRV BALANCED/HIGH):\n"
                "  - AI BẮT BUỘC khẳng định cơ thể đang hấp thu Tapering xuất sắc, sẵn sàng kích hoạt hiện tượng Siêu bù (Supercompensation) cho giải Hanoi Full Marathon (04/10)."
            )

    readiness_score = tm.get("training_readiness_score")
    readiness_num = float(readiness_score) if readiness_score is not None else None
    is_rem_suppressed = False
    gct_val = str(tm.get("gct_balance") or "")
    is_gct_imbalanced = False
    if gct_val:
        import re
        m = re.search(r"(\d+\.?\d*)%", gct_val)
        if m and float(m.group(1)) > 51.0:
            is_gct_imbalanced = True
        elif "left" in gct_val.lower() and ("51" in gct_val or "52" in gct_val):
            is_gct_imbalanced = True

    is_low_readiness = (readiness_num is not None) and (readiness_num < 40)
    is_very_low_readiness = (readiness_num is not None) and (readiness_num < 30)

    if is_very_low_readiness:
        parts.append(
            f"🛑 KHÓA AN TOÀN GÂN ACHILLES KHI READINESS THẤP (< 30/100, HIỆN TẠI = {_format_value(readiness_score)}/100):\n"
            "  - Cơ thể đang kiệt sức/thiếu ngủ.\n"
            "  - TUYỆT ĐỐI CẤM kê đơn bài tập 'Eccentric Heel Drops' (hạ gót trên mép bậc thang) vì tải kéo giãn động này có thể làm tổn thương sợi collagen gân gót khi cơ bắp đang mệt mỏi!\n"
            "  - CHỈ ĐƯỢC CHỈ ĐỊNH: Bài tập đẳng trường giữ tĩnh 'Isometric Holds' trên mặt phẳng (đứng 2 chân nhón nhẹ 2-3cm giữ tĩnh 30s) hoặc nghỉ ngơi thụ động hoàn toàn (gác chân lên tường 10-15 phút).\n"
        )

    if is_gct_imbalanced or is_low_readiness or is_hrv_unbalanced:
        parts.append(
            "🚨 CỜ CHỈ DẪN GHI ĐÈ BÀI TẬP (BIOMECHANICS & READINESS OVERRIDE - CẤM TUYỆT ĐỐI STRIDES & TĂNG TỐC 85% FOR SECTION 3):\n"
            "  - Phát hiện GCT Balance > 51.0% (Lệch tiếp đất chân trái) HOẶC Readiness < 40 HOẶC HRV Unbalanced.\n"
            "  - AI BẮT BUỘC LOẠI BỎ HOÀN TOÀN các từ 'Strides', 'tăng tốc 85%', hoặc 'biến tốc' khỏi LỰA CHỌN 1 trong Mục 3.\n"
            "  - LỰA CHỌN 1 MỤC 3 BẮT BUỘC PHẢI LÀ: 'Chạy nhẹ MAF Zone 2 phẳng, HR < 136-140 bpm, 20 phút, bước chân tự nhiên thoải mái, KHÔNG BỨT TỐC / KHÔNG STRIDES / KHÔNG TĂNG TỐC 85%'\n"
            "    HOẶC Nghỉ ngơi hoàn toàn (Rest Day)."
        )
    parts.append("")

    if report_type in ["midday", "evening"]:
        parts.append("--- CHỈ SỐ SINH LÝ & VẬN ĐỘNG HÔM NAY DẪN CHIẾU TÓM TẮT ---")
        parts.append(f"- Training Readiness Score: {_format_value(tm.get('training_readiness_score'))}/100 | Recovery Time: {_format_value(tm.get('recovery_time_hours'), 'giờ')}")
        parts.append(f"- Sleep Score: {_format_value(tm.get('sleep_score'))}/100 | HRV Overnight: {_format_value(tm.get('hrv_last_night'), 'ms')} (Status: {tm.get('hrv_status') or 'BALANCED'}) | RHR: {_format_value(tm.get('resting_heart_rate'), 'bpm')}")
        bs_cal = bm.get("active_calories", {})
        parts.append(f"- Active Calories (Garmin tiêu hao tích lũy cả ngày): Hôm nay = {_format_value(tm.get('active_calories'), 'kcal')} | Baseline 30d Avg = {bs_cal.get('avg', 'NULL')} kcal")
        bs_steps = bm.get("total_steps", {})
        parts.append(f"- Total Steps (Garmin tổng bước chân tích lũy cả ngày): Hôm nay = {_format_value(tm.get('total_steps'))} bước (Step Goal = {_format_value(tm.get('step_goal'))} bước) | Baseline 30d Avg = {bs_steps.get('avg', 'NULL')}")
        parts.append(f"⚠️ BẮT BUỘC TRUNG THỰC DỮ LIỆU: Báo cáo BẮT BUỘC dùng chính xác con số Total Steps = {_format_value(tm.get('total_steps'))} bước và Active Calories = {_format_value(tm.get('active_calories'))} kcal ở trên. Tuyệt đối KHÔNG tự suy diễn hoặc bịa ra con số bước chân khác (như 12.770 bước), cũng KHÔNG lấy calo của bài chạy đơn lẻ làm tổng Active Calories cả ngày!")
        parts.append("⚠️ SEPARATION OF CONCERNS: TUYỆT ĐỐI KHÔNG phân tích lại cấu trúc giấc ngủ, bảng sleep norms, hay SpO2 đêm trong báo cáo phiên này!\n")
        morning_snap = baseline_data.get("morning_report_snapshot")
        if morning_snap:
            parts.append(f"--- MORNING BRIEFING SNAPSHOT CONTEXT ---\n{morning_snap}\n--- END MORNING BRIEFING SNAPSHOT ---\n")
    else:
        parts.append(f"--- CHỈ SỐ SINH LÝ HÔM NAY VS BASELINE 30 NGÀY & 7 NGÀY GẦN NHẤT ---")

        # Sleep & HRV
        bs_sleep = bm.get("sleep_score", {})
        parts.append(f"- Sleep Score: Hôm nay = {_format_value(tm.get('sleep_score'))} | Baseline 30d Avg = {bs_sleep.get('avg', 'NULL')} (Std: {bs_sleep.get('std', 'NULL')})")

        bs_hrv = bm.get("hrv_last_night", {})
        parts.append(f"- HRV Overnight (ms): Hôm nay = {_format_value(tm.get('hrv_last_night'), 'ms')} (Status: {tm.get('hrv_status') or 'NULL'}) | Baseline 30d Avg = {bs_hrv.get('avg', 'NULL')} ms (Std: {bs_hrv.get('std', 'NULL')})")

        bs_rhr = bm.get("resting_heart_rate", {})
        parts.append(f"- Resting Heart Rate (bpm): Hôm nay = {_format_value(tm.get('resting_heart_rate'), 'bpm')} | Baseline 30d Avg = {bs_rhr.get('avg', 'NULL')} bpm (Std: {bs_rhr.get('std', 'NULL')})")

        bs_stress = bm.get("avg_stress_level", {})
        parts.append(f"- Overnight Sleep Stress (Resting recovery): Hôm nay = {_format_value(tm.get('avg_stress_level'))} (Max: {tm.get('max_stress_level') or 'NULL'}) | Baseline 30d Avg = {bs_stress.get('avg', 'NULL')}")

        # Respiration & SpO2
        parts.append(f"- Nhịp thở đêm (Respiration): Avg = {_format_value(tm.get('respiration_avg'), 'brpm')}, Min = {_format_value(tm.get('respiration_min'), 'brpm')}, Max = {_format_value(tm.get('respiration_max'), 'brpm')}")
        parts.append(f"- Nồng độ Oxy SpO2 đêm (%): Avg = {_format_value(tm.get('spo2_avg'), '%')}, Min = {_format_value(tm.get('spo2_min'), '%')}")

        # Body Battery, Recovery & Cardiorespiratory Metrics
        parts.append(f"- Body Battery: Sạc = {_format_value(tm.get('body_battery_charged'))}, Xả = {_format_value(tm.get('body_battery_drained'))}, Cao nhất = {_format_value(tm.get('body_battery_highest'))}, Thấp nhất = {_format_value(tm.get('body_battery_lowest'))}")
        parts.append(f"- Training Readiness Score: {_format_value(tm.get('training_readiness_score'))}/100")
        parts.append(f"- Recovery Time Remaining: {_format_value(tm.get('recovery_time_hours'), 'giờ')}")

        raw_ts = tm.get("training_status")
        ts_display = format_training_status(raw_ts) if raw_ts else "Chưa xác định"
        parts.append(f"- Training Status (Trạng thái tập luyện): {ts_display}")

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
        parts.append(f"- Active Calories: Hôm nay = {_format_value(tm.get('active_calories'), 'kcal')} | Baseline 30d Avg = {bs_cal.get('avg', 'NULL')} kcal")
        bs_steps = bm.get("total_steps", {})
        parts.append(f"- Total Steps: Hôm nay = {_format_value(tm.get('total_steps'))} | Baseline 30d Avg = {bs_steps.get('avg', 'NULL')}")

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

        # Sleep Norms Benchmark Table Data Pre-calculation
        deep_sec_val = float(tm.get("deep_sleep_seconds") or 0.0)
        rem_sec_val = float(tm.get("rem_sleep_seconds") or 0.0)
        light_sec_val = float(tm.get("light_sleep_seconds") or 0.0)
        awake_sec_val = float(tm.get("awake_duration_seconds") or 0.0)

        # Strictly derive Total Sleep Time = Deep + REM + Light, Total Bed Time = Deep + REM + Light + Awake
        if deep_sec_val > 0 or rem_sec_val > 0 or light_sec_val > 0:
            calc_sleep_sec = deep_sec_val + rem_sec_val + light_sec_val
            calc_bed_sec = calc_sleep_sec + awake_sec_val
        else:
            calc_sleep_sec = float(sleep_dur or 0.0)
            calc_bed_sec = calc_sleep_sec + awake_sec_val

        sleep_dur_val = calc_sleep_sec
        tot_sleep_min = int(round(calc_sleep_sec / 60.0))
        tot_sleep_h = tot_sleep_min // 60
        tot_sleep_m = tot_sleep_min % 60
        tot_sleep_display = f"{tot_sleep_h} giờ {tot_sleep_m} phút ({tot_sleep_h}h {tot_sleep_m}m)"

        tot_bed_min = int(round(calc_bed_sec / 60.0))
        tot_bed_h = tot_bed_min // 60
        tot_bed_m = tot_bed_min % 60
        tot_bed_display = f"{tot_bed_h} giờ {tot_bed_m} phút ({tot_bed_h}h {tot_bed_m}m)"

        parts.append(f"- Tổng thời gian ngủ (Total Sleep Time = Deep + REM + Light): {tot_sleep_display}")
        parts.append(f"- Tổng thời gian trên giường (Total Bed Time = Deep + REM + Light + Awake): {tot_bed_display}")
        parts.append(f"- Thức giấc trong đêm (Awake): {_format_seconds(awake_sec_val)}")
        parts.append(f"- Ngủ sâu (Deep Sleep): {_format_seconds(deep_sec_val)}")
        parts.append(f"- Ngủ mơ (REM Sleep): {_format_seconds(rem_sec_val)}")
        parts.append(f"- Ngủ nông (Light Sleep): {_format_seconds(light_sec_val)}")

        deep_m = round(deep_sec_val / 60.0, 1)
        rem_m = round(rem_sec_val / 60.0, 1)
        light_m = round(light_sec_val / 60.0, 1)
        awake_m = round(awake_sec_val / 60.0, 1)

        total_asleep = deep_m + rem_m + light_m
        total_bed = total_asleep + awake_m

        if total_asleep > 0:
            deep_pct = round((deep_m / total_asleep) * 100.0, 1)
            rem_pct = round((rem_m / total_asleep) * 100.0, 1)
            light_pct = round((100.0 - deep_pct - rem_pct), 1)  # Ensure exact 100.0% sum
        else:
            deep_pct = 0.0
            rem_pct = 0.0
            light_pct = 0.0

        if total_bed > 0:
            awake_pct = round((awake_m / total_bed) * 100.0, 1)
        else:
            awake_pct = 0.0

        b30_deep_sec = bm.get("deep_sleep_seconds", {}).get("avg") or bm_180.get("deep_sleep_seconds", {}).get("avg")
        b30_rem_sec = bm.get("rem_sleep_seconds", {}).get("avg") or bm_180.get("rem_sleep_seconds", {}).get("avg")
        b30_light_sec = bm.get("light_sleep_seconds", {}).get("avg") or bm_180.get("light_sleep_seconds", {}).get("avg")
        b30_awake_sec = bm.get("awake_duration_seconds", {}).get("avg") or bm_180.get("awake_duration_seconds", {}).get("avg")
        b30_dur_sec = bm.get("sleep_duration_seconds", {}).get("avg") or bm_180.get("sleep_duration_seconds", {}).get("avg")

        base_dur = float(b30_dur_sec) if b30_dur_sec else (sleep_dur_val if sleep_dur_val > 0 else 25200.0)

        deep_base_val = float(b30_deep_sec) if b30_deep_sec is not None else base_dur * 0.18
        rem_base_val = float(b30_rem_sec) if b30_rem_sec is not None else base_dur * 0.22
        light_base_val = float(b30_light_sec) if b30_light_sec is not None else base_dur * 0.55
        awake_base_val = float(b30_awake_sec) if b30_awake_sec is not None else base_dur * 0.05

        b30_deep_m = round(deep_base_val / 60.0, 1)
        b30_rem_m = round(rem_base_val / 60.0, 1)
        b30_light_m = round(light_base_val / 60.0, 1)
        b30_awake_m = round(awake_base_val / 60.0, 1)

        b30_total_asleep = b30_deep_m + b30_rem_m + b30_light_m
        b30_total_bed = b30_total_asleep + b30_awake_m

        if b30_total_asleep > 0:
            b30_deep_pct = round((b30_deep_m / b30_total_asleep) * 100.0, 1)
            b30_rem_pct = round((b30_rem_m / b30_total_asleep) * 100.0, 1)
            b30_light_pct = round((100.0 - b30_deep_pct - b30_rem_pct), 1)  # Ensure exact 100.0% sum
        else:
            b30_deep_pct = b30_rem_pct = b30_light_pct = 0.0

        if b30_total_bed > 0:
            b30_awake_pct = round((b30_awake_m / b30_total_bed) * 100.0, 1)
        else:
            b30_awake_pct = 0.0

        b30_deep_str = f"{b30_deep_m}m ({b30_deep_pct}%)"
        b30_rem_str = f"{b30_rem_m}m ({b30_rem_pct}%)"
        b30_light_str = f"{b30_light_m}m ({b30_light_pct}%)"
        b30_awake_str = f"{b30_awake_m}m ({b30_awake_pct}%)"

        if sleep_dur_val > 0 and sleep_dur_val < 18000:
            h_sleep = round(sleep_dur_val / 3600.0, 1)
            sleep_supercomp_directive = (
                f"3. BẢO VỆ TÍNH CHUẨN XÁC Y HỌC KHI THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG - thực tế = {h_sleep}h):\n"
                f"   * TUYỆT ĐỐI KHÔNG ca ngợi thời lượng Deep Sleep ({deep_m}m) là 'Siêu phục hồi xuất sắc' (Supercompensation)!\n"
                f"   * BẮT BUỘC nhận định chính xác theo sinh lý học giấc ngủ: 'Cơ thể phải nén sóng não chậm (Deep Sleep Rebound) để cấp cứu tổn thương tế bào do thời gian ngủ bị cắt ngắn nghiêm trọng.'\n"
                f"   * Trong bảng đối chuẩn 'Sleep Norms Benchmark', cột Đánh giá của dòng Deep Sleep ghi: 'Nén sóng chậm cấp cứu (Deep Sleep Rebound do thiếu ngủ)' thay vì 'Siêu phục hồi'."
            )
        else:
            sleep_supercomp_directive = (
                "3. BẮT BUỘC phân tích và nhận định rõ xem đêm qua có phải là đêm 'Siêu phục hồi' (Supercompensation) bù đắp cho sự thiếu hụt các ngày trước hay không."
            )

        parts.append(
            f"\n📊 DỮ LIỆU TÍNH TOÁN BẢNG ĐỐI CHUẨN GIẤC NGỦ (SLEEP NORMS BENCHMARK FOR SECTION 2):\n"
            f"- Deep Sleep Đêm qua: {deep_m} phút ({deep_pct}%) | Baseline 30d: {b30_deep_str} | Chuẩn Y học Thể thao: 15% - 25%\n"
            f"- REM Sleep Đêm qua: {rem_m} phút ({rem_pct}%) | Baseline 30d: {b30_rem_str} | Chuẩn Y học Thể thao: 20% - 25%\n"
            f"- Light Sleep Đêm qua: {light_m} phút ({light_pct}%) | Baseline 30d: {b30_light_str} | Chuẩn Y học Thể thao: 50% - 60%\n"
            f"- Awake Đêm qua: {awake_m} phút ({awake_pct}% trên Total Bed Time) | Baseline 30d: {b30_awake_str} | Chuẩn Y học Thể thao: < 5%\n"
            f"⚠️ YÊU CẦU BẮT BUỘC TRONG MỤC 2:\n"
            f"1. Phải xuất Bảng Markdown 'Sleep Norms Benchmark' theo đúng 5 cột: | Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |\n"
            f"2. BẮT BUỘC sử dụng các con số Baseline 30d đã tính toán ở trên ({b30_deep_str}, {b30_rem_str}, v.v.), THAY THẾ TRIỆT ĐỂ CHỮ N/A trong bảng đối chuẩn!\n"
            f"3. RÀNG BUỘC TOÁN HỌC TỶ LỆ PHA GIẤC NGỦ (DETERMINISTIC SLEEP STAGE MATH):\n"
            f"   - Total Bed Time = Deep + REM + Light + Awake = {tot_bed_min} phút ({tot_bed_display})\n"
            f"   - Time Asleep = Deep + REM + Light = {tot_sleep_min} phút ({tot_sleep_display})\n"
            f"   - Tỷ lệ % của các pha ngủ (Deep %, REM %, Light %) BẮT BUỘC tính trên Time Asleep ({tot_sleep_min}m) và tổng chính xác 100.0%: Deep {deep_pct}% + REM {rem_pct}% + Light {light_pct}% = 100.0%.\n"
            f"   - Tỷ lệ Awake % ({awake_pct}%) BẮT BUỘC tính trên Total Bed Time ({tot_bed_min}m) (Awake / Total Bed Time = {awake_m}m / {tot_bed_min}m).\n"
            f"   - Ràng buộc khớp số học: Tổng thời gian ngủ (Total Sleep Time) trong văn bản BẮT BUỘC phải bằng chính xác tổng số phút của (Deep Sleep + REM Sleep + Light Sleep) = {tot_sleep_min} phút = {tot_sleep_h} giờ {tot_sleep_m} phút ({tot_sleep_h}h {tot_sleep_m}m). Tuyệt đối không làm tròn lệch phút so với bảng số liệu.\n"
            f"{sleep_supercomp_directive}\n"
            f"4. QUY TẮC RENDER BẢNG: Bảng Markdown PHẢI viết sát lề trái (không thụt lề đầu dòng), có 1 dòng trống trước và sau bảng để hiển thị hoàn hảo trên Web Dashboard."
        )

        # Check Acute REM Collapse / Alcohol Suppression Syndrome
        is_rem_suppressed = (rem_pct < 5.0 or rem_m == 0.0 or (rem_base_val > 0 and rem_sec_val <= rem_base_val * 0.35))
        rem_drop_pct = round(((rem_base_val - rem_sec_val) / rem_base_val) * 100.0, 1) if rem_base_val > 0 else 0.0

        if is_rem_suppressed:
            parts.append(
                f"\n🚨 CẢNH BÁO LÂM SÀNG BẤT THƯỜNG: HỘI CHỨNG MẤT PHA REM (ACUTE REM SLEEP COLLAPSE / ALCOHOL SUPPRESSION SYNDROME):\n"
                f"- Tỷ lệ REM đêm qua: {rem_m} phút ({rem_pct}%) | Baseline 30d: {b30_rem_str} (Sụt giảm -{rem_drop_pct}% so với mức nền 30 ngày; Chuẩn Y học Thể thao: 20% - 25%).\n"
                f"- Tình trạng sinh lý đi kèm: RHR đêm: {tm.get('resting_heart_rate')} bpm | HRV đêm: {tm.get('hrv_last_night')} ms | Stress đêm: {tm.get('sleep_stress')} (Đỉnh {tm.get('sleep_stress_max') or 'cao'}) | Awake: {awake_m}m ({awake_pct}%).\n"
                f"⚠️ CHỈ ĐẠO LÂM SÀNG BẮT BUỘC TRONG MỤC 2 (BẢNG ĐỐI CHUẨN & ĐỐI CHIẾU DINH DƯỠNG/ĐỒ NHẬU):\n"
                f"1. BẮT BUỘC đánh giá dòng REM Sleep: Ghi rõ 'Bất thường (Mất pha REM hoàn toàn/Sụt giảm nghiêm trọng)' và phân tích sự suy giảm phục hồi nhận thức, trí nhớ cơ bắp và hệ thần kinh trung ương.\n"
                f"2. ĐỐI CHIẾU ĐỒ NHẬU & CỒN (PHÂN TÍCH NGUYÊN NHÂN LÂM SÀNG):\n"
                f"   * Nếu có cồn trong nhật ký hôm qua (alcohol_units > 0): Khẳng định cồn là tác nhân gây mất pha REM và tăng stress tim mạch nửa sau đêm.\n"
                f"   * Nếu KHÔNG có cồn hoặc nhật ký thiếu bữa tối: TUYỆT ĐỐI NGHIÊM CẤM kết luận rằng dạ dày rỗng lý tưởng hay phục hồi tốt! BẮT BUỘC đưa ra cảnh báo nghi vấn lâm sàng: Mất pha REM kèm stress đêm cao là dấu hiệu điển hình của việc sử dụng bia/rượu hoặc đồ ăn dầu mỡ tối muộn chưa được ghi nhận (Unlogged alcohol intake). Đặt câu hỏi truy vấn VĐV. Nếu không dùng cồn, phải kết luận cơ thể đang bị Kiệt quệ hệ thần kinh trung ương cấp tính (Acute CNS Exhaustion / Central Fatigue) sau vận động tích lũy và cần nghỉ ngơi phục hồi khẩn cấp!"
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
        em_instructions = [
            f"  1. Kê đơn giấc ngủ ngắn ban ngày: Power Nap 20 phút (hoặc chu kỳ 90 phút trước 14:30).",
            f"  2. Cấm tuyệt đối chất kích thích/caffeine sau 12:00 trưa.",
            f"  3. Bổ sung bữa phụ giàu Carb giải phóng chậm + Tryptophan lúc 20:00 (1/2 quả chuối chín hoặc 100ml sữa tách béo ấm; CẤM TUYỆT ĐỐI hạt hạnh nhân/chất béo > 3g fat trong vòng 2 tiếng trước khi đi ngủ 21:30) HOẶC gộp tinh bột vào bữa tối 19:00 và bỏ bữa phụ 20:00."
        ]
        if not allow_running:
            em_instructions.append(f"  4. {mandatory_exercise_directive}")

        parts.append(
            f"\n🚨 TỰ ĐỘNG KÍCH HOẠT EMERGENCY RECOVERY PROTOCOL (CẤP CỨU THỂ TRẠNG):\n"
            f"- Lý do kích hoạt: {', '.join(em_reasons)}.\n"
            f"- AI BẮT BUỘC kê đơn Emergency Recovery Protocol trong các Mục 2, 3, 4:\n" +
            "\n".join(em_instructions)
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

    days_left = race_info.get("days_to_race") if race_info else None
    is_close_race = (days_left is not None and days_left <= 7)

    readiness_val = float(readiness_score) if readiness_score is not None else 100.0

    if readiness_val < 30.0:
        achilles_rule3_str = (
            "Do Training Readiness < 30/100 (cơ thể kiệt sức/thiếu ngủ): TUYỆT ĐỐI CẤM kê đơn bài tập 'Eccentric Heel Drops' (hạ gót trên mép bậc thang) vì tải kéo giãn động này có thể làm tổn thương sợi collagen gân gót khi cơ bắp đang mệt mỏi! "
            "CHỈ ĐƯỢC CHỈ ĐỊNH: Bài tập đẳng trường giữ tĩnh 'Isometric Holds' trên mặt phẳng (đứng 2 chân nhón nhẹ 2-3cm giữ tĩnh 30s) hoặc nghỉ ngơi thụ động hoàn toàn (gác chân lên tường 10-15 phút)."
        )
    else:
        achilles_rule3_str = (
            "Bài tập hạ gót thụ động 'Eccentric Heel Drops' (3 set x 10-12 lần mép bậc thang) là BẮT BUỘC chỉ định ngoài đường chạy để xả tải gân Achilles trái theo Rule 3 (kết hợp Isometric Holds 3 set x 30-45s, Foam Roller giải phóng cơ mông nhỡ chân phải và Magie Bisglycinate 300-400mg)."
        )

    if gct_left_high or (tm.get("gct_balance") and float(str(tm.get("gct_balance")).split("%")[0]) >= 51.5):
        parts.append(
            f"\n⚠️ CỜ CHỈ DẪN BẢO VỆ GÂN ACHILLES TRÁI (GCT BALANCE LEFT = {gct_val_display}% >= 51.5%):\n"
            f"- AI BẮT BUỘC cảnh báo nguy cơ xung chấn va đập cơ học dồn lên gân gót trái (Achilles Left).\n"
            f"- Khi xa ngày thi đấu (days_to_race > 7): Nhắc nhở duy trì guồng chân Cadence 178 - 182 spm để đưa GCT Balance về 50.3% L (đi kèm thu ngắn sải chân).\n"
            f"- Giai đoạn sát giải (days_to_race <= 7 HOẶC T-1/T-2): TUYỆT ĐỐI KHÔNG đưa ra khuyến nghị 'hướng tới Cadence 178-182 spm'. Bắt buộc chỉ dẫn: 'Chạy sải bước ngắn tự nhiên, lướt sát đất'. {achilles_rule3_str}"
        )

    is_high_risk_exercise = (readiness_val < 40) or gct_left_high or (tm.get("gct_balance") and float(str(tm.get("gct_balance")).split("%")[0]) > 51.0)

    if not allow_running:
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Nghỉ ngơi hoàn toàn - CẤM CHẠY DO THIẾU NGỦ < 5 TIẾNG): Nghỉ ngơi hoàn toàn (Full Rest Day) để tái tạo thần kinh cơ và bảo vệ gân Achilles trái. Bổ sung bài tập tĩnh Isometric Holds trên mặt phẳng (đứng 2 chân nhón nhẹ 2-3cm giữ 30s x 3 set). PROHIBIT (NGHIÊM CẤM): NGHIÊM CẤM TUYỆT ĐỐI chạy bộ (kể cả shakeout run 2-3km) để bảo vệ gân Achilles trái. CẤM Strides, Tempo, Interval.\n"
            f"  + LỰA CHỌN 2 (Phục hồi không trọng lực): Bơi sải thả lỏng không trọng lực 500m Zone 1 (triệt tiêu 90% trọng lực) HOẶC đi bộ nhẹ nhàng 15 phút. Kết hợp foam roller nhẹ nhàng giải phóng bắp chân."
        )
    elif phase == "POST_RACE_ACUTE":
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Active Recovery Post-Race Acute D+1 đến D+7): Đi bộ nhẹ nhàng 15-20 phút / Bơi lội thả lỏng Zone 1 thư giãn (triệt tiêu 90% trọng lực lên gân cơ) hoặc dùng foam roller nhẹ nhàng giải phóng bắp chân & cơ mông. PROHIBIT (NGHIÊM CẤM): CẤM CHẠY HOÀN TOÀN. CẤM kê các bài tập Strides, Tempo, bứt tốc, biến tốc hay gò ép sải chân/cadence. Tuyệt đối KHÔNG nhầm lẫn với Tapering.\n"
            f"  + LỰA CHỌN 2 (Nghỉ ngơi hoàn toàn - Complete Rest): Nghỉ ngơi hoàn toàn (Full Rest Day) để hệ cơ bắp và sợi cơ vi tổn thương sau giải FM 42.195km tự tái tạo. Bổ sung bài tập tĩnh Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set) để bảo vệ gân Achilles."
        )
    elif phase == "POST_RACE_RECOVERY":
        from src.analytics.training_prescriber import prescribe_running_workout
        rec_time_val = tm.get("recovery_time_hours")
        hrv_status_val = tm.get("hrv_status")
        gct_balance_val = tm.get("gct_balance")
        d_pct_val = deep_pct if ('deep_pct' in locals() and deep_pct > 0) else None
        r_pct_val = rem_pct if ('rem_pct' in locals() and rem_pct > 0) else None
        presc = prescribe_running_workout(
            readiness_score=readiness_score,
            recovery_time_hours=rec_time_val,
            deep_sleep_pct=d_pct_val,
            rem_sleep_pct=r_pct_val,
            sleep_duration_seconds=sleep_dur_sec,
            hrv_status=hrv_status_val,
            gct_balance=gct_balance_val,
            days_since_race=d_val,
            phase=phase
        )
        if presc["status"] == "GO_RUN":
            exercise_options_str = (
                f"  + LỰA CHỌN 1 ({presc['option_1']['title']} - ĐẠT ĐỦ ĐIỀU KIỆN REVERSE TAPER: Readiness {readiness_score} >= 65, Recovery Time {rec_time_val}h <= 6h, HRV {hrv_status_val}): {presc['option_1']['description']} {presc['achilles_directive']}\n"
                f"  + LỰA CHỌN 2 ({presc['option_2']['title']}): {presc['option_2']['description']}"
            )
        elif presc["status"] == "OPTIONAL_ACTIVE_RECOVERY":
            exercise_options_str = (
                f"  + LỰA CHỌN 1 ({presc['option_1']['title']}): {presc['option_1']['description']} {presc['achilles_directive']}\n"
                f"  + LỰA CHỌN 2 (Nghỉ ngơi hoàn toàn - Complete Rest): {presc['option_2']['description']}"
            )
        else:
            exercise_options_str = (
                f"  + LỰA CHỌN 1 (Active Recovery / Đi bộ nhẹ - CHƯA ĐẠT ĐIỀU KIỆN CHẠY: {presc['reason'] or 'Readiness < 65 hoặc Recovery Time > 6h hoặc HRV chưa Balanced'}): Đi bộ nhẹ nhàng 15 phút hoặc bơi thả lỏng thư giãn Zone 1. PROHIBIT (NGHIÊM CẤM): CẤM chạy bộ, cấm Strides, Tempo, Interval. Tiếp tục bổ sung bài tập tĩnh Isometric Holds trên mặt phẳng (nhón gót 2-3cm giữ 30s x 3 set) để bảo vệ gân Achilles.\n"
                f"  + LỰA CHỌN 2 (Nghỉ ngơi hoàn toàn - Complete Rest): Nghỉ ngơi hoàn toàn (Rest Day) để cơ thể và gân gót tiếp tục hồi phục."
            )
    elif is_close_race:
        heel_drop_choice = (
            "TUYỆT ĐỐI CẤM Eccentric Heel Drops khi Readiness < 30. CHỈ ĐƯỢC chỉ định Isometric Holds trên mặt phẳng hoặc nghỉ ngơi thụ động (gác chân lên tường 10-15 phút)."
            if readiness_val < 30.0 else
            "Bài tập hạ gót thụ động 'Eccentric Heel Drops' (3 set x 10-12 lần mép bậc thang) là BẮT BUỘC chỉ định ngoài đường chạy để xả tải gân Achilles trái theo Rule 3."
        )
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Shakeout Run nhẹ nhàng sát giải - RULE 3): Shakeout Run nhẹ nhàng 15-20 phút Zone 1/2 (HR < 135 bpm). Chạy sải bước ngắn tự nhiên, lướt sát đất. PROHIBIT (NGHIÊM CẤM): TUYỆT ĐỐI KHÔNG gợi ý chạy bứt tốc, Strides, Interval hay bất kỳ bài tập tăng tốc nào. TUYỆT ĐỐI KHÔNG đưa ra khuyến nghị 'hướng tới Cadence 178-182 spm'.\n"
            f"  + LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực hoặc Rest Day): Bơi sải thả lỏng 500m - 800m (Zone 1/2) hoặc nghỉ ngơi hoàn toàn. {heel_drop_choice}"
        )
    elif is_high_risk_exercise:
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Chạy bộ Zone 2 phẳng): Chạy nhẹ MAF 20-30 phút (HR < 136-140 bpm, ưu tiên hàng đầu nhịp tim Zone 2). Chạy sải bước ngắn tự nhiên, lướt sát đất. Nếu tim tăng vọt: Chạy chậm lại hoặc đi bộ. PROHIBIT (NGHIÊM CẤM): Strides bứt tốc 85-90%, intervals tốc độ cao, downhill sprints.\n"
            f"  + LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực): Bơi sải thả lỏng 800m - 1.000m (Zone 1/2). Triệt tiêu 90% áp lực trọng lực lên gân gót chân trái. Cảnh báo tuyệt đối không đạp chân ếch mạnh."
        )
    else:
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Chạy bộ - Neuromuscular Priming): Chạy nhẹ MAF 25-30 phút (<136-140 bpm, thu ngắn sải chân bước nhỏ) + 4-5 tổ Strides 80m nhẹ kỹ thuật (Cadence 180-184 spm, thu ngắn sải chân).\n"
            f"  + LỰA CHỌN 2 (Bơi lội - Phục hồi không trọng lực): Bơi sải thả lỏng 800m - 1.000m (Zone 1/2), xen kẽ 3-4 đoạn 25m guồng tay nhanh. Triệt tiêu 90% áp lực trọng lực lên gân gót chân trái. Cảnh báo không đạp chân ếch mạnh."
        )

    if not allow_running:
        exercise_options_str = (
            f"  + LỰA CHỌN 1 (Nghỉ ngơi hoàn toàn - CẢNH BÁO THIẾU NGỦ CẤP TÍNH < 5 TIẾNG): {mandatory_exercise_directive}\n"
            f"  + LỰA CHỌN 2 (Phục hồi không trọng lực): Bơi sải thả lỏng không trọng lực 500m Zone 1 triệt tiêu 90% trọng lực lên gân cơ."
        )
        parts.append(
            f"\n🛑 KHÓA CỨNG BÀI TẬP VẬN ĐỘNG DO THIẾU NGỦ CẤP TÍNH (ACUTE SLEEP DEPRIVATION HARD LOCK):\n"
            f"- {mandatory_exercise_directive}\n"
            f"- AI BẮT BUỘC LOẠI BỎ HOÀN TOÀN bài chạy bộ (kể cả Shakeout run 2-3km) khỏi LỰA CHỌN 1 và LỰA CHỌN 2 trong Mục 3, bất kể điểm Readiness là bao nhiêu ({_format_value(readiness_score)}/100).\n"
            f"- Mục 3 BẮT BUỘC chỉ định: Lựa chọn 1 = Nghỉ ngơi hoàn toàn (Rest Day); Lựa chọn 2 = Bơi sải thả lỏng không trọng lực 500m Zone 1."
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
    tot_alc_prev = 0.0
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

        # Check Alcohol and REM Suppression in Yesterday's Log
        tot_alc_prev = sum(float(log.get("alcohol_units") or 0.0) for log in nut_logs_prev)
        if tot_alc_prev > 0:
            parts.append(
                f"🍺 XÁC NHẬN CỒN HÔM QUA ({tot_alc_prev} đơn vị):\n"
                f"- VĐV có sử dụng đồ uống có cồn. BẮT BUỘC chỉ rõ trong Mục 2 tác động của ethanol lên việc ức chế pha REM và làm tăng stress tim mạch ban đêm.\n"
                f"- GIAO THỨC ĐÀO THẢI ACID URIC HẬU ĐỒ UỐNG CÓ CỒN (POST-ALCOHOL URIC ACID FLUSH PROTOCOL):\n"
                f"  Vận động viên có nồng độ Acid Uric nền 442 µmol/L (vượt trần bão hòa EULAR 420 µmol/L). Khi nạp {tot_alc_prev} đơn vị cồn, nguy cơ kết tinh tinh thể Urate và viêm gân gót Achilles tăng vọt.\n"
                f"  Báo cáo (đặc biệt trong Mục 4) BẮT BUỘC phải quy định rõ ràng giao thức bù nước kiềm nguyên văn:\n"
                f"  'Uống tối thiểu 3.0L - 3.2L nước rải đều trong ngày, ưu tiên nước khoáng kiềm pH 8.5-9.0 (Fujiwa) để nâng pH nước tiểu, chống lắng đọng tinh thể urat tại gân Achilles.'"
            )
        elif is_rem_suppressed:
            parts.append(
                f"⚠️ ĐỐI SOÁT DINH DƯỠNG & MẤT PHA REM: Không ghi nhận cồn nhưng pha REM bị triệt tiêu ({rem_m}m / {rem_pct}%).\n"
                f"-> NGHIÊM CẤM kết luận dạ dày rỗng lý tưởng! Phải đặt nghi vấn lâm sàng về bia/rượu chưa log hoặc cảnh báo kiệt quệ thần kinh trung ương cấp."
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

    is_post_race_cur = phase in ("POST_RACE_ACUTE", "POST_RACE_RECOVERY")

    if is_post_race_cur:
        d_val = days_since or (3 if phase == "POST_RACE_ACUTE" else 8)
        day_type_str = f"Post-Race Recovery Day (Giai đoạn Hậu Marathon D+{d_val})"
    elif days_left is not None and 1 <= days_left <= 3:
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
            f"Buổi chiều CHỈ ĐƯỢC kê đơn phục hồi thụ động (stretching thả lỏng gân cơ, bài tập đẳng trường tĩnh isometric holds, ngâm chân nước ấm/mát)."
        )
    elif is_post_race_cur:
        d_val = days_since or (3 if phase == "POST_RACE_ACUTE" else 8)
        parts.append(
            f"\n⚡ QUY TẮC TIÊU ĐỀ & KÊ ĐƠN CHO MỤC 3 (GIAI ĐOẠN HẬU MARATHON):\n"
            f"1. TIÊU ĐỀ MỤC 3 BẮT BUỘC ĐẶT LÀ: '### 🏃‍♂️ 3. Kê đơn Vận động & Phục hồi Thể thao (Giai đoạn Hậu Marathon D+{d_val}):'\n"
            f"2. XÓA BỎ VĨNH VIỄN CỤM TỪ 'Dynamic Tapering' hay bất kỳ từ khóa Tapering nào trong Mục 3.\n"
            f"3. ĐẢM BẢO KHÔNG BAO GIỜ NHẦM LẪN giữa phục hồi sau giải (Post-Race) với giảm tải trước giải (Tapering)."
        )

    from src.services.nutrition_calculator import calculate_daily_macro_targets
    macro_targets = calculate_daily_macro_targets(
        weight_kg=w_eff,
        day_type="post_race_acute" if phase == "POST_RACE_ACUTE" else ("post_race_recovery" if phase == "POST_RACE_RECOVERY" else day_type_str),
        uric_acid_umol_l=442.0,
        active_calories_garmin=act_cals_today,
        days_to_race=days_left,
        days_since_race=days_since
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

        if report_type == "midday":
            from src.analytics.midday_review import calculate_evening_targets, detect_high_purine_lunch
            dt_mid = {"protein": target_p, "carb": target_c, "fat": target_f, "calories": target_cal}
            li_mid = {"protein": tot_p_today, "carb": tot_c_today, "fat": tot_f_today, "calories": tot_cal_today}
            din_p_target, din_c_target, fat_status = calculate_evening_targets(dt_mid, li_mid, uric_acid_level=442.0)
            din_p_cap = round(din_p_target, 1)
            snack_p = round(max(0.0, rem_p - din_p_cap), 1) if rem_p > 0 else 0.0

            lunch_dishes = []
            lunch_prot = 0.0
            for log in nut_logs_today:
                m_type = str(log.get("meal_type") or "").lower()
                ts = str(log.get("timestamp") or "")
                if any(kw in m_type for kw in ["trưa", "lunch"]) or ("11:" in ts or "12:" in ts or "13:" in ts):
                    lunch_dishes = log.get("dishes") or []
                    lunch_prot = float(log.get("protein_g") or 0.0)
                    break
            if not lunch_dishes and len(nut_logs_today) > 1:
                lunch_dishes = nut_logs_today[-1].get("dishes") or []
                lunch_prot = float(nut_logs_today[-1].get("protein_g") or 0.0)
            purine_res = detect_high_purine_lunch(lunch_dishes, lunch_prot, uric_acid_level=442.0)
        else:
            default_din_cap = 28.0 if is_post_race_cur else 30.0
            din_p_cap = round(min(macro_dict.get("dinner_protein_cap", default_din_cap), rem_p if rem_p > 0 else default_din_cap), 1)
            snack_p = round(max(0.0, rem_p - din_p_cap), 1) if rem_p > 0 else 0.0
            din_c_target = 70.0
            fat_status = "EXCEEDED" if (target_f - tot_f_today) <= 0 else "AVAILABLE"
            purine_res = {"is_high_purine": False}

        p_status_str = f"Đã nạp cả ngày: {tot_p_today}g / Mục tiêu: {target_p}g"
        if tot_p_today > target_p:
            p_surplus = round(tot_p_today - target_p, 1)
            p_recap_instruction = f"{p_status_str} (Thừa +{p_surplus}g Protein, bữa tối vượt trần đạm an toàn)."
        elif rem_p > 5:
            p_recap_instruction = f"{p_status_str} (Còn thiếu {rem_p}g Protein cho hôm nay)."
        else:
            p_recap_instruction = f"{p_status_str} (Chuẩn đạt mục tiêu)."

        nut_constraint_4 = (
            f"4. RÀNG BUỘC POST-RACE NUTRITION & QUY CHUẨN THỰC CHIẾN DÂN DÃ: Chấm dứt Carbo-loading. Carb 45-50% TDEE ({target_c}g). "
            f"Protein nâng lên dải phục hồi mô cơ ~1.4 - 1.5 g/kg ({target_p}g/ngày), ưu tiên đạm trắng dễ tiêu hóa (ức gà nạc, cá, trứng, đậu phụ). "
            f"{p_recap_instruction} Khóa trần Protein an toàn bữa tối <= {din_p_cap}g (Bảo vệ Acid Uric 442 µmol/L). "
            f"CHỈ DẪN LÀM DỊU ĐƯỜNG TIÊU HÓA: Tránh thực phẩm kích thích co thắt đại tràng (chua cay, đường đơn đậm đặc, dầu mỡ). "
            f"CẤM TUYỆT ĐỐI: Không gợi ý 'Yến mạch cán vỡ' hay ngũ cốc thô trong pha phục hồi ruột nhạy cảm. Không viết theo kiểu cân đong tiểu ly phi thực tế (như '180g gạo chín', '40g thịt thăn'). "
            f"QUY CHUẨN MÓN ĂN THỰC TẾ (Định lượng theo bát/đĩa thông thường):\n"
            f"   - Bữa sáng: 1 Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ + hành hoa thái nhỏ + 1 quả trứng gà luộc chín tới (HOẶC: 1 Bát phở gà nạc nước trong: bỏ da, không váng mỡ, không quẩy).\n"
            f"   - Bữa trưa: 1.5 bát con cơm trắng mềm + Đạm nạc (1 lạng ức gà luộc HOẶC 1 khúc cá nạc hấp/áp chảo ít dầu HOẶC 1 lạng tôm hấp bóc vỏ) + 1 bát canh bí đao/mồng tơi/bầu nấu thịt nạc băm (nước trong).\n"
            f"   - Bữa xế chiều: {snack_example_str}. Dòng chi tiết món ăn bữa phụ chiều BẮT BUỘC ghi: Protein ~{snack_p}g.\n"
            f"   - Bữa tối: 1 bát con cơm trắng mềm (~130-150g, ~38-40g Carb) + Đậu phụ non sốt cà chua nhạt (1 bìa) + Ức gà nạc áp chảo / thịt nạc thăn băm nhỏ (hoặc 1 quả trứng gà luộc, TUYỆT ĐỐI KHÔNG dùng tôm/hải sản tối để ngừa lắng đọng Acid Uric) + Canh rau luộc nước trong. Dòng chi tiết món ăn bữa tối ghi nhận: Protein ~{din_p_cap}g.\n"
            if is_post_race_cur else
            f"4. RÀNG BUỘC CARBO-LOADING TAPERING (days_to_race <= 3): Chế độ Low-Residue: BẮT BUỘC chỉ gợi ý Carb sạch, ít xơ (cơm trắng, bánh mì gối trắng quết mật ong, chuối tiêu, bánh canh/phở nước trong). KHÔNG gợi ý sữa chua Hy Lạp Chobani vào bữa chiều/tối nếu tổng đạm tích lũy trong ngày đã đạt >= 55g ({tot_p_today}g đạm đã nạp).\n"
        )

        rem_c_today = max(0.0, round(target_c - tot_c_today, 1))
        unconsumed_c = max(0.0, round(rem_c_today - (45.0 + din_c_target), 1))

        if report_type == "midday":
            rule_6_text = (
                f"6. KHÓA LÂM SÀNG BỮA TỐI & CHỐNG HỘI CHỨNG CARB-DUMPING (CLINICAL GUARDS CHO MIDDAY REVIEW):\n"
                f"   - Trần Carb bữa tối (Clinical Guard 2): BẮT BUỘC khống chế tối đa {din_c_target}g Carb (~1 - 1.5 bát con cơm trắng mềm). Tuyệt đối CẤM dồn/dump lượng Carb còn thiếu lớn ({rem_c_today}g) vào bữa tối để ép khớp calo ngày. Lượng Carb chưa nạp đủ ban ngày (~{unconsumed_c}g Carb) được ghi nhận là 'Chưa nạp trong khung giờ hoạt động (bỏ qua)', KHÔNG dồn/dump vào ban đêm.\n"
                f"   - Sàn chất béo tự nhiên (Clinical Guard 3 - Realistic Fat Floor): Trạng thái Fat ngày: {fat_status}. Các món đạm thanh đạm (đậu phụ non, trứng luộc, ức gà) luôn chứa chất béo nội tại tự nhiên (~5-7g Fat/bữa). TUYỆT ĐỐI KHÔNG ảo giác gán 0.0g Fat cho bữa tối!\n"
                f"   - Bù trừ Protein: {target_p}g (Mục tiêu) - {tot_p_today}g (Đã nạp) = {rem_p}g Protein (Còn thiếu). Kê đơn bữa phụ chiều ({snack_p}g) + bữa tối ({din_p_cap}g) khớp đúng bằng {rem_p}g Protein.\n"
            )
            if purine_res.get("is_high_purine"):
                rule_6_text += (
                    f"   - 🚨 CẢNH BÁO TẢI PURINE BỮA TRƯA & GIAO THỨC KIỀM HÓA:\n"
                    f"     {purine_res['warning_message']}\n"
                    f"     {purine_res['counter_measure_protocol']}\n"
                )
            rule_10_text = (
                "10. ⚠️ BỎ HOÀN TOÀN FOOTER CŨ (STALE FOOTER REMOVAL): "
                "Báo cáo Midday Review TUYỆT ĐỐI KHÔNG in ghi chú '💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. "
                "Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse).' "
                "vào cuối báo cáo, vì buổi tập sáng và tiêu hao đã được tính toán đối soát trực tiếp."
            )
        else:
            rule_6_text = (
                f"6. BẢO ĐẢM TÍNH TOÁN CỘNG TRỪ MACRO CHÍNH XÁC: Phép tính bù trừ: {target_cal} kcal (Mục tiêu) - {tot_cal_today} kcal (Đã nạp) = {rem_cal} kcal (Còn thiếu); {target_p}g Protein (Mục tiêu) - {tot_p_today}g (Đã nạp) = {rem_p}g Protein (Còn thiếu). Kê đơn các bữa ăn còn lại sao cho tổng Calo và Protein từ thực đơn gợi ý BẮT BUỘC cộng lại vừa đúng bằng {rem_cal} kcal và {rem_p}g Protein, không được tính nhẩm sai lệch!\n"
            )
            rule_10_text = (
                "10. ⚠️ LƯU Ý ĐỘNG ĐẦU NGÀY (INTRADAY DYNAMIC NOTICE CHO MỤC 4):\n"
                "   BẮT BUỘC kết thúc Mục 4 bằng ghi chú nguyên văn:\n"
                "   '💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse).'"
            )

        alloc_eq_str = f" ({snack_p}g + {din_p_cap}g = {rem_p}g)" if rem_p > 0 else ""
        rule_2_text = (
            f"2. ĐỒNG BỘ TUYỆT ĐỐI SỐ LIỆU PROTEIN BỮA TỐI & BỮA PHỤ: "
            f"Trần bữa tối tiêu chuẩn là {din_p_cap}g Protein (TUYỆT ĐỐI KHÔNG ĐƯỢC VIẾT là 31.0g) (Acid Uric 442 µmol/L). "
            f"Phân bổ chuẩn: Bữa phụ chiều nhận đúng {snack_p}g Protein ({snack_alloc_label}), Bữa tối nhận chuẩn xác {din_p_cap}g Protein{alloc_eq_str} (đậu phụ non + ức gà nạc/thịt nạc thăn/trứng luộc, không dùng tôm/hải sản).\n"
        )

        parts.append(
            f"\nTỔNG HỢP DINH DƯỠNG ĐÃ NẠP HÔM NAY ({target_date}) [{day_type_str}]:\n"
            f"- Cân nặng thực tế: {w_eff} kg -> BMR cơ bản ~{bmr_est} kcal\n"
            f"- Đã nạp: ~{tot_cal_today} kcal / Mục tiêu ~{target_cal} kcal (Còn thiếu cho hôm nay: ~{rem_cal} kcal)\n"
            f"- Protein đã nạp: {tot_p_today}g / Mục tiêu ~{target_p}g ({p_recap_instruction})\n"
            f"- Carb đã nạp: {tot_c_today}g / Mục tiêu ~{target_c}g | Fat đã nạp: {tot_f_today}g / Mục tiêu ~{target_f}g\n"
            f"⚠️ QUY TẮC BẮT BUỘC ĐỘNG HÓA THỜI GIAN CHO MỤC 4 (KÊ ĐƠN DINH DƯỠNG VÀ TOÁN HỌC MACRO):\n"
            f"1. Mốc thời gian thực tế hiện tại là {current_time_str}. Chỉ kê đơn chi tiết các bữa ăn BẮT ĐẦU TỪ {current_time_str} TRỞ ĐI trong ngày. Tuyệt đối KHÔNG kê đơn các bữa ăn ở mốc giờ đã trôi qua.\n"
            f"{rule_2_text}"
            f"3. RÀNG BUỘC URIC ACID (>= 420 µmol/L): TUYỆT ĐỐI KHÔNG gợi ý thịt đỏ (thịt bò, thịt dê, phủ tạng) hay hải sản (tôm, cua, mực, nghêu, sò, ốc, tôm hùm). Bữa tối TUYỆT ĐỐI KHÔNG kê đơn tôm/hải sản do nguy cơ kết tinh tinh thể Urate ban đêm. Chỉ gợi ý đạm thanh đạm ít purin: Đậu phụ non, ức gà nạc không da, thịt nạc thăn heo băm, cá nạc nước ngọt hấp, trứng gà luộc.\n"
            f"{nut_constraint_4}"
            f"5. ĐỘNG HÓA ATWATER, CAM TƯƠI & CẤM BỊA ĐẶT MACRO CƠM TRẮNG: abs(Calo - (P*4 + C*4 + F*9)) <= 4.0 kcal cho từng món ăn. Không khống carb của 100g cam tươi (> 15g C, cam tươi thực tế 9.5g C, ~47 kcal). TUYỆT ĐỐI CẤM hạ khống Carb của 1 bát cơm trắng (~130-150g có ~35-40g Carb) xuống mức phi sinh học (như 10.7g C) chỉ để ép khớp quota! Phân bổ Carb còn thiếu vào tinh bột sạch (cơm trắng mềm, chuối chín, phở{', khoai lang' if not has_no_sweet_potato else ''}).\n"
            f"{rule_6_text}"
            f"7. TÍNH KHẢ THI BỮA TỐI: Khi gợi ý các bữa ăn có thời gian chế biến/dùng bữa kéo dài (như Lẩu hoặc tiệc tối gia đình): BẮT BUỘC bổ sung lưu ý thực tế: 'Nếu chọn ăn lẩu hoặc ăn ngoài, nên thu xếp hoàn tất bữa ăn trước giờ đi ngủ 2.5 - 3.0 tiếng, đảm bảo hệ tiêu hóa có đủ thời gian hoàn tất chu trình trước giờ ngủ.'\n"
            f"8. ⚠️ PHÂN BỔ CHẤT BÉO SẠCH TƯỜNG MINH (EXPLICIT HEALTHY FAT ALLOCATION CHO MỤC 4):\n"
            f"   - Mục tiêu Fat cả ngày hôm nay: ~{target_f}g Fat (Tổng Calo ~{target_cal} kcal).\n"
            f"   - Với thực đơn đạm nạc, thanh đạm, thấp purin (ức gà, trứng luộc, đậu phụ non, canh rau luộc), lượng chất béo tự nhiên chỉ đạt ~20-23g Fat (thiếu hụt > 15g so với target {target_f}g).\n"
            f"   - TUYỆT ĐỐI KHÔNG coi mỡ tự có trong đồ luộc/thịt nạc là đủ quota (không dùng 'Ghost Fat').\n"
            f"   - BẮT BUỘC kê đơn bổ sung chất béo sạch, dễ tiêu hóa một cách tường minh vào khâu chế biến từng bữa:\n"
            f"     * Bữa sáng: 'Dùng 1 thìa nhỏ dầu thực vật/dầu phi hành thơm nấu cháo' (+5g Fat).\n"
            f"     * Bữa trưa: 'Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc' (+5g Fat).\n"
            f"     * Bữa tối: 'Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc' (+5g Fat).\n"
            f"   - Đảm bảo Sum(Dish Fat) khớp với Daily Target Fat ({target_f}g) trong dung sai ±3g.\n"
            f"{('9. ⚠️ GIAO THỨC ĐÀO THẢI ACID URIC HẬU CỒN: Do đêm qua có cồn, BẮT BUỘC trong Mục 4 quy định rõ ràng giao thức bù nước kiềm: \"Uống tối thiểu 3.0L - 3.2L nước rải đều trong ngày, ưu tiên nước khoáng kiềm pH 8.5-9.0 (Fujiwa) để nâng pH nước tiểu, chống lắng đọng tinh thể urat tại gân Achilles.\"\n' if tot_alc_prev > 0 else '')}"
            f"{rule_10_text}\n"
        )
    else:
        din_p_cap = round(min(macro_dict.get("dinner_protein_cap", 28.0 if is_post_race_cur else 30.0), target_p), 1)
        nut_constraint_4 = (
            f"⚠️ RÀNG BUỘC POST-RACE NUTRITION & QUY CHUẨN THỰC CHIẾN DÂN DÃ: Chấm dứt Carbo-loading. Carb 45-50% TDEE ({target_c}g). "
            f"Protein nâng lên dải phục hồi mô cơ ~1.4 - 1.5 g/kg ({target_p}g/ngày), ưu tiên đạm trắng dễ tiêu hóa (ức gà nạc, cá, trứng, đậu phụ). "
            f"Khóa trần Protein bữa tối <= {din_p_cap}g (Bảo vệ Acid Uric 442 µmol/L). "
            f"CHỈ DẪN LÀM DỊU ĐƯỜNG TIÊU HÓA: Tránh thực phẩm kích thích co thắt đại tràng (chua cay, đường đơn đậm đặc, dầu mỡ). "
            f"CẤM TUYỆT ĐỐI: Không gợi ý 'Yến mạch cán vỡ' hay ngũ cốc thô trong pha phục hồi ruột nhạy cảm. Không viết theo kiểu cân đong tiểu ly phi thực tế (như '180g gạo chín', '40g thịt thăn'). "
            f"QUY CHUẨN MÓN ĂN THỰC TẾ (Định lượng theo bát/đĩa thông thường): "
            f"Bữa sáng: 1 Bát cháo gạo trắng nấu thịt nạc băm/ức gà xé nhỏ + hành hoa thái nhỏ + 1 quả trứng gà luộc chín tới (HOẶC: 1 Bát phở gà nạc nước trong: bỏ da, không váng mỡ, không quẩy). "
            f"Bữa trưa: 1.5 bát con cơm trắng mềm + Đạm nạc (1 lạng ức gà luộc HOẶC 1 khúc cá nạc hấp/áp chảo ít dầu HOẶC 1 lạng tôm hấp bóc vỏ) + 1 bát canh bí đao/mồng tơi/bầu nấu thịt nạc băm (nước trong). "
            f"Bữa xế chiều: {snack_example_str}. "
            f"Bữa tối: 1 bát con cơm trắng mềm (~130-150g, ~38-40g Carb) + Đậu phụ non sốt cà chua nhạt (1 bìa) + Ức gà nạc áp chảo / thịt nạc thăn băm nhỏ (hoặc 1 quả trứng gà luộc, TUYỆT ĐỐI CẤM tôm/hải sản tối để ngừa lắng đọng Acid Uric) + Canh rau luộc nước trong (Protein tối <= {din_p_cap}g, số Protein ở dòng chi tiết món ăn bữa tối PHẢI BẰNG CHÍNH XÁC {din_p_cap}g, tối đa {din_p_cap}g).\n"
            if is_post_race_cur else
            f"⚠️ RÀNG BUỘC CARBO-LOADING TAPERING (days_to_race <= 3): Chế độ Low-Residue: BẮT BUỘC chỉ gợi ý Carb sạch, ít xơ (cơm trắng, bánh mì gối trắng quết mật ong, chuối tiêu, bánh canh/phở nước trong).\n"
        )
        if report_type != "midday":
            empty_log_footer_rule = (
                "⚠️ LƯU Ý ĐỘNG ĐẦU NGÀY (INTRADAY DYNAMIC NOTICE CHO MỤC 4):\n"
                "BẮT BUỘC kết thúc Mục 4 bằng ghi chú nguyên văn:\n"
                "'💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse).'\n"
            )
        else:
            empty_log_footer_rule = "⚠️ BỎ HOÀN TOÀN FOOTER CŨ: Báo cáo Midday Review TUYỆT ĐỐI KHÔNG in ghi chú '💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng...'.\n"

        parts.append(
            f"Chưa ghi nhận bản ghi bữa ăn nào trong ngày hôm nay ({target_date}).\n"
            f"Cân nặng thực tế: {w_eff} kg -> BMR cơ bản ~{bmr_est} kcal | Loai ngày: {day_type_str}.\n"
            f"Mục tiêu cả ngày hôm nay: ~{target_p}g Protein, ~{target_f}g Fat, ~{target_c}g Carb, tổng ~{target_cal} kcal.\n"
            f"⚠️ QUY TẮC BẮT BUỘC ĐỘNG HÓA THỜI GIAN CHO MỤC 4: Mốc thời gian hiện tại là {current_time_str}. Chỉ kê đơn các bữa ăn từ {current_time_str} trở đi trong ngày, không ghi mốc giờ đã trôi qua!\n"
            f"⚠️ GIỚI HẠN PROTEIN BỮA TỐI (ĐỒNG BỘ TUYỆT ĐỐI): Protein bữa tối KHÔNG ĐƯỢC VƯỢT QUÁ {din_p_cap}g cho ngày Rest/Taper/Post-Race (bảo vệ thận & HRV đêm với Uric Acid 442 µmol/L). Số Protein ở dòng chi tiết món ăn bữa tối PHẢI BẰNG CHÍNH XÁC con số này (tối đa {din_p_cap}g).\n"
            f"⚠️ RÀNG BUỘC URIC ACID (>= 420 µmol/L): TUYỆT ĐỐI KHÔNG gợi ý thịt đỏ (thịt bò, thịt dê, phủ tạng) hay hải sản (tôm, cua, mực, nghêu, sò, ốc, tôm hùm). Bữa tối TUYỆT ĐỐI KHÔNG kê đơn tôm/hải sản do nguy cơ kết tinh tinh thể Urate ban đêm. Chỉ gợi ý đạm thanh đạm ít purin: Đậu phụ non, ức gà nạc không da, thịt nạc thăn heo băm, cá nạc nước ngọt hấp, trứng gà luộc.\n"
            f"{nut_constraint_4}"
            f"⚠️ ĐỘNG HÓA ATWATER, CAM TƯƠI & CẤM BỊA ĐẶT MACRO CƠM TRẮNG: abs(Calo - (P*4 + C*4 + F*9)) <= 4.0 kcal cho từng món ăn. Không khống carb của 100g cam tươi (> 15g C, cam tươi thực tế 9.5g C, ~47 kcal). TUYỆT ĐỐI CẤM hạ khống Carb của 1 bát cơm trắng (~130-150g có ~35-40g Carb) xuống mức phi sinh học (như 10.7g C) chỉ để ép khớp quota! Phân bổ Carb còn thiếu vào tinh bột sạch (cơm trắng mềm, chuối chín, phở{', khoai lang' if not has_no_sweet_potato else ''}).\n"
            f"⚠️ PHÂN BỔ CHẤT BÉO SẠCH TƯỜNG MINH (EXPLICIT HEALTHY FAT ALLOCATION CHO MỤC 4):\n"
            f"- Mục tiêu Fat cả ngày hôm nay: ~{target_f}g Fat (Tổng Calo ~{target_cal} kcal).\n"
            f"- Với thực đơn đạm nạc, thanh đạm, thấp purin (ức gà, trứng luộc, đậu phụ non, canh rau luộc), lượng chất béo tự nhiên chỉ đạt ~20-23g Fat (thiếu hụt > 15g so với target {target_f}g).\n"
            f"- TUYỆT ĐỐI KHÔNG coi mỡ tự có trong đồ luộc/thịt nạc là đủ quota (không dùng 'Ghost Fat').\n"
            f"- BẮT BUỘC kê đơn bổ sung chất béo sạch, dễ tiêu hóa một cách tường minh vào khâu chế biến từng bữa:\n"
            f"  * Bữa sáng: 'Dùng 1 thìa nhỏ dầu thực vật/dầu phi hành thơm nấu cháo' (+5g Fat).\n"
            f"  * Bữa trưa: 'Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc' (+5g Fat).\n"
            f"  * Bữa tối: 'Thêm 1 thìa cà phê (5ml) dầu mè hoặc dầu olive trộn vào canh/rau luộc' (+5g Fat).\n"
            f"- Đảm bảo Sum(Dish Fat) khớp với Daily Target Fat ({target_f}g) trong dung sai ±3g.\n"
            f"{('⚠️ GIAO THỨC ĐÀO THẢI ACID URIC HẬU CỒN: Do đêm qua có cồn, BẮT BUỘC trong Mục 4 quy định rõ ràng giao thức bù nước kiềm: \"Uống tối thiểu 3.0L - 3.2L nước rải đều trong ngày, ưu tiên nước khoáng kiềm pH 8.5-9.0 (Fujiwa) để nâng pH nước tiểu, chống lắng đọng tinh thể urat tại gân Achilles.\"\n' if tot_alc_prev > 0 else '')}"
            f"{empty_log_footer_rule}"
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
    """Post-processing cleaner to eliminate Chinese token bleed, meta-instruction leaks,
    developer debug pseudo-code, academic fluff, and normalize Garmin training status strings.
    """
    if not text:
        return ""

    # 1. Chinese token bleed replacements
    replacements = {
        "指数": "Chỉ số",
        "恢复": "Phục hồi",
        "睡眠": "Giấc ngủ",
        "压力": "Stress",
        "心率": "Nhịp tim",
    }
    for zh, vi in replacements.items():
        text = text.replace(zh, vi)

    # 2. Normalize raw Garmin Training Status codes (e.g. MAINTAINING_4 -> Duy trì (Maintaining))
    status_cleaners = {
        r'\bMAINTAINING(?:_\d+)?\b': "Duy trì (Maintaining)",
        r'(?<!EMERGENCY\s)(?<!POST_RACE_)(?<!ACUTE_REST_)\bRECOVERY(?:_\d+)?\b': "Phục hồi (Recovery)",
        r'\bPRODUCTIVE(?:_\d+)?\b': "Hiệu quả (Productive)",
        r'\bPEAKING(?:_\d+)?\b': "Đạt đỉnh (Peaking)",
        r'\bOVERREACHING(?:_\d+)?\b': "Quá tải (Overreaching)",
        r'\bUNPRODUCTIVE(?:_\d+)?\b': "Không hiệu quả (Unproductive)",
        r'\bDETRAINING(?:_\d+)?\b': "Giảm thể lực (Detraining)",
    }
    for pattern, vi_name in status_cleaners.items():
        text = re.sub(pattern, vi_name, text)

    # Remove raw Garmin code leak: e.g. "(Mã Garmin gốc: MAINTAINING_4)"
    text = re.sub(r'\s*\(Mã Garmin gốc:[^\)]*\)', '', text)

    # 3. Clean meta-instruction leaks
    # Remove: *Quy tắc Bảng Markdown:* ...
    text = re.sub(r'^\s*\*?Quy tắc Bảng Markdown:?\*?.*$\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*Bảng Markdown PHẢI viết sát lề.*$\n?', '', text, flags=re.MULTILINE)

    # Remove meta sentences: "Tuyệt đối không nhầm lẫn giữa phục hồi sau giải..."
    text = re.sub(
        r'[\s\.\,\;]*Tuyệt đối\s+(?:KHÔNG|không)\s+nhầm lẫn\s+giữa\s+phục\s+hồi\s+sau\s+giải[^\.\n]*[\.\n]?',
        '. ',
        text,
        flags=re.IGNORECASE
    )

    # Remove / sanitize: "Sử dụng chính xác 100% mục tiêu Macro Deterministic..."
    text = re.sub(
        r'Sử dụng chính xác 100% mục tiêu Macro Deterministic(?: do hệ thống quy định)?(?:\s*\(Tổng Calo[^\)]*\))?:?',
        'Nhu cầu năng lượng và các chất dinh dưỡng đa lượng được phân bổ chuẩn xác cho ngày hồi phục:',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(r'\bMacro Deterministic\b', 'khung dinh dưỡng đa lượng', text, flags=re.IGNORECASE)

    # Academic fluff cleanups
    text = re.sub(
        r'hiện tượng ức chế acetylcholine hay hội chứng cồn ức chế pha REM',
        'tác động tiêu cực của cồn lên pha REM',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'tác nhân ức chế acetylcholine tại cầu não',
        'tác nhân gây ảnh hưởng giấc ngủ',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'ức chế acetylcholine',
        'gây ức chế thần kinh',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'dọn dẹp bộ nhớ vận động',
        'tái tạo cơ bắp',
        text,
        flags=re.IGNORECASE
    )

    # Sanitize overpraising deep sleep when sleep debt rebound occurs
    text = re.sub(
        r'Tăng cao vượt trội\s*\(Siêu phục hồi\)',
        'Nén sóng chậm cấp cứu (Deep Sleep Rebound do thiếu ngủ)',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'Đánh giá Siêu phục hồi \(Supercompensation\)(?=:\s*Mặc dù tổng thời gian ngủ ngắn)',
        'Đánh giá Nén sóng chậm do thiếu ngủ (Deep Sleep Rebound)',
        text,
        flags=re.IGNORECASE
    )

    # Sanitize western grains (oatmeal, whole wheat bread, quinoa) in meal recommendations
    # Protect negations like "không yến mạch", "cấm yến mạch" so they don't turn into "không khoai lang hấp"
    text = re.sub(
        r'(\b(?:không|cấm|tránh|loại\s+bỏ)\s+)(?:yến\s+mạch|oatmeal)\b',
        r'\g<1>ngũ cốc thô',
        text,
        flags=re.IGNORECASE
    )
    # If not negated, replace oatmeal with chuối tiêu chín
    text = re.sub(r'\b(?:yến mạch|oatmeal)\b', 'chuối tiêu chín', text, flags=re.IGNORECASE)
    text = re.sub(r'\bbánh mì nguyên cám\b', 'chuối tiêu chín', text, flags=re.IGNORECASE)
    text = re.sub(r'\bquinoa\b', 'cơm trắng', text, flags=re.IGNORECASE)

    # 4. Strict Negative Ingredient Filter & Menu Validation Check
    # Replace afternoon sweet potato with banana/apple + yogurt (Instruction 1)
    text = re.sub(
        r'(?:1\s+củ\s+)?khoai\s+lang\s+hấp\s*(?:cỡ\s+vừa)?\s*(?:\(~?\d+g\))?\s*\+\s*1\s+hộp\s+sữa\s+chua\s+(?:ít\s+béo|Chobani)',
        '1 quả chuối tiêu chín (~110g) HOẶC 1 quả táo tây + 1 hộp sữa chua Chobani/ít béo',
        text,
        flags=re.IGNORECASE
    )

    # Check if a negative constraint against sweet potato is active in the report
    has_no_sweet_potato = bool(re.search(r'(?:không|cấm|tránh|loại\s+bỏ)\s+(?:ăn\s+)?khoai\s+lang', text, re.IGNORECASE))
    if has_no_sweet_potato:
        # Purge any remaining sweet potato suggestion under ANY meal
        text = re.sub(
            r'(?:1\s+củ\s+)?khoai\s+lang(?:\s+hấp)?\s*(?:cỡ\s+vừa)?\s*(?:\(~?\d+g\))?\s*(?:\+|kèm|với)?\s*(?:1\s+hộp\s+sữa\s+chua\s+(?:ít\s+béo|Chobani))?',
            '1 quả chuối tiêu chín hoặc 1 lát bánh mì mềm kèm sữa chua ít béo',
            text,
            flags=re.IGNORECASE
        )
        text = re.sub(
            r'\bkhoai\s+lang(?:\s+hấp)?\b',
            'chuối tiêu chín hoặc bánh mì mềm',
            text,
            flags=re.IGNORECASE
        )

    # 5. Eliminate developer debug pseudo-code in report
    lines = text.splitlines()
    filtered_lines = []
    for line in lines:
        stripped = line.strip()
        # Drop standalone pseudo-code lines
        if re.search(r'training_readiness\s*[><=]+', stripped) or \
           re.search(r'recovery_time_hours\s*[><=]+', stripped) or \
           re.search(r'hrv_status\s*==', stripped):
            continue
        # Drop pseudo-code sub-headers
        if "Điều kiện để mở cửa chạy thử" in stripped and stripped.endswith(":"):
            continue
        filtered_lines.append(line)

    text = "\n".join(filtered_lines)

    # 6. Deterministic Sleep Table Math & Sleep Duration Sync
    def _fix_sleep_table_math(match):
        prefix_d, d_str, u_d, suffix_d = match.group(1), match.group(2), match.group(3), match.group(4)
        prefix_r, r_str, u_r, suffix_r = match.group(5), match.group(6), match.group(7), match.group(8)
        prefix_l, l_str, u_l, suffix_l = match.group(9), match.group(10), match.group(11), match.group(12)
        prefix_a, a_str, u_a, suffix_a = match.group(13), match.group(14), match.group(15), match.group(16)
        
        d_val, r_val, l_val, a_val = float(d_str), float(r_str), float(l_str), float(a_str)
        tot_asleep = d_val + r_val + l_val
        tot_bed = tot_asleep + a_val
        
        if tot_asleep > 0 and tot_bed > 0:
            deep_pct = round((d_val / tot_asleep) * 100.0, 1)
            rem_pct = round((r_val / tot_asleep) * 100.0, 1)
            light_pct = round(100.0 - deep_pct - rem_pct, 1)  # Enforce exact 100.0% sum
            awake_pct = round((a_val / tot_bed) * 100.0, 1)   # Awake / Total Bed Time
            
            row_d = f"{prefix_d}{d_str}{u_d} ({deep_pct}%){suffix_d}"
            row_r = f"{prefix_r}{r_str}{u_r} ({rem_pct}%){suffix_r}"
            row_l = f"{prefix_l}{l_str}{u_l} ({light_pct}%){suffix_l}"
            row_a = f"{prefix_a}{a_str}{u_a} ({awake_pct}%){suffix_a}"
            return f"{row_d}\n{row_r}\n{row_l}\n{row_a}"
        return match.group(0)

    sleep_table_pattern = re.compile(
        r'(\|\s*Deep Sleep\s*\|\s*)(\d+(?:\.\d+)?)\s*(m|phút)\s*\([^\)]*%\)(.*?)\n'
        r'(\|\s*REM Sleep\s*\|\s*)(\d+(?:\.\d+)?)\s*(m|phút)\s*\([^\)]*%\)(.*?)\n'
        r'(\|\s*Light Sleep\s*\|\s*)(\d+(?:\.\d+)?)\s*(m|phút)\s*\([^\)]*%\)(.*?)\n'
        r'(\|\s*Awake\s*\|\s*)(\d+(?:\.\d+)?)\s*(m|phút)\s*\([^\)]*%\)(.*?)(?=\n|$)',
        re.IGNORECASE
    )
    text = sleep_table_pattern.sub(_fix_sleep_table_math, text)

    # Sync text mentions of Light Sleep percentage with deterministic calculation if table exists
    table_light_pct_match = re.search(r'\|\s*Light Sleep\s*\|\s*\d+(?:\.\d+)?\s*(?:m|phút)\s*\(([0-9.]+)%\)', text, re.IGNORECASE)
    if table_light_pct_match:
        corr_light_pct_str = table_light_pct_match.group(1)
        text = re.sub(
            r'(\b(?:chiếm|dành\s+đến|đạt)\s+)\d+(?:\.\d+)?%\s*(thời\s+lượng\s+giấc\s+ngủ\s+ở\s+pha\s+ngủ\s+nông)',
            rf'\g<1>{corr_light_pct_str}% \g<2>',
            text,
            flags=re.IGNORECASE
        )

    # Fix Sleep Duration Text-Table Mismatch (Total Sleep Time = Deep + REM + Light)
    table_match = re.search(
        r'\|\s*Deep Sleep\s*\|\s*(\d+(?:\.\d+)?)\s*m.*?\|\s*REM Sleep\s*\|\s*(\d+(?:\.\d+)?)\s*m.*?\|\s*Light Sleep\s*\|\s*(\d+(?:\.\d+)?)\s*m',
        text,
        re.DOTALL | re.IGNORECASE
    )
    if table_match:
        deep_min = float(table_match.group(1))
        rem_min = float(table_match.group(2))
        light_min = float(table_match.group(3))
        sum_min = int(round(deep_min + rem_min + light_min))
        sum_h = sum_min // 60
        sum_m = sum_min % 60

        def replace_sleep_dur(m):
            prefix = m.group(1)
            old_h = int(m.group(2))
            old_m = int(m.group(3))
            suffix = m.group(4)
            if old_h * 60 + old_m != sum_min:
                if "giờ" in m.group(0):
                    return f"{prefix}{sum_h} giờ {sum_m} phút{suffix}"
                else:
                    return f"{prefix}{sum_h}h {sum_m}m{suffix}"
            return m.group(0)

        text = re.sub(
            r'((?:Tổng\s+thời\s+gian\s+ngủ|Thời\s+gian\s+ngủ)[^.\n]*?(?:đạt|là)?\s*)(\d+)\s*(?:giờ|h)\s*(\d+)\s*(?:phút|m)([^.\n]*)',
            replace_sleep_dur,
            text,
            flags=re.IGNORECASE
        )

    # 7. Post-Alcohol Uric Acid Flush Protocol Enforcement
    alcohol_detected = bool(re.search(
        r'(?:đơn\s+vị\s+cồn|uống\s+bia|cốc\s+bia|lon\s+bia|đồ\s+nhậu|chuyển\s+hóa\s+cồn|\bethanol\b|tiệc\s+nhậu)',
        text,
        re.IGNORECASE
    ))
    required_flush_protocol = (
        "Uống tối thiểu 3.0L - 3.2L nước rải đều trong ngày, ưu tiên nước khoáng kiềm pH 8.5-9.0 (Fujiwa) "
        "để nâng pH nước tiểu, chống lắng đọng tinh thể urat tại gân Achilles."
    )
    if alcohol_detected and "chống lắng đọng tinh thể urat tại gân Achilles" not in text:
        if "### 🍱 4." in text:
            ua_match = re.search(r'(-\s*\*\*Bảo\s+vệ\s+Lâm\s+sàng\s+Acid\s+Uric[^\n]*\n)', text, re.IGNORECASE)
            if ua_match:
                insert_idx = ua_match.end()
                protocol_line = f"  * **Giao thức Thải trừ Acid Uric Hậu Cồn (Alkaline Hydration Protocol):** {required_flush_protocol}\n"
                text = text[:insert_idx] + protocol_line + text[insert_idx:]
            else:
                notice_idx = text.find("💡 Lưu ý: Đây là thực đơn khung")
                if notice_idx != -1:
                    protocol_block = f"- **Giao thức Thải trừ Acid Uric Hậu Cồn (Alkaline Hydration Protocol):** {required_flush_protocol}\n"
                    text = text[:notice_idx] + protocol_block + text[notice_idx:]
                else:
                    sec4_idx = text.find("### 🍱 4.")
                    next_break = text.find("===TELEGRAM_CARD_BREAK===", sec4_idx)
                    if next_break != -1:
                        text = text[:next_break].rstrip() + f"\n- **Giao thức Thải trừ Acid Uric Hậu Cồn:** {required_flush_protocol}\n\n" + text[next_break:]
                    else:
                        text = text.rstrip() + f"\n- **Giao thức Thải trừ Acid Uric Hậu Cồn:** {required_flush_protocol}\n"

    # 6. Ensure Intraday Dynamic Notice in Section 4 for morning reports (Strip from Midday Review)
    is_midday_text = (
        ("midday review" in text.lower() or "đánh giá vận động sáng & điều chỉnh" in text.lower() or "thực đơn tối đề xuất" in text.lower())
        and not ("morning briefing" in text.lower() or "báo cáo khởi động ngày" in text.lower() or "khởi động ngày" in text.lower())
    )
    if is_midday_text:
        text = re.sub(r'[\r\n]+\s*(?:[-*•]\s*)?💡?\s*Lưu ý:\s*Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng\.[^\n]*\n?', '\n', text)
    else:
        intraday_notice = "💡 Lưu ý: Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng. Mọi tiêu hao từ bài chạy/bơi phát sinh hôm nay sẽ được tự động cộng bù hạn mức trong Thẻ Nhịp Trưa (Midday Pulse)."
        if "### 🍱 4." in text and intraday_notice not in text and "Đây là thực đơn khung ngày nghỉ/hồi phục nền tảng" not in text:
            sec4_idx = text.find("### 🍱 4.")
            next_break = text.find("===TELEGRAM_CARD_BREAK===", sec4_idx)
            if next_break != -1:
                text = text[:next_break].rstrip() + f"\n- {intraday_notice}\n\n" + text[next_break:]
            else:
                next_sec = text.find("===SECTION_BREAK===", sec4_idx)
                if next_sec != -1:
                    text = text[:next_sec].rstrip() + f"\n- {intraday_notice}\n\n" + text[next_sec:]
                else:
                    text = text.rstrip() + f"\n- {intraday_notice}\n"

    # Clean consecutive empty lines
    text = re.sub(r'\n{3,}', '\n\n', text)
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
    ts_display = format_training_status(ts_raw)

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
    race_ctx = get_race_context(target_date)
    phase = race_ctx["phase"]
    days_left = race_ctx["days_to_race"]
    days_since = race_ctx["days_since_race"]
    race_info = race_ctx["race_info"]

    if phase in ("POST_RACE_ACUTE", "POST_RACE_RECOVERY") and race_info:
        phase_label = "Post-Race Acute" if phase == "POST_RACE_ACUTE" else "Post-Race Recovery (Reverse Taper)"
        race_str = f"• {race_info.get('name')} ({race_info.get('distance')}): ĐÃ KẾT THÚC (Đã qua {days_since} ngày — Phase {phase_label})"
        nut_str = f"• Target Protein: ~{protein_target}g (1.4-1.5g/kg) | Carb 45-50% TDEE | Khóa bữa tối <= 28.0g | Tránh chua cay, đường đơn, dầu mỡ"
    elif race_info and isinstance(race_info, dict):
        if days_left is not None and 0 <= days_left <= 3:
            race_str = f"• {race_info.get('name')} ({race_info.get('distance')}): Còn {days_left} ngày (🔥 CHẾ ĐỘ CARBO-LOADING 70% CARBS)"
        else:
            race_str = f"• {race_info.get('name')} ({race_info.get('distance')}): Còn {days_left} ngày (Giai đoạn Tapering)"
        if days_left is not None and 0 <= days_left <= 3:
            if days_left == 1:
                carb_target = round(6.0 * float(w_kg))
                nut_str = f"• 🔥 Carbo-Loading T-1 (70% Carbs, ~{carb_target}g Carb) | Target Protein: {protein_target}g | Nước kiềm Fujiwa: 3.0L"
            else:
                c_min = round(5.0 * float(w_kg))
                c_max = round(5.5 * float(w_kg))
                nut_str = f"• 🔥 Carbo-Loading T-{days_left} (70% Carbs, ~{c_min}-{c_max}g Carb) | Target Protein: {protein_target}g | Nước kiềm Fujiwa: 3.0L"
        else:
            target_cal_est = macro_brief.get("target_calories", 1850.0)
            nut_str = f"• Target Protein: {protein_target}g | Calo ước tính: ~{target_cal_est} kcal | Nước kiềm Fujiwa: 3.0L"
    else:
        race_str = "• Chưa ghi nhận giải đấu trong lịch races.json."
        target_cal_est = macro_brief.get("target_calories", 1850.0)
        nut_str = f"• Target Protein: {protein_target}g | Calo ước tính: ~{target_cal_est} kcal | Nước kiềm Fujiwa: 3.0L"

    if is_incomplete:
        sleep_line = "• ⚠️ Giấc ngủ chưa chốt xong / Dậy muộn. Cân Omron xong gửi /report để cập nhật."
    elif is_emergency:
        sleep_line = f"• 🚨 EMERGENCY RECOVERY PROTOCOL: Power Nap 20m trước 14:30 | Cấm caffeine sau 12:00 | Bữa phụ 20:00 (1/2 chuối/sữa tách béo ấm, cấm dùng hạt fat>3g)"
    else:
        sleep_line = f"• Sleep Score: {sleep_score}/100 | Ngủ sâu (Deep Sleep): {deep_str} | Sạc Body Battery: +{bb_charged}"

    sleep_sec_brief = float(sleep_dur) if sleep_dur is not None else None
    if sleep_sec_brief is not None and 0 < sleep_sec_brief < 18000:
        workout_brief_line = (
            "• 🚨 CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG): CẤM CHẠY TUYỆT ĐỐI (kể cả shakeout run) "
            "để bảo vệ gân Achilles trái. HÔM NAY BẮT BUỘC: Nghỉ ngơi hoàn toàn (Rest Day) "
            "HOẶC bơi sải thả lỏng không trọng lực 500m Zone 1. Kèm Isometric Holds gân gót.\n"
        )
    elif phase == "POST_RACE_ACUTE":
        workout_brief_line = f"• Trạng thái Phục hồi Post-Race Acute (D+{days_since or 3}): CẤM CHẠY HOÀN TOÀN. Active Recovery (Đi bộ nhẹ 15-20p, bơi thả lỏng) hoặc Nghỉ hoàn toàn (Full Rest). Kèm Isometric Holds gân gót.\n"
    elif phase == "POST_RACE_RECOVERY":
        from src.analytics.training_prescriber import prescribe_running_workout, calculate_sleep_stage_percentages
        rec_val = tm.get("recovery_time_hours")
        hrv_st = tm.get("hrv_status")
        readiness_val_brief = tm.get("training_readiness_score")
        sleep_stages_brief = calculate_sleep_stage_percentages(
            tm.get("deep_sleep_seconds"),
            tm.get("rem_sleep_seconds"),
            tm.get("light_sleep_seconds"),
            tm.get("awake_duration_seconds")
        )
        presc = prescribe_running_workout(
            readiness_score=readiness_val_brief,
            recovery_time_hours=rec_val,
            deep_sleep_pct=sleep_stages_brief["deep_pct"] if sleep_stages_brief["total_asleep_min"] > 0 else None,
            rem_sleep_pct=sleep_stages_brief["rem_pct"] if sleep_stages_brief["total_asleep_min"] > 0 else None,
            sleep_duration_seconds=sleep_dur,
            hrv_status=hrv_st,
            gct_balance=tm.get("gct_balance"),
            days_since_race=days_since,
            phase=phase
        )
        workout_brief_line = presc["brief_line"] + "\n"
    elif days_left is not None and days_left <= 7:
        workout_brief_line = f"• Trạng thái {ts_display}: Shakeout Run 15-20m Zone 1/2 (HR < 135 bpm), sải bước ngắn tự nhiên lướt sát đất (KHÔNG bứt tốc/Strides). Kèm Eccentric Heel Drops xả tải Achilles.\n"
    else:
        workout_brief_line = f"• Trạng thái {ts_display}: MAF Zone 2 nhẹ nhàng (HR < 136 bpm, Cadence 178-182 spm) hoặc Bơi lội phục hồi. Chiều giãn cơ.\n"

    brief_lines = [
        f"⚡ EXECUTIVE BRIEF PHỤC HỒI & TẢI VẬN ĐỘNG",
        f"📅 {date_vn}\n",
        f"🏃‍♂️ Sinh lý & Phục hồi Đêm qua:",
        f"• HRV Overnight: {hrv_str} ({diff_str}, {tm.get('hrv_status') or 'BALANCED'}) | RHR: {rhr_str} | Stress: {tm.get('avg_stress_level') or 'N/A'}",
        f"{sleep_line}\n",
        f"🎯 Đếm ngược Giải đấu:",
        f"{race_str}\n",
        f"🏋️ Kê đơn Vận động Hôm nay:",
        workout_brief_line,
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

    from src.analytics.nutrition_engine import calculate_daily_macros
    race_ctx_card = get_race_context(target_date)
    phase_card = race_ctx_card["phase"]
    d_left_card = race_ctx_card["days_to_race"]
    d_since_card = race_ctx_card["days_since_race"]

    macro_targets = calculate_daily_macros(
        weight_kg=float(w_kg),
        phase=phase_card,
        uric_acid_level=442.0,
        active_calories_garmin=act_cals,
        days_since_race=d_since_card,
        days_to_race=d_left_card
    )
    target_cal = macro_targets["target_calories"]
    target_p = macro_targets["protein_g"]
    target_c = macro_targets["carb_g"]
    target_f = macro_targets["fat_g"]
    dinner_cap = macro_targets["dinner_protein_cap"]

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
        from src.analytics.midday_review import calculate_evening_targets
        din_p_target, din_c_target, fat_status = calculate_evening_targets(
            {"protein": target_p, "carb": target_c, "fat": target_f},
            {"protein": tot_p, "carb": tot_c, "fat": tot_f},
            uric_acid_level=442.0
        )
        fat_card_str = "Đã đủ/vượt quota (Hấp/luộc)" if fat_status == "EXCEEDED" else f"~{rem_f}g"

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

        phase_title = f"HỒI PHỤC CẤP POST-RACE D+{d_since_card or 3}" if phase_card == "POST_RACE_ACUTE" else "MIDDAY CARD"

        lines = [
            f"☀️ **TÓM TẮT ĐÁNH GIÁ TRƯA ({phase_title})** ({date_vn})",
            f"• **🏃 Bài chạy sáng:** {act_desc}",
            f"• **⚡ Readiness & Phục hồi chiều:** Readiness {readiness}/100 — Phục hồi thụ động, stretching nhẹ (CẤM chạy thêm buổi chiều)",
            f"• **🍱 Quota Macro còn lại:** Calo ~{rem_cal} kcal | Protein ~{rem_p}g | Carb tối đa ~{din_c_target}g (Chống Carb-Dumping) | Fat: {fat_card_str}",
            f"• **🔒 Khóa bữa tối:** Protein tối <= {din_p_target}g | Carb tối <= {din_c_target}g (Acid Uric 442 µmol/L)",
            f"• **⚠️ Cảnh báo sinh lý:** {warning_text}"
        ]

    elif r_type == "evening":
        from src.analytics.card_generator import generate_evening_card
        return generate_evening_card(baseline_data)

    else: # morning
        sleep_dur_card = tm.get("sleep_duration_seconds")
        sleep_sec_card = float(sleep_dur_card) if sleep_dur_card is not None else None
        if sleep_sec_card is not None and 0 < sleep_sec_card < 18000:
            workout_plan = "🚨 CẢNH BÁO THIẾU NGỦ CẤP TÍNH (< 5 TIẾNG): CẤM CHẠY BỘ TUYỆT ĐỐI (kể cả shakeout run) để bảo vệ gân Achilles trái. HÔM NAY BẮT BUỘC: Nghỉ ngơi hoàn toàn (Rest Day) HOẶC bơi sải thả lỏng không trọng lực 500m Zone 1. Kèm bài tập tĩnh Isometric Holds nhón gót 30s x 3 set."
        elif phase_card == "POST_RACE_ACUTE":
            workout_plan = "NGHỈ CHẠY HOÀN TOÀN (Full Rest Day) hoặc đi bộ nhẹ nhàng 15-20 phút / bơi nhẹ. CẤM mọi hình thức chạy bộ, strides, tempo hay gò sải chân. Kèm Isometric Holds gân gót."
        elif phase_card == "POST_RACE_RECOVERY":
            from src.analytics.training_prescriber import prescribe_running_workout, calculate_sleep_stage_percentages
            sleep_stages_card = calculate_sleep_stage_percentages(
                tm.get("deep_sleep_seconds"),
                tm.get("rem_sleep_seconds"),
                tm.get("light_sleep_seconds"),
                tm.get("awake_duration_seconds")
            )
            presc_card = prescribe_running_workout(
                readiness_score=readiness,
                recovery_time_hours=tm.get("recovery_time_hours"),
                deep_sleep_pct=sleep_stages_card["deep_pct"] if sleep_stages_card["total_asleep_min"] > 0 else None,
                rem_sleep_pct=sleep_stages_card["rem_pct"] if sleep_stages_card["total_asleep_min"] > 0 else None,
                sleep_duration_seconds=sleep_dur_card,
                hrv_status=tm.get("hrv_status"),
                gct_balance=tm.get("gct_balance"),
                days_since_race=d_since_card,
                phase=phase_card
            )
            workout_plan = presc_card["card_plan"]
        elif d_left_card is not None and d_left_card <= 7:
            workout_plan = "Shakeout Run 15-20 phút Zone 1/2 (HR < 135 bpm), sải bước ngắn tự nhiên, lướt sát đất (TUYỆT ĐỐI KHÔNG bứt tốc/Strides/Interval). Kèm Eccentric Heel Drops (3 set x 10-12 lần mép bậc thang) ngoài đường chạy."
        else:
            workout_plan = "MAF Zone 2 phẳng (HR < 136 bpm, 25-30 phút, Cadence locked 178-182 spm) hoặc Bơi lội phục hồi."

        header_title = f"HỒI PHỤC CẤP (POST-RACE D+{d_since_card or 3})" if phase_card == "POST_RACE_ACUTE" else (f"PHỤC HỒI SAU RACE (POST-RACE D+{d_since_card or 8})" if phase_card == "POST_RACE_RECOVERY" else "MORNING CARD")

        lines = [
            f"🌅 **TÓM TẮT KHỞI ĐỘNG SÁNG ({header_title})** ({date_vn})",
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




