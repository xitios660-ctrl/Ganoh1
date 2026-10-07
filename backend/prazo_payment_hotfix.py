"""Canonical prazo payment routes and reconciliation safeguards.

Fixes:
- partial/full payments update both active debt orders and archived copies;
- full payment is store-scoped and validates the amount against the live debt;
- payment history records previous/new debt;
- paid/partially-paid active orders are mirrored to history on startup;
- reconciles Segurança noite's verified 28/09 debt against the existing
  R$ 108,10 payment record from 30/09 so it cannot be charged twice.
"""
from datetime import datetime, timezone
import re
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server import _require_prazo_password

router = APIRouter()
db = None
VALID_STORES = {"runner", "gym-londres"}

SECURITY_NAME = "Segurança noite"
SECURITY_STORE = "gym-londres"
SECURITY_PAYMENT_AMOUNT = 108.10
SECURITY_REPAIR_ID = "security-night-reconcile-payment-10810-2026-09-30-v1"
SECURITY_ORDER_IDS = [
    "9cbfedb9-0cc4-4058-84b7-a76777638f94",
    "ff3fe498-837c-43a3-acc3-53503e1ef18c",
    "36de7de8-44e3-425d-b0bf-7e5603bc5067",
    "87fa1a3d-3bdd-4aaf-9c69-c816e1670d75",
    "e67cb908-ba5e-48e1-9295-e562cfb7bb55",
    "9f9206e6-af94-4a0e-82fe-015423f53f9c",
]


class FullPrazoPayment(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)
    password: str
    payment_method: str = "cash"
    store: Optional[str] = None


class PartialPrazoPayment(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)
    password: str
    payment_method: str = "cash"
    store: str


class SinglePrazoPayment(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)
    password: str
    payment_method: str = "cash"


def set_database(database):
    global db
    db = database


def _name_query(name: str):
    return {"$regex": f"^{re.escape(name)}$", "$options": "i"}


def _remaining(order):
    return round(
        max(0.0, float(order.get("total", 0) or 0) - float(order.get("partial_paid", 0) or 0)),
        2,
    )


async def _mirror_state(order_id: str, fields: dict):
    """Keep archived duplicate consistent with the canonical active order."""
    await db.order_history.update_many({"id": order_id}, {"$set": fields})


async def _record_history(customer_name, store, event_type, amount, previous_debt, new_debt, payment_method, notes=None):
    await db.prazo_history.insert_one({
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "store": store,
        "event_type": event_type,
        "amount": round(float(amount or 0), 2),
        "previous_debt": round(float(previous_debt or 0), 2),
        "new_debt": round(float(new_debt or 0), 2),
        "payment_method": payment_method,
        "notes": notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def sync_active_payment_state_to_history():
    """Repair stale archived copies that could otherwise resurrect paid debts."""
    if db is None:
        return {"synced": 0}
    q = {
        "payment_method": "prazo",
        "$or": [
            {"prazo_paid": True},
            {"partial_paid": {"$gt": 0}},
        ],
    }
    rows = await db.orders.find(q, {
        "_id": 0, "id": 1, "partial_paid": 1, "prazo_paid": 1,
        "prazo_paid_at": 1, "paid_at": 1, "prazo_paid_amount": 1,
        "prazo_paid_method": 1, "prazo_cleared": 1,
    }).to_list(10000)
    synced = 0
    for row in rows:
        oid = row.get("id")
        if not oid:
            continue
        fields = {
            "partial_paid": float(row.get("partial_paid", 0) or 0),
            "prazo_paid": bool(row.get("prazo_paid")),
        }
        for key in ("prazo_paid_at", "paid_at", "prazo_paid_amount", "prazo_paid_method", "prazo_cleared"):
            if key in row:
                fields[key] = row.get(key)
        result = await db.order_history.update_many({"id": oid}, {"$set": fields})
        synced += result.modified_count
    return {"synced": synced, "active_payment_states": len(rows)}


async def reconcile_security_night_paid_snapshot():
    """Use the existing 30/09 R$108,10 payment to settle the six 28/09 debts once."""
    if db is None:
        return {"status": "no_db"}

    marker = await db.repair_runs.find_one({"id": SECURITY_REPAIR_ID})
    if marker:
        return {"status": "already_reconciled", "amount": marker.get("amount", SECURITY_PAYMENT_AMOUNT)}

    payment = await db.prazo_payments.find_one({
        "customer_name": _name_query(SECURITY_NAME),
        "store": SECURITY_STORE,
        "amount": {"$gte": 108.095, "$lte": 108.105},
    }, {"_id": 0})
    if not payment:
        return {"status": "payment_not_found"}

    orders = await db.orders.find({
        "id": {"$in": SECURITY_ORDER_IDS},
        "customer_name": _name_query(SECURITY_NAME),
        "store": SECURITY_STORE,
        "payment_method": "prazo",
    }, {"_id": 0, "id": 1, "total": 1}).to_list(20)
    if len(orders) != 6:
        return {"status": "orders_not_complete", "found": len(orders)}

    total = round(sum(float(o.get("total", 0) or 0) for o in orders), 2)
    if abs(total - SECURITY_PAYMENT_AMOUNT) > 0.01:
        return {"status": "unexpected_total", "total": total}

    paid_at = payment.get("created_at") or datetime.now(timezone.utc).isoformat()
    method = payment.get("payment_method") or "debit"
    for order in orders:
        oid = order["id"]
        order_total = round(float(order.get("total", 0) or 0), 2)
        fields = {
            "partial_paid": order_total,
            "prazo_paid": True,
            "prazo_paid_at": paid_at,
            "prazo_paid_amount": order_total,
            "prazo_paid_method": method,
            "reconciled_from_existing_payment": True,
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.orders.update_one({"id": oid}, {"$set": fields})
        await _mirror_state(oid, fields)

    await db.repair_runs.insert_one({
        "id": SECURITY_REPAIR_ID,
        "status": "verified",
        "customer_name": SECURITY_NAME,
        "store": SECURITY_STORE,
        "amount": SECURITY_PAYMENT_AMOUNT,
        "payment_id": payment.get("id"),
        "orders": len(orders),
        "reconciled_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"status": "reconciled", "orders": 6, "amount": SECURITY_PAYMENT_AMOUNT}


@router.post("/api/prazo/abater/{customer_name}")
async def partial_payment(customer_name: str, data: PartialPrazoPayment):
    _require_prazo_password(data.password)
    store = (data.store or "").strip()
    if store not in VALID_STORES:
        raise HTTPException(status_code=422, detail="Loja inválida")

    query = {
        "customer_name": _name_query(customer_name),
        "store": store,
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", 1).to_list(2000)
    if not orders:
        raise HTTPException(status_code=404, detail="Cliente não tem dívidas no prazo")

    previous_debt = round(sum(_remaining(o) for o in orders), 2)
    amount = round(float(data.amount), 2)
    if amount > previous_debt + 0.005:
        raise HTTPException(status_code=400, detail=f"Valor maior que a dívida total (R$ {previous_debt:.2f})")

    # Customer credit is touched only when explicitly paying with saldo.
    customer = await db.prazo_customers.find_one({
        "name": _name_query(customer_name),
        "store": store,
    })
    if data.payment_method == "saldo":
        available = round(float((customer or {}).get("credit", 0) or 0), 2)
        if amount > available + 0.005:
            raise HTTPException(status_code=400, detail=f"Saldo a favor insuficiente. Disponível: R$ {available:.2f}")
        if customer:
            await db.prazo_customers.update_one({"id": customer["id"]}, {"$set": {"credit": round(available - amount, 2)}})

    remaining_payment = amount
    orders_updated = 0
    orders_paid_off = 0
    now = datetime.now(timezone.utc).isoformat()

    for order in orders:
        if remaining_payment <= 0.005:
            break
        debt = _remaining(order)
        if debt <= 0:
            continue
        applied = round(min(remaining_payment, debt), 2)
        new_partial = round(float(order.get("partial_paid", 0) or 0) + applied, 2)
        total = round(float(order.get("total", 0) or 0), 2)
        paid = new_partial >= total - 0.005

        fields = {"partial_paid": min(new_partial, total)}
        if paid:
            fields.update({
                "prazo_paid": True,
                "prazo_paid_at": now,
                "prazo_paid_amount": total,
                "prazo_paid_method": data.payment_method,
            })
            orders_paid_off += 1

        await db.orders.update_one({"id": order["id"], "store": store}, {"$set": fields})
        await _mirror_state(order["id"], fields)
        remaining_payment = round(remaining_payment - applied, 2)
        orders_updated += 1

    new_debt = round(previous_debt - amount, 2)
    record = {
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "amount": amount,
        "payment_method": data.payment_method,
        "type": "partial_payment",
        "store": store,
        "created_at": now,
        "orders_updated": orders_updated,
        "orders_paid_off": orders_paid_off,
        "previous_debt": previous_debt,
        "new_debt": new_debt,
    }
    await db.prazo_partial_payments.insert_one(record)
    await _record_history(customer_name, store, "payment_partial", amount, previous_debt, new_debt, data.payment_method)

    return {
        "success": True,
        "message": f"Pagamento de R$ {amount:.2f} registrado!",
        "previous_debt": previous_debt,
        "paid": amount,
        "new_debt": new_debt,
        "orders_updated": orders_updated,
        "orders_paid_off": orders_paid_off,
    }


@router.post("/api/prazo/pay-all/{customer_name}")
async def full_payment(customer_name: str, data: FullPrazoPayment):
    _require_prazo_password(data.password)

    name_rx = _name_query(customer_name)
    base = {
        "customer_name": name_rx,
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }
    stores = await db.orders.distinct("store", base)
    stores = [s for s in stores if s in VALID_STORES]

    if data.store:
        if data.store not in VALID_STORES:
            raise HTTPException(status_code=422, detail="Loja inválida")
        store = data.store
    elif len(stores) == 1:
        store = stores[0]
    elif len(stores) == 0:
        raise HTTPException(status_code=404, detail="Cliente não tem dívidas no prazo")
    else:
        raise HTTPException(status_code=409, detail="Cliente possui dívidas em mais de uma loja; informe a loja")

    query = {**base, "store": store}
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", 1).to_list(2000)
    if not orders:
        raise HTTPException(status_code=404, detail="Cliente não tem dívidas no prazo")

    previous_debt = round(sum(_remaining(o) for o in orders), 2)
    amount = round(float(data.amount), 2)
    if abs(amount - previous_debt) > 0.02:
        raise HTTPException(
            status_code=400,
            detail=f"Para quitar tudo, o valor deve ser R$ {previous_debt:.2f}. Para pagar parte, use Abater.",
        )

    now = datetime.now(timezone.utc).isoformat()
    modified = 0
    for order in orders:
        total = round(float(order.get("total", 0) or 0), 2)
        fields = {
            "partial_paid": total,
            "prazo_paid": True,
            "prazo_paid_at": now,
            "prazo_paid_amount": total,
            "prazo_paid_method": data.payment_method,
        }
        r = await db.orders.update_one({"id": order["id"], "store": store}, {"$set": fields})
        modified += r.modified_count
        await _mirror_state(order["id"], fields)

    await db.prazo_payments.insert_one({
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "amount": previous_debt,
        "payment_method": data.payment_method,
        "type": "full_payment",
        "store": store,
        "created_at": now,
        "previous_debt": previous_debt,
        "new_debt": 0.0,
    })
    await _record_history(customer_name, store, "payment_full", previous_debt, previous_debt, 0.0, data.payment_method)

    return {
        "success": True,
        "message": f"Todos os débitos de {customer_name} foram quitados ({data.payment_method})",
        "orders_paid": modified,
        "previous_debt": previous_debt,
        "new_debt": 0.0,
        "store": store,
    }


@router.post("/api/prazo/pay/{order_id}")
async def single_order_payment(order_id: str, data: SinglePrazoPayment):
    _require_prazo_password(data.password)
    order = await db.orders.find_one({"id": order_id, "payment_method": "prazo"}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    remaining = _remaining(order)
    amount = round(float(data.amount), 2)
    if abs(amount - remaining) > 0.02:
        raise HTTPException(status_code=400, detail=f"Valor para quitar este pedido: R$ {remaining:.2f}")

    now = datetime.now(timezone.utc).isoformat()
    total = round(float(order.get("total", 0) or 0), 2)
    fields = {
        "partial_paid": total,
        "prazo_paid": True,
        "prazo_paid_at": now,
        "prazo_paid_amount": total,
        "prazo_paid_method": data.payment_method,
    }
    await db.orders.update_one({"id": order_id}, {"$set": fields})
    await _mirror_state(order_id, fields)

    store = order.get("store", "")
    name = order.get("customer_name", "")
    await db.prazo_payments.insert_one({
        "id": str(uuid.uuid4()),
        "order_id": order_id,
        "customer_name": name,
        "amount": remaining,
        "payment_method": data.payment_method,
        "type": "single_order_payment",
        "store": store,
        "created_at": now,
        "previous_debt": remaining,
        "new_debt": 0.0,
    })
    await _record_history(name, store, "payment_order", remaining, remaining, 0.0, data.payment_method)
    return {"success": True, "message": "Pagamento registrado", "new_debt": 0.0}
