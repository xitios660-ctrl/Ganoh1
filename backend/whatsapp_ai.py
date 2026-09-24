"""
Secure OpenAI integration for GANOH WhatsApp AI (ETAPA 6 + 7).

- Keys only from env: OPENAI_API_KEY (required for replies), OPENAI_MODEL (default gpt-4o-mini)
- Never logs API keys or full customer message bodies
- Never invents financial numbers; ETAPA 7 injects official Mongo facts into the prompt
- Sensitive mutations require Gestor confirmation (stub — never executed here)
- Optional EMERGENT_LLM_KEY only affects is_configured() / status fallback — chat path prefers OPENAI_API_KEY

Design (ETAPA 7): intent detect + read-only Mongo fetch + facts in prompt (not OpenAI tools).
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("whatsapp_ai")

DEFAULT_MODEL = "gpt-4o-mini"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MAX_USER_CHARS = 4000
MAX_REPLY_CHARS = 2000

MSG_UNAVAILABLE = (
    "A assistente de IA ainda não está configurada. "
    "Peça ao Gestor para definir a chave OPENAI_API_KEY."
)
MSG_ERROR = (
    "Não consegui processar sua mensagem agora. "
    "Tente novamente em instantes ou fale com o Gestor."
)
MSG_FINANCIAL_NO_DATA = (
    "Consultei o sistema e não há dados financeiros para esse pedido "
    "neste momento. Não invento números."
)
MSG_FINANCIAL_UNAVAILABLE = (
    "Não consegui obter os dados financeiros do sistema agora. "
    "Não invento números — tente de novo ou confira no Gestor."
)
# Kept for backward-compatible imports/tests naming
MSG_FINANCIAL_STUB = MSG_FINANCIAL_UNAVAILABLE
MSG_SENSITIVE_STUB = (
    "Essa ação é sensível e precisa da confirmação do Gestor. "
    "Eu preparei a intenção, mas não executo sozinho: apagar vendas, "
    "alterar valores, confirmar PIX, registrar saques, alterar/zerar dívidas, "
    "apagar clientes, alterar caixa/estoque ou apagar histórico."
)

SYSTEM_PROMPT = """Você é o assistente operacional e financeiro do GANOH via WhatsApp.
Regras obrigatórias:
1. Responda sempre em português do Brasil, de forma objetiva e educada.
2. NUNCA invente números, saldos, vendas, dívidas, estoque, PIX ou qualquer valor financeiro.
3. Se a mensagem incluir um bloco [DADOS OFICIAIS DO SISTEMA ...], use SOMENTE esses valores para responder. Não some, estime nem complete lacunas com números inventados.
4. Se os dados oficiais indicarem falha ou ausência de registros, diga isso claramente — sem inventar.
5. Você NÃO pode sozinho: apagar vendas, alterar valores, confirmar PIX, registrar saques, alterar dívidas, zerar dívidas, apagar clientes, alterar caixa/estoque, apagar histórico.
6. Ações sensíveis: explique que precisa da confirmação do Gestor (não execute).
7. Não peça nem revele chaves, tokens, senhas ou dados de autenticação.
8. Não invente status de pedidos ou comprovantes; comprovantes são etapa futura.
"""

_FINANCIAL_RE = re.compile(
    r"\b("
    r"saldo|venda|vendas|faturamento|caixa|lucro|preju[ií]zo|"
    r"d[ií]vida|dividas|a\s*receber|a\s*pagar|prazo|"
    r"pix|estoque|retirada|saque|sangria|fechamento|"
    r"relat[oó]rio|quanto\s+(fez|vendeu|entrou|saiu)|"
    r"r\$|reais?"
    r")\b",
    re.IGNORECASE,
)

_SENSITIVE_RE = re.compile(
    r"\b("
    r"apaga(r)?|delet(a|ar)|excluir|zera(r)?|limpa(r)?\s+(d[ií]vida|hist[oó]rico|caixa)|"
    r"confirma(r)?\s+pix|registrar?\s+saque|altera(r)?\s+(valor|d[ií]vida|venda|estoque|caixa)|"
    r"remover?\s+cliente"
    r")\b",
    re.IGNORECASE,
)

# Injected completer for unit tests: (messages, model, api_key) -> reply text
_complete_override: Optional[Callable[[list, str, str], str]] = None


def _env_key(name: str) -> Optional[str]:
    value = (os.environ.get(name) or "").strip()
    return value or None


def get_model() -> str:
    model = _env_key("OPENAI_MODEL") or DEFAULT_MODEL
    return model


def is_openai_ready() -> bool:
    """True when WhatsApp AI can call OpenAI (OPENAI_API_KEY present)."""
    return bool(_env_key("OPENAI_API_KEY"))


def is_configured() -> bool:
    """
    Status boolean for Gestor UI.
    Prefer OPENAI_API_KEY; EMERGENT_LLM_KEY counts only as fallback presence.
    """
    if is_openai_ready():
        return True
    return bool(_env_key("EMERGENT_LLM_KEY"))


def get_ai_status() -> str:
    """Non-secret status: active | pending | unavailable."""
    if is_openai_ready():
        return "active"
    if _env_key("EMERGENT_LLM_KEY"):
        return "pending"
    return "unavailable"


def looks_financial(text: str) -> bool:
    if not text:
        return False
    return bool(_FINANCIAL_RE.search(text))


def looks_sensitive(text: str) -> bool:
    if not text:
        return False
    return bool(_SENSITIVE_RE.search(text))


def _truncate(text: Optional[str], limit: int) -> str:
    if not isinstance(text, str):
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _default_openai_complete(messages: list, model: str, api_key: str) -> str:
    """
    Call OpenAI Chat Completions via stdlib urllib (no key logging).
    Prefer litellm when installed (optional).
    """
    try:
        import litellm  # type: ignore

        response = litellm.completion(
            model=model if "/" in model else f"openai/{model}",
            messages=messages,
            api_key=api_key,
            timeout=30,
        )
        content = response["choices"][0]["message"]["content"]
        return _truncate(content if isinstance(content, str) else str(content), MAX_REPLY_CHARS)
    except ImportError:
        pass
    except Exception as exc:
        # Fall through to urllib; log only exception class/name
        logger.warning("litellm completion failed: %s", type(exc).__name__)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 500,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        return _truncate(content if isinstance(content, str) else str(content), MAX_REPLY_CHARS)
    except urllib.error.HTTPError as exc:
        logger.warning("openai http error: %s", getattr(exc, "code", "http"))
        raise
    except Exception as exc:
        logger.warning("openai request failed: %s", type(exc).__name__)
        raise


def set_complete_override(fn: Optional[Callable[[list, str, str], str]]) -> None:
    """Test helper — inject mock completer; pass None to clear."""
    global _complete_override
    _complete_override = fn


def _reply_from_finance_facts(facts, user_text: str, context: Optional[Dict[str, Any]]) -> str:
    """Call OpenAI with official facts injected; never invent beyond facts."""
    api_key = _env_key("OPENAI_API_KEY")
    if not api_key:
        return MSG_UNAVAILABLE

    if facts is None:
        return MSG_FINANCIAL_UNAVAILABLE
    if not getattr(facts, "ok", False):
        return MSG_FINANCIAL_UNAVAILABLE
    if getattr(facts, "empty", False):
        # Still allow AI to phrase "sem dados" using the facts block, if key present
        pass

    model = get_model()
    context = context or {}
    facts_block = facts.to_prompt_block() if hasattr(facts, "to_prompt_block") else str(facts)
    system = SYSTEM_PROMPT + "\n\n" + facts_block
    if context.get("isGroup"):
        system += "\nContexto: mensagem de grupo."
    if context.get("pushName"):
        system += "\nHá um nome de remetente disponível; use com cautela."

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    completer = _complete_override or _default_openai_complete
    try:
        reply = completer(messages, model, api_key)
        reply = _truncate(reply, MAX_REPLY_CHARS)
        return reply or MSG_ERROR
    except Exception:
        return MSG_ERROR


def chat_reply(user_text: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate a WhatsApp reply. Sync API for unit testing.

    Financial path (ETAPA 7):
      - If context contains pre-fetched `finance_facts`, inject them and call the model.
      - If financial but no facts provided, return MSG_FINANCIAL_UNAVAILABLE
        (async path `achat_reply` fetches from Mongo).
    Sensitive mutations always return MSG_SENSITIVE_STUB (never executed).
    """
    text = _truncate(user_text, MAX_USER_CHARS)
    if not text:
        return MSG_ERROR

    if looks_sensitive(text):
        return MSG_SENSITIVE_STUB

    context = context or {}
    finance_facts = context.get("finance_facts")

    if looks_financial(text):
        if finance_facts is not None:
            return _reply_from_finance_facts(finance_facts, text, context)
        return MSG_FINANCIAL_UNAVAILABLE

    api_key = _env_key("OPENAI_API_KEY")
    if not api_key:
        return MSG_UNAVAILABLE

    model = get_model()
    extra_bits = []
    if context.get("isGroup"):
        extra_bits.append("Contexto: mensagem de grupo.")
    if context.get("pushName"):
        extra_bits.append("Há um nome de remetente disponível; use com cautela.")
    system = SYSTEM_PROMPT
    if extra_bits:
        system = system + "\n" + " ".join(extra_bits)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": text},
    ]

    completer = _complete_override or _default_openai_complete
    try:
        reply = completer(messages, model, api_key)
        reply = _truncate(reply, MAX_REPLY_CHARS)
        return reply or MSG_ERROR
    except Exception:
        return MSG_ERROR


async def achat_reply(user_text: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Async wrapper for FastAPI inbound path.
    For financial questions, fetches read-only Mongo facts (ETAPA 7) before completing.
    """
    text = _truncate(user_text, MAX_USER_CHARS)
    context = dict(context or {})

    if text and looks_sensitive(text):
        return MSG_SENSITIVE_STUB

    if text and looks_financial(text) and context.get("finance_facts") is None:
        try:
            import whatsapp_finance as wf

            facts = await wf.fetch_facts_for_text(text, db=context.get("db"))
            context["finance_facts"] = facts
        except Exception as exc:
            logger.warning("finance fetch failed: %s", type(exc).__name__)
            context["finance_facts"] = None

    return chat_reply(text, context=context)


# Exported constants for tests
__all__ = [
    "SYSTEM_PROMPT",
    "DEFAULT_MODEL",
    "MSG_UNAVAILABLE",
    "MSG_ERROR",
    "MSG_FINANCIAL_STUB",
    "MSG_FINANCIAL_NO_DATA",
    "MSG_FINANCIAL_UNAVAILABLE",
    "MSG_SENSITIVE_STUB",
    "is_configured",
    "is_openai_ready",
    "get_ai_status",
    "get_model",
    "looks_financial",
    "looks_sensitive",
    "chat_reply",
    "achat_reply",
    "set_complete_override",
]
