import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional
from config.settings import settings
from .schema import (
    CREATE_RAW_GARMIN_DATA_TABLE,
    CREATE_DAILY_METRICS_TABLE,
    CREATE_AI_REPORTS_TABLE,
    CREATE_NUTRITION_LOGS_TABLE
)

@contextmanager
def get_db_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    target_path = db_path or settings.absolute_db_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db(db_path: Optional[Path] = None) -> Path:
    target_path = db_path or settings.absolute_db_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection(target_path) as conn:
        cursor = conn.cursor()
        cursor.execute(CREATE_RAW_GARMIN_DATA_TABLE)
        cursor.execute(CREATE_DAILY_METRICS_TABLE)
        cursor.execute(CREATE_AI_REPORTS_TABLE)
        cursor.execute(CREATE_NUTRITION_LOGS_TABLE)

        # Auto-migrate columns if table existed with older schema
        cursor.execute("PRAGMA table_info(daily_metrics)")
        dm_cols = [row[1] for row in cursor.fetchall()]
        if "awake_duration_seconds" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN awake_duration_seconds INTEGER")
        if "respiration_min" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN respiration_min REAL")
        if "respiration_max" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN respiration_max REAL")
        if "respiration_avg" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN respiration_avg REAL")
        if "spo2_avg" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN spo2_avg REAL")
        if "spo2_min" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN spo2_min REAL")
        if "training_load_7d" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN training_load_7d REAL")
        if "training_readiness_score" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN training_readiness_score INTEGER")
        if "recovery_time_hours" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN recovery_time_hours INTEGER")
        if "training_status" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN training_status TEXT")
        if "skin_temp_deviation" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN skin_temp_deviation REAL")
        if "weight_kg" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN weight_kg REAL")
        if "body_fat_pct" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN body_fat_pct REAL")
        if "muscle_mass_pct" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN muscle_mass_pct REAL")
        if "visceral_fat" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN visceral_fat INTEGER")
        if "nap_duration_seconds" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN nap_duration_seconds INTEGER")
        if "nap_body_battery_recharge" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN nap_body_battery_recharge INTEGER")
        if "step_goal" not in dm_cols:
            cursor.execute("ALTER TABLE daily_metrics ADD COLUMN step_goal INTEGER")

        cursor.execute("PRAGMA table_info(ai_reports)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        if "raw_prompt" not in existing_cols:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN raw_prompt TEXT")
        if "model_used" not in existing_cols:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN model_used TEXT")
        if "status" not in existing_cols:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN status TEXT DEFAULT 'SUCCESS'")
        if "delivered_status" not in existing_cols:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN delivered_status TEXT DEFAULT 'PENDING'")

        conn.commit()
    return target_path
