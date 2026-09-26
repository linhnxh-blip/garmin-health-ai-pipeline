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

    # Determine muscle_mass_pct (for SQLite) and muscle_mass_kg (for Garmin Connect API)
    muscle_pct = None
    muscle_kg_for_garmin = None

    if muscle is not None:
        m_val = float(muscle)
        if m_val > 30.0:  # User provided muscle percentage directly (e.g. 36.5%)
            muscle_pct = round(m_val, 1)
            muscle_kg_for_garmin = round((m_val / 100.0) * weight_kg, 2)
        else:  # User provided muscle mass in kg (e.g. 23.4 kg)
            muscle_kg_for_garmin = round(m_val, 2)
            if weight_kg > 0:
                muscle_pct = round((m_val / weight_kg) * 100.0, 1)

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
            (date_str, weight_kg, fat, muscle_pct, visceral)
        )
        conn.commit()
    click.echo(f"✅ Saved body composition to SQLite database (`daily_metrics`): Weight={weight_kg}kg, Fat={fat}%, Muscle={muscle_pct}%, VisceralFat={visceral}")

    # 2. Sync to Garmin Connect if session is available
    try:
        client = get_garmin_client()
        iso_timestamp = f"{date_str}T08:00:00.000Z"
        client.add_body_composition(
            timestamp=iso_timestamp,
            weight=weight_kg,
            percent_fat=fat,
            muscle_mass=muscle_kg_for_garmin,
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

@cli.command("process-garmin-zip")
@click.option("--zip-path", required=True, type=click.Path(exists=True), help="Path to Garmin Data Export zip file")
def process_garmin_zip(zip_path):
    """[Automated] In-memory extraction and ingestion of Garmin Data Export ZIP archive (Sleep, Wellness, FIT dynamics)."""
    from src.ingestion.garmin_zip_extractor import process_garmin_zip_archive
    click.echo(f"🔍 Starting automated in-memory extraction of Garmin Export ZIP: {zip_path}...")
    try:
        res = process_garmin_zip_archive(zip_path)
        click.echo("\n" + "=" * 65)
        click.echo("🎉 GARMIN ZIP EXTRACTION & INGESTION COMPLETE")
        click.echo("=" * 65)
        click.echo(f"  • Total Daily Metrics / Sleep Days Imported : {res.get('total_dates', 0)} days")
        click.echo(f"  • Running FIT Activities Decoded           : {res.get('fit_running_count', 0)} activities")
        click.echo(f"  • HRM-Pro Biomechanics FIT Files Decoded   : {res.get('hrm_pro_count', 0)} activities")
        click.echo(f"  • Recorded Date Range                      : {res.get('min_date', 'N/A')} to {res.get('max_date', 'N/A')}")
        click.echo("=" * 65)
    except Exception as exc:
        click.echo(f"❌ Error processing Garmin ZIP archive: {exc}", err=True)
        sys.exit(1)

@cli.command("analyze-achilles")
def analyze_achilles():
    """Analyze historical HRM-Pro GCT Balance biomechanics and Achilles tendon overload risk."""
    from src.analytics.analyze_achilles_risk import analyze_achilles_risk
    analyze_achilles_risk()

@cli.command("cleanup-duplicates")
def cleanup_duplicates():
    """Purge duplicate nutrition logs in SQLite database, keeping only the earliest entry per meal/dishes on each date."""
    from src.db.nutrition_repository import delete_duplicate_nutrition_logs
    click.echo("🧹 Purging duplicate nutrition logs from SQLite database...")
    count = delete_duplicate_nutrition_logs()
    click.echo(f"✅ Cleanup complete: {count} duplicate log entries purged.")

# ==============================================================================
# NHÓM 1: ĐỒNG BỘ DỮ LIỆU (SYNC-ONLY COMMANDS)
# ==============================================================================

@cli.command("sync-today")
def sync_today():
    """[Sync-only] Sync live Garmin & Omron health data for today without generating AI report."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🔄 Syncing Garmin health data for today ({today_str})...")
    res = fetch_and_store_daily_data(today_str)
    click.echo(f"✅ Sync complete for {res.date}!")
    click.echo(f"   - Sleep Score: {res.sleep_score}")
    click.echo(f"   - HRV Overnight Avg: {res.hrv_last_night}")
    click.echo(f"   - Resting HR: {res.resting_heart_rate} bpm")
    click.echo(f"   - Avg Stress: {res.avg_stress_level}")
    click.echo(f"   - Total Steps: {res.total_steps}")

@cli.command("sync-day")
@click.option('--date', default=None, help='Target date in YYYY-MM-DD format (default: today)')
def sync_day(date):
    """[Sync-only] Sync live Garmin & Omron health data for a specific date (YYYY-MM-DD)."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🔄 Syncing Garmin health data for date: {target_date}...")
    res = fetch_and_store_daily_data(target_date)
    click.echo(f"✅ Sync complete for {res.date}!")
    click.echo(f"   - Sleep Score: {res.sleep_score}")
    click.echo(f"   - HRV Overnight Avg: {res.hrv_last_night}")
    click.echo(f"   - Resting HR: {res.resting_heart_rate} bpm")
    click.echo(f"   - Avg Stress: {res.avg_stress_level}")
    click.echo(f"   - Total Steps: {res.total_steps}")

@cli.command("sync-date", hidden=True)
@click.option('--date', required=True, help='Target date in YYYY-MM-DD format')
def sync_date(date):
    """Alias for sync-day."""
    sync_day.callback(date)

@cli.command("sync-range")
@click.option('--days', default=30, type=int, help='Number of consecutive historical days to sync (default: 30)')
@click.option('--start-date', default=None, help='Start date in YYYY-MM-DD format')
@click.option('--end-date', default=None, help='End date in YYYY-MM-DD format')
@click.option('--force', is_flag=True, help='Force re-fetch and overwrite existing dates in database')
def sync_range(days, start_date, end_date, force):
    """[Sync-only] Backfill N consecutive days of Garmin data up to today to build 30-day baseline."""
    click.echo(f"🔄 Initializing sync sequence for {days} days...")
    res = backfill_historical_data(
        days=days,
        start_date=start_date,
        end_date=end_date,
        force=force
    )
    click.echo(f"\n🎉 Sync Range Complete!")
    click.echo(f"   - Total dates in range: {res['total_dates']}")
    click.echo(f"   - Newly synced: {res['synced']}")
    click.echo(f"   - Skipped (already in DB): {res['skipped']}")
    click.echo(f"   - Errors: {res['errors']}")


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
@click.option('--send-telegram', is_flag=True, help='Send generated report directly to Telegram after analysis')
def analyze(date, dry_run, force, send_telegram):
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

    if send_telegram:
        click.echo(f"\n📲 Dispatching AI analysis report to Telegram...")
        from src.delivery.telegram_bot import send_telegram_report
        ok = send_telegram_report(res["report_markdown"])
        if ok:
            click.echo("🎉 Report successfully delivered to Telegram in 4 Message Cards!")
        else:
            click.echo("⚠️ Failed to send report to Telegram. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID settings.")


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

@cli.command("bot")
@click.option("--once", is_flag=True, help="Run single update poll and exit")
def run_bot(once):
    """Run Telegram Bot listener to process photo messages of meal/pub food."""
    from src.delivery.telegram_bot import TelegramMealBot
    try:
        bot = TelegramMealBot()
        bot.poll_updates(once=once)
    except Exception as exc:
        click.echo(f"❌ Failed to start Telegram Bot: {exc}", err=True)

@cli.command("analyze-image")
@click.argument("image_path", type=click.Path(exists=True))
@click.option("--caption", default=None, help="Optional text caption for the meal image")
def analyze_image(image_path, caption):
    """Analyze a local meal photo directly via Gemini Vision and save to SQLite."""
    from src.delivery.telegram_bot import process_single_image_file
    click.echo(f"📸 Analyzing meal image: {image_path}...")
    try:
        res = process_single_image_file(image_path, caption=caption)
        click.echo(f"✅ Meal image analyzed & logged into SQLite (Record ID: {res.get('record_id')})!")
        click.echo(f"   - Meal Type: {res.get('meal_type')}")
        click.echo(f"   - Dishes: {', '.join(res.get('dishes', []))}")
        click.echo(f"   - Calories: {res.get('total_calories')} kcal (P: {res.get('protein_g')}g, C: {res.get('carb_g')}g, F: {res.get('fat_g')}g)")
        click.echo(f"   - Alcohol: {res.get('alcohol_units')} units ({res.get('alcohol_description')})")
        click.echo(f"   - Sleep Risk: {res.get('sleep_risk_assessment')}")
        click.echo(f"   - Summary: {res.get('short_summary')}")
    except Exception as exc:
        click.echo(f"❌ Meal image analysis failed: {exc}", err=True)

@cli.command("run-daily")
@click.option("--date", "target_date", default=None, help="Target date in YYYY-MM-DD format (default: today)")
def run_daily(target_date):
    """Execute complete daily pipeline: sync data -> compute baseline & AI report -> publish Telegraph -> send Executive Brief to Telegram."""
    today_str = target_date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🚀 Running Daily Garmin Health AI Pipeline for date: {today_str}...")

    # Step 1: Sync live metrics
    click.echo(f"🔄 Step 1/4: Syncing Garmin health data for {today_str}...")
    try:
        sync_res = fetch_and_store_daily_data(today_str)
        click.echo(f"✅ Data synced successfully for {sync_res.date}!")
    except Exception as exc:
        click.echo(f"⚠️ Warning: Live sync encountered error: {exc}. Proceeding with existing DB metrics...")

    # Step 2: Generate AI Report & Executive Brief
    click.echo(f"🧠 Step 2/4: Computing 30-day baseline, AI report & Executive Brief...")
    baseline_data = calculate_baseline(today_str, days=30)
    analysis_res = generate_health_analysis(baseline_data, dry_run=False)

    from src.analytics.prompt_engine import generate_executive_brief
    quick_brief = generate_executive_brief(baseline_data)

    save_report_to_db(
        date=today_str,
        report_markdown=analysis_res["report_markdown"],
        raw_prompt=analysis_res["raw_prompt"],
        model_used=analysis_res["model_used"],
        status="SUCCESS",
        prompt_tokens=analysis_res.get("prompt_tokens", 0),
        completion_tokens=analysis_res.get("completion_tokens", 0)
    )

    exported_path = export_report_to_file(today_str, analysis_res["report_markdown"])
    click.echo(f"✅ AI Report generated & exported to: {exported_path}")

    # Step 3: Split AI report into 4 sequential Message Cards & Dispatch to Telegram
    click.echo(f"📲 Step 3/3: Splitting AI report into 4 Message Cards & Dispatching to Telegram...")
    from src.analytics.prompt_engine import split_report_into_sections
    from src.delivery.telegram_bot import send_multi_section_report

    sections = split_report_into_sections(analysis_res["report_markdown"])
    click.echo(f"📊 Report split into {len(sections)} Message Card(s). Sending sequentially...")

    delivery_ok = send_multi_section_report(sections)

    if delivery_ok:
        click.echo("🎉 Daily execution complete: 4 Message Cards successfully delivered to Telegram!")
    else:
        click.echo("⚠️ Daily execution complete: Report saved locally, but Telegram delivery encountered an issue.")

@cli.command("send-report")
@click.option('--date', default=None, help='Target date in YYYY-MM-DD format (default: today)')
@click.option('--chat-id', default=None, help='Target Telegram Chat ID (optional)')
def send_report(date, chat_id):
    """Send an existing AI health analysis report to Telegram."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"📲 Preparing to send AI report for date: {target_date} to Telegram...")

    report_markdown = None

    # 1. Try reading from local markdown report file first
    report_file = BASE_DIR / "data" / "reports" / f"{target_date}_health_journal.md"
    if report_file.exists():
        report_markdown = report_file.read_text(encoding="utf-8")
        click.echo(f"📄 Found local report file at: {report_file}")
    else:
        # 2. Try fetching from SQLite ai_reports table
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT report_markdown FROM ai_reports WHERE date = ? AND status = 'SUCCESS' ORDER BY created_at DESC LIMIT 1", (target_date,))
            row = cursor.fetchone()
            if row and row[0]:
                report_markdown = row[0]
                click.echo(f"🗄️ Found report in SQLite database (`ai_reports` table).")

    if not report_markdown:
        click.echo(f"❌ No AI report found for date {target_date}. Please run `python main.py analyze --date {target_date}` first.", err=True)
        sys.exit(1)

    from src.delivery.telegram_bot import send_telegram_report
    ok = send_telegram_report(report_markdown, chat_id=chat_id)
    if ok:
        click.echo("🎉 Report successfully delivered to Telegram in 4 Message Cards!")
    else:
        click.echo("⚠️ Failed to deliver report to Telegram. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID settings.", err=True)


@cli.command("evening-checkin")
@click.option('--date', default=None, help='Target date in YYYY-MM-DD format (default: today)')
@click.option('--send-telegram/--no-send-telegram', default=True, help='Dispatch check-in card to Telegram (default: True)')
def evening_checkin(date, send_telegram):
    """Run 21:00 evening check-in: Total steps, mechanical load analysis, pre-bedtime recovery reminders, and dispatch 1 Telegram card."""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    click.echo(f"🌙 Running Evening Check-in for date: {target_date}...")

    # 1. Sync live data first to ensure latest step counts
    try:
        fetch_and_store_daily_data(target_date, verbose=False)
    except Exception as exc:
        click.echo(f"ℹ️ Sync notice: {exc}")

    # 2. Generate Check-in summary
    from src.analytics.evening_checkin import generate_evening_checkin
    checkin_res = generate_evening_checkin(target_date)
    card_md = checkin_res["card_markdown"]

    click.echo("\n" + "=" * 50)
    click.echo(card_md)
    click.echo("=" * 50 + "\n")

    # 3. Deliver to Telegram if requested
    if send_telegram:
        from src.delivery.telegram_bot import send_telegram_report
        ok = send_telegram_report(card_md)
        if ok:
            click.echo("📲 Evening Check-in Card successfully delivered to Telegram!")
        else:
            click.echo("⚠️ Notice: Telegram delivery failed or credentials missing.")


if __name__ == "__main__":
    cli()





