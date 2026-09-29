from pathlib import Path
from typing import Optional, Dict, Any
from config.settings import BASE_DIR
from src.db.connection import get_db_connection, init_db
from src.db.models import AIReport
from src.db.schema import UPSERT_AI_REPORTS_SQL
from src.db.report_repository import save_report, get_report_by_type

def save_report_to_db(
    date: str,
    report_markdown: str,
    raw_prompt: str = "",
    model_used: str = "",
    status: str = "SUCCESS",
    delivered_status: str = "PENDING",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    report_type: str = "morning",
    metrics_snapshot: Optional[Dict[str, Any]] = None,
    db_path: Optional[Path] = None
) -> AIReport:
    """Save or update AI health analysis report in SQLite database (both ai_reports and daily_reports tables)."""
    target_db_path = init_db(db_path)
    report_model = AIReport(
        date=date,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        report_markdown=report_markdown,
        raw_prompt=raw_prompt,
        model_used=model_used,
        status=status,
        delivered_status=delivered_status
    )

    with get_db_connection(target_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(UPSERT_AI_REPORTS_SQL, report_model.to_db_tuple())
        conn.commit()

    # Save to versioned daily_reports table unique on (date, report_type)
    save_report(
        date=date,
        report_type=report_type,
        content=report_markdown,
        metrics_snapshot=metrics_snapshot,
        db_path=target_db_path
    )

    return report_model

def export_report_to_file(
    date: str,
    report_markdown: str,
    report_type: str = "morning",
    output_dir: Optional[Path] = None
) -> Path:
    """Export report markdown content to a local file at data/reports/YYYY-MM-DD_[report_type_]health_journal.md."""
    target_dir = output_dir or (BASE_DIR / "data" / "reports")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    cleaned_md = report_markdown.replace("===SECTION_BREAK===", "\n---\n")

    r_type = (report_type or "morning").lower()
    if r_type == "morning":
        file_path = target_dir / f"{date}_health_journal.md"
    else:
        file_path = target_dir / f"{date}_{r_type}_health_journal.md"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(cleaned_md)

    return file_path


def get_report_from_db(
    date: str,
    report_type: Optional[str] = None,
    db_path: Optional[Path] = None
) -> Optional[AIReport]:
    """Retrieve an existing report record from SQLite by date (and optional report_type)."""
    if report_type:
        typed = get_report_by_type(date, report_type, db_path=db_path)
        if typed:
            return AIReport(
                date=date,
                prompt_tokens=0,
                completion_tokens=0,
                report_markdown=typed["content"],
                raw_prompt="",
                model_used="daily_reports",
                status="SUCCESS",
                delivered_status="DELIVERED"
            )

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_reports WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row:
            return AIReport(**dict(row))
    return None
