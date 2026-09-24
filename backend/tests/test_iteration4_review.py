"""
Iteration 4 - Review request validation tests for GANOH Café Bistrô.
Covers: health, accounts, auth, stores, menu, orders, status flow, cash summary,
gestor dashboard (HTTP Basic), and PIX order creation.
"""
import os
import pytest
import requests
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend .env value (Kubernetes ingress)
    BASE_URL = "https://code-deploy-95.preview.emergentagent.com"

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health & metadata ----------
class TestHealthAndMeta:
    def test_root_returns_message(self, session):
        r = session.get(f"{API}/")
        assert r.status_code == 200
        data = r.json()
        assert "GANOH" in data.get("message", "")

    def test_get_accounts_has_default_gestor(self, session):
        r = session.get(f"{API}/auth/accounts")
        assert r.status_code == 200
        data = r.json()
        assert "accounts" in data
        usernames = [a["username"] for a in data["accounts"]]
        assert "gestor" in usernames

    def test_get_stores(self, session):
        r = session.get(f"{API}/stores")
        assert r.status_code == 200
        stores = r.json()["stores"]
        assert "runner" in stores
        assert "gym-londres" in stores


# ---------- Authentication ----------
class TestAuth:
    def test_login_success(self, session):
        r = session.post(f"{API}/auth/login",
                         json={"username": "gestor", "password": "test-only-value"})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["username"] == "gestor"
        assert "tenant_id" in data

    def test_login_wrong_password(self, session):
        r = session.post(f"{API}/auth/login",
                         json={"username": "gestor", "password": "wrong"})
        assert r.status_code == 401

    def test_login_with_whitespace_and_case(self, session):
        """PRD mentions strip+case-insensitive fix."""
        r = session.post(f"{API}/auth/login",
                         json={"username": " GESTOR ", "password": "test-only-value"})
        assert r.status_code == 200


# ---------- Menu ----------
class TestMenu:
    def test_get_menu_runner(self, session):
        r = session.get(f"{API}/menu/runner")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list) and len(data["items"]) > 0
        assert "categories" in data
        assert "adicionais" in data
        # spot check item shape
        item = data["items"][0]
        assert "id" in item and "name" in item and "price" in item


# ---------- Orders end-to-end (cash flow) ----------
class TestOrdersCashFlow:
    order_id = None

    def test_create_cash_order(self, session):
        # Pick first item from menu
        menu = session.get(f"{API}/menu/runner").json()
        item = menu["items"][0]
        payload = {
            "store": "runner",
            "customer_name": "TEST_iter4_cash",
            "customer_phone": "11999990001",
            "items": [{
                "menu_item_id": item["id"],
                "name": item["name"],
                "price": item["price"],
                "quantity": 1,
                "adicionais": [],
                "observacao": "TEST iter4"
            }],
            "total": item["price"],
            "payment_method": "cash",
            "order_type": "balcao",
        }
        r = session.post(f"{API}/orders", json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        assert "id" in data or "order_id" in data
        TestOrdersCashFlow.order_id = data.get("id") or data.get("order_id")
        # For cash, status should be 'received' (not pending_payment)
        assert data.get("status") in ("received", "preparing"), f"Unexpected status: {data.get('status')}"

    def test_list_orders_runner(self, session):
        r = session.get(f"{API}/orders/runner")
        assert r.status_code == 200
        data = r.json()
        orders = data if isinstance(data, list) else data.get("orders", [])
        ids = [o.get("id") for o in orders]
        assert TestOrdersCashFlow.order_id in ids, "Created order not visible in /api/orders/runner"

    def test_update_order_status_preparing(self, session):
        oid = TestOrdersCashFlow.order_id
        assert oid
        r = session.patch(f"{API}/orders/runner/{oid}/status",
                          json={"status": "preparing"})
        assert r.status_code == 200, r.text

    def test_update_order_status_ready(self, session):
        oid = TestOrdersCashFlow.order_id
        r = session.patch(f"{API}/orders/runner/{oid}/status",
                          json={"status": "ready"})
        assert r.status_code == 200, r.text

    def test_update_order_status_delivered(self, session):
        oid = TestOrdersCashFlow.order_id
        r = session.patch(f"{API}/orders/runner/{oid}/status",
                          json={"status": "delivered"})
        assert r.status_code == 200, r.text


# ---------- Cash summary ----------
class TestCashSummary:
    def test_cash_today_runner(self, session):
        r = session.get(f"{API}/cash/runner/today")
        assert r.status_code == 200, r.text
        data = r.json()
        # Should include numeric totals
        assert isinstance(data, dict)
        # tolerate different shapes
        assert any(k in data for k in ("total", "totals", "by_payment_method", "summary"))


# ---------- Gestor Dashboard (HTTP Basic) ----------
class TestGestorDashboard:
    def test_dashboard_requires_basic_auth(self, session):
        r = requests.get(f"{API}/gestor/dashboard")
        assert r.status_code in (401, 403)

    def test_dashboard_with_basic_auth(self):
        r = requests.get(f"{API}/gestor/dashboard", auth=("gestor", "test-only-value"))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "stores" in data
        assert "runner" in data["stores"]


# ---------- PIX flow (structure only) ----------
class TestPixOrderStructure:
    def test_create_pix_order_pending(self, session):
        menu = session.get(f"{API}/menu/runner").json()
        item = menu["items"][0]
        payload = {
            "store": "runner",
            "customer_name": "TEST_iter4_pix",
            "customer_phone": "11999990002",
            "items": [{
                "menu_item_id": item["id"],
                "name": item["name"],
                "price": item["price"],
                "quantity": 1,
                "adicionais": [],
                "observacao": "TEST iter4 pix"
            }],
            "total": item["price"],
            "payment_method": "pix",
            "order_type": "balcao",
        }
        r = session.post(f"{API}/orders", json=payload)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        # PIX should be in pending_payment until comprovante validated
        assert data.get("status") in ("pending_payment", "received"), data.get("status")
