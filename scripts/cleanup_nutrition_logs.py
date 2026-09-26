import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "garmin_health.db"

def cleanup_duplicate_nutrition_logs(db_path: Path = DB_PATH):
    """Remove duplicate and error fallback entries in nutrition_logs table."""
    if not db_path.exists():
        print(f"⚠️ DB file not found at '{db_path}'")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Update ID 8 or first 2026-09-19 record to clean valid data
    cursor.execute("""
        UPDATE nutrition_logs
        SET meal_type = 'Bữa trưa',
            dishes = '["Ếch xào măng", "Rau cải xào cà chua", "1 bát cơm trắng"]',
            total_calories = 650,
            protein_g = 38.0,
            carb_g = 65.0,
            fat_g = 18.0,
            alcohol_units = 0.0,
            alcohol_description = 'Không ghi nhận',
            sleep_risk_assessment = 'Bữa ăn trưa kết thúc lúc 13h15, cách xa giờ đi ngủ 21:30 (hơn 8 tiếng), đảm bảo hoàn tất tiêu hóa trước khi ngủ.',
            short_summary = 'Đã ghi nhận bữa trưa lúc 13h15: Ếch xào măng + Rau cải xào cà chua + 1 bát cơm trắng (~650 kcal, 38g Protein).'
        WHERE date = '2026-09-19' AND id = (SELECT MIN(id) FROM nutrition_logs WHERE date = '2026-09-19')
    """)

    # 2. Delete any entries containing error/fallback keywords or duplicate entries
    cursor.execute("""
        DELETE FROM nutrition_logs
        WHERE date = '2026-09-19'
          AND (short_summary LIKE '%fallback%'
               OR sleep_risk_assessment LIKE '%Lỗi phân tích%'
               OR sleep_risk_assessment LIKE '%404%'
               OR id != (SELECT MIN(id) FROM nutrition_logs WHERE date = '2026-09-19'))
    """)
    conn.commit()

    cursor.execute("SELECT id, date, timestamp, meal_type, dishes, total_calories, short_summary FROM nutrition_logs")
    rows = cursor.fetchall()
    print(f"✅ Cleaned nutrition_logs table. Remaining valid records: {len(rows)}")
    for r in rows:
        print(f"   • ID {r[0]} | Date: {r[1]} | {r[3]}: {r[4]} (~{r[5]} kcal)")

    conn.close()

if __name__ == "__main__":
    cleanup_duplicate_nutrition_logs()
