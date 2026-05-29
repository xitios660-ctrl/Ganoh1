"""Backend regression tests for review request iteration_2 (Jan 2026).

Validates:
- /api/prazo/customers?store=runner returns 69 customers
- /api/prazo/customers?store=gym-londres returns 13 customers
- /api/prazo/debts?store=runner total ~R$ 9.009,00, 54 debtors, top ALESSANDRA ALLUNA = 23 orders R$865,50
- /api/prazo/debts?store=gym-londres total ~R$1.835,60, 10 debtors
- /api/menu/runner returns >=60 items spread across required categories
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://menu-3d-branding.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

EXPECTED_CATEGORIES = {
    "Omeletes", "Brunchs", "Toasts", "Shakes Proteicos", "Açaí",
    "Sucos e Vitaminas", "Saladas", "Bebidas Quentes", "Bebidas Geladas",
}


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Prazo customers ----------
class TestPrazoCustomers:
    def test_customers_runner_count(self, s):
        r = s.get(f"{API}/prazo/customers", params={"store": "runner"}, timeout=20)
        assert r.status_code == 200, r.text
        customers = r.json().get("customers", [])
        print(f"Runner customers: {len(customers)}")
        assert len(customers) == 69, f"Expected 69 runner customers, got {len(customers)}"

    def test_customers_gym_londres_count(self, s):
        r = s.get(f"{API}/prazo/customers", params={"store": "gym-londres"}, timeout=20)
        assert r.status_code == 200, r.text
        customers = r.json().get("customers", [])
        print(f"Gym-londres customers: {len(customers)}")
        assert len(customers) == 13, f"Expected 13 gym-londres customers, got {len(customers)}"


# ---------- Prazo debts ----------
class TestPrazoDebts:
    def test_debts_runner_totals_and_top_debtor(self, s):
        r = s.get(f"{API}/prazo/debts", params={"store": "runner"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        debts = data.get("debts", [])
        total = data.get("total_prazo", 0)
        count = data.get("customer_count", 0)
        print(f"Runner debts: {count} debtors, total R$ {total:.2f}")
        assert count == 54, f"Expected 54 debtors, got {count}"
        assert abs(total - 9009.0) < 1.0, f"Expected total ~9009.00, got {total}"

        # Top debtor should be ALESSANDRA ALLUNA with 23 orders / R$ 865,50
        assert debts, "No debtors returned"
        top = debts[0]
        print(f"Top debtor: {top.get('name')} -> {top.get('order_count')} orders, R$ {top.get('total'):.2f}")
        assert top.get("name", "").upper() == "ALESSANDRA ALLUNA"
        assert top.get("order_count") == 23, f"Expected 23 orders, got {top.get('order_count')}"
        assert abs(top.get("total", 0) - 865.50) < 0.05

    def test_debts_gym_londres_totals(self, s):
        r = s.get(f"{API}/prazo/debts", params={"store": "gym-londres"}, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        count = data.get("customer_count", 0)
        total = data.get("total_prazo", 0)
        print(f"Gym-londres debts: {count} debtors, total R$ {total:.2f}")
        assert count == 10, f"Expected 10 gym-londres debtors, got {count}"
        assert abs(total - 1835.60) < 1.0, f"Expected total ~1835.60, got {total}"


# ---------- Menu ----------
class TestMenuRunner:
    def test_menu_runner_returns_60_plus_with_categories(self, s):
        r = s.get(f"{API}/menu/runner", timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        # endpoint may return a list or {"items": [...]}
        items = body if isinstance(body, list) else body.get("items") or body.get("menu") or []
        print(f"Menu runner items: {len(items)}")
        assert len(items) >= 60, f"Expected >=60 items, got {len(items)}"
        cats = {item.get("category") for item in items if item.get("category")}
        print(f"Categories present: {sorted(cats)}")
        missing = EXPECTED_CATEGORIES - cats
        assert not missing, f"Missing expected categories: {missing}"
