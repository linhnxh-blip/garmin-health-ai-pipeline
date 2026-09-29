import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

from src.db.connection import get_db_connection
from src.analytics.constants import CORE_SPORT_MARKERS, SUPPLEMENTARY_MARKERS, SPORTS_MEDICINE_RECOMMENDATIONS



def evaluate_blood_trends(db_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """Query 2 most recent blood test dates and evaluate trend delta, status, and international sports medicine recommendations (ADA, AHA, EULAR, ACSM)."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT test_date FROM blood_tests ORDER BY test_date DESC LIMIT 2")
        dates = [r[0] for r in cursor.fetchall()]

        if len(dates) < 2:
            return {
                "previous_date": dates[0] if dates else None,
                "current_date": dates[0] if dates else None,
                "evaluations": [],
                "summary_text": "⚠️ Cần ít nhất 2 đợt xét nghiệm máu trong cơ sở dữ liệu để thực hiện đánh giá xu hướng."
            }

        current_date = max(dates)
        previous_date = min(dates)

        cursor.execute(
            """
            SELECT test_date, category, marker_name, raw_name, value, value_text, unit, ref_min, ref_max, status
            FROM blood_tests
            WHERE test_date IN (?, ?)
            """,
            (previous_date, current_date)
        )
        rows = [dict(r) for r in cursor.fetchall()]

    prev_map = {r["marker_name"]: r for r in rows if r["test_date"] == previous_date}
    curr_map = {r["marker_name"]: r for r in rows if r["test_date"] == current_date}

    evaluations = []

    # Calculate TG/HDL ratio if both exist in current test
    tg_val = curr_map.get("TRIGLYCERIDE", {}).get("value")
    hdl_val = curr_map.get("HDL_C", {}).get("value")
    tg_hdl_ratio = round(tg_val / hdl_val, 2) if (tg_val and hdl_val and hdl_val > 0) else None

    # Evaluate 14 Core Markers + Supplementary
    all_target_markers = CORE_SPORT_MARKERS + [m for m in SUPPLEMENTARY_MARKERS if m in curr_map or m in prev_map]

    for mk in all_target_markers:
        if mk not in curr_map or mk not in prev_map:
            continue

        p_rec = prev_map[mk]
        c_rec = curr_map[mk]

        p_val = p_rec.get("value")
        c_val = c_rec.get("value")

        if p_val is None or c_val is None:
            continue

        unit = c_rec.get("unit") or p_rec.get("unit") or ""
        category = c_rec.get("category") or p_rec.get("category") or "Chung"
        delta = round(c_val - p_val, 4)
        pct_change = round((delta / p_val) * 100, 2) if p_val != 0 else 0.0

        status = "STABLE"
        status_label = "⚪ Ổn định"
        recommendation = ""
        clinical_note = ""

        # --- INTERNATIONAL CLINICAL STANDARDS EVALUATION ---
        if mk == "GLUCOSE":
            # ADA Standard: Fasting Glucose < 5.6 mmol/L is Normal. > 5.6 mmol/L is Prediabetes.
            if c_val > 5.6:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Tiền tiểu đường ADA > 5.6 mmol/L)"
                clinical_note = f"Glucose {c_val} mmol/L > 5.6 mmol/L (Ngưỡng Tiền tiểu đường ADA)"
                recommendation = "Cắt bỏ hoàn toàn đường lỏng HFCS/nước ngọt và bánh kẹo công nghiệp. Nạp carb phức hợp (gạo lứt, yến mạch, khoai lang), tăng cường bài tập Zone 2 để kích hoạt cơ chế FatMax đốt mỡ."
            elif delta < 0:
                status = "IMPROVED"
                status_label = "🟢 Tốt lên"

        elif mk == "HBA1C":
            # ADA Standard: HbA1c < 5.7% is Normal. > 5.7% is Prediabetes.
            if c_val > 5.7:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Tiền tiểu đường ADA > 5.7%)"
                clinical_note = f"HbA1c {c_val}% > 5.7% (Ngưỡng Tiền tiểu đường ADA)"
                recommendation = "Duy trì kiểm soát carb nghiêm ngặt, cắt bỏ HFCS & đường đơn; tăng cường bài tập MAF Zone 2 đều đặn để cải thiện độ nhạy Insulin dài hạn."
            elif delta < 0:
                status = "IMPROVED"
                status_label = "🟢 Tốt lên"

        elif mk == "TRIGLYCERIDE":
            # NCEP/AHA Standard: Triglyceride < 1.70 mmol/L is Normal.
            if c_val > 1.70 or delta > 0.3:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Vượt chuẩn NCEP/AHA > 1.70 mmol/L)"
                clinical_note = f"Triglyceride {c_val} mmol/L > 1.70 mmol/L (Ngưỡng cao NCEP/AHA)"
                rec_parts = ["Cắt bỏ hoàn toàn đường lỏng HFCS/nước ngọt và bánh kẹo công nghiệp. Nạp carb phức hợp (gạo lứt, yến mạch, khoai lang), tăng cường bài tập Zone 2 để kích hoạt cơ chế FatMax đốt mỡ."]
                if tg_hdl_ratio and tg_hdl_ratio > 1.3:
                    rec_parts.append(f"⚠️ Tỷ lệ TG/HDL = {tg_hdl_ratio} (> 1.3): Cảnh báo suy giảm độ nhạy Insulin và kháng Insulin tiềm ẩn.")
                recommendation = " ".join(rec_parts)
            elif delta < 0:
                status = "IMPROVED"
                status_label = "🟢 Tốt lên"

        elif mk == "URIC_ACID":
            # EULAR Standard: Uric Acid < 420 umol/L.
            if c_val > 420.0:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Sát trần bão hòa EULAR > 420 µmol/L)"
                clinical_note = f"Uric Acid {c_val} µmol/L > 420 µmol/L (Bão hòa dịch khớp EULAR)"
                recommendation = "Uric acid sát trần bão hòa dịch khớp (> 420 µmol/L). Ép uống tối thiểu 2.8 - 3.2L nước khoáng kiềm/ngày, hạn chế ăn dồn dập hải sản/phủ tạng để tránh áp lực thận và co rút cơ bắp."
            elif delta < 0:
                status = "IMPROVED"
                status_label = "🟢 Tốt lên"

        elif mk == "WBC":
            # ACSM / Clinical Standard: 4.0 - 8.0 G/L. < 3.5 G/L is suppressed/overtrained.
            if c_val < 3.5 or c_val < 4.0:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Bạch cầu nền thấp < 4.0 G/L)"
                clinical_note = f"WBC {c_val} G/L < 4.0 G/L (Ức chế miễn dịch/mệt mỏi thần kinh)"
                recommendation = "Bạch cầu nền thấp (< 3.5 G/L). Cần ưu tiên giấc ngủ sâu (> 7.5 tiếng) và dinh dưỡng phục hồi, tránh tập dồn volume cao liên tiếp nhiều ngày."
            elif p_val < 4.0 and c_val >= 4.0:
                status = "IMPROVED"
                status_label = "🟢 Tốt lên (Phục hồi dải chuẩn 4.0 - 8.0 G/L)"

        elif mk == "HGB":
            # ACSM Standard: 14.0 - 16.0 g/dL. < 13.5 g/dL is anemia risk.
            if c_val < 13.5:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Sụt giảm < 13.5 g/dL)"
                recommendation = "Huyết sắc tố HGB giảm sút. Bổ sung thực phẩm giàu Sắt heme (thịt bò thăn, gan, hải sản) kết hợp Vitamin C; rà soát tải chạy bộ để tránh vỡ hồng cầu do va đập bàn chân (Footstrike Hemolysis)."
            elif c_val >= 14.0 and c_val <= 16.0:
                status = "STABLE" if abs(pct_change) < 2.0 else ("IMPROVED" if delta >= 0 else "STABLE")
                status_label = "🟢 Duy trì chuẩn (14.0 - 16.0 g/dL)" if status == "IMPROVED" else "⚪ Duy trì chuẩn tối ưu"

        elif mk == "HCT":
            # ACSM Standard: 40 - 46% (Optimal blood viscosity).
            if c_val < 39.0:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (HCT < 39.0% - Loãng máu/thiếu máu)"
                recommendation = "HCT sụt giảm dưới 40%. Bổ sung vi chất tạo máu (Sắt, Folate, B12) và duy trì hidrat hóa hợp lý."
            elif 40.0 <= c_val <= 46.0:
                status = "STABLE"
                status_label = "⚪ Duy trì độ nhớt máu tối ưu (40 - 46%)"

        elif mk in ["ALT", "AST"]:
            # ACSM / EASL Standard: < 35 U/L. > 40 U/L is muscle/liver strain.
            if c_val > 40.0:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Vượt 40 U/L - Tổn thương cơ/gan)"
                recommendation = "Men gan ALT/AST vượt 40 U/L do vi tổn thương cơ bắp sau bài tập nặng hoặc mệt mỏi gan. Giảm tải sức mạnh, ưu tiên bơi lội thả lỏng không trọng lực và bổ sung Silymarin/Milk Thistle."
            elif delta < 0 or c_val <= 35.0:
                status = "IMPROVED" if delta < 0 else "STABLE"
                status_label = "🟢 Tốt lên (Chuẩn < 35 U/L)" if status == "IMPROVED" else "⚪ Ổn định (< 35 U/L)"

        elif mk == "LDL_C":
            # ACSM / AHA Optimal Standard: < 2.60 mmol/L.
            if c_val <= 2.60:
                status = "IMPROVED" if delta <= 0 else "STABLE"
                status_label = "🟢 Tốt lên (Dải tối ưu ACSM < 2.6 mmol/L)" if status == "IMPROVED" else "⚪ Duy trì tối ưu (< 2.6 mmol/L)"
            else:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Vượt dải tối ưu > 2.6 mmol/L)"
                recommendation = "LDL-Cholesterol vượt ngưỡng tối ưu (< 2.6 mmol/L). Cắt giảm chất béo bão hòa/trans-fat, bổ sung 2000mg/ngày Omega-3 và duy trì tập endurance Zone 2."

        elif mk == "HDL_C":
            # AHA Standard: > 1.20 mmol/L for males.
            if c_val >= 1.20:
                status = "IMPROVED" if delta >= 0 else "STABLE"
                status_label = "🟢 Tốt lên (Tối ưu > 1.2 mmol/L)" if status == "IMPROVED" else "⚪ Duy trì tối ưu (> 1.2 mmol/L)"
            elif c_val < 1.00:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Thấp < 1.0 mmol/L)"
                recommendation = "HDL-Cholesterol thấp (< 1.0 mmol/L). Tăng cường tập luyện hiếu khí MAF Zone 2 và nạp chất béo tốt (dầu olive, quả bơ, hạt óc chó)."

        elif mk == "CREATININE":
            if c_val > 115.0:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Vượt 115 µmol/L - Áp lực thận/quá tải cơ)"
                recommendation = "Creatinine tăng cao phản ánh quá tải cơ bắp hoặc áp lực lọc thận. Ép bù đủ 3.0L nước/ngày và giảm khối lượng tập tạ nặng."
            else:
                status = "STABLE"
                status_label = "⚪ Duy trì chuẩn (60 - 110 µmol/L)"

        elif mk == "CHOLESTEROL":
            if c_val > 5.20:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (Vượt 5.2 mmol/L)"
                recommendation = "Cholesterol toàn phần tăng. Tăng chất xơ hòa tan (yến mạch, rau xanh) và tập Zone 2 để cải thiện chỉ số mỡ máu."
            else:
                status = "STABLE"
                status_label = "⚪ Duy trì chuẩn (< 5.2 mmol/L)"

        elif mk == "RBC":
            if c_val < 4.2:
                status = "DECLINED"
                status_label = "🔴 Xấu đi (< 4.2 T/L)"
                recommendation = "Số lượng hồng cầu giảm sút. Bổ sung vi chất tạo máu (Sắt, B12, Folate)."
            else:
                status = "STABLE"
                status_label = "⚪ Duy trì chuẩn (4.2 - 6.0 T/L)"

        evaluations.append({
            "marker_name": mk,
            "category": category,
            "previous_value": p_val,
            "current_value": c_val,
            "unit": unit,
            "delta": delta,
            "pct_change": pct_change,
            "status": status,
            "status_label": status_label,
            "clinical_note": clinical_note,
            "recommendation": recommendation
        })

    result = {
        "previous_date": previous_date,
        "current_date": current_date,
        "tg_hdl_ratio": tg_hdl_ratio,
        "evaluations": evaluations
    }
    result["summary_text"] = format_blood_trend_summary(result)
    return result


def format_blood_trend_summary(trends_dict: Dict[str, Any]) -> str:
    """Format evaluations list into printable sports medicine terminal summary block according to ADA, AHA, EULAR, ACSM standards."""
    prev_date = trends_dict.get("previous_date")
    curr_date = trends_dict.get("current_date")
    tg_hdl_ratio = trends_dict.get("tg_hdl_ratio")
    evals = trends_dict.get("evaluations", [])

    if not evals:
        return trends_dict.get("summary_text", "⚠️ Không có dữ liệu đánh giá xu hướng xét nghiệm máu.")

    improved = [e for e in evals if e["status"] == "IMPROVED"]
    declined = [e for e in evals if e["status"] == "DECLINED"]
    stable = [e for e in evals if e["status"] == "STABLE"]

    lines = []
    lines.append("📋 NHẬN XÉT XU HƯỚNG VÀ HƯỚNG XỬ LÝ SINH LÝ Y HỌC THỂ THAO (CHUẨN ADA, AHA, EULAR, ACSM)")
    lines.append("=" * 95)
    lines.append(f"📅 Mốc so sánh: {prev_date} ➔ {curr_date}")
    if tg_hdl_ratio:
        tg_flag = " ⚠️ KHÁNG INSULIN TIỀM ẨN (> 1.3)" if tg_hdl_ratio > 1.3 else " ✅ TỐI ƯU"
        lines.append(f"⚖️ Tỷ lệ Chuyển hóa TG/HDL-C: {tg_hdl_ratio}{tg_flag}\n")

    if improved:
        lines.append("🟢 CHỈ SỐ CẢI THIỆN / ĐẠT CHUẨN TỐI ƯU:")
        for e in improved:
            sign = "+" if e["delta"] > 0 else ""
            lines.append(f"  • {e['marker_name']} ({e['category']}): {e['previous_value']} ➔ {e['current_value']} {e['unit']} ({sign}{e['delta']} | {sign}{e['pct_change']}%) - {e['status_label']}")
        lines.append("")

    if declined:
        lines.append("🔴 CHỈ SỐ CẦN LƯU Ý & HƯỚNG XỬ LÝ (SPORTS MEDICINE ACTION PLAN):")
        for e in declined:
            sign = "+" if e["delta"] > 0 else ""
            lines.append(f"  • {e['marker_name']} ({e['category']}): {e['previous_value']} ➔ {e['current_value']} {e['unit']} ({sign}{e['delta']} | {sign}{e['pct_change']}%) - {e['status_label']}")
            if e.get("recommendation"):
                lines.append(f"    👉 Hướng xử lý: {e['recommendation']}")
        lines.append("")

    if stable:
        lines.append("⚪ CHỈ SỐ ỔN ĐỊNH & DUY TRÌ BÌNH THƯỜNG:")
        for e in stable:
            lines.append(f"  • {e['marker_name']} ({e['category']}): {e['previous_value']} ➔ {e['current_value']} {e['unit']} - {e['status_label']}")
        lines.append("")

    lines.append("=" * 95)
    return "\n".join(lines)
