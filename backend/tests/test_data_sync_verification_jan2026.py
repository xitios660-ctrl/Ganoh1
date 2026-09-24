"""
Test suite to verify data sync from reference site (prazo-payment-sys.emergent.host).
Validates cash drawer values, prazo debts, and expenses.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://0b70e0ff-bd72-49a6-9a5e-947a6db8f30e.preview.emergentagent.com").rstrip("/")
GESTOR_USER = "gestor"
GESTOR_PASS = "test-only-value"


@pytest.fixture(scope="module")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def gestor_token(api_client):
    # Try common login endpoints
    candidates = [
        ("/api/auth/login", {"username": GESTOR_USER, "password": GESTOR_PASS}),
        ("/api/gestor/login", {"username": GESTOR_USER, "password": GESTOR_PASS}),
        ("/api/login", {"username": GESTOR_USER, "password": GESTOR_PASS}),
    ]
    for path, payload in candidates:
        try:
            r = api_client.post(f"{BASE_URL}{path}", json=payload, timeout=15)
            if r.status_code == 200:
                data = r.json()
                token = data.get("token") or data.get("access_token")
                if token:
                    return token
        except Exception:
            continue
    return None


# ===== Cash Drawer Tests =====
class TestCashDrawer:
    def test_runner_drawer(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/cash/runner/drawer", timeout=20)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        print(f"\nRUNNER drawer: {data}")
        assert abs(data.get("current_balance", 0) - 197.75) < 0.01, f"current_balance={data.get('current_balance')}"
        assert abs(data.get("initial_balance", 0) - 93.0) < 0.01, f"initial_balance={data.get('initial_balance')}"
        assert abs(data.get("total_cash_sales", 0) - 185.0) < 0.01, f"total_cash_sales={data.get('total_cash_sales')}"
        assert abs(data.get("total_prazo_cash", 0) - 150.0) < 0.01, f"total_prazo_cash={data.get('total_prazo_cash')}"
        assert abs(data.get("total_withdrawals", 0) - 230.25) < 0.01, f"total_withdrawals={data.get('total_withdrawals')}"

    def test_gym_londres_drawer(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/cash/gym-londres/drawer", timeout=20)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        print(f"\nGYM LONDRES drawer: {data}")
        assert abs(data.get("current_balance", 0) - 117.4) < 0.01, f"current_balance={data.get('current_balance')}"
        assert abs(data.get("initial_balance", 0) - 55.44) < 0.01, f"initial_balance={data.get('initial_balance')}"
        assert abs(data.get("total_cash_sales", 0) - 758.85) < 0.01, f"total_cash_sales={data.get('total_cash_sales')}"
        assert abs(data.get("total_prazo_cash", 0) - 227.7) < 0.01, f"total_prazo_cash={data.get('total_prazo_cash')}"
        assert abs(data.get("total_withdrawals", 0) - 924.59) < 0.01, f"total_withdrawals={data.get('total_withdrawals')}"


# ===== Prazo Debts Tests =====
class TestPrazoDebts:
    def test_prazo_runner(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/prazo/debts?store=runner", timeout=20)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        # Could be list of customers or wrapped object
        customers = data if isinstance(data, list) else (data.get("customers") or data.get("debts") or data.get("data") or [])
        total = sum((c.get("total") or c.get("balance") or c.get("amount") or 0) for c in customers)
        print(f"\nRUNNER prazo debts: {len(customers)} customers, total={total}")
        assert len(customers) == 53, f"Expected 53 customers, got {len(customers)}"
        assert abs(total - 8727.9) < 0.5, f"Expected total ~8727.9, got {total}"

    def test_prazo_gym_londres(self, api_client):
        r = api_client.get(f"{BASE_URL}/api/prazo/debts?store=gym-londres", timeout=20)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        customers = data if isinstance(data, list) else (data.get("customers") or data.get("debts") or data.get("data") or [])
        total = sum((c.get("total") or c.get("balance") or c.get("amount") or 0) for c in customers)
        print(f"\nGYM LONDRES prazo debts: {len(customers)} customers, total={total}")
        assert len(customers) == 11, f"Expected 11 customers, got {len(customers)}"
        assert abs(total - 1887.7) < 0.5, f"Expected total ~1887.7, got {total}"


# ===== Expenses Test =====
class TestExpenses:
    def test_expenses_total(self, api_client):
        # Try basic auth
        r = api_client.get(
            f"{BASE_URL}/api/expenses",
            auth=(GESTOR_USER, GESTOR_PASS),
            timeout=20,
        )
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:300]}"
        data = r.json()
        expenses = data if isinstance(data, list) else (data.get("expenses") or data.get("data") or [])
        total = sum(e.get("amount", e.get("valor", 0)) for e in expenses)
        print(f"\nExpenses: {len(expenses)} items, total={total}")
        assert len(expenses) == 122, f"Expected 122 expenses, got {len(expenses)}"
        assert abs(total - 23125.79) < 1.0, f"Expected total ~23125.79, got {total}"
