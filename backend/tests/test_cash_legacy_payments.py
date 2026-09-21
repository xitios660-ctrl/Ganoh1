"""Regression tests for legacy payment methods in the daily cash summary."""
import asyncio
from datetime import datetime
import os
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server
from routers import cash


class FakeCursor:
    def __init__(self, records):
        self.records = records

    async def to_list(self, _limit):
        return self.records

    def sort(self, *_args, **_kwargs):
        return self


class FakeCollection:
    def __init__(self, records):
        self.records = records

    def find(self, query, *_args, **_kwargs):
        records = self.records
        date_filter = query.get("created_at", {}).get("$gte")
        if date_filter:
            # Reproduce MongoDB's lexical comparison for stored strings.
            records = [r for r in records if r.get("created_at", "") >= date_filter]
        return FakeCursor(records)


@pytest.mark.parametrize(
    ("module", "store"),
    [(server, server.StoreLocation.RUNNER), (cash, "runner")],
)
def test_daily_cash_accepts_unknown_legacy_payment_method(monkeypatch, module, store):
    today = datetime.now(cash.BRAZIL_TZ)
    legacy_order = {
        "store": "runner",
        "status": "delivered",
        "payment_method": "legacy-card",
        "total": 12.34,
        "created_at": today.replace(hour=10, minute=0, second=0, microsecond=0).isoformat(),
    }
    fake_db = SimpleNamespace(
        orders=FakeCollection([legacy_order]),
        pix_adjustments=FakeCollection([]),
    )
    monkeypatch.setattr(module, "db", fake_db)

    summary = asyncio.run(module.get_today_cash(store))

    assert summary["total"] == pytest.approx(12.34)
    assert summary["by_payment_method"]["legacy-card"] == pytest.approx(12.34)
    assert summary["shifts"]["morning"]["by_payment"]["legacy-card"] == pytest.approx(12.34)


@pytest.mark.parametrize(
    ("module", "store"),
    [(server, server.StoreLocation.RUNNER), (cash, "runner")],
)
def test_daily_cash_includes_local_offset_sale_just_after_midnight(monkeypatch, module, store):
    today = datetime.now(cash.BRAZIL_TZ)
    early_sale = {
        "store": "runner",
        "status": "delivered",
        "payment_method": "cash",
        "total": 20.0,
        "created_at": today.replace(hour=0, minute=30, second=0, microsecond=0).isoformat(),
    }
    fake_db = SimpleNamespace(
        orders=FakeCollection([early_sale]),
        pix_adjustments=FakeCollection([]),
    )
    monkeypatch.setattr(module, "db", fake_db)

    summary = asyncio.run(module.get_today_cash(store))

    assert summary["total"] == pytest.approx(20.0)
    assert summary["by_payment_method"]["cash"] == pytest.approx(20.0)
