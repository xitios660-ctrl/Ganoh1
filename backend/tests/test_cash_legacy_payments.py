"""Regression tests for legacy payment methods in the daily cash summary."""
import asyncio
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


class FakeCollection:
    def __init__(self, records):
        self.records = records

    def find(self, *_args, **_kwargs):
        return FakeCursor(self.records)


@pytest.mark.parametrize(
    ("module", "store"),
    [(server, server.StoreLocation.RUNNER), (cash, "runner")],
)
def test_daily_cash_accepts_unknown_legacy_payment_method(monkeypatch, module, store):
    legacy_order = {
        "store": "runner",
        "status": "delivered",
        "payment_method": "legacy-card",
        "total": 12.34,
        "created_at": "2026-09-21T10:00:00-03:00",
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
