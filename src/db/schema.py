CREATE_RAW_GARMIN_DATA_TABLE = """
CREATE TABLE IF NOT EXISTS raw_garmin_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    data_type TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, data_type) ON CONFLICT REPLACE
);
"""

CREATE_DAILY_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    sleep_score INTEGER,
    sleep_duration_seconds INTEGER,
    deep_sleep_seconds INTEGER,
    rem_sleep_seconds INTEGER,
    light_sleep_seconds INTEGER,
    awake_duration_seconds INTEGER,
    hrv_weekly_avg REAL,
    hrv_last_night REAL,
    hrv_status TEXT,
    resting_heart_rate INTEGER,
    avg_stress_level INTEGER,
    max_stress_level INTEGER,
    body_battery_charged INTEGER,
    body_battery_drained INTEGER,
    body_battery_highest INTEGER,
    body_battery_lowest INTEGER,
    active_calories INTEGER,
    total_steps INTEGER,
    step_goal INTEGER,
    vo2_max REAL,
    respiration_min REAL,
    respiration_max REAL,
    respiration_avg REAL,
    spo2_avg REAL,
    spo2_min REAL,
    training_load_7d REAL,
    training_readiness_score INTEGER,
    recovery_time_hours INTEGER,
    training_status TEXT,
    skin_temp_deviation REAL,
    weight_kg REAL,
    body_fat_pct REAL,
    muscle_mass_pct REAL,
    visceral_fat INTEGER,
    activities_summary TEXT,
    nap_duration_seconds INTEGER,
    nap_body_battery_recharge INTEGER,
    raw_sync_timestamp DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_AI_REPORTS_TABLE = """
CREATE TABLE IF NOT EXISTS ai_reports (
    date TEXT PRIMARY KEY,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    report_markdown TEXT NOT NULL,
    raw_prompt TEXT,
    model_used TEXT,
    status TEXT DEFAULT 'SUCCESS',
    delivered_status TEXT DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

UPSERT_AI_REPORTS_SQL = """
INSERT INTO ai_reports (
    date,
    prompt_tokens,
    completion_tokens,
    report_markdown,
    raw_prompt,
    model_used,
    status,
    delivered_status,
    created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT(date) DO UPDATE SET
    prompt_tokens = COALESCE(excluded.prompt_tokens, ai_reports.prompt_tokens),
    completion_tokens = COALESCE(excluded.completion_tokens, ai_reports.completion_tokens),
    report_markdown = excluded.report_markdown,
    raw_prompt = COALESCE(excluded.raw_prompt, ai_reports.raw_prompt),
    model_used = COALESCE(excluded.model_used, ai_reports.model_used),
    status = COALESCE(excluded.status, ai_reports.status),
    delivered_status = COALESCE(excluded.delivered_status, ai_reports.delivered_status),
    created_at = CURRENT_TIMESTAMP;
"""

UPSERT_DAILY_METRICS_SQL = """
INSERT INTO daily_metrics (
    date,
    sleep_score,
    sleep_duration_seconds,
    deep_sleep_seconds,
    rem_sleep_seconds,
    light_sleep_seconds,
    awake_duration_seconds,
    hrv_weekly_avg,
    hrv_last_night,
    hrv_status,
    resting_heart_rate,
    avg_stress_level,
    max_stress_level,
    body_battery_charged,
    body_battery_drained,
    body_battery_highest,
    body_battery_lowest,
    active_calories,
    total_steps,
    step_goal,
    vo2_max,
    respiration_min,
    respiration_max,
    respiration_avg,
    spo2_avg,
    spo2_min,
    training_load_7d,
    training_readiness_score,
    recovery_time_hours,
    training_status,
    skin_temp_deviation,
    weight_kg,
    body_fat_pct,
    muscle_mass_pct,
    visceral_fat,
    activities_summary,
    raw_sync_timestamp,
    updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    sleep_score = COALESCE(excluded.sleep_score, daily_metrics.sleep_score),
    sleep_duration_seconds = COALESCE(excluded.sleep_duration_seconds, daily_metrics.sleep_duration_seconds),
    deep_sleep_seconds = COALESCE(excluded.deep_sleep_seconds, daily_metrics.deep_sleep_seconds),
    rem_sleep_seconds = COALESCE(excluded.rem_sleep_seconds, daily_metrics.rem_sleep_seconds),
    light_sleep_seconds = COALESCE(excluded.light_sleep_seconds, daily_metrics.light_sleep_seconds),
    awake_duration_seconds = COALESCE(excluded.awake_duration_seconds, daily_metrics.awake_duration_seconds),
    hrv_weekly_avg = COALESCE(excluded.hrv_weekly_avg, daily_metrics.hrv_weekly_avg),
    hrv_last_night = COALESCE(excluded.hrv_last_night, daily_metrics.hrv_last_night),
    hrv_status = COALESCE(excluded.hrv_status, daily_metrics.hrv_status),
    resting_heart_rate = COALESCE(excluded.resting_heart_rate, daily_metrics.resting_heart_rate),
    avg_stress_level = COALESCE(excluded.avg_stress_level, daily_metrics.avg_stress_level),
    max_stress_level = COALESCE(excluded.max_stress_level, daily_metrics.max_stress_level),
    body_battery_charged = COALESCE(excluded.body_battery_charged, daily_metrics.body_battery_charged),
    body_battery_drained = COALESCE(excluded.body_battery_drained, daily_metrics.body_battery_drained),
    body_battery_highest = COALESCE(excluded.body_battery_highest, daily_metrics.body_battery_highest),
    body_battery_lowest = COALESCE(excluded.body_battery_lowest, daily_metrics.body_battery_lowest),
    active_calories = COALESCE(excluded.active_calories, daily_metrics.active_calories),
    total_steps = COALESCE(excluded.total_steps, daily_metrics.total_steps),
    step_goal = COALESCE(excluded.step_goal, daily_metrics.step_goal),
    vo2_max = COALESCE(excluded.vo2_max, daily_metrics.vo2_max),
    respiration_min = COALESCE(excluded.respiration_min, daily_metrics.respiration_min),
    respiration_max = COALESCE(excluded.respiration_max, daily_metrics.respiration_max),
    respiration_avg = COALESCE(excluded.respiration_avg, daily_metrics.respiration_avg),
    spo2_avg = COALESCE(excluded.spo2_avg, daily_metrics.spo2_avg),
    spo2_min = COALESCE(excluded.spo2_min, daily_metrics.spo2_min),
    training_load_7d = COALESCE(excluded.training_load_7d, daily_metrics.training_load_7d),
    training_readiness_score = COALESCE(excluded.training_readiness_score, daily_metrics.training_readiness_score),
    recovery_time_hours = COALESCE(excluded.recovery_time_hours, daily_metrics.recovery_time_hours),
    training_status = COALESCE(excluded.training_status, daily_metrics.training_status),
    skin_temp_deviation = COALESCE(excluded.skin_temp_deviation, daily_metrics.skin_temp_deviation),
    weight_kg = COALESCE(excluded.weight_kg, daily_metrics.weight_kg),
    body_fat_pct = COALESCE(excluded.body_fat_pct, daily_metrics.body_fat_pct),
    muscle_mass_pct = COALESCE(excluded.muscle_mass_pct, daily_metrics.muscle_mass_pct),
    visceral_fat = COALESCE(excluded.visceral_fat, daily_metrics.visceral_fat),
    activities_summary = COALESCE(excluded.activities_summary, daily_metrics.activities_summary),
    raw_sync_timestamp = COALESCE(excluded.raw_sync_timestamp, daily_metrics.raw_sync_timestamp),
    updated_at = CURRENT_TIMESTAMP;
"""

CREATE_NUTRITION_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS nutrition_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    meal_type TEXT,
    dishes TEXT,
    total_calories INTEGER,
    protein_g REAL,
    carb_g REAL,
    fat_g REAL,
    alcohol_units REAL,
    alcohol_description TEXT,
    sleep_risk_assessment TEXT,
    short_summary TEXT,
    image_path TEXT,
    raw_ai_response TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

INSERT_NUTRITION_LOG_SQL = """
INSERT INTO nutrition_logs (
    date,
    timestamp,
    meal_type,
    dishes,
    total_calories,
    protein_g,
    carb_g,
    fat_g,
    alcohol_units,
    alcohol_description,
    sleep_risk_assessment,
    short_summary,
    image_path,
    raw_ai_response,
    created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
"""

