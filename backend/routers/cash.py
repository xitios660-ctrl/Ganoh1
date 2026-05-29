"""Cash Drawer (Caixa) Routes"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import logging
import pytz

router = APIRouter(prefix="/cash", tags=["Cash"])
logger = logging.getLogger(__name__)

# Will be set by main app
db = None
BRAZIL_TZ = pytz.timezone("America/Sao_Paulo")

def set_dependencies(database, brazil_tz=None):
    global db, BRAZIL_TZ
    db = database
    if brazil_tz:
        BRAZIL_TZ = brazil_tz

# ==================== MODELS ====================

class CashBalanceAdjust(BaseModel):
    balance: float
    notes: Optional[str] = None

class CashWithdrawal(BaseModel):
    amount: float
    category: str  # "vt" (vale transporte) or "outros"
    description: Optional[str] = None

class PixAdjustment(BaseModel):
    amount: float
    description: str = ""
    store: str

# ==================== CASH TODAY ROUTES ====================

@router.get("/{store}/today")
async def get_today_cash(store: str):
    """Get today's cash summary"""
    now_brazil = datetime.now(BRAZIL_TZ)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_brazil.astimezone(pytz.UTC)
    
    orders = await db.orders.find({
        "store": store,
        "status": {"$in": ["ready", "delivered"]},
        "created_at": {"$gte": today_utc.isoformat()}
    }, {"_id": 0}).to_list(1000)
    
    # Get manual PIX adjustments for today
    pix_adjustments = await db.pix_adjustments.find({
        "store": store,
        "removed": {"$ne": True},
        "created_at": {"$gte": today_utc.isoformat()}
    }, {"_id": 0}).to_list(1000)
    pix_manual_total = sum(a.get("amount", 0) for a in pix_adjustments)
    
    # Separate PIX adjustments by shift
    pix_manual_morning = 0
    pix_manual_afternoon = 0
    for adj in pix_adjustments:
        try:
            adj_time = datetime.fromisoformat(adj.get("created_at", "").replace("Z", "+00:00"))
            adj_time_brazil = adj_time.astimezone(BRAZIL_TZ)
            adj_hour = adj_time_brazil.hour
            if 6 <= adj_hour < 14:
                pix_manual_morning += adj.get("amount", 0)
            else:
                pix_manual_afternoon += adj.get("amount", 0)
        except Exception:
            pix_manual_afternoon += adj.get("amount", 0)
    
    by_payment_value = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "prazo": 0, "voucher": 0}
    total = 0
    
    shift_morning = {"total": 0, "count": 0, "by_payment": {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}}
    shift_afternoon = {"total": 0, "count": 0, "by_payment": {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}}
    
    for order in orders:
        payment = order.get("payment_method", "cash")
        amount = order.get("total", 0)
        
        # Prazo não soma no total de vendas
        if payment != "prazo":
            by_payment_value[payment] = by_payment_value.get(payment, 0) + amount
            total += amount
        
        created_at = order.get("created_at", "")
        try:
            if isinstance(created_at, str):
                order_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                order_time = created_at
            
            order_time_brazil = order_time.astimezone(BRAZIL_TZ)
            brazil_hour = order_time_brazil.hour
            
            if payment != "prazo":
                if 6 <= brazil_hour < 14:
                    shift_morning["total"] += amount
                    shift_morning["count"] += 1
                    shift_morning["by_payment"][payment] += amount
                else:
                    shift_afternoon["total"] += amount
                    shift_afternoon["count"] += 1
                    shift_afternoon["by_payment"][payment] += amount
        except Exception:
            if payment != "prazo":
                shift_afternoon["total"] += amount
                shift_afternoon["count"] += 1
                shift_afternoon["by_payment"][payment] += amount
    
    # Add manual PIX adjustments
    by_payment_value["pix"] += pix_manual_total
    total += pix_manual_total
    
    shift_morning["by_payment"]["pix"] += pix_manual_morning
    shift_morning["total"] += pix_manual_morning
    shift_afternoon["by_payment"]["pix"] += pix_manual_afternoon
    shift_afternoon["total"] += pix_manual_afternoon
    
    return {
        "date": today_brazil.strftime("%Y-%m-%d"),
        "total": total,
        "by_payment_method": by_payment_value,
        "order_count": len(orders),
        "pix_manual_adjustments": round(pix_manual_total, 2),
        "pix_manual_morning": round(pix_manual_morning, 2),
        "pix_manual_afternoon": round(pix_manual_afternoon, 2),
        "shifts": {
            "morning": {"label": "06:00 - 14:00", **shift_morning},
            "afternoon": {"label": "14:00 - 22:00", **shift_afternoon}
        }
    }

# ==================== CASH DRAWER ROUTES ====================

@router.get("/{store}/drawer")
async def get_cash_drawer(store: str):
    """Get current cash drawer status"""
    now_brazil = datetime.now(BRAZIL_TZ)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_brazil.astimezone(pytz.UTC)
    
    drawer_config = await db.cash_drawer_config.find_one({"store": store}, {"_id": 0})
    initial_balance = drawer_config.get("balance", 0) if drawer_config else 0
    last_reset_at = drawer_config.get("last_reset_at") if drawer_config else None
    
    cash_query = {
        "store": store,
        "status": {"$in": ["ready", "delivered"]},
        "payment_method": "cash"
    }
    if last_reset_at:
        cash_query["created_at"] = {"$gte": last_reset_at}
    
    cash_orders = await db.orders.find(cash_query, {"_id": 0, "total": 1, "created_at": 1}).to_list(100000)
    total_cash_sales = sum(o.get("total", 0) for o in cash_orders)
    
    # Get prazo payments made in CASH
    prazo_cash_query = {
        "store": store,
        "payment_method": "cash"
    }
    if last_reset_at:
        prazo_cash_query["created_at"] = {"$gte": last_reset_at}
    
    prazo_full_payments = await db.prazo_payments.find(prazo_cash_query, {"_id": 0, "amount": 1, "created_at": 1}).to_list(10000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_cash_query, {"_id": 0, "amount": 1, "created_at": 1}).to_list(10000)
    total_prazo_cash = sum(p.get("amount", 0) for p in prazo_full_payments) + sum(p.get("amount", 0) for p in prazo_partial_payments)
    
    withdrawal_query = {"store": store}
    if last_reset_at:
        withdrawal_query["created_at"] = {"$gte": last_reset_at}
    
    all_withdrawals = await db.cash_withdrawals.find(withdrawal_query, {"_id": 0}).to_list(10000)
    total_withdrawn = sum(w.get("amount", 0) for w in all_withdrawals)
    
    # Today's data
    today_cash_orders = [o for o in cash_orders if o.get("created_at", "") >= today_utc.isoformat()]
    today_cash_in = sum(o.get("total", 0) for o in today_cash_orders)
    
    today_prazo_full = [p for p in prazo_full_payments if p.get("created_at", "") >= today_utc.isoformat()]
    today_prazo_partial = [p for p in prazo_partial_payments if p.get("created_at", "") >= today_utc.isoformat()]
    today_prazo_cash = sum(p.get("amount", 0) for p in today_prazo_full) + sum(p.get("amount", 0) for p in today_prazo_partial)
    
    today_withdrawals = [w for w in all_withdrawals if w.get("created_at", "") >= today_utc.isoformat()]
    today_withdrawn = sum(w.get("amount", 0) for w in today_withdrawals)
    
    current_balance = initial_balance + total_cash_sales + total_prazo_cash - total_withdrawn
    
    return {
        "store": store,
        "date": now_brazil.strftime("%d/%m/%Y"),
        "initial_balance": round(initial_balance, 2),
        "total_cash_sales": round(total_cash_sales, 2),
        "total_prazo_cash": round(total_prazo_cash, 2),
        "total_withdrawals": round(total_withdrawn, 2),
        "current_balance": round(current_balance, 2),
        "today_cash_in": round(today_cash_in, 2),
        "today_prazo_cash": round(today_prazo_cash, 2),
        "today_withdrawals": round(today_withdrawn, 2),
        "withdrawal_history": today_withdrawals,
        "last_reset_at": last_reset_at
    }

@router.get("/{store}/drawer-debug")
async def get_cash_drawer_debug(store: str):
    """Debug endpoint - shows all cash orders being counted"""
    
    drawer_config = await db.cash_drawer_config.find_one({"store": store}, {"_id": 0})
    initial_balance = drawer_config.get("balance", 0) if drawer_config else 0
    last_reset_at = drawer_config.get("last_reset_at") if drawer_config else None
    
    cash_query = {
        "store": store,
        "status": {"$in": ["ready", "delivered"]},
        "payment_method": "cash"
    }
    if last_reset_at:
        cash_query["created_at"] = {"$gte": last_reset_at}
    
    cash_orders = await db.orders.find(cash_query, {"_id": 0, "customer_name": 1, "total": 1, "created_at": 1, "status": 1}).to_list(1000)
    total_cash_sales = sum(o.get("total", 0) for o in cash_orders)
    
    prazo_cash_query = {"store": store, "payment_method": "cash"}
    if last_reset_at:
        prazo_cash_query["created_at"] = {"$gte": last_reset_at}
    
    prazo_full_payments = await db.prazo_payments.find(prazo_cash_query, {"_id": 0}).to_list(1000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_cash_query, {"_id": 0}).to_list(1000)
    total_prazo_cash = sum(p.get("amount", 0) for p in prazo_full_payments) + sum(p.get("amount", 0) for p in prazo_partial_payments)
    
    withdrawal_query = {"store": store}
    if last_reset_at:
        withdrawal_query["created_at"] = {"$gte": last_reset_at}
    all_withdrawals = await db.cash_withdrawals.find(withdrawal_query, {"_id": 0}).to_list(1000)
    total_withdrawn = sum(w.get("amount", 0) for w in all_withdrawals)
    
    current_balance = initial_balance + total_cash_sales + total_prazo_cash - total_withdrawn
    
    return {
        "store": store,
        "drawer_config": drawer_config,
        "last_reset_at": last_reset_at,
        "initial_balance": initial_balance,
        "cash_orders": cash_orders,
        "cash_orders_count": len(cash_orders),
        "total_cash_sales": round(total_cash_sales, 2),
        "prazo_cash_payments": prazo_full_payments + prazo_partial_payments,
        "prazo_cash_count": len(prazo_full_payments) + len(prazo_partial_payments),
        "total_prazo_cash": round(total_prazo_cash, 2),
        "withdrawals": all_withdrawals,
        "total_withdrawn": round(total_withdrawn, 2),
        "current_balance": round(current_balance, 2),
        "formula": f"{initial_balance} + {total_cash_sales} (vendas) + {total_prazo_cash} (prazo em dinheiro) - {total_withdrawn} = {current_balance}"
    }

@router.post("/{store}/set-balance")
async def set_cash_balance(store: str, data: CashBalanceAdjust):
    """Set/adjust the initial cash drawer balance"""
    now_brazil = datetime.now(BRAZIL_TZ)
    
    existing = await db.cash_drawer_config.find_one({"store": store})
    
    if existing:
        await db.cash_drawer_config.update_one(
            {"store": store},
            {"$set": {
                "balance": data.balance,
                "notes": data.notes or "Ajuste de saldo",
                "updated_at": now_brazil.isoformat()
            }}
        )
    else:
        await db.cash_drawer_config.insert_one({
            "store": store,
            "balance": data.balance,
            "notes": data.notes or "Saldo inicial",
            "created_at": now_brazil.isoformat(),
            "updated_at": now_brazil.isoformat()
        })
    
    return await get_cash_drawer(store)

@router.post("/{store}/reset")
async def reset_cash_drawer(store: str):
    """Reset the cash drawer"""
    now_brazil = datetime.now(BRAZIL_TZ)
    
    await db.cash_drawer_config.update_one(
        {"store": store},
        {"$set": {
            "balance": 0,
            "last_reset_at": now_brazil.isoformat(),
            "notes": f"Caixa zerado em {now_brazil.strftime('%d/%m/%Y %H:%M')}",
            "updated_at": now_brazil.isoformat()
        }},
        upsert=True
    )
    
    return await get_cash_drawer(store)

@router.post("/{store}/withdraw")
async def withdraw_cash(store: str, withdrawal: CashWithdrawal):
    """Withdraw cash from the drawer"""
    now_brazil = datetime.now(BRAZIL_TZ)
    
    current_drawer = await get_cash_drawer(store)
    if withdrawal.amount > current_drawer["current_balance"]:
        raise HTTPException(status_code=400, detail="Saldo insuficiente no caixa")
    
    withdrawal_record = {
        "id": str(uuid.uuid4()),
        "store": store,
        "amount": withdrawal.amount,
        "category": withdrawal.category,
        "description": withdrawal.description or ("Vale Transporte" if withdrawal.category == "vt" else "Retirada de caixa"),
        "created_at": now_brazil.isoformat()
    }
    
    await db.cash_withdrawals.insert_one({**withdrawal_record})
    
    if withdrawal.category == "vt":
        expense = {
            "id": str(uuid.uuid4()),
            "description": "Vale Transporte (VT)",
            "amount": withdrawal.amount,
            "category": "vt",
            "store": store,
            "notes": f"Retirado do caixa em {now_brazil.strftime('%d/%m/%Y %H:%M')}",
            "created_at": now_brazil.isoformat(),
            "image_url": ""
        }
        await db.expenses.insert_one({**expense})
    
    updated_drawer = await get_cash_drawer(store)
    
    return {
        "success": True,
        "withdrawal": withdrawal_record,
        "expense_created": withdrawal.category == "vt",
        "current_balance": updated_drawer["current_balance"]
    }

# ==================== PIX ADJUSTMENTS ====================

@router.get("/pix-adjustments/{store}")
async def get_pix_adjustments(store: str):
    """Get all manual PIX adjustments for a store (today)"""
    now_brazil = datetime.now(BRAZIL_TZ)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_brazil.astimezone(pytz.UTC)
    
    adjustments = await db.pix_adjustments.find({
        "store": store,
        "removed": {"$ne": True},
        "created_at": {"$gte": today_utc.isoformat()}
    }, {"_id": 0}).to_list(1000)
    
    total_added = sum(a.get("amount", 0) for a in adjustments)
    
    return {
        "store": store,
        "adjustments": adjustments,
        "total": round(total_added, 2),
        "count": len(adjustments)
    }

@router.post("/pix-adjustments")
async def add_pix_adjustment(adjustment: PixAdjustment):
    """Add a manual PIX adjustment"""
    now_brazil = datetime.now(BRAZIL_TZ)
    
    new_adjustment = {
        "id": str(uuid.uuid4()),
        "store": adjustment.store,
        "amount": adjustment.amount,
        "description": adjustment.description or "Ajuste manual PIX",
        "type": "add",
        "created_at": now_brazil.isoformat()
    }
    
    await db.pix_adjustments.insert_one({**new_adjustment})
    
    return {
        "success": True,
        "adjustment": {k: v for k, v in new_adjustment.items() if k != "_id"}
    }

@router.delete("/pix-adjustments/{adjustment_id}")
async def remove_pix_adjustment(adjustment_id: str):
    """Remove/reverse a PIX adjustment"""
    now_brazil = datetime.now(BRAZIL_TZ)
    
    result = await db.pix_adjustments.update_one(
        {"id": adjustment_id},
        {"$set": {
            "removed": True,
            "removed_at": now_brazil.isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ajuste não encontrado")
    
    return {"success": True, "message": "Ajuste removido"}
