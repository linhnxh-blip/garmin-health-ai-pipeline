import pytest
from unittest.mock import MagicMock, patch

from src.analytics.chat_advisor import (
    get_athlete_live_context,
    build_chat_system_prompt,
    ask_chat_advisor,
    CHAT_HISTORIES
)


def test_get_athlete_live_context():
    context = get_athlete_live_context("2026-11-12")
    assert "HỒ SƠ SINH LÝ HỌC & DINH DƯỠNG THỰC TẾ HÔM NAY" in context
    assert "Uric Acid nền 442 µmol/L" in context
    assert "gân Achilles" in context


def test_build_chat_system_prompt():
    ctx = "Dữ liệu thể trạng mẫu"
    prompt = build_chat_system_prompt(ctx)
    assert "Chuyên gia Sinh lý học Thể thao" in prompt
    assert ctx in prompt
    assert "yến mạch" in prompt


def test_ask_chat_advisor_mock(monkeypatch):
    mock_gemini = MagicMock(return_value={
        "reply_text": "Chào bạn, hôm nay điểm Readiness của bạn là 84/100, rất tốt để phục hồi thụ động.",
        "model_used": "gemini (gemini-3.5-flash)",
        "latency_seconds": 1.15,
        "prompt_tokens": 450,
        "completion_tokens": 120,
        "total_tokens": 570
    })
    monkeypatch.setattr("src.analytics.chat_advisor.call_chat_gemini", mock_gemini)

    res = ask_chat_advisor("Hôm nay tôi nên tập gì?", chat_id="test_chat_123")
    assert "Readiness của bạn là 84/100" in res["reply_text"]
    assert "🤖 AI Engine: Google Gemini 3.5 Flash (Cloud)" in res["reply_text"]
    assert res["model_used"] == "gemini (gemini-3.5-flash)"
    assert res["latency_seconds"] == 1.15

    # Check conversation history sliding window
    history = CHAT_HISTORIES.get("test_chat_123")
    assert len(history) == 2
    assert history[0]["content"] == "Hôm nay tôi nên tập gì?"
    assert "Readiness của bạn là 84/100" in history[1]["content"]


def test_ask_chat_advisor_fallback_to_ollama(monkeypatch):
    # Simulate Gemini failure, fallback to Ollama
    monkeypatch.setattr("src.analytics.chat_advisor.call_chat_gemini", MagicMock(side_effect=RuntimeError("Cloud 503")))
    monkeypatch.setattr("src.analytics.chat_advisor.call_chat_openai", MagicMock(side_effect=RuntimeError("No key")))

    mock_ollama = MagicMock(return_value={
        "reply_text": "Phản hồi từ Local Ollama PC GPU: Nên uống thêm nước kiềm Fujiwa.",
        "model_used": "ollama (qwen2.5:7b) via http://100.115.174.225:11434",
        "latency_seconds": 0.85,
        "prompt_tokens": 300,
        "completion_tokens": 80,
        "total_tokens": 380
    })
    monkeypatch.setattr("src.analytics.chat_advisor.call_chat_ollama", mock_ollama)

    res = ask_chat_advisor("Có nên uống nước kiềm không?", chat_id="test_chat_fallback")
    assert "Phản hồi từ Local Ollama" in res["reply_text"]
    assert "Local PC GPU" in res["reply_text"]
    assert res["latency_seconds"] == 0.85

