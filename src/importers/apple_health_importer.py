import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from src.db.connection import get_db_connection, init_db
from src.ingestion.garmin_client import get_garmin_client

def parse_apple_health_date(date_str: str) -> Optional[str]:
    """Parse Apple Health XML date string (e.g. '2026-09-19 08:30:00 +0700') to YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        # Most common Apple Health format: 'YYYY-MM-DD HH:MM:SS TZ'
        parts = date_str.strip().split()
        if parts:
            return parts[0]
    except Exception:
        pass
    return None

def import_apple_health_export(
    file_path: str,
    sync_to_garmin: bool = True
) -> Dict[str, Any]:
    """Import weight, body fat & health metrics from Apple Health export.xml or export.zip.
    
    Parses HKQuantityTypeIdentifierBodyMass, HKQuantityTypeIdentifierBodyFatPercentage,
    HKQuantityTypeIdentifierLeanBodyMass, etc. and saves to SQLite daily_metrics table.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"❌ Apple Health export file not found at: {path}")

    print(f"📦 Processing Apple Health export file: '{path}'...")
    xml_file_obj = None
    temp_dir = None

    if path.suffix.lower() == ".zip":
        print("🔓 Extracting 'export.xml' from Apple Health export.zip...")
        z = zipfile.ZipFile(path, 'r')
        xml_member = None
        for name in z.namelist():
            if name.endswith("export.xml"):
                xml_member = name
                break
        if not xml_member:
            raise ValueError("❌ 'export.xml' not found inside the zip file!")
        xml_file_obj = z.open(xml_member)
    elif path.suffix.lower() == ".xml":
        xml_file_obj = open(path, "rb")
    else:
        raise ValueError("❌ Unsupported file format! Please provide 'export.zip' or 'export.xml'.")

    # Group metrics by date: { 'YYYY-MM-DD': { 'weight_kg': float, 'body_fat_pct': float, ... } }
    daily_records: Dict[str, Dict[str, Any]] = {}

    print("⚡ Streaming and parsing Apple Health XML records...")
    count_records = 0
    try:
        # High-performance iterparse to handle large XML files memory-efficiently
        for event, elem in ET.iterparse(xml_file_obj, events=("end",)):
            if elem.tag == "Record":
                rec_type = elem.attrib.get("type", "")
                val_str = elem.attrib.get("value")
                start_date_raw = elem.attrib.get("startDate") or elem.attrib.get("creationDate")
                date_key = parse_apple_health_date(start_date_raw)

                if date_key and val_str is not None:
                    try:
                        val = float(val_str)
                        if date_key not in daily_records:
                            daily_records[date_key] = {
                                "weight_kg": None,
                                "body_fat_pct": None,
                                "muscle_mass_pct": None,
                                "active_calories": None,
                                "total_steps": None,
                                "resting_heart_rate": None
                            }

                        rec = daily_records[date_key]

                        # Cân nặng (Body Mass)
                        if rec_type == "HKQuantityTypeIdentifierBodyMass":
                            unit = (elem.attrib.get("unit") or "kg").lower()
                            w_kg = val * 0.45359237 if ("lb" in unit or "lbs" in unit) else val
                            rec["weight_kg"] = round(w_kg, 2)
                            count_records += 1

                        # % Mỡ cơ thể (Body Fat Percentage)
                        elif rec_type == "HKQuantityTypeIdentifierBodyFatPercentage":
                            fat_pct = val * 100.0 if val <= 1.0 else val
                            rec["body_fat_pct"] = round(fat_pct, 1)
                            count_records += 1

                        # Khối lượng cơ / nạc (Lean Body Mass)
                        elif rec_type == "HKQuantityTypeIdentifierLeanBodyMass":
                            rec["muscle_mass_pct"] = round(val, 1)
                            count_records += 1

                        # Nhịp tim nghỉ
                        elif rec_type == "HKQuantityTypeIdentifierRestingHeartRate":
                            rec["resting_heart_rate"] = int(val)

                    except (ValueError, TypeError):
                        pass

                # Clear element from memory to stay lightweight
                elem.clear()
    finally:
        if xml_file_obj:
            xml_file_obj.close()

    print(f"📊 Parsed {count_records} body composition records across {len(daily_records)} days from Apple Health.")

    if not daily_records:
        print("⚠️ No valid weight/body composition records found in the Apple Health export.")
        return {"processed_days": 0, "records_count": 0}

    # Save to SQLite database
    init_db()
    inserted_count = 0
    latest_date_synced = None
    latest_weight_synced = None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        for d_key, m_dict in sorted(daily_records.items()):
            if m_dict["weight_kg"] is not None or m_dict["body_fat_pct"] is not None:
                cursor.execute(
                    """
                    INSERT INTO daily_metrics (date, weight_kg, body_fat_pct, muscle_mass_pct, resting_heart_rate, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(date) DO UPDATE SET
                        weight_kg = COALESCE(excluded.weight_kg, daily_metrics.weight_kg),
                        body_fat_pct = COALESCE(excluded.body_fat_pct, daily_metrics.body_fat_pct),
                        muscle_mass_pct = COALESCE(excluded.muscle_mass_pct, daily_metrics.muscle_mass_pct),
                        resting_heart_rate = COALESCE(excluded.resting_heart_rate, daily_metrics.resting_heart_rate),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        d_key,
                        m_dict["weight_kg"],
                        m_dict["body_fat_pct"],
                        m_dict["muscle_mass_pct"],
                        m_dict["resting_heart_rate"]
                    )
                )
                inserted_count += 1
                if m_dict["weight_kg"] is not None:
                    latest_date_synced = d_key
                    latest_weight_synced = m_dict["weight_kg"]

        conn.commit()

    print(f"✅ Successfully updated SQLite `daily_metrics` for {inserted_count} days!")

    # Optionally sync latest weight to Garmin Connect
    if sync_to_garmin and latest_date_synced and latest_weight_synced:
        try:
            print(f"🔄 Syncing latest Apple Health weight ({latest_weight_synced} kg on {latest_date_synced}) to Garmin Connect...")
            client = get_garmin_client()
            iso_ts = f"{latest_date_synced}T08:00:00.000Z"
            m_latest = daily_records[latest_date_synced]
            client.add_body_composition(
                timestamp=iso_ts,
                weight=latest_weight_synced,
                percent_fat=m_latest.get("body_fat_pct"),
                muscle_mass=m_latest.get("muscle_mass_pct")
            )
            print(f"✅ Successfully synced latest weight ({latest_weight_synced} kg) to Garmin Connect cloud!")
        except Exception as g_err:
            print(f"ℹ️ Garmin sync notice: {g_err}")

    return {
        "processed_days": inserted_count,
        "records_count": count_records,
        "latest_weight": latest_weight_synced,
        "latest_date": latest_date_synced
    }
