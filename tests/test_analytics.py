import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from click.testing import CliRunner

from src.db.connection import init_db, get_db_connection
from src.db.models import DailyMetrics
from src.db.schema import UPSERT_DAILY_METRICS_SQL
from src.analytics.baseline import calculate_baseline
from src.analytics.llm_analyst import build_user_prompt, generate_health_analysis
from src.analytics.report_manager import save_report_to_db, export_report_to_file, get_report_from_db
from main import cli

@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_p = tmp_path / "test_garmin.db"
    init_db(db_p)
    return db_p

def populate_mock_daily_metrics(db_path: Path, start_date_str: str, num_days: int):
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        for i in range(num_days):
            current_date = (start_dt + timedelta(days=i)).strftime("%Y-%m-%d")
            acts = None
            if i % 2 == 0:
                acts = json.dumps([{
                    "name": "Running",
                    "type": "running",
                    "duration_seconds": 1800,
                    "distance_meters": 5000,
                    "calories": 350,
                    "avg_hr": 145,
                    "max_hr": 165,
                    "aerobic_training_effect": 3.2
                }])

            metric = DailyMetrics(
                date=current_date,
                sleep_score=75 + (i % 10),
                sleep_duration_seconds=25200 + (i * 300),
                deep_sleep_seconds=5400,
                rem_sleep_seconds=5400,
                light_sleep_seconds=14400,
                hrv_weekly_avg=60.0,
                hrv_last_night=55.0 + (i % 5),
                hrv_status="BALANCED",
                resting_heart_rate=58 - (i % 3),
                avg_stress_level=25 + (i % 5),
                max_stress_level=70,
                body_battery_charged=80,
                body_battery_drained=75,
                body_battery_highest=95,
                body_battery_lowest=20,
                active_calories=400 + (i * 10),
                total_steps=8000 + (i * 100),
                vo2_max=48.5,
                activities_summary=acts
            )
            cursor.execute(UPSERT_DAILY_METRICS_SQL, metric.to_db_tuple())
        conn.commit()

def test_calculate_baseline_full_data(temp_db: Path):
    populate_mock_daily_metrics(temp_db, "2026-08-01", 35)
    target_date = "2026-09-01"

    res = calculate_baseline(target_date=target_date, days=30, db_path=temp_db)

    assert res["target_date"] == target_date
    assert res["sample_size_days"] == 31
    assert res["date_range"]["start"] == "2026-08-01"
    assert res["date_range"]["end"] == "2026-08-31"

    # Metrics baseline checks
    bs = res["metrics_baseline"]
    assert bs["sleep_score"]["sample_count"] == 31
    assert bs["sleep_score"]["avg"] is not None
    assert bs["hrv_last_night"]["sample_count"] == 31
    assert bs["resting_heart_rate"]["sample_count"] == 31

    # 7-day training load checks
    tl = res["training_load_7d"]
    assert tl["total_active_calories"] > 0
    assert tl["total_steps"] > 0
    assert tl["total_workout_count"] > 0

def test_calculate_baseline_partial_data(temp_db: Path):
    populate_mock_daily_metrics(temp_db, "2026-08-25", 5)
    target_date = "2026-08-30"

    res = calculate_baseline(target_date=target_date, days=30, db_path=temp_db)

    assert res["sample_size_days"] == 5
    assert res["metrics_baseline"]["sleep_score"]["sample_count"] == 5

def test_calculate_baseline_with_missing_null_metrics(temp_db: Path):
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        m1 = DailyMetrics(date="2026-09-01", sleep_score=80, hrv_last_night=None, resting_heart_rate=60)
        m2 = DailyMetrics(date="2026-09-02", sleep_score=None, hrv_last_night=50.0, resting_heart_rate=62)
        cursor.execute(UPSERT_DAILY_METRICS_SQL, m1.to_db_tuple())
        cursor.execute(UPSERT_DAILY_METRICS_SQL, m2.to_db_tuple())
        conn.commit()

    res = calculate_baseline("2026-09-03", days=30, db_path=temp_db)
    assert res["sample_size_days"] == 2
    assert res["metrics_baseline"]["sleep_score"]["sample_count"] == 1
    assert res["metrics_baseline"]["sleep_score"]["avg"] == 80.0
    assert res["metrics_baseline"]["hrv_last_night"]["sample_count"] == 1
    assert res["metrics_baseline"]["hrv_last_night"]["avg"] == 50.0

def test_build_user_prompt(temp_db: Path):
    populate_mock_daily_metrics(temp_db, "2026-08-01", 10)
    baseline_data = calculate_baseline("2026-08-11", days=30, db_path=temp_db)
    
    prompt = build_user_prompt(baseline_data)
    
    assert "DỮ LIỆU SINH LÝ HỌC NGÀY: 2026-08-11" in prompt
    assert "Sleep Score" in prompt
    assert "HRV Overnight" in prompt
    assert "Resting Heart Rate" in prompt
    assert "TỔNG TẢI VẬN ĐỘNG 7 NGÀY GẦN NHẤT" in prompt

def test_generate_health_analysis_dry_run(temp_db: Path):
    populate_mock_daily_metrics(temp_db, "2026-08-01", 5)
    baseline_data = calculate_baseline("2026-08-06", days=30, db_path=temp_db)

    res = generate_health_analysis(baseline_data, dry_run=True)

    assert res["model_used"] == "dry-run"
    assert "DRY RUN MODE" in res["report_markdown"]
    assert res["prompt_tokens"] == 0
    assert res["completion_tokens"] == 0

@patch("src.analytics.llm_analyst.call_gemini")
def test_generate_health_analysis_mocked_gemini(mock_call, temp_db: Path):
    mock_call.return_value = {
        "report_markdown": "# 🩺 Test Report\n\n- State: Recovered",
        "model_used": "gemini (gemini-2.5-flash)",
        "prompt_tokens": 120,
        "completion_tokens": 85
    }

    populate_mock_daily_metrics(temp_db, "2026-08-01", 5)
    baseline_data = calculate_baseline("2026-08-06", days=30, db_path=temp_db)

    with patch("config.settings.settings.llm_provider", "gemini"):
        res = generate_health_analysis(baseline_data, dry_run=False)

    assert res["model_used"] == "gemini (gemini-2.5-flash)"
    assert res["prompt_tokens"] == 120
    assert res["completion_tokens"] == 85
    assert "# 🩺 Test Report" in res["report_markdown"]

def test_report_manager_save_and_export(temp_db: Path, tmp_path: Path):
    report_markdown = "# 🩺 Daily Journal Test\n\nEverything optimal."
    date_str = "2026-09-18"

    # Test DB save
    saved_model = save_report_to_db(
        date=date_str,
        report_markdown=report_markdown,
        raw_prompt="[RAW PROMPT]",
        model_used="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        db_path=temp_db
    )

    assert saved_model.date == date_str
    assert saved_model.model_used == "test-model"

    # Verify retrieval from DB
    fetched = get_report_from_db(date_str, db_path=temp_db)
    assert fetched is not None
    assert fetched.report_markdown == report_markdown
    assert fetched.prompt_tokens == 100

    # Test file export
    export_dir = tmp_path / "reports"
    file_p = export_report_to_file(date_str, report_markdown, output_dir=export_dir)
    
    assert file_p.exists()
    assert file_p.name == f"{date_str}_health_journal.md"
    content = file_p.read_text(encoding="utf-8")
    assert content == report_markdown

def test_cli_analyze_dry_run(temp_db: Path):
    populate_mock_daily_metrics(temp_db, "2026-08-01", 10)
    runner = CliRunner()
    
    result = runner.invoke(cli, ["analyze", "--date", "2026-08-11", "--dry-run"])
    assert result.exit_code == 0
    assert "Running Garmin Health AI Analysis" in result.output
    assert "DRY RUN PROMPT PREVIEW" in result.output

def test_cli_analyze_with_send_telegram():
    runner = CliRunner()
    with patch("main.calculate_baseline") as mock_base, \
         patch("main.generate_health_analysis") as mock_gen, \
         patch("main.save_report_to_db"), \
         patch("main.export_report_to_file", return_value=Path("data/reports/2026-09-19_health_journal.md")), \
         patch("src.delivery.telegram_bot.send_telegram_report", return_value=True) as mock_send:

        mock_base.return_value = {"sample_size_days": 30}
        mock_gen.return_value = {
            "report_markdown": "# 🩺 Report Test",
            "raw_prompt": "prompt",
            "model_used": "gemini-2.5-flash",
            "prompt_tokens": 10,
            "completion_tokens": 20
        }

        result = runner.invoke(cli, ["analyze", "--date", "2026-09-19", "--send-telegram"])
        assert result.exit_code == 0
        assert "Dispatching AI analysis report to Telegram" in result.output
        assert "delivered to Telegram" in result.output
        mock_send.assert_called_once()

def test_cli_send_report_command(tmp_path: Path):
    runner = CliRunner()
    report_file = tmp_path / "2026-09-19_health_journal.md"
    report_file.write_text("# 🩺 Test Report Content", encoding="utf-8")

    with patch("main.BASE_DIR", tmp_path.parent), \
         patch("src.delivery.telegram_bot.send_telegram_report", return_value=True) as mock_send:

        # Mock BASE_DIR / "data" / "reports"
        reports_dir = tmp_path.parent / "data" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "2026-09-19_health_journal.md").write_text("# 🩺 Test Report Content", encoding="utf-8")

        result = runner.invoke(cli, ["send-report", "--date", "2026-09-19"])
        assert result.exit_code == 0
        assert "Preparing to send AI report" in result.output
        assert "delivered to Telegram" in result.output
        mock_send.assert_called_once()

