"""
Inbound AI path decisions (ETAPA 6) — pure logic mirror tests.
Does not import backend.server (needs Mongo). Covers unavailable / send-off contract.
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import whatsapp_ai as wai


def decide_ai_path(*, text, message_type, is_group, send_enabled):
    """Mirror of backend inbound AI gating (keep in sync with server._process_whatsapp_inbound_ai)."""
    if is_group:
        return {"status": "skipped", "reason": "group_skip", "processed": False}
    if message_type != "text" or not text:
        return {"status": "skipped", "reason": "non_text", "processed": False}
    if not wai.is_openai_ready():
        return {"status": "unavailable", "reason": "openai_not_configured", "processed": False}
    reply = wai.chat_reply(text, context={"isGroup": False})
    if not send_enabled:
        return {
            "status": "would_reply",
            "reason": "WHATSAPP_SEND_ENABLED_off",
            "processed": True,
            "replyLen": len(reply),
            "reply": reply,
        }
    return {
        "status": "replied",
        "reason": None,
        "processed": True,
        "replyLen": len(reply),
        "reply": reply,
        "sendAttempted": True,
    }


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    wai.set_complete_override(None)
    yield
    wai.set_complete_override(None)


def test_ai_unavailable_path():
    out = decide_ai_path(text="Oi", message_type="text", is_group=False, send_enabled=False)
    assert out["status"] == "unavailable"
    assert out["processed"] is False


def test_ai_available_would_reply_when_send_off(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    wai.set_complete_override(lambda messages, model, key: "Resposta segura de teste")
    out = decide_ai_path(text="Bom dia", message_type="text", is_group=False, send_enabled=False)
    assert out["status"] == "would_reply"
    assert out["reason"] == "WHATSAPP_SEND_ENABLED_off"
    assert out["processed"] is True
    assert out["reply"] == "Resposta segura de teste"


def test_group_and_non_text_skipped(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert decide_ai_path(text="Oi", message_type="text", is_group=True, send_enabled=False)["reason"] == "group_skip"
    assert decide_ai_path(text=None, message_type="image", is_group=False, send_enabled=False)["reason"] == "non_text"


def test_financial_without_facts_on_inbound_sync_mirror(monkeypatch):
    """Mirror uses sync chat_reply; without finance_facts → unavailable message, no OpenAI."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    wai.set_complete_override(lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no call")))
    out = decide_ai_path(
        text="Qual o saldo do caixa?",
        message_type="text",
        is_group=False,
        send_enabled=False,
    )
    assert out["status"] == "would_reply"
    assert out["reply"] == wai.MSG_FINANCIAL_UNAVAILABLE


def test_comprovante_media_non_text_skipped_for_ai(monkeypatch):
    """Image/document inbound still skips text AI path (comprovante module owns media)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    wai.set_complete_override(lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no call")))
    out = decide_ai_path(text=None, message_type="image", is_group=False, send_enabled=False)
    assert out["reason"] == "non_text"
    assert out["processed"] is False


def test_system_prompt_no_longer_says_comprovantes_future():
    assert "etapa futura" not in wai.SYSTEM_PROMPT.lower()
    assert "Gestor" in wai.SYSTEM_PROMPT
