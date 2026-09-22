"""Receipt regression tests with in-memory data and no startup/network calls.

These tests cover no-op settlements, not Mongo multi-document atomicity.
"""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MONGO_URL="mongodb://127.0.0.1:27017", DB_NAME="test_only",
                  LITELLM_LOCAL_MODEL_COST_MAP="True")
import server
from routers import prazo


class Orders:
    def __init__(self, unpaid=1, stale_snapshot=False):
        self.unpaid = unpaid
        self.stale_snapshot = stale_snapshot

    async def find_one(self, query, projection):
        return {"store": "runner"} if self.unpaid or self.stale_snapshot else None

    async def update_many(self, query, update):
        assert query["prazo_paid"] == {"$ne": True}
        assert update["$set"]["prazo_paid"] is True
        changed = self.unpaid
        self.unpaid = 0
        return SimpleNamespace(modified_count=changed)


@pytest.fixture(params=[server, prazo], ids=["active-monolith", "modular-router"])
def api(request, monkeypatch):
    implementation = request.param
    receipts = AsyncMock()
    history = AsyncMock()
    database = SimpleNamespace(orders=Orders(), prazo_payments=receipts)
    monkeypatch.setattr(implementation, "db", database)
    monkeypatch.setattr(implementation, "PRAZO_PASSWORD", "isolated-test-password")
    if implementation is server:
        app = server.app
    else:
        monkeypatch.setattr(prazo, "_log_prazo_event", history)
        app = FastAPI()
        app.include_router(prazo.router, prefix="/api")
    # Do not enter TestClient as a context manager: production startup stays off.
    return TestClient(app), database, history, implementation


def post(api, **overrides):
    return api[0].post("/api/prazo/pay-all/Cliente%20Teste", json={
        "amount": 100, "password": "isolated-test-password",
        "payment_method": "cash", **overrides,
    })


def test_first_settlement_then_repeated_calls_record_only_100(api):
    _, database, history, implementation = api
    response = post(api)
    assert response.status_code == 200
    assert response.json()["orders_paid"] == 1
    for _ in range(4):
        assert post(api).status_code == 409
    database.prazo_payments.insert_one.assert_awaited_once()
    receipt = database.prazo_payments.insert_one.await_args.args[0]
    assert receipt["amount"] == 100
    assert receipt["payment_method"] == "cash"
    assert receipt["store"] == "runner"
    if implementation is prazo:
        history.assert_awaited_once()


def test_customer_without_debt_cannot_create_receipt_or_history(api):
    _, database, history, _ = api
    database.orders.unpaid = 0
    response = post(api)
    assert response.status_code == 409
    assert "Confira o histórico" in response.json()["detail"]
    database.prazo_payments.insert_one.assert_not_awaited()
    history.assert_not_awaited()


def test_stale_read_cannot_create_receipt_after_zero_modified_orders(api):
    _, database, history, _ = api
    # Simulate another request paying between the initial read and write.
    database.orders = Orders(unpaid=0, stale_snapshot=True)
    assert post(api).status_code == 409
    database.prazo_payments.insert_one.assert_not_awaited()
    history.assert_not_awaited()


def test_password_check_still_precedes_any_database_access(api):
    class ForbiddenDatabase:
        def __getattr__(self, name):
            raise AssertionError("Invalid password reached the database")

    client, database, history, _ = api
    database.orders = ForbiddenDatabase()
    assert post(api, password="wrong").status_code == 403
    database.prazo_payments.insert_one.assert_not_awaited()
    history.assert_not_awaited()
