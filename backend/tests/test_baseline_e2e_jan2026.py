"""
Baseline E2E test suite — GANOH Café Bistrô (Jan 2026)
Covers required endpoints from review_request: root, menu, orders, prazo, cash, auth/login.
Whatsapp is intentionally OUT OF SCOPE.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://kitchen-order-system-6.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- root / health ----------
def test_root(session):
    r = session.get(f"{API}/")
    assert r.status_code == 200
    assert "GANOH" in r.json().get("message", "")


# ---------- stores ----------
def test_stores(session):
    r = session.get(f"{API}/stores")
    assert r.status_code == 200
    stores = r.json().get("stores", {})
    assert "runner" in stores and "gym-londres" in stores


# ---------- menu ----------
@pytest.mark.parametrize("store", ["runner", "gym-londres"])
def test_menu_per_store(session, store):
    r = session.get(f"{API}/menu/{store}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data.get("items"), list) and len(data["items"]) > 10
    assert isinstance(data.get("categories"), list) and len(data["categories"]) > 0
    assert isinstance(data.get("adicionais"), list)
    assert data.get("store", {}).get("name", "").startswith("GANOH")


# ---------- auth/login ----------
def test_auth_login_success(session):
    r = session.post(f"{API}/auth/login", json={"username": GESTOR_USER, "password": GESTOR_PASS})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True
    assert data.get("username") == "gestor"


def test_auth_login_invalid(session):
    r = session.post(f"{API}/auth/login", json={"username": "gestor", "password": "wrong"})
    assert r.status_code == 401


def test_auth_login_trim_whitespace(session):
    # mobile keyboards add a space sometimes; backend trims
    r = session.post(f"{API}/auth/login", json={"username": "  Gestor  ", "password": " ganoh2024 "})
    assert r.status_code == 200


def test_auth_accounts_list(session):
    r = session.get(f"{API}/auth/accounts")
    assert r.status_code == 200
    body = r.json()
    assert "accounts" in body and "max_accounts" in body


# ---------- categories ----------
def test_categories(session):
    r = session.get(f"{API}/categories")
    assert r.status_code == 200
    cats = r.json().get("categories", [])
    assert "Brunchs" in cats


# ---------- orders ----------
@pytest.fixture(scope="module")
def created_order(session):
    payload = {
        "store": "runner",
        "customer_name": "TEST_baseline_jan2026",
        "items": [
            {"menu_item_id": "48", "name": "Café Pequeno", "price": 4.50, "quantity": 1}
        ],
        "total": 4.50,
        "payment_method": "cash",
    }
    r = session.post(f"{API}/orders", json=payload)
    assert r.status_code == 200, r.text
    order = r.json()
    assert order.get("status") == "received"
    assert order.get("customer_name") == "TEST_baseline_jan2026"
    assert "id" in order
    yield order
    # teardown — best-effort delete via direct status flip to delivered then leave
    try:
        session.patch(f"{API}/orders/runner/{order['id']}/status", json={"status": "delivered"})
    except Exception:
        pass


def test_create_order_persists(session, created_order):
    order_id = created_order["id"]
    r = session.get(f"{API}/orders/runner/{order_id}")
    assert r.status_code == 200
    assert r.json().get("customer_name") == "TEST_baseline_jan2026"


def test_list_orders_by_store(session):
    r = session.get(f"{API}/orders/runner")
    assert r.status_code == 200
    assert isinstance(r.json().get("orders"), list)


def test_update_order_status(session, created_order):
    r = session.patch(
        f"{API}/orders/runner/{created_order['id']}/status",
        json={"status": "preparing"},
    )
    assert r.status_code == 200
    assert r.json().get("status") == "preparing"


def test_create_pix_order_pending_payment(session):
    payload = {
        "store": "gym-londres",
        "customer_name": "TEST_pix_pending",
        "items": [{"menu_item_id": "48", "name": "Café Pequeno", "price": 4.50, "quantity": 1}],
        "total": 4.50,
        "payment_method": "pix",
    }
    r = session.post(f"{API}/orders", json=payload)
    assert r.status_code == 200
    assert r.json().get("status") == "pending_payment"


# ---------- prazo (credit/tab) ----------
def test_prazo_customers_list(session):
    r = session.get(f"{API}/prazo/customers")
    # endpoint exists in router; runner store default param may apply
    assert r.status_code in (200, 422), f"prazo customers status={r.status_code}: {r.text[:200]}"


def test_prazo_customers_runner(session):
    r = session.get(f"{API}/prazo/customers", params={"store": "runner"})
    assert r.status_code == 200, r.text
    assert "customers" in r.json() or isinstance(r.json(), list)


# ---------- cash expenses ----------
def test_expenses_list_requires_auth(session):
    r = session.get(f"{API}/expenses")
    assert r.status_code == 401  # gestor basic auth


def test_expenses_list_authed():
    r = requests.get(f"{API}/expenses", auth=(GESTOR_USER, GESTOR_PASS))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "expenses" in body and isinstance(body["expenses"], list)


# ---------- gestor (basic auth) ----------
def test_gestor_dashboard_requires_auth(session):
    r = requests.get(f"{API}/gestor/dashboard")
    assert r.status_code == 401


def test_gestor_dashboard_with_auth():
    r = requests.get(
        f"{API}/gestor/dashboard",
        auth=(GESTOR_USER, GESTOR_PASS),
        params={"store": "runner"},
    )
    # Should be 200 or 422 (param). Accept either to detect endpoint existence.
    assert r.status_code in (200, 422), f"dashboard status={r.status_code}: {r.text[:300]}"


# ---------- stock ----------
def test_stock_runner(session):
    r = session.get(f"{API}/stock/runner")
    assert r.status_code == 200, r.text


# ---------- live ----------
def test_live_dashboard():
    r = requests.get(f"{API}/live/dashboard", auth=(GESTOR_USER, GESTOR_PASS))
    assert r.status_code in (200, 404, 422), f"live status={r.status_code}"
