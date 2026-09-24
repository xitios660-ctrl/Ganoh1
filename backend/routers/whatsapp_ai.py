"""WhatsApp + OpenAI bridge for Ganoh.

Financial questions are read-only. Receipt media can be analyzed, but a manager
must explicitly confirm a matching pending PIX order before any financial state
changes. WhatsApp media is retained encrypted by the loopback Baileys service.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp AI"])
security = HTTPBasic()

db = None
send_whatsapp_message = None
BRAZIL_TZ = None
verify_manager = None

READONLY_MUTATION_WORDS = re.compile(
    r"\b(apag(?:a|ue|ar)|exclu(?:a|ir)|zer(?:a|e|ar)|alter(?:a|e|ar)|"
    r"mud(?:a|e|ar)|registr(?:a|e|ar)|lan[çc](?:a|e|ar)|confirm(?:a|e|ar)|"
    r"aprov(?:a|e|ar)|saqu(?:e|ar)|pag(?:a|ue|ar)|baix(?:a|e|ar)|remov(?:a|er))\b",
    re.IGNORECASE,
)
FINANCIAL_WORDS = re.compile(
    r"\b(pix|caixa|venda|valor|d[ií]vida|prazo|pagamento|saldo|estoque|pedido|despesa)\b",
    re.IGNORECASE,
)
FINAL_EVENT_STATUSES = {
    "answered",
    "paused",
    "unauthorized_source",
    "ignored_media",
    "requires_human",
    "receipt_pending_review",
    "receipt_duplicate_suspected",
    "receipt_media_missing",
}


class IncomingWhatsAppMessage(BaseModel):
    messageId: str = Field(min_length=1, max_length=256)
    chatId: str = Field(min_length=1, max_length=256)
    sender: str = Field(min_length=1, max_length=256)
    fromGroup: bool = False
    kind: str = Field(default="unsupported", max_length=32)
    text: str = Field(default="", max_length=4000)
    mimeType: str = Field(default="", max_length=120)
    fileName: str = Field(default="", max_length=180)
    mediaBase64: str = ""
    receivedAt: Optional[str] = Field(default=None, max_length=64)


class ReceiptReview(BaseModel):
    action: Literal["confirm", "reject", "correct"]
    order_id: Optional[str] = Field(default=None, max_length=128)
    amount: Optional[float] = Field(default=None, gt=0, allow_inf_nan=False)
    payer_name: Optional[str] = Field(default=None, max_length=180)
    notes: Optional[str] = Field(default=None, max_length=500)


def set_dependencies(database, whatsapp_sender, brazil_tz, manager_verifier=None):
    global db, send_whatsapp_message, BRAZIL_TZ, verify_manager
    db = database
    send_whatsapp_message = whatsapp_sender
    BRAZIL_TZ = brazil_tz
    verify_manager = manager_verifier


async def require_manager(credentials: HTTPBasicCredentials = Depends(security)):
    if verify_manager is None:
        raise HTTPException(status_code=503, detail="Manager authentication unavailable")
    return await verify_manager(credentials)


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


def parse_json_object(text: str) -> dict[str, Any]:
    value = (text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s*```$", "", value)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No JSON object returned")
    parsed = json.loads(value[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Receipt analysis is not an object")
    return parsed


def _safe_jids_from_env() -> set[str]:
    raw = os.environ.get("WHATSAPP_AI_ALLOWED_JIDS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


async def _is_authorized_source(message: IncomingWhatsAppMessage) -> bool:
    allowed = _safe_jids_from_env()
    setting = await db.settings.find_one({"key": "whatsapp_group_id"}, {"_id": 0, "value": 1})
    if setting and setting.get("value"):
        allowed.add(setting["value"])
    return message.chatId in allowed or message.sender in allowed


def _jid_phone(jid: str) -> str:
    local = (jid or "").split("@", 1)[0]
    return "".join(ch for ch in local if ch.isdigit())


async def _is_known_customer_sender(message: IncomingWhatsAppMessage) -> bool:
    sender_digits = _jid_phone(message.sender)
    if len(sender_digits) < 10:
        return False
    customers = await db.prazo_customers.find(
        {"phone": {"$nin": [None, ""]}},
        {"_id": 0, "phone": 1},
    ).to_list(1500)
    for customer in customers:
        phone_digits = "".join(ch for ch in str(customer.get("phone", "")) if ch.isdigit())
        if not phone_digits:
            continue
        if len(phone_digits) in (10, 11):
            phone_digits = "55" + phone_digits
        if sender_digits == phone_digits or sender_digits.endswith(phone_digits) or phone_digits.endswith(sender_digits):
            return True
    return False


async def _receipt_rate_limited(message: IncomingWhatsAppMessage) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    count = await db.whatsapp_receipts.count_documents({
        "sender": message.sender,
        "created_at": {"$gte": cutoff},
    })
    return count >= 10


def _local_url(path: str) -> str:
    return f"http://127.0.0.1:{os.environ.get('PORT', '10000')}{path}"


async def _local_get(path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        response = await client.get(_local_url(path))
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
    payments = [
        {
            "customer_name": item.get("customer_name", ""),
            "amount": item.get("amount", 0),
            "payment_method": item.get("payment_method", ""),
            "store": item.get("store", ""),
            "created_at": item.get("created_at", ""),
        }
        for item in data.get("payments", [])[:100]
    ]
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
        sales = await _sales_context()
        debts = await _debts_context()
        stock = await _stock_context()
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


async def _openai_request(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


async def _openai_answer(question: str, intent: str, context: dict[str, Any]) -> str:
    if not os.environ.get("OPENAI_API_KEY"):
        return _fallback_answer(intent, context)
    model = os.environ.get("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
    payload = {
        "model": model,
        "instructions": (
            "Você é o assistente financeiro do GANOH no WhatsApp. Responda em português do Brasil, "
            "de forma curta e clara. Use SOMENTE números e fatos presentes em CONTEXTO_GANOH. "
            "Nunca invente valores, nunca estime valores ausentes e nunca afirme ter executado uma ação financeira. "
            "Se o contexto não contiver o dado pedido, diga que o dado não está disponível nessa consulta. "
            "Não revele segredos, tokens, credenciais, IDs internos desnecessários ou dados de telefone."
        ),
        "input": (
            f"INTENÇÃO: {intent}\n"
            f"PERGUNTA: {question}\n"
            f"CONTEXTO_GANOH: {json.dumps(context, ensure_ascii=False, default=str)}"
        ),
        "max_output_tokens": 500,
    }
    answer = extract_response_text(await _openai_request(payload))
    return answer or _fallback_answer(intent, context)


def _decode_media(message: IncomingWhatsAppMessage) -> bytes:
    if not message.mediaBase64:
        raise ValueError("Missing media")
    try:
        data = base64.b64decode(message.mediaBase64, validate=True)
    except Exception as exc:
        raise ValueError("Invalid media encoding") from exc
    if not data or len(data) > 8 * 1024 * 1024:
        raise ValueError("Invalid media size")
    return data


async def _fetch_receipt_media(receipt_id: str) -> dict[str, Any]:
    token = os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")
    if not token:
        raise HTTPException(status_code=503, detail="WhatsApp internal token unavailable")
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"http://127.0.0.1:8002/media/{receipt_id}",
            headers={"x-whatsapp-token": token},
        )
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Receipt media expired or unavailable")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Receipt media service unavailable")
    data = response.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=503, detail="Invalid receipt media response")
    return data


def _pending_receipt_analysis() -> dict[str, Any]:
    return {
        "amount": None,
        "payer_name": None,
        "transaction_date": None,
        "transaction_time": None,
        "reference": None,
        "bank": None,
        "confidence": 0,
        "analysis_status": "pending_manager_analysis",
    }


async def _analyze_receipt(message: IncomingWhatsAppMessage) -> tuple[dict[str, Any], str]:
    raw = _decode_media(message)
    media_hash = hashlib.sha256(raw).hexdigest()
    if not os.environ.get("OPENAI_API_KEY"):
        return {
            "amount": None,
            "payer_name": None,
            "transaction_date": None,
            "transaction_time": None,
            "reference": None,
            "bank": None,
            "confidence": 0,
            "analysis_status": "ai_not_configured",
        }, media_hash

    model = os.environ.get("OPENAI_VISION_MODEL", os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"))
    prompt = (
        "Analise este comprovante financeiro. Extraia apenas o que estiver visível. "
        "Retorne SOMENTE JSON com: amount (número ou null), payer_name (string ou null), "
        "transaction_date (string ou null), transaction_time (string ou null), "
        "reference (string ou null), bank (string ou null), confidence (0 a 1). "
        "Não conclua que o pagamento é válido e não invente campos ausentes."
    )
    if message.mimeType.startswith("image/"):
        content = [
            {"type": "input_text", "text": prompt},
            {
                "type": "input_image",
                "image_url": f"data:{message.mimeType};base64,{message.mediaBase64}",
                "detail": "high",
            },
        ]
    elif message.mimeType == "application/pdf":
        content = [
            {"type": "input_text", "text": prompt},
            {
                "type": "input_file",
                "filename": message.fileName or "comprovante.pdf",
                "file_data": message.mediaBase64,
            },
        ]
    else:
        raise ValueError("Unsupported receipt media type")

    response = await _openai_request({
        "model": model,
        "input": [{"role": "user", "content": content}],
        "max_output_tokens": 500,
    })
    analysis = parse_json_object(extract_response_text(response))
    analysis["analysis_status"] = "analyzed"
    return analysis, media_hash


async def _find_candidate_orders(amount: Any) -> list[dict[str, Any]]:
    try:
        numeric = float(amount)
    except (TypeError, ValueError):
        return []
    orders = await db.orders.find(
        {
            "payment_method": "pix",
            "status": "pending_payment",
            "total": {"$gte": numeric - 0.01, "$lte": numeric + 0.01},
        },
        {
            "_id": 0,
            "id": 1,
            "store": 1,
            "customer_name": 1,
            "order_number": 1,
            "total": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).to_list(20)
    return orders


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


async def _store_receipt(
    message: IncomingWhatsAppMessage,
    analysis: dict[str, Any],
    media_hash: str,
    candidates: list[dict[str, Any]],
) -> str:
    duplicate = await db.whatsapp_receipts.find_one(
        {"media_hash": media_hash, "_id": {"$ne": message.messageId}, "status": {"$ne": "rejected"}},
        {"_id": 1, "status": 1},
    )
    status = "duplicate_suspected" if duplicate else "pending_review"
    await db.whatsapp_receipts.update_one(
        {"_id": message.messageId},
        {
            "$set": {
                "message_id": message.messageId,
                "chat_id": message.chatId,
                "sender": message.sender,
                "mime_type": message.mimeType,
                "file_name": message.fileName,
                "media_hash": media_hash,
                "analysis": analysis,
                "candidate_orders": candidates,
                "status": status,
                "duplicate_of": duplicate.get("_id") if duplicate else None,
                "source": "whatsapp_receipt",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )
    return status


@router.get("/ai/status")
async def whatsapp_ai_status():
    return {
        "configured": bool(os.environ.get("OPENAI_API_KEY")),
        "model": os.environ.get("OPENAI_MODEL", "gpt-5.6-luna"),
        "sendingEnabled": os.environ.get("WHATSAPP_SEND_ENABLED", "false").lower() == "true",
        "mode": "read_only",
    }


@router.get("/receipts", dependencies=[Depends(require_manager)])
async def list_whatsapp_receipts(limit: int = 50):
    limit = max(1, min(limit, 100))
    docs = await db.whatsapp_receipts.find(
        {"status": {"$in": ["pending_review", "duplicate_suspected"]}},
        {"media_hash": 0},
    ).sort("created_at", -1).to_list(limit)
    for item in docs:
        item["id"] = str(item.pop("_id"))
    return {"receipts": docs}


@router.get("/receipts/{receipt_id}/media", dependencies=[Depends(require_manager)])
async def get_whatsapp_receipt_media(receipt_id: str):
    return await _fetch_receipt_media(receipt_id)


@router.post("/receipts/{receipt_id}/analyze", dependencies=[Depends(require_manager)])
async def analyze_whatsapp_receipt(receipt_id: str):
    receipt = await db.whatsapp_receipts.find_one({"_id": receipt_id})
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="OpenAI is not configured")

    media = await _fetch_receipt_media(receipt_id)
    message = IncomingWhatsAppMessage(
        messageId=receipt_id,
        chatId=receipt.get("chat_id", ""),
        sender=receipt.get("sender", ""),
        fromGroup=bool(receipt.get("from_group")),
        kind="document" if media.get("mimeType") == "application/pdf" else "image",
        text="",
        mimeType=media.get("mimeType", ""),
        fileName=media.get("fileName", ""),
        mediaBase64=media.get("data", ""),
        receivedAt=receipt.get("received_at"),
    )
    try:
        analysis, media_hash = await _analyze_receipt(message)
    except Exception as exc:
        await db.whatsapp_receipts.update_one(
            {"_id": receipt_id},
            {"$set": {
                "analysis.analysis_status": "analysis_failed",
                "analysis_error": type(exc).__name__,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        raise HTTPException(status_code=503, detail="Receipt analysis unavailable")

    candidates = await _find_candidate_orders(analysis.get("amount"))
    duplicate = await db.whatsapp_receipts.find_one({
        "media_hash": media_hash,
        "_id": {"$ne": receipt_id},
        "status": {"$ne": "rejected"},
    }, {"_id": 1})
    status = "duplicate_suspected" if duplicate else "pending_review"
    await db.whatsapp_receipts.update_one(
        {"_id": receipt_id},
        {"$set": {
            "analysis": analysis,
            "media_hash": media_hash,
            "candidate_orders": candidates,
            "status": status,
            "duplicate_of": duplicate.get("_id") if duplicate else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"success": True, "status": status, "candidate_count": len(candidates)}


@router.post("/receipts/{receipt_id}/review", dependencies=[Depends(require_manager)])
async def review_whatsapp_receipt(receipt_id: str, review: ReceiptReview):
    receipt = await db.whatsapp_receipts.find_one({"_id": receipt_id})
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if receipt.get("status") == "confirmed":
        return {"success": True, "status": "confirmed", "duplicate": True}

    now = datetime.now(timezone.utc).isoformat()
    analysis = dict(receipt.get("analysis") or {})
    if review.amount is not None:
        analysis["amount"] = review.amount
    if review.payer_name is not None:
        analysis["payer_name"] = review.payer_name

    if review.action == "reject":
        await db.whatsapp_receipts.update_one(
            {"_id": receipt_id},
            {"$set": {"status": "rejected", "analysis": analysis, "notes": review.notes or "", "reviewed_at": now, "updated_at": now}},
        )
        return {"success": True, "status": "rejected"}

    if review.action == "correct":
        candidates = await _find_candidate_orders(analysis.get("amount"))
        selected_order_id = review.order_id
        if selected_order_id and not any(item.get("id") == selected_order_id for item in candidates):
            selected_order_id = None
        await db.whatsapp_receipts.update_one(
            {"_id": receipt_id},
            {"$set": {
                "status": "pending_review",
                "analysis": analysis,
                "candidate_orders": candidates,
                "selected_order_id": selected_order_id,
                "notes": review.notes or "",
                "updated_at": now,
            }},
        )
        return {"success": True, "status": "pending_review", "candidate_count": len(candidates)}

    order_id = review.order_id or receipt.get("selected_order_id")
    if not order_id:
        raise HTTPException(status_code=400, detail="Select an order before confirming")

    order = await db.orders.find_one(
        {"id": order_id, "payment_method": "pix"},
        {"_id": 0, "id": 1, "store": 1, "status": 1, "total": 1},
    )
    if not order:
        raise HTTPException(status_code=404, detail="PIX order not found")
    if order.get("status") != "pending_payment":
        raise HTTPException(status_code=409, detail="Order is no longer pending payment")

    amount = analysis.get("amount")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Receipt amount must be reviewed before confirmation")
    if abs(amount - float(order.get("total", 0) or 0)) > 0.01:
        raise HTTPException(status_code=409, detail="Receipt amount does not match the selected order")

    duplicate_confirmed = await db.whatsapp_receipts.find_one({
        "media_hash": receipt.get("media_hash"),
        "_id": {"$ne": receipt_id},
        "status": "confirmed",
    })
    if duplicate_confirmed:
        raise HTTPException(status_code=409, detail="This receipt was already confirmed")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            _local_url(f"/api/orders/{order['store']}/{order_id}/approve-payment"),
            json={"approved": True},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=409, detail="Order approval failed")

    await db.orders.update_one(
        {"id": order_id, "store": order["store"]},
        {"$set": {
            "payment_origin": "whatsapp_receipt",
            "whatsapp_receipt_id": receipt_id,
            "pix_payer_name": analysis.get("payer_name") or "",
            "whatsapp_receipt_analysis": analysis,
            "updated_at": now,
        }},
    )
    await db.whatsapp_receipts.update_one(
        {"_id": receipt_id},
        {"$set": {
            "status": "confirmed",
            "analysis": analysis,
            "selected_order_id": order_id,
            "confirmed_order_id": order_id,
            "notes": review.notes or "",
            "reviewed_at": now,
            "updated_at": now,
        }},
    )
    return {"success": True, "status": "confirmed", "order_id": order_id}


@router.post("/internal/incoming")
async def incoming_whatsapp(
    message: IncomingWhatsAppMessage,
    x_whatsapp_token: Optional[str] = Header(default=None),
):
    expected = os.environ.get("WHATSAPP_INTERNAL_TOKEN", "")
    if not expected or not x_whatsapp_token or not secrets.compare_digest(expected, x_whatsapp_token):
        raise HTTPException(status_code=401, detail="Unauthorized")

    existing = await db.whatsapp_ai_events.find_one({"_id": message.messageId}, {"_id": 0, "status": 1})
    if existing and existing.get("status") in FINAL_EVENT_STATUSES:
        return {"success": True, "duplicate": True, "status": existing.get("status")}

    authorized_source = await _is_authorized_source(message)

    if message.kind in {"image", "document"}:
        # Private senders may submit receipts, but financial Q&A remains manager-only.
        # Untrusted groups are ignored to avoid turning group spam into receipt processing.
        if message.fromGroup and not authorized_source:
            await _record_event(message, "unauthorized_source")
            return {"success": True, "status": "unauthorized_source"}
        if await _receipt_rate_limited(message):
            await _record_event(message, "rate_limited")
            return {"success": True, "status": "rate_limited"}
        if not message.mediaBase64:
            await _record_event(message, "receipt_media_missing")
            return {"success": True, "status": "receipt_media_missing"}

        try:
            raw = _decode_media(message)
            media_hash = hashlib.sha256(raw).hexdigest()
            should_auto_analyze = authorized_source or await _is_known_customer_sender(message)
            if should_auto_analyze and os.environ.get("OPENAI_API_KEY"):
                analysis, media_hash = await _analyze_receipt(message)
                candidates = await _find_candidate_orders(analysis.get("amount"))
            else:
                analysis = _pending_receipt_analysis()
                candidates = []
            status = await _store_receipt(message, analysis, media_hash, candidates)
        except Exception as exc:
            await _record_event(message, "error", error=type(exc).__name__)
            raise HTTPException(status_code=503, detail="Receipt processing unavailable")

        event_status = "receipt_duplicate_suspected" if status == "duplicate_suspected" else "receipt_pending_review"
        await db.whatsapp_receipts.update_one(
            {"_id": message.messageId},
            {"$set": {
                "from_group": message.fromGroup,
                "received_at": message.receivedAt,
                "auto_analyzed": analysis.get("analysis_status") == "analyzed",
            }},
        )
        await _record_event(message, event_status, candidate_count=len(candidates))
        if os.environ.get("WHATSAPP_SEND_ENABLED", "false").lower() == "true":
            notice = (
                "Recebi o comprovante e deixei no Gestor para conferência. "
                "Nenhum pagamento foi confirmado automaticamente."
            )
            await send_whatsapp_message(notice, message.chatId)
        return {"success": True, "status": event_status, "candidate_count": len(candidates)}

    if not authorized_source:
        await _record_event(message, "unauthorized_source")
        return {"success": True, "status": "unauthorized_source"}

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
