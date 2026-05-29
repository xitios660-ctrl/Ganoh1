"""
One-shot script to mirror data from the production GANOH instance
(https://prazo-payment-sys.emergent.host) into the local MongoDB
so all pages (Cardápio, Cozinha, Gestor) show matching numbers.

Usage:
    python import_from_prod.py
"""
import os
import sys
import requests
from pymongo import MongoClient
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

SRC = "https://prazo-payment-sys.emergent.host"
GESTOR_AUTH = ("gestor", "ganoh2024")
STORES = ["runner", "gym-londres"]

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

client = MongoClient(MONGO_URL)
db = client[DB_NAME]


def fetch(path, auth=None):
    url = f"{SRC}{path}"
    r = requests.get(url, auth=auth, timeout=60)
    r.raise_for_status()
    return r.json()


def replace_collection(name, docs, key="id"):
    """Drop the matching docs and reinsert. Uses delete_many on the keys
    we are inserting, so other docs (none expected) remain untouched."""
    if not docs:
        print(f"  • {name}: 0 docs (nothing to import)")
        return
    # Strip any potential _id to avoid duplicate-key issues
    cleaned = []
    for d in docs:
        d = {k: v for k, v in d.items() if k != "_id"}
        cleaned.append(d)
    keys = [d.get(key) for d in cleaned if d.get(key) is not None]
    if keys:
        db[name].delete_many({key: {"$in": keys}})
    db[name].insert_many(cleaned)
    print(f"  • {name}: imported {len(cleaned)} docs")


def wipe(name):
    res = db[name].delete_many({})
    print(f"  • {name}: wiped {res.deleted_count}")


def main():
    print("=" * 60)
    print(f"Importing from {SRC}")
    print(f"Into          {MONGO_URL} / {DB_NAME}")
    print("=" * 60)

    # -------- 1) MENU (custom items adicionados pelo gestor / cozinha) --------
    # /api/menu/{store} retorna MENU_DATA hardcoded + custom items.
    # /api/kitchen/menu/{store} retorna SOMENTE os custom items da collection db.menu.
    # Importamos os customs para reproduzir o banco fielmente.
    print("\n[1] MENU (custom items)")
    all_menu = []
    for store in STORES:
        data = fetch(f"/api/kitchen/menu/{store}")
        items = data.get("items", [])
        for it in items:
            it["store"] = store
        all_menu.extend(items)
        print(f"   {store}: {len(items)} custom items")
    wipe("menu")
    if all_menu:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in all_menu]
        db["menu"].insert_many(cleaned)
        print(f"  • menu: imported {len(cleaned)} docs")

    # -------- 2) ADICIONAIS (globais) --------
    print("\n[2] ADICIONAIS")
    data = fetch("/api/kitchen/adicionais")
    adicionais = data.get("adicionais", [])
    wipe("adicionais")
    if adicionais:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in adicionais]
        db["adicionais"].insert_many(cleaned)
        print(f"  • adicionais: imported {len(cleaned)} docs")

    # -------- 3) STOCK por loja --------
    print("\n[3] STOCK")
    all_stock = []
    for store in STORES:
        data = fetch(f"/api/stock/{store}")
        stock = data.get("stock", [])
        # Mantém "name" (pois é necessário para items custom).
        # Remove apenas campos que são calculados a cada request.
        for s in stock:
            s.pop("low_stock", None)
            s["store"] = store
        all_stock.extend(stock)
        print(f"   {store}: {len(stock)} items")
    wipe("stock")
    if all_stock:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in all_stock]
        db["stock"].insert_many(cleaned)
        print(f"  • stock: imported {len(cleaned)} docs")

    # -------- 4) ORDERS (ativos) + ORDER_HISTORY (entregues) + PRAZO ORDERS --------
    # A API /api/orders/{store} é limitada a 100 itens, então só ela perde a maior parte
    # dos pedidos prazo antigos. Reconstruímos os prazo a partir de /api/prazo/debts
    # que retorna até 1000 e contém TODOS os pedidos prazo pendentes.
    print("\n[4] ORDERS + ORDER_HISTORY + PRAZO")
    wipe("orders")
    wipe("order_history")
    all_active = []
    all_history = []
    all_prazo = []
    for store in STORES:
        # Active orders (limited to 100 by API, mostly recent)
        active = fetch(f"/api/orders/{store}").get("orders", [])
        for o in active:
            o["store"] = store
        # Delivered orders
        history = fetch(f"/api/orders/{store}/history?limit=10000").get("orders", [])
        for o in history:
            o["store"] = store
        # All prazo unpaid orders (from debts endpoint, agregado por cliente)
        debts_data = fetch(f"/api/prazo/debts?store={store}")
        prazo_orders = []
        for debt in debts_data.get("debts", []):
            customer_name = debt.get("name", "Desconhecido")
            for o in debt.get("orders", []):
                # Reconstruct an order document
                prazo_orders.append({
                    "id": o.get("id"),
                    "store": store,
                    "customer_name": customer_name,
                    "items": o.get("items", []),
                    "total": o.get("total", 0),
                    "partial_paid": o.get("partial_paid", 0),
                    "payment_method": "prazo",
                    "prazo_paid": False,
                    "status": "ready",
                    "created_at": o.get("date"),
                    "updated_at": o.get("date"),
                })
        all_active.extend(active)
        all_history.extend(history)
        all_prazo.extend(prazo_orders)
        print(f"   {store}: active={len(active)}, history={len(history)}, prazo_unpaid={len(prazo_orders)}")

    # Dedup: priorize prazo orders (have correct partial_paid), then active (recent), then history
    by_id = {}
    for o in all_history:
        by_id[o.get("id")] = o
    for o in all_active:
        by_id[o.get("id")] = o
    for o in all_prazo:
        # Only overwrite if not already a more complete record from active
        oid = o.get("id")
        if oid not in by_id or by_id[oid].get("payment_method") != "prazo":
            by_id[oid] = o
        else:
            # Merge partial_paid into existing
            by_id[oid]["partial_paid"] = o.get("partial_paid", by_id[oid].get("partial_paid", 0))

    # Separate into orders (active/prazo) and order_history (delivered)
    active_ids = set(o.get("id") for o in all_active) | set(o.get("id") for o in all_prazo)
    history_ids = set(o.get("id") for o in all_history) - active_ids

    final_active = [by_id[i] for i in active_ids if i in by_id]
    final_history = [by_id[i] for i in history_ids if i in by_id]

    if final_active:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in final_active]
        db["orders"].insert_many(cleaned)
        print(f"  • orders: imported {len(cleaned)} docs (active + prazo unpaid)")
    if final_history:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in final_history]
        db["order_history"].insert_many(cleaned)
        print(f"  • order_history: imported {len(cleaned)} docs (delivered only)")

    # -------- 5) PIX ADJUSTMENTS por loja --------
    print("\n[5] PIX ADJUSTMENTS")
    wipe("pix_adjustments")
    all_adj = []
    for store in STORES:
        data = fetch(f"/api/pix-adjustments/{store}")
        adjs = data.get("adjustments", [])
        for a in adjs:
            a["store"] = store
        all_adj.extend(adjs)
        print(f"   {store}: {len(adjs)} adjustments")
    if all_adj:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in all_adj]
        db["pix_adjustments"].insert_many(cleaned)
        print(f"  • pix_adjustments: imported {len(cleaned)} docs")

    # -------- 6) PRAZO CUSTOMERS --------
    print("\n[6] PRAZO CUSTOMERS")
    wipe("prazo_customers")
    all_customers = []
    for store in STORES:
        data = fetch(f"/api/prazo/customers?store={store}")
        custs = data.get("customers", [])
        for c in custs:
            c["store"] = store
        all_customers.extend(custs)
        print(f"   {store}: {len(custs)} customers")
    if all_customers:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in all_customers]
        db["prazo_customers"].insert_many(cleaned)
        print(f"  • prazo_customers: imported {len(cleaned)} docs")

    # -------- 7) PRAZO PAYMENTS (full + partial) --------
    print("\n[7] PRAZO PAYMENTS")
    wipe("prazo_payments")
    wipe("prazo_partial_payments")
    for store in STORES:
        data = fetch(f"/api/prazo/payments-history?store={store}&limit=10000")
        payments = data.get("payments", [])
        full = [p for p in payments if p.get("type") == "full_payment"]
        partial = [p for p in payments if p.get("type") == "partial_payment"]
        for p in full + partial:
            p["store"] = store
            p.pop("type", None)  # type is computed when joined
        print(f"   {store}: full={len(full)}, partial={len(partial)}")
        if full:
            cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in full]
            db["prazo_payments"].insert_many(cleaned)
        if partial:
            cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in partial]
            db["prazo_partial_payments"].insert_many(cleaned)

    # -------- 8) EXPENSES (auth) --------
    print("\n[8] EXPENSES")
    wipe("expenses")
    data = fetch("/api/expenses?limit=10000", auth=GESTOR_AUTH)
    expenses = data.get("expenses", [])
    if expenses:
        cleaned = [{k: v for k, v in d.items() if k != "_id"} for d in expenses]
        db["expenses"].insert_many(cleaned)
        print(f"  • expenses: imported {len(cleaned)} docs")

    # -------- 9) CASH DRAWER CONFIG --------
    print("\n[9] CASH DRAWER CONFIG")
    wipe("cash_drawer_config")
    for store in STORES:
        data = fetch(f"/api/cash/{store}/drawer")
        # Persist current balance and shift state per store
        doc = {
            "store": store,
            "current_balance": data.get("current_balance", 0),
            "initial_balance": data.get("initial_balance", 0),
            "last_reset_at": data.get("last_reset_at"),
            "shift_morning_initial": data.get("shift_morning_initial"),
            "shift_afternoon_initial": data.get("shift_afternoon_initial"),
        }
        # Remove None values to avoid clobbering schema defaults
        doc = {k: v for k, v in doc.items() if v is not None}
        db["cash_drawer_config"].insert_one(doc)
        print(f"   {store}: balance={doc.get('current_balance')}")

    # -------- 10) PRAZO CHARGE MESSAGES (settings) --------
    print("\n[10] PRAZO CHARGE MESSAGES")
    # /api/prazo/charge-messages?store=X => { messages: {...} }
    for store in STORES:
        data = fetch(f"/api/prazo/charge-messages?store={store}")
        # The endpoint returns the saved messages object; persist via settings
        # collection used by the backend (key = "prazo_charge_messages_{store}")
        key = f"prazo_charge_messages_{store}"
        db["settings"].delete_one({"key": key})
        db["settings"].insert_one({"key": key, "value": data, "store": store})
        msgs = data.get("messages") if isinstance(data, dict) else data
        print(f"   {store}: charge messages stored ({len(msgs) if isinstance(msgs, list) else 'obj'})")

    print("\n" + "=" * 60)
    print("Import finished.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        sys.exit(1)
