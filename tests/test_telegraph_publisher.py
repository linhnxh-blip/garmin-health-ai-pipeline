import pytest
from unittest.mock import MagicMock, patch

from src.delivery.telegraph_publisher import markdown_to_telegraph_nodes, publish_report_to_telegraph

def test_markdown_to_telegraph_nodes():
    md = "# Title Header\n- Item 1\n- Item 2\n\nSome paragraph with **bold** text."
    nodes = markdown_to_telegraph_nodes(md)
    assert len(nodes) > 0
    assert any(n.get("tag") == "h3" for n in nodes)
    assert any(n.get("tag") == "ul" for n in nodes)

def test_publish_report_to_telegraph(monkeypatch, tmp_path):
    monkeypatch.setattr("src.delivery.telegraph_publisher.TOKEN_FILE", tmp_path / ".telegraph_token")

    mock_account_resp = MagicMock()
    mock_account_resp.json.return_value = {
        "ok": True,
        "result": {"access_token": "test_telegraph_token"}
    }

    mock_page_resp = MagicMock()
    mock_page_resp.json.return_value = {
        "ok": True,
        "result": {"url": "https://telegra.ph/Test-Page-09-19"}
    }

    mock_post = MagicMock(side_effect=[mock_account_resp, mock_page_resp])

    with patch("requests.post", mock_post):
        url = publish_report_to_telegraph("Test Title", "# Section\nContent body")
        assert url == "https://telegra.ph/Test-Page-09-19"
