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
    """Retrieve nutrition logs recorded for a given date (YYYY-MM-DD), deduplicating similar meal entries and ignoring API fallback error records."""
    target_date = date_str or datetime.now().strftime("%Y-%m-%d")
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, date, timestamp, meal_type, dishes, total_calories,
                   protein_g, carb_g, fat_g, alcohol_units, alcohol_description,
                   sleep_risk_assessment, short_summary, image_path, created_at, raw_ai_response
            FROM nutrition_logs
            WHERE date = ? OR date(timestamp) = ?
            ORDER BY timestamp ASC
        """, (target_date, target_date))
        rows = cursor.fetchall()
        result = []
        seen_dishes = set()
        for r in rows:
            d = dict(r)
            risk = str(d.get("sleep_risk_assessment") or "")
            raw_err = str(d.get("raw_ai_response") or "")
            tot_cal = float(d.get("total_calories") or 0)
            tot_p = float(d.get("protein_g") or 0)

            # Skip fallback error records from Vision API
            if ("401" in risk or "Unauthenticated" in risk or "Gemini Vision API chưa được xác thực" in risk or "Lỗi kết nối" in risk
                or "401" in raw_err or "UNAUTHENTICATED" in raw_err):
                continue
            if d.get("dishes") and "Bữa ăn chưa phân biệt" in str(d.get("dishes")) and tot_cal == 600 and tot_p == 30:
                continue

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
    """Purge duplicate & invalid Vision API fallback error logs in SQLite database."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Purge Vision API fallback error records
        cursor.execute(
            """
            DELETE FROM nutrition_logs
            WHERE sleep_risk_assessment LIKE '%401%'
               OR sleep_risk_assessment LIKE '%Unauthenticated%'
               OR sleep_risk_assessment LIKE '%Gemini Vision API chưa được xác thực%'
               OR sleep_risk_assessment LIKE '%Lỗi kết nối Gemini Vision API%'
               OR raw_ai_response LIKE '%401%'
               OR raw_ai_response LIKE '%UNAUTHENTICATED%'
               OR (dishes LIKE '%Bữa ăn chưa phân biệt%' AND total_calories = 600 AND protein_g = 30)
            """
        )
        fallback_deleted = cursor.rowcount

        # 2. Purge duplicates
        cursor.execute("SELECT id, date, dishes, image_path FROM nutrition_logs ORDER BY id ASC")
        rows = cursor.fetchall()
        
        seen_keys = set()
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
        total_purged = fallback_deleted + len(ids_to_delete)
        if total_purged > 0:
            print(f"🧹 Cleaned up {total_purged} duplicate/fallback error nutrition logs from database.")

        return total_purged


def get_remaining_nutrition_quota(
    user_date: Optional[str] = None,
    date_str: Optional[str] = None,
    weight_kg: float = 65.3,
    day_type: str = "rest",
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Calculate remaining calorie and macro quotas for today using dynamic target source of truth from nutrition_calculator.
    Formula: remaining = target - sum(intraday_logged_macros).
    """
    from datetime import datetime
    from src.services.nutrition_calculator import calculate_daily_macro_targets

    target_d = user_date or date_str or datetime.now().strftime("%Y-%m-%d")
    summary = get_today_nutrition_summary(target_d, db_path=db_path)

    eff_weight = weight_kg
    if eff_weight in (65.3, 65.6):
        try:
            from src.db.connection import get_db_connection
            with get_db_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT weight_kg FROM daily_metrics WHERE date = ?", (target_d,))
                row = cursor.fetchone()
                if row and row[0]:
                    eff_weight = float(row[0])
        except Exception:
            pass

    targets = calculate_daily_macro_targets(target_date=target_d, weight_kg=eff_weight, day_type=day_type)

    target_cal = targets["target_calories"]
    target_p = targets["protein_g"]
    target_c = targets["carb_g"]
    target_f = targets["fat_g"]

    logged_cal = summary["total_cal"]
    logged_p = summary["total_protein"]
    logged_c = summary["total_carbs"]
    logged_f = summary["total_fat"]

    rem_cal = round(max(0.0, target_cal - logged_cal), 1)
    rem_p = round(max(0.0, target_p - logged_p), 1)
    rem_c = round(max(0.0, target_c - logged_c), 1)
    rem_f = round(max(0.0, target_f - logged_f), 1)

    return {
        "target": targets,
        "logged": summary,
        "remaining_cal": rem_cal,
        "remaining_protein": rem_p,
        "remaining_carbs": rem_c,
        "remaining_fat": rem_f
    }


def reparse_uncalculated_meal_logs(
    db_path: Optional[Path] = None,
    target_date: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Scan meal/nutrition logs for records with missing or zero calories/protein,
    re-analyze them using AI (with fallback & retry models), and update them in SQLite.
    """
    from src.analytics.vision_analyst import analyze_quick_log_text

    def _extract_meal_text(raw_val: Any) -> str:
        if not raw_val:
            return ""
        if isinstance(raw_val, list):
            return ", ".join(str(x).strip() for x in raw_val if x)
        s = str(raw_val).strip()
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return ", ".join(str(x).strip() for x in parsed if x)
                if isinstance(parsed, dict) and "dishes" in parsed:
                    return _extract_meal_text(parsed["dishes"])
            except Exception:
                pass
        return s

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Determine table name (nutrition_logs or meal_logs)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('nutrition_logs', 'meal_logs')")
        tables = [r[0] for r in cursor.fetchall()]
        if not tables:
            return {"status": "error", "message": "Neither 'nutrition_logs' nor 'meal_logs' table exists in database.", "total_found": 0, "updated_count": 0}

        table_name = "nutrition_logs" if "nutrition_logs" in tables else tables[0]

        # 2. Inspect available column names
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = {row[1]: row[1] for row in cursor.fetchall()}

        text_col = "raw_text" if "raw_text" in cols else ("dishes" if "dishes" in cols else None)
        cal_col = "calories" if "calories" in cols else ("total_calories" if "total_calories" in cols else None)
        p_col = "protein" if "protein" in cols else ("protein_g" if "protein_g" in cols else None)
        c_col = "carb" if "carb" in cols else ("carb_g" if "carb_g" in cols else None)
        f_col = "fat" if "fat" in cols else ("fat_g" if "fat_g" in cols else None)

        if not text_col or not cal_col or not p_col:
            return {
                "status": "error",
                "message": f"Required columns not found in {table_name} (found: text={text_col}, cal={cal_col}, p={p_col}).",
                "total_found": 0,
                "updated_count": 0
            }

        # 3. Query uncalculated or zero macro records
        query = f"""
            SELECT id, date, timestamp, {text_col}, {cal_col}, {p_col}
            FROM {table_name}
            WHERE ({cal_col} IS NULL OR {cal_col} = 0 OR {p_col} = 0 OR {p_col} IS NULL)
              AND {text_col} IS NOT NULL AND TRIM({text_col}) != '' AND TRIM({text_col}) != '[]'
        """
        params = []
        if target_date:
            query += " AND date = ?"
            params.append(target_date)

        query += " ORDER BY id ASC"
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    if not rows:
        return {"status": "success", "message": "No uncalculated meal records found.", "total_found": 0, "updated_count": 0, "records": []}

    updated_records = []
    updated_count = 0

    for r in rows:
        rec_id = r[0]
        rec_date = r[1]
        rec_ts = r[2] or f"{rec_date} 12:00:00"
        raw_text_val = r[3]
        old_cal = r[4]
        old_p = r[5]

        meal_desc = _extract_meal_text(raw_text_val)
        if not meal_desc:
            continue

        # 4. Call AI estimation with built-in retry and fallback
        analysis = analyze_quick_log_text(meal_desc, timestamp=rec_ts)

        new_cal = int(round(analysis.get("total_calories") or analysis.get("calories") or 0))
        new_p = round(float(analysis.get("protein_g") or analysis.get("protein") or 0.0), 1)
        new_c = round(float(analysis.get("carb_g") or analysis.get("carb") or 0.0), 1)
        new_f = round(float(analysis.get("fat_g") or analysis.get("fat") or 0.0), 1)
        meal_type = analysis.get("meal_type")
        short_summary = analysis.get("short_summary")
        sleep_risk = analysis.get("sleep_risk_assessment")

        rec_info = {
            "id": rec_id,
            "date": rec_date,
            "description": meal_desc,
            "old": {"calories": old_cal, "protein": old_p},
            "new": {"calories": new_cal, "protein": new_p, "carb": new_c, "fat": new_f}
        }

        # 5. Update SQLite record
        if not dry_run:
            with get_db_connection(db_path) as conn:
                cur = conn.cursor()
                update_fields = [f"{cal_col} = ?", f"{p_col} = ?"]
                update_vals = [new_cal, new_p]

                if c_col:
                    update_fields.append(f"{c_col} = ?")
                    update_vals.append(new_c)
                if f_col:
                    update_fields.append(f"{f_col} = ?")
                    update_vals.append(new_f)

                if "meal_type" in cols and meal_type:
                    update_fields.append("meal_type = COALESCE(?, meal_type)")
                    update_vals.append(meal_type)
                if "short_summary" in cols and short_summary:
                    update_fields.append("short_summary = COALESCE(?, short_summary)")
                    update_vals.append(short_summary)
                if "sleep_risk_assessment" in cols and sleep_risk:
                    update_fields.append("sleep_risk_assessment = COALESCE(?, sleep_risk_assessment)")
                    update_vals.append(sleep_risk)

                update_vals.append(rec_id)
                update_sql = f"UPDATE {table_name} SET {', '.join(update_fields)} WHERE id = ?"
                cur.execute(update_sql, tuple(update_vals))
                conn.commit()

        updated_count += 1
        updated_records.append(rec_info)

    return {
        "status": "success",
        "table": table_name,
        "dry_run": dry_run,
        "total_found": len(rows),
        "updated_count": updated_count,
        "records": updated_records
    }

