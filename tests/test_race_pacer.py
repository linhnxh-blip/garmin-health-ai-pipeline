import pytest
from src.delivery.race_pacer import RaceNutritionPacer, DEFAULT_RACE_TIMELINE

def test_race_pacer_timeline_count_and_offsets():
    pacer = RaceNutritionPacer()
    timeline = pacer.get_timeline("04:00")

    assert len(timeline) == 11
    assert timeline[0]["scheduled_time"] == "01:45"
    assert timeline[1]["scheduled_time"] == "03:45"
    assert timeline[2]["scheduled_time"] == "04:50"
    assert timeline[3]["scheduled_time"] == "05:25"
    assert timeline[5]["scheduled_time"] == "06:45"
    assert timeline[7]["scheduled_time"] == "08:05"
    assert timeline[10]["scheduled_time"] == "09:25"

def test_race_pacer_custom_start_time():
    pacer = RaceNutritionPacer()
    timeline = pacer.get_timeline("05:00")

    assert len(timeline) == 11
    assert timeline[0]["scheduled_time"] == "02:45"
    assert timeline[1]["scheduled_time"] == "04:45"
    assert timeline[2]["scheduled_time"] == "05:50"
    assert timeline[10]["scheduled_time"] == "10:25"

def test_race_pacer_format_alert_message():
    pacer = RaceNutritionPacer()
    timeline = pacer.get_timeline("04:00")
    first_item = timeline[0]

    msg = pacer.format_alert_message(first_item, "04:00")
    assert "01:45" in msg
    assert "Nhắc nhở #1/11" in msg
    assert "Bữa sáng tinh bột sạch" in msg
    assert "3 lát bánh mì gối trắng" in msg
    assert "Uric Acid 442 µmol/L" in msg
    assert "Achilles GCT 50.3% L" in msg

def test_race_pacer_dry_run_executes_cleanly(capsys):
    pacer = RaceNutritionPacer()
    pacer.run_dry_run("04:00")

    captured = capsys.readouterr().out
    assert "TIMELINE NHẮC DINH DƯỠNG & CƠ SINH HỌC FULL MARATHON" in captured
    assert "[01:45]" in captured
    assert "[09:25]" in captured
    assert "Dry-run complete" in captured
