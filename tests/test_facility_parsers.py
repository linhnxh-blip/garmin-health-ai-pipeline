import pytest
from src.analytics.parsers import parse_medlatec_record, parse_matsuoka_record


def test_parse_medlatec_record_anchors():
    # HGB
    rec = parse_medlatec_record({
        "section": "HUYET_HOC",
        "raw_name": "Huyết sắc tố (Hb)",
        "value": 14.8,
        "value_text": "14.8",
        "unit": "g/dL",
        "ref_min": 13.5,
        "ref_max": 18.0,
        "status": "NORMAL"
    })
    assert rec["marker_name"] == "HGB"
    assert rec["category"] == "Huyết học"
    assert rec["value"] == 14.8

    # RBC Micro PCT
    rec_micro = parse_medlatec_record({
        "section": "HUYET_HOC",
        "raw_name": "Tỷ lệ hồng cầu nhỏ",
        "value": 6.3,
        "value_text": "6.3",
        "unit": "%",
        "ref_min": None,
        "ref_max": None,
        "status": "NORMAL"
    })
    assert rec_micro["marker_name"] == "RBC_MICRO_PCT"
    assert rec_micro["category"] == "Huyết học"

    # Cholesterol Cobas
    rec_chol = parse_medlatec_record({
        "section": "HOA_SINH_MAU",
        "raw_name": "Cholesterol (Cobas c503)*",
        "value": 3.38,
        "value_text": "3.38",
        "unit": "mmol/L",
        "ref_min": None,
        "ref_max": 5.2,
        "status": "NORMAL"
    })
    assert rec_chol["marker_name"] == "CHOLESTEROL"
    assert rec_chol["category"] == "Lipid"

    # LDL-C Cobas
    rec_ldl = parse_medlatec_record({
        "section": "HOA_SINH_MAU",
        "raw_name": "LDL-Cholesterol (Cobas c503)",
        "value": 1.71,
        "value_text": "1.71",
        "unit": "mmol/L",
        "ref_min": None,
        "ref_max": 3.4,
        "status": "NORMAL"
    })
    assert rec_ldl["marker_name"] == "LDL_C"
    assert rec_ldl["category"] == "Lipid"

    # HbA1c
    rec_a1c = parse_medlatec_record({
        "section": "HOA_SINH_MAU",
        "raw_name": "HbA1c (G11)*",
        "value": 5.94,
        "value_text": "5.94",
        "unit": "%",
        "ref_min": None,
        "ref_max": 5.7,
        "status": "HIGH"
    })
    assert rec_a1c["marker_name"] == "HBA1C"
    assert rec_a1c["category"] == "Chuyển hóa"


def test_parse_matsuoka_record_anchors():
    # HGB conversion g/L -> g/dL
    rec_hgb = parse_matsuoka_record({
        "section": "HUYET_HOC",
        "raw_name": "(NURA) Huyết sắc tố (HGB)",
        "value": 142.0,
        "value_text": "142",
        "unit": "g/L",
        "ref_min": 130.0,
        "ref_max": 170.0,
        "status": "NORMAL"
    })
    assert rec_hgb["marker_name"] == "HGB"
    assert rec_hgb["value"] == 14.2
    assert rec_hgb["unit"] == "g/dL"

    # WBC
    rec_wbc = parse_matsuoka_record({
        "section": "HUYET_HOC",
        "raw_name": "Số lượng bạch cầu (WBC)",
        "value": 3.70,
        "value_text": "3.70",
        "unit": "G/L",
        "ref_min": 4.0,
        "ref_max": 10.0,
        "status": "LOW"
    })
    assert rec_wbc["marker_name"] == "WBC"
    assert rec_wbc["value"] == 3.70

    # Anti-HBs
    rec_anti = parse_matsuoka_record({
        "section": "MIEN_DICH",
        "raw_name": "Anti HBs miễn dịch tự động",
        "value": 827.0,
        "value_text": "827.0",
        "unit": "mUI/mL",
        "ref_min": 10.0,
        "ref_max": None,
        "status": "NORMAL"
    })
    assert rec_anti["marker_name"] == "ANTI_HBS"
    assert rec_anti["value"] == 827.0

    # Cholesterol & LDL_C
    rec_chol = parse_matsuoka_record({
        "section": "HOA_SINH_MAU",
        "raw_name": "Định lượng Cholesterol",
        "value": 4.27,
        "value_text": "4.27",
        "unit": "mmol/L",
        "ref_min": 0.0,
        "ref_max": 5.18,
        "status": "NORMAL"
    })
    assert rec_chol["marker_name"] == "CHOLESTEROL"

    rec_ldl = parse_matsuoka_record({
        "section": "HOA_SINH_MAU",
        "raw_name": "Định lượng LDL-C",
        "value": 2.03,
        "value_text": "2.03",
        "unit": "mmol/L",
        "ref_min": 0.0,
        "ref_max": 3.4,
        "status": "NORMAL"
    })
    assert rec_ldl["marker_name"] == "LDL_C"
