"""Unit tests for WhatsApp comprovantes (ETAPA 8) — FakeDB, no prod Mongo/OpenAI/send."""

from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import whatsapp_comprovantes as wc
import whatsapp_ai as wai


class FakeCursor:
    def __init__(self, docs: List[dict]):
        self._docs = list(docs)

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, limit: int):
        return self._docs[:limit]


def _match_value(actual, expected) -> bool:
    if isinstance(expected, dict):
        if "$in" in expected:
            return actual in expected["$in"]
        if "$ne" in expected:
            return actual != expected["$ne"]
        if "$lte" in expected:
            return actual is not None and actual <= expected["$lte"]
        if "$gte" in expected:
            return actual is not None and actual >= expected["$gte"]
        return False
    return actual == expected


def _match_doc(doc: dict, query: dict) -> bool:
    if not query:
        return True
    if "$or" in query:
        ors = query["$or"]
        rest = {k: v for k, v in query.items() if k != "$or"}
        if not any(_match_doc(doc, clause) for clause in ors):
            return False
        return _match_doc(doc, rest) if rest else True
    for key, expected in query.items():
        if not _match_value(doc.get(key), expected):
            return False
    return True


class FakeCollection:
    def __init__(self, docs: Optional[List[dict]] = None):
        self.docs = list(docs or [])

    def find(self, query: dict, projection=None):
        matched = [dict(d) for d in self.docs if _match_doc(d, query)]
        return FakeCursor(matched)

    async def find_one(self, query: dict, projection=None):
        for d in self.docs:
            if _match_doc(d, query):
                return dict(d)
        return None

    async def insert_one(self, doc: dict):
        # unique messageId for comprovantes
        if "messageId" in doc:
            for d in self.docs:
                if d.get("messageId") == doc["messageId"]:
                    err = Exception("duplicate")
                    err.code = 11000  # type: ignore[attr-defined]
                    raise err
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        for i, d in enumerate(self.docs):
            if _match_doc(d, query):
                if "$set" in update:
                    self.docs[i] = {**d, **update["$set"]}
                return type("R", (), {"matched_count": 1})()
        if upsert:
            base = dict(query)
            if "$set" in update:
                base.update(update["$set"])
            self.docs.append(base)
            return type("R", (), {"matched_count": 0, "upserted_id": True})()
        return type("R", (), {"matched_count": 0})()


class FakeDB:
    def __init__(self, **collections):
        self._cols = {name: FakeCollection(docs) for name, docs in collections.items()}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cols:
            self._cols[name] = FakeCollection([])
        return self._cols[name]


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    wc.set_db(None)
    wc.set_extract_override(None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("WHATSAPP_SEND_ENABLED", raising=False)
    yield
    wc.set_db(None)
    wc.set_extract_override(None)


def test_create_pending_idempotent_by_message_id():
    db = FakeDB()
    wc.set_db(db)
    first = _run(
        wc.create_pending_from_inbound(
            message_id="m1",
            remote_jid="5511@s.whatsapp.net",
            push_name="Cliente",
            media_mime="image/jpeg",
            message_type="image",
            comprovante_stub={"awaitingDownload": True, "purpose": "comprovante_candidate"},
        )
    )
    assert first["created"] is True
    assert first["record"]["status"] == wc.STATUS_AWAITING_MEDIA
    assert first["record"]["origin"] == wc.ORIGIN_LABEL

    second = _run(
        wc.create_pending_from_inbound(
            message_id="m1",
            remote_jid="5511@s.whatsapp.net",
            media_mime="image/jpeg",
            message_type="image",
        )
    )
    assert second["created"] is False
    assert second["record"]["id"] == first["record"]["id"]
    assert len(db.whatsapp_comprovantes.docs) == 1
    assert len(db.whatsapp_comprovante_audit.docs) == 1


def test_document_pdf_flagged_images_only():
    db = FakeDB()
    wc.set_db(db)
    out = _run(
        wc.create_pending_from_inbound(
            message_id="pdf1",
            remote_jid="5511@s.whatsapp.net",
            media_mime="application/pdf",
            message_type="document",
            comprovante_stub={"awaitingDownload": True, "purpose": "comprovante_candidate"},
        )
    )
    assert out["record"]["mediaUnsupportedReason"] == "images_only_pdf_deferred"


def test_attach_media_size_and_mime_guards():
    db = FakeDB()
    wc.set_db(db)
    _run(
        wc.create_pending_from_inbound(
            message_id="img1",
            remote_jid="5511@s.whatsapp.net",
            media_mime="image/png",
            message_type="image",
        )
    )
    bad_mime = _run(
        wc.attach_media(message_id="img1", media_base64=base64.b64encode(b"abc").decode(), media_mime="application/pdf")
    )
    assert bad_mime["ok"] is False
    assert bad_mime["error"] == "mime_not_allowed"

    huge = b"x" * (wc.MAX_MEDIA_BYTES + 10)
    too_big = _run(
        wc.attach_media(
            message_id="img1",
            media_base64=base64.b64encode(huge).decode(),
            media_mime="image/png",
        )
    )
    assert too_big["ok"] is False
    assert too_big["error"] == "media_too_large"

    ok = _run(
        wc.attach_media(
            message_id="img1",
            media_base64=base64.b64encode(b"\x89PNG-fake").decode(),
            media_mime="image/png",
        )
    )
    assert ok["ok"] is True
    assert ok["record"]["hasMediaBinary"] is True
    assert ok["record"]["status"] == wc.STATUS_AWAITING_GESTOR
    assert ok["record"]["mediaSha256"]
    # binary not in public record
    assert "binary" not in ok["record"]
    assert "mediaBinary" not in ok["record"]


def test_extraction_match_confirm_refuse_no_money_mutation():
    db = FakeDB(
        orders=[
            {
                "id": "ord-1",
                "order_number": "100",
                "customer_name": "Maria Silva",
                "total": 45.5,
                "store": "runner",
                "status": "pending_payment",
                "payment_method": "pix",
            }
        ],
        prazo_customers=[{"id": "c1", "name": "Maria Silva", "store": "runner", "balance": 45.5}],
    )
    wc.set_db(db)
    created = _run(
        wc.create_pending_from_inbound(
            message_id="pay1",
            remote_jid="5511@s.whatsapp.net",
            media_mime="image/jpeg",
            message_type="image",
            comprovante_stub={"awaitingDownload": False},
        )
    )
    cid = created["record"]["id"]
    _run(
        wc.attach_media(
            message_id="pay1",
            media_base64=base64.b64encode(b"jpeg-bytes").decode(),
            media_mime="image/jpeg",
        )
    )

    wc.set_extract_override(
        lambda b64, mime: {
            "payer_name": "Maria Silva",
            "amount": 45.5,
            "recipient": "GANOH",
            "transaction_time": "10:30",
            "transaction_date": "24/09/2026",
            "confidence": "high",
        }
    )
    extracted = _run(wc.run_extraction(comprovante_id=cid))
    assert extracted["ok"] is True
    assert extracted["record"]["extraction"]["amount"] == 45.5
    assert any(m["kind"] == "order" for m in extracted["record"]["matches"])

    # Confirm — review only
    conf = _run(wc.confirm(comprovante_id=cid, linked_order_id="ord-1", note="ok"))
    assert conf["ok"] is True
    assert conf["moneyApplied"] is False
    assert conf["record"]["status"] == wc.STATUS_CONFIRMED
    assert conf["record"]["origin"] == wc.ORIGIN_LABEL

    # Idempotent re-confirm
    again = _run(wc.confirm(comprovante_id=cid, linked_order_id="ord-1"))
    assert again["ok"] is True
    assert again.get("idempotent") is True

    # Orders untouched
    assert db.orders.docs[0]["status"] == "pending_payment"
    assert len(db.whatsapp_comprovante_audit.docs) >= 3


def test_duplicate_media_blocks_second_confirm():
    db = FakeDB()
    wc.set_db(db)
    payload = base64.b64encode(b"same-bytes").decode()

    for mid in ("a1", "a2"):
        _run(
            wc.create_pending_from_inbound(
                message_id=mid,
                remote_jid="5511@s.whatsapp.net",
                media_mime="image/webp",
                message_type="image",
            )
        )
        _run(wc.attach_media(message_id=mid, media_base64=payload, media_mime="image/webp"))

    c1 = _run(wc.get_one_by_message_id("a1"))
    c2 = _run(wc.get_one_by_message_id("a2"))
    assert c2["duplicateOf"] == c1["id"]

    ok = _run(wc.confirm(comprovante_id=c1["id"]))
    assert ok["ok"] is True
    blocked = _run(wc.confirm(comprovante_id=c2["id"]))
    assert blocked["ok"] is False
    assert blocked["error"] == "duplicate_payment"


def test_refuse_and_ack_would_reply(monkeypatch):
    db = FakeDB()
    wc.set_db(db)
    created = _run(
        wc.create_pending_from_inbound(
            message_id="r1",
            remote_jid="5511@s.whatsapp.net",
            media_mime="image/jpeg",
            message_type="image",
        )
    )
    refused = _run(wc.refuse(comprovante_id=created["record"]["id"], note="ilegível"))
    assert refused["ok"] is True
    assert refused["record"]["status"] == wc.STATUS_REFUSED

    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "false")
    ack = wc.ack_message_for_inbound(send_enabled=False)
    assert ack["status"] == "would_reply"
    assert ack["reason"] == "WHATSAPP_SEND_ENABLED_off"
    assert ack["sendAttempted"] is False


def test_list_pending_and_ai_prompt_mentions_gestor_review():
    db = FakeDB()
    wc.set_db(db)
    _run(
        wc.create_pending_from_inbound(
            message_id="l1",
            remote_jid="5511@s.whatsapp.net",
            media_mime="image/jpeg",
            message_type="image",
            comprovante_stub={"awaitingDownload": False},
        )
    )
    items = _run(wc.list_pending())
    assert len(items) == 1
    assert "comprovante" in wai.SYSTEM_PROMPT.lower() or "Comprovantes" in wai.SYSTEM_PROMPT
    assert "Gestor" in wai.SYSTEM_PROMPT
    assert "MSG_COMPROVANTE_PENDING" in wai.__all__ or hasattr(wai, "MSG_COMPROVANTE_PENDING")


def test_mime_helpers():
    assert wc.is_allowed_image_mime("image/jpeg")
    assert wc.is_allowed_image_mime("image/png; charset=binary")
    assert not wc.is_allowed_image_mime("application/pdf")
    assert wc.normalize_mime("image/jpg") == "image/jpeg"
