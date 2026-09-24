"""
Iteration 2 (Jan 2026) - tests for 3 bug fixes:
 (1) Gestor → Gastos: filter by loja (store param on monthly/daily/yearly chart endpoints)
 (2) Prazo customer lookup: returns customers when q is empty
 (3) Menu add: POST /api/gestor/menu adds item to selected store; category 'Pão Doce' available
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://charts-3.preview.emergentagent.com").rstrip("/")
AUTH = ("gestor", "test-only-value")


# -------------------- Categories (Pão Doce) --------------------
class TestCategories:
    def test_categories_includes_pao_doce(self):
        r = requests.get(f"{BASE_URL}/api/categories", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # API may return a list of strings or list of objects
        names = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    names.append(item.get("name") or item.get("category") or "")
        elif isinstance(data, dict) and "categories" in data:
            for item in data["categories"]:
                names.append(item if isinstance(item, str) else item.get("name", ""))
        assert "Pão Doce" in names, f"'Pão Doce' missing from categories: {names}"


# -------------------- Monthly / Daily / Yearly with store filter --------------------
class TestChartsWithStoreFilter:
    def _get(self, endpoint, params):
        r = requests.get(f"{BASE_URL}{endpoint}", params=params, auth=AUTH, timeout=30)
        assert r.status_code == 200, f"{endpoint} {params} -> {r.status_code} {r.text[:300]}"
        return r.json()

    def test_monthly_runner_may_2026(self):
        d = self._get("/api/gestor/chart/monthly-with-expenses",
                      {"month": 5, "year": 2026, "store": "runner"})
        assert round(d.get("total_revenue", 0), 2) == 29890.60, d
        assert round(d.get("total_expenses", 0), 2) == 13747.54, d
        assert round(d.get("total_profit", 0), 2) == 16143.06, d
        assert d.get("total_orders") == 659, d

    def test_monthly_gym_may_2026(self):
        d = self._get("/api/gestor/chart/monthly-with-expenses",
                      {"month": 5, "year": 2026, "store": "gym-londres"})
        assert round(d.get("total_revenue", 0), 2) == 15889.65, d
        assert round(d.get("total_expenses", 0), 2) == 7330.55, d
        assert round(d.get("total_profit", 0), 2) == 8559.10, d
        assert d.get("total_orders") == 923, d

    def test_monthly_combined_may_2026(self):
        d = self._get("/api/gestor/chart/monthly-with-expenses",
                      {"month": 5, "year": 2026})
        assert round(d.get("total_revenue", 0), 2) == 45780.25, d
        assert round(d.get("total_expenses", 0), 2) == 21078.09, d
        assert round(d.get("total_profit", 0), 2) == 24702.16, d
        assert d.get("total_orders") == 1582, d

    def test_daily_accepts_store_param(self):
        # Just verify endpoint accepts store and returns 200; values differ per day
        r_runner = self._get("/api/gestor/chart/daily-with-expenses",
                             {"month": 5, "year": 2026, "store": "runner"})
        r_gym = self._get("/api/gestor/chart/daily-with-expenses",
                          {"month": 5, "year": 2026, "store": "gym-londres"})
        r_all = self._get("/api/gestor/chart/daily-with-expenses",
                          {"month": 5, "year": 2026})
        # Combined total should equal runner + gym (revenue)
        rev_runner = r_runner.get("total_revenue", 0)
        rev_gym = r_gym.get("total_revenue", 0)
        rev_all = r_all.get("total_revenue", 0)
        assert abs((rev_runner + rev_gym) - rev_all) < 0.05, \
            f"runner={rev_runner}, gym={rev_gym}, all={rev_all}"

    def test_yearly_accepts_store_param(self):
        r_runner = self._get("/api/gestor/chart/yearly-with-expenses",
                             {"year": 2026, "store": "runner"})
        r_gym = self._get("/api/gestor/chart/yearly-with-expenses",
                          {"year": 2026, "store": "gym-londres"})
        r_all = self._get("/api/gestor/chart/yearly-with-expenses",
                          {"year": 2026})
        rev_runner = r_runner.get("total_revenue", 0)
        rev_gym = r_gym.get("total_revenue", 0)
        rev_all = r_all.get("total_revenue", 0)
        assert abs((rev_runner + rev_gym) - rev_all) < 0.05, \
            f"runner={rev_runner}, gym={rev_gym}, all={rev_all}"


# -------------------- Prazo customer lookup --------------------
class TestPrazoLookup:
    def test_lookup_runner_no_q_returns_50(self):
        r = requests.get(f"{BASE_URL}/api/prazo/customers/lookup",
                         params={"store": "runner"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data if isinstance(data, list) else data.get("customers", data.get("items", []))
        assert len(items) == 50, f"expected 50 customers, got {len(items)}"

    def test_lookup_gym_no_q_returns_13(self):
        r = requests.get(f"{BASE_URL}/api/prazo/customers/lookup",
                         params={"store": "gym-londres"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data if isinstance(data, list) else data.get("customers", data.get("items", []))
        assert len(items) == 13, f"expected 13 customers, got {len(items)}"

    def test_lookup_with_q_still_filters(self):
        r = requests.get(f"{BASE_URL}/api/prazo/customers/lookup",
                         params={"store": "runner", "q": "ma"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data if isinstance(data, list) else data.get("customers", data.get("items", []))
        # at least one match, all should contain 'ma' (case-insensitive) in name or phone
        assert len(items) >= 1, "expected at least one prazo customer matching 'ma'"
        for it in items:
            name = (it.get("name") or it.get("customer_name") or "").lower()
            phone = (it.get("phone") or it.get("customer_phone") or "").lower()
            assert "ma" in name or "ma" in phone, f"no 'ma' match in {it}"


# -------------------- POST /api/gestor/menu add item to selected store --------------------
class TestMenuAdd:
    def _list_menu(self, store):
        r = requests.get(f"{BASE_URL}/api/gestor/menu/{store}", auth=AUTH, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # server.py returns {"menu":[...], "count":N}; routers/menu.py returns {"items":[...]}
        return body.get("menu", body.get("items", body if isinstance(body, list) else []))

    def test_add_pao_doce_item_to_runner(self):
        unique_name = f"TEST_PaoDoce_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "category": "Pão Doce",
            "price": 4.50,
            "store": "runner",
            "description": "Teste pão doce",
            "available": True,
        }
        r = requests.post(f"{BASE_URL}/api/gestor/menu",
                          json=payload, auth=AUTH, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        body = r.json()
        # server.py creates in BOTH stores and returns {"items":[{...runner},{...gym}]}
        created_ids = [i.get("id") for i in body.get("items", [])]
        # Verify the item appears in /api/gestor/menu/runner
        items_runner = self._list_menu("runner")
        names_runner = [i.get("name") for i in items_runner]
        assert unique_name in names_runner, \
            f"new item {unique_name} not in runner menu (got {len(items_runner)} items)"
        # Item has Pão Doce category preserved
        match = next(i for i in items_runner if i.get("name") == unique_name)
        assert match.get("category") == "Pão Doce"
        # Cleanup
        for cid in created_ids:
            requests.delete(f"{BASE_URL}/api/gestor/menu/{cid}", auth=AUTH, timeout=10)

    def test_add_item_to_gym(self):
        unique_name = f"TEST_GymItem_{uuid.uuid4().hex[:8]}"
        payload = {
            "name": unique_name,
            "category": "Pão Doce",
            "price": 5.00,
            "store": "gym-londres",
            "available": True,
        }
        r = requests.post(f"{BASE_URL}/api/gestor/menu",
                          json=payload, auth=AUTH, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        body = r.json()
        created_ids = [i.get("id") for i in body.get("items", [])]
        items_gym = self._list_menu("gym-londres")
        names_gym = [i.get("name") for i in items_gym]
        assert unique_name in names_gym, \
            f"new item {unique_name} not in gym-londres menu (got {len(items_gym)} items)"
        for cid in created_ids:
            requests.delete(f"{BASE_URL}/api/gestor/menu/{cid}", auth=AUTH, timeout=10)
