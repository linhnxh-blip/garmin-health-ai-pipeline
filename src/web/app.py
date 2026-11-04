"""
Garmin Health AI Pipeline - Web Dashboard Application Entrypoint
Delegates and re-exports the FastAPI app from src.delivery.web_dashboard for compatibility.
"""

from src.delivery.web_dashboard import (
    app,
    _render_markdown_to_html,
    _get_daily_metrics_row,
    get_dashboard_data,
    dashboard_homepage,
    view_report_detail
)

__all__ = [
    "app",
    "_render_markdown_to_html",
    "_get_daily_metrics_row",
    "get_dashboard_data",
    "dashboard_homepage",
    "view_report_detail"
]
