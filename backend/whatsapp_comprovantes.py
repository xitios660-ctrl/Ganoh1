"""
WhatsApp comprovante (payment proof) candidates — ETAPA 8.

Flow: inbound image metadata → pending review → optional AI extraction →
Mongo match suggestions → Gestor confirm / correct / refuse.

Rules:
  - NEVER auto-confirm payment or mutate orders/prazo/cash/pix collections.
  - On confirm: store review + audit only; Gestor still applies money via
    existing PIX/prazo UI (safer incomplete path).
  - AI extracts/formats only; Mongo is source of truth for matches.
  - Media: images jpeg/png/webp only (PDF deferred — vision/path unclear).
  - Size-capped binary in Mongo; never log bytes, QR, credentials, or full bodies.
  - Keys only from env: OPENAI_API_KEY / OPENAI_MODEL.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("whatsapp_comprovantes")

# Statuses
STATUS_AWAITING_GESTOR = "awaiting_gestor"
STATUS_AWAITING_MEDIA = "awaiting_media"
STATUS_CONFIRMED = "confirmed"
STATUS_CORRECTED = "corrected"
STATUS_REFUSED = "refused"

ALLOWED_IMAGE_MIMES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)
# PDF intentionally not accepted in ETAPA 8 — document in progress file.
MAX_MEDIA_BYTES = 2 * 1024 * 1024  # 2 MiB
ORIGIN_LABEL = "WhatsApp / comprovante"
COLLECTION = "whatsapp_comprovantes"
AUDIT_COLLECTION = "whatsapp_comprovante_audit"
MEDIA_COLLECTION = "whatsapp_comprovante_media"

EXTRACT_PROMPT = """Você é um assistente de OCR para comprovantes PIX/transferência.
Extraia APENAS o que aparece na imagem. NÃO invente valores.
Responda SOMENTE JSON:
{
  "payer_name": "nome do pagador ou null",
  "amount": número float ou null,
  "recipient": "destinatário ou null",
  "transaction_time": "HH:MM ou null",
  "transaction_date": "DD/MM/YYYY ou null",
  "confidence": "low|medium|high"
}
Se não conseguir ler, use nulls e confidence low.
"""

_db = None
# Test override: (b64, mime) -> dict extraction
_extract_override: Optional[Callable[[str, str], Dict[str, Any]]] = None


def set_db(db) -> None:
    global _db
    _db = db


def set_extract_override(fn: Optional[Callable[[str, str], Dict[str, Any]]]) -> None:
    global _extract_override
    _extract_override = fn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_key(name: str) -> Optional[str]:
    value = (os.environ.get(name) or "").strip()
    return value or None


def _new_id() -> str:
    return str(uuid.uuid4())


def normalize_mime(mime: Optional[str]) -> Optional[str]:
    if not mime or not isinstance(mime, str):
        return None
    base = mime.split(";")[0].strip().lower()
    if base == "image/jpg":
        return "image/jpeg"
    return base


def is_allowed_image_mime(mime: Optional[str]) -> bool:
    m = normalize_mime(mime)
    return bool(m and m in ALLOWED_IMAGE_MIMES)


def media_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass
class MatchCandidate:
    kind: str  # order | prazo_customer | known_customer
    ref_id: Optional[str]
    label: str
    amount: Optional[float] = None
    store: Optional[str] = None
    score: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "ref_id": self.ref_id,
            "label": self.label,
            "amount": self.amount,
            "store": self.store,
            "score": round(self.score, 3),
            "extra": self.extra,
        }


def _col(db, name: str):
    return getattr(db, name)


async def create_pending_from_inbound(
    *,
    message_id: str,
    remote_jid: str,
    push_name: Optional[str] = None,
    media_mime: Optional[str] = None,
    media_caption: Optional[str] = None,
    media_file_name: Optional[str] = None,
    message_type: str = "image",
    comprovante_stub: Optional[dict] = None,
    db=None,
) -> dict:
    """
    Create or return existing pending comprovante for this messageId (idempotent).
    Does not store media bytes yet — status awaiting_media if stub awaitingDownload.
    """
    database = db if db is not None else _db
    if database is None:
        raise RuntimeError("db_not_configured")

    message_id = (message_id or "").strip()
    remote_jid = (remote_jid or "").strip()
    if not message_id or not remote_jid:
        raise ValueError("messageId and remoteJid required")

    existing = await _col(database, COLLECTION).find_one({"messageId": message_id})
    if existing:
        existing.pop("_id", None)
        return {"created": False, "record": _public_record(existing)}

    mime = normalize_mime(media_mime)
    awaiting = True
    if isinstance(comprovante_stub, dict):
        awaiting = bool(comprovante_stub.get("awaitingDownload", True))

    # Reject non-image early (document/PDF deferred)
    media_ok = is_allowed_image_mime(mime) if mime else (message_type == "image")
    status = STATUS_AWAITING_MEDIA if awaiting else STATUS_AWAITING_GESTOR
    if message_type == "document" and not is_allowed_image_mime(mime):
        # Still create a pending so Gestor sees it, but flag unsupported
        status = STATUS_AWAITING_GESTOR

    now = _now_iso()
    doc = {
        "id": _new_id(),
        "messageId": message_id,
        "remoteJid": remote_jid,
        "pushName": (push_name or "")[:120] or None,
        "messageType": (message_type or "unknown")[:40],
        "mediaMime": mime,
        "mediaCaption": (media_caption[:500] if isinstance(media_caption, str) else None),
        "mediaFileName": (media_file_name[:200] if isinstance(media_file_name, str) else None),
        "mediaAccepted": bool(media_ok and (mime is None or is_allowed_image_mime(mime))),
        "mediaUnsupportedReason": None
        if (mime is None or is_allowed_image_mime(mime) or message_type == "image")
        else "images_only_pdf_deferred",
        "status": status,
        "origin": ORIGIN_LABEL,
        "extraction": None,
        "matches": [],
        "duplicateOf": None,
        "mediaSha256": None,
        "hasMediaBinary": False,
        "gestorNote": None,
        "linkedOrderId": None,
        "linkedPaymentHint": None,
        "confirmedAt": None,
        "refusedAt": None,
        "created_at": now,
        "updated_at": now,
        "retentionNote": "Media binary retained with candidate; purge policy TBD (do not delete financial audit).",
    }
    try:
        await _col(database, COLLECTION).insert_one(doc)
    except Exception as exc:
        # Duplicate key race
        if getattr(exc, "code", None) == 11000:
            again = await _col(database, COLLECTION).find_one({"messageId": message_id})
            if again:
                again.pop("_id", None)
                return {"created": False, "record": _public_record(again)}
        raise

    await _audit(
        database,
        comprovante_id=doc["id"],
        action="created",
        actor="system",
        detail={"status": status, "messageId": message_id},
    )
    return {"created": True, "record": _public_record(doc)}


def _public_record(doc: dict) -> dict:
    """Strip Mongo _id and never expose media bytes."""
    out = {k: v for k, v in doc.items() if k != "_id" and k != "mediaBinary"}
    return out


async def attach_media(
    *,
    message_id: str,
    media_base64: str,
    media_mime: Optional[str] = None,
    db=None,
) -> dict:
    """
    Accept size-capped image bytes (base64) from Baileys sidecar.
    Stores binary in media collection keyed by messageId / sha256.
    """
    database = db if db is not None else _db
    if database is None:
        raise RuntimeError("db_not_configured")

    message_id = (message_id or "").strip()
    if not message_id:
        raise ValueError("messageId required")

    mime = normalize_mime(media_mime) or "image/jpeg"
    if not is_allowed_image_mime(mime):
        return {"ok": False, "error": "mime_not_allowed", "hint": "images_only_jpeg_png_webp"}

    raw_b64 = media_base64 or ""
    if raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[-1]
    try:
        raw = base64.b64decode(raw_b64, validate=False)
    except Exception:
        return {"ok": False, "error": "invalid_base64"}

    if not raw:
        return {"ok": False, "error": "empty_media"}
    if len(raw) > MAX_MEDIA_BYTES:
        return {"ok": False, "error": "media_too_large", "maxBytes": MAX_MEDIA_BYTES}

    digest = media_sha256(raw)
    record = await _col(database, COLLECTION).find_one({"messageId": message_id})
    if not record:
        return {"ok": False, "error": "comprovante_not_found"}

    # Duplicate by content hash across other candidates
    dup = await _col(database, COLLECTION).find_one(
        {"mediaSha256": digest, "messageId": {"$ne": message_id}, "status": {"$ne": STATUS_REFUSED}}
    )
    duplicate_of = dup.get("id") if dup else None

    await _col(database, MEDIA_COLLECTION).update_one(
        {"messageId": message_id},
        {
            "$set": {
                "messageId": message_id,
                "comprovanteId": record["id"],
                "mime": mime,
                "sha256": digest,
                "size": len(raw),
                "binary": raw,
                "updated_at": _now_iso(),
            }
        },
        upsert=True,
    )

    patch = {
        "hasMediaBinary": True,
        "mediaSha256": digest,
        "mediaMime": mime,
        "mediaSize": len(raw),
        "status": STATUS_AWAITING_GESTOR,
        "duplicateOf": duplicate_of,
        "updated_at": _now_iso(),
    }
    await _col(database, COLLECTION).update_one({"messageId": message_id}, {"$set": patch})
    await _audit(
        database,
        comprovante_id=record["id"],
        action="media_attached",
        actor="baileys",
        detail={"sha256": digest, "size": len(raw), "mime": mime, "duplicateOf": duplicate_of},
    )
    # Never return binary
    updated = await _col(database, COLLECTION).find_one({"messageId": message_id})
    updated.pop("_id", None)
    return {"ok": True, "record": _public_record(updated)}


async def run_extraction(
    *,
    comprovante_id: str,
    db=None,
) -> dict:
    """Optional AI OCR — extracts fields only; never confirms payment."""
    database = db if db is not None else _db
    if database is None:
        raise RuntimeError("db_not_configured")

    record = await _col(database, COLLECTION).find_one({"id": comprovante_id})
    if not record:
        return {"ok": False, "error": "not_found"}

    media = await _col(database, MEDIA_COLLECTION).find_one({"messageId": record["messageId"]})
    if not media or not media.get("binary"):
        return {"ok": False, "error": "media_missing"}

    mime = media.get("mime") or record.get("mediaMime") or "image/jpeg"
    b64 = base64.b64encode(media["binary"]).decode("ascii")

    if _extract_override is not None:
        extraction = _extract_override(b64, mime)
    else:
        extraction = await _openai_extract(b64, mime)

    extraction = _sanitize_extraction(extraction)
    matches = await match_candidates(extraction=extraction, remote_jid=record.get("remoteJid"), db=database)

    patch = {
        "extraction": extraction,
        "matches": [m.to_dict() for m in matches],
        "status": STATUS_AWAITING_GESTOR,
        "updated_at": _now_iso(),
    }
    await _col(database, COLLECTION).update_one({"id": comprovante_id}, {"$set": patch})
    await _audit(
        database,
        comprovante_id=comprovante_id,
        action="extraction",
        actor="system",
        detail={
            "has_amount": extraction.get("amount") is not None,
            "match_count": len(matches),
            "confidence": extraction.get("confidence"),
        },
    )
    updated = await _col(database, COLLECTION).find_one({"id": comprovante_id})
    updated.pop("_id", None)
    return {"ok": True, "record": _public_record(updated)}


def _sanitize_extraction(raw: Optional[dict]) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    amount = raw.get("amount")
    try:
        amount_f = float(amount) if amount is not None else None
        if amount_f is not None and (amount_f < 0 or amount_f > 1_000_000):
            amount_f = None
    except (TypeError, ValueError):
        amount_f = None
    confidence = str(raw.get("confidence") or "low").lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "low"
    return {
        "payer_name": _trunc_str(raw.get("payer_name"), 120),
        "amount": amount_f,
        "recipient": _trunc_str(raw.get("recipient"), 120),
        "transaction_time": _trunc_str(raw.get("transaction_time"), 16),
        "transaction_date": _trunc_str(raw.get("transaction_date"), 32),
        "confidence": confidence,
    }


def _trunc_str(value: Any, limit: int) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.lower() == "null":
        return None
    return value[:limit]


async def _openai_extract(b64: str, mime: str) -> dict:
    api_key = _env_key("OPENAI_API_KEY")
    if not api_key:
        return {"confidence": "low", "amount": None, "payer_name": None}

    model = _env_key("OPENAI_MODEL") or "gpt-4o-mini"
    # Vision chat completions via stdlib
    import urllib.error
    import urllib.request

    data_url = f"data:{mime};base64,{b64}"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": EXTRACT_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extraia os campos do comprovante."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        match = re.search(r"\{[\s\S]*\}", content if isinstance(content, str) else "")
        if match:
            return json.loads(match.group())
    except Exception as exc:
        logger.warning("comprovante extract failed: %s", type(exc).__name__)
    return {"confidence": "low", "amount": None, "payer_name": None}


async def match_candidates(
    *,
    extraction: dict,
    remote_jid: Optional[str] = None,
    db=None,
    limit: int = 8,
) -> List[MatchCandidate]:
    """
    Read-only suggestions against orders / prazo customers.
    Never writes. Amount + name heuristics only.
    """
    database = db if db is not None else _db
    if database is None:
        return []

    amount = extraction.get("amount") if isinstance(extraction, dict) else None
    payer = (extraction.get("payer_name") or "") if isinstance(extraction, dict) else ""
    payer_l = payer.strip().lower()
    results: List[MatchCandidate] = []

    # Pending PIX orders with similar amount
    try:
        orders = await _col(database, "orders").find(
            {"status": {"$in": ["pending_payment", "payment_rejected", "received"]}},
            {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1, "total": 1, "store": 1, "status": 1, "payment_method": 1},
        ).to_list(200)
    except Exception:
        orders = []

    for order in orders or []:
        total = order.get("total")
        score = 0.0
        try:
            total_f = float(total) if total is not None else None
        except (TypeError, ValueError):
            total_f = None
        if amount is not None and total_f is not None:
            diff = abs(total_f - float(amount))
            if diff < 0.02:
                score += 0.7
            elif diff <= 1.0:
                score += 0.35
        cname = (order.get("customer_name") or "").strip().lower()
        if payer_l and cname and (payer_l in cname or cname in payer_l):
            score += 0.4
        if order.get("payment_method") == "pix":
            score += 0.1
        if score >= 0.35:
            results.append(
                MatchCandidate(
                    kind="order",
                    ref_id=order.get("id"),
                    label=f"Pedido #{order.get('order_number') or (order.get('id') or '')[:8]} — {order.get('customer_name') or '?'}",
                    amount=total_f,
                    store=order.get("store"),
                    score=score,
                    extra={"status": order.get("status"), "payment_method": order.get("payment_method")},
                )
            )

    # Prazo customers by name
    if payer_l:
        try:
            customers = await _col(database, "prazo_customers").find(
                {},
                {"_id": 0, "id": 1, "name": 1, "store": 1, "balance": 1, "debt": 1},
            ).to_list(300)
        except Exception:
            customers = []
        for cust in customers or []:
            cname = (cust.get("name") or "").strip().lower()
            if not cname:
                continue
            if payer_l in cname or cname in payer_l:
                bal = cust.get("balance", cust.get("debt"))
                try:
                    bal_f = float(bal) if bal is not None else None
                except (TypeError, ValueError):
                    bal_f = None
                score = 0.5
                if amount is not None and bal_f is not None and abs(bal_f - float(amount)) < 0.05:
                    score += 0.3
                results.append(
                    MatchCandidate(
                        kind="prazo_customer",
                        ref_id=cust.get("id"),
                        label=f"Prazo: {cust.get('name')}",
                        amount=bal_f,
                        store=cust.get("store"),
                        score=score,
                        extra={},
                    )
                )

    results.sort(key=lambda m: m.score, reverse=True)
    return results[:limit]


async def find_duplicates(
    *,
    message_id: Optional[str] = None,
    media_sha256_value: Optional[str] = None,
    linked_order_id: Optional[str] = None,
    db=None,
) -> List[dict]:
    database = db if db is not None else _db
    if database is None:
        return []
    query: Dict[str, Any] = {"status": {"$in": [STATUS_CONFIRMED, STATUS_CORRECTED, STATUS_AWAITING_GESTOR]}}
    or_clauses = []
    if media_sha256_value:
        or_clauses.append({"mediaSha256": media_sha256_value})
    if linked_order_id:
        or_clauses.append({"linkedOrderId": linked_order_id})
    if message_id:
        or_clauses.append({"messageId": message_id})
    if not or_clauses:
        return []
    query["$or"] = or_clauses
    try:
        rows = await _col(database, COLLECTION).find(query, {"_id": 0, "id": 1, "messageId": 1, "status": 1, "mediaSha256": 1, "linkedOrderId": 1}).to_list(20)
    except Exception:
        rows = []
    return rows or []


async def list_pending(*, status: Optional[str] = None, limit: int = 50, db=None) -> List[dict]:
    database = db if db is not None else _db
    if database is None:
        return []
    limit = max(1, min(100, int(limit or 50)))
    query: Dict[str, Any] = {}
    if status:
        query["status"] = status
    else:
        query["status"] = {"$in": [STATUS_AWAITING_GESTOR, STATUS_AWAITING_MEDIA]}
    try:
        rows = await _col(database, COLLECTION).find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    except Exception:
        rows = []
    return [_public_record(r) for r in (rows or [])]



async def get_one_by_message_id(message_id: str, db=None) -> Optional[dict]:
    database = db if db is not None else _db
    if database is None or not message_id:
        return None
    row = await _col(database, COLLECTION).find_one({"messageId": message_id}, {"_id": 0})
    return _public_record(row) if row else None


async def get_one(comprovante_id: str, db=None) -> Optional[dict]:
    database = db if db is not None else _db
    if database is None:
        return None
    row = await _col(database, COLLECTION).find_one({"id": comprovante_id}, {"_id": 0})
    return _public_record(row) if row else None


async def confirm(
    *,
    comprovante_id: str,
    actor: str = "gestor",
    linked_order_id: Optional[str] = None,
    note: Optional[str] = None,
    corrected_amount: Optional[float] = None,
    as_corrected: bool = False,
    db=None,
) -> dict:
    """
    Gestor confirm/correct — stores review + audit ONLY.
    Does NOT mutate orders / prazo / cash / pix (safer path).
    Idempotent if already confirmed/corrected with same linked order.
    """
    database = db if db is not None else _db
    if database is None:
        raise RuntimeError("db_not_configured")

    record = await _col(database, COLLECTION).find_one({"id": comprovante_id})
    if not record:
        return {"ok": False, "error": "not_found"}

    current = record.get("status")
    if current in (STATUS_CONFIRMED, STATUS_CORRECTED):
        # Idempotent — already done
        record.pop("_id", None)
        return {"ok": True, "idempotent": True, "record": _public_record(record), "moneyApplied": False}

    if current == STATUS_REFUSED:
        return {"ok": False, "error": "already_refused"}

    # Duplicate payment guard: same media or same order already confirmed
    if record.get("mediaSha256"):
        dups = await find_duplicates(
            media_sha256_value=record["mediaSha256"],
            linked_order_id=linked_order_id,
            db=database,
        )
        for d in dups:
            if d.get("id") != comprovante_id and d.get("status") in (STATUS_CONFIRMED, STATUS_CORRECTED):
                return {
                    "ok": False,
                    "error": "duplicate_payment",
                    "duplicateId": d.get("id"),
                    "moneyApplied": False,
                }

    new_status = STATUS_CORRECTED if as_corrected else STATUS_CONFIRMED
    now = _now_iso()
    patch = {
        "status": new_status,
        "linkedOrderId": linked_order_id or record.get("linkedOrderId"),
        "gestorNote": _trunc_str(note, 500),
        "confirmedAt": now,
        "origin": ORIGIN_LABEL,
        "updated_at": now,
        "moneyApplied": False,
        "moneyApplyHint": (
            "Confirmação registra revisão/auditoria apenas. "
            "Aplique o valor pelo fluxo existente de PIX/prazo no Gestor."
        ),
    }
    if corrected_amount is not None:
        try:
            patch["correctedAmount"] = float(corrected_amount)
        except (TypeError, ValueError):
            pass

    await _col(database, COLLECTION).update_one({"id": comprovante_id}, {"$set": patch})
    await _audit(
        database,
        comprovante_id=comprovante_id,
        action=new_status,
        actor=actor,
        detail={
            "linkedOrderId": patch.get("linkedOrderId"),
            "moneyApplied": False,
            "note_len": len(note or ""),
        },
    )
    updated = await _col(database, COLLECTION).find_one({"id": comprovante_id})
    updated.pop("_id", None)
    return {"ok": True, "idempotent": False, "record": _public_record(updated), "moneyApplied": False}


async def refuse(
    *,
    comprovante_id: str,
    actor: str = "gestor",
    note: Optional[str] = None,
    db=None,
) -> dict:
    database = db if db is not None else _db
    if database is None:
        raise RuntimeError("db_not_configured")

    record = await _col(database, COLLECTION).find_one({"id": comprovante_id})
    if not record:
        return {"ok": False, "error": "not_found"}
    if record.get("status") == STATUS_REFUSED:
        record.pop("_id", None)
        return {"ok": True, "idempotent": True, "record": _public_record(record)}
    if record.get("status") in (STATUS_CONFIRMED, STATUS_CORRECTED):
        return {"ok": False, "error": "already_confirmed"}

    now = _now_iso()
    patch = {
        "status": STATUS_REFUSED,
        "gestorNote": _trunc_str(note, 500),
        "refusedAt": now,
        "updated_at": now,
    }
    await _col(database, COLLECTION).update_one({"id": comprovante_id}, {"$set": patch})
    await _audit(
        database,
        comprovante_id=comprovante_id,
        action="refused",
        actor=actor,
        detail={"note_len": len(note or "")},
    )
    updated = await _col(database, COLLECTION).find_one({"id": comprovante_id})
    updated.pop("_id", None)
    return {"ok": True, "idempotent": False, "record": _public_record(updated)}


async def _audit(db, *, comprovante_id: str, action: str, actor: str, detail: Optional[dict] = None) -> None:
    try:
        await _col(db, AUDIT_COLLECTION).insert_one(
            {
                "id": _new_id(),
                "comprovanteId": comprovante_id,
                "action": action,
                "actor": (actor or "system")[:80],
                "detail": detail or {},
                "created_at": _now_iso(),
            }
        )
    except Exception:
        logger.warning("comprovante audit failed action=%s", action)


def ack_message_for_inbound(*, send_enabled: bool) -> dict:
    """
    Draft ack when media comprovante arrives.
    Respects WHATSAPP_SEND_ENABLED — if false, would_reply only.
    """
    text = (
        "Recebi o comprovante. Ele ficará em análise do Gestor — "
        "não confirmo pagamento automaticamente."
    )
    if not send_enabled:
        return {"status": "would_reply", "reason": "WHATSAPP_SEND_ENABLED_off", "reply": text, "sendAttempted": False}
    return {"status": "replied_pending", "reason": None, "reply": text, "sendAttempted": True}


__all__ = [
    "STATUS_AWAITING_GESTOR",
    "STATUS_AWAITING_MEDIA",
    "STATUS_CONFIRMED",
    "STATUS_CORRECTED",
    "STATUS_REFUSED",
    "ALLOWED_IMAGE_MIMES",
    "MAX_MEDIA_BYTES",
    "ORIGIN_LABEL",
    "set_db",
    "set_extract_override",
    "create_pending_from_inbound",
    "attach_media",
    "run_extraction",
    "match_candidates",
    "find_duplicates",
    "list_pending",
    "get_one",
    "get_one_by_message_id",
    "confirm",
    "refuse",
    "ack_message_for_inbound",
    "is_allowed_image_mime",
    "normalize_mime",
]
