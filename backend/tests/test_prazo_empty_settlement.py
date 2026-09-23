"""Receipt regression tests with in-memory data and no startup/network calls.

These tests cover no-op settlements, not Mongo multi-document atomicity.
"""
import os
import json
import multiprocessing
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MONGO_URL="mongodb://127.0.0.1:27017", DB_NAME="test_only",
                  LITELLM_LOCAL_MODEL_COST_MAP="True")
import server
from routers import prazo


class Orders:
    def __init__(self, documents=None, stale_snapshot=False):
        self.documents = documents if documents is not None else [
            {"id": "runner-order", "customer_name": "Cliente Teste", "store": "runner",
             "payment_method": "prazo", "prazo_paid": False, "total": 100, "partial_paid": 0}
        ]
        self.stale_snapshot = stale_snapshot

    def find(self, query, projection):
        documents = [dict(document) for document in self.documents
                     if document.get("store") == query["store"]
                     and document.get("payment_method") == "prazo"
                     and not document.get("prazo_paid")]

        class Cursor:
            async def to_list(self, limit):
                return documents[:limit]

        return Cursor()

    async def update_many(self, query, update):
        assert query["prazo_paid"] == {"$ne": True}
        assert update["$set"]["prazo_paid"] is True
        if self.stale_snapshot:
            return SimpleNamespace(modified_count=0)
        accepted_ids = set(query["id"]["$in"])
        changed = 0
        for document in self.documents:
            if (document.get("id") in accepted_ids and document.get("store") == query["store"]
                    and not document.get("prazo_paid")):
                document.update(update["$set"])
                changed += 1
        return SimpleNamespace(modified_count=changed)


class SettlementOperations:
    def __init__(self):
        self.documents = {}

    async def find_one(self, query, projection):
        document = self.documents.get(query["_id"])
        if not document:
            return None
        result = dict(document)
        if projection.get("_id") == 0:
            result.pop("_id", None)
        return result

    async def insert_one(self, document):
        if document["_id"] in self.documents:
            raise DuplicateKeyError("duplicate settlement operation")
        self.documents[document["_id"]] = dict(document)

    async def update_one(self, query, update):
        document = self.documents.get(query["_id"])
        if document and ("status" not in query or document.get("status") == query["status"]):
            document.update(update["$set"])
            return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)


class DurableSettlementOperations:
    """SQLite adapter used only to prove restart durability of Mongo's unique _id contract."""
    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    async def find_one(self, query, projection):
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT body FROM operations WHERE id=?", (query["_id"],)).fetchone()
        if not row:
            return None
        document = json.loads(row[0])
        if projection.get("_id") == 0:
            document.pop("_id", None)
        return document

    async def insert_one(self, document):
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute("INSERT INTO operations VALUES (?, ?)",
                                   (document["_id"], json.dumps(document)))
        except sqlite3.IntegrityError as exc:
            raise DuplicateKeyError("duplicate settlement operation") from exc

    async def update_one(self, query, update):
        with sqlite3.connect(self.path) as connection:
            row = connection.execute("SELECT body FROM operations WHERE id=?", (query["_id"],)).fetchone()
            if not row:
                return SimpleNamespace(modified_count=0)
            document = json.loads(row[0])
            if "status" in query and document.get("status") != query["status"]:
                return SimpleNamespace(modified_count=0)
            document.update(update["$set"])
            connection.execute("UPDATE operations SET body=? WHERE id=?",
                               (json.dumps(document), query["_id"]))
        return SimpleNamespace(modified_count=1)


class ForbiddenCollection:
    def __getattr__(self, name):
        raise AssertionError(f"Replay after restart accessed {name}")


def replay_after_restart(path, payload):
    server.db = SimpleNamespace(
        prazo_settlement_operations=DurableSettlementOperations(path),
        orders=ForbiddenCollection(), prazo_payments=ForbiddenCollection(),
    )
    server.PRAZO_PASSWORD = "isolated-test-password"
    response = TestClient(server.app).post("/api/prazo/pay-all/Cliente%20Teste", json=payload)
    assert response.status_code == 200
    assert response.json()["replayed"] is True


@pytest.fixture(params=[server, prazo], ids=["active-monolith", "modular-router"])
def api(request, monkeypatch):
    implementation = request.param
    receipts = AsyncMock()
    history = AsyncMock()
    database = SimpleNamespace(
        orders=Orders(), prazo_payments=receipts,
        prazo_settlement_operations=SettlementOperations(),
    )
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


def post(api, operation_id="11111111-1111-4111-8111-111111111111", **overrides):
    return api[0].post("/api/prazo/pay-all/Cliente%20Teste", json={
        "amount": 100, "password": "isolated-test-password",
        "payment_method": "cash", "store": "runner", "operation_id": operation_id,
        **overrides,
    })


def test_first_settlement_then_repeated_calls_record_only_100(api):
    _, database, history, implementation = api
    response = post(api)
    assert response.status_code == 200
    assert response.json()["orders_paid"] == 1
    for _ in range(4):
        replay = post(api)
        assert replay.status_code == 200
        assert replay.json()["replayed"] is True
    database.prazo_payments.insert_one.assert_awaited_once()
    receipt = database.prazo_payments.insert_one.await_args.args[0]
    assert receipt["amount"] == 100
    assert receipt["payment_method"] == "cash"
    assert receipt["store"] == "runner"
    if implementation is prazo:
        history.assert_awaited_once()


def test_customer_without_debt_cannot_create_receipt_or_history(api):
    _, database, history, _ = api
    database.orders.documents = []
    response = post(api, operation_id=str(uuid4()))
    assert response.status_code == 409
    assert "não possui débito" in response.json()["detail"]
    database.prazo_payments.insert_one.assert_not_awaited()
    history.assert_not_awaited()


def test_stale_read_cannot_create_receipt_after_zero_modified_orders(api):
    _, database, history, _ = api
    # Simulate another request paying between the initial read and write.
    database.orders = Orders(stale_snapshot=True)
    assert post(api, operation_id=str(uuid4())).status_code == 409
    database.prazo_payments.insert_one.assert_not_awaited()
    history.assert_not_awaited()


def test_same_name_in_another_store_is_not_settled(api):
    _, database, _, _ = api
    other_store = {"id": "gym-order", "customer_name": "Cliente Teste", "store": "gym-londres",
                   "payment_method": "prazo", "prazo_paid": False, "total": 300, "partial_paid": 0}
    database.orders.documents.append(other_store)
    response = post(api, operation_id=str(uuid4()))
    assert response.status_code == 200
    assert response.json()["amount"] == 100
    assert response.json()["store"] == "runner"
    assert other_store["prazo_paid"] is False


def test_receipt_uses_remaining_database_value_in_cents(api):
    _, database, _, _ = api
    database.orders.documents = [
        {"id": "one", "customer_name": "Cliente Teste", "store": "runner",
         "payment_method": "prazo", "prazo_paid": False, "total": 50.005, "partial_paid": 10},
        {"id": "two", "customer_name": "Cliente Teste", "store": "runner",
         "payment_method": "prazo", "prazo_paid": False, "total": 60.004, "partial_paid": 0},
    ]
    response = post(api, operation_id=str(uuid4()), amount=100.01)
    assert response.status_code == 200
    assert response.json()["amount"] == 100.01
    receipt = database.prazo_payments.insert_one.await_args.args[0]
    assert receipt["amount"] == 100.01


def test_stale_screen_amount_is_rejected_before_writing(api):
    _, database, history, _ = api
    response = post(api, operation_id=str(uuid4()), amount=99.99)
    assert response.status_code == 409
    assert "saldo mudou" in response.json()["detail"]
    assert database.orders.documents[0]["prazo_paid"] is False
    database.prazo_payments.insert_one.assert_not_awaited()
    history.assert_not_awaited()


@pytest.mark.parametrize("payload", [
    {"amount": 100, "password": "isolated-test-password", "payment_method": "cash"},
    {"amount": 100, "password": "isolated-test-password", "payment_method": "cash", "store": "unknown"},
])
def test_missing_or_unknown_store_is_rejected_before_database(api, payload):
    class ForbiddenDatabase:
        def __getattr__(self, name):
            raise AssertionError("Invalid store reached the database")

    client, database, history, _ = api
    database.orders = ForbiddenDatabase()
    response = client.post("/api/prazo/pay-all/Cliente%20Teste", json=payload)
    assert response.status_code == 422
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


def test_completed_operation_conflicting_payload_is_rejected(api):
    operation_id = str(uuid4())
    assert post(api, operation_id=operation_id).status_code == 200
    conflict = post(api, operation_id=operation_id, amount=101)
    assert conflict.status_code == 409
    assert "dados diferentes" in conflict.json()["detail"]
    api[1].prazo_payments.insert_one.assert_awaited_once()


def test_incomplete_operation_is_not_replayed_or_recreated(api):
    operation_id = str(uuid4())
    key = f"prazo-full:runner:{operation_id}"
    api[1].prazo_settlement_operations.documents[key] = {
        "_id": key, "operation_id": operation_id, "customer_key": "cliente teste",
        "requested_cents": 10000, "payment_method": "cash", "status": "pending",
    }
    response = post(api, operation_id=operation_id)
    assert response.status_code == 409
    assert "incompleta" in response.json()["detail"]
    assert api[1].orders.documents[0]["prazo_paid"] is False
    api[1].prazo_payments.insert_one.assert_not_awaited()


def test_completed_operation_survives_process_restart(api, tmp_path):
    operation_id = str(uuid4())
    path = tmp_path / "settlements.sqlite"
    api[1].prazo_settlement_operations = DurableSettlementOperations(path)
    first = post(api, operation_id=operation_id)
    assert first.status_code == 200
    payload = {
        "amount": 100, "password": "isolated-test-password", "payment_method": "cash",
        "store": "runner", "operation_id": operation_id,
    }
    process = multiprocessing.get_context("spawn").Process(
        target=replay_after_restart, args=(str(path), payload)
    )
    process.start()
    process.join(20)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("Restart replay test timed out")
    assert process.exitcode == 0
    api[1].prazo_payments.insert_one.assert_awaited_once()
