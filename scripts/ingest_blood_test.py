import os
import sys
import io
import json
import sqlite3
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from PIL import Image

# Ensure project root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import settings
from src.db.connection import get_db_connection, init_db
from src.db.schema import UPSERT_BLOOD_TESTS_SQL
from src.analytics.parsers import (
    parse_medlatec_record,
    MEDLATEC_VISION_PROMPT,
    parse_matsuoka_record,
    MATSUOKA_VISION_PROMPT
)

from src.analytics.constants import CORE_SPORT_MARKERS




def extract_markers_from_image(image_path: Path, system_prompt: str) -> List[Dict[str, Any]]:
    """Call Gemini Vision API to OCR medical test image using facility-specific prompt."""
    api_key = settings.gemini_api_key
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in environment or settings!")

    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")

    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="JPEG", quality=95)
    img_jpeg_bytes = img_byte_arr.getvalue()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    image_part = types.Part.from_bytes(data=img_jpeg_bytes, mime_type="image/jpeg")

    candidate_models = [
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        getattr(settings, "gemini_vision_model", "gemini-2.5-flash"),
        "gemini-2.0-flash",
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    last_err = None
    for model in models_to_try:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[image_part, "Trích xuất toàn bộ các chỉ số xét nghiệm trong ảnh này."],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
            raw_text = response.text or ""
            clean_text = raw_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
            clean_text = clean_text.strip()

            items = json.loads(clean_text)
            if isinstance(items, list):
                return items
        except Exception as e:
            last_err = e
            print(f"⚠️ Warning: Model {model} failed on {image_path.name}: {e}")

    print(f"❌ Failed to extract markers from {image_path.name}: {last_err}")
    return []


def render_review_table(records: List[Dict[str, Any]], test_date: str, facility: str):
    """Render terminal summary table for human-in-the-loop review."""
    print("\n" + "=" * 95)
    print(f"📋 BẢNG RÀO SOÁT DỮ LIỆU XÉT NGHIỆM MÁU - {facility.upper()} (Ngày: {test_date})")
    print("=" * 95)
    print(f"{'STT':<5} | {'Mã Chỉ Số':<14} | {'Tên Tiếng Việt':<32} | {'Giá Trị':<10} | {'Đơn Vị':<10} | {'Ngưỡng Tham Chiếu'}")
    print("-" * 95)
    for idx, rec in enumerate(records, 1):
        mk = rec.get("marker_name", "")
        raw_n = rec.get("raw_name", "")
        if len(raw_n) > 30:
            raw_n = raw_n[:27] + "..."
        v_str = str(rec.get("value_text", rec.get("value", "")))
        unit = rec.get("unit", "")
        r_min = rec.get("ref_min")
        r_max = rec.get("ref_max")
        ref_str = f"{r_min if r_min is not None else ''} - {r_max if r_max is not None else ''}".strip(" -") or "N/A"
        
        star = "⭐ [CORE]" if mk in CORE_SPORT_MARKERS else ""
        print(f"{idx:<5} | {mk:<14} | {raw_n:<32} | {v_str:<10} | {unit:<10} | {ref_str:<15} {star}")
    print("-" * 95)


def interactive_review_records(
    records: List[Dict[str, Any]],
    test_date: str,
    facility: str,
    input_fn=input
) -> Optional[List[Dict[str, Any]]]:
    """Interactively review and edit extracted records before saving to SQLite."""
    if not records:
        return records

    records_copy = [dict(r) for r in records]

    while True:
        render_review_table(records_copy, test_date, facility)
        prompt_msg = "\nXác nhận lưu vào DB? (Nhấn ENTER để đồng ý, hoặc gõ '<STT> <Giá trị mới>' để sửa, hoặc 'q' để hủy): "
        user_input = input_fn(prompt_msg).strip()

        if user_input == "":
            return records_copy

        if user_input.lower() == "q":
            print(f"⚠️ Đã hủy thao tác lưu dữ liệu ngày {test_date}.")
            return None

        parts = user_input.split(maxsplit=1)
        if len(parts) == 2:
            stt_str, new_val_str = parts[0], parts[1]
            if stt_str.isdigit():
                stt = int(stt_str)
                if 1 <= stt <= len(records_copy):
                    target_rec = records_copy[stt - 1]
                    old_val = target_rec.get("value_text")
                    try:
                        new_val_float = float(new_val_str)
                        target_rec["value"] = new_val_float
                        target_rec["value_text"] = str(new_val_float)
                    except ValueError:
                        target_rec["value"] = None
                        target_rec["value_text"] = new_val_str

                    # Recalculate status
                    v = target_rec.get("value")
                    r_min = target_rec.get("ref_min")
                    r_max = target_rec.get("ref_max")
                    if v is not None:
                        if r_min is not None and v < r_min:
                            target_rec["status"] = "LOW"
                        elif r_max is not None and v > r_max:
                            target_rec["status"] = "HIGH"
                        else:
                            target_rec["status"] = "NORMAL"

                    print(f"\n✏️ Đã cập nhật STT {stt} ({target_rec['marker_name']}): '{old_val}' -> '{target_rec['value_text']}'")
                    continue

        print("\n❌ Cú pháp không hợp lệ. Hãy nhập '<STT> <Giá trị mới>' (ví dụ: '1 14.2'), bấm ENTER để lưu, hoặc 'q' để hủy.")


def process_blood_test_images(
    image_dir: Path,
    db_path: Optional[Path] = None,
    review_mode: bool = False,
    facility_filter: Optional[str] = None
):
    """Scan and process Medlatec and T-Matsuoka images into SQLite blood_tests table using dedicated facility parsers."""
    target_dir = Path(image_dir)
    if not target_dir.exists():
        print(f"❌ Error: Image directory '{target_dir}' does not exist.")
        return

    init_db(db_path)

    fac_norm = (facility_filter or "").strip().lower()

    medlatec_files = sorted(list(target_dir.glob("IMG_*.*")))
    matsuoka_files = sorted(list(target_dir.glob("Screenshot*.*")))

    groups = []
    if fac_norm in ["medlatec", "all", "auto", ""]:
        if medlatec_files:
            groups.append(("Medlatec", "2026-03-28", medlatec_files, parse_medlatec_record, MEDLATEC_VISION_PROMPT))
    if fac_norm in ["matsuoka", "t-matsuoka", "all", "auto", ""]:
        if matsuoka_files:
            groups.append(("T-Matsuoka", "2026-06-10", matsuoka_files, parse_matsuoka_record, MATSUOKA_VISION_PROMPT))

    if not groups:
        print(f"⚠️ Warning: No image files matching facility filter '{facility_filter or 'all'}' found in '{target_dir}'.")
        return

    total_inserted = 0

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        for facility, test_date, files, parse_fn, prompt_str in groups:
            print(f"\n🏥 Processing Facility: {facility} (Test Date: {test_date}) - Found {len(files)} image files...", flush=True)
            facility_records: Dict[str, Dict[str, Any]] = {}

            for img_path in files:
                print(f"  📸 Extracting from image: {img_path.name} (Parser: {parse_fn.__name__})...", flush=True)
                raw_records = extract_markers_from_image(img_path, prompt_str)
                print(f"     Found {len(raw_records)} raw markers.", flush=True)

                for rec in raw_records:
                    processed = parse_fn(rec)
                    if not processed:
                        continue
                    facility_records[processed["marker_name"]] = processed

            records_list = list(facility_records.values())

            if review_mode:
                final_records = interactive_review_records(records_list, test_date, facility)
            else:
                final_records = records_list

            if not final_records:
                print(f"⏩ Skipped inserting records for {facility} ({test_date}).")
                continue

            for processed in final_records:
                cursor.execute(
                    UPSERT_BLOOD_TESTS_SQL,
                    (
                        test_date,
                        facility,
                        processed["category"],
                        processed["marker_name"],
                        processed["raw_name"],
                        processed["value"],
                        processed["value_text"],
                        processed["unit"],
                        processed["ref_min"],
                        processed["ref_max"],
                        processed["status"]
                    )
                )
                total_inserted += 1

            print(f"🎉 Đã lưu thành công dữ liệu ngày {test_date} vào SQLite!")

        conn.commit()

    print(f"\n🎉 Successfully processed and inserted/updated {total_inserted} blood test records in SQLite `blood_tests`!")


def compare_blood_tests(db_path: Optional[Path] = None):
    """Compare blood test markers between 2026-03-28 (Medlatec) and 2026-06-10 (T-Matsuoka)."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT test_date, facility, category, marker_name, raw_name, value, value_text, unit, ref_min, ref_max, status
            FROM blood_tests
            WHERE test_date IN ('2026-03-28', '2026-06-10')
            ORDER BY category, marker_name, test_date
            """
        )
        rows = [dict(r) for r in cursor.fetchall()]

    m_28 = {r["marker_name"]: r for r in rows if r["test_date"] == "2026-03-28"}
    m_10 = {r["marker_name"]: r for r in rows if r["test_date"] == "2026-06-10"}

    common_markers = sorted(list(set(m_28.keys()) & set(m_10.keys())))
    only_28 = sorted(list(set(m_28.keys()) - set(m_10.keys())))
    only_10 = sorted(list(set(m_10.keys()) - set(m_28.keys())))

    print("\n" + "=" * 100)
    print("🩸 BẢNG ĐỐI SOÁT & SO SÁNH KẾT QUẢ XÉT NGHIỆM MÁU (2026-03-28 vs 2026-06-10)")
    print("=" * 100 + "\n")

    print("### 📊 1. CÁC CHỈ SỐ DÙNG CHUNG CỦA CẢ 2 LẦN XÉT NGHIỆM:")
    print("| Danh mục | Mã Chỉ Số | Tên Gốc (Medlatec) | Medlatec (2026-03-28) | T-Matsuoka (2026-06-10) | Đơn vị | Ngưỡng Chuẩn | Biến đổi / Đánh giá |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    status_icon = {"NORMAL": "✅", "LOW": "🔻 LOW", "HIGH": "🔺 HIGH"}

    for mk in common_markers:
        r1 = m_28[mk]
        r2 = m_10[mk]
        cat = r1.get("category") or r2.get("category") or "Chung"
        raw_n = r1.get("raw_name") or r2.get("raw_name")
        v1_str = f"{r1['value_text']} {status_icon.get(r1['status'], '')}".strip()
        v2_str = f"{r2['value_text']} {status_icon.get(r2['status'], '')}".strip()
        unit = r1.get("unit") or r2.get("unit") or ""
        ref_str = f"{r1.get('ref_min') or ''} - {r1.get('ref_max') or ''}".strip(" -") or "N/A"

        diff_str = "Duy trì"
        if r1.get("value") is not None and r2.get("value") is not None:
            diff = round(r2["value"] - r1["value"], 2)
            if diff > 0:
                diff_str = f"+{diff}"
            elif diff < 0:
                diff_str = f"{diff}"
            else:
                diff_str = "0.0"

        print(f"| {cat} | `{mk}` | {raw_n} | {v1_str} | {v2_str} | {unit} | {ref_str} | {diff_str} |")

    if only_28:
        print("\n### 📌 2. CÁC CHỈ SỐ CHỈ CÓ TẠI MEDLATEC (2026-03-28):")
        print("| Danh mục | Mã Chỉ Số | Tên Gốc | Kết quả | Đơn vị | Ngưỡng Chuẩn | Trạng thái |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for mk in only_28:
            r = m_28[mk]
            st = status_icon.get(r['status'], r['status'])
            ref_str = f"{r.get('ref_min') or ''} - {r.get('ref_max') or ''}".strip(" -") or "N/A"
            print(f"| {r.get('category')} | `{mk}` | {r.get('raw_name')} | {r.get('value_text')} | {r.get('unit')} | {ref_str} | {st} |")

    if only_10:
        print("\n### 📌 3. CÁC CHỈ SỐ CHỈ CÓ TẠI T-MATSUOKA (2026-06-10):")
        print("| Danh mục | Mã Chỉ Số | Tên Gốc | Kết quả | Đơn vị | Ngưỡng Chuẩn | Trạng thái |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for mk in only_10:
            r = m_10[mk]
            st = status_icon.get(r['status'], r['status'])
            ref_str = f"{r.get('ref_min') or ''} - {r.get('ref_max') or ''}".strip(" -") or "N/A"
            print(f"| {r.get('category')} | `{mk}` | {r.get('raw_name')} | {r.get('value_text')} | {r.get('unit')} | {ref_str} | {st} |")

    # Trend Evaluation Block (Sports Medicine)
    from src.analytics.blood_trend_evaluator import evaluate_blood_trends
    trends = evaluate_blood_trends(db_path)
    print("\n" + trends.get("summary_text", ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest blood test result images into SQLite blood_tests table.")
    parser.add_argument("--image-dir", "--dir", default=r"C:\Users\linhn\Downloads\Photos-1-001", help="Path to directory containing images")
    parser.add_argument("--facility", choices=["medlatec", "matsuoka", "all", "auto"], default="auto", help="Specify facility parser (medlatec, matsuoka, or auto)")
    parser.add_argument("--compare", action="store_true", help="Compare test results between 2026-03-28 and 2026-06-10")
    parser.add_argument("--review", action="store_true", help="Enable interactive Human-in-the-loop review mode before DB commit")

    args = parser.parse_args()

    if args.compare:
        compare_blood_tests()
    else:
        process_blood_test_images(Path(args.image_dir), review_mode=args.review, facility_filter=args.facility)
