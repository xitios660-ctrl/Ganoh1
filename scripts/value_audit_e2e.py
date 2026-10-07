"""One-shot production audit for menu prices, numeric totals, prazo and sale preservation.

Runs only when GANOH_VALUE_AUDIT_ONCE=true. It creates one marked temporary sale
to verify the ready-order cleanup behavior, then removes every test artifact and
restores stock. All other checks are read-only.
"""
import base64
import json
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytz
from pymongo import MongoClient

ROOT = "http://127.0.0.1:" + os.environ.get("PORT", "10000")
USER = (os.environ.get("GESTOR_USERNAME") or "gestor").strip()
PASSWORD = (os.environ.get("GESTOR_PASSWORD") or "").strip()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "ganoh_production")
MARKER = "VALUE_AUDIT_" + uuid.uuid4().hex[:10]
BRT = pytz.timezone("America/Sao_Paulo")

if not PASSWORD:
    raise RuntimeError("GESTOR_PASSWORD is required")


def auth_header():
    raw = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    return "Basic " + raw


def request(method, path, data=None, auth=False, timeout=20):
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
            ctype = (resp.headers.get("Content-Type") or "").lower()
            return json.loads(raw) if "json" in ctype else raw.decode(errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {raw[:260]}") from exc


def get(path, auth=False):
    return request("GET", path, auth=auth)


def post(path, data, auth=False):
    return request("POST", path, data=data, auth=auth)


def patch(path, data, auth=False):
    return request("PATCH", path, data=data, auth=auth)


def delete(path, auth=False):
    return request("DELETE", path, auth=auth)


def m(value):
    return round(float(value or 0), 2)


def close(a, b, tol=0.02):
    return abs(m(a) - m(b)) <= tol


def assert_true(cond, msg):
    if not cond:
        raise AssertionError(msg)


def parse_dt(value):
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT)


def direct_receivables(db, store=None):
    q = {"payment_method": "prazo", "prazo_paid": {"$ne": True}}
    if store:
        q["store"] = store
    total = 0.0
    groups = set()
    for o in db.orders.find(q, {"_id": 0, "store": 1, "customer_name": 1, "total": 1, "partial_paid": 1}):
        remaining = float(o.get("total") or 0) - float(o.get("partial_paid") or 0)
        if remaining > 0:
            total += remaining
            groups.add((o.get("store", ""), o.get("customer_name", "")))
    return round(total, 2), len(groups)


def main():
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
    db = client[DB_NAME]
    created_order_id = None
    stock_snapshot = None

    try:
        for _ in range(75):
            try:
                if get("/healthz").get("status") == "ok":
                    break
            except Exception:
                time.sleep(2)
        else:
            raise RuntimeError("health unavailable")
        print("VALUE AUDIT PASS 01 health", flush=True)

        menus = {}
        for store in ("runner", "gym-londres"):
            payload = get(f"/api/menu/{store}")
            items = payload.get("items") or []
            assert_true(items, f"{store}: menu vazio")
            bad = [
                x for x in items
                if not isinstance(x.get("price"), (int, float))
                or not math.isfinite(float(x.get("price")))
                or float(x.get("price")) <= 0
            ]
            assert_true(not bad, f"{store}: preço inválido no cardápio")
            cafes = [x for x in items if (x.get("name") or "").strip().lower() == "café com leite"]
            assert_true(len(cafes) == 1, f"{store}: Café com Leite duplicado/ausente")
            assert_true(close(cafes[0].get("price"), 8.00), f"{store}: Café com Leite != 8,00")
            menus[store] = {x.get("id"): x for x in items}
        print("VALUE AUDIT PASS 02 menus + all positive prices + Café com Leite R$ 8,00", flush=True)

        dashboard = get("/api/gestor/dashboard", auth=True)
        stores = dashboard.get("stores") or {}
        assert_true("runner" in stores and "gym-londres" in stores, "dashboard sem as duas lojas")
        expected_today = sum(float(stores[s]["today"]["total"]) for s in stores)
        expected_month = sum(float(stores[s]["month"]["total"]) for s in stores)
        expected_today_orders = sum(int(stores[s]["today"]["order_count"]) for s in stores)
        expected_month_orders = sum(int(stores[s]["month"]["order_count"]) for s in stores)
        combined = dashboard.get("combined") or {}
        assert_true(close(combined.get("today_total"), expected_today), "dashboard today_total não fecha")
        assert_true(close(combined.get("month_total"), expected_month), "dashboard month_total não fecha")
        assert_true(int(combined.get("today_orders", -1)) == expected_today_orders, "dashboard today_orders não fecha")
        assert_true(int(combined.get("month_orders", -1)) == expected_month_orders, "dashboard month_orders não fecha")
        for store, row in stores.items():
            by_pm = row["today"].get("by_payment_method") or {}
            assert_true(close(sum(float(v or 0) for v in by_pm.values()), row["today"]["total"]),
                        f"{store}: formas de pagamento não fecham com total")
        print("VALUE AUDIT PASS 03 dashboard totals + payment methods arithmetic", flush=True)

        for store in ("runner", "gym-londres"):
            cash = get(f"/api/cash/{store}/today")
            by_pm = cash.get("by_payment_method") or {}
            assert_true(close(sum(float(v or 0) for v in by_pm.values()), cash.get("total")),
                        f"{store}: cash total != formas")
            shifts = cash.get("shifts") or {}
            mt = float((shifts.get("morning") or {}).get("total") or 0)
            at = float((shifts.get("afternoon") or {}).get("total") or 0)
            assert_true(close(mt + at, cash.get("total")), f"{store}: turnos não fecham com total")
            for shift_name in ("morning", "afternoon"):
                sh = shifts.get(shift_name) or {}
                assert_true(close(sum(float(v or 0) for v in (sh.get("by_payment") or {}).values()), sh.get("total")),
                            f"{store}: {shift_name} formas não fecham")
        print("VALUE AUDIT PASS 04 caixa diário + turnos + formas fechando", flush=True)

        summary = get("/api/gestor/financial-summary", auth=True)
        direct_total, direct_groups = direct_receivables(db)
        current = summary.get("current") or {}
        assert_true(close(current.get("receivables"), direct_total), "resumo financeiro: contas a receber divergentes")
        assert_true(int(current.get("debt_groups", -1)) == direct_groups, "resumo financeiro: grupos de dívida divergentes")
        for key in ("today", "week", "month", "year"):
            p = (summary.get("periods") or {}).get(key) or {}
            assert_true(close(float(p.get("revenue") or 0) - float(p.get("expenses") or 0), p.get("result_simple")),
                        f"financial-summary {key}: resultado não fecha")
        print("VALUE AUDIT PASS 05 financial summary + receivables + result arithmetic", flush=True)

        all_debts = get("/api/prazo/debts")
        api_total = sum(float(x.get("total") or 0) for x in all_debts.get("debts", []))
        assert_true(close(api_total, direct_total), "prazo/debts total diverge do banco")
        for store in ("runner", "gym-londres"):
            direct_store, _ = direct_receivables(db, store)
            pd = get(f"/api/prazo/debts?store={store}")
            api_store = sum(float(x.get("total") or 0) for x in pd.get("debts", []))
            assert_true(close(api_store, direct_store), f"{store}: prazo/debts diverge do banco")
        print("VALUE AUDIT PASS 06 prazo/devedores exact match with live DB", flush=True)

        expenses = get("/api/expenses", auth=True)
        rows = expenses.get("expenses") or []
        direct_expenses = list(db.expenses.find({}, {"_id": 0}))
        assert_true(int(expenses.get("count", len(rows))) == len(direct_expenses), "quantidade de gastos divergente")
        assert_true(close(expenses.get("total"), sum(float(x.get("amount") or 0) for x in direct_expenses)),
                    "total de gastos divergente")
        parsed = [parse_dt(x.get("created_at")) for x in rows if x.get("created_at")]
        parsed = [x for x in parsed if x]
        assert_true(all(parsed[i] >= parsed[i+1] for i in range(len(parsed)-1)), "lista de gastos não está newest-first")
        print("VALUE AUDIT PASS 07 expenses count + total + ordering", flush=True)

        now_brt = datetime.now(BRT)
        week = get(f"/api/gestor/chart/weekly-with-expenses?date={now_brt.strftime('%Y-%m-%d')}", auth=True)
        assert_true(close(week.get("total_revenue", 0) - week.get("total_expenses", 0), week.get("total_profit", 0)),
                    "gráfico semanal: resultado não fecha")
        assert_true(len(week.get("data") or []) == 7, "gráfico semanal sem 7 dias")
        monthly = get(f"/api/gestor/chart/monthly-with-expenses?month={now_brt.month}&year={now_brt.year}", auth=True)
        assert_true(close(monthly.get("total_revenue", 0) - monthly.get("total_expenses", 0), monthly.get("total_profit", 0)),
                    "gráfico mensal: resultado não fecha")
        yearly = get(f"/api/gestor/chart/yearly?year={now_brt.year}", auth=True)
        assert_true(yearly.get("data") is not None, "gráfico anual indisponível")
        print("VALUE AUDIT PASS 08 weekly/monthly/yearly financial charts", flush=True)

        # Targeted regression for the bug seen in the screenshots:
        # finalized sale can leave the kitchen but must remain in history/financial totals.
        gym_menu = get("/api/menu/gym-londres")["items"]
        cafe = next(x for x in gym_menu if (x.get("name") or "").strip().lower() == "café com leite")
        item_id = str(cafe["id"]).split("-")[0]
        stock_snapshot = db.stock.find_one({"store": "gym-londres", "menu_item_id": item_id})
        before = get("/api/cash/gym-londres/today")
        order = post("/api/orders", {
            "store": "gym-londres",
            "customer_name": MARKER,
            "items": [{
                "menu_item_id": cafe["id"],
                "name": cafe["name"],
                "price": 8.00,
                "quantity": 1,
            }],
            "total": 8.00,
            "original_total": 8.00,
            "payment_method": "debit",
            "pickup_time": "VALUE_AUDIT",
        })
        created_order_id = order["id"]
        assert_true(close(order.get("total"), 8.00), "pedido Café com Leite não gravou R$ 8,00")
        patch(f"/api/orders/gym-londres/{created_order_id}/status", {"status": "preparing"})
        patch(f"/api/orders/gym-londres/{created_order_id}/status", {"status": "ready"})
        during = get("/api/cash/gym-londres/today")
        assert_true(close(float(during.get("total") or 0) - float(before.get("total") or 0), 8.00),
                    "venda débito R$ 8,00 não entrou no caixa diário")
        removed = delete(f"/api/orders/gym-londres/{created_order_id}")
        assert_true(removed.get("archived") is True, "pedido pronto foi apagado em vez de arquivado")
        active = get("/api/orders/gym-londres").get("orders") or []
        assert_true(not any(x.get("id") == created_order_id for x in active), "pedido removido ainda aparece na cozinha")
        hist = get("/api/orders/gym-londres/history").get("orders") or []
        assert_true(any(x.get("id") == created_order_id for x in hist), "venda removida da cozinha sumiu do histórico")
        after = get("/api/cash/gym-londres/today")
        assert_true(close(float(after.get("total") or 0) - float(before.get("total") or 0), 8.00),
                    "valor caiu após retirar pedido pronto da cozinha")
        print("VALUE AUDIT PASS 09 R$ 8,00 debit sale survives kitchen removal", flush=True)

    finally:
        if created_order_id:
            db.orders.delete_many({"id": created_order_id})
            db.order_history.delete_many({"id": created_order_id})
        db.orders.delete_many({"customer_name": {"$regex": f"^{MARKER}"}})
        db.order_history.delete_many({"customer_name": {"$regex": f"^{MARKER}"}})
        if stock_snapshot is not None:
            restore = {k: v for k, v in stock_snapshot.items() if k != "_id"}
            db.stock.replace_one({"store": "gym-londres", "menu_item_id": "50"}, restore, upsert=True)
        elif stock_snapshot is None:
            db.stock.delete_many({"store": "gym-londres", "menu_item_id": "50", "updated_at": {"$exists": True}})
        leftovers = (
            db.orders.count_documents({"customer_name": {"$regex": f"^{MARKER}"}})
            + db.order_history.count_documents({"customer_name": {"$regex": f"^{MARKER}"}})
        )
        if leftovers:
            raise RuntimeError(f"value audit cleanup left {leftovers} records")
        client.close()
        print("VALUE AUDIT PASS 10 cleanup verified", flush=True)

    print("GANOH VALUE AUDIT PASSED", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("GANOH VALUE AUDIT FAILED: " + str(exc)[:700], file=sys.stderr, flush=True)
        sys.exit(1)
