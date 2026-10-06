"""Export a read-only cash-flow snapshot to Render logs for report generation.

Runs only when explicitly launched by start_render.py. It does not mutate MongoDB.
The output is gzip+base64 chunked so it can be retrieved safely from Render logs.
"""
import base64
import gzip
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

from pymongo import MongoClient
import pytz

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

try:
    from recovered_history import archived_month
except Exception:
    archived_month = None

BRT = pytz.timezone("America/Sao_Paulo")


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


def fnum(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def blank_day():
    return {
        "entry_total": 0.0,
        "expense_total": 0.0,
        "net": 0.0,
        "entry_count": 0,
        "expense_count": 0,
        "by_store": {
            "runner": {"entries": 0.0, "expenses": 0.0},
            "gym-londres": {"entries": 0.0, "expenses": 0.0},
            "all": {"entries": 0.0, "expenses": 0.0},
        },
        "by_method": {},
        "by_entry_source": {},
        "by_expense_category": {},
    }


def add_entry(days, date_key, amount, store, source, method=None):
    amount = fnum(amount)
    if amount == 0:
        return
    d = days[date_key]
    d["entry_total"] = round(d["entry_total"] + amount, 2)
    d["entry_count"] += 1
    s = store if store in ("runner", "gym-londres") else "all"
    d["by_store"][s]["entries"] = round(d["by_store"][s]["entries"] + amount, 2)
    d["by_entry_source"][source] = round(d["by_entry_source"].get(source, 0) + amount, 2)
    if method:
        d["by_method"][method] = round(d["by_method"].get(method, 0) + amount, 2)


def add_expense(days, date_key, amount, store, category):
    amount = fnum(amount)
    if amount == 0:
        return
    d = days[date_key]
    d["expense_total"] = round(d["expense_total"] + amount, 2)
    d["expense_count"] += 1
    s = store if store in ("runner", "gym-londres") else "all"
    d["by_store"][s]["expenses"] = round(d["by_store"][s]["expenses"] + amount, 2)
    cat = (category or "outros").strip() or "outros"
    d["by_expense_category"][cat] = round(d["by_expense_category"].get(cat, 0) + amount, 2)


def main():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=15000)
    db = client[db_name]
    client.admin.command("ping")

    days = defaultdict(blank_day)

    # Sales with money received at sale time. Exclude prazo because its cash flow
    # belongs to the actual debt-payment date. Include received/ready/delivered.
    projection = {
        "_id": 0, "id": 1, "store": 1, "created_at": 1, "total": 1,
        "payment_method": 1, "status": 1, "manual_sale": 1,
    }
    active_orders = list(db.orders.find({
        "status": {"$in": ["received", "ready", "delivered"]},
        "payment_method": {"$ne": "prazo"},
    }, projection))
    history_orders = list(db.order_history.find({
        "status": {"$in": ["ready", "delivered"]},
        "payment_method": {"$ne": "prazo"},
    }, projection))

    # De-duplicate orders that may appear in both active and history.
    order_by_id = {}
    anonymous = []
    for order in active_orders + history_orders:
        oid = order.get("id")
        if oid:
            if oid not in order_by_id or order in active_orders:
                order_by_id[oid] = order
        else:
            anonymous.append(order)
    all_orders = list(order_by_id.values()) + anonymous

    for order in all_orders:
        dt = parse_dt(order.get("created_at"))
        if not dt:
            continue
        add_entry(
            days, dt.strftime("%Y-%m-%d"), order.get("total", 0),
            order.get("store"), "venda_manual" if order.get("manual_sale") else "venda",
            order.get("payment_method") or "outro",
        )

    # Manual PIX adjustments are explicit cash-flow entries in the existing charts.
    pix_adjustments = list(db.pix_adjustments.find({"removed": {"$ne": True}}, {"_id": 0}))
    for adj in pix_adjustments:
        dt = parse_dt(adj.get("created_at"))
        if not dt:
            continue
        add_entry(days, dt.strftime("%Y-%m-%d"), adj.get("amount", 0), adj.get("store"), "ajuste_pix", "pix")

    # Payments of debts are counted on the date the money was actually received.
    prazo_full = list(db.prazo_payments.find({}, {"_id": 0}))
    prazo_partial = list(db.prazo_partial_payments.find({}, {"_id": 0}))
    for pay, source in [(p, "prazo_quitacao") for p in prazo_full] + [(p, "prazo_parcial") for p in prazo_partial]:
        dt = parse_dt(pay.get("created_at"))
        if not dt:
            continue
        add_entry(
            days, dt.strftime("%Y-%m-%d"), pay.get("amount", 0), pay.get("store"), source,
            pay.get("payment_method") or "prazo_recebido",
        )

    # Cash credit top-ups are physical cash entries not represented by an order.
    topups = list(db.cash_credit_topups.find({}, {"_id": 0}))
    for topup in topups:
        dt = parse_dt(topup.get("created_at"))
        if not dt:
            continue
        add_entry(days, dt.strftime("%Y-%m-%d"), topup.get("amount", 0), topup.get("store"), "credito_cliente", "cash")

    # Every registered expense is a cash-flow outflow according to the current system.
    expenses = list(db.expenses.find({}, {"_id": 0}))
    for exp in expenses:
        # Prefer explicit expense date when present; otherwise use created_at.
        raw_dt = exp.get("date") or exp.get("expense_date") or exp.get("created_at")
        dt = parse_dt(raw_dt)
        if not dt and isinstance(raw_dt, str) and len(raw_dt) >= 10:
            try:
                dt = BRT.localize(datetime.strptime(raw_dt[:10], "%Y-%m-%d"))
            except Exception:
                dt = None
        if not dt:
            continue
        add_expense(days, dt.strftime("%Y-%m-%d"), exp.get("amount", 0), exp.get("store"), exp.get("category"))

    exact_rows = []
    running = 0.0
    for date_key in sorted(days):
        d = days[date_key]
        d["net"] = round(d["entry_total"] - d["expense_total"], 2)
        running = round(running + d["net"], 2)
        row = {"date": date_key, **d, "running_from_zero": running}
        exact_rows.append(row)

    # Historical paid sales recovered from the old system exist only as monthly totals.
    # Do not fabricate daily dates for them.
    archive_rows = []
    if archived_month:
        for year in range(2024, datetime.now(BRT).year + 1):
            for month in range(1, 13):
                total, count = archived_month(year, month, None)
                runner, runner_count = archived_month(year, month, "runner")
                gym, gym_count = archived_month(year, month, "gym-londres")
                if fnum(total) or int(count or 0):
                    archive_rows.append({
                        "year": year, "month": month,
                        "revenue": fnum(total), "orders": int(count or 0),
                        "runner_revenue": fnum(runner), "runner_orders": int(runner_count or 0),
                        "gym_revenue": fnum(gym), "gym_orders": int(gym_count or 0),
                    })

    # Read-only diagnostic summary for today's GYM Londres sales. No customer names/items.
    today_key = datetime.now(BRT).strftime("%Y-%m-%d")
    today_gym_orders = []
    diagnostic_projection = {
        "_id": 0, "id": 1, "store": 1, "created_at": 1, "total": 1,
        "payment_method": 1, "status": 1, "manual_sale": 1,
    }
    for collection_name in ("orders", "order_history"):
        for order in db[collection_name].find({"store": "gym-londres"}, diagnostic_projection):
            dt = parse_dt(order.get("created_at"))
            if not dt or dt.strftime("%Y-%m-%d") != today_key:
                continue
            today_gym_orders.append({
                "source": collection_name,
                "id_suffix": str(order.get("id") or "")[-8:],
                "created_at": order.get("created_at"),
                "total": fnum(order.get("total")),
                "payment_method": order.get("payment_method"),
                "status": order.get("status"),
                "manual_sale": bool(order.get("manual_sale")),
            })

    payload = {
        "generated_at_brt": datetime.now(BRT).isoformat(),
        "database": db_name,
        "exact_daily": exact_rows,
        "archived_monthly_sales": archive_rows,
        "today_gym_orders": today_gym_orders,
        "counts": {
            "orders_exact": len(all_orders),
            "expenses": len(expenses),
            "pix_adjustments": len(pix_adjustments),
            "prazo_full_payments": len(prazo_full),
            "prazo_partial_payments": len(prazo_partial),
            "cash_credit_topups": len(topups),
        },
        "notes": [
            "Entradas exatas: vendas nao-a-prazo recebidas/prontas/entregues, ajustes PIX, pagamentos a prazo e creditos em dinheiro registrados.",
            "Saidas exatas: gastos registrados no modulo de despesas.",
            "Vendas historicas recuperadas antes da migracao estao disponiveis apenas por mes; nao foram distribuidas artificialmente por dia.",
            "running_from_zero e um acumulado matematico dos lancamentos disponiveis, nao o saldo bancario real sem um saldo inicial informado.",
        ],
    }

    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    packed = gzip.compress(raw, compresslevel=9)
    b64 = base64.b64encode(packed).decode("ascii")
    checksum = hashlib.sha256(raw).hexdigest()
    chunk_size = 7000
    chunks = [b64[i:i + chunk_size] for i in range(0, len(b64), chunk_size)]
    print(f"CASHFLOW_EXPORT_BEGIN chunks={len(chunks)} sha256={checksum} bytes={len(raw)}", flush=True)
    for i, chunk in enumerate(chunks, 1):
        print(f"CASHFLOW_EXPORT_CHUNK {i}/{len(chunks)} {chunk}", flush=True)
    print(f"CASHFLOW_EXPORT_END sha256={checksum}", flush=True)
    client.close()


if __name__ == "__main__":
    main()
