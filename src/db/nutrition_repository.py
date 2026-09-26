import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .connection import get_db_connection
from .schema import INSERT_NUTRITION_LOG_SQL

def save_nutrition_log(log_data: Dict[str, Any], db_path: Optional[Path] = None) -> int:
    """Save a nutrition/meal analysis log into nutrition_logs table with smart deduplication.
    Returns the inserted or existing log record ID.
    """
    dishes = log_data.get("dishes", [])
    dishes_json = json.dumps(dishes, ensure_ascii=False) if isinstance(dishes, list) else str(dishes)

    dt_str = log_data.get("date") or datetime.now().strftime("%Y-%m-%d")
    timestamp_str = log_data.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    img_path = log_data.get("image_path", "")

    dish_items = dishes if isinstance(dishes, list) else [dishes]
    dish_key = "".join(sorted([str(item).lower().strip() for item in dish_items]))

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Check if exact same image_path was already logged
        if img_path:
            cursor.execute("SELECT id FROM nutrition_logs WHERE image_path = ? AND image_path != ''", (img_path,))
            row = cursor.fetchone()
            if row:
                print(f"ℹ️ Image '{img_path}' already exists in DB (ID: {row[0]}). Skipping duplicate insertion.")
                return row[0]

        # 2. Check if identical dishes were logged on same date within last 30 minutes
        cursor.execute(
            """
            SELECT id, timestamp, dishes FROM nutrition_logs
            WHERE (date = ? OR date(timestamp) = ?)
            ORDER BY id DESC
            """,
            (dt_str, dt_str)
        )
        existing_rows = cursor.fetchall()
        for r_id, r_ts, r_dishes_raw in existing_rows:
            try:
                r_items = json.loads(r_dishes_raw) if r_dishes_raw else []
            except Exception:
                r_items = [r_dishes_raw]
            r_key = "".join(sorted([str(item).lower().strip() for item in r_items]))

            if dish_key and r_key == dish_key:
                try:
                    t1 = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    t0 = datetime.strptime(r_ts, "%Y-%m-%d %H:%M:%S")
                    if abs((t1 - t0).total_seconds()) < 1800:
                        print(f"ℹ️ Duplicate meal entry detected within 30m window (ID: {r_id}). Updating existing log instead of inserting duplicate.")
                        cursor.execute(
                            """
                            UPDATE nutrition_logs SET
                                total_calories = ?, protein_g = ?, carb_g = ?, fat_g = ?,
                                image_path = COALESCE(NULLIF(?, ''), image_path)
                            WHERE id = ?
                            """,
                            (
                                log_data.get("total_calories"),
                                log_data.get("protein_g"),
                                log_data.get("carb_g"),
                                log_data.get("fat_g"),
                                img_path,
                                r_id
                            )
                        )
                        conn.commit()
                        return r_id
                except Exception:
                    pass

        # 3. Insert new unique record
        params = (
            dt_str,
            timestamp_str,
            log_data.get("meal_type", "Bữa ăn / Nhậu"),
            dishes_json,
            log_data.get("total_calories"),
            log_data.get("protein_g"),
            log_data.get("carb_g"),
            log_data.get("fat_g"),
            log_data.get("alcohol_units", 0.0),
            log_data.get("alcohol_description", ""),
            log_data.get("sleep_risk_assessment", ""),
            log_data.get("short_summary", ""),
            img_path,
            log_data.get("raw_ai_response", "")
        )
        cursor.execute(INSERT_NUTRITION_LOG_SQL, params)
        conn.commit()
        return cursor.lastrowid

def get_nutrition_logs_by_date(date_str: Optional[str] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve nutrition logs recorded for a given date (YYYY-MM-DD), deduplicating similar meal entries."""
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, timestamp, meal_type, dishes, total_calories,
                   protein_g, carb_g, fat_g, alcohol_units, alcohol_description,
                   sleep_risk_assessment, short_summary, image_path, created_at
            FROM nutrition_logs
            WHERE date = ? OR date(timestamp) = ?
            ORDER BY timestamp ASC
        """, (target_date, target_date))
        rows = cursor.fetchall()
        result = []
        seen_dishes = set()
        for r in rows:
            d = dict(r)
            try:
                d["dishes"] = json.loads(d["dishes"]) if d["dishes"] else []
            except Exception:
                pass

            dish_items = d.get("dishes") or []
            dish_key = "".join(sorted([str(item).lower().strip() for item in dish_items])) if isinstance(dish_items, list) else str(dish_items).lower().strip()
            if dish_key and dish_key in seen_dishes:
                continue
            if dish_key:
                seen_dishes.add(dish_key)
            result.append(d)
        return result

def get_today_nutrition_summary(date_str: Optional[str] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Calculate total nutrition calories and macros logged for today (or specified date_str YYYY-MM-DD)
    using deduplicated meal records.
    Returns dict: {'total_cal': int, 'total_protein': float, 'total_carbs': float, 'total_fat': float}.
    """
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    logs = get_nutrition_logs_by_date(target_date, db_path=db_path)
    tot_cal = sum(int(l.get("total_calories") or 0) for l in logs)
    tot_p = sum(float(l.get("protein_g") or 0.0) for l in logs)
    tot_c = sum(float(l.get("carb_g") or 0.0) for l in logs)
    tot_f = sum(float(l.get("fat_g") or 0.0) for l in logs)
    return {
        "total_cal": tot_cal,
        "total_protein": round(tot_p, 1),
        "total_carbs": round(tot_c, 1),
        "total_fat": round(tot_f, 1)
    }

def delete_duplicate_nutrition_logs(db_path: Optional[Path] = None) -> int:
    """Purge duplicate nutrition logs in SQLite database, keeping only the earliest entry per meal/dishes on each date."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, date, dishes, image_path FROM nutrition_logs ORDER BY id ASC")
        rows = cursor.fetchall()
        
        seen_keys = set()
        deleted_count = 0
        ids_to_delete = []

        for r_id, r_date, r_dishes, r_img in rows:
            try:
                items = json.loads(r_dishes) if r_dishes else []
            except Exception:
                items = [r_dishes]
            
            d_key = "".join(sorted([str(i).lower().strip() for i in items]))
            combo_key = f"{r_date}_{d_key}" if d_key else f"{r_date}_img_{r_img}"

            if combo_key in seen_keys:
                ids_to_delete.append(r_id)
            else:
                seen_keys.add(combo_key)

        if ids_to_delete:
            cursor.executemany("DELETE FROM nutrition_logs WHERE id = ?", [(i,) for i in ids_to_delete])
            conn.commit()
            deleted_count = len(ids_to_delete)
            print(f"🧹 Cleaned up {deleted_count} duplicate nutrition logs from database.")

        return deleted_count

