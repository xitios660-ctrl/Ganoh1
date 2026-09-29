"""Regression tests for the cash bug reported on 2026-09-29.

Scenario: a full cash withdrawal closes the old drawer period. A later R$ 5.00
cash entry must be counted as R$ 5.00 and must not be shifted by older orders.
No real MongoDB is used.
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server


class FakeCollection:
    def __init__(self):
        self.inserted = []
        self.updated = []

    async def insert_one(self, document):
        self.inserted.append(document)
        return SimpleNamespace(inserted_id="fake")

    async def update_one(self, query, update, upsert=False):
        self.updated.append((query, update, upsert))
        return SimpleNamespace(modified_count=1)


def test_full_withdrawal_closes_old_cash_period(monkeypatch):
    withdrawals = FakeCollection()
    config = FakeCollection()
    expenses = FakeCollection()
    fake_db = SimpleNamespace(
        cash_withdrawals=withdrawals,
        cash_drawer_config=config,
        expenses=expenses,
    )
    monkeypatch.setattr(server, "db", fake_db)

    calls = {"count": 0}

    async def fake_get_cash_drawer(_store):
        calls["count"] += 1
        return {"current_balance": 12.34 if calls["count"] == 1 else 0.0}

    monkeypatch.setattr(server, "get_cash_drawer", fake_get_cash_drawer)

    result = asyncio.run(
        server.withdraw_cash(
            server.StoreLocation.RUNNER,
            server.CashWithdrawal(amount=12.34, category="outros"),
        )
    )

    assert result["current_balance"] == 0.0
    assert len(withdrawals.inserted) == 1
    assert len(config.updated) == 1
    _, update, upsert = config.updated[0]
    assert upsert is True
    assert update["$set"]["balance"] == 0
    assert update["$set"]["last_reset_at"]
    assert update["$set"]["last_full_withdrawal"]["amount"] == 12.34


def test_r5_manual_cash_after_reset_counts_as_r5():
    reset = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)
    orders = [
        {
            "id": "old-order",
            "total": 99.55,
            "created_at": "2026-09-29T13:30:00+00:00",
            "manual_sale": False,
        },
        {
            "id": "new-r5",
            "total": 5.00,
            # Reporting date/shift can be earlier; cash_recorded_at is the real entry time.
            "created_at": "2026-09-29T09:00:00-03:00",
            "cash_recorded_at": "2026-09-29T14:01:00+00:00",
            "manual_sale": True,
        },
    ]

    filtered = server._filter_cash_orders_since(orders, reset)
    assert [item["id"] for item in filtered] == ["new-r5"]
    assert round(sum(item["total"] for item in filtered), 2) == 5.00
