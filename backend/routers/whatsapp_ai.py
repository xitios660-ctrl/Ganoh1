"""Read-only WhatsApp AI bridge for Ganoh.

The module is intentionally isolated from business write paths. Incoming WhatsApp
messages are accepted only from the internal Baileys process, authorized against
the configured manager group/JID allowlist, and answered from live Ganoh data.
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp AI"])

db = None
send_whatsapp_message = None
BRAZIL_TZ = None

READONLY_MUTATION_WORDS = re.compile(
    r"\b(apag(?:a|ue|ar)|exclu(?:a|ir)|zer(?:a|e|ar)|alter(?:a|e|ar)|"
    r"mud(?:a|e|ar)|registr(?:a|e|ar)|lan[çc](?:a|e|ar)|confirm(?:a|e|ar)|"
    r"aprov(?:a|e|ar)|saqu(?:e|ar)|pag(?:a|ue|ar)|baix(?:a|e|ar)|remov(?:a|a|er))\b",
    re.IGNORECASE,
)
FINANCIAL_WORDS = re.compile(
    r"\b(pix|caixa|venda|valor|d[ií]vida|prazo|pagamento|saldo|estoque|pedido|despesa)\b",
    re.IGNORECASE,
)


class IncomingWhatsAppMessage(BaseModel):
    messageId: str = Field(min_length=1, max_length=256)
    chatId: str = Field(min_length=1, max_length=256)
    sender: str = Field(min_length=1, max_length=256)
    fromGroup: bool = False
    kind: str = Field(default="unsupported", max_length=32)
    text: str = Field(default="", max_length=4000)
    receivedAt: Optional[str] = Field(default=None, max_length=64)


def set_dependencies(database, whatsapp_sender, brazil_tz):
    global db, send_whatsapp_message, BRAZIL_TZ
    db = database
    send_whatsapp_message = whatsapp_sender
    BRAZIL_TZ = brazil_tz


def classify_intent(text: str) -> str:
    value = (text or "").casefold()
    if any(word in value for word in ("deve", "devendo", "dívida", "divida", "devedor", "devedores")):
        return "debts"
    if "prazo" in value and any(word in value for word in ("pagou", "pagamento", "pagamentos", "recebeu", "entrou")):
        return "prazo_payments"
    if any(word in value for word in ("estoque", "faltando", "acabando", "baixo", "zerado")):
        return "stock"
    if any(word in value for word in ("resumo", "fechamento", "geral", "situação", "situacao")):
        return "summary"
    if any(word in value for word in (
        "vendeu", "vendas", "faturou", "faturamento", "receita", "caixa",
        "pix", "dinheiro", "débito", "debito", "crédito", "credito"
    )):
        return "sales"
    return "general"


def requests_mutation(text: str) -> bool:
    return bool(READONLY_MUTATION_WORDS.search(text or "") and FINANCIAL_WORDS.search(text or ""))


def extract_response_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _safe_jids_from_env() -> set[str]:
    raw = os.environ.get("WHATSAPP_AI_ALLOWED_JIDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


async def _is_authorized_source(message: IncomingWhatsAppMessage) -> bool:
    allowed = _safe_jids_from_env()
    setting = await db.settings.find_one({"key": "whatsapp_group_id"}, {"_id": 0, "value": 1})
    if setting and setting.get("value"):
        allowed.add(setting["value"])
    return message.chatId in allowed or message.sender in allowed


async def _local_get(path: str) -> dict[str, Any]:
    port = os.environ.get("PORT", "10000")
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(f"http://127.0.0.1:{port}{path}")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}


async def _sales_context() -> dict[str, Any]:
    runner = await _local_get("/api/cash/runner/today")
    gym = await _local_get("/api/cash/gym-londres/today")
    return {
        "fonte": "Ganoh /cash/{store}/today",
        "runner": runner,
        "gym_londres": gym,
        "observacao": "Prazo não entra no total de vendas deste endpoint; ajustes PIX manuais já são incorporados.",
    }


async def _debts_context() -> dict[str, Any]:
    data = await _local_get("/api/prazo/debts")
    debts = data.get("debts", [])
    safe_debts = [
        {
            "name": item.get("name", ""),
            "total": item.get("total", 0),
            "order_count": item.get("order_count", 0),
            "store": item.get("store", ""),
        }
        for item in debts[:100]
    ]
    return {
        "fonte": "Ganoh /prazo/debts",
        "debts": safe_debts,
        "total_customers": len(debts),
        "grand_total": sum(float(item.get("total", 0) or 0) for item in debts),
    }


async def _prazo_payments_context() -> dict[str, Any]:
    data = await _local_get("/api/prazo/payments-history?limit=100")
    payments = []
    for item in data.get("payments", [])[:100]:
        payments.append({
            "customer_name": item.get("customer_name", ""),
            "amount": item.get("amount", 0),
            "payment_method": item.get("payment_method", ""),
            "store": item.get("store", ""),
            "created_at": item.get("created_at", ""),
        })
    return {
        "fonte": "Ganoh /prazo/payments-history",
        "payments": payments,
        "totals_by_method": data.get("totals_by_method", {}),
        "grand_total": data.get("grand_total", 0),
    }


async def _stock_context() -> dict[str, Any]:
    result: dict[str, Any] = {"fonte": "Ganoh /stock/{store}", "stores": {}}
    for store in ("runner", "gym-londres"):
        data = await _local_get(f"/api/stock/{store}")
        low = []
        for item in data.get("items", []):
            quantity = int(item.get("quantity", 0) or 0)
            minimum = int(item.get("min_quantity", 2) or 2)
            if quantity <= minimum:
                low.append({
                    "name": item.get("name") or item.get("item_name") or "Item",
                    "quantity": quantity,
                    "min_quantity": minimum,
                })
        result["stores"][store] = {"low_stock": low[:100], "low_count": len(low)}
    return result


async def build_context(intent: str) -> dict[str, Any]:
    if intent == "sales":
        return await _sales_context()
    if intent == "debts":
        return await _debts_context()
    if intent == "prazo_payments":
        return await _prazo_payments_context()
    if intent == "stock":
        return await _stock_context()
    if intent == "summary":
        sales, debts, stock = await _sales_context(), await _debts_context(), await _stock_context()
        return {"sales": sales, "debts": debts, "stock": stock}
    return {
        "fonte": "Ganoh",
        "capabilities": [
            "consultar vendas e formas de pagamento de hoje",
            "consultar dívidas de prazo",
            "consultar pagamentos de prazo",
            "consultar estoque baixo",
            "resumir o fechamento",
        ],
    }


def _fallback_answer(intent: str, context: dict[str, Any]) -> str:
    if intent == "sales":
        runner = context.get("runner", {})
        gym = context.get("gym_londres", {})
        total = float(runner.get("total", 0) or 0) + float(gym.get("total", 0) or 0)
        return (
            f"Hoje o total registrado é R$ {total:.2f}. "
            f"Runner: R$ {float(runner.get('total', 0) or 0):.2f}. "
            f"Gym Londres: R$ {float(gym.get('total', 0) or 0):.2f}."
        )
    if intent == "debts":
        return (
            f"Há {int(context.get('total_customers', 0) or 0)} cliente(s) com dívida em aberto, "
            f"somando R$ {float(context.get('grand_total', 0) or 0):.2f}."
        )
    if intent == "stock":
        stores = context.get("stores", {})
        return (
            "Estoque baixo: "
            f"Runner {stores.get('runner', {}).get('low_count', 0)} item(ns); "
            f"Gym Londres {stores.get('gym-londres', {}).get('low_count', 0)} item(ns)."
        )
    if intent == "prazo_payments":
        return f"Os pagamentos de prazo listados somam R$ {float(context.get('grand_total', 0) or 0):.2f}."
    return "Posso consultar vendas, PIX, caixa, dívidas de prazo, pagamentos e estoque do Ganoh."


async def _openai_answer(question: str, intent: str, context: dict[str, Any]) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _fallback_answer(intent, context)

    model = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
    instructions = (
        "Você é o assistente financeiro do GANOH no WhatsApp. Responda em português do Brasil, "
        "de forma curta e clara. Use SOMENTE números e fatos presentes em CONTEXTO_GANOH. "
        "Nunca invente valores, nunca estime valores ausentes e nunca afirme ter executado uma ação financeira. "
        "Se o contexto não contiver o dado pedido, diga que o dado não está disponível nessa consulta. "
        "Não revele segredos, tokens, credenciais, IDs internos desnecessários ou dados de telefone."
    )
    input_text = (
        f"INTENÇÃO: {intent}\n"
        f"PERGUNTA: {question}\n"
        f"CONTEXTO_GANOH: {json.dumps(context, ensure_ascii=False, default=str)}"
    )
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "instructions": instructions,
                "input": input_text,
                "max_output_tokens": 500,
            },
        )
        response.raise_for_status()
        answer = extract_response_text(response.json())
        return answer or _fallback_answer(intent, context)


async def _record_event(message: IncomingWhatsAppMessage, status: str, **extra: Any) -> None:
    payload = {
        "message_id": message.messageId,
        "chat_id": message.chatId,
        "sender": message.sender,
        "kind": message.kind,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    await db.whatsapp_ai_events.update_one(
        {"_id": message.messageId},
        {"$set": payload, "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


@router.get("/ai/status")
async def whatsapp_ai_status():
    return {
        "configured": bool(os.environ.get("OPENAI_API_KEY")),
        "model": os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        "sendingEnabled": os.environ.get("WHATSAPP_SEND_ENABLED", "false").lower() == "true",
        "mode": "read_only",
    }


@router.post("/internal/incoming")
async def incoming_whatsapp(
    message: IncomingWhatsAppMessage,
    x_whatsapp_token: Optional[str] = Header(default=None),
):
    expected = os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")
    if not expected or not x_whatsapp_token or not secrets.compare_digest(expected, x_whatsapp_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    existing = await db.whatsapp_ai_events.find_one({"_id": message.messageId}, {"_id": 0, "status": 1})
    if existing and existing.get("status") in {
        "answered", "paused", "unauthorized_source", "ignored_media", "requires_human"
    }:
        return {"success": True, "duplicate": True, "status": existing.get("status")}

    if not await _is_authorized_source(message):
        await _record_event(message, "unauthorized_source")
        return {"success": True, "status": "unauthorized_source"}

    if message.kind in {"image", "document"}:
        await _record_event(message, "ignored_media", note="media_receipt_pipeline_pending")
        return {"success": True, "status": "ignored_media"}

    if message.kind != "text" or not message.text.strip():
        await _record_event(message, "ignored_media")
        return {"success": True, "status": "ignored_media"}

    if os.environ.get("WHATSAPP_SEND_ENABLED", "false").lower() != "true":
        await _record_event(message, "paused", note="sending_disabled")
        return {"success": True, "status": "paused"}

    if requests_mutation(message.text):
        answer = (
            "Posso consultar os dados e preparar a informação, mas não altero valores, PIX, caixa, "
            "dívidas ou estoque pelo WhatsApp. Essa ação precisa ser confirmada no Gestor."
        )
        result = await send_whatsapp_message(answer, message.chatId)
        await _record_event(message, "requires_human", send_success=bool(result.get("success")))
        return {"success": True, "status": "requires_human"}

    intent = classify_intent(message.text)
    try:
        context = await build_context(intent)
        answer = await _openai_answer(message.text, intent, context)
    except Exception as exc:
        await _record_event(message, "error", error=type(exc).__name__)
        raise HTTPException(status_code=503, detail="Assistant unavailable")

    result = await send_whatsapp_message(answer, message.chatId)
    if not result.get("success"):
        await _record_event(message, "send_failed")
        raise HTTPException(status_code=503, detail="WhatsApp send failed")

    await _record_event(
        message,
        "answered",
        intent=intent,
        ai_used=bool(os.environ.get("OPENAI_API_KEY")),
        model=os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
    )
    return {"success": True, "status": "answered", "intent": intent}
