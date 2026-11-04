"""
Unit tests for Periodization State Machine (src/analytics/periodization.py).
"""

import json
import pytest
from datetime import date
from src.analytics.periodization import (
    TrainingPhase,
    detect_current_phase,
    is_taper_strict_mode,
    get_phase_display_name,
    is_post_race_shakeout_eligible
)


@pytest.fixture
def mock_race_config(tmp_path):
    race_file = tmp_path / "races.json"
    data = [
        {
            "name": "Hanoi Full Marathon",
            "date": "2026-10-04",
            "distance": "42.195km",
            "type": "running",
            "priority": "A"
        }
    ]
    with open(race_file, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return race_file


def test_post_race_acute_phase_detection(mock_race_config):
    # Target dates from 2026-10-05 to 2026-10-11 (D+1 to D+7 post Hanoi FM 2026-10-04)
    for day in range(5, 12):
        d_str = f"2026-10-{day:02d}"
        phase = detect_current_phase(d_str, config_path=mock_race_config)
        assert phase == TrainingPhase.POST_RACE_ACUTE, f"Failed for date {d_str}"
        assert is_taper_strict_mode(phase) is False


def test_post_race_recovery_phase_detection(mock_race_config):
    # Target dates from 2026-10-12 to 2026-10-25 (D+8 to D+21 post Hanoi FM 2026-10-04)
    for day in range(12, 26):
        d_str = f"2026-10-{day:02d}"
        phase = detect_current_phase(d_str, config_path=mock_race_config)
        assert phase == TrainingPhase.POST_RACE_RECOVERY, f"Failed for date {d_str}"
        assert is_taper_strict_mode(phase) is False


def test_tapering_phase_detection(mock_race_config):
    # Target date 2026-09-25 (9 days before 2026-10-04)
    phase = detect_current_phase("2026-09-25", config_path=mock_race_config)
    assert phase == TrainingPhase.TAPERING
    assert is_taper_strict_mode(phase) is True


def test_peak_training_phase_detection(mock_race_config):
    # Target date 2026-09-01 (33 days before 2026-10-04)
    phase = detect_current_phase("2026-09-01", config_path=mock_race_config)
    assert phase == TrainingPhase.PEAK_TRAINING


def test_race_day_detection(mock_race_config):
    # Target date 2026-10-04
    phase = detect_current_phase("2026-10-04", config_path=mock_race_config)
    assert phase == TrainingPhase.RACE_DAY


def test_get_phase_display_name():
    assert "HỒI PHỤC CẤP (POST-RACE D+3)" in get_phase_display_name(TrainingPhase.POST_RACE_ACUTE, days_since_race=3)
    assert "PHỤC HỒI SAU RACE (POST-RACE D+10)" in get_phase_display_name(TrainingPhase.POST_RACE_RECOVERY, days_since_race=10)
    assert "SIẾT TẢI TAPERING (T-5)" in get_phase_display_name(TrainingPhase.TAPERING, days_to_race=5)


def test_is_post_race_shakeout_eligible():
    # Eligible: Readiness >= 65, Recovery <= 6h, HRV == BALANCED
    assert is_post_race_shakeout_eligible(65, 6, "BALANCED") is True
    assert is_post_race_shakeout_eligible(75, 2, "BALANCED") is True
    assert is_post_race_shakeout_eligible(90, 0, "balanced") is True

    # Not eligible: Readiness < 65
    assert is_post_race_shakeout_eligible(64, 4, "BALANCED") is False
    assert is_post_race_shakeout_eligible(45, 0, "BALANCED") is False

    # Not eligible: Recovery Time > 6h
    assert is_post_race_shakeout_eligible(70, 7, "BALANCED") is False
    assert is_post_race_shakeout_eligible(80, 12, "BALANCED") is False

    # Not eligible: HRV not BALANCED
    assert is_post_race_shakeout_eligible(70, 4, "UNBALANCED") is False
    assert is_post_race_shakeout_eligible(70, 4, "LOW") is False
    assert is_post_race_shakeout_eligible(70, 4, "POOR") is False

    assert is_post_race_shakeout_eligible(None, 4, "BALANCED") is False
    assert is_post_race_shakeout_eligible(70, None, "BALANCED") is False
    assert is_post_race_shakeout_eligible(70, 4, None) is False


def test_detect_current_phase_d9_recovery(mock_race_config):
    """Verify that when current date is D+9 (2026-10-13, 9 days after 2026-10-04 Hanoi FM),
    detect_current_phase MUST return TrainingPhase.POST_RACE_RECOVERY.
    """
    # 1. Config-driven detection
    phase_config = detect_current_phase("2026-10-13", config_path=mock_race_config)
    assert phase_config == TrainingPhase.POST_RACE_RECOVERY

    # 2. Target race date direct parameter
    phase_param = detect_current_phase("2026-10-13", target_race_date="2026-10-04")
    assert phase_param == TrainingPhase.POST_RACE_RECOVERY

