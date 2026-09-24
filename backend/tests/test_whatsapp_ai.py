"""Unit tests for WhatsApp AI module (ETAPA 6) — no real OpenAI / Mongo."""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import whatsapp_ai as wai


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    wai.set_complete_override(None)
    yield
    wai.set_complete_override(None)


def test_missing_key_not_openai_ready():
    assert wai.is_openai_ready() is False
    assert wai.is_configured() is False
    assert wai.get_ai_status() == "unavailable"


def test_emergent_fallback_configured_pending(monkeypatch):
    monkeypatch.setenv("EMERGENT_LLM_KEY", "emergent-test-not-a-real-secret")
    assert wai.is_configured() is True
    assert wai.is_openai_ready() is False
    assert wai.get_ai_status() == "pending"


def test_openai_key_active(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-secret")
    assert wai.is_openai_ready() is True
    assert wai.is_configured() is True
    assert wai.get_ai_status() == "active"
    assert wai.get_model() == wai.DEFAULT_MODEL


def test_model_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    assert wai.get_model() == "gpt-4o-mini"


def test_system_prompt_never_invent_numbers():
    prompt = wai.SYSTEM_PROMPT.lower()
    assert "nunca invente" in prompt or "nunca invent" in prompt
    assert "números" in prompt or "numeros" in prompt or "número" in prompt
    assert "confirmação do gestor" in prompt or "confirmacao do gestor" in prompt


def test_chat_reply_missing_key_safe_message():
    reply = wai.chat_reply("Olá, tudo bem?")
    assert reply == wai.MSG_UNAVAILABLE
    assert "OPENAI_API_KEY" in reply or "configurada" in reply.lower()


def test_chat_reply_financial_without_facts_no_openai(monkeypatch):
    """Sync path without pre-fetched facts must not call OpenAI or invent numbers."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    called = {"n": 0}

    def boom(*_a, **_k):
        called["n"] += 1
        raise AssertionError("must not call OpenAI without finance facts")

    wai.set_complete_override(boom)
    reply = wai.chat_reply("Qual o saldo do caixa de hoje?")
    assert called["n"] == 0
    assert reply == wai.MSG_FINANCIAL_UNAVAILABLE
    assert "invent" in reply.lower() or "números" in reply.lower() or "numeros" in reply.lower()


def test_chat_reply_sensitive_stub(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(*_a, **_k):
        raise AssertionError("must not call OpenAI for sensitive stub")

    wai.set_complete_override(boom)
    reply = wai.chat_reply("Apagar venda 123 e zerar dívida do cliente")
    assert reply == wai.MSG_SENSITIVE_STUB
    assert "Gestor" in reply


def test_chat_reply_mock_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    def fake(messages, model, api_key):
        assert model == "gpt-4o-mini"
        assert api_key == "sk-test"
        assert messages[0]["role"] == "system"
        assert "NUNCA invente" in messages[0]["content"] or "nunca invente" in messages[0]["content"].lower()
        assert messages[1]["content"] == "Bom dia"
        # Ensure key never appears in system prompt
        assert "sk-test" not in messages[0]["content"]
        return "Olá! Como posso ajudar no GANOH?"

    wai.set_complete_override(fake)
    reply = wai.chat_reply("Bom dia")
    assert "GANOH" in reply


def test_chat_reply_api_failure_graceful(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def fail(*_a, **_k):
        raise RuntimeError("network")

    wai.set_complete_override(fail)
    reply = wai.chat_reply("Oi")
    assert reply == wai.MSG_ERROR


def test_looks_financial_helpers():
    assert wai.looks_financial("me diga o faturamento")
    assert wai.looks_financial("saldo do caixa")
    assert not wai.looks_financial("bom dia, tudo bem?")


def test_never_hardcodes_secrets_in_module_source():
    src = Path(wai.__file__).read_text(encoding="utf-8")
    assert "sk-proj-" not in src
    assert "sk-live-" not in src
    assert "OPENAI_API_KEY" in src
    assert "OPENAI_MODEL" in src
    assert "_env_key" in src


def test_sensitive_detection_pt():
    assert wai.looks_sensitive("confirma pix agora")
    assert wai.looks_sensitive("apagar venda")
    assert not wai.looks_sensitive("bom dia")
