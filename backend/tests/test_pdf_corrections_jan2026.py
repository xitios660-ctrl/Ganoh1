"""Tests for PDF corrections applied to both stores (Runner + GYM Londres) - Jan 2026.

Covers: menu dedup, test-item filtering, adicionais dedup, tenant auth (new password,
old password rejection, account enumeration prevention), prazo customer lookup
(min 2 chars + masked phone), auto-archive of stale ready orders, and kitchen
stats consistency.
"""

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

# Mongo direct access (for arrange + cleanup of stale-order test)
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


# ============ MENU: category dedup + filtering ============
@pytest.mark.parametrize("store", ["runner", "gym-londres"])
class TestMenuDedup:
    def test_categories_no_duplicates_case_insensitive(self, http, store):
        r = http.get(f"{API}/menu/{store}")
        assert r.status_code == 200, r.text
        data = r.json()
        cats = data.get("categories", [])
        lows = [c.lower() for c in cats]
        assert len(lows) == len(set(lows)), f"Duplicate cats: {cats}"

    def test_no_bebidas_or_sucos_duplicate(self, http, store):
        cats = http.get(f"{API}/menu/{store}").json().get("categories", [])
        lows = [c.lower() for c in cats]
        # 'bebidas' alone must not coexist with 'bebidas geladas'
        assert not ("bebidas" in lows and "bebidas geladas" in lows)
        # 'sucos e vitaminas' duplicates (with E maiúsculo) must be merged
        sucos = [c for c in cats if "sucos" in c.lower() and "vitamina" in c.lower()]
        assert len(sucos) <= 1, f"Duplicated sucos cat: {sucos}"
        # 'Omeletes, Tapiocas E Crepiocas' duplicated form must not appear with lower-case 'e'
        omeletes = [c for c in cats if "omelete" in c.lower()]
        assert len(omeletes) <= 1, f"Duplicate omelete cat: {omeletes}"

    def test_no_test_items_in_menu(self, http, store):
        items = http.get(f"{API}/menu/{store}").json().get("items", [])
        for it in items:
            name = (it.get("name") or "").lower()
            assert not any(t in name for t in ("promo", "promoção", "teste", "placeholder")), it
            price = float(it.get("price") or 0)
            # Only flag items below R$1.00 that are not free / zero (zero = unset)
            assert not (0 < price < 1.0), f"Test item leaked: {it}"

    def test_adicionais_deduplicated(self, http, store):
        adicionais = http.get(f"{API}/menu/{store}").json().get("adicionais", [])
        names = [(a.get("name") or "").strip().lower() for a in adicionais]
        assert len(names) == len(set(names)), f"Dup adicionais: {names}"
        # Nutella and Queijo Branco must appear at most once each
        assert names.count("nutella") <= 1
        assert names.count("queijo branco") <= 1


# ============ AUTH ============
class TestAuth:
    def test_login_with_new_password(self, http):
        r = http.post(f"{API}/auth/login", json={"username": "gestor", "password": "test-only-value"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True
        assert data.get("tenant_id")
        assert data.get("username") == "gestor"

    def test_login_with_old_password_rejected(self, http):
        r = http.post(f"{API}/auth/login", json={"username": "gestor", "password": "test-only-value"})
        assert r.status_code == 401

    def test_accounts_endpoint_does_not_expose_usernames(self, http):
        r = http.get(f"{API}/auth/accounts")
        assert r.status_code == 200
        data = r.json()
        assert data.get("accounts") == [], f"Should be empty list, got: {data.get('accounts')}"
        assert isinstance(data.get("count"), int)
        assert data.get("count") >= 1
        # Ensure no usernames leaked anywhere in payload
        payload_str = str(data).lower()
        assert "gestor" not in payload_str
        assert "display_name" not in data


# ============ PRAZO CUSTOMERS LOOKUP ============
class TestPrazoLookup:
    def test_empty_q_returns_empty(self, http):
        r = http.get(f"{API}/prazo/customers/lookup")
        assert r.status_code == 200
        assert r.json().get("customers") == []

    def test_one_char_q_returns_empty(self, http):
        r = http.get(f"{API}/prazo/customers/lookup", params={"q": "a"})
        assert r.status_code == 200
        assert r.json().get("customers") == []

    def test_valid_q_returns_masked_phone_only(self, http, mongo):
        # Seed a customer to ensure we have something to match
        test_name = f"TEST_Joao_{uuid.uuid4().hex[:6]}"
        full_phone = "11987654321"
        mongo.prazo_customers.insert_one({
            "id": str(uuid.uuid4()),
            "name": test_name,
            "phone": full_phone,
            "store": "runner",
            "credit": 0,
            "debt": 0,
        })
        try:
            r = http.get(f"{API}/prazo/customers/lookup", params={"q": "TEST_Joao"})
            assert r.status_code == 200
            customers = r.json().get("customers", [])
            assert len(customers) >= 1
            found = next((c for c in customers if c.get("name") == test_name), None)
            assert found is not None, customers
            # phone must NOT appear, only phone_masked
            assert "phone" not in found or found.get("phone") is None
            assert "phone_masked" in found
            masked = found["phone_masked"]
            assert full_phone not in masked
            assert masked.endswith("4321")
            assert "•" in masked
            # No credit/debt/financial info
            for forbidden in ("credit", "debt", "history", "notes"):
                assert forbidden not in found, f"Leaked: {forbidden} in {found}"
        finally:
            mongo.prazo_customers.delete_many({"name": test_name})


# ============ AUTO-ARCHIVE OF STALE READY ORDERS + KITCHEN STATS ============
class TestStaleReadyAutoArchive:
    def test_ready_older_than_12h_is_auto_archived_and_stats_consistent(self, http, mongo):
        store = "runner"
        old_id = f"TEST_stale_{uuid.uuid4().hex[:8]}"
        fresh_id = f"TEST_fresh_{uuid.uuid4().hex[:8]}"
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=13)).isoformat()
        fresh_ts = datetime.now(timezone.utc).isoformat()

        common = {
            "store": store,
            "customer_name": "TEST_Customer",
            "items": [{"menu_item_id": "1", "name": "Test", "price": 1.0, "quantity": 1}],
            "total": 1.0,
            "payment_method": "cash",
            "status": "ready",
            "prep_time": 15,
            "synced": True,
        }
        mongo.orders.insert_one({**common, "id": old_id, "created_at": old_ts, "updated_at": old_ts})
        mongo.orders.insert_one({**common, "id": fresh_id, "created_at": fresh_ts, "updated_at": fresh_ts})

        try:
            r = http.get(f"{API}/orders/{store}", params={"status": "ready"})
            assert r.status_code == 200
            ids = [o.get("id") for o in r.json().get("orders", [])]
            assert old_id not in ids, "Stale ready order was NOT auto-archived"
            assert fresh_id in ids, "Fresh ready order was incorrectly removed"

            # Old order should now be in history
            hist = mongo.order_history.find_one({"id": old_id})
            assert hist is not None, "Auto-archived order not found in order_history"
            assert hist.get("status") == "delivered"

            # Kitchen stats should NOT count the stale one
            r2 = http.get(f"{API}/kitchen/{store}/stats")
            assert r2.status_code == 200
            stats = r2.json()
            # The exact field name may vary; ensure ready count corresponds to current ready list size
            current_ready_ids = [
                o.get("id") for o in http.get(f"{API}/orders/{store}", params={"status": "ready"}).json().get("orders", [])
            ]
            # Find a "ready" count field
            ready_count = None
            for k in ("ready", "ready_count", "ready_orders", "ready_total"):
                if k in stats:
                    ready_count = stats[k]
                    break
            if ready_count is None:
                # Search nested
                for v in stats.values():
                    if isinstance(v, dict) and "ready" in v:
                        ready_count = v["ready"]
                        break
            assert ready_count is not None, f"Could not find ready count in stats: {stats}"
            assert ready_count == len(current_ready_ids), (
                f"Stats ready={ready_count} but live list has {len(current_ready_ids)}"
            )
        finally:
            mongo.orders.delete_many({"id": {"$in": [old_id, fresh_id]}})
            mongo.order_history.delete_many({"id": {"$in": [old_id, fresh_id]}})
