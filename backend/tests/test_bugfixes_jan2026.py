"""
Backend regression tests for January 2026 bug fixes:
- Bug Fix 1: Login (HTTPBasic + /auth/login) accepts whitespace/case variations
- Bug Fix 2: Cash drawer / today endpoints use UTC consistently
- Regular endpoints still operational
"""
import os
import pytest
import requests
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

GESTOR_USER = "gestor"
GESTOR_PASS = "test-only-value"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health / basic sanity ----------
class TestHealth:
    def test_api_reachable(self, session):
        # Try a public-ish endpoint
        r = session.get(f"{API}/menu/runner", timeout=15)
        assert r.status_code == 200, f"Backend not reachable: {r.status_code} {r.text[:300]}"


# ---------- Bug Fix 1: /auth/login whitespace and case insensitivity ----------
class TestAuthLoginWhitespace:
    def _post_login(self, session, username, password):
        return session.post(
            f"{API}/auth/login",
            json={"username": username, "password": password},
            timeout=15,
        )

    def test_login_normal(self, session):
        r = self._post_login(session, GESTOR_USER, GESTOR_PASS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True, f"Expected success=True, got {data}"

    def test_login_with_leading_trailing_spaces(self, session):
        r = self._post_login(session, f" {GESTOR_USER} ", f" {GESTOR_PASS} ")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True, f"Expected success=True with spaces, got {data}"

    def test_login_with_uppercase_username(self, session):
        r = self._post_login(session, GESTOR_USER.upper(), GESTOR_PASS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True, f"Expected success=True with uppercase, got {data}"

    def test_login_mixed_case_with_spaces(self, session):
        r = self._post_login(session, " Gestor ", GESTOR_PASS)
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

    def test_login_wrong_password_fails(self, session):
        r = self._post_login(session, GESTOR_USER, "wrongpass")
        # Should NOT succeed
        if r.status_code == 200:
            assert r.json().get("success") is False
        else:
            assert r.status_code in (401, 403)


# ---------- Bug Fix 1B: HTTPBasic on /gestor/dashboard ----------
class TestGestorDashboardHTTPBasic:
    def test_dashboard_normal_creds(self, session):
        r = session.get(f"{API}/gestor/dashboard", auth=HTTPBasicAuth(GESTOR_USER, GESTOR_PASS), timeout=20)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        # Must be valid JSON
        data = r.json()
        assert isinstance(data, dict)

    def test_dashboard_creds_with_spaces(self, session):
        r = session.get(
            f"{API}/gestor/dashboard",
            auth=HTTPBasicAuth(f" {GESTOR_USER} ", f" {GESTOR_PASS} "),
            timeout=20,
        )
        assert r.status_code == 200, f"With spaces failed: {r.status_code} {r.text[:300]}"
        assert isinstance(r.json(), dict)

    def test_dashboard_creds_uppercase(self, session):
        r = session.get(
            f"{API}/gestor/dashboard",
            auth=HTTPBasicAuth("GESTOR", GESTOR_PASS),
            timeout=20,
        )
        assert r.status_code == 200, f"Uppercase failed: {r.status_code} {r.text[:300]}"

    def test_dashboard_wrong_creds_rejected(self, session):
        r = session.get(
            f"{API}/gestor/dashboard",
            auth=HTTPBasicAuth("gestor", "wrongpass"),
            timeout=20,
        )
        assert r.status_code == 401


# ---------- Bug Fix 2: Cash drawer endpoints (runner + gym-londres) ----------
class TestCashDrawer:
    @pytest.mark.parametrize("store", ["runner", "gym-londres"])
    def test_drawer_endpoint(self, session, store):
        r = session.get(f"{API}/cash/{store}/drawer", timeout=20)
        assert r.status_code == 200, f"{store} drawer failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        # Must include current_balance per bug fix description
        assert "current_balance" in data, f"current_balance missing in: {list(data.keys())}"
        assert isinstance(data["current_balance"], (int, float)), f"current_balance not numeric: {data['current_balance']}"

    @pytest.mark.parametrize("store", ["runner", "gym-londres"])
    def test_today_endpoint(self, session, store):
        r = session.get(f"{API}/cash/{store}/today", timeout=20)
        assert r.status_code == 200, f"{store} today failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert isinstance(data, dict)
        # Spec: should include total and by_payment_method
        assert "total" in data, f"'total' missing in today response: {list(data.keys())}"
        assert "by_payment_method" in data, f"'by_payment_method' missing: {list(data.keys())}"
        assert isinstance(data["total"], (int, float))
        assert isinstance(data["by_payment_method"], dict)

    def test_drawer_debug_no_objectid_leak(self, session):
        r = session.get(f"{API}/cash/runner/drawer-debug", timeout=20)
        # Should return valid JSON (no ObjectId serialization issues)
        assert r.status_code == 200, r.text[:300]
        # Trying to parse JSON validates no leak issues
        r.json()


# ---------- Regular endpoints ----------
class TestRegularEndpoints:
    @pytest.mark.parametrize("store", ["runner", "gym-londres"])
    def test_menu_endpoint(self, session, store):
        r = session.get(f"{API}/menu/{store}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        # Endpoint returns dict with items/categories/adicionais
        assert isinstance(data, dict), f"Expected dict, got {type(data)}"
        assert "items" in data and isinstance(data["items"], list)
        assert len(data["items"]) > 0, "Menu items list is empty"

    def test_auth_accounts_gestor(self, session):
        r = session.get(f"{API}/auth/accounts", auth=HTTPBasicAuth(GESTOR_USER, GESTOR_PASS), timeout=15)
        # Either 200 with list or could be different; accept 200
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        # Should be a list or dict
        assert data is not None
