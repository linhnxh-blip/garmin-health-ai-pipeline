from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.db.connection import init_db, get_db_connection
from src.db.report_repository import save_report
from src.web.app import app, _render_markdown_to_html
from src.delivery.web_dashboard import app as delivery_app, get_dashboard_data

@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    db_p = tmp_path / "test_garmin.db"
    init_db(db_p)
    return db_p

def test_render_markdown_to_html():
    md = "# Title Header\n\n===SECTION_BREAK===\n### Section 1\n- Item 1\n- Item 2"
    html_out = _render_markdown_to_html(md)
    assert 'class="report-container"' in html_out
    assert "Title Header" in html_out
    assert "Section 1" in html_out
    assert "Item 1" in html_out

def test_web_homepage_empty(temp_db: Path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "db_path", str(temp_db))

    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Garmin Health AI Dashboard" in response.text
    assert "7 Ngày gần nhất" in response.text
    assert "30 Ngày qua" in response.text
    assert "Tất cả" in response.text

def test_web_homepage_and_detail(temp_db: Path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "db_path", str(temp_db))

    # Save a mock report
    date_str = "2026-09-29"
    save_report(
        date=date_str,
        report_type="midday",
        content="# ☀️ Test Midday Report\n\n===SECTION_BREAK===\n### 🧠 1. Status\nOptimal.",
        db_path=temp_db
    )

    client = TestClient(app)
    # Test homepage
    resp_home = client.get("/")
    assert resp_home.status_code == 200
    assert date_str in resp_home.text
    assert "/report/2026-09-29/midday" in resp_home.text

    # Test report detail page
    resp_detail = client.get(f"/report/{date_str}/midday")
    assert resp_detail.status_code == 200
    assert "Test Midday Report" in resp_detail.text
    assert "MIDDAY REPORT" in resp_detail.text

def test_compact_data_table_metrics_and_one_click_actions(temp_db: Path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "db_path", str(temp_db))

    date_str = "2026-10-11"
    # Insert daily metrics
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO daily_metrics (
                date, sleep_score, hrv_last_night, resting_heart_rate, total_steps, hrv_status
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (date_str, 85, 43.2, 56, 8, "BALANCED"))
        conn.commit()

    # Save morning and evening reports (midday is None)
    save_report(date=date_str, report_type="morning", content="Morning Report", db_path=temp_db)
    save_report(date=date_str, report_type="evening", content="Evening Report", db_path=temp_db)

    client = TestClient(delivery_app)
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.text

    # 1. Date column: check formatted date & calendar icon
    assert "CN, 11/10/2026" in html
    assert "2026-10-11" in html
    assert "📅" in html

    # 2. Quick Metrics badges: Sleep (green >= 80), HRV, RHR, Steps
    assert "pill-sleep-good" in html
    assert "85/100" in html
    assert "43.2 ms" in html
    assert "56 bpm" in html
    assert "8 bước" in html

    # 3. One-Click action buttons: Sáng and Tối are active links; Trưa is disabled
    assert f'href="/report/{date_str}/morning"' in html
    assert f'href="/report/{date_str}/evening"' in html
    assert f'href="/report/{date_str}/midday"' not in html
    assert "action-btn-midday disabled" in html

def test_dashboard_api_endpoint(temp_db: Path, monkeypatch):
    from config.settings import settings
    monkeypatch.setattr(settings, "db_path", str(temp_db))

    date_str = "2026-10-11"
    save_report(date=date_str, report_type="morning", content="Morning", db_path=temp_db)

    client = TestClient(app)
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert data["total"] >= 1
    row = data["data"][0]
    assert row["date"] == date_str
    assert row["has_morning"] is True
    assert row["has_midday"] is False
    assert row["has_evening"] is False
    assert row["morning_url"] == f"/report/{date_str}/morning"
    assert row["midday_url"] is None


def test_render_markdown_table_indented_and_responsive():
    """Verify that indented markdown tables under list items parse into <table> within responsive wrappers."""
    raw_md = """### 💤 2. Bóc tách Cấu trúc Giấc ngủ & Tái tạo Sinh học:
- **BẢNG ĐỐI CHUẨN CẤU TRÚC GIẤC NGỦ (SLEEP NORMS BENCHMARK):**
  | Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |
  | :--- | :--- | :--- | :--- | :--- |
  | Deep Sleep | 65.0 phút (19.6%) | 54.8m (13.4%) | 15% - 25% | Đạt chuẩn |
  | REM Sleep | 0.0 phút (0.0%) | 75.0m (18.3%) | 20% - 25% | Bất thường (Mất pha REM) |
"""
    html_out = _render_markdown_to_html(raw_md)
    assert "<table" in html_out
    assert "class=\"table-responsive\"" in html_out
    assert "Deep Sleep" in html_out
    assert "REM Sleep" in html_out
    assert "<th" in html_out
    assert "<td" in html_out


def test_report_detail_uses_report_template(temp_db: Path, monkeypatch):
    """Verify report detail page uses templates/report.html and renders metrics cards and tables."""
    from config.settings import settings
    monkeypatch.setattr(settings, "db_path", str(temp_db))

    date_str = "2026-10-12"
    with get_db_connection(temp_db) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO daily_metrics (
                date, sleep_score, hrv_last_night, resting_heart_rate, total_steps, hrv_status, training_readiness_score, weight_kg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (date_str, 47, 31.0, 61, 8500, "BALANCED", 15, 65.2))
        conn.commit()

    report_content = """# 🌅 Báo cáo Khởi động Ngày

===SECTION_BREAK===
### 💤 2. Bóc tách Cấu trúc Giấc ngủ:
| Pha giấc ngủ | Đêm qua (Phút / %) | Baseline 30d | Chuẩn Y học Thể thao | Đánh giá |
| :--- | :--- | :--- | :--- | :--- |
| Deep Sleep | 65.0 phút (19.6%) | 54.8m (13.4%) | 15% - 25% | Đạt chuẩn |
| REM Sleep | 0.0 phút (0.0%) | 75.0m (18.3%) | 20% - 25% | Bất thường |
"""
    save_report(date=date_str, report_type="morning", content=report_content, db_path=temp_db)

    client = TestClient(delivery_app)
    resp = client.get(f"/report/{date_str}/morning")
    assert resp.status_code == 200
    assert "MORNING REPORT" in resp.text
    assert "47/100" in resp.text
    assert "31.0 ms" in resp.text
    assert "61 bpm" in resp.text
    assert "15/100" in resp.text
    assert "65.2 kg" in resp.text
    assert "<table" in resp.text
    assert "table-responsive" in resp.text
    assert "Deep Sleep" in resp.text
    assert "REM Sleep" in resp.text

