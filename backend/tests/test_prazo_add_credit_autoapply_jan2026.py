"""
Tests for POST /api/prazo/customers/{id}/add-credit AUTO-APPLY behavior.
Iteration 6 - Jan 2026.

Scenarios:
  T1 - R$35 over (30 + 20) debt -> 1 paid off, 1 partial=5, credit=0
  T2 - R$50 over R$15 remaining debt -> all paid, excess 35 to credit
  T3 - R$100 on debtless customer -> 100 fully to credit
  T4 - amount <= 0 returns 400
  T5 - non-existent customer returns 404
  T6 - prazo_partial_payments collection populated with source='credit_auto_apply'
  T7 - GET /api/prazo/debts reflects reduced debts (subtracts partial_paid)
  T8 - Customer lookup via GET /api/prazo/customers shows updated credit
  T9 - Credit on customer with all debt paid -> 100% to balance
  T10 - Case-insensitive regex match on customer name with accents/uppercase
"""

import os
import uuid
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback used inside the container; the public URL is preferred.
    BASE_URL = "http://localhost:8001"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ganoh_db")
AUTH = ("gestor", "test-only-value")

TEST_PREFIX = "TEST_PRAZO_CRED_"


# ----------------------------- Fixtures -----------------------------

@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(autouse=True)
def cleanup(mongo_db):
    """Cleanup TEST_ prefixed data before and after every test."""
    def _wipe():
        mongo_db.prazo_customers.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
        mongo_db.orders.delete_many({"customer_name": {"$regex": f"^{TEST_PREFIX}"}})
        mongo_db.prazo_partial_payments.delete_many({"customer_name": {"$regex": f"^{TEST_PREFIX}"}})
        mongo_db.prazo_history.delete_many({"customer_name": {"$regex": f"^{TEST_PREFIX}"}})
    _wipe()
    yield
    _wipe()


# ----------------------------- Helpers ------------------------------

def make_customer(suffix: str = "", store: str = "runner", credit: float = 0.0):
    """Create a prazo customer via the API. Returns the customer dict (with id)."""
    name = f"{TEST_PREFIX}{suffix}_{uuid.uuid4().hex[:6]}"
    payload = {"name": name, "phone": "11999999999", "notes": "", "credit": credit, "store": store}
    r = requests.post(f"{BASE_URL}/api/prazo/customers", json=payload, auth=AUTH, timeout=15)
    assert r.status_code == 200, f"create_customer failed: {r.status_code} {r.text}"
    return r.json()


def insert_unpaid_order(mongo_db, customer_name: str, total: float, store: str = "runner",
                       created_offset_seconds: int = 0):
    """Insert an unpaid prazo order directly in mongo with controllable creation time."""
    order_id = str(uuid.uuid4())
    created_at = (datetime.now(timezone.utc) + timedelta(seconds=created_offset_seconds)).isoformat()
    mongo_db.orders.insert_one({
        "id": order_id,
        "customer_name": customer_name,
        "payment_method": "prazo",
        "prazo_paid": False,
        "total": total,
        "partial_paid": 0,
        "items": [{"name": "Item Teste", "price": total, "quantity": 1}],
        "store": store,
        "created_at": created_at,
        "status": "completed",
    })
    return order_id


def get_customer_by_id(customer_id: str):
    r = requests.get(f"{BASE_URL}/api/prazo/customers", timeout=15)
    assert r.status_code == 200
    for c in r.json().get("customers", []):
        if c.get("id") == customer_id:
            return c
    return None


def add_credit(customer_id: str, amount: float, notes: str = ""):
    return requests.post(
        f"{BASE_URL}/api/prazo/customers/{customer_id}/add-credit",
        json={"amount": amount, "notes": notes},
        timeout=15,
    )


# ----------------------------- Tests --------------------------------

# T1: R$35 over (R$30 oldest + R$20 newest) debt
class TestAddCreditAutoApply:

    def test_t1_partial_payoff_first_order(self, mongo_db):
        cust = make_customer("T1")
        oid_old = insert_unpaid_order(mongo_db, cust["name"], 30.0, created_offset_seconds=-3600)
        oid_new = insert_unpaid_order(mongo_db, cust["name"], 20.0, created_offset_seconds=-60)

        r = add_credit(cust["id"], 35.0)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["success"] is True
        assert data["applied_to_debt"] == 35.0
        assert data["orders_paid_off"] == 1
        assert data["remaining_credit_added"] == 0
        assert data["new_credit"] == 0

        # DB state
        o1 = mongo_db.orders.find_one({"id": oid_old})
        o2 = mongo_db.orders.find_one({"id": oid_new})
        assert o1["prazo_paid"] is True
        assert round(o1["partial_paid"], 2) == 30.0
        assert o2.get("prazo_paid", False) is False
        assert round(o2["partial_paid"], 2) == 5.0

    def test_t2_excess_goes_to_credit(self, mongo_db):
        cust = make_customer("T2")
        # Single order R$15 unpaid (simulating remaining after T1 scenario)
        oid = insert_unpaid_order(mongo_db, cust["name"], 15.0, created_offset_seconds=-60)
        r = add_credit(cust["id"], 50.0)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["applied_to_debt"] == 15.0
        assert data["orders_paid_off"] == 1
        assert data["remaining_credit_added"] == 35.0
        assert data["new_credit"] == 35.0

        o = mongo_db.orders.find_one({"id": oid})
        assert o["prazo_paid"] is True
        c = get_customer_by_id(cust["id"])
        assert c is not None and round(c["credit"], 2) == 35.0

    def test_t3_no_debt_full_credit(self):
        cust = make_customer("T3")
        r = add_credit(cust["id"], 100.0)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["applied_to_debt"] == 0
        assert data["orders_paid_off"] == 0
        assert data["remaining_credit_added"] == 100.0
        assert data["new_credit"] == 100.0

        c = get_customer_by_id(cust["id"])
        assert round(c["credit"], 2) == 100.0

    def test_t4_invalid_amount_zero(self):
        cust = make_customer("T4a")
        r = add_credit(cust["id"], 0)
        assert r.status_code == 400
        assert "maior que zero" in r.json().get("detail", "").lower()

    def test_t4_invalid_amount_negative(self):
        cust = make_customer("T4b")
        r = add_credit(cust["id"], -5)
        assert r.status_code == 400

    def test_t5_nonexistent_customer(self):
        r = add_credit("does-not-exist-xyz", 10.0)
        assert r.status_code == 404
        assert "não encontrado" in r.json().get("detail", "").lower()

    def test_t6_partial_payments_collection_populated(self, mongo_db):
        cust = make_customer("T6")
        oid1 = insert_unpaid_order(mongo_db, cust["name"], 30.0, created_offset_seconds=-3600)
        oid2 = insert_unpaid_order(mongo_db, cust["name"], 20.0, created_offset_seconds=-60)
        r = add_credit(cust["id"], 35.0, notes="autotest-T6")
        assert r.status_code == 200

        recs = list(mongo_db.prazo_partial_payments.find(
            {"customer_id": cust["id"]}, {"_id": 0}
        ))
        assert len(recs) == 2, f"Expected 2 partial_payments records, got {len(recs)}: {recs}"
        for rec in recs:
            assert rec["type"] == "partial_payment"
            assert rec["source"] == "credit_auto_apply"
            assert rec["customer_name"] == cust["name"]
            assert rec["order_id"] in (oid1, oid2)
        total_recorded = sum(r["amount"] for r in recs)
        assert round(total_recorded, 2) == 35.0

    def test_t7_debts_endpoint_reflects_reduction(self, mongo_db):
        cust = make_customer("T7", store="runner")
        insert_unpaid_order(mongo_db, cust["name"], 30.0, store="runner", created_offset_seconds=-3600)
        insert_unpaid_order(mongo_db, cust["name"], 20.0, store="runner", created_offset_seconds=-60)

        # Total before = 50
        r0 = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner", timeout=15)
        debts0 = {d["name"]: d for d in r0.json()["debts"]}
        assert cust["name"] in debts0
        assert round(debts0[cust["name"]]["total"], 2) == 50.0

        # Apply 35
        add_credit(cust["id"], 35.0).raise_for_status()

        r1 = requests.get(f"{BASE_URL}/api/prazo/debts?store=runner", timeout=15)
        debts1 = {d["name"]: d for d in r1.json()["debts"]}
        assert cust["name"] in debts1
        # 50 - 35 = 15 remaining
        assert round(debts1[cust["name"]]["total"], 2) == 15.0
        # Only the newer order remains
        assert debts1[cust["name"]]["order_count"] == 1

    def test_t8_get_customers_shows_updated_credit(self):
        cust = make_customer("T8")
        add_credit(cust["id"], 42.5).raise_for_status()
        c = get_customer_by_id(cust["id"])
        assert c is not None
        assert round(c["credit"], 2) == 42.5

    def test_t9_subsequent_credit_after_debt_cleared(self, mongo_db):
        cust = make_customer("T9")
        insert_unpaid_order(mongo_db, cust["name"], 20.0, created_offset_seconds=-60)
        # Clear debt
        r1 = add_credit(cust["id"], 20.0)
        assert r1.status_code == 200
        assert r1.json()["applied_to_debt"] == 20.0
        assert r1.json()["new_credit"] == 0

        # Now add credit again - no debt should remain
        r2 = add_credit(cust["id"], 50.0)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["applied_to_debt"] == 0
        assert d2["remaining_credit_added"] == 50.0
        assert d2["new_credit"] == 50.0

    def test_t10_case_insensitive_name_lookup(self, mongo_db):
        # Customer name with accent + mixed case. Orders inserted with different case.
        suffix = uuid.uuid4().hex[:6]
        name = f"{TEST_PREFIX}AcÉntÚado_{suffix}"
        payload = {"name": name, "phone": "11", "notes": "", "credit": 0, "store": "runner"}
        r = requests.post(f"{BASE_URL}/api/prazo/customers", json=payload, auth=AUTH, timeout=15)
        assert r.status_code == 200
        cust = r.json()
        # Insert orders with different case (lowercase)
        mongo_db.orders.insert_one({
            "id": str(uuid.uuid4()),
            "customer_name": name.lower(),
            "payment_method": "prazo",
            "prazo_paid": False,
            "total": 25.0,
            "partial_paid": 0,
            "items": [],
            "store": "runner",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        r2 = add_credit(cust["id"], 25.0)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        # Should find via case-insensitive regex
        assert data["applied_to_debt"] == 25.0
        assert data["orders_paid_off"] == 1
