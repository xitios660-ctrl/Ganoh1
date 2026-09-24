"""
Backend tests for the GANOH redesign iteration (green theme + Semana chart + VT flow).

Focus areas (per review_request):
  - POST /api/auth/login with gestor / test-only-value
  - GET /api/gestor/chart/weekly returns 7 daily buckets
  - POST /api/cash/{store}/withdraw with category=vt -> creates BOTH a
    cash withdrawal AND an automatic expense
  - GET /api/gestor/dashboard / chart/daily / chart/monthly / chart/yearly basic regression
"""
import os
import time
import uuid
from datetime import datetime, timedelta

import pytest
import requests

def _read_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    env_path = "/app/frontend/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL is not set")


BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"
GESTOR_AUTH = ("gestor", "test-only-value")
TAG = f"TestE2E-{int(time.time())}"


# -------------------------------------------------------------------- Auth
class TestAuth:
    def test_login_success(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"username": "gestor", "password": "test-only-value"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("success") is True
        assert data.get("username", "").lower() == "gestor"
        assert "tenant_id" in data

    def test_login_invalid_password(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"username": "gestor", "password": "wrong-password"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_basic_auth_gestor_endpoint(self):
        # verify_gestor uses HTTP Basic
        r = requests.get(f"{API}/gestor/dashboard", auth=GESTOR_AUTH, timeout=15)
        assert r.status_code == 200, r.text


# -------------------------------------------------------------- Weekly chart
class TestWeeklyChart:
    def test_weekly_chart_no_filters(self):
        r = requests.get(f"{API}/gestor/chart/weekly", auth=GESTOR_AUTH, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # endpoint should return a list of 7 day buckets
        assert "data" in data or "daily_data" in data or isinstance(data, dict)
        # Find the 7-item array somewhere in the payload
        buckets = data.get("data") or data.get("daily_data") or data.get("days")
        if buckets is None:
            # Try keys that look like arrays of 7
            for v in data.values():
                if isinstance(v, list) and len(v) == 7:
                    buckets = v
                    break
        assert buckets is not None, f"Could not find weekly buckets in payload: {list(data.keys())}"
        assert len(buckets) == 7, f"Expected 7 daily buckets, got {len(buckets)}"
        # Each bucket should have day_name in Portuguese short form
        valid_day_names = {"Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"}
        for b in buckets:
            assert "day_name" in b, f"Bucket missing day_name: {b}"
            assert b["day_name"] in valid_day_names
            assert "total" in b
            assert "date" in b

    def test_weekly_chart_with_date(self):
        d = datetime.now().strftime("%Y-%m-%d")
        r = requests.get(
            f"{API}/gestor/chart/weekly",
            params={"date": d},
            auth=GESTOR_AUTH,
            timeout=20,
        )
        assert r.status_code == 200, r.text

    def test_weekly_chart_runner_filter(self):
        r = requests.get(
            f"{API}/gestor/chart/weekly",
            params={"store": "runner"},
            auth=GESTOR_AUTH,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        buckets = data.get("data") or data.get("daily_data") or data.get("days")
        if buckets is None:
            for v in data.values():
                if isinstance(v, list) and len(v) == 7:
                    buckets = v
                    break
        assert buckets and len(buckets) == 7

    def test_weekly_chart_gym_londres_filter(self):
        r = requests.get(
            f"{API}/gestor/chart/weekly",
            params={"store": "gym-londres"},
            auth=GESTOR_AUTH,
            timeout=20,
        )
        assert r.status_code == 200, r.text

    def test_weekly_chart_requires_auth(self):
        r = requests.get(f"{API}/gestor/chart/weekly", timeout=10)
        assert r.status_code == 401


# ---------------------------------------------------- Other chart regressions
class TestOtherCharts:
    def test_daily_chart(self):
        r = requests.get(f"{API}/gestor/chart/daily", auth=GESTOR_AUTH, timeout=20)
        assert r.status_code == 200, r.text

    def test_monthly_chart(self):
        r = requests.get(f"{API}/gestor/chart/monthly", auth=GESTOR_AUTH, timeout=20)
        assert r.status_code == 200, r.text

    def test_yearly_chart(self):
        r = requests.get(f"{API}/gestor/chart/yearly", auth=GESTOR_AUTH, timeout=20)
        assert r.status_code == 200, r.text


# ----------------------------------------------------------- Dashboard
class TestDashboard:
    def test_dashboard_returns_combined_stats(self):
        r = requests.get(f"{API}/gestor/dashboard", auth=GESTOR_AUTH, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Should have at least some structure (top sold/least sold/totals)
        assert isinstance(data, dict)
        # No mongo _id leakage
        assert "_id" not in data


# ------------------------------------------------------------------ VT flow
class TestVTWithdrawal:
    """POST /api/cash/{store}/withdraw with category=vt should:
       1. Insert a cash_withdrawal record
       2. Insert an automatic expense doc with description starting 'Vale Transporte'
    """

    STORE = "runner"

    @classmethod
    def _seed_balance(cls):
        # ensure drawer has enough cash for VT
        requests.post(f"{API}/cash/{cls.STORE}/reset", timeout=15)
        # Initial balance via set-balance endpoint
        requests.post(
            f"{API}/cash/{cls.STORE}/set-balance",
            json={"balance": 500.0, "notes": "seed for VT test"},
            timeout=15,
        )

    def test_vt_creates_withdrawal_and_expense(self):
        self._seed_balance()

        # snapshot expenses before
        r0 = requests.get(
            f"{API}/expenses",
            params={"store": self.STORE, "category": "vt"},
            auth=GESTOR_AUTH,
            timeout=15,
        )
        assert r0.status_code == 200, r0.text
        before = r0.json()
        before_count = len(before if isinstance(before, list) else before.get("expenses", []))

        # withdraw VT
        amount = 12.34
        payload = {"amount": amount, "category": "vt", "description": f"{TAG}-VT"}
        r1 = requests.post(
            f"{API}/cash/{self.STORE}/withdraw", json=payload, timeout=15
        )
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body.get("success") is True
        assert body.get("expense_created") is True
        wd = body.get("withdrawal", {})
        assert wd.get("category") == "vt"
        assert abs(wd.get("amount") - amount) < 0.001

        # verify expenses list grew by 1 with description starting 'Vale Transporte'
        r2 = requests.get(
            f"{API}/expenses",
            params={"store": self.STORE, "category": "vt"},
            auth=GESTOR_AUTH,
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        after_list = r2.json()
        after = after_list if isinstance(after_list, list) else after_list.get("expenses", [])
        assert len(after) >= before_count + 1, (
            f"Expense not auto-created. before={before_count} after={len(after)}"
        )
        latest = sorted(after, key=lambda e: e.get("created_at", ""), reverse=True)[0]
        assert latest["category"] == "vt"
        assert "Vale Transporte" in latest.get("description", "")
        assert abs(latest.get("amount", 0) - amount) < 0.001
        assert latest.get("store") == self.STORE

        # cleanup: delete the auto-created expense to keep db clean
        try:
            requests.delete(
                f"{API}/expenses/{latest['id']}",
                auth=GESTOR_AUTH,
                timeout=10,
            )
        except Exception:
            pass

    def test_vt_blocks_when_insufficient_balance(self):
        # reset to a tiny balance then try to withdraw a huge amount
        requests.post(f"{API}/cash/{self.STORE}/reset", timeout=10)
        requests.post(
            f"{API}/cash/{self.STORE}/set-balance",
            json={"balance": 1.0, "notes": "seed for insufficient balance test"},
            timeout=10,
        )
        r = requests.post(
            f"{API}/cash/{self.STORE}/withdraw",
            json={"amount": 9999.0, "category": "vt", "description": f"{TAG}-OVER"},
            timeout=10,
        )
        assert r.status_code == 400
