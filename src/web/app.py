import html
import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
import markdown

from config.settings import settings, BASE_DIR
from src.db.connection import get_db_connection, init_db
from src.db.report_repository import get_all_reports_for_date, get_report_by_type

app = FastAPI(
    title="Garmin Health AI Local Dashboard",
    description="Local Web Dashboard for viewing versioned Garmin Health AI reports from SQLite",
    version="1.0.0"
)


COMMON_CSS = """
:root {
    --bg-main: #0f172a;
    --bg-card: #1e293b;
    --bg-card-hover: #334155;
    --border-color: #334155;
    --text-primary: #f8fafc;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --accent-blue: #38bdf8;
    --accent-cyan: #06b6d4;
    --accent-green: #34d399;
    --accent-amber: #fbbf24;
    --accent-purple: #a78bfa;
    --accent-red: #f87171;
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--bg-main);
    color: var(--text-primary);
    line-height: 1.6;
    padding: 20px;
    max-width: 1200px;
    margin: 0 auto;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 0;
    border-bottom: 1px solid var(--border-color);
    margin-bottom: 30px;
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent-blue);
    text-decoration: none;
}

.logo-icon {
    font-size: 1.8rem;
}

.nav-back {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-card);
    color: var(--accent-blue);
    padding: 8px 16px;
    border-radius: 8px;
    text-decoration: none;
    border: 1px solid var(--border-color);
    font-weight: 600;
    transition: all 0.2s ease;
}

.nav-back:hover {
    background: var(--bg-card-hover);
    color: #ffffff;
    border-color: var(--accent-blue);
}

.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.badge-morning {
    background: rgba(251, 191, 36, 0.15);
    color: var(--accent-amber);
    border: 1px solid rgba(251, 191, 36, 0.3);
}

.badge-midday {
    background: rgba(56, 189, 248, 0.15);
    color: var(--accent-blue);
    border: 1px solid rgba(56, 189, 248, 0.3);
}

.badge-evening {
    background: rgba(167, 139, 250, 0.15);
    color: var(--accent-purple);
    border: 1px solid rgba(167, 139, 250, 0.3);
}

.metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 30px;
}

.metric-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
}

.metric-label {
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-bottom: 6px;
}

.metric-value {
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text-primary);
}

.metric-sub {
    font-size: 0.75rem;
    color: var(--accent-green);
    margin-top: 4px;
}

/* Markdown Render Styling */
.report-container {
    display: flex;
    flex-direction: column;
    gap: 24px;
}

.section-box {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 16px;
    padding: 24px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4 {
    color: var(--accent-blue);
    margin-top: 16px;
    margin-bottom: 12px;
    font-weight: 700;
}

.markdown-body h1 {
    font-size: 1.8rem;
    border-bottom: 2px solid var(--border-color);
    padding-bottom: 8px;
    color: #ffffff;
}

.markdown-body h3 {
    font-size: 1.25rem;
    color: var(--accent-cyan);
    margin-top: 20px;
}

.markdown-body p {
    margin-bottom: 12px;
    color: var(--text-primary);
}

.markdown-body ul, .markdown-body ol {
    margin-left: 24px;
    margin-bottom: 16px;
}

.markdown-body li {
    margin-bottom: 6px;
}

.markdown-body table {
    width: 100%;
    border-collapse: collapse;
    margin: 20px 0;
    background: var(--bg-main);
    border-radius: 8px;
    overflow: hidden;
}

.markdown-body th, .markdown-body td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

.markdown-body th {
    background: rgba(56, 189, 248, 0.1);
    color: var(--accent-blue);
    font-weight: 600;
}

.markdown-body tr:hover {
    background: rgba(255, 255, 255, 0.03);
}

.markdown-body blockquote {
    border-left: 4px solid var(--accent-amber);
    background: rgba(251, 191, 36, 0.08);
    padding: 12px 16px;
    margin: 16px 0;
    border-radius: 0 8px 8px 0;
}

.markdown-body code {
    background: rgba(255, 255, 255, 0.1);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.9em;
    color: var(--accent-amber);
}

.date-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.date-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: border-color 0.2s ease;
}

.date-card:hover {
    border-color: var(--accent-blue);
}

.date-title {
    font-size: 1.2rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 6px;
}

.reports-badges {
    display: flex;
    gap: 10px;
    margin-top: 8px;
}

.btn-view {
    text-decoration: none;
    background: var(--accent-blue);
    color: #0f172a;
    font-weight: 700;
    padding: 8px 16px;
    border-radius: 8px;
    transition: opacity 0.2s ease;
}

.btn-view:hover {
    opacity: 0.9;
}

.type-nav {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
}

.type-nav-btn {
    text-decoration: none;
    padding: 8px 16px;
    border-radius: 8px;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
    color: var(--text-secondary);
    font-weight: 600;

}

.type-nav-btn.active {
    background: var(--accent-blue);
    color: #0f172a;
    border-color: var(--accent-blue);
}

footer {
    text-align: center;
    padding: 30px 0;
    margin-top: 40px;
    border-top: 1px solid var(--border-color);
    color: var(--text-muted);
    font-size: 0.85rem;
}
"""

def _render_markdown_to_html(md_text: str) -> str:
    """Render markdown string into clean HTML using markdown package and section break boxes."""
    if not md_text:
        return "<p><i>Không có nội dung báo cáo.</i></p>"

    # Process SECTION_BREAK delimiters into separate card boxes
    sections = [s.strip() for s in md_text.split("===SECTION_BREAK===") if s.strip()]
    if not sections:
        sections = [md_text.strip()]

    html_boxes = []
    for sec in sections:
        rendered = markdown.markdown(
            sec,
            extensions=["tables", "fenced_code", "nl2br", "sane_lists"]
        )
        html_boxes.append(f'<div class="section-box markdown-body">{rendered}</div>')

    return f'<div class="report-container">{"".join(html_boxes)}</div>'

def _get_daily_metrics_row(date: str) -> Optional[Dict[str, Any]]:
    """Fetch metrics row from SQLite daily_metrics for header stats."""
    init_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


@app.get("/", response_class=HTMLResponse)
def dashboard_homepage():
    """Homepage listing all dates with intraday versioned reports from SQLite."""
    init_db()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Query distinct dates from daily_reports and ai_reports
        cursor.execute("""
            SELECT DISTINCT date FROM daily_reports
            UNION
            SELECT DISTINCT date FROM ai_reports
            ORDER BY date DESC
        """)
        dates = [r[0] for r in cursor.fetchall()]

    cards_html = []

    if not dates:
        cards_html.append("""
            <div class="section-box" style="text-align: center; padding: 40px;">
                <h3>📭 Chưa có báo cáo nào trong cơ sở dữ liệu</h3>
                <p style="margin-top: 12px; color: var(--text-secondary);">Hãy chạy lệnh CLI để tạo báo cáo đầu tiên:</p>
                <code style="display: inline-block; margin-top: 12px; padding: 10px 20px; font-size: 1rem;">python main.py analyze --type auto</code>
            </div>
        """)
    else:
        for d in dates:
            reports = get_all_reports_for_date(d)
            metrics = _get_daily_metrics_row(d) or {}

            report_types = [r["report_type"] for r in reports] if reports else ["morning"]
            badges_html = []
            for rt in ["morning", "midday", "evening"]:
                if rt in report_types:
                    rt_label = "Sáng" if rt == "morning" else ("Trưa" if rt == "midday" else "Tối")
                    badges_html.append(f'<span class="badge badge-{rt}">{rt_label}</span>')

            sleep_sc = metrics.get("sleep_score") or "N/A"
            hrv_val = metrics.get("hrv_last_night")
            hrv_str = f"{hrv_val} ms" if hrv_val is not None else "N/A"
            rhr_val = metrics.get("resting_heart_rate")
            rhr_str = f"{rhr_val} bpm" if rhr_val is not None else "N/A"
            steps = metrics.get("total_steps")
            steps_str = f"{steps:,}" if steps is not None else "N/A"

            # Default to latest available report_type
            latest_rt = report_types[-1] if report_types else "morning"

            cards_html.append(f"""
                <div class="date-card">
                    <div>
                        <div class="date-title">📅 Ngày {d}</div>
                        <div style="font-size: 0.9rem; color: var(--text-secondary); margin-bottom: 8px;">
                            Sleep: <b>{sleep_sc}/100</b> | HRV: <b>{hrv_str}</b> | RHR: <b>{rhr_str}</b> | Steps: <b>{steps_str}</b>
                        </div>
                        <div class="reports-badges">
                            {"".join(badges_html)}
                        </div>
                    </div>
                    <div>
                        <a href="/report/{d}/{latest_rt}" class="btn-view">Xem Báo cáo →</a>
                    </div>
                </div>
            """)

    content = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Garmin Health AI - Dashboard</title>
        <style>{COMMON_CSS}</style>
    </head>
    <body>
        <header>
            <a href="/" class="logo">
                <span class="logo-icon">🏃‍♂️</span>
                <span>Garmin Health AI Dashboard</span>
            </a>
            <div style="color: var(--text-secondary); font-size: 0.9rem;">
                Hệ thống Báo cáo Sinh lý học & Phục hồi
            </div>
        </header>

        <main>
            <h2 style="margin-bottom: 20px; font-size: 1.4rem;">📊 Danh sách Báo cáo Nhật ký Sức khỏe</h2>
            <div class="date-list">
                {"".join(cards_html)}
            </div>
        </main>

        <footer>
            Garmin Health AI Pipeline &copy; 2026 | Local SQLite Web Dashboard
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=content)


@app.get("/report/{date}/{report_type}", response_class=HTMLResponse)
@app.get("/report/{date}", response_class=HTMLResponse)
def view_report_detail(date: str, report_type: Optional[str] = None):
    """Render full intraday report Markdown as HTML for a given date and report_type."""
    init_db()

    # Resolve report_type
    r_type = (report_type or "morning").lower()
    report = get_report_by_type(date, r_type)

    # If specific report_type not found, fallback to any report for date or ai_reports table
    if not report:
        all_reps = get_all_reports_for_date(date)
        if all_reps:
            report = all_reps[-1]
            r_type = report["report_type"]
        else:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT report_markdown, created_at FROM ai_reports WHERE date = ?", (date,))
                row = cursor.fetchone()
                if row:
                    report = {"content": row[0], "report_type": r_type, "date": date}

    if not report:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy báo cáo cho ngày {date} ({r_type})")

    content_md = report.get("content") or report.get("report_markdown") or ""
    rendered_html = _render_markdown_to_html(content_md)

    # Header metrics
    metrics = _get_daily_metrics_row(date) or {}
    sleep_sc = metrics.get("sleep_score") or "N/A"
    hrv_val = metrics.get("hrv_last_night")
    hrv_str = f"{hrv_val} ms" if hrv_val is not None else "N/A"
    rhr_val = metrics.get("resting_heart_rate")
    rhr_str = f"{rhr_val} bpm" if rhr_val is not None else "N/A"
    readiness = metrics.get("training_readiness_score") or "N/A"
    weight = metrics.get("weight_kg") or "N/A"
    steps = metrics.get("total_steps")
    steps_str = f"{steps:,}" if steps is not None else "N/A"

    # Intraday Navigation tabs
    all_intraday = get_all_reports_for_date(date)
    existing_types = [r["report_type"] for r in all_intraday] if all_intraday else [r_type]

    type_tabs_html = []
    type_names = {"morning": "🌅 Sáng (Morning)", "midday": "☀️ Trưa (Midday)", "evening": "🌙 Tối (Evening)"}
    for t_key, t_title in type_names.items():
        if t_key in existing_types or t_key == r_type:
            active_cls = "active" if t_key == r_type else ""
            type_tabs_html.append(f'<a href="/report/{date}/{t_key}" class="type-nav-btn {active_cls}">{t_title}</a>')

    html_page = f"""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Báo cáo {date} ({r_type.upper()}) - Garmin Health AI</title>
        <style>{COMMON_CSS}</style>
    </head>
    <body>
        <header>
            <a href="/" class="logo">
                <span class="logo-icon">🏃‍♂️</span>
                <span>Garmin Health AI</span>
            </a>
            <a href="/" class="nav-back">← Trở về Dashboard</a>
        </header>

        <main>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h1 style="font-size: 1.6rem; color: #ffffff;">📄 Báo cáo Phân tích Ngày {date}</h1>
                <span class="badge badge-{r_type}" style="font-size: 0.9rem; padding: 6px 14px;">{r_type.upper()} REPORT</span>
            </div>

            <div class="type-nav">
                {"".join(type_tabs_html)}
            </div>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">Giấc ngủ (Sleep)</div>
                    <div class="metric-value">{sleep_sc}/100</div>
                    <div class="metric-sub">Garmin Score</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">HRV Overnight</div>
                    <div class="metric-value">{hrv_str}</div>
                    <div class="metric-sub">{metrics.get('hrv_status') or 'BALANCED'}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Nhịp tim nghỉ (RHR)</div>
                    <div class="metric-value">{rhr_str}</div>
                    <div class="metric-sub">Phục hồi tim mạch</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Readiness</div>
                    <div class="metric-value">{readiness}/100</div>
                    <div class="metric-sub">Điểm sẵn sàng</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Cân nặng Omron</div>
                    <div class="metric-value">{weight} kg</div>
                    <div class="metric-sub">Thể trạng thực tế</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Tổng bước chân</div>
                    <div class="metric-value">{steps_str}</div>
                    <div class="metric-sub">Vận động hàng ngày</div>
                </div>
            </div>

            {rendered_html}
        </main>

        <footer>
            Garmin Health AI Pipeline &copy; 2026 | Local SQLite Web Dashboard
        </footer>
    </body>
    </html>
    """
    return HTMLResponse(content=html_page)
