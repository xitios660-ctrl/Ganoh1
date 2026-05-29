"""Iteration 2 - Jan 2026: Validates chart store filters, new /admin/* endpoints,
and regression suite for PDF corrections + bug-fix of duplo-login.
"""

import os
import pytest
import requests
from requests.auth import HTTPBasicAuth

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

USER = "gestor"
PWD = "Gan0h#G3st0r@2026"
AUTH = HTTPBasicAuth(USER, PWD)


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ============ CHART STORE FILTER FIX ============
class TestChartStoreFilter:
    def test_daily_store_filter_runner(self, http):
        r = http.get(f"{API}/gestor/chart/daily", params={"store": "runner"}, auth=AUTH)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("store_filter") == "runner", f"store_filter missing/wrong: {data.get('store_filter')}"

    def test_daily_store_filter_all_default(self, http):
        r = http.get(f"{API}/gestor/chart/daily", auth=AUTH)
        assert r.status_code == 200
        assert r.json().get("store_filter") == "all"

    def test_monthly_accepts_store_param(self, http):
        # Endpoint should accept `store` (was previously ignored).
        # We verify: 200 OK + filter actually applied → with store=gym-londres,
        # by_store.runner.total/orders must be 0 (no runner data leaks through).
        r = http.get(f"{API}/gestor/chart/monthly",
                     params={"month": 1, "year": 2026, "store": "gym-londres"}, auth=AUTH)
        assert r.status_code == 200, r.text
        data = r.json()
        by_store = data.get("by_store") or {}
        runner = by_store.get("runner") or {}
        # When filtered to gym-londres, runner totals/orders must be 0
        assert runner.get("total", 0) == 0, f"store=gym-londres but runner total != 0: {runner}"
        assert runner.get("orders", 0) == 0, f"store=gym-londres but runner orders != 0: {runner}"

    def test_yearly_accepts_store_param(self, http):
        # Verify endpoint accepts param (200) and filter is applied internally.
        # by_store.gym_londres totals must be 0 when filtered to runner.
        r = http.get(f"{API}/gestor/chart/yearly",
                     params={"year": 2026, "store": "runner"}, auth=AUTH)
        assert r.status_code == 200, r.text
        data = r.json()
        by_store = data.get("by_store") or {}
        # by_store key may not exist in yearly response; if it does, validate gym-londres is 0
        if by_store:
            gym = by_store.get("gym_londres") or by_store.get("gym-londres") or {}
            assert gym.get("total", 0) == 0, f"store=runner but gym total != 0: {gym}"

    def test_weekly_accepts_store_param(self, http):
        r = http.get(f"{API}/gestor/chart/weekly",
                     params={"store": "runner"}, auth=AUTH)
        assert r.status_code == 200, r.text

    def test_daily_with_specific_date(self, http):
        # frontend sends local YYYY-MM-DD; backend should return that date as date_iso
        r = http.get(f"{API}/gestor/chart/daily",
                     params={"date": "2026-01-15", "store": "runner"}, auth=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert data.get("date_iso") == "2026-01-15", f"date_iso mismatch: {data.get('date_iso')}"
        assert data.get("store_filter") == "runner"


# ============ NEW ADMIN ENDPOINTS ============
class TestAdminEndpoints:
    def test_fix_product_names_authenticated(self, http):
        r = http.post(f"{API}/admin/fix-product-names", auth=AUTH)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True
        totals = data.get("totals", {})
        for key in ("products_renamed", "products_merged", "adicionais_renamed", "adicionais_merged"):
            assert key in totals, f"missing totals key: {key}"
            assert isinstance(totals[key], int)

    def test_fix_product_names_unauthenticated(self, http):
        r = http.post(f"{API}/admin/fix-product-names")
        assert r.status_code == 401, f"expected 401, got {r.status_code}"

    def test_reset_stock_placeholders_authenticated(self, http):
        r = http.post(f"{API}/admin/reset-stock-placeholders", auth=AUTH)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True
        assert "reset_count" in data
        assert isinstance(data["reset_count"], int)
        assert "reset_ids" in data
        assert isinstance(data["reset_ids"], list)

    def test_reset_stock_placeholders_unauthenticated(self, http):
        r = http.post(f"{API}/admin/reset-stock-placeholders")
        assert r.status_code == 401

    def test_prazo_audit_log_authenticated(self, http):
        r = http.get(f"{API}/admin/prazo-audit-log", params={"limit": 5}, auth=AUTH)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "entries" in data
        assert isinstance(data["entries"], list)
        assert "count" in data
        assert isinstance(data["count"], int)
        assert len(data["entries"]) <= 5

    def test_prazo_audit_log_unauthenticated(self, http):
        r = http.get(f"{API}/admin/prazo-audit-log")
        assert r.status_code == 401


# ============ REGRESSION (iteration 1 cases - smoke) ============
class TestRegression:
    def test_old_password_rejected(self, http):
        r = http.post(f"{API}/auth/login", json={"username": "gestor", "password": "ganoh2024"})
        assert r.status_code == 401

    def test_new_password_works(self, http):
        r = http.post(f"{API}/auth/login", json={"username": "gestor", "password": PWD})
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_accounts_returns_empty_accounts_list(self, http):
        r = http.get(f"{API}/auth/accounts")
        assert r.status_code == 200
        data = r.json()
        assert data.get("accounts") == []
        assert isinstance(data.get("count"), int)

    def test_prazo_lookup_no_q_returns_empty(self, http):
        r = http.get(f"{API}/prazo/customers/lookup")
        assert r.status_code == 200
        assert r.json().get("customers") == []

    def test_prazo_lookup_one_char_returns_empty(self, http):
        r = http.get(f"{API}/prazo/customers/lookup", params={"q": "a"})
        assert r.status_code == 200
        assert r.json().get("customers") == []

    def test_menu_runner_no_duplicate_categories(self, http):
        r = http.get(f"{API}/menu/runner")
        assert r.status_code == 200
        cats = r.json().get("categories", [])
        lows = [c.lower() for c in cats]
        assert len(lows) == len(set(lows)), f"Duplicate cats: {cats}"
