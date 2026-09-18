from pathlib import Path
from typing import Optional
from config.settings import BASE_DIR
from src.db.connection import get_db_connection, init_db
from src.db.models import AIReport
from src.db.schema import UPSERT_AI_REPORTS_SQL

def save_report_to_db(
    date: str,
    report_markdown: str,
    raw_prompt: str = "",
    model_used: str = "",
    status: str = "SUCCESS",
    delivered_status: str = "PENDING",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    db_path: Optional[Path] = None
) -> AIReport:
    """Save or update AI health analysis report in SQLite database (ai_reports table)."""
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

    return report_model

def export_report_to_file(
    date: str,
    report_markdown: str,
    output_dir: Optional[Path] = None
) -> Path:
    """Export report markdown content to a local file at data/reports/YYYY-MM-DD_health_journal.md."""
    target_dir = output_dir or (BASE_DIR / "data" / "reports")
    target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / f"{date}_health_journal.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(report_markdown)

    return file_path

def get_report_from_db(
    date: str,
    db_path: Optional[Path] = None
) -> Optional[AIReport]:
    """Retrieve an existing report record from SQLite by date."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_reports WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row:
            return AIReport(**dict(row))
    return None
