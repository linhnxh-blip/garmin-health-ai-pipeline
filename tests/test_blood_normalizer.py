import sqlite3
import pytest
from pathlib import Path

from src.analytics.blood_normalizer import normalize_marker, normalize_unit_and_value
from src.db.connection import init_db, get_db_connection
from src.db.schema import UPSERT_BLOOD_TESTS_SQL
from scripts.ingest_blood_test import compare_blood_tests


def test_normalize_marker_canonical_mapping():
    # Huyết học
    mk, cat = normalize_marker("Số lượng hồng cầu (RBC)")
    assert mk == "RBC"
    assert cat == "Huyết học"

    mk, cat = normalize_marker("(NURA) Huyết sắc tố (Hb)")
    assert mk == "HGB"
    assert cat == "Huyết học"

    mk, cat = normalize_marker("Độ phân bố HC (RDW-CV)")
    assert mk == "RDW_CV"
    assert cat == "Huyết học"

    # Tiểu cầu
    mk, cat = normalize_marker("Số lượng tiểu cầu (PLT)")
    assert mk == "PLT"
    assert cat == "Tiểu cầu"

    # Bạch cầu
    mk, cat = normalize_marker("Bạch cầu đoạn trung tính %")
    assert mk == "NEUT_PCT"
    assert cat == "Bạch cầu"

    # Gan mật
    mk, cat = normalize_marker("AST (SGOT)")
    assert mk == "AST"
    assert cat == "Gan mật"

    # Chuyển hóa
    mk, cat = normalize_marker("Định lượng Glucose máu")
    assert mk == "GLUCOSE"
    assert cat == "Chuyển hóa"

    # Thận
    mk, cat = normalize_marker("Creatinin máu")
    assert mk == "CREATININE"
    assert cat == "Thận"

    # Lipid
    mk, cat = normalize_marker("Triglyceride")
    assert mk == "TRIGLYCERIDE"
    assert cat == "Lipid"

    # Nước tiểu
    mk, cat = normalize_marker("Tỷ trọng nước tiểu")
    assert mk == "URINE_SG"
    assert cat == "Nước tiểu"


def test_strict_canonical_mapping_exclusions():
    # 1. HBA1C vs HGB
    mk, cat = normalize_marker("Định lượng HbA1c")
    assert mk == "HBA1C"
    assert cat == "Chuyển hóa"

    # 2. Anti-HBs vs HGB
    mk, cat = normalize_marker("Anti-HBs (Miễn dịch tự động)")
    assert mk == "ANTI_HBS"
    assert cat == "Nội tiết & Miễn dịch"

    # 3. MCH vs MCHC
    mk, cat = normalize_marker("Nồng độ Hb trung bình HC (MCHC)")
    assert mk == "MCHC"
    assert cat == "Huyết học"

    mk, cat = normalize_marker("Lượng Hb trung bình HC (MCH)")
    assert mk == "MCH"
    assert cat == "Huyết học"

    # 4. HCT vs RBC
    mk, cat = normalize_marker("Thể tích khối hồng cầu (HCT)")
    assert mk == "HCT"
    assert cat == "Huyết học"

    # 5. RBC Micro / Macro
    mk, cat = normalize_marker("Tỷ lệ hồng cầu nhỏ (Micro RBC)")
    assert mk == "RBC_MICRO_PCT"
    assert cat == "Huyết học"

    # 6. WBC vs Sub-types
    mk, cat = normalize_marker("Bạch cầu ưa bazo (BASON)")
    assert mk == "BASO_ABS"
    assert cat == "Bạch cầu"

    mk, cat = normalize_marker("Bạch cầu đoạn trung tính %")
    assert mk == "NEUT_PCT"
    assert cat == "Bạch cầu"

    mk, cat = normalize_marker("Số lượng bạch cầu (WBC)")
    assert mk == "WBC"
    assert cat == "Bạch cầu"

    # 7. Cholesterol vs LDL-C
    mk, cat = normalize_marker("Định lượng Cholesterol")
    assert mk == "CHOLESTEROL"
    assert cat == "Lipid"

    mk, cat = normalize_marker("Định lượng LDL-C")
    assert mk == "LDL_C"
    assert cat == "Lipid"

    # 8. ASCII Slug Fallback for Vietnamese text
    mk, cat = normalize_marker("Màu sắc bất thường")
    assert mk == "MAU_SAC_BAT_THUONG"
    assert cat == "Khác"



def test_normalize_unit_and_value_hgb():
    # HGB conversion g/L -> g/dL
    val, unit = normalize_unit_and_value("HGB", 142.0, "g/L")
    assert val == 14.2
    assert unit == "g/dL"

    val2, unit2 = normalize_unit_and_value("HGB", 15.1, "g/dL")
    assert val2 == 15.1
    assert unit2 == "g/dL"

    # Other markers remain unchanged
    val3, unit3 = normalize_unit_and_value("GLUCOSE", 5.2, "mmol/L")
    assert val3 == 5.2
    assert unit3 == "mmol/L"


def test_compare_blood_tests_logic(tmp_path, capsys):
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        # Insert 2026-03-28 (Medlatec)
        cursor.execute(
            UPSERT_BLOOD_TESTS_SQL,
            ("2026-03-28", "Medlatec", "Huyết học", "HGB", "Huyết sắc tố", 14.2, "14.2", "g/dL", 13.0, 18.0, "NORMAL")
        )
        cursor.execute(
            UPSERT_BLOOD_TESTS_SQL,
            ("2026-03-28", "Medlatec", "Chuyển hóa", "GLUCOSE", "Glucose", 5.2, "5.2", "mmol/L", 3.9, 6.4, "NORMAL")
        )

        # Insert 2026-06-10 (T-Matsuoka)
        cursor.execute(
            UPSERT_BLOOD_TESTS_SQL,
            ("2026-06-10", "T-Matsuoka", "Huyết học", "HGB", "HGB", 14.8, "14.8", "g/dL", 13.0, 18.0, "NORMAL")
        )
        cursor.execute(
            UPSERT_BLOOD_TESTS_SQL,
            ("2026-06-10", "T-Matsuoka", "Gan mật", "AST", "AST", 25.0, "25.0", "U/L", 0.0, 37.0, "NORMAL")
        )
        conn.commit()

    compare_blood_tests(db_path=db_file)
    captured = capsys.readouterr().out

    assert "BẢNG ĐỐI SOÁT & SO SÁNH KẾT QUẢ XÉT NGHIỆM MÁU" in captured
    assert "`HGB`" in captured
    assert "+0.6" in captured
    assert "`GLUCOSE`" in captured
    assert "`AST`" in captured


def test_interactive_review_mode():
    from scripts.ingest_blood_test import interactive_review_records

    sample_records = [
        {"category": "Huyết học", "marker_name": "HGB", "raw_name": "Huyết sắc tố", "value": 14.8, "value_text": "14.8", "unit": "g/dL", "ref_min": 13.5, "ref_max": 18.0, "status": "NORMAL"},
        {"category": "Bạch cầu", "marker_name": "WBC", "raw_name": "Số lượng bạch cầu", "value": 3.15, "value_text": "3.15", "unit": "G/L", "ref_min": 3.6, "ref_max": 10.6, "status": "LOW"},
    ]

    inputs = iter(["2 3.70", ""])
    def mock_input(prompt):
        return next(inputs)

    reviewed = interactive_review_records(sample_records, "2026-06-10", "T-Matsuoka", input_fn=mock_input)
    assert reviewed is not None
    assert len(reviewed) == 2
    assert reviewed[1]["marker_name"] == "WBC"
    assert reviewed[1]["value"] == 3.70
    assert reviewed[1]["value_text"] == "3.7"
    assert reviewed[1]["status"] == "NORMAL"

    # Test cancel
    cancelled = interactive_review_records(sample_records, "2026-06-10", "T-Matsuoka", input_fn=lambda _: "q")
    assert cancelled is None


def test_evaluate_blood_trends(tmp_path):
    from src.analytics.blood_trend_evaluator import evaluate_blood_trends
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        # Date 1: 2026-03-28
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Huyết học", "HGB", "HGB", 14.8, "14.8", "g/dL", 13.5, 18.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Huyết học", "HCT", "HCT", 43.6, "43.6", "%", 40.0, 54.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Chuyển hóa", "GLUCOSE", "Glucose", 5.73, "5.73", "mmol/L", 3.9, 6.4, "HIGH"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Lipid", "TRIGLYCERIDE", "Triglyceride", 1.08, "1.08", "mmol/L", 0.4, 1.7, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Lipid", "HDL_C", "HDL-C", 1.18, "1.18", "mmol/L", 1.0, 2.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Bạch cầu", "WBC", "WBC", 3.15, "3.15", "G/L", 4.0, 9.0, "LOW"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-03-28", "Medlatec", "Thận", "URIC_ACID", "Uric Acid", 435.9, "435.9", "umol/L", 220.0, 420.0, "HIGH"))

        # Date 2: 2026-06-10
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Huyết học", "HGB", "HGB", 14.2, "14.2", "g/dL", 13.5, 18.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Huyết học", "HCT", "HCT", 41.3, "41.3", "%", 40.0, 54.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Chuyển hóa", "GLUCOSE", "Glucose", 6.16, "6.16", "mmol/L", 3.9, 6.4, "HIGH"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Lipid", "TRIGLYCERIDE", "Triglyceride", 2.07, "2.07", "mmol/L", 0.4, 1.7, "HIGH"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Lipid", "HDL_C", "HDL-C", 1.30, "1.30", "mmol/L", 1.0, 2.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Bạch cầu", "WBC", "WBC", 3.76, "3.76", "G/L", 4.0, 9.0, "LOW"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Thận", "URIC_ACID", "Uric Acid", 442.0, "442.0", "umol/L", 220.0, 420.0, "HIGH"))
        conn.commit()

    res = evaluate_blood_trends(db_file)
    assert res["previous_date"] == "2026-03-28"
    assert res["current_date"] == "2026-06-10"
    assert res["tg_hdl_ratio"] == 1.59  # 2.07 / 1.30

    evals = {e["marker_name"]: e for e in res["evaluations"]}
    assert evals["GLUCOSE"]["status"] == "DECLINED"
    assert "Tiền tiểu đường ADA" in evals["GLUCOSE"]["status_label"]
    assert "HFCS" in evals["GLUCOSE"]["recommendation"]

    assert evals["TRIGLYCERIDE"]["status"] == "DECLINED"
    assert "1.59" in evals["TRIGLYCERIDE"]["recommendation"]

    assert evals["URIC_ACID"]["status"] == "DECLINED"
    assert "2.8 - 3.2L" in evals["URIC_ACID"]["recommendation"]

    assert evals["WBC"]["status"] == "DECLINED"
    assert "Bạch cầu nền thấp" in evals["WBC"]["status_label"]

    assert evals["HGB"]["status"] == "STABLE"
    assert evals["HCT"]["status"] == "STABLE"
    assert evals["HDL_C"]["status"] == "IMPROVED"

    assert "📋 NHẬN XÉT XU HƯỚNG VÀ HƯỚNG XỬ LÝ SINH LÝ Y HỌC THỂ THAO" in res["summary_text"]


def test_get_latest_blood_summary(tmp_path):
    from src.analytics.prompt_engine import get_latest_blood_summary
    db_file = tmp_path / "garmin_health.db"
    init_db(db_file)

    with get_db_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Huyết học", "HGB", "HGB", 14.2, "14.2", "g/dL", 13.5, 18.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Huyết học", "HCT", "HCT", 41.3, "41.3", "%", 40.0, 54.0, "NORMAL"))
        cursor.execute(UPSERT_BLOOD_TESTS_SQL, ("2026-06-10", "T-Matsuoka", "Thận", "URIC_ACID", "Uric Acid", 450.0, "450.0", "umol/L", 220.0, 420.0, "HIGH"))
        conn.commit()

    summary = get_latest_blood_summary(db_file)
    assert "2026-06-10 tại T-Matsuoka" in summary
    assert "HGB = 14.2 g/dL" in summary
    assert "HCT = 41.3 %" in summary
    assert "Uric Acid sát trần bão hòa EULAR" in summary



