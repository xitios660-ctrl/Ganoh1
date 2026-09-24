"""
Iteration 12 backend regression tests:
- Timezone-safe cash drawer (runner=197.75, gym-londres=117.40)
- drawer-debug new fields
- Add-credit cash flow with cash_credit_topups leftover
- pix-adjustments 200
"""
import os
import time
import uuid
import pytest
import requests
from requests.auth import HTTPBasicAuth
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://charts-3.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "ganoh_db")
AUTH = HTTPBasicAuth("gestor", "test-only-value")


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


def test_drawer_runner_balance():
    r = requests.get(f"{BASE_URL}/api/cash/runner/drawer", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    print("runner drawer:", data)
    assert abs(float(data["current_balance"]) - 197.75) < 0.01, f"Expected 197.75 got {data['current_balance']}"
    assert "total_credit_topups" in data


def test_drawer_gym_balance():
    r = requests.get(f"{BASE_URL}/api/cash/gym-londres/drawer", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    print("gym drawer:", data)
    assert abs(float(data["current_balance"]) - 117.40) < 0.01, f"Expected 117.40 got {data['current_balance']}"
    assert "total_credit_topups" in data


def test_drawer_debug_new_fields():
    r = requests.get(f"{BASE_URL}/api/cash/runner/drawer-debug", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ["credit_topups_cash", "total_credit_topups", "auto_apply_without_payment_method"]:
        assert key in data, f"Missing {key} in drawer-debug"
    formula = data.get("formula") or data.get("formula_string") or ""
    assert isinstance(formula, str) and len(formula) > 0, "formula string missing"
    print("debug keys ok. formula:", formula[:200])


def test_cash_today_200():
    r = requests.get(f"{BASE_URL}/api/cash/runner/today", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), (dict, list))


def test_pix_adjustments_200():
    r = requests.get(f"{BASE_URL}/api/pix-adjustments/runner", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, (list, dict))


def test_add_credit_cash_flow_with_cleanup(db):
    """Full add-credit cash flow with leftover, then cleanup, verifying drawer returns to 197.75."""
    # Initial balance snapshot
    r0 = requests.get(f"{BASE_URL}/api/cash/runner/drawer", timeout=15)
    initial_balance = float(r0.json()["current_balance"])
    print("initial:", initial_balance)

    unique_tag = f"TEST_ITER12_{uuid.uuid4().hex[:8]}"
    customer_name = f"TEST Cliente {unique_tag}"

    # 1) Create prazo customer
    cust_payload = {"name": customer_name, "phone": "11999999999", "store": "runner"}
    rc = requests.post(f"{BASE_URL}/api/prazo/customers", json=cust_payload, auth=AUTH, timeout=15)
    assert rc.status_code in (200, 201), rc.text
    customer = rc.json()
    customer_id = customer.get("id") or customer.get("_id")
    print("customer:", customer_id)

    # 2) Create a prazo order (debt)
    order_payload = {
        "store": "runner",
        "items": [{"menu_item_id": "test-item", "name": "Item Teste", "price": 30.0, "quantity": 1}],
        "total": 30.0,
        "payment_method": "prazo",
        "customer_name": customer_name,
        "notes": unique_tag,
    }
    ro = requests.post(f"{BASE_URL}/api/orders", json=order_payload, timeout=15)
    assert ro.status_code in (200, 201), ro.text
    order = ro.json()
    order_id = order.get("id") or order.get("_id")
    print("order:", order_id)

    time.sleep(1.5)

    # 3) Add credit in cash with amount > debt (30). Add 50 => leftover 20
    add_amount = 50.0
    debt = 30.0
    expected_leftover = add_amount - debt
    add_payload = {"amount": add_amount, "payment_method": "cash", "note": unique_tag}
    ra = requests.post(f"{BASE_URL}/api/prazo/customers/{customer_id}/add-credit", json=add_payload, timeout=15)
    assert ra.status_code in (200, 201), ra.text
    print("add-credit response:", ra.json())

    time.sleep(1.5)

    # 4) Verify drawer-debug shows cash prazo payment + leftover credit topup
    rdbg = requests.get(f"{BASE_URL}/api/cash/runner/drawer-debug", timeout=15).json()
    print("credit_topups_cash:", rdbg.get("credit_topups_cash"),
          "prazo_cash_payments (sum):", rdbg.get("prazo_cash_payments"),
          "total_credit_topups:", rdbg.get("total_credit_topups"))

    # 5) Verify drawer increased by FULL amount (add_amount)
    rd = requests.get(f"{BASE_URL}/api/cash/runner/drawer", timeout=15).json()
    new_balance = float(rd["current_balance"])
    print("new balance:", new_balance)
    delta = round(new_balance - initial_balance, 2)
    assert abs(delta - add_amount) < 0.01, f"Drawer delta {delta} != full add_amount {add_amount}"

    # 6) CLEANUP
    try:
        rdel = requests.delete(f"{BASE_URL}/api/orders/runner/{order_id}", timeout=15)
        print("delete order:", rdel.status_code)
    except Exception as e:
        print("order delete failed:", e)

    # delete partial payments + cash_credit_topups records tagged with unique_tag or customer_id
    try:
        pp_res = db["prazo_partial_payments"].delete_many({"customer_id": customer_id})
        print("deleted prazo_partial_payments:", pp_res.deleted_count)
    except Exception as e:
        print("pp cleanup err:", e)
    try:
        # cash_credit_topups may reference customer_id or note
        ct_res = db["cash_credit_topups"].delete_many({"$or": [
            {"customer_id": customer_id},
            {"note": unique_tag},
        ]})
        print("deleted cash_credit_topups:", ct_res.deleted_count)
    except Exception as e:
        print("ct cleanup err:", e)

    # delete customer via API if exists
    try:
        rcd = requests.delete(f"{BASE_URL}/api/prazo/customers/{customer_id}", auth=AUTH, timeout=15)
        print("delete customer:", rcd.status_code)
    except Exception as e:
        print("customer delete err:", e)
    # If API delete not available, remove directly
    try:
        db["prazo_customers"].delete_one({"id": customer_id})
        db["prazo_customers"].delete_one({"_id": customer_id})
    except Exception:
        pass

    time.sleep(1.5)

    # 7) Verify drawer back to 197.75
    r_final = requests.get(f"{BASE_URL}/api/cash/runner/drawer", timeout=15).json()
    final_balance = float(r_final["current_balance"])
    print("final balance after cleanup:", final_balance)
    assert abs(final_balance - 197.75) < 0.02, f"Drawer NOT restored: {final_balance}"
