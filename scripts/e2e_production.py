"""Write-capable production E2E smoke for GANOH.

Runs only when GANOH_E2E_ONCE=true. It exercises the real HTTP API on loopback,
uses clearly marked temporary records, and cleans every created document in a
finally block (including prazo audit/payment rows) so production totals are not
polluted by the test.
"""
import base64
import json
import os
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from pymongo import MongoClient

ROOT = "http://127.0.0.1:" + os.environ.get("PORT", "10000")
USER = (os.environ.get("GESTOR_USERNAME") or "gestor").strip()
PASSWORD = (os.environ.get("GESTOR_PASSWORD") or "").strip()
PRAZO_PASSWORD = (os.environ.get("PRAZO_PASSWORD") or "").strip()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "ganoh_production")
MARKER = "E2E_TEST_" + uuid.uuid4().hex[:10]
STORE = "runner"

if not PASSWORD:
    raise RuntimeError("GESTOR_PASSWORD is required for E2E")
if not PRAZO_PASSWORD:
    raise RuntimeError("PRAZO_PASSWORD is required for prazo E2E")


def auth_header():
    raw = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    return "Basic " + raw


def request(method, path, data=None, auth=False, timeout=15):
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    if auth:
        headers["Authorization"] = auth_header()
    req = Request(ROOT + path, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return {}
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "application/json" in content_type:
                return json.loads(raw)
            return raw.decode(errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {raw[:240]}") from exc


def get(path, auth=False):
    return request("GET", path, auth=auth)


def post(path, data, auth=False):
    return request("POST", path, data=data, auth=auth)


def patch(path, data, auth=False):
    return request("PATCH", path, data=data, auth=auth)


def delete(path, auth=False):
    return request("DELETE", path, auth=auth)


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def money(value):
    return round(float(value or 0), 2)


def debt_for(payload, name):
    for row in payload.get("debts", []):
        if row.get("name") == name and row.get("store") == STORE:
            return row
    return None


def main():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]
    created_order_ids = []
    created_customer_ids = []
    created_expense_ids = []
    created_manual_ids = []
    stock_snapshot = None
    selected_item = None

    try:
        for _ in range(60):
            try:
                if get("/healthz").get("status") == "ok":
                    break
            except (URLError, RuntimeError):
                time.sleep(2)
        else:
            raise RuntimeError("Health check did not become ready")

        print("E2E PASS 01 health", flush=True)
        home = request("GET", "/")
        assert_true("Ganoh em preparação" not in home, "maintenance/preparation page is visible")
        print("E2E PASS 02 public site", flush=True)

        runner_menu = get("/api/menu/runner")
        gym_menu = get("/api/menu/gym-londres")
        assert_true(runner_menu.get("items"), "Runner menu empty")
        assert_true(gym_menu.get("items"), "GYM Londres menu empty")
        selected_item = runner_menu["items"][0]
        item_id = str(selected_item["id"]).split("-")[0]
        item_price = money(selected_item.get("price"))
        assert_true(item_price > 0, "selected menu item price invalid")
        print("E2E PASS 03 both menus", flush=True)

        stock_snapshot = db.stock.find_one({"store": STORE, "menu_item_id": item_id})
        baseline_orders = get(f"/api/orders/{STORE}")["orders"]
        baseline_cash = get(f"/api/cash/{STORE}/drawer")
        baseline_dashboard = get("/api/gestor/dashboard", auth=True)
        baseline_week = get("/api/gestor/chart/weekly?date=2026-09-29", auth=True)
        baseline_week_fin = get("/api/gestor/chart/weekly-with-expenses?date=2026-09-29", auth=True)
        assert_true("combined" in baseline_dashboard, "Gestor dashboard unavailable")
        assert_true(len(baseline_week.get("data", [])) == 7, "weekly sales chart does not have 7 days")
        assert_true(len(baseline_week_fin.get("data", [])) == 7, "weekly financial chart does not have 7 days")
        print("E2E PASS 04 gestor + weekly charts", flush=True)

        # Real menu -> discounted CASH order -> kitchen -> tracking -> gestor -> cash.
        cash_name = MARKER + "_PEDIDO"
        discounted_total = money(max(0.5, item_price - min(1.23, max(0.01, item_price / 5))))
        cash_order = post("/api/orders", {
            "store": STORE,
            "customer_name": cash_name,
            "items": [{
                "menu_item_id": selected_item["id"],
                "name": selected_item["name"],
                "price": item_price,
                "quantity": 1,
            }],
            "total": discounted_total,
            "original_total": item_price,
            "payment_method": "cash",
            "pickup_time": "E2E",
        })
        cash_id = cash_order["id"]
        created_order_ids.append(cash_id)
        assert_true(money(cash_order["total"]) == discounted_total, "discounted total not saved")
        assert_true(discounted_total < item_price, "discount scenario was not discounted")
        print("E2E PASS 05 discounted order created", flush=True)

        tracked = get(f"/api/orders/{STORE}/{cash_id}")
        assert_true(tracked.get("customer_name") == cash_name, "order tracking cannot find created order")
        live_orders = get(f"/api/orders/{STORE}")["orders"]
        assert_true(any(o.get("id") == cash_id for o in live_orders), "order did not reach kitchen feed")
        kitchen_stats = get(f"/api/kitchen/{STORE}/stats")
        assert_true(isinstance(kitchen_stats, dict) and kitchen_stats, "kitchen stats unavailable")
        print("E2E PASS 06 order -> kitchen -> tracking", flush=True)

        dash_after_order = get("/api/gestor/dashboard", auth=True)
        assert_true(
            money(dash_after_order["combined"]["today_total"]) >= money(baseline_dashboard["combined"]["today_total"]) + discounted_total - 0.01,
            "order revenue did not reach Gestor",
        )
        cash_after_order = get(f"/api/cash/{STORE}/drawer")
        assert_true(
            money(cash_after_order["current_balance"]) >= money(baseline_cash["current_balance"]) + discounted_total - 0.01,
            "cash order did not reach cash drawer",
        )
        print("E2E PASS 07 order -> gestor + cash", flush=True)

        for status in ("preparing", "ready", "delivered"):
            updated = patch(f"/api/orders/{STORE}/{cash_id}/status", {"status": status})
            assert_true(updated.get("status") == status, f"status transition failed: {status}")
        history = get(f"/api/orders/{STORE}/history")["orders"]
        assert_true(any(o.get("id") == cash_id for o in history), "delivered order missing from history")
        print("E2E PASS 08 received -> preparing -> ready -> delivered/history", flush=True)

        # Manual sale through Gestor, list, then delete.
        manual = post("/api/gestor/manual-sale", {
            "store": STORE,
            "payment_method": "pix",
            "amount": 0.83,
            "period": "tarde",
            "description": MARKER + "_VENDA_MANUAL",
        }, auth=True)
        manual_id = manual["order_id"]
        created_manual_ids.append(manual_id)
        manual_sales = get("/api/gestor/manual-sales?limit=100", auth=True)["sales"]
        assert_true(any(x.get("id") == manual_id for x in manual_sales), "manual sale missing from Gestor list")
        delete(f"/api/gestor/manual-sale/{manual_id}", auth=True)
        created_manual_ids.remove(manual_id)
        print("E2E PASS 09 manual sale create/list/delete", flush=True)

        # Expense create/read/financial chart/delete.
        expense = post("/api/expenses", {
            "description": MARKER + "_GASTO",
            "amount": 0.37,
            "category": "outros",
            "store": STORE,
            "notes": MARKER,
        }, auth=True)
        expense_id = expense["id"]
        created_expense_ids.append(expense_id)
        expenses = get("/api/expenses?store=runner", auth=True)["expenses"]
        assert_true(any(x.get("id") == expense_id for x in expenses), "expense missing from Gestor")
        week_fin_during = get("/api/gestor/chart/weekly-with-expenses?date=2026-09-29", auth=True)
        assert_true("total_expenses" in week_fin_during and "total_profit" in week_fin_during, "weekly result fields missing")
        delete(f"/api/expenses/{expense_id}", auth=True)
        created_expense_ids.remove(expense_id)
        print("E2E PASS 10 expense -> weekly result -> delete", flush=True)

        # Prazo customer / comanda.
        customer_name = MARKER + "_DEVEDOR"
        customer = post("/api/prazo/customers", {
            "name": customer_name,
            "phone": "",
            "notes": MARKER,
            "credit": 0,
            "store": STORE,
        }, auth=True)
        customer_id = customer["id"]
        created_customer_ids.append(customer_id)
        customers = get(f"/api/prazo/customers?store={STORE}")["customers"]
        assert_true(any(x.get("id") == customer_id for x in customers), "prazo customer missing")
        print("E2E PASS 11 prazo/comanda customer", flush=True)

        # Add value (credit) and consume it again, without touching cash.
        credit_added = post(f"/api/prazo/customers/{customer_id}/add-credit", {
            "amount": 2.31,
            "payment_method": "pix",
            "notes": MARKER + "_ADD_VALUE",
        })
        assert_true(money(credit_added.get("new_credit")) == 2.31, "add value/credit failed")
        credit_used = post(f"/api/prazo/customers/{customer_id}/use-credit", {
            "amount": 2.31,
            "payment_method": "pix",
            "notes": MARKER + "_USE_VALUE",
        })
        assert_true(money(credit_used.get("new_credit")) == 0.0, "credit use did not restore zero")
        print("E2E PASS 12 add value/credit + use credit", flush=True)

        # Create a prazo order (the operational comanda/debt flow).
        prazo_total = money(max(4.0, min(item_price, 8.47)))
        prazo_order = post("/api/orders", {
            "store": STORE,
            "customer_name": customer_name,
            "items": [{
                "menu_item_id": selected_item["id"],
                "name": selected_item["name"],
                "price": item_price,
                "quantity": 1,
            }],
            "total": prazo_total,
            "payment_method": "prazo",
            "pickup_time": "E2E_COMANDA",
        })
        prazo_id = prazo_order["id"]
        created_order_ids.append(prazo_id)
        debts = get(f"/api/prazo/debts?store={STORE}")
        row = debt_for(debts, customer_name)
        assert_true(row is not None and abs(money(row["total"]) - prazo_total) < 0.02, "prazo debt not created")
        print("E2E PASS 13 comanda/prazo -> devedor", flush=True)

        # Add value while debt exists: must auto-apply, never create simultaneous debt + positive credit.
        auto_amount = min(1.11, round(prazo_total / 3, 2))
        auto = post(f"/api/prazo/customers/{customer_id}/add-credit", {
            "amount": auto_amount,
            "payment_method": "pix",
            "notes": MARKER + "_AUTO_ABATE",
        })
        assert_true(money(auto.get("applied_to_debt")) == money(auto_amount), "add value did not auto-apply to debt")
        assert_true(money(auto.get("new_credit")) == 0.0, "debt customer incorrectly retained positive credit")
        debts = get(f"/api/prazo/debts?store={STORE}")
        row = debt_for(debts, customer_name)
        expected_after_auto = money(prazo_total - auto_amount)
        assert_true(row and abs(money(row["total"]) - expected_after_auto) < 0.02, "debt total wrong after auto-apply")
        print("E2E PASS 14 add value -> automatic debt reduction", flush=True)

        # Partial debt payment/discount-style adjustment from Prazo UI.
        abater_amount = min(1.22, max(0.01, money(expected_after_auto / 3)))
        abater = post("/api/prazo/abater/" + quote(customer_name), {
            "amount": abater_amount,
            "password": PRAZO_PASSWORD,
            "payment_method": "pix",
            "store": STORE,
        })
        assert_true(abater.get("success") is True, "partial debt payment failed")
        debts = get(f"/api/prazo/debts?store={STORE}")
        row = debt_for(debts, customer_name)
        expected_remaining = money(expected_after_auto - abater_amount)
        assert_true(row and abs(money(row["total"]) - expected_remaining) < 0.02, "debt total wrong after partial payment")
        print("E2E PASS 15 devedor partial payment", flush=True)

        # Full settlement must remove the customer from the debtor list.
        paid = post("/api/prazo/pay-all/" + quote(customer_name), {
            "amount": expected_remaining,
            "password": PRAZO_PASSWORD,
            "payment_method": "pix",
        })
        assert_true(paid.get("success") is True, "full prazo settlement failed")
        debts = get(f"/api/prazo/debts?store={STORE}")
        assert_true(debt_for(debts, customer_name) is None, "paid customer still appears as debtor")
        print("E2E PASS 16 full settlement removes debtor", flush=True)

        # Core read surfaces still healthy after write flows.
        assert_true(get("/api/gestor/financial-summary", auth=True).get("periods"), "financial summary failed")
        assert_true(get("/api/gestor/chart/yearly?year=2026", auth=True).get("data"), "yearly chart failed")
        assert_true(get("/api/gestor/chart/weekly?date=2026-09-29", auth=True).get("data"), "weekly chart failed")
        assert_true(get("/api/stock/runner").get("stock") is not None, "stock endpoint failed")
        print("E2E PASS 17 gestor/charts/stock after writes", flush=True)

    finally:
        # Restore stock exactly as it was before the two real order writes.
        try:
            if selected_item:
                item_id = str(selected_item["id"]).split("-")[0]
                if stock_snapshot is None:
                    db.stock.delete_many({"store": STORE, "menu_item_id": item_id, "updated_at": {"$exists": True}})
                else:
                    restore = {k: v for k, v in stock_snapshot.items() if k != "_id"}
                    db.stock.replace_one(
                        {"store": STORE, "menu_item_id": item_id},
                        restore,
                        upsert=True,
                    )

            # Remove every temporary record and every audit/payment side effect.
            db.orders.delete_many({"$or": [{"id": {"$in": created_order_ids + created_manual_ids}}, {"customer_name": {"$regex": f"^{MARKER}"}}]})
            db.order_history.delete_many({"$or": [{"id": {"$in": created_order_ids}}, {"customer_name": {"$regex": f"^{MARKER}"}}]})
            db.prazo_customers.delete_many({"$or": [{"id": {"$in": created_customer_ids}}, {"name": {"$regex": f"^{MARKER}"}}]})
            db.prazo_partial_payments.delete_many({"customer_name": {"$regex": f"^{MARKER}"}})
            db.prazo_payments.delete_many({"customer_name": {"$regex": f"^{MARKER}"}})
            db.prazo_history.delete_many({"customer_name": {"$regex": f"^{MARKER}"}})
            db.cash_credit_topups.delete_many({"customer_name": {"$regex": f"^{MARKER}"}})
            db.expenses.delete_many({"$or": [{"id": {"$in": created_expense_ids}}, {"description": {"$regex": f"^{MARKER}"}}, {"notes": MARKER}]})
            db.orders.delete_many({"manual_sale": True, "customer_name": {"$regex": f"^{MARKER}"}})

            # Prove cleanup rather than merely attempting it.
            leftovers = {
                "orders": db.orders.count_documents({"customer_name": {"$regex": f"^{MARKER}"}}),
                "history": db.order_history.count_documents({"customer_name": {"$regex": f"^{MARKER}"}}),
                "customers": db.prazo_customers.count_documents({"name": {"$regex": f"^{MARKER}"}}),
                "partial_payments": db.prazo_partial_payments.count_documents({"customer_name": {"$regex": f"^{MARKER}"}}),
                "payments": db.prazo_payments.count_documents({"customer_name": {"$regex": f"^{MARKER}"}}),
                "prazo_history": db.prazo_history.count_documents({"customer_name": {"$regex": f"^{MARKER}"}}),
                "cash_topups": db.cash_credit_topups.count_documents({"customer_name": {"$regex": f"^{MARKER}"}}),
                "expenses": db.expenses.count_documents({"$or": [{"description": {"$regex": f"^{MARKER}"}}, {"notes": MARKER}]}),
            }
            if any(leftovers.values()):
                raise RuntimeError("E2E cleanup left records: " + json.dumps(leftovers, sort_keys=True))
            print("E2E PASS 18 cleanup verified: no test records left", flush=True)
        finally:
            client.close()

    print("GANOH E2E PASSED: order, discount, kitchen, tracking, gestor, cash, statuses, history, manual sale, expense, weekly result, prazo/comanda, debtor, add value, auto-apply, partial payment, full settlement, charts, stock, cleanup", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("GANOH E2E FAILED: " + str(exc)[:500], file=sys.stderr, flush=True)
        sys.exit(1)
