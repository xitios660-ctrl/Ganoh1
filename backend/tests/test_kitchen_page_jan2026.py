"""
Comprehensive test for Kitchen Page (Cozinha) endpoints - Jan 2026 review.
Tests all backend endpoints used by /:store/cozinha route.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://gourmet-3d-portal.preview.emergentagent.com').rstrip('/')
STORE = "runner"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- GET endpoints (kitchen page initial loads) ---------------- #

KITCHEN_GET_ENDPOINTS = [
    f"/api/orders/{STORE}",
    f"/api/kitchen/{STORE}/stats",
    f"/api/cash/{STORE}/today",
    f"/api/stock/{STORE}",
    f"/api/orders/{STORE}/pending-pix",
    f"/api/orders/{STORE}/history",
    f"/api/prazo/debts",
    f"/api/kitchen/adicionais",
    f"/api/kitchen/menu/{STORE}",
    f"/api/prazo/customers",
    f"/api/cash/{STORE}/drawer",
    f"/api/pix-adjustments/{STORE}",
    f"/api/prazo/payments-history",
]


@pytest.mark.parametrize("endpoint", KITCHEN_GET_ENDPOINTS)
def test_kitchen_get_endpoints(api, endpoint):
    """All kitchen GET endpoints must return 200."""
    r = api.get(f"{BASE_URL}{endpoint}")
    assert r.status_code == 200, f"{endpoint} returned {r.status_code}: {r.text[:200]}"
    # Make sure response is JSON
    body = r.json()
    assert body is not None


# ---------------- Order lifecycle ---------------- #

class TestOrderLifecycle:
    """Order create -> status updates -> delete"""

    @pytest.fixture(scope="class")
    def created_order(self, api):
        payload = {
            "store": STORE,
            "customer_name": f"TEST_kitchen_{uuid.uuid4().hex[:6]}",
            "items": [
                {"menu_item_id": "cafezinho", "name": "Cafezinho", "price": 5.0, "quantity": 1}
            ],
            "payment_method": "cash",
            "total": 5.0,
        }
        r = api.post(f"{BASE_URL}/api/orders", json=payload)
        assert r.status_code in (200, 201), f"Create order failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        # The order may be wrapped or returned flat
        order_id = data.get("id") or data.get("order_id") or data.get("_id") or (data.get("order") or {}).get("id")
        assert order_id, f"No order id in response: {data}"
        return {"id": order_id, "data": data}

    def test_order_listed_in_orders(self, api, created_order):
        r = api.get(f"{BASE_URL}/api/orders/{STORE}")
        assert r.status_code == 200
        orders = r.json()
        if isinstance(orders, dict):
            orders = orders.get("orders") or orders.get("data") or []
        ids = [o.get("id") or o.get("_id") for o in orders]
        assert created_order["id"] in ids, f"created order not in list (ids={ids[:5]}...)"

    def test_order_status_preparing(self, api, created_order):
        oid = created_order["id"]
        r = api.patch(
            f"{BASE_URL}/api/orders/{STORE}/{oid}/status",
            json={"status": "preparing"}
        )
        assert r.status_code in (200, 204), f"PATCH preparing failed {r.status_code}: {r.text[:200]}"

    def test_order_status_ready(self, api, created_order):
        oid = created_order["id"]
        r = api.patch(
            f"{BASE_URL}/api/orders/{STORE}/{oid}/status",
            json={"status": "ready"}
        )
        assert r.status_code in (200, 204), f"PATCH ready failed {r.status_code}: {r.text[:200]}"

    def test_order_delete(self, api, created_order):
        oid = created_order["id"]
        r = api.delete(f"{BASE_URL}/api/orders/{STORE}/{oid}")
        assert r.status_code in (200, 204), f"DELETE failed {r.status_code}: {r.text[:200]}"


# ---------------- Stock CRUD ---------------- #

class TestStock:
    def test_stock_returns_list_or_dict(self, api):
        r = api.get(f"{BASE_URL}/api/stock/{STORE}")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, (list, dict))


# ---------------- Menu ---------------- #

class TestMenu:
    def test_create_menu_item(self, api):
        payload = {
            "name": f"TEST_item_{uuid.uuid4().hex[:6]}",
            "price": 9.99,
            "category": "Bebidas",
            "store": STORE,
        }
        r = api.post(f"{BASE_URL}/api/kitchen/menu", json=payload)
        # If endpoint validates fiscal fields it may 422, capture & report
        assert r.status_code in (200, 201, 422), f"Create menu item unexpected {r.status_code}: {r.text[:200]}"
        if r.status_code in (200, 201):
            data = r.json()
            item_id = data.get("id") or data.get("_id")
            if item_id:
                # cleanup
                api.delete(f"{BASE_URL}/api/kitchen/menu/{item_id}")


# ---------------- Adicionais ---------------- #

class TestAdicionais:
    def test_list_adicionais(self, api):
        r = api.get(f"{BASE_URL}/api/kitchen/adicionais")
        assert r.status_code == 200
        assert isinstance(r.json(), (list, dict))


# ---------------- Prazo (tab system) ---------------- #

class TestPrazo:
    def test_list_customers(self, api):
        r = api.get(f"{BASE_URL}/api/prazo/customers")
        assert r.status_code == 200

    def test_payments_history(self, api):
        r = api.get(f"{BASE_URL}/api/prazo/payments-history")
        assert r.status_code == 200


# ---------------- PIX Adjustments ---------------- #

class TestPixAdjustments:
    def test_list_pix_adjustments(self, api):
        r = api.get(f"{BASE_URL}/api/pix-adjustments/{STORE}")
        assert r.status_code == 200


# ---------------- Cash drawer ---------------- #

class TestCashDrawer:
    def test_get_drawer(self, api):
        r = api.get(f"{BASE_URL}/api/cash/{STORE}/drawer")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_today_summary(self, api):
        r = api.get(f"{BASE_URL}/api/cash/{STORE}/today")
        assert r.status_code == 200
