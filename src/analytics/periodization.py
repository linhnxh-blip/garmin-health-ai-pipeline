"""
Garmin Health AI Pipeline - Training Periodization & Phase Detection State Machine
Manages training microcycle phases relative to target race dates and completed events.
"""

import json
from enum import Enum
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Any, Optional, Union

from config.settings import BASE_DIR


class TrainingPhase(str, Enum):
    BASE_BUILDING = "BASE_BUILDING"         # Giai đoạn tích lũy nền tảng (> 6 tuần đến Race)
    PEAK_TRAINING = "PEAK_TRAINING"         # Giai đoạn tải cao (2 - 6 tuần đến Race)
    TAPERING = "TAPERING"                   # 14 ngày trước Race Day (Siết tải Tapering)
    RACE_DAY = "RACE_DAY"                   # Đúng ngày thi đấu (T-0)
    POST_RACE_ACUTE = "POST_RACE_ACUTE"     # D+1 đến D+7 sau race HM/FM (Hồi phục cấp, chống tiêu cơ vân nhẹ, sửa chữa gân, cấm chạy hoàn toàn)
    POST_RACE_RECOVERY = "POST_RACE_RECOVERY" # D+8 đến D+14 (Reverse Taper) / D+21 sau race (Hồi phục & cho phép Shakeout Run có điều kiện)
    MAINTENANCE = "MAINTENANCE"             # Duy trì thông thường (Không có giải gần)


def detect_current_phase(
    current_date: Union[str, date],
    target_race_date: Optional[Union[str, date]] = None,
    race_completed: bool = False,
    config_path: Optional[Path] = None
) -> TrainingPhase:
    """
    Deterministic State Machine for Periodization Phase Detection.
    Determines training phase based on target race date or recent completed races.
    """
    if isinstance(current_date, str):
        curr_dt = datetime.strptime(current_date, "%Y-%m-%d").date()
    elif isinstance(current_date, datetime):
        curr_dt = current_date.date()
    else:
        curr_dt = current_date

    # 1. Direct explicit target_race_date override
    if target_race_date:
        if isinstance(target_race_date, str):
            r_dt = datetime.strptime(target_race_date, "%Y-%m-%d").date()
        elif isinstance(target_race_date, datetime):
            r_dt = target_race_date.date()
        else:
            r_dt = target_race_date

        delta = (curr_dt - r_dt).days
        if delta == 0:
            return TrainingPhase.RACE_DAY
        elif delta > 0 or race_completed:
            days_since = abs(delta)
            if 1 <= days_since <= 7:
                return TrainingPhase.POST_RACE_ACUTE
            elif 8 <= days_since <= 21:
                return TrainingPhase.POST_RACE_RECOVERY
            else:
                return TrainingPhase.MAINTENANCE
        else:
            days_to = abs(delta)
            if 1 <= days_to <= 14:
                return TrainingPhase.TAPERING
            elif 15 <= days_to <= 42:
                return TrainingPhase.PEAK_TRAINING
            else:
                return TrainingPhase.BASE_BUILDING

    # 2. Config-driven detection from config/races.json
    path = Path(config_path) if config_path else BASE_DIR / "config" / "races.json"
    if not path.exists():
        return TrainingPhase.MAINTENANCE

    try:
        with open(path, "r", encoding="utf-8") as f:
            races = json.load(f)
        if not isinstance(races, list):
            return TrainingPhase.MAINTENANCE

        priority_order = {"A": 1, "B": 2, "C": 3}
        recent_completed = []
        upcoming_races = []

        for race in races:
            if not isinstance(race, dict) or not race.get("date"):
                continue
            try:
                r_date = datetime.strptime(race["date"], "%Y-%m-%d").date()
                delta_days = (r_date - curr_dt).days
                p_val = priority_order.get(str(race.get("priority")).upper(), 99)
                r_entry = {
                    "name": race.get("name") or "Race",
                    "date": race["date"],
                    "distance": race.get("distance") or "FM",
                    "delta_days": delta_days,
                    "priority_val": p_val
                }
                if delta_days == 0:
                    return TrainingPhase.RACE_DAY
                elif delta_days < 0:
                    days_since = abs(delta_days)
                    if days_since <= 21:
                        recent_completed.append({**r_entry, "days_since": days_since})
                else:
                    upcoming_races.append({**r_entry, "days_to": delta_days})
            except Exception:
                continue

        # Priority 1: Recent completed races (D+1 to D+21)
        if recent_completed:
            recent_completed.sort(key=lambda x: (x["days_since"], x["priority_val"]))
            days_since = recent_completed[0]["days_since"]
            if 1 <= days_since <= 7:
                return TrainingPhase.POST_RACE_ACUTE
            elif 8 <= days_since <= 21:
                return TrainingPhase.POST_RACE_RECOVERY

        # Priority 2: Upcoming races
        if upcoming_races:
            upcoming_races.sort(key=lambda x: (x["days_to"], x["priority_val"]))
            days_to = upcoming_races[0]["days_to"]
            if 1 <= days_to <= 14:
                return TrainingPhase.TAPERING
            elif 15 <= days_to <= 42:
                return TrainingPhase.PEAK_TRAINING
            else:
                return TrainingPhase.BASE_BUILDING

    except Exception:
        pass

    return TrainingPhase.MAINTENANCE


def is_taper_strict_mode(phase: TrainingPhase) -> bool:
    """Strictly disable Tapering rules outside TAPERING phase."""
    return phase == TrainingPhase.TAPERING


def get_phase_display_name(
    phase: TrainingPhase,
    days_since_race: Optional[int] = None,
    days_to_race: Optional[int] = None
) -> str:
    """Returns human-readable Vietnamese periodization display title."""
    if phase == TrainingPhase.POST_RACE_ACUTE:
        d_str = f"D+{days_since_race}" if days_since_race is not None else "ACUTE"
        return f"HỒI PHỤC CẤP (POST-RACE {d_str})"
    elif phase == TrainingPhase.POST_RACE_RECOVERY:
        d_str = f"D+{days_since_race}" if days_since_race is not None else "RECOVERY"
        return f"PHỤC HỒI SAU RACE (POST-RACE {d_str})"
    elif phase == TrainingPhase.TAPERING:
        d_str = f"T-{days_to_race}" if days_to_race is not None else "TAPER"
        return f"SIẾT TẢI TAPERING ({d_str})"
    elif phase == TrainingPhase.RACE_DAY:
        return "NGÀY THI ĐẤU (RACE DAY T-0)"
    elif phase == TrainingPhase.PEAK_TRAINING:
        return "GIAI ĐOẠN TẢI CAO (PEAK TRAINING)"
    elif phase == TrainingPhase.BASE_BUILDING:
        return "TÍCH LŨY NỀN TẢNG (BASE BUILDING)"
    else:
        return "DUY TRÌ THÔNG THƯỜNG (MAINTENANCE)"


def is_post_race_shakeout_eligible(
    training_readiness: Optional[Union[int, float]] = None,
    recovery_time_hours: Optional[Union[int, float]] = None,
    hrv_status: Optional[str] = None,
    sleep_duration_seconds: Optional[Union[int, float]] = None,
    deep_sleep_pct: Optional[Union[int, float]] = None,
    rem_sleep_pct: Optional[Union[int, float]] = None,
    subjective_fatigue: Optional[Union[str, bool]] = None,
    gct_balance: Optional[Union[str, float]] = None
) -> bool:
    """
    Xác định điều kiện để mở cửa chạy thử (Shakeout Run / Progressive Run) trong giai đoạn POST_RACE_RECOVERY:
    - training_readiness >= 65
    - recovery_time_hours <= 6
    - hrv_status == "BALANCED"
    - sleep_duration_seconds >= 18000 (>= 5.0 giờ) - KHÓA CỨNG AN TOÀN NẾU THIẾU NGỦ CẤP TÍNH (< 5 tiếng)
    - deep_sleep_pct >= 10.0 (nếu có dữ liệu) - Phục hồi thể chất & thần kinh cơ sâu
    - rem_sleep_pct >= 15.0 (nếu có dữ liệu) - Phục hồi thần kinh nhận thức
    - subjective_fatigue is None / False
    - GCT Balance <= 51.0% Chân Trái
    """
    if training_readiness is None or recovery_time_hours is None or hrv_status is None:
        return False
    try:
        from src.analytics.training_prescriber import evaluate_run_readiness, has_gct_balance_issue
        gct_issue, _ = has_gct_balance_issue(gct_balance)
        status, _ = evaluate_run_readiness(
            readiness_score=training_readiness,
            recovery_time_hours=recovery_time_hours,
            deep_sleep_pct=deep_sleep_pct,
            rem_sleep_pct=rem_sleep_pct,
            sleep_duration_seconds=sleep_duration_seconds,
            hrv_status=hrv_status,
            gct_balance_issue=gct_issue,
            subjective_fatigue=subjective_fatigue
        )
        return status == "GO_RUN"
    except Exception:
        # Fallback to base checks
        try:
            if sleep_duration_seconds is not None and float(sleep_duration_seconds) < 18000:
                return False
            readiness_ok = float(training_readiness) >= 65
            recovery_ok = float(recovery_time_hours) <= 6
            hrv_ok = str(hrv_status).strip().upper() == "BALANCED"
            deep_ok = (deep_sleep_pct is None) or float(deep_sleep_pct) >= 10.0
            rem_ok = (rem_sleep_pct is None) or float(rem_sleep_pct) >= 15.0
            return readiness_ok and recovery_ok and hrv_ok and deep_ok and rem_ok
        except (ValueError, TypeError):
            return False
