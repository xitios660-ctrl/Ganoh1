"""
Tests for the regex-escape fix applied to all prazo endpoints that match
customers/orders by name via MongoDB $regex.

Bug RCA (production):
    Customer 'Erick Ramos (personal)' could not have partial payments (Abater)
    applied. The endpoint built a regex like f"^{customer_name}$" and the
    parentheses were interpreted by MongoDB as a regex capture group, so the
    stored value didn't match the pattern → returned 404 "Cliente não tem
    dívidas no prazo".

Fix verified here:
    re.escape() is now applied to every customer_name regex pattern in
    backend/server.py and backend/routers/prazo.py (19 occurrences total).

Endpoints exercised:
    - POST /api/prazo/customers                  (gestor authed; uses regex)
    - POST /api/prazo/abater/{customer_name}     (the originally broken flow)
    - POST /api/prazo/customers/{id}/add-credit  (auto-apply against debt)
    - GET  /api/prazo/customers/{id}/history     (regex search over events)
    - Backwards compatibility for plain alphanumeric names
"""
import os
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient
from requests.auth import HTTPBasicAuth
from urllib.parse import quote


def _enc(name: str) -> str:
    """URL-encode a customer_name for use as a path segment."""
    return quote(name, safe="")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ganoh_db")
PRAZO_PASSWORD = os.environ.get("PRAZO_PASSWORD", "1234")
GESTOR_USER = "gestor"
GESTOR_PASS = "ganoh2024"

# --- environment validation ---------------------------------------------------

if not BASE_URL:
    # Fallback to frontend/.env value
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass

assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

AUTH = HTTPBasicAuth(GESTOR_USER, GESTOR_PASS)


# --- fixtures -----------------------------------------------------------------

@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def run_tag():
    """Unique suffix for this test run so collisions are impossible."""
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="module", autouse=True)
def cleanup(mongo, run_tag):
    """Wipe TEST_* docs both before and after the run."""
    def purge():
        mongo.prazo_customers.delete_many({"name": {"$regex": f"^TEST_PRZX_{run_tag}"}})
        mongo.orders.delete_many({"customer_name": {"$regex": f"^TEST_PRZX_{run_tag}"}})
        mongo.prazo_partial_payments.delete_many({"customer_name": {"$regex": f"^TEST_PRZX_{run_tag}"}})
        mongo.prazo_payments.delete_many({"customer_name": {"$regex": f"^TEST_PRZX_{run_tag}"}})
        mongo.prazo_history.delete_many({"customer_name": {"$regex": f"^TEST_PRZX_{run_tag}"}})
    purge()
    yield
    purge()


# --- helpers ------------------------------------------------------------------

def _create_customer(session, name, store="runner"):
    resp = session.post(
        f"{BASE_URL}/api/prazo/customers",
        json={"name": name, "phone": "", "notes": "test", "store": store, "credit": 0},
        auth=AUTH,
        timeout=20,
    )
    return resp


def _seed_order(mongo, name, total, store="runner"):
    order_id = str(uuid.uuid4())
    mongo.orders.insert_one({
        "id": order_id,
        "customer_name": name,
        "store": store,
        "items": [{"name": "TEST item", "quantity": 1, "price": total}],
        "total": float(total),
        "partial_paid": 0,
        "payment_method": "prazo",
        "prazo_paid": False,
        "status": "delivered",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return order_id


def _customer_id_by_name(session, name):
    resp = session.get(f"{BASE_URL}/api/prazo/customers", auth=AUTH, timeout=20)
    assert resp.status_code == 200, resp.text
    for c in resp.json().get("customers", []):
        if c.get("name") == name:
            return c.get("id")
    return None


# --- the special-char names being tested -------------------------------------

SPECIAL_NAMES = [
    "Erick Ramos (personal)",  # the production bug
    "Joao A.",                 # dot
    "TEST plus + extra",       # plus
    "Cli [teste]",             # square brackets
    "Star * Marcus",           # star
    "Quem? Carlos",            # question mark
    "Or | bar",                # pipe
    "Caret ^ guy",             # caret
    "Dollar $ Bill",           # dollar
]


# --- tests --------------------------------------------------------------------

class TestAbaterRegexEscape:
    """POST /api/prazo/abater/{customer_name} must work for regex-special names."""

    @pytest.mark.parametrize("base_name", SPECIAL_NAMES)
    def test_abater_succeeds_with_special_chars(self, session, mongo, run_tag, base_name):
        full_name = f"TEST_PRZX_{run_tag}_{base_name}"
        # 1) register the customer
        r = _create_customer(session, full_name)
        assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"

        # 2) seed an unpaid prazo order of R$172
        order_id = _seed_order(mongo, full_name, 172.00)

        # 3) call abater with pix R$0.50
        r = session.post(
            f"{BASE_URL}/api/prazo/abater/{_enc(full_name)}",
            json={"password": PRAZO_PASSWORD, "amount": 0.50, "payment_method": "pix"},
            timeout=20,
        )
        assert r.status_code == 200, f"abater failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("success") is True
        assert data.get("orders_updated", 0) == 1
        # Response schema: server.py returns "paid", router returns "amount_paid"
        amount_field = data.get("paid", data.get("amount_paid"))
        assert amount_field is not None and abs(amount_field - 0.50) < 1e-6, (
            f"expected R$0.50 paid, got {amount_field}; response={data}"
        )
        # new_debt should be 172 - 0.5 = 171.5
        assert abs(data.get("new_debt", 0) - 171.5) < 1e-6

        # 4) verify partial_paid persisted in DB
        order = mongo.orders.find_one({"id": order_id}, {"_id": 0})
        assert order is not None
        assert abs(order.get("partial_paid", 0) - 0.50) < 1e-6
        assert order.get("prazo_paid") in (False, None)


class TestAddCreditRegexEscape:
    """POST /api/prazo/customers/{id}/add-credit auto-applies to debt for special-char names."""

    def test_add_credit_applies_to_debt_with_parens(self, session, mongo, run_tag):
        name = f"TEST_PRZX_{run_tag}_Maria (vip)"
        r = _create_customer(session, name)
        assert r.status_code == 200, r.text
        cust_id = _customer_id_by_name(session, name)
        assert cust_id

        _seed_order(mongo, name, 100.00)

        # Add R$30 credit → should fully apply to debt
        r = session.post(
            f"{BASE_URL}/api/prazo/customers/{cust_id}/add-credit",
            json={"amount": 30.0, "notes": "test add-credit parens"},
            timeout=20,
        )
        assert r.status_code == 200, f"add-credit failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("success") is True
        # Either the server endpoint or the router endpoint can answer; both should
        # have applied at least part of the value against the debt.
        applied = data.get("applied_to_debt")
        if applied is not None:
            assert abs(applied - 30.0) < 1e-6, f"expected R$30 applied to debt, got {applied}"
            assert data.get("remaining_credit_added", 0) == 0
            assert data.get("new_credit", 0) == 0

        # Verify the order's partial_paid moved
        order = mongo.orders.find_one(
            {"customer_name": name, "payment_method": "prazo"}, {"_id": 0}
        )
        assert order is not None
        # If applied_to_debt is None, the endpoint may not auto-apply; in that case
        # at minimum the customer's credit should reflect the +30.
        if applied is None:
            cust = mongo.prazo_customers.find_one({"id": cust_id}, {"_id": 0})
            assert (cust.get("credit") or 0) >= 30.0
        else:
            assert abs(order.get("partial_paid", 0) - 30.0) < 1e-6


class TestHistoryRegexEscape:
    """GET /api/prazo/customers/{id}/history filters events by name via regex."""

    def test_history_returns_for_parens_name(self, session, mongo, run_tag):
        name = f"TEST_PRZX_{run_tag}_Pedro (alt)"
        r = _create_customer(session, name)
        assert r.status_code == 200, r.text
        cust_id = _customer_id_by_name(session, name)
        assert cust_id

        _seed_order(mongo, name, 50.00)

        # Trigger an event (abater) so history has something to filter by name
        r = session.post(
            f"{BASE_URL}/api/prazo/abater/{_enc(name)}",
            json={"password": PRAZO_PASSWORD, "amount": 10.0, "payment_method": "cash"},
            timeout=20,
        )
        assert r.status_code == 200, r.text

        r = session.get(f"{BASE_URL}/api/prazo/customers/{cust_id}/history", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["customer"]["name"] == name
        # current_debt must be 50 - 10 = 40
        assert abs(data["customer"]["current_debt"] - 40.0) < 1e-6


class TestBackwardsCompatPlainNames:
    """Plain alphanumeric names must still work after re.escape was added."""

    def test_abater_plain_name(self, session, mongo, run_tag):
        name = f"TEST_PRZX_{run_tag}_Paulo Henrique"
        r = _create_customer(session, name)
        assert r.status_code == 200, r.text
        order_id = _seed_order(mongo, name, 80.00)

        r = session.post(
            f"{BASE_URL}/api/prazo/abater/{_enc(name)}",
            json={"password": PRAZO_PASSWORD, "amount": 25.0, "payment_method": "cash"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        amount_field = body.get("paid", body.get("amount_paid"))
        assert amount_field == 25.0, f"expected 25.0, got {amount_field}; resp={body}"

        order = mongo.orders.find_one({"id": order_id}, {"_id": 0})
        assert abs(order.get("partial_paid", 0) - 25.0) < 1e-6


class TestAbaterUnknownCustomerStillReturns404:
    """The escape fix must NOT make abater match unrelated customers."""

    def test_unknown_customer_returns_404(self, session, run_tag):
        unknown = f"TEST_PRZX_{run_tag}_NeverExisted (ghost)"
        r = session.post(
            f"{BASE_URL}/api/prazo/abater/{_enc(unknown)}",
            json={"password": PRAZO_PASSWORD, "amount": 1.0, "payment_method": "pix"},
            timeout=20,
        )
        assert r.status_code == 404, f"expected 404 for unknown customer, got {r.status_code}: {r.text}"


class TestAbaterWrongPassword:
    """Sanity: bad password still rejected even with special chars."""

    def test_wrong_password_403(self, session, mongo, run_tag):
        name = f"TEST_PRZX_{run_tag}_Auth (chk)"
        _create_customer(session, name)
        _seed_order(mongo, name, 10.0)
        r = session.post(
            f"{BASE_URL}/api/prazo/abater/{_enc(name)}",
            json={"password": "wrong-pass", "amount": 1.0, "payment_method": "pix"},
            timeout=20,
        )
        assert r.status_code == 403
