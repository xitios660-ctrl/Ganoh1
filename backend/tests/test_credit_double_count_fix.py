"""
Tests for the CRITICAL P0 bug fix: Saldo a Favor / Crédito double-counting.

Bug: When a prazo customer with credit (saldo a favor) made a partial payment
('abater') using cash/pix/debit/credit, the system was BOTH reducing the debt
AND deducting the credit balance — double counting.

Fix: At /app/backend/server.py:3224-3251, credit balance is ONLY reduced when
payment_method == 'saldo'. For cash/pix/debit/credit, only the debt is reduced.

Scenarios covered:
  a) Abater via 'pix' / 'cash' / 'debit' / 'credit' -> credit unchanged
  b) Abater via 'saldo' -> credit reduced AND debt reduced
  c) Abater via 'saldo' with insufficient credit -> HTTP 400

Also regresses:
  - POST /api/auth/login (gestor with whitespace + case insensitivity)
  - GET /api/gestor/dashboard (HTTPBasic)
  - GET /api/cash/runner/today
  - GET /api/prazo/customers, GET /api/prazo/debts?store=runner
  - POST /api/prazo/customers/{id}/add-credit and use-credit
  - POST /api/orders with prazo + credit auto-consumption
"""

import os
import uuid
import pytest
import requests
from requests.auth import HTTPBasicAuth

# Public URL routes to Framer landing for unauthenticated curl in this preview env;
# backend regression tests run against internal port 8001 (same approach as iter 1).
PUBLIC_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
LOCAL_URL = "http://localhost:8001"


def _pick_base_url() -> str:
    """Prefer public URL if it routes to backend; fallback to localhost:8001."""
    if PUBLIC_URL:
        try:
            r = requests.get(f"{PUBLIC_URL}/api/prazo/customers", timeout=5)
            if r.status_code == 200:
                return PUBLIC_URL
        except Exception:
            pass
    return LOCAL_URL


BASE_URL = _pick_base_url()
GESTOR_USER = "gestor"
GESTOR_PASS = "test-only-value"
PRAZO_PASSWORD = "1234"
TEST_CUSTOMER = f"TestUser_{uuid.uuid4().hex[:8]}"  # unique per run
GESTOR_AUTH = HTTPBasicAuth(GESTOR_USER, GESTOR_PASS)


# ============== Fixtures ==============

@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def test_customer(api):
    """Create the test prazo customer with initial credit=100, cleanup at end."""
    # Create customer (requires HTTPBasic gestor)
    payload = {
        "name": TEST_CUSTOMER,
        "phone": "11999999999",
        "notes": "automated test - safe to delete",
        "credit": 100.0,
        "store": "runner",
    }
    r = api.post(f"{BASE_URL}/api/prazo/customers", json=payload, auth=GESTOR_AUTH)
    assert r.status_code in (200, 201), f"Create customer failed: {r.status_code} {r.text}"

    # Lookup customer to get id (NOTE: POST /api/prazo/customers ignores 'store'
    # and 'credit' fields, so we look up without store filter and add credit explicitly).
    r2 = api.get(f"{BASE_URL}/api/prazo/customers")
    assert r2.status_code == 200
    customers = r2.json().get("customers", [])
    matching = [c for c in customers if c.get("name", "").lower() == TEST_CUSTOMER.lower()]
    assert matching, f"Customer not found after create: {TEST_CUSTOMER}"
    cust = matching[0]

    # Ensure credit=100 (create endpoint does not persist 'credit')
    needed = 100.0 - cust.get("credit", 0)
    if needed > 0:
        rc = api.post(
            f"{BASE_URL}/api/prazo/customers/{cust['id']}/add-credit",
            json={"amount": needed},
        )
        assert rc.status_code == 200, f"add-credit init failed: {rc.text}"

    yield cust

    # Teardown
    api.delete(f"{BASE_URL}/api/prazo/customers/{cust['id']}", auth=GESTOR_AUTH)
    # Also clean any orders + partial payments left over via mongo shell
    try:
        import subprocess
        subprocess.run(
            [
                "mongosh", "test_database", "--quiet", "--eval",
                f'db.orders.deleteMany({{customer_name:"{TEST_CUSTOMER}"}}); '
                f'db.prazo_partial_payments.deleteMany({{customer_name:"{TEST_CUSTOMER}"}}); '
                f'db.prazo_customers.deleteMany({{name:"{TEST_CUSTOMER}"}});',
            ],
            timeout=15, check=False, capture_output=True,
        )
    except Exception:
        pass


def _get_customer(api, customer_id: str) -> dict:
    r = api.get(f"{BASE_URL}/api/prazo/customers")
    assert r.status_code == 200
    for c in r.json().get("customers", []):
        if c.get("id") == customer_id:
            return c
    return {}


def _get_debt(api, name: str) -> float:
    # Don't filter by store - the create endpoint doesn't persist 'store' either.
    r = api.get(f"{BASE_URL}/api/prazo/debts")
    assert r.status_code == 200
    for d in r.json().get("debts", []):
        if d.get("name", "").lower() == name.lower():
            return d.get("total", 0)
    return 0.0


def _create_prazo_order(api, name: str, total: float) -> dict:
    payload = {
        "store": "runner",
        "customer_name": name,
        "items": [{
            "menu_item_id": "test-item",
            "name": "Item Teste",
            "price": total,
            "quantity": 1,
        }],
        "total": total,
        "payment_method": "prazo",
    }
    r = api.post(f"{BASE_URL}/api/orders", json=payload)
    assert r.status_code == 200, f"Create order failed: {r.status_code} {r.text}"
    return r.json()


# ============== Regression: login + dashboard ==============

class TestLoginRegression:
    def test_login_normal(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"username": GESTOR_USER, "password": GESTOR_PASS})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True or "token" in data or "tenant_id" in data

    def test_login_whitespace_and_uppercase(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"username": "  Gestor  ", "password": GESTOR_PASS})
        assert r.status_code == 200, r.text

    def test_login_rejects_wrong_password(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"username": GESTOR_USER, "password": "wrong"})
        assert r.status_code in (401, 403)

    def test_dashboard_httpbasic(self, api):
        r = api.get(f"{BASE_URL}/api/gestor/dashboard", auth=GESTOR_AUTH)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), dict)


# ============== Regression: cash/runner/today ==============

class TestCashRunnerToday:
    def test_runner_today(self, api):
        r = api.get(f"{BASE_URL}/api/cash/runner/today")
        assert r.status_code == 200, r.text
        data = r.json()
        # Should contain total and a payment-method breakdown
        assert "total" in data or "total_sales" in data


# ============== Regression: prazo customers + debts ==============

class TestPrazoListing:
    def test_get_customers(self, api):
        r = api.get(f"{BASE_URL}/api/prazo/customers")
        assert r.status_code == 200
        assert "customers" in r.json()

    def test_get_debts_runner(self, api):
        r = api.get(f"{BASE_URL}/api/prazo/debts?store=runner")
        assert r.status_code == 200
        data = r.json()
        assert "debts" in data and "total_prazo" in data


# ============== Regression: add-credit / use-credit ==============

class TestCreditEndpoints:
    def test_add_then_use_credit(self, api, test_customer):
        # Save baseline
        before = _get_customer(api, test_customer["id"]).get("credit", 0)

        # Add 25
        r = api.post(f"{BASE_URL}/api/prazo/customers/{test_customer['id']}/add-credit",
                     json={"amount": 25.0})
        assert r.status_code == 200, r.text
        assert r.json()["new_credit"] == pytest.approx(before + 25.0)

        # Use 25
        r2 = api.post(f"{BASE_URL}/api/prazo/customers/{test_customer['id']}/use-credit",
                      json={"amount": 25.0})
        assert r2.status_code == 200, r2.text
        assert r2.json()["new_credit"] == pytest.approx(before)


# ============== CORE: credit double-count fix ==============

class TestCreditDoubleCountFix:
    """
    Main P0 scenario from the review request:
      Customer starts at credit=100.
      Order 1 (R$100, prazo) -> consumes all credit, paid_by_credit=True. credit=0.
      Order 2 (R$50, prazo)  -> debt=50, credit=0.
      Add credit R$30        -> credit=30, debt=50.
      a) Abater R$20 via 'pix'   -> credit stays 30, debt=30
      b) Abater R$20 via 'saldo' -> credit=10, debt=10
      c) Abater R$50 via 'saldo' -> HTTP 400 (insufficient)
    """

    def test_step_1_first_order_consumes_credit(self, api, test_customer):
        # Confirm starting credit
        c = _get_customer(api, test_customer["id"])
        assert c.get("credit", 0) == pytest.approx(100.0), f"Expected credit=100, got {c}"

        # Create R$100 prazo order — should consume all credit
        resp = _create_prazo_order(api, TEST_CUSTOMER, 100.0)
        assert resp.get("credit_used") == pytest.approx(100.0)
        assert resp.get("paid_by_credit") is True
        assert resp.get("new_credit") == pytest.approx(0.0)

        # Credit now 0
        c2 = _get_customer(api, test_customer["id"])
        assert c2.get("credit", 0) == pytest.approx(0.0)

        # Debt should be 0 because order was fully paid by credit
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(0.0)

    def test_step_2_second_order_creates_debt(self, api, test_customer):
        # R$50 prazo order, no credit available -> creates debt
        resp = _create_prazo_order(api, TEST_CUSTOMER, 50.0)
        # No credit used
        assert resp.get("credit_used", 0) == 0
        # Debt should now be 50
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(50.0)

    def test_step_3_add_credit_30(self, api, test_customer):
        r = api.post(f"{BASE_URL}/api/prazo/customers/{test_customer['id']}/add-credit",
                     json={"amount": 30.0})
        assert r.status_code == 200, r.text
        c = _get_customer(api, test_customer["id"])
        assert c.get("credit", 0) == pytest.approx(30.0)
        # Debt unchanged
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(50.0)

    def test_step_4a_abater_pix_does_not_touch_credit(self, api, test_customer):
        """CORE BUG FIX: payment_method='pix' must NOT reduce credit."""
        credit_before = _get_customer(api, test_customer["id"]).get("credit", 0)
        assert credit_before == pytest.approx(30.0)

        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 20.0, "password": PRAZO_PASSWORD, "payment_method": "pix"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Response must NOT report credit_used (the previous bug DID report it)
        assert body.get("credit_used", 0) == 0, (
            f"BUG REGRESSION: pix abater used credit: {body}"
        )

        # Credit must be unchanged
        credit_after = _get_customer(api, test_customer["id"]).get("credit", 0)
        assert credit_after == pytest.approx(30.0), (
            f"BUG: credit changed after pix abater (before=30, after={credit_after})"
        )

        # Debt must be reduced by 20 (was 50, now 30)
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(30.0)

    def test_step_4b_abater_cash_does_not_touch_credit(self, api, test_customer):
        """payment_method='cash' must also not reduce credit."""
        credit_before = _get_customer(api, test_customer["id"]).get("credit", 0)

        # Use small amount to keep state predictable; debt is 30 now
        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 5.0, "password": PRAZO_PASSWORD, "payment_method": "cash"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("credit_used", 0) == 0

        # Credit unchanged
        assert _get_customer(api, test_customer["id"]).get("credit", 0) == pytest.approx(credit_before)
        # Debt now 25
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(25.0)

    def test_step_4c_abater_debit_does_not_touch_credit(self, api, test_customer):
        credit_before = _get_customer(api, test_customer["id"]).get("credit", 0)
        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 5.0, "password": PRAZO_PASSWORD, "payment_method": "debit"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("credit_used", 0) == 0
        assert _get_customer(api, test_customer["id"]).get("credit", 0) == pytest.approx(credit_before)
        # Debt now 20
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(20.0)

    def test_step_4d_abater_credit_card_does_not_touch_credit(self, api, test_customer):
        credit_before = _get_customer(api, test_customer["id"]).get("credit", 0)
        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 5.0, "password": PRAZO_PASSWORD, "payment_method": "credit"},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("credit_used", 0) == 0
        assert _get_customer(api, test_customer["id"]).get("credit", 0) == pytest.approx(credit_before)
        # Debt now 15
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(15.0)

    def test_step_5_abater_saldo_reduces_both(self, api, test_customer):
        """payment_method='saldo' MUST reduce credit AND debt."""
        credit_before = _get_customer(api, test_customer["id"]).get("credit", 0)
        debt_before = _get_debt(api, TEST_CUSTOMER)
        # credit=30 (unchanged), debt=15
        assert credit_before == pytest.approx(30.0)
        assert debt_before == pytest.approx(15.0)

        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 10.0, "password": PRAZO_PASSWORD, "payment_method": "saldo"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("credit_used") == pytest.approx(10.0), body
        assert body.get("new_credit") == pytest.approx(20.0), body

        # Credit reduced to 20, debt reduced to 5
        assert _get_customer(api, test_customer["id"]).get("credit", 0) == pytest.approx(20.0)
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(5.0)

    def test_step_6_abater_saldo_insufficient_returns_400(self, api, test_customer):
        """Asking for more 'saldo' than credit available must 400 and NOT mutate state."""
        credit_before = _get_customer(api, test_customer["id"]).get("credit", 0)
        debt_before = _get_debt(api, TEST_CUSTOMER)
        # credit=20, debt=5. Ask for 50 via saldo. But amount > debt also triggers 400 earlier.
        # Use amount=4 (< debt) but credit=20 is enough; instead, set up: ask amount=21 -> amount > debt(5), gets 400.
        # To specifically hit insufficient-saldo path, we need amount <= debt AND amount > credit.
        # debt=5, credit=20 -> can't construct. Make debt larger first via a new prazo order.
        # Create order R$100 prazo (no credit available was just reduced, but customer.credit is 20,
        # which WILL be consumed by the new order's create_order endpoint).
        # Simpler approach: first DRAIN credit by using use-credit, then create debt, then test 400.

        # Drain credit
        api.post(f"{BASE_URL}/api/prazo/customers/{test_customer['id']}/use-credit",
                 json={"amount": credit_before})
        # Add small credit 3
        api.post(f"{BASE_URL}/api/prazo/customers/{test_customer['id']}/add-credit",
                 json={"amount": 3.0})

        # Confirm credit=3, debt still 5
        assert _get_customer(api, test_customer["id"]).get("credit", 0) == pytest.approx(3.0)
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(debt_before)

        # Now ask abater amount=5 via saldo: amount <= debt(5), but credit (3) insufficient -> 400
        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 5.0, "password": PRAZO_PASSWORD, "payment_method": "saldo"},
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        detail = (r.json() or {}).get("detail", "").lower()
        assert "saldo" in detail or "insuficiente" in detail or "insufficient" in detail, r.text

        # State must NOT have changed
        assert _get_customer(api, test_customer["id"]).get("credit", 0) == pytest.approx(3.0)
        assert _get_debt(api, TEST_CUSTOMER) == pytest.approx(debt_before)

    def test_step_7_wrong_password_returns_403(self, api, test_customer):
        r = api.post(
            f"{BASE_URL}/api/prazo/abater/{TEST_CUSTOMER}",
            json={"amount": 1.0, "password": "wrong", "payment_method": "pix"},
        )
        assert r.status_code == 403
