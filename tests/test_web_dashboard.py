from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.db.connection import init_db, get_db_connection
from src.db.report_repository import save_report
from src.web.app import app, _render_markdown_to_html

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
