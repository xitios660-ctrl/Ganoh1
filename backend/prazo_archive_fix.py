"""Keep unpaid prazo debts visible after kitchen order archiving."""
from datetime import datetime, timezone, timedelta
import re
import uuid

from fastapi import APIRouter, HTTPException

router = APIRouter()
db = None


def set_database(database):
    global db
    db = database


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
    return {"restored": restored}


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
        events.append({
            "id": f"credit-order-{order_id}",
            "order_id": order_id,
            "customer_id": customer_id,
            "customer_name": name,
            "store": order.get("store", customer.get("store", "")),
            "event_type": "credit_used",
            "amount": float(order.get("credit_used", 0) or 0),
            "previous_credit": float(order.get("previous_credit", 0) or 0),
            "new_credit": float(order.get("new_credit", 0) or 0),
            "notes": "Crédito consumido no pedido",
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
