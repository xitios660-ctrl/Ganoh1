"""Unit tests for WhatsApp finance tools (ETAPA 7) — fake in-memory Mongo, no production DB."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import pytz

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import whatsapp_finance as wf
import whatsapp_ai as wai

BRAZIL = pytz.timezone("America/Sao_Paulo")


def _iso_brazil(hour: int, minute: int = 0, day_offset: int = 0) -> str:
    now = datetime.now(BRAZIL)
    dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=day_offset)
    return dt.astimezone(pytz.UTC).isoformat()


class FakeCursor:
    def __init__(self, docs: List[dict]):
        self._docs = list(docs)

    def sort(self, *_a, **_k):
        return self

    async def to_list(self, limit: int):
        return self._docs[:limit]


class FakeCollection:
    def __init__(self, docs: Optional[List[dict]] = None):
        self.docs = list(docs or [])

    def _match(self, doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            actual = doc.get(key)
            if isinstance(expected, dict):
                if "$in" in expected:
                    if actual not in expected["$in"]:
                        return False
                elif "$ne" in expected:
                    if actual == expected["$ne"]:
                        return False
                elif "$lte" in expected:
                    if not (actual is not None and actual <= expected["$lte"]):
                        return False
                else:
                    return False
            else:
                if actual != expected:
                    return False
        return True

    def find(self, query: dict, projection=None):
        matched = [d for d in self.docs if self._match(d, query)]
        return FakeCursor(matched)

    async def find_one(self, query: dict, projection=None):
        for d in self.docs:
            if self._match(d, query):
                return dict(d)
        return None


class FakeDB:
    def __init__(self, **collections):
        self._cols = {name: FakeCollection(docs) for name, docs in collections.items()}

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cols:
            self._cols[name] = FakeCollection([])
        return self._cols[name]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    wf.set_fetcher_override(None)
    wf.set_db(None)
    wai.set_complete_override(None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    yield
    wf.set_fetcher_override(None)
    wf.set_db(None)
    wai.set_complete_override(None)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_detect_intent_sales_pix_debt_stock():
    assert wf.detect_intent("Quanto vendeu hoje?").intent == wf.INTENT_SALES_TODAY
    assert wf.detect_intent("Quanto entrou de PIX hoje?").intent == wf.INTENT_PIX_TODAY
    assert wf.detect_intent("Quem está devendo?").intent == wf.INTENT_DEBTS
    assert wf.detect_intent("Estoque baixo").intent == wf.INTENT_LOW_STOCK
    assert wf.detect_intent("Fechamento da manhã Runner").intent == wf.INTENT_MORNING_CLOSE
    assert wf.detect_store("vendas gym londres") == "gym-londres"
    assert wf.detect_store("Runner hoje") == "runner"


def test_sales_today_with_fixture_orders():
    db = FakeDB(
        orders=[
            {
                "store": "runner",
                "status": "ready",
                "payment_method": "pix",
                "total": 50.0,
                "created_at": _iso_brazil(10),
                "customer_name": "A",
            },
            {
                "store": "runner",
                "status": "delivered",
                "payment_method": "cash",
                "total": 20.0,
                "created_at": _iso_brazil(11),
                "customer_name": "B",
            },
            {
                "store": "gym-londres",
                "status": "ready",
                "payment_method": "pix",
                "total": 30.0,
                "created_at": _iso_brazil(12),
                "customer_name": "C",
            },
            # prazo must not inflate à vista total
            {
                "store": "runner",
                "status": "ready",
                "payment_method": "prazo",
                "total": 999.0,
                "created_at": _iso_brazil(9),
                "customer_name": "D",
                "prazo_paid": False,
            },
        ],
        pix_adjustments=[],
    )
    facts = _run(wf.query_sales_bundle(db, store="runner"))
    assert facts.ok
    assert facts.empty is False
    assert facts.data["total_vendas_rs"] == 70.0
    assert facts.data["pix_rs"] == 50.0
    assert facts.data["dinheiro_rs"] == 20.0
    assert facts.data["qtd_pedidos"] == 3  # includes prazo order count

    pix = _run(wf.query_payment_focus(db, "runner", "pix", wf.INTENT_PIX_TODAY))
    assert pix.data["total_rs"] == 50.0


def test_sales_empty_no_invention():
    db = FakeDB(orders=[], pix_adjustments=[])
    facts = _run(wf.query_sales_bundle(db, store="runner"))
    assert facts.ok
    assert facts.empty is True
    assert facts.data["total_vendas_rs"] == 0.0
    block = facts.to_prompt_block()
    assert "sem registros" in block.lower() or "SEM" in block or "não invente" in block.lower() or "NÃO invente" in block


def test_debts_and_customer_hint():
    db = FakeDB(
        orders=[
            {
                "store": "runner",
                "payment_method": "prazo",
                "prazo_paid": False,
                "customer_name": "João Silva",
                "total": 100.0,
                "partial_paid": 40.0,
                "created_at": _iso_brazil(8, day_offset=-2),
            },
            {
                "store": "runner",
                "payment_method": "prazo",
                "prazo_paid": False,
                "customer_name": "Maria",
                "total": 50.0,
                "partial_paid": 0,
                "created_at": _iso_brazil(8, day_offset=-1),
            },
        ]
    )
    debts = _run(wf.query_debts(db))
    assert debts.ok
    assert debts.data["customer_count"] == 2
    assert debts.data["total_prazo_aberto_rs"] == 110.0

    one = _run(wf.query_debts(db, customer_hint="João"))
    assert one.intent == wf.INTENT_DEBT_CUSTOMER or one.data.get("cliente") == "João Silva" or one.data.get("total_deve_rs") == 60.0
    assert one.data.get("total_deve_rs") == 60.0

    missing = _run(wf.query_debts(db, customer_hint="Zé Ninguém"))
    assert missing.empty is True


def test_low_stock():
    db = FakeDB(
        stock=[
            {"store": "runner", "name": "Coca", "quantity": 1, "min_quantity": 5, "menu_item_id": "1"},
            {"store": "runner", "name": "Água", "quantity": 20, "min_quantity": 5, "menu_item_id": "2"},
            {"store": "gym-londres", "name": "Suco", "quantity": 0, "min_quantity": 2, "menu_item_id": "3"},
        ]
    )
    facts = _run(wf.query_low_stock(db))
    assert facts.ok
    assert facts.data["qtd_itens_baixos"] == 2
    assert any("Coca" in line for line in facts.data["itens"])


def test_cash_drawer_expected_balance():
    db = FakeDB(
        cash_drawer_config=[{"store": "runner", "balance": 100.0, "last_reset_at": _iso_brazil(0, day_offset=-1)}],
        orders=[
            {
                "store": "runner",
                "status": "ready",
                "payment_method": "cash",
                "total": 25.0,
                "created_at": _iso_brazil(10),
                "synthetic": False,
            }
        ],
        prazo_payments=[],
        prazo_partial_payments=[],
        cash_credit_topups=[],
        cash_withdrawals=[{"store": "runner", "amount": 10.0, "created_at": _iso_brazil(11)}],
    )
    facts = _run(wf.query_cash_drawer(db, store="runner"))
    assert facts.ok
    assert facts.data["saldo_esperado_rs"] == 115.0  # 100 + 25 - 10
    assert "Gestor" in facts.data["nota"] or "gestor" in facts.data["nota"].lower()


def test_prazo_payments_today():
    db = FakeDB(
        prazo_payments=[
            {
                "store": "runner",
                "customer_name": "Ana",
                "amount": 40.0,
                "payment_method": "pix",
                "created_at": _iso_brazil(15),
            }
        ],
        prazo_partial_payments=[
            {
                "store": "runner",
                "customer_name": "Bob",
                "amount": 10.0,
                "payment_method": "cash",
                "created_at": _iso_brazil(16),
            }
        ],
    )
    facts = _run(wf.query_prazo_payments_today(db, store="runner"))
    assert facts.ok
    assert facts.data["total_rs"] == 50.0
    assert facts.data["qtd_pagamentos"] == 2


def test_sensitive_still_blocked(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(*_a, **_k):
        raise AssertionError("must not call OpenAI for sensitive")

    wai.set_complete_override(boom)
    reply = wai.chat_reply("Apagar venda e zerar dívida")
    assert reply == wai.MSG_SENSITIVE_STUB


def test_ai_formats_only_with_injected_facts(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured = {}

    def fake(messages, model, api_key):
        captured["system"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        assert "150.00" in messages[0]["content"] or "150" in messages[0]["content"]
        assert "DADOS OFICIAIS" in messages[0]["content"]
        # Model must only format — return text using injected number
        return "Hoje o total de vendas foi R$ 150,00 (dados do sistema)."

    wai.set_complete_override(fake)
    facts = wf.FinanceFacts(
        intent=wf.INTENT_SALES_TODAY,
        ok=True,
        label="Vendas hoje",
        data={"total_vendas_rs": 150.0, "date": "2026-09-24"},
        empty=False,
    )
    reply = wai.chat_reply("Quanto vendeu hoje?", context={"finance_facts": facts})
    assert "150" in reply
    assert "DADOS OFICIAIS" in captured["system"]
    assert "sk-test" not in captured["system"]


def test_financial_without_facts_no_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    wai.set_complete_override(lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no call")))
    reply = wai.chat_reply("Qual o saldo do caixa?")
    assert reply == wai.MSG_FINANCIAL_UNAVAILABLE


def test_achat_reply_fetches_via_override(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    async def fake_fetch(text):
        return wf.FinanceFacts(
            intent=wf.INTENT_SALES_TODAY,
            ok=True,
            label="Vendas",
            data={"total_vendas_rs": 88.5, "date": "2026-09-24"},
        )

    wf.set_fetcher_override(fake_fetch)

    def completer(messages, model, key):
        assert "88.5" in messages[0]["content"] or "88.50" in messages[0]["content"]
        return "Vendas de hoje: R$ 88,50."

    wai.set_complete_override(completer)
    reply = _run(wai.achat_reply("Quanto vendeu hoje?"))
    assert "88" in reply


def test_fetch_facts_end_to_end_fake_db():
    db = FakeDB(
        orders=[
            {
                "store": "runner",
                "status": "ready",
                "payment_method": "pix",
                "total": 12.0,
                "created_at": _iso_brazil(9),
            }
        ],
        pix_adjustments=[],
        stock=[{"store": "runner", "name": "X", "quantity": 0, "min_quantity": 2}],
    )
    wf.set_db(db)
    sales = _run(wf.fetch_facts_for_text("Quanto vendeu hoje no Runner?"))
    assert sales.ok
    assert sales.data["total_vendas_rs"] == 12.0
    stock = _run(wf.fetch_facts_for_text("tem estoque baixo?"))
    assert stock.intent == wf.INTENT_LOW_STOCK
    assert stock.data["qtd_itens_baixos"] == 1


def test_no_secrets_in_finance_module_source():
    src = Path(wf.__file__).read_text(encoding="utf-8")
    assert "mongodb+srv" not in src.lower()
    assert "MONGO_URL" not in src  # wiring is via set_db, not env scrape in this module
    assert "sk-proj-" not in src
