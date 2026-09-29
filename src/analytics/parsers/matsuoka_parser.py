"""
T-Matsuoka Lab Report Parser & Normalizer.
Handles OCR extraction and anchor-based normalization for T-Matsuoka (NURA) lab reports.
"""

from typing import Dict, Any, Optional
from src.analytics.blood_normalizer import normalize_marker, normalize_unit_and_value

MATSUOKA_VISION_PROMPT = """Bạn là chuyên gia bóc tách dữ liệu phiếu xét nghiệm y khoa T-Matsuoka (NURA).
Nhiệm vụ của bạn là đọc từng dòng trong bảng kết quả xét nghiệm và chuyển đổi thành JSON.

QUY TẮC BÓC TÁCH PHIẾU T-MATSUOKA:
1. PHÂN BIỆT MÁU VÀ NƯỚC TIỂU:
   - Các dòng thuộc 'Sinh hoá nước tiểu' (đơn vị mg/dL, BC/µL, HC/µL hoặc 'Âm tính'): BẮT BUỘC đặt section là "NUOC_TIEU" và category là "Nước tiểu".
2. CÁC CHỈ SỐ CHUẨN FORM T-MATSUOKA:
   - "(NURA) Huyết sắc tố (HGB)" -> HGB (ví dụ: 142 g/L -> tự động quy đổi thành 14.2 g/dL). KHÔNG lấy HbA1c hay Anti-HBs.
   - "Số lượng hồng cầu (RBC)" -> RBC (unit: T/L).
   - "Số lượng bạch cầu (WBC)" -> WBC (ví dụ: 3.70 G/L). TUYỆT ĐỐI KHÔNG lấy các dòng con như BASON hay LYMPH#.
   - "Lượng HST trung bình HC (MCH)" -> MCH (unit: pg).
   - "Nồng độ HST trung bình HC (MCHC)" -> MCHC (unit: g/dL).
   - "Anti HBs miễn dịch tự động" -> ANTI_HBS (unit: mUI/mL, ví dụ: 827).
   - "Định lượng Cholesterol" -> CHOLESTEROL (unit: mmol/L).
   - "Định lượng LDL-C" -> LDL_C (unit: mmol/L).
   - "Định lượng HDL-C" -> HDL_C (unit: mmol/L).

3. XUẤT JSON SCHEMA DẠNG DANH SÁCH:
   [
     {
       "section": "HUYET_HOC" | "HOA_SINH_MAU" | "NUOC_TIEU" | "MIEN_DICH",
       "raw_name": "<Tên nguyên văn chỉ số>",
       "value": <float hoặc null>,
       "value_text": "<chuỗi giá trị gốc>",
       "unit": "<đơn vị>",
       "ref_min": <float hoặc null>,
       "ref_max": <float hoặc null>,
       "status": "NORMAL" | "LOW" | "HIGH"
     }
   ]
"""


def parse_matsuoka_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize and validate a raw extracted record from a T-Matsuoka lab report."""
    raw_name = (rec.get("raw_name") or "").strip()
    if not raw_name:
        return None

    section = (rec.get("section") or "").upper().strip()
    val_raw = rec.get("value")
    val_text = rec.get("value_text")
    if val_text is None and val_raw is not None:
        val_text = str(val_raw)
    elif val_text is not None:
        val_text = str(val_text).strip()
    else:
        val_text = ""

    unit_raw = (rec.get("unit") or "").strip()
    ref_min = rec.get("ref_min")
    ref_max = rec.get("ref_max")
    status_raw = (rec.get("status") or "").upper().strip()

    # Convert numeric types safely
    if val_raw is not None:
        try:
            val_raw = float(val_raw)
        except Exception:
            val_raw = None

    if ref_min is not None:
        try:
            ref_min = float(ref_min)
        except Exception:
            ref_min = None

    if ref_max is not None:
        try:
            ref_max = float(ref_max)
        except Exception:
            ref_max = None

    is_urine = (section == "NUOC_TIEU") or ("NƯỚC TIỂU" in raw_name.upper()) or ("NUOC TIEU" in raw_name.upper())

    if is_urine:
        lookup_name = raw_name if "nước tiểu" in raw_name.lower() else f"Nước tiểu {raw_name}"
        marker_name, category = normalize_marker(lookup_name)
        if not marker_name.startswith("URINE_"):
            marker_name = f"URINE_{marker_name}"
        category = "Nước tiểu"
    else:
        clean_raw_lower = raw_name.lower()
        if "anti hbs" in clean_raw_lower or "anti-hbs" in clean_raw_lower:
            marker_name, category = "ANTI_HBS", "Nội tiết & Miễn dịch"
        elif "hba1c" in clean_raw_lower or "a1c" in clean_raw_lower:
            marker_name, category = "HBA1C", "Chuyển hóa"
        elif "(nura) huyết sắc tố (hgb)" in clean_raw_lower or "huyết sắc tố (hgb)" in clean_raw_lower or "hgb" in clean_raw_lower:
            marker_name, category = "HGB", "Huyết học"
        elif "số lượng hồng cầu" in clean_raw_lower or "rbc" in clean_raw_lower:
            marker_name, category = "RBC", "Huyết học"
        elif any(sub in clean_raw_lower for sub in ["trung tính", "lympho", "mono", "ái toan", "ái kiềm", "neut", "lymph", "baso", "eo"]):
            marker_name, category = normalize_marker(raw_name)
        elif "số lượng bạch cầu" in clean_raw_lower or "wbc" in clean_raw_lower:
            marker_name, category = "WBC", "Bạch cầu"
        elif "nồng độ hst trung bình hc" in clean_raw_lower or "mchc" in clean_raw_lower:
            marker_name, category = "MCHC", "Huyết học"
        elif "lượng hst trung bình hc" in clean_raw_lower or "mch" in clean_raw_lower:
            marker_name, category = "MCH", "Huyết học"
        elif "hdl-cholesterol" in clean_raw_lower or "hdl" in clean_raw_lower:
            marker_name, category = "HDL_C", "Lipid"
        elif "định lượng ldl-c" in clean_raw_lower or "ldl" in clean_raw_lower:
            marker_name, category = "LDL_C", "Lipid"
        elif "định lượng cholesterol" in clean_raw_lower or "cholesterol" in clean_raw_lower:
            marker_name, category = "CHOLESTEROL", "Lipid"
        else:
            marker_name, category = normalize_marker(raw_name)

    value, unit = normalize_unit_and_value(marker_name, val_raw, unit_raw)

    if marker_name == "HGB" and value is not None:
        val_text = str(value)

    # Adjust HGB ref min/max if unit was g/L converted to g/dL
    if marker_name == "HGB" and unit_raw and "g/l" in unit_raw.lower():
        if ref_min is not None and ref_min > 50:
            ref_min = round(ref_min / 10.0, 2)
        if ref_max is not None and ref_max > 50:
            ref_max = round(ref_max / 10.0, 2)
        if value is not None:
            val_text = str(value)

    # Status determination
    if status_raw in ["NORMAL", "LOW", "HIGH"]:
        status = status_raw
    elif value is not None:
        if ref_min is not None and value < ref_min:
            status = "LOW"
        elif ref_max is not None and value > ref_max:
            status = "HIGH"
        else:
            status = "NORMAL"
    else:
        status = "NORMAL"

    return {
        "category": category,
        "marker_name": marker_name,
        "raw_name": raw_name,
        "value": value,
        "value_text": val_text,
        "unit": unit,
        "ref_min": ref_min,
        "ref_max": ref_max,
        "status": status
    }


class MatsuokaParser:
    facility_name = "T-Matsuoka"
    test_date = "2026-06-10"
    prompt = MATSUOKA_VISION_PROMPT

    @staticmethod
    def parse_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return parse_matsuoka_record(rec)
