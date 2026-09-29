import re
import unicodedata
from typing import Dict, List, Tuple, Optional, Any


def remove_vietnamese_accents(text: str) -> str:
    """Convert Vietnamese accented string to plain ASCII."""
    if not text:
        return ""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = text.replace('Đ', 'D').replace('đ', 'd')
    return text


def _clean_str(s: str) -> str:
    if not s:
        return ""
    s_lower = s.strip().lower()
    s_norm = unicodedata.normalize("NFC", s_lower)
    return s_norm


from src.analytics.constants import CORE_SPORT_MARKERS, SUPPLEMENTARY_MARKERS




CANONICAL_MARKERS: Dict[str, Tuple[List[str], str]] = {

    # Huyết học
    "RBC_MICRO_PCT": (["tỷ lệ hồng cầu nhỏ", "hồng cầu nhỏ", "rbc micro", "micro rbc"], "Huyết học"),
    "RBC_MACRO_PCT": (["tỷ lệ hồng cầu lớn", "hồng cầu lớn", "rbc macro", "macro rbc"], "Huyết học"),
    "RBC": (["số lượng hồng cầu", "rbc", "(nura) số lượng hồng cầu", "số lượng hồng cầu (rbc)"], "Huyết học"),
    "HGB": (["huyết sắc tố", "hb", "hgb", "(nura) huyết sắc tố", "huyết sắc tố (hb)"], "Huyết học"),
    "HCT": (["thể tích khối hồng cầu", "thể tích khối hc", "hct", "thể tích khối hồng cầu (hct)"], "Huyết học"),
    "MCV": (["thể tích trung bình hc", "thể tích trung bình hồng cầu", "mcv", "thể tích trung bình hc (mcv)"], "Huyết học"),
    "MCH": (["lượng hb trung bình hc", "lượng hst trung bình hc", "mch", "lượng hb trung bình hc (mch)"], "Huyết học"),
    "MCHC": (["nồng độ hb trung bình hc", "nồng độ hst trung bình hc", "mchc", "nồng độ hb trung bình hc (mchc)"], "Huyết học"),
    "RDW_CV": (["độ phân bố hc (rdw-cv)", "rdw-cv", "rdw_cv", "độ phân bố hồng cầu (rdw-cv)"], "Huyết học"),
    "RDW_SD": (["độ phân bố hc (rdw-sd)", "rdw-sd", "rdw_sd", "dải phân bố hc (rdw)", "dải phân bố hồng cầu (rdw)"], "Huyết học"),

    # Tiểu cầu
    "PLT": (["số lượng tiểu cầu", "plt", "số lượng tiểu cầu (plt)"], "Tiểu cầu"),
    "MPV": (["thể tích trung bình tc", "mpv", "thể tích trung bình tiểu cầu", "thể tích trung bình tc (mpv)"], "Tiểu cầu"),
    "PCT": (["thể tích khối tiểu cầu", "pct", "thể tích khối tiểu cầu (pct)"], "Tiểu cầu"),
    "PDW": (["độ phân bố tc", "pdw", "dải phân bố tiểu cầu", "độ phân bố tc (pdw)"], "Tiểu cầu"),
    "P_LCR": (["tl tiểu cầu có kt lớn", "p-lcr", "p_lcr", "tỷ lệ tiểu cầu kích thước lớn", "tl tiểu cầu có kt lớn (p-lcr)"], "Tiểu cầu"),

    # Bạch cầu (Tổng)
    "WBC": (["số lượng bạch cầu (wbc)", "số lượng bạch cầu", "wbc", "(nura) số lượng bạch cầu"], "Bạch cầu"),

    # Bạch cầu thành phần con
    "NEUT_PCT": (["tỷ lệ % bạch cầu trung tính", "neut%", "bạch cầu đoạn trung tính %", "% bạch cầu trung tính", "tỷ lệ bạch cầu trung tính", "neutrophil %"], "Bạch cầu"),
    "NEUT_ABS": (["số lượng bạch cầu trung tính", "neut#", "số lượng bạch cầu đoạn trung tính", "neutrophil absolute"], "Bạch cầu"),

    "LYMPH_PCT": (["tỷ lệ % bạch cầu lympho", "lymph%", "% bạch cầu lympho", "tỷ lệ bạch cầu lympho"], "Bạch cầu"),
    "LYMPH_ABS": (["số lượng bạch cầu lympho", "lymph#"], "Bạch cầu"),

    "MONO_PCT": (["tỷ lệ % bạch cầu mono", "mono%", "% bạch cầu mono", "tỷ lệ bạch cầu mono"], "Bạch cầu"),
    "MONO_ABS": (["số lượng bạch cầu mono", "mono#"], "Bạch cầu"),

    "EO_PCT": (["tỷ lệ % bạch cầu ái toan", "eo%", "% bạch cầu ái toan", "tỷ lệ bạch cầu ái toan"], "Bạch cầu"),
    "EO_ABS": (["số lượng bạch cầu ái toan", "eo#", "bạch cầu ưa axit"], "Bạch cầu"),

    "BASO_PCT": (["tỷ lệ % bạch cầu ái kiềm", "baso%", "% bạch cầu ái kiềm", "tỷ lệ bạch cầu ái kiềm"], "Bạch cầu"),
    "BASO_ABS": (["số lượng bạch cầu ái kiềm", "baso#", "bạch cầu ưa bazo"], "Bạch cầu"),

    # Gan mật
    "AST": (["ast (sgot)", "ast", "sgot", "đo hoạt độ ast"], "Gan mật"),
    "ALT": (["alt (sgpt)", "alt", "sgpt", "đo hoạt độ alt"], "Gan mật"),
    "GGT": (["gamma gt", "ggt", "đo hoạt độ ggt", "gamma-gt"], "Gan mật"),
    "BILIRUBIN_TOTAL": (["bilirubin toàn phần", "bilirubin (bil)", "bilirubin total", "định lượng bilirubin toàn phần"], "Gan mật"),
    "BILIRUBIN_DIRECT": (["bilirubin trực tiếp", "bilirubin direct", "định lượng bilirubin trực tiếp"], "Gan mật"),
    "BILIRUBIN_INDIRECT": (["bilirubin gián tiếp", "bilirubin indirect"], "Gan mật"),

    # Chuyển hóa
    "GLUCOSE": (["glucose máu", "định lượng glucose máu", "glucose"], "Chuyển hóa"),
    "HBA1C": (["hba1c", "định lượng hba1c", "a1c"], "Chuyển hóa"),

    # Thận
    "UREA": (["ure máu", "ure trong máu", "định lượng ure", "urea"], "Thận"),
    "CREATININE": (["creatinin máu", "creatinin", "creatinine", "định lượng creatinine"], "Thận"),
    "URIC_ACID": (["acid uric máu", "acid uric", "uric acid", "định lượng acid uric"], "Thận"),

    # Lipid
    "TRIGLYCERIDE": (["triglyceride", "định lượng triglyceride", "triglycerides"], "Lipid"),
    "CHOLESTEROL": (["cholesterol toàn phần", "định lượng cholesterol", "cholesterol"], "Lipid"),
    "HDL_C": (["hdl-cholesterol", "hdl", "định lượng hdl-c", "hdl cholesterol", "hdl_c"], "Lipid"),
    "LDL_C": (["ldl-cholesterol", "ldl", "định lượng ldl-c", "ldl cholesterol", "ldl_c"], "Lipid"),

    # Nội tiết & Miễn dịch
    "IRON": (["sắt huyết thanh", "định lượng sắt huyết thanh", "iron"], "Nội tiết & Miễn dịch"),
    "CALCIUM": (["calci toàn phần", "canxi", "calcium", "định lượng calci toàn phần"], "Nội tiết & Miễn dịch"),
    "FT4": (["ft4", "định lượng ft4", "free t4"], "Nội tiết & Miễn dịch"),
    "TSH": (["tsh", "định lượng tsh"], "Nội tiết & Miễn dịch"),
    "AFP": (["afp", "alpha fetoprotein", "định lượng afp"], "Nội tiết & Miễn dịch"),
    "CA_72_4": (["ca 72-4", "cancer antigen 72-4", "ca 72.4", "định lượng ca 72-4"], "Nội tiết & Miễn dịch"),
    "ANTI_HBS": (["anti-hbs", "anti hbs miễn dịch tự động", "anti hbs", "anti hbs (miễn dịch tự động)"], "Nội tiết & Miễn dịch"),

    # Nước tiểu
    "URINE_SG": (["tỷ trọng nước tiểu", "nước tiểu tỷ trọng", "tỷ trọng", "sg", "specific gravity"], "Nước tiểu"),
    "URINE_PH": (["ph nước tiểu", "nước tiểu ph", "ph"], "Nước tiểu"),
    "URINE_LEU": (["bạch cầu nước tiểu", "nước tiểu bạch cầu", "leukocytes", "leu"], "Nước tiểu"),
    "URINE_NIT": (["nitrit nước tiểu", "nước tiểu nitrit", "nitrit", "nitrite", "nit"], "Nước tiểu"),
    "URINE_PRO": (["protein nước tiểu", "nước tiểu protein", "protein", "pro"], "Nước tiểu"),
    "URINE_GLU": (["glucose nước tiểu", "nước tiểu glucose", "glu"], "Nước tiểu"),
    "URINE_KET": (["ketone nước tiểu", "nước tiểu ketone", "ketone", "ketones", "ket"], "Nước tiểu"),
    "URINE_URO": (["urobilinogen nước tiểu", "nước tiểu urobilinogen", "urobilinogen", "uro"], "Nước tiểu"),
    "URINE_BIL": (["bilirubin nước tiểu", "nước tiểu bilirubin", "bilirubin", "bil"], "Nước tiểu"),
    "URINE_ERY": (["hồng cầu nước tiểu", "nước tiểu hồng cầu", "erythrocytes", "ery", "blood nước tiểu"], "Nước tiểu"),
    "URINE_ASC": (["acid ascorbic nước tiểu", "acid ascorbic", "ascorbic acid", "asc"], "Nước tiểu"),
}


def normalize_marker(raw_name: str) -> Tuple[str, str]:
    """
    Map raw marker name from lab report to (canonical_marker_key, category).
    """
    clean_raw = _clean_str(raw_name)
    if not clean_raw:
        return "UNKNOWN", "Khác"

    # --- STRICT PRIORITY EXCLUSION RULES ---

    # 1. HbA1c vs HGB
    if "hba1c" in clean_raw or "a1c" in clean_raw:
        return "HBA1C", "Chuyển hóa"

    # 2. Anti-HBs vs HGB
    if "anti-hbs" in clean_raw or "anti hbs" in clean_raw or "antihbs" in clean_raw:
        return "ANTI_HBS", "Nội tiết & Miễn dịch"

    # 3. MCH vs MCHC
    if "mchc" in clean_raw or "nồng độ" in clean_raw:
        if "hb" in clean_raw or "hst" in clean_raw or "mchc" in clean_raw:
            return "MCHC", "Huyết học"
    if "mch" in clean_raw or ("lượng hb" in clean_raw or "lượng hst" in clean_raw):
        if "nồng độ" not in clean_raw and "mchc" not in clean_raw:
            return "MCH", "Huyết học"

    # 4. HCT vs RBC
    if "hct" in clean_raw or "thể tích khối" in clean_raw:
        if "hồng cầu" in clean_raw or "hc" in clean_raw or "hct" in clean_raw:
            return "HCT", "Huyết học"

    # 5. RBC Micro / Macro vs RBC Total
    if "hồng cầu nhỏ" in clean_raw or "micro" in clean_raw:
        return "RBC_MICRO_PCT", "Huyết học"
    if "hồng cầu lớn" in clean_raw or "macro" in clean_raw:
        return "RBC_MACRO_PCT", "Huyết học"

    # 6. WBC vs WBC Sub-types (Lympho, Mono, Neutrophil, Eosinophil, Basophil)
    wbc_subtypes = ["lympho", "mono", "ái toan", "ái kiềm", "trung tính", "neut", "lymph", "baso", "eo", "ưa axit", "ưa bazo"]
    if any(sub in clean_raw for sub in wbc_subtypes):
        if "neut" in clean_raw or "trung tính" in clean_raw:
            if "%" in clean_raw or "tỷ lệ" in clean_raw or "đoạn" in clean_raw:
                return "NEUT_PCT", "Bạch cầu"
            return "NEUT_ABS", "Bạch cầu"
        if "lymph" in clean_raw or "lympho" in clean_raw:
            if "%" in clean_raw or "tỷ lệ" in clean_raw:
                return "LYMPH_PCT", "Bạch cầu"
            return "LYMPH_ABS", "Bạch cầu"
        if "mono" in clean_raw:
            if "%" in clean_raw or "tỷ lệ" in clean_raw:
                return "MONO_PCT", "Bạch cầu"
            return "MONO_ABS", "Bạch cầu"
        if "eo" in clean_raw or "ái toan" in clean_raw or "ưa axit" in clean_raw:
            if "%" in clean_raw or "tỷ lệ" in clean_raw:
                return "EO_PCT", "Bạch cầu"
            return "EO_ABS", "Bạch cầu"
        if "baso" in clean_raw or "ái kiềm" in clean_raw or "ưa bazo" in clean_raw:
            if "%" in clean_raw or "tỷ lệ" in clean_raw:
                return "BASO_PCT", "Bạch cầu"
            return "BASO_ABS", "Bạch cầu"

    # 7. Lipid: Cholesterol vs LDL-C vs HDL-C vs Triglyceride
    if "ldl" in clean_raw:
        return "LDL_C", "Lipid"
    if "hdl" in clean_raw:
        return "HDL_C", "Lipid"
    if "triglyceride" in clean_raw:
        return "TRIGLYCERIDE", "Lipid"
    if "cholesterol" in clean_raw and "ldl" not in clean_raw and "hdl" not in clean_raw:
        return "CHOLESTEROL", "Lipid"

    # --- GENERAL CANONICAL DICTIONARY MATCHING ---
    # First: Exact match
    for canonical_key, (aliases, category) in CANONICAL_MARKERS.items():
        for alias in aliases:
            if _clean_str(alias) == clean_raw:
                return canonical_key, category

    # Second: Substring match (longer aliases first)
    for canonical_key, (aliases, category) in CANONICAL_MARKERS.items():
        sorted_aliases = sorted(aliases, key=len, reverse=True)
        for alias in sorted_aliases:
            clean_alias = _clean_str(alias)
            if clean_alias and clean_alias in clean_raw:
                return canonical_key, category

    # Fallback if no match: ASCII slug generation
    ascii_name = remove_vietnamese_accents(raw_name)
    canonical_fallback = re.sub(r"[^A-Za-z0-9_]", "_", ascii_name.upper()).strip("_")
    while "__" in canonical_fallback:
        canonical_fallback = canonical_fallback.replace("__", "_")
    return canonical_fallback or "UNKNOWN", "Khác"


def normalize_unit_and_value(
    marker_name: str,
    value: Optional[float],
    unit: Optional[str]
) -> Tuple[Optional[float], Optional[str]]:
    """
    Normalize unit and value for specific markers (e.g. HGB g/L -> g/dL).
    Returns (value, unit).
    """
    norm_unit = (unit or "").strip()
    norm_val = value

    if marker_name == "HGB" and norm_unit and "g/l" in norm_unit.lower():
        if norm_val is not None:
            norm_val = round(norm_val / 10.0, 2)
        norm_unit = "g/dL"

    return norm_val, norm_unit
