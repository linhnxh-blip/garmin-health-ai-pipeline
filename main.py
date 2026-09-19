import sys
from pathlib import Path
from datetime import datetime
import click

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure root project directory is in python path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.db.connection import init_db, get_db_connection
from src.importers.zip_importer import import_garmin_export
from src.ingestion.collector import fetch_and_store_daily_data, backfill_historical_data
from src.analytics.baseline import calculate_baseline
from src.analytics.llm_analyst import generate_health_analysis
from src.analytics.report_manager import save_report_to_db, export_report_to_file
from src.ingestion.browser_session_client import fetch_and_store_daily_data_browser
from src.ingestion.garmin_client import get_garmin_client

@click.group()
def cli():
    """Garmin Health AI Pipeline CLI Tool"""
    pass

@cli.command("log-weight")
@click.argument("weight_kg", type=float)
@click.option("--fat", type=float, default=None, help="Body fat percentage (%)")
@click.option("--muscle", type=float, default=None, help="Muscle mass percentage (%) or kg")
@click.option("--visceral", type=int, default=None, help="Visceral fat rating (1-30)")
@click.option("--date", "target_date", default=None, help="Target date in YYYY-MM-DD format (default: today)")
def log_weight(weight_kg, fat, muscle, visceral, target_date):
    """Log body weight & body composition metrics (from OMRON VIVA scale or manual input) and sync to Garmin Connect."""
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"⚖️ Logging body weight ({weight_kg} kg) for date: {date_str}...")

    # Ensure database schema & migrations are initialized
    init_db()

    # 1. Update SQLite database (daily_metrics table)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO daily_metrics (date, weight_kg, body_fat_pct, muscle_mass_pct, visceral_fat, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(date) DO UPDATE SET
                weight_kg = excluded.weight_kg,
                body_fat_pct = COALESCE(excluded.body_fat_pct, daily_metrics.body_fat_pct),
                muscle_mass_pct = COALESCE(excluded.muscle_mass_pct, daily_metrics.muscle_mass_pct),
                visceral_fat = COALESCE(excluded.visceral_fat, daily_metrics.visceral_fat),
                updated_at = CURRENT_TIMESTAMP
            """,
            (date_str, weight_kg, fat, muscle, visceral)
        )
        conn.commit()
    click.echo(f"✅ Saved body composition to SQLite database (`daily_metrics`): Weight={weight_kg}kg, Fat={fat}%, Muscle={muscle}%, VisceralFat={visceral}")

    # 2. Sync to Garmin Connect if session is available
    try:
        client = get_garmin_client()
        iso_timestamp = f"{date_str}T08:00:00.000Z"
        client.add_body_composition(
            timestamp=iso_timestamp,
            weight=weight_kg,
            percent_fat=fat,
            muscle_mass=muscle,
            visceral_fat_rating=visceral
        )
        click.echo(f"✅ Successfully synced weight ({weight_kg} kg) to Garmin Connect!")
    except Exception as exc:
        click.echo(f"ℹ️ Weight recorded locally in SQLite database. (Garmin Connect sync notice: {exc})")

@cli.command()
@click.option('--days', default=30, type=int, help='Number of historical days to backfill from yesterday (default: 30)')
@click.option('--start-date', default=None, help='Start date in YYYY-MM-DD format')
@click.option('--end-date', default=None, help='End date in YYYY-MM-DD format')
@click.option('--force', is_flag=True, help='Force re-fetch and overwrite existing dates in database')
def backfill(days, start_date, end_date, force):
    """Backfill historical health data for N days from Garmin Connect API into SQLite."""
    click.echo(f"🔄 Initializing backfill sequence...")
    res = backfill_historical_data(
        days=days,
        start_date=start_date,
        end_date=end_date,
        force=force
    )
    click.echo(f"\n🎉 Backfill Complete!")
    click.echo(f"   - Total dates in range: {res['total_dates']}")
    click.echo(f"   - Newly synced: {res['synced']}")
    click.echo(f"   - Skipped (already in DB): {res['skipped']}")
    click.echo(f"   - Errors: {res['errors']}")

@cli.command()
def init():
    """Initialize SQLite database tables."""
    db_p = init_db()
    click.echo(f"✅ Database initialized successfully at: {db_p}")

@cli.command()
@click.argument('path', type=click.Path(exists=True))
def import_zip(path):
    """Import historical Garmin data from a export .ZIP file or unzipped directory."""
    click.echo(f"🔍 Parsing Garmin export data from: {path}...")
    res = import_garmin_export(path)
    click.echo(f"🎉 Import Complete!")
    click.echo(f"   - Total dates processed: {res['dates_processed']}")
    click.echo(f"   - Raw records saved: {res['raw_records_inserted']}")
    click.echo(f"   - Database path: {res['db_path']}")

@cli.command()
def sync_today():
    """Sync live Garmin health data for today from Garmin Connect API."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🔄 Syncing Garmin health data for today ({today_str})...")
    res = fetch_and_store_daily_data(today_str)
    click.echo(f"✅ Sync complete for {res.date}!")
    click.echo(f"   - Sleep Score: {res.sleep_score}")
    click.echo(f"   - HRV Overnight Avg: {res.hrv_last_night}")
    click.echo(f"   - Resting HR: {res.resting_heart_rate} bpm")
    click.echo(f"   - Avg Stress: {res.avg_stress_level}")
    click.echo(f"   - Total Steps: {res.total_steps}")

@cli.command()
@click.option('--date', required=True, help='Target date in YYYY-MM-DD format')
def sync_date(date):
    """Sync live Garmin health data for a specific date (YYYY-MM-DD) from Garmin Connect API."""
    click.echo(f"🔄 Syncing Garmin health data for date: {date}...")
    res = fetch_and_store_daily_data(date)
    click.echo(f"✅ Sync complete for {res.date}!")
    click.echo(f"   - Sleep Score: {res.sleep_score}")
    click.echo(f"   - HRV Overnight Avg: {res.hrv_last_night}")
    click.echo(f"   - Resting HR: {res.resting_heart_rate} bpm")
    click.echo(f"   - Avg Stress: {res.avg_stress_level}")
    click.echo(f"   - Total Steps: {res.total_steps}")

@cli.command()
def status():
    """Check current database status and record counts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM daily_metrics")
        daily_count, min_date, max_date = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) FROM raw_garmin_data")
        raw_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ai_reports")
        report_count = cursor.fetchone()[0]

    click.echo("📊 Garmin Health Database Status:")
    click.echo(f"   - Daily Metrics Records: {daily_count} (Date Range: {min_date or 'N/A'} to {max_date or 'N/A'})")
    click.echo(f"   - Raw JSON Records: {raw_count}")
    click.echo(f"   - AI Reports Stored: {report_count}")

@cli.command()
@click.option('--date', default=None, help='Target date in YYYY-MM-DD format (default: today)')
@click.option('--dry-run', is_flag=True, help='Print generated prompt without calling LLM API')
@click.option('--force', is_flag=True, help='Force re-generation of AI analysis report')
def analyze(date, dry_run, force):
    """Run 30-day baseline physiology analysis & LLM report generation for a target date."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🧠 Running Garmin Health AI Analysis for date: {target_date}...")

    # 1. Compute baseline & fetch target date metrics
    baseline_data = calculate_baseline(target_date, days=30)
    sample_size = baseline_data["sample_size_days"]
    click.echo(f"📊 Baseline computed using {sample_size} historical days.")

    # 2. Generate report using LLM Analyst (or dry run)
    res = generate_health_analysis(baseline_data, dry_run=dry_run)

    if dry_run:
        click.echo("\n--- DRY RUN PROMPT PREVIEW ---")
        click.echo(res["raw_prompt"])
        click.echo("------------------------------\n")
        click.echo("💡 Dry run complete. No API tokens were used.")
        return

    # 3. Save report to DB & File
    save_report_to_db(
        date=target_date,
        report_markdown=res["report_markdown"],
        raw_prompt=res["raw_prompt"],
        model_used=res["model_used"],
        status="SUCCESS",
        prompt_tokens=res.get("prompt_tokens", 0),
        completion_tokens=res.get("completion_tokens", 0)
    )

    exported_path = export_report_to_file(target_date, res["report_markdown"])

    click.echo(f"✅ AI Analysis completed successfully using {res['model_used']}!")
    click.echo(f"   - Tokens used: {res.get('prompt_tokens', 0)} prompt / {res.get('completion_tokens', 0)} completion")
    click.echo(f"   - Saved report to SQLite database (ai_reports table)")
    click.echo(f"   - Exported Markdown report to: {exported_path}")
    click.echo("\n--- HEALTH JOURNAL PREVIEW ---")
    click.echo(res["report_markdown"])

@cli.command()
@click.option('--date', default=None, help='Target date in YYYY-MM-DD format (default: today)')
@click.option('--curl', default="", help='cURL command string extracted from browser Network tab')
@click.option('--cookie', default="", help='Raw Cookie header string')
def sync_browser(date, curl, cookie):
    """Sync Garmin health data using Browser Session Cookie (bypasses 429 mobile login)."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    raw_input = curl or cookie
    click.echo(f"🔄 Syncing Garmin health data for {target_date} via Browser Session Adapter...")

    try:
        res = fetch_and_store_daily_data_browser(target_date, raw_curl_or_cookie=raw_input)
        click.echo(f"✅ Browser Sync complete for {res.date}!")
        click.echo(f"   - Sleep Score: {res.sleep_score}")
        click.echo(f"   - HRV Overnight Avg: {res.hrv_last_night}")
        click.echo(f"   - Resting HR: {res.resting_heart_rate} bpm")
        click.echo(f"   - Avg Stress: {res.avg_stress_level}")
        click.echo(f"   - Total Steps: {res.total_steps}")
    except Exception as e:
        click.echo(f"❌ Browser sync failed: {e}", err=True)

@cli.command("import-apple-health")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--sync-garmin/--no-sync-garmin", default=True, help="Sync latest weight to Garmin Connect cloud (default: True)")
def import_apple_health(file_path, sync_garmin):
    """Import weight, body fat & health metrics from Apple Health export file (export.zip or export.xml)."""
    from src.importers.apple_health_importer import import_apple_health_export
    click.echo(f"🍎 Importing Apple Health data from: {file_path}...")
    try:
        res = import_apple_health_export(file_path, sync_to_garmin=sync_garmin)
        click.echo(f"✅ Apple Health Import Complete: {res['processed_days']} days updated into SQLite.")
        if res.get("latest_weight"):
            click.echo(f"   - Latest Weight Recorded: {res['latest_weight']} kg ({res.get('latest_date')})")
    except Exception as e:
        click.echo(f"❌ Apple Health import failed: {e}", err=True)

@cli.command("sync-google-health")
@click.option("--date", "target_date", default=None, help="Target date in YYYY-MM-DD format (default: today)")
def sync_google_health(target_date):
    """Sync Weight & Body Fat metrics from Google Fitness REST API into SQLite DB."""
    from src.ingestion.google_health_client import fetch_and_store_google_health_data
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🔄 Syncing Google Health (Fit API) data for date: {date_str}...")
    res = fetch_and_store_google_health_data(date_str, verbose=True)
    if res is None:
        click.echo("ℹ️ Google Health sync was skipped. (Make sure credentials.json exists and is configured).")
    elif not res:
        click.echo(f"ℹ️ No weight or body fat data points returned from Google Fit for {date_str}.")
    else:
        click.echo(f"🎉 Sync Complete! Weight: {res.get('weight_kg', 'N/A')} kg, Body Fat: {res.get('body_fat_pct', 'N/A')}%")

if __name__ == "__main__":
    cli()

