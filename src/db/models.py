from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

class DailyMetrics(BaseModel):
    """Pydantic model for daily normalized health metrics.
    Strict NULL policy: Any missing or unrecorded metric is None (NULL in DB).
    """
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    sleep_score: Optional[int] = Field(default=None, description="Sleep score (0-100)")
    sleep_duration_seconds: Optional[int] = Field(default=None, description="Total sleep time in seconds")
    deep_sleep_seconds: Optional[int] = Field(default=None, description="Deep sleep time in seconds")
    rem_sleep_seconds: Optional[int] = Field(default=None, description="REM sleep time in seconds")
    light_sleep_seconds: Optional[int] = Field(default=None, description="Light sleep time in seconds")
    awake_duration_seconds: Optional[int] = Field(default=None, description="Awake time in seconds during sleep")
    hrv_weekly_avg: Optional[float] = Field(default=None, description="7-day average HRV in ms")
    hrv_last_night: Optional[float] = Field(default=None, description="Overnight HRV in ms")
    hrv_status: Optional[str] = Field(default=None, description="HRV status string e.g. BALANCED")
    resting_heart_rate: Optional[int] = Field(default=None, description="Resting heart rate in bpm")
    avg_stress_level: Optional[int] = Field(default=None, description="Average stress level (1-100)")
    max_stress_level: Optional[int] = Field(default=None, description="Maximum stress level")
    body_battery_charged: Optional[int] = Field(default=None, description="Body battery charged points")
    body_battery_drained: Optional[int] = Field(default=None, description="Body battery drained points")
    body_battery_highest: Optional[int] = Field(default=None, description="Body battery highest value")
    body_battery_lowest: Optional[int] = Field(default=None, description="Body battery lowest value")
    active_calories: Optional[int] = Field(default=None, description="Active calories in kcal")
    total_steps: Optional[int] = Field(default=None, description="Total step count")
    vo2_max: Optional[float] = Field(default=None, description="VO2 Max value")
    respiration_min: Optional[float] = Field(default=None, description="Minimum overnight respiration rate (brpm)")
    respiration_max: Optional[float] = Field(default=None, description="Maximum overnight respiration rate (brpm)")
    respiration_avg: Optional[float] = Field(default=None, description="Average overnight respiration rate (brpm)")
    spo2_avg: Optional[float] = Field(default=None, description="Average overnight SpO2 percentage")
    spo2_min: Optional[float] = Field(default=None, description="Minimum overnight SpO2 percentage")
    training_load_7d: Optional[float] = Field(default=None, description="7-day total training load score")
    training_readiness_score: Optional[int] = Field(default=None, description="Training readiness score (1-100)")
    recovery_time_hours: Optional[int] = Field(default=None, description="Remaining recovery time in hours")
    training_status: Optional[str] = Field(default=None, description="Training status string e.g. PRODUCTIVE, RECOVERY, MAINTAINING")
    skin_temp_deviation: Optional[float] = Field(default=None, description="Overnight skin temperature deviation in degrees")
    activities_summary: Optional[str] = Field(default=None, description="JSON string of activities recorded on date")
    raw_sync_timestamp: Optional[str] = Field(default=None, description="Raw sync ISO timestamp")
    updated_at: Optional[str] = Field(default=None, description="Record last update ISO timestamp")

    def to_db_tuple(self) -> tuple:
        return (
            self.date,
            self.sleep_score,
            self.sleep_duration_seconds,
            self.deep_sleep_seconds,
            self.rem_sleep_seconds,
            self.light_sleep_seconds,
            self.awake_duration_seconds,
            self.hrv_weekly_avg,
            self.hrv_last_night,
            self.hrv_status,
            self.resting_heart_rate,
            self.avg_stress_level,
            self.max_stress_level,
            self.body_battery_charged,
            self.body_battery_drained,
            self.body_battery_highest,
            self.body_battery_lowest,
            self.active_calories,
            self.total_steps,
            self.vo2_max,
            self.respiration_min,
            self.respiration_max,
            self.respiration_avg,
            self.spo2_avg,
            self.spo2_min,
            self.training_load_7d,
            self.training_readiness_score,
            self.recovery_time_hours,
            self.training_status,
            self.skin_temp_deviation,
            self.activities_summary,
            self.raw_sync_timestamp,
            self.updated_at or datetime.now().isoformat()
        )

class RawGarminData(BaseModel):
    date: str
    data_type: str
    raw_json: str
    created_at: Optional[str] = None

class AIReport(BaseModel):
    date: str = Field(..., description="Report date in YYYY-MM-DD format")
    prompt_tokens: Optional[int] = 0
    completion_tokens: Optional[int] = 0
    report_markdown: str
    raw_prompt: Optional[str] = None
    model_used: Optional[str] = None
    status: str = "SUCCESS"
    delivered_status: str = "PENDING"
    created_at: Optional[str] = None

    def to_db_tuple(self) -> tuple:
        return (
            self.date,
            self.prompt_tokens or 0,
            self.completion_tokens or 0,
            self.report_markdown,
            self.raw_prompt,
            self.model_used,
            self.status,
            self.delivered_status,
        )
