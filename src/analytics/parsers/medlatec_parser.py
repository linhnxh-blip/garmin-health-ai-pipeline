"""
Medlatec Lab Report Parser & Normalizer.
Handles OCR extraction and anchor-based normalization for Medlatec lab reports.
"""

from typing import Dict, Any, Optional
from src.analytics.blood_normalizer import normalize_marker, normalize_unit_and_value

MEDLATEC_VISION_PROMPT = """Bạn là chuyên gia bóc tách dữ liệu phiếu xét nghiệm y khoa Medlatec.
Nhiệm vụ của bạn là đọc từng dòng trong bảng kết quả xét nghiệm và chuyển đổi thành JSON.

QUY TẮC BÓC TÁCH PHIẾU MEDLATEC:
1. PHÂN BIỆT MÁU VÀ NƯỚC TIỂU:
   - Các dòng thuộc 'Xét nghiệm sinh hoá nước tiểu' hoặc 'Tổng phân tích nước tiểu' (đơn vị mg/dL, BC/µL, HC/µL hoặc 'Âm tính'): BẮT BUỘC đặt section là "NUOC_TIEU" và category là "Nước tiểu".
2. CÁC CHỈ SỐ BẢNG HUYẾT HỌC & SINH HÓA (MEDLATEC FORM):
   - "Huyết sắc tố (Hb)" -> HGB (unit: g/dL). KHÔNG nhầm với "HbA1c".
   - "Số lượng hồng cầu (RBC)" -> RBC (unit: Tera/L).
   - "Tỷ lệ hồng cầu nhỏ" -> RBC_MICRO_PCT.
   - "Tỷ lệ hồng cầu lớn" -> RBC_MACRO_PCT.
   - "Số lượng hồng cầu có nhân (NRBC)" -> NRBC_ABS.
   - "Thể tích khối hồng cầu (HCT)" -> HCT.
   - "Lượng Hb trung bình HC (MCH)" -> MCH (unit: pg).
   - "Nồng độ Hb trung bình HC (MCHC)" -> MCHC (unit: g/dL).
   - "Số lượng bạch cầu (WBC)" -> WBC (unit: G/L).
   - "Cholesterol (Cobas c503)*" -> CHOLESTEROL (unit: mmol/L).
   - "LDL-Cholesterol (Cobas c503)" -> LDL_C (unit: mmol/L).
   - "HDL-Cholesterol (Cobas c503)" -> HDL_C (unit: mmol/L).
   - "HbA1c (G11)*" -> HBA1C (unit: %).

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


def parse_medlatec_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize and validate a raw extracted record from a Medlatec lab report."""
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

        # 1. HbA1c vs HGB
        if "hba1c" in clean_raw_lower or "a1c" in clean_raw_lower:
            marker_name, category = "HBA1C", "Chuyển hóa"

        elif "huyết sắc tố (hb)" in clean_raw_lower or ("huyết sắc tố" in clean_raw_lower and "nura" not in clean_raw_lower and "hba1c" not in clean_raw_lower):
            marker_name, category = "HGB", "Huyết học"

        # 2. RBC vs RBC Micro/Macro vs NRBC
        elif "có nhân" in clean_raw_lower or "nrbc" in clean_raw_lower:
            marker_name, category = "NRBC_ABS", "Huyết học"

        elif "tỷ lệ hồng cầu nhỏ" in clean_raw_lower or "hồng cầu nhỏ" in clean_raw_lower:
            marker_name, category = "RBC_MICRO_PCT", "Huyết học"

        elif "tỷ lệ hồng cầu lớn" in clean_raw_lower or "hồng cầu lớn" in clean_raw_lower:
            marker_name, category = "RBC_MACRO_PCT", "Huyết học"

        elif "số lượng hồng cầu (rbc)" in clean_raw_lower or ("số lượng hồng cầu" in clean_raw_lower and "có nhân" not in clean_raw_lower):
            marker_name, category = "RBC", "Huyết học"

        # 3. HCT / MCH / MCHC
        elif "thể tích khối hồng cầu" in clean_raw_lower or "hct" in clean_raw_lower:
            marker_name, category = "HCT", "Huyết học"

        elif "nồng độ hb trung bình hc" in clean_raw_lower or "mchc" in clean_raw_lower:
            marker_name, category = "MCHC", "Huyết học"

        elif "lượng hb trung bình hc" in clean_raw_lower or "mch" in clean_raw_lower:
            marker_name, category = "MCH", "Huyết học"

        # 4. Total WBC vs WBC Sub-types
        elif any(sub in clean_raw_lower for sub in ["trung tính", "lympho", "mono", "ái toan", "ái kiềm", "hạt", "neut", "lymph", "baso", "eo"]):
            marker_name, category = normalize_marker(raw_name)

        elif "số lượng bạch cầu (wbc)" in clean_raw_lower or "số lượng bạch cầu" in clean_raw_lower:
            marker_name, category = "WBC", "Bạch cầu"

        # 5. Lipid: HDL-C / LDL-C vs Cholesterol
        elif "hdl-cholesterol" in clean_raw_lower or "hdl" in clean_raw_lower:
            marker_name, category = "HDL_C", "Lipid"

        elif "ldl-cholesterol" in clean_raw_lower or "ldl" in clean_raw_lower:
            marker_name, category = "LDL_C", "Lipid"

        elif "cholesterol" in clean_raw_lower:
            marker_name, category = "CHOLESTEROL", "Lipid"

        else:
            marker_name, category = normalize_marker(raw_name)

    value, unit = normalize_unit_and_value(marker_name, val_raw, unit_raw)

    if marker_name == "HGB" and value is not None:
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


class MedlatecParser:
    facility_name = "Medlatec"
    test_date = "2026-03-28"
    prompt = MEDLATEC_VISION_PROMPT

    @staticmethod
    def parse_record(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return parse_medlatec_record(rec)
