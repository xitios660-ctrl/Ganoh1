"""Protect finalized sales from disappearing when a ready order is cleared.

The kitchen trash action removes a finalized order from the operational screen,
but keeps its financial/history record. Also restores the single verified
GYM Londres debit movement visible in the 06/10/2026 14:00 screenshot.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
import pytz

router = APIRouter()
db = None

BRT = pytz.timezone("America/Sao_Paulo")
VALID_STORES = {"runner", "gym-londres"}
RECOVERY_ID = "gym-debit-screenshot-2026-10-06-5010"
RECOVERY_ORDER_ID = "gym-debit-recovery-2026-10-06-5010"


def set_database(database):
    global db
    db = database


def _parse_dt(value):
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


@router.delete("/api/orders/{store}/{order_id}")
async def clear_order_without_losing_sale(store: str, order_id: str):
    if db is None:
        raise HTTPException(status_code=503, detail="Banco indisponível")
    if store not in VALID_STORES:
        raise HTTPException(status_code=404, detail="Loja inválida")

    order = await db.orders.find_one({"id": order_id, "store": store})
    if not order:
        history = await db.order_history.find_one({"id": order_id, "store": store})
        if history:
            return {
                "success": True,
                "archived": True,
                "message": "Pedido já estava fora da cozinha e continua no histórico",
            }
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    now = datetime.now(timezone.utc).isoformat()
    status = order.get("status")

    # Ready/delivered means the sale has already been finalized. Clearing it
    # from the kitchen must never erase the value from Vendas/Financeiro.
    if status in {"ready", "delivered"}:
        doc = {k: v for k, v in order.items() if k != "_id"}
        doc["status"] = "delivered"
        doc["delivered_at"] = doc.get("delivered_at") or now
        doc["updated_at"] = now
        doc["removed_from_kitchen"] = True
        doc["removed_from_kitchen_at"] = now
        await db.order_history.update_one(
            {"id": order_id, "store": store},
            {"$set": doc},
            upsert=True,
        )
        await db.orders.delete_one({"id": order_id, "store": store})
        return {
            "success": True,
            "archived": True,
            "message": "Pedido retirado da cozinha e venda preservada no histórico",
        }

    # Non-finalized orders can still be cancelled before becoming a sale.
    await db.orders.delete_one({"id": order_id, "store": store})
    return {
        "success": True,
        "archived": False,
        "message": "Pedido cancelado antes da finalização",
    }


async def restore_verified_gym_debit_sale():
    """Restore the R$ 50,10 debit movement proved by the 14:00 screenshot once."""
    if db is None:
        return {"status": "no_db"}

    marker = await db.repair_runs.find_one({"id": RECOVERY_ID})
    if marker and marker.get("status") in {"restored", "already_present"}:
        return {"status": marker.get("status"), "amount": marker.get("amount", 0)}

    target_date = "2026-10-06"
    rows = []
    projection = {
        "_id": 0, "id": 1, "created_at": 1, "total": 1,
        "payment_method": 1, "status": 1,
    }
    for source in ("orders", "order_history"):
        cursor = db[source].find({
            "store": "gym-londres",
            "payment_method": "debit",
            "status": {"$in": ["ready", "delivered"]},
        }, projection)
        async for order in cursor:
            dt = _parse_dt(order.get("created_at"))
            if not dt or dt.strftime("%Y-%m-%d") != target_date:
                continue
            if not (6 <= dt.hour < 14):
                continue
            rows.append((source, order))

    # De-duplicate records that exist in active orders and history.
    by_id = {}
    anonymous = []
    for source, order in rows:
        oid = order.get("id")
        if oid:
            if oid not in by_id or source == "orders":
                by_id[oid] = order
        else:
            anonymous.append(order)

    morning_debit = round(sum(float(o.get("total") or 0) for o in list(by_id.values()) + anonymous), 2)

    # Screenshot at 14:00 proves debit R$ 204,40. Current DB had R$ 154,30,
    # exactly one order / R$ 50,10 less. Never insert if the total is already right.
    if abs(morning_debit - 204.40) < 0.01:
        await db.repair_runs.update_one(
            {"id": RECOVERY_ID},
            {"$set": {
                "id": RECOVERY_ID,
                "status": "already_present",
                "amount": 50.10,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        return {"status": "already_present", "morning_debit": morning_debit}

    if abs(morning_debit - 154.30) >= 0.01:
        # Financial data is safety-critical: refuse to guess if the live total
        # no longer matches the exact screenshot delta.
        return {"status": "skipped_unexpected_total", "morning_debit": morning_debit}

    created_brt = BRT.localize(datetime(2026, 10, 6, 13, 59, 0))
    created_utc = created_brt.astimezone(timezone.utc).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    recovered = {
        "id": RECOVERY_ORDER_ID,
        "store": "gym-londres",
        "customer_name": "Venda recuperada 06/10",
        "items": [{
            "menu_item_id": "recovered-debit-5010",
            "name": "Venda débito recuperada",
            "category": "Outros",
            "price": 50.10,
            "quantity": 1,
        }],
        "total": 50.10,
        "original_total": 50.10,
        "payment_method": "debit",
        "status": "delivered",
        "created_at": created_utc,
        "updated_at": now,
        "delivered_at": created_utc,
        "recovered_sale": True,
        "recovery_source": "screenshot_2026-10-06_14h",
        "time_estimated_from_screenshot": True,
    }

    await db.orders.update_one(
        {"id": RECOVERY_ORDER_ID},
        {"$setOnInsert": recovered},
        upsert=True,
    )
    await db.order_history.update_one(
        {"id": RECOVERY_ORDER_ID},
        {"$setOnInsert": recovered},
        upsert=True,
    )
    await db.repair_runs.update_one(
        {"id": RECOVERY_ID},
        {"$set": {
            "id": RECOVERY_ID,
            "status": "restored",
            "amount": 50.10,
            "before_morning_debit": morning_debit,
            "after_morning_debit": 204.40,
            "restored_at": now,
        }},
        upsert=True,
    )
    return {"status": "restored", "before": morning_debit, "after": 204.40}
