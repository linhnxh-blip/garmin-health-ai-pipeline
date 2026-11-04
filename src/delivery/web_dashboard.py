"""
Garmin Health AI Pipeline - Web Dashboard
Compact Data Table & Intraday Navigation Delivery Module.
Provides responsive, high-performance HTML/JSON views for versioned health reports.
"""

import html
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import markdown

from config.settings import settings, BASE_DIR
from src.db.connection import get_db_connection, init_db
from src.db.report_repository import get_all_reports_for_date, get_report_by_type

app = FastAPI(
    title="Garmin Health AI Dashboard",
    description="Compact Data Table & Real-Time Recovery Monitoring Dashboard",
    version="2.0.0"
)

# Mount static files if directory exists
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

TEMPLATES_DIR = BASE_DIR / "templates"

VIETNAMESE_WEEKDAYS = {
    0: "T2",
    1: "T3",
    2: "T4",
    3: "T5",
    4: "T6",
    5: "T7",
    6: "CN"
}


def _format_date_vietnamese(date_str: str) -> Tuple[str, str]:
    """Convert YYYY-MM-DD into (formatted_display, weekday_short), e.g. ('CN, 11/10/2026', 'CN')."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        w_short = VIETNAMESE_WEEKDAYS.get(dt.weekday(), "N/A")
        return f"{w_short}, {dt.strftime('%d/%m/%Y')}", w_short
    except Exception:
        return date_str, ""


def normalize_markdown_tables(md_text: str) -> str:
    """
    Ensure markdown tables are properly separated from lists/paragraphs and unindented.
    In standard markdown, indented table rows (e.g. inside a list item) fail to parse as HTML tables.
    """
    if not md_text:
        return ""

    lines = md_text.splitlines()
    normalized_lines = []
    in_table = False
    table_lines = []

    for line in lines:
        stripped = line.strip()
        is_table_row = stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2

        if is_table_row:
            if not in_table:
                in_table = True
                if normalized_lines and normalized_lines[-1].strip() != "":
                    normalized_lines.append("")
            table_lines.append(stripped)
        else:
            if in_table:
                normalized_lines.extend(table_lines)
                table_lines = []
                in_table = False
                if stripped != "":
                    normalized_lines.append("")
            normalized_lines.append(line)

    if in_table:
        normalized_lines.extend(table_lines)
        normalized_lines.append("")

    return "\n".join(normalized_lines)


def _render_markdown_to_html(md_text: str) -> str:
    """Render markdown string into clean HTML with section break boxes, tables extension, and styling."""
    if not md_text:
        return '<div class="report-container"><p><i>Không có nội dung báo cáo.</i></p></div>'

    sections = [s.strip() for s in md_text.split("===SECTION_BREAK===") if s.strip()]
    if not sections:
        sections = [md_text.strip()]

    html_boxes = []
    for sec in sections:
        clean_sec = normalize_markdown_tables(sec)
        rendered = markdown.markdown(
            clean_sec,
            extensions=["extra", "tables", "fenced_code", "nl2br", "sane_lists"]
        )
        # Wrap rendered tables into a responsive container for smooth mobile and desktop view
        rendered = re.sub(
            r"(<table>.*?</table>)",
            r'<div class="table-responsive">\1</div>',
            rendered,
            flags=re.DOTALL
        )
        html_boxes.append(f'<div class="section-box markdown-body bg-[#1e293b] border border-[#334155] rounded-xl p-6 mb-4 shadow-md">{rendered}</div>')

    return f'<div class="report-container">{"".join(html_boxes)}</div>'



def _get_daily_metrics_row(date: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Fetch metrics row from SQLite daily_metrics for header and badge stats."""
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def get_dashboard_data(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Retrieve structured daily data entries for the dashboard table.
    Each entry contains physiological metrics and one-click report availability flags.
    """
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT date FROM daily_reports
            UNION
            SELECT DISTINCT date FROM ai_reports
            ORDER BY date DESC
        """)
        dates = [r[0] for r in cursor.fetchall()]

    entries = []
    for d in dates:
        reports = get_all_reports_for_date(d, db_path=db_path)
        metrics = _get_daily_metrics_row(d, db_path=db_path) or {}

        report_types = set([r["report_type"] for r in reports]) if reports else set()
        if not report_types:
            with get_db_connection(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM ai_reports WHERE date = ?", (d,))
                if cursor.fetchone():
                    report_types.add("morning")

        has_morning = "morning" in report_types
        has_midday = "midday" in report_types
        has_evening = "evening" in report_types

        date_display, weekday = _format_date_vietnamese(d)

        sleep_sc = metrics.get("sleep_score")
        if sleep_sc is not None:
            try:
                s_val = int(sleep_sc)
                if s_val >= 80:
                    sleep_class = "pill-sleep-good"
                elif s_val >= 60:
                    sleep_class = "pill-sleep-fair"
                else:
                    sleep_class = "pill-sleep-poor"
                sleep_display = f"{s_val}/100"
            except Exception:
                sleep_class = "pill-sleep-none"
                sleep_display = f"{sleep_sc}/100"
        else:
            sleep_class = "pill-sleep-none"
            sleep_display = "N/A"

        hrv_val = metrics.get("hrv_last_night")
        hrv_str = f"{round(float(hrv_val), 1)} ms" if hrv_val is not None else "N/A"
        hrv_status = metrics.get("hrv_status") or ("Balanced" if hrv_val and hrv_val >= 40 else "N/A")

        rhr_val = metrics.get("resting_heart_rate")
        rhr_str = f"{rhr_val} bpm" if rhr_val is not None else "N/A"

        steps_val = metrics.get("total_steps")
        if steps_val is not None:
            try:
                steps_str = f"{int(steps_val):,} bước"
            except Exception:
                steps_str = f"{steps_val} bước"
        else:
            steps_str = "N/A"

        entries.append({
            "date": d,
            "date_display": date_display,
            "weekday": weekday,
            "has_morning": has_morning,
            "has_midday": has_midday,
            "has_evening": has_evening,
            "morning_url": f"/report/{d}/morning" if has_morning else None,
            "midday_url": f"/report/{d}/midday" if has_midday else None,
            "evening_url": f"/report/{d}/evening" if has_evening else None,
            "sleep_score": sleep_sc,
            "sleep_display": sleep_display,
            "sleep_class": sleep_class,
            "hrv_str": hrv_str,
            "hrv_status": hrv_status,
            "rhr_str": rhr_str,
            "steps_str": steps_str,
            "metrics": metrics
        })

    return entries


def _render_table_rows_html(entries: List[Dict[str, Any]]) -> str:
    """Render HTML table rows from dashboard entries."""
    if not entries:
        return ""

    rows_html = []
    for e in entries:
        d = e["date"]
        date_display = e["date_display"]
        sleep_class = e["sleep_class"]
        sleep_display = e["sleep_display"]
        hrv_str = e["hrv_str"]
        hrv_status = e["hrv_status"]
        rhr_str = e["rhr_str"]
        steps_str = e["steps_str"]

        # Action Buttons
        if e["has_morning"]:
            btn_morning = f'<a href="/report/{d}/morning" class="action-btn action-btn-morning" title="Xem Báo cáo Sáng">🌅 Sáng</a>'
        else:
            btn_morning = '<span class="action-btn action-btn-morning disabled" title="Chưa có báo cáo sáng">🌅 Sáng</span>'

        if e["has_midday"]:
            btn_midday = f'<a href="/report/{d}/midday" class="action-btn action-btn-midday" title="Xem Báo cáo Trưa">☀️ Trưa</a>'
        else:
            btn_midday = '<span class="action-btn action-btn-midday disabled" title="Chưa có báo cáo trưa">☀️ Trưa</span>'

        if e["has_evening"]:
            btn_evening = f'<a href="/report/{d}/evening" class="action-btn action-btn-evening" title="Xem Báo cáo Tối">🌙 Tối</a>'
        else:
            btn_evening = '<span class="action-btn action-btn-evening disabled" title="Chưa có báo cáo tối">🌙 Tối</span>'

        # Sleep pill icon
        sleep_icon = "🟢" if "good" in sleep_class else ("🟡" if "fair" in sleep_class else ("🔴" if "poor" in sleep_class else "⚪"))

        row = f"""
        <tr data-date="{d}" class="hover:bg-slate-800/60 transition-colors">
            <td>
                <div class="date-cell">
                    <span class="date-icon" aria-hidden="true">📅</span>
                    <div>
                        <span class="date-title-main">{date_display}</span>
                        <span class="date-title-sub">{d}</span>
                    </div>
                </div>
            </td>
            <td>
                <div class="metrics-pill-list">
                    <span class="metric-pill {sleep_class}" title="Điểm Giấc ngủ Garmin">
                        <span class="label">Sleep</span>
                        <b>{sleep_display}</b>
                    </span>
                    <span class="metric-pill pill-hrv" title="HRV Đêm qua & Trạng thái">
                        <span class="label">HRV</span>
                        <b>{hrv_str}</b>
                        <span class="text-[0.7rem] opacity-75">({hrv_status})</span>
                    </span>
                    <span class="metric-pill pill-rhr" title="Nhịp tim nghỉ qua đêm">
                        <span class="label">RHR</span>
                        <b>{rhr_str}</b>
                    </span>
                    <span class="metric-pill pill-steps" title="Tổng số bước chân">
                        <span class="label">Steps</span>
                        <b>{steps_str}</b>
                    </span>
                </div>
            </td>
            <td>
                <div class="actions-cell">
                    {btn_morning}
                    {btn_midday}
                    {btn_evening}
                </div>
            </td>
        </tr>
        """
        rows_html.append(row)

    return "\n".join(rows_html)


@app.get("/api/dashboard", response_class=JSONResponse)
def api_dashboard_data():
    """JSON API returning all daily records with physiological badges and report availability."""
    entries = get_dashboard_data()
    return JSONResponse(content={"total": len(entries), "data": entries})


@app.get("/", response_class=HTMLResponse)
def dashboard_homepage():
    """Homepage rendering compact responsive data table with quick filters and pagination."""
    entries = get_dashboard_data()
    rows_html = _render_table_rows_html(entries)

    template_file = TEMPLATES_DIR / "dashboard.html"
    if template_file.exists():
        html_content = template_file.read_text(encoding="utf-8")
        if rows_html:
            html_content = html_content.replace("<!-- TABLE_ROWS_PLACEHOLDER -->", rows_html)
        else:
            # If no rows, show empty state initially
            empty_snippet = """
            <tr>
                <td colspan="3" class="text-center py-12 text-slate-400">
                    <div class="text-3xl mb-2">📭</div>
                    <div class="font-semibold text-white">Chưa có báo cáo nào trong cơ sở dữ liệu</div>
                    <div class="text-xs mt-1 text-slate-500">Chạy: <code>python main.py analyze --type auto</code> để tạo báo cáo đầu tiên.</div>
                </td>
            </tr>
            """
            html_content = html_content.replace("<!-- TABLE_ROWS_PLACEHOLDER -->", empty_snippet)
    else:
        # Fallback inline template
        html_content = f"""
        <!DOCTYPE html>
        <html lang="vi">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Garmin Health AI Dashboard</title>
            <link rel="stylesheet" href="/static/css/dashboard.css">
        </head>
        <body>
            <header>
                <a href="/" class="logo">
                    <span class="logo-icon">🏃‍♂️</span>
                    <span>Garmin Health AI Dashboard</span>
                </a>
            </header>
            <main>
                <div class="table-container">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>📅 Ngày & Thứ</th>
                                <th>⚡ Chỉ số Sinh lý</th>
                                <th>🎯 Báo cáo Sẵn sàng</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html or '<tr><td colspan="3" style="text-align: center; padding: 30px;">Chưa có báo cáo nào.</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </main>
        </body>
        </html>
        """

    return HTMLResponse(content=html_content)


@app.get("/report/{date}/{report_type}", response_class=HTMLResponse)
@app.get("/report/{date}", response_class=HTMLResponse)
def view_report_detail(date: str, report_type: Optional[str] = None):
    """Render full intraday report Markdown as HTML for a given date and report_type."""
    init_db()
    r_type = (report_type or "morning").lower()
    report = get_report_by_type(date, r_type)

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

    all_intraday = get_all_reports_for_date(date)
    existing_types = [r["report_type"] for r in all_intraday] if all_intraday else [r_type]

    type_tabs_html = []
    type_names = {"morning": "🌅 Sáng (Morning)", "midday": "☀️ Trưa (Midday)", "evening": "🌙 Tối (Evening)"}
    for t_key, t_title in type_names.items():
        if t_key in existing_types or t_key == r_type:
            active_cls = "active" if t_key == r_type else ""
            type_tabs_html.append(f'<a href="/report/{date}/{t_key}" class="type-nav-btn {active_cls}">{t_title}</a>')

    date_display, _ = _format_date_vietnamese(date)

    template_file = TEMPLATES_DIR / "report.html"
    if template_file.exists():
        template_raw = template_file.read_text(encoding="utf-8")
        replacements = {
            "{{TITLE}}": f"Báo cáo Ngày {date_display} ({r_type.upper()}) - Garmin Health AI",
            "{{DATE}}": date,
            "{{DATE_DISPLAY}}": date_display,
            "{{REPORT_TYPE}}": r_type,
            "{{REPORT_TYPE_UPPER}}": r_type.upper(),
            "{{TYPE_TABS_HTML}}": "".join(type_tabs_html),
            "{{SLEEP_SCORE}}": f"{sleep_sc}/100" if sleep_sc != "N/A" else "N/A",
            "{{HRV_STR}}": hrv_str,
            "{{HRV_STATUS}}": metrics.get("hrv_status") or "BALANCED",
            "{{RHR_STR}}": rhr_str,
            "{{READINESS}}": f"{readiness}/100" if readiness != "N/A" else "N/A",
            "{{WEIGHT}}": f"{weight} kg" if weight != "N/A" else "N/A",
            "{{STEPS_STR}}": steps_str,
            "{{RENDERED_CONTENT}}": rendered_html
        }
        for placeholder, val in replacements.items():
            template_raw = template_raw.replace(placeholder, str(val))
        return HTMLResponse(content=template_raw)

    html_page = f"""
    <!DOCTYPE html>

    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Báo cáo {date} ({r_type.upper()}) - Garmin Health AI</title>
        <link rel="stylesheet" href="/static/css/dashboard.css">
        <style>
            .type-nav {{ display: flex; gap: 10px; margin-bottom: 20px; }}
            .type-nav-btn {{
                text-decoration: none; padding: 8px 16px; border-radius: 8px;
                border: 1px solid var(--border-color); background: var(--bg-card);
                color: var(--text-secondary); font-weight: 600; font-size: 0.9rem;
                transition: all 0.2s ease;
            }}
            .type-nav-btn.active {{
                background: var(--accent-blue); color: #0f172a; border-color: var(--accent-blue);
                box-shadow: 0 2px 8px rgba(56, 189, 248, 0.35);
            }}
            .type-nav-btn:hover:not(.active) {{
                background: var(--bg-hover); color: #ffffff;
            }}
            .metrics-grid {{
                display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 14px; margin-bottom: 24px;
            }}
            .metric-card {{
                background: var(--bg-card); border: 1px solid var(--border-color);
                border-radius: 12px; padding: 14px; text-align: center;
            }}
            .metric-label {{ font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 4px; }}
            .metric-value {{ font-size: 1.3rem; font-weight: 700; color: #ffffff; }}
            .metric-sub {{ font-size: 0.75rem; color: var(--accent-green); margin-top: 2px; }}
            .nav-back {{
                display: inline-flex; align-items: center; gap: 6px;
                background: var(--bg-card); color: var(--accent-blue);
                padding: 6px 14px; border-radius: 8px; text-decoration: none;
                border: 1px solid var(--border-color); font-weight: 600; font-size: 0.85rem;
                transition: all 0.2s ease;
            }}
            .nav-back:hover {{
                background: var(--bg-hover); color: #ffffff; border-color: var(--accent-blue);
            }}
            .badge-report-tag {{
                display: inline-block; padding: 4px 12px; border-radius: 12px;
                font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .badge-morning {{ background: rgba(251, 191, 36, 0.15); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.3); }}
            .badge-midday {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); }}
            .badge-evening {{ background: rgba(167, 139, 250, 0.15); color: #a78bfa; border: 1px solid rgba(167, 139, 250, 0.3); }}
            .section-box {{
                background: var(--bg-card); border: 1px solid var(--border-color);
                border-radius: 14px; padding: 22px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
            }}
            .markdown-body h1, .markdown-body h2, .markdown-body h3 {{
                color: var(--accent-blue); margin-top: 16px; margin-bottom: 12px; font-weight: 700;
            }}
            .markdown-body h1 {{ font-size: 1.6rem; border-bottom: 2px solid var(--border-color); padding-bottom: 8px; color: #ffffff; }}
            .markdown-body h3 {{ font-size: 1.2rem; color: var(--accent-cyan); }}
            .markdown-body p {{ margin-bottom: 10px; color: var(--text-primary); }}
            .markdown-body ul, .markdown-body ol {{ margin-left: 20px; margin-bottom: 14px; }}
            .markdown-body li {{ margin-bottom: 4px; }}
            .markdown-body table {{
                width: 100%; border-collapse: collapse; margin: 16px 0; background: var(--bg-main);
                border-radius: 8px; overflow: hidden;
            }}
            .markdown-body th, .markdown-body td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid var(--border-color); }}
            .markdown-body th {{ background: rgba(56, 189, 248, 0.1); color: var(--accent-blue); font-weight: 600; }}
            .markdown-body tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
            .markdown-body blockquote {{
                border-left: 4px solid var(--accent-amber); background: rgba(251, 191, 36, 0.08);
                padding: 10px 14px; margin: 14px 0; border-radius: 0 8px 8px 0;
            }}
            .markdown-body code {{
                background: rgba(255, 255, 255, 0.1); padding: 2px 6px; border-radius: 4px;
                font-family: monospace; font-size: 0.9em; color: var(--accent-amber);
            }}
        </style>
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
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; flex-wrap: wrap; gap: 10px;">
                <h1 style="font-size: 1.5rem; color: #ffffff; font-weight: 800;">📄 Báo cáo Ngày {date_display}</h1>
                <span class="badge-report-tag badge-{r_type}">{r_type.upper()} REPORT</span>
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
