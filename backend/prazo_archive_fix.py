"""Keep unpaid prazo debts visible after kitchen order archiving."""
from datetime import datetime, timezone, timedelta
import re

from fastapi import APIRouter, HTTPException

router = APIRouter()
db = None

TARGET_REPAIR_ID = "security-night-pdf-debt-2026-09-28-v1"
TARGET_CUSTOMER_ID = "0bdbd62d-a39f-479a-bd12-1bc3e57d3b85"
TARGET_CUSTOMER_NAME = "Segurança noite"
TARGET_STORE = "gym-londres"
TARGET_ORDERS = [
    {
        "id": "9cbfedb9-0cc4-4058-84b7-a76777638f94",
        "created_at": "2026-09-24T23:16:00+00:00",
        "total": 31.00,
        "items": [
            {"name": "3 ovos mexidos", "price": 12.00, "quantity": 2},
            {"name": "Café com Leite (Leite Integral)", "price": 7.00, "quantity": 1},
        ],
    },
    {
        "id": "ff3fe498-837c-43a3-acc3-53503e1ef18c",
        "created_at": "2026-09-24T23:24:00+00:00",
        "total": 16.00,
        "items": [{"name": "3 ovos mexidos + queijo branco", "price": 16.00, "quantity": 1}],
    },
    {
        "id": "36de7de8-44e3-425d-b0bf-7e5603bc5067",
        "created_at": "2026-09-24T23:26:00+00:00",
        "total": 10.50,
        "items": [{"name": "Paçoquita", "price": 1.50, "quantity": 7}],
    },
    {
        "id": "87fa1a3d-3bdd-4aaf-9c69-c816e1670d75",
        "created_at": "2026-09-25T22:04:00+00:00",
        "total": 12.00,
        "items": [{"name": "kitkat", "price": 6.00, "quantity": 2}],
    },
    {
        "id": "e67cb908-ba5e-48e1-9295-e562cfb7bb55",
        "created_at": "2026-09-25T23:05:00+00:00",
        "total": 32.60,
        "items": [
            {"name": "Frango, Mussarela, Tomate e Orégano", "price": 26.00, "quantity": 1},
            {"name": "Coca-Cola Lata", "price": 6.60, "quantity": 1},
        ],
    },
    {
        "id": "9f9206e6-af94-4a0e-82fe-015423f53f9c",
        "created_at": "2026-09-25T23:19:00+00:00",
        "total": 6.00,
        "items": [{"name": "kitkat", "price": 6.00, "quantity": 1}],
    },
]


def set_database(database):
    global db
    db = database


async def _repair_verified_security_night_debt_once():
    """Restore the six verified PDF debts exactly once.

    This is intentionally guarded by a repair marker so later legitimate payments
    are never undone on a future restart.
    """
    if await db.repair_runs.find_one({"id": TARGET_REPAIR_ID}):
        return {"applied": False, "reason": "already_applied"}

    customer = await db.prazo_customers.find_one({"id": TARGET_CUSTOMER_ID})
    if not customer:
        customer = await db.prazo_customers.find_one({
            "name": {"$regex": f"^{re.escape(TARGET_CUSTOMER_NAME)}$", "$options": "i"},
            "store": TARGET_STORE,
        })
    if not customer:
        await db.prazo_customers.insert_one({
            "id": TARGET_CUSTOMER_ID,
            "name": TARGET_CUSTOMER_NAME,
            "phone": "",
            "notes": "Recuperado do relatório gerencial de 28/09/2026",
            "store": TARGET_STORE,
            "credit": 0.0,
            "source": "pdf_recovery",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    repaired = 0
    for spec in TARGET_ORDERS:
        oid = spec["id"]
        active = await db.orders.find_one({"id": oid})
        history = await db.order_history.find_one({"id": oid})

        if active:
            base = {k: v for k, v in active.items() if k != "_id"}
        elif history:
            base = {k: v for k, v in history.items() if k != "_id"}
        else:
            base = {
                "id": oid,
                "created_at": spec["created_at"],
                "updated_at": spec["created_at"],
                "items": spec["items"],
                "source": "pdf_recovery",
            }

        base.update({
            "id": oid,
            "customer_name": TARGET_CUSTOMER_NAME,
            "store": TARGET_STORE,
            "total": float(spec["total"]),
            "partial_paid": 0.0,
            "payment_method": "prazo",
            "prazo_paid": False,
            "status": "delivered",
            "created_at": base.get("created_at") or spec["created_at"],
            "updated_at": base.get("updated_at") or spec["created_at"],
            "items": base.get("items") or spec["items"],
            "source": base.get("source") or "pdf_recovery",
            "verified_pdf_debt_restored": True,
            "verified_pdf_debt_restored_at": datetime.now(timezone.utc).isoformat(),
        })
        for field in ("prazo_paid_at", "paid_at", "prazo_paid_method", "prazo_cleared"):
            base.pop(field, None)

        await db.orders.replace_one({"id": oid}, base, upsert=True)
        repaired += 1

    rows = await db.orders.find({
        "id": {"$in": [x["id"] for x in TARGET_ORDERS]},
        "customer_name": {"$regex": f"^{re.escape(TARGET_CUSTOMER_NAME)}$", "$options": "i"},
        "store": TARGET_STORE,
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }, {"_id": 0, "total": 1, "partial_paid": 1}).to_list(20)
    restored_total = round(sum(
        max(0.0, float(x.get("total", 0) or 0) - float(x.get("partial_paid", 0) or 0))
        for x in rows
    ), 2)
    if len(rows) != 6 or abs(restored_total - 108.10) > 0.01:
        raise RuntimeError("verified prazo repair did not reach expected 6 orders / 108.10")

    await db.repair_runs.insert_one({
        "id": TARGET_REPAIR_ID,
        "status": "verified",
        "customer_id": TARGET_CUSTOMER_ID,
        "store": TARGET_STORE,
        "orders": 6,
        "amount": 108.10,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"applied": True, "orders": repaired, "amount": restored_total}


async def restore_unpaid_prazo_from_history():
    """Restore archived unpaid prazo orders to the active collection, idempotently."""
    if db is None:
        return {"restored": 0}
    archived = await db.order_history.find({
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }).to_list(5000)
    restored = 0
    for old in archived:
        order_id = old.get("id")
        if not order_id:
            continue
        if await db.orders.find_one({"id": order_id}, {"_id": 1}):
            continue
        doc = {k: v for k, v in old.items() if k != "_id"}
        doc["status"] = "delivered"
        doc["restored_prazo_debt"] = True
        doc["restored_from_history_at"] = datetime.now(timezone.utc).isoformat()
        await db.orders.insert_one(doc)
        restored += 1

    target = await _repair_verified_security_night_debt_once()
    if target.get("applied"):
        print(
            f"PRAZO_TARGET_REPAIR verified orders={target.get('orders')} amount={target.get('amount'):.2f}",
            flush=True,
        )
    return {"restored": restored, "target_repair": target}


@router.get("/api/orders/{store}")
async def safe_get_orders(store: str, status: str = None):
    """Archive stale kitchen orders without removing unpaid prazo debts."""
    if store not in ("runner", "gym-londres"):
        raise HTTPException(status_code=422, detail="Loja inválida")
    query = {"store": store}
    if status:
        query["status"] = status

    if status is None or status == "ready":
        stale_iso = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        stale_query = {
            "store": store,
            "status": "ready",
            "$and": [
                {"$or": [
                    {"updated_at": {"$lt": stale_iso}},
                    {"updated_at": {"$exists": False}, "created_at": {"$lt": stale_iso}},
                ]},
                {"$or": [
                    {"payment_method": {"$ne": "prazo"}},
                    {"prazo_paid": True},
                ]},
            ],
        }
        stale = await db.orders.find(stale_query).to_list(500)
        ids = []
        for old in stale:
            doc = {k: v for k, v in old.items() if k != "_id"}
            doc["status"] = "delivered"
            doc["delivered_at"] = doc.get("updated_at") or doc.get("created_at") or datetime.now(timezone.utc).isoformat()
            doc["auto_archived"] = True
            await db.order_history.update_one({"id": doc.get("id")}, {"$set": doc}, upsert=True)
            if doc.get("id"):
                ids.append(doc["id"])
        if ids:
            await db.orders.delete_many({"id": {"$in": ids}})

    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"orders": orders}


@router.get("/api/prazo/customers/{customer_id}/history")
async def prazo_customer_history(customer_id: str, limit: int = 200):
    """Show debt/credit history, including credit consumed directly by orders."""
    customer = await db.prazo_customers.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    name = customer.get("name", "")
    name_rx = {"$regex": f"^{re.escape(name)}$", "$options": "i"}
    events = await db.prazo_history.find({
        "$or": [{"customer_id": customer_id}, {"customer_name": name_rx}]
    }, {"_id": 0}).sort("created_at", -1).to_list(limit)

    seen_order_ids = {e.get("order_id") for e in events if e.get("event_type") == "credit_used" and e.get("order_id")}
    credit_orders = []
    for collection in (db.orders, db.order_history):
        rows = await collection.find({"customer_name": name_rx, "credit_used": {"$gt": 0}}, {"_id": 0}).to_list(2000)
        credit_orders.extend(rows)
    by_id = {}
    for order in credit_orders:
        if order.get("id"):
            by_id[order["id"]] = order
    for order_id, order in by_id.items():
        if order_id in seen_order_ids:
            continue
        credit_used = float(order.get("credit_used", 0) or 0)
        order_total = float(order.get("total", 0) or 0)
        overrun = round(max(0.0, order_total - credit_used), 2)
        note = "Crédito consumido no pedido"
        if overrun > 0:
            note += f"; pedido excedeu o saldo em R$ {overrun:.2f}, valor lançado no prazo"
        events.append({
            "id": f"credit-order-{order_id}",
            "order_id": order_id,
            "customer_id": customer_id,
            "customer_name": name,
            "store": order.get("store", customer.get("store", "")),
            "event_type": "credit_used",
            "amount": credit_used,
            "previous_credit": float(order.get("previous_credit", 0) or 0),
            "new_credit": float(order.get("new_credit", 0) or 0),
            "previous_debt": 0,
            "new_debt": overrun,
            "notes": note,
            "created_at": order.get("created_at") or "",
        })
    events.sort(key=lambda e: e.get("created_at") or "", reverse=True)
    events = events[:limit]

    debt_orders = await db.orders.find({
        "customer_name": name_rx,
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }, {"_id": 0, "total": 1, "partial_paid": 1}).to_list(5000)
    current_debt = round(sum(max(0, float(o.get("total", 0) or 0) - float(o.get("partial_paid", 0) or 0)) for o in debt_orders), 2)
    return {
        "customer": {
            "id": customer_id,
            "name": name,
            "phone": customer.get("phone", ""),
            "credit": customer.get("credit", 0),
            "store": customer.get("store", ""),
            "current_debt": current_debt,
        },
        "events": events,
        "total_count": len(events),
    }
