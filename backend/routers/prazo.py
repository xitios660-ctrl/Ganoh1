"""Prazo (Credit/Tab) Routes - Customer debts, payments, and credit management"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import uuid
import re
import logging

router = APIRouter(prefix="/prazo", tags=["Prazo"])
logger = logging.getLogger(__name__)

# Will be set by main app
db = None
PRAZO_PASSWORD = ""  # set via set_dependencies from env; empty = fail closed
send_whatsapp_message = None

def set_dependencies(database, password, whatsapp_func=None):
    global db, PRAZO_PASSWORD, send_whatsapp_message
    db = database
    PRAZO_PASSWORD = password
    send_whatsapp_message = whatsapp_func


def _require_prazo_password(provided: str) -> None:
    expected = (PRAZO_PASSWORD or "").strip()
    if not expected or (provided or "").strip() != expected:
        raise HTTPException(status_code=403, detail="Senha incorreta")

# ==================== MODELS ====================

class PrazoCustomerCreate(BaseModel):
    name: str
    phone: str = ""
    notes: str = ""
    store: str = "runner"
    credit: float = 0

class PrazoPayment(BaseModel):
    password: str
    amount: float = 0
    payment_method: str = "cash"

class PrazoCreditAdd(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)
    notes: str = ""

class PrazoAbaterRequest(BaseModel):
    password: str
    amount: float
    payment_method: str = "cash"

class PrazoDebtAdjust(BaseModel):
    password: str
    amount: float
    notes: str = ""
    payment_method: str = "cash"  # used only for "remove" entries

# ==================== HISTORY HELPER ====================

async def _log_prazo_event(
    *,
    customer_name: str,
    customer_id: str = "",
    store: str = "",
    event_type: str,
    amount: float,
    payment_method: str = "",
    previous_debt: float = 0,
    new_debt: float = 0,
    previous_credit: float = 0,
    new_credit: float = 0,
    credit_generated: float = 0,
    notes: str = "",
):
    """Append an entry to the prazo_history collection (single source of truth)."""
    try:
        await db.prazo_history.insert_one({
            "id": str(uuid.uuid4()),
            "customer_id": customer_id or "",
            "customer_name": customer_name,
            "store": store or "",
            "event_type": event_type,
            "amount": float(amount or 0),
            "payment_method": payment_method or "",
            "previous_debt": float(previous_debt or 0),
            "new_debt": float(new_debt or 0),
            "previous_credit": float(previous_credit or 0),
            "new_credit": float(new_credit or 0),
            "credit_generated": float(credit_generated or 0),
            "notes": notes or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.exception("Failed to log prazo event: %s", e)

async def _get_customer_total_debt(customer_name: str) -> float:
    """Sum unpaid prazo orders for a given customer name (case-insensitive)."""
    orders = await db.orders.find({
        "customer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"},
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }, {"_id": 0}).to_list(2000)
    return sum(o.get("total", 0) - o.get("partial_paid", 0) for o in orders)

# ==================== CUSTOMER ROUTES ====================

@router.get("/customers")
async def get_prazo_customers(store: str = None):
    """Get all registered prazo customers, optionally filtered by store.
    NOTE: This endpoint is used by the manager dashboard (authenticated context).
    For the PUBLIC checkout flow, use /customers/lookup instead.
    """
    query = {}
    if store:
        query["store"] = store
    customers = await db.prazo_customers.find(query, {"_id": 0}).to_list(500)
    return {"customers": customers}

def _mask_phone(phone: str) -> str:
    """Mask phone number - show only last 4 digits."""
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) <= 4:
        return "•" * len(digits)
    return "•" * (len(digits) - 4) + digits[-4:]

@router.get("/customers/lookup")
async def lookup_prazo_customers(q: str = "", store: str = None):
    """Public-facing search for prazo customers used in the checkout flow.
    - Returns customers from the current store first; falls back to ALL stores when
      a search query is provided and the store-filtered set is empty.
    - Accent-insensitive name match: typing "paulao" matches "Paulão".
    - Masks phone numbers (only last 4 digits visible).
    """
    import unicodedata

    def _normalize(s: str) -> str:
        if not s:
            return ""
        nfd = unicodedata.normalize("NFD", str(s))
        no_diacritics = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
        return no_diacritics.casefold()

    q = (q or "").strip()
    q_norm = _normalize(q)

    async def _fetch(store_filter):
        query = {}
        if store_filter:
            query["store"] = store_filter
        docs_ = await db.prazo_customers.find(
            query,
            {"_id": 0, "id": 1, "name": 1, "phone": 1, "store": 1}
        ).sort("name", 1).to_list(500)
        if q_norm:
            docs_ = [d for d in docs_ if q_norm in _normalize(d.get("name", ""))]
        return docs_

    # 1) prefer customers from the current store
    docs = await _fetch(store) if store else await _fetch(None)

    # 2) if user is searching and got no hits, broaden to all stores
    if q_norm and not docs and store:
        docs = await _fetch(None)

    docs = docs[:50]

    return {
        "customers": [
            {
                "id": d.get("id"),
                "name": d.get("name", ""),
                "phone_masked": _mask_phone(d.get("phone", "")),
                "store": d.get("store", "")
            }
            for d in docs
        ]
    }

@router.post("/customers")
async def create_prazo_customer(customer: PrazoCustomerCreate):
    """Register a new prazo customer"""
    existing = await db.prazo_customers.find_one({
        "name": {"$regex": f"^{re.escape(customer.name)}$", "$options": "i"},
        "store": customer.store
    })
    if existing:
        raise HTTPException(status_code=400, detail="Cliente já cadastrado nesta loja")
    
    new_customer = {
        "id": str(uuid.uuid4()),
        "name": customer.name,
        "phone": customer.phone,
        "notes": customer.notes,
        "store": customer.store,
        "credit": customer.credit,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.prazo_customers.insert_one(new_customer)
    return {**new_customer, "_id": None}

@router.delete("/customers/{customer_id}")
async def delete_prazo_customer(customer_id: str):
    """Delete a prazo customer"""
    result = await db.prazo_customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"success": True, "message": "Cliente removido"}

@router.put("/customers/{customer_id}")
async def update_prazo_customer(customer_id: str, data: dict):
    """Update prazo customer information"""
    update_data = {}
    if "name" in data and data["name"]:
        update_data["name"] = data["name"]
    if "phone" in data:
        update_data["phone"] = data["phone"]
    if "notes" in data:
        update_data["notes"] = data["notes"]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.prazo_customers.update_one(
        {"id": customer_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    return {"success": True, "message": "Cliente atualizado"}

# ==================== CREDIT ROUTES ====================

@router.post("/customers/{customer_id}/add-credit")
async def add_prazo_credit(customer_id: str, credit_data: PrazoCreditAdd):
    """Add credit to a prazo customer's account.
    AUTO-APPLY behaviour:
      1. The amount is first used to settle the customer's UNPAID prazo orders
         (FIFO — oldest first). Each order has its `partial_paid` increased;
         when fully covered it is marked `prazo_paid=True`.
      2. Whatever is left after the debt is fully paid goes to the customer's
         `credit` balance.
      3. Result: the customer never has BOTH a debt AND a positive credit
         balance simultaneously.
    """
    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    amount = float(credit_data.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Valor deve ser maior que zero")

    name = customer["name"]
    previous_credit = float(customer.get("credit", 0) or 0)

    # 1) Fetch unpaid prazo orders for this customer (oldest first)
    unpaid_orders = await db.orders.find(
        {
            "customer_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
            "payment_method": "prazo",
            "prazo_paid": {"$ne": True},
        },
        {"_id": 0, "id": 1, "total": 1, "partial_paid": 1, "created_at": 1, "store": 1},
    ).sort("created_at", 1).to_list(1000)

    remaining = amount
    applied_to_debt = 0.0
    orders_paid_off = 0
    payment_records = []

    for order in unpaid_orders:
        if remaining <= 0:
            break
        already_paid = float(order.get("partial_paid", 0) or 0)
        order_total = float(order.get("total", 0) or 0)
        debt = round(order_total - already_paid, 2)
        if debt <= 0:
            continue
        apply = min(remaining, debt)
        apply = round(apply, 2)
        new_partial = round(already_paid + apply, 2)
        is_paid = new_partial >= round(order_total - 0.005, 2)

        update_set = {"partial_paid": new_partial}
        if is_paid:
            update_set["prazo_paid"] = True
            update_set["paid_at"] = datetime.now(timezone.utc).isoformat()
            orders_paid_off += 1

        await db.orders.update_one({"id": order["id"]}, {"$set": update_set})

        # Record the partial payment so existing analytics/history keep working
        payment_records.append({
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "customer_name": name,
            "store": order.get("store", customer.get("store", "")),
            "order_id": order["id"],
            "amount": apply,
            "type": "partial_payment",
            "source": "credit_auto_apply",
            "payment_method": (credit_data.payment_method or "cash").lower(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": credit_data.notes or "Abate automático ao adicionar crédito",
        })

        remaining = round(remaining - apply, 2)
        applied_to_debt = round(applied_to_debt + apply, 2)

    if payment_records:
        await db.prazo_partial_payments.insert_many(payment_records)

    # 2) Whatever was not used to pay debt goes to the customer credit balance
    new_credit = round(previous_credit + remaining, 2)
    await db.prazo_customers.update_one(
        {"id": customer_id},
        {"$set": {"credit": new_credit}},
    )

    # Sobra em dinheiro além da dívida = dinheiro físico que entrou no caixa
    if remaining > 0 and (credit_data.payment_method or "cash").lower() == "cash":
        await db.cash_credit_topups.insert_one({
            "id": str(uuid.uuid4()),
            "store": customer.get("store", ""),
            "customer_id": customer_id,
            "customer_name": name,
            "amount": remaining,
            "payment_method": "cash",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": "Crédito adicionado em dinheiro (valor além da dívida)",
        })

    # 3) Log a single consolidated event
    notes_summary = []
    if applied_to_debt > 0:
        notes_summary.append(
            f"Abatido R$ {applied_to_debt:.2f} de {orders_paid_off} pedido(s) liquidados"
            if orders_paid_off
            else f"Abatido R$ {applied_to_debt:.2f} em pedido(s) pendente(s)"
        )
    if remaining > 0:
        notes_summary.append(f"R$ {remaining:.2f} foi para o saldo de crédito")
    if credit_data.notes:
        notes_summary.append(credit_data.notes)

    await _log_prazo_event(
        customer_id=customer_id,
        customer_name=name,
        store=customer.get("store", ""),
        event_type="credit_added",
        amount=amount,
        previous_credit=previous_credit,
        new_credit=new_credit,
        credit_generated=remaining,
        notes=" | ".join(notes_summary) if notes_summary else None,
    )

    if applied_to_debt > 0 and remaining > 0:
        msg = (
            f"R$ {amount:.2f} adicionados! Abatido R$ {applied_to_debt:.2f} da dívida "
            f"e R$ {remaining:.2f} foi para o saldo (atual: R$ {new_credit:.2f})."
        )
    elif applied_to_debt > 0:
        msg = (
            f"R$ {amount:.2f} adicionados — abateu R$ {applied_to_debt:.2f} da dívida"
            + (f" ({orders_paid_off} pedido(s) quitado(s))" if orders_paid_off else "")
            + f". Saldo de crédito: R$ {new_credit:.2f}"
        )
    else:
        msg = f"Crédito adicionado! Saldo: R$ {new_credit:.2f}"

    return {
        "success": True,
        "message": msg,
        "previous_credit": previous_credit,
        "added": amount,
        "applied_to_debt": applied_to_debt,
        "orders_paid_off": orders_paid_off,
        "remaining_credit_added": remaining,
        "new_credit": new_credit,
    }

@router.post("/customers/{customer_id}/use-credit")
async def use_prazo_credit(customer_id: str, credit_data: PrazoCreditAdd):
    """Use credit from a prazo customer's account"""
    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    current_credit = customer.get("credit", 0)
    if credit_data.amount > current_credit:
        raise HTTPException(status_code=400, detail=f"Crédito insuficiente. Saldo: R$ {current_credit:.2f}")
    
    new_credit = current_credit - credit_data.amount
    
    await db.prazo_customers.update_one(
        {"id": customer_id},
        {"$set": {"credit": new_credit}}
    )
    
    await _log_prazo_event(
        customer_id=customer_id,
        customer_name=customer["name"],
        store=customer.get("store", ""),
        event_type="credit_used",
        amount=credit_data.amount,
        previous_credit=current_credit,
        new_credit=new_credit,
        notes=credit_data.notes,
    )

    return {
        "success": True, 
        "message": f"Crédito utilizado! Novo saldo: R$ {new_credit:.2f}",
        "previous_credit": current_credit,
        "used": credit_data.amount,
        "new_credit": new_credit
    }

# ==================== DEBT ROUTES ====================

@router.get("/debts")
async def get_prazo_debts(store: Optional[str] = None):
    """Get prazo debts summary - optionally filtered by store"""
    query = {
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }
    if store:
        query["store"] = store
    
    prazo_orders = await db.orders.find(query, {"_id": 0}).to_list(1000)
    
    prazo_customers = await db.prazo_customers.find({}, {"_id": 0, "name": 1, "phone": 1}).to_list(1000)
    customer_phones = {c.get("name", "").lower(): c.get("phone", "") for c in prazo_customers}
    
    debts_by_customer = {}
    for order in prazo_orders:
        name = order.get("customer_name", "Desconhecido")
        order_store = order.get("store", "")
        order_total = order.get("total", 0)
        partial_paid = order.get("partial_paid", 0)
        remaining = order_total - partial_paid
        
        if remaining <= 0:
            continue
        
        if name not in debts_by_customer:
            phone = customer_phones.get(name.lower(), "")
            debts_by_customer[name] = {"name": name, "total": 0, "orders": [], "order_count": 0, "store": order_store, "phone": phone}
        debts_by_customer[name]["total"] += remaining
        debts_by_customer[name]["order_count"] += 1
        debts_by_customer[name]["orders"].append({
            "id": order.get("id"),
            "total": order_total,
            "partial_paid": partial_paid,
            "remaining": remaining,
            "date": order.get("created_at"),
            "items": order.get("items", []),
            "store": order_store
        })
    
    debts = sorted(debts_by_customer.values(), key=lambda x: x["total"], reverse=True)
    total_prazo = sum(d["total"] for d in debts)
    
    return {
        "debts": debts,
        "total_prazo": total_prazo,
        "customer_count": len(debts),
        "store_filter": store or "all"
    }

# ==================== PAYMENT ROUTES ====================

@router.post("/pay/{order_id}")
async def pay_prazo_order(order_id: str, payment: PrazoPayment):
    """Mark a prazo order as paid (requires password)"""
    _require_prazo_password(payment.password)
    
    result = await db.orders.update_one(
        {"id": order_id, "payment_method": "prazo"},
        {"$set": {"prazo_paid": True, "prazo_paid_at": datetime.now(timezone.utc).isoformat(), "prazo_paid_amount": payment.amount}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    return {"success": True, "message": "Pagamento registrado"}

@router.post("/pay-all/{customer_name}")
async def pay_all_prazo_customer(customer_name: str, payment: PrazoPayment):
    """Mark all prazo orders for a customer as paid (requires password)"""
    _require_prazo_password(payment.password)
    
    first_order = await db.orders.find_one(
        {"customer_name": customer_name, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"store": 1}
    )
    customer_store = first_order.get("store", "runner") if first_order else "runner"
    
    result = await db.orders.update_many(
        {"customer_name": customer_name, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"$set": {
            "prazo_paid": True, 
            "prazo_paid_at": datetime.now(timezone.utc).isoformat(),
            "prazo_paid_method": payment.payment_method
        }}
    )
    
    payment_record = {
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "type": "full_payment",
        "store": customer_store,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.prazo_payments.insert_one(payment_record)
    
    await _log_prazo_event(
        customer_name=customer_name,
        store=customer_store,
        event_type="payment_full",
        amount=payment.amount,
        payment_method=payment.payment_method,
    )

    return {"success": True, "message": f"Todos os débitos de {customer_name} foram quitados ({payment.payment_method})", "orders_paid": result.modified_count}

@router.post("/abater/{customer_name}")
async def abater_prazo_debt(customer_name: str, abater_data: PrazoAbaterRequest):
    """
    Abater (partial payment) on a prazo customer's debt.
    This reduces the total debt by the specified amount.
    If the customer has credit, it will be reduced by the payment amount.
    """
    _require_prazo_password(abater_data.password)
    
    prazo_orders = await db.orders.find({
        "customer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"},
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }, {"_id": 0}).sort("created_at", 1).to_list(1000)
    
    if not prazo_orders:
        raise HTTPException(status_code=404, detail="Cliente não tem dívidas no prazo")
    
    total_debt = sum(o.get("total", 0) - o.get("partial_paid", 0) for o in prazo_orders)
    
    if abater_data.amount > total_debt:
        raise HTTPException(status_code=400, detail=f"Valor maior que a dívida total (R$ {total_debt:.2f})")
    
    remaining_to_apply = abater_data.amount
    orders_updated = 0
    orders_fully_paid = 0
    customer_store = prazo_orders[0].get("store", "runner") if prazo_orders else "runner"
    
    # FIX: Credit balance is the customer's pre-paid money. It should ONLY be reduced
    # when payment_method == 'saldo' (explicit choice to pay using the customer's credit).
    # For any other payment method (cash/pix/debit/credit-card), the credit balance must NOT
    # be touched - the customer is paying with real money.
    customer = await db.prazo_customers.find_one({
        "name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}
    })
    
    previous_credit = 0
    new_credit = 0
    credit_used = 0
    
    if abater_data.payment_method == "saldo" and customer and customer.get("credit", 0) > 0:
        previous_credit = customer.get("credit", 0)
        credit_used = min(abater_data.amount, previous_credit)
        new_credit = previous_credit - credit_used
        
        if credit_used < abater_data.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Saldo a favor insuficiente. Disponível: R$ {previous_credit:.2f}, solicitado: R$ {abater_data.amount:.2f}"
            )
        
        await db.prazo_customers.update_one(
            {"id": customer["id"]},
            {"$set": {"credit": new_credit}}
        )
    
    for order in prazo_orders:
        if remaining_to_apply <= 0:
            break
        
        order_total = order.get("total", 0)
        current_partial = order.get("partial_paid", 0)
        order_remaining = order_total - current_partial
        
        if order_remaining <= 0:
            continue
        
        amount_to_apply = min(remaining_to_apply, order_remaining)
        new_partial = current_partial + amount_to_apply
        
        if new_partial >= order_total:
            await db.orders.update_one(
                {"id": order["id"]},
                {"$set": {
                    "partial_paid": new_partial,
                    "prazo_paid": True,
                    "prazo_paid_at": datetime.now(timezone.utc).isoformat(),
                    "prazo_paid_method": abater_data.payment_method
                }}
            )
            orders_fully_paid += 1
        else:
            await db.orders.update_one(
                {"id": order["id"]},
                {"$set": {"partial_paid": new_partial}}
            )
        
        orders_updated += 1
        remaining_to_apply -= amount_to_apply
    
    payment_record = {
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "amount": abater_data.amount,
        "payment_method": abater_data.payment_method,
        "type": "partial_payment",
        "store": customer_store,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.prazo_partial_payments.insert_one(payment_record)
    
    new_total_debt = total_debt - abater_data.amount
    
    await _log_prazo_event(
        customer_name=customer_name,
        store=customer_store,
        event_type="payment_partial",
        amount=abater_data.amount,
        payment_method=abater_data.payment_method,
        previous_debt=total_debt,
        new_debt=new_total_debt,
        previous_credit=previous_credit,
        new_credit=new_credit,
    )
    
    response = {
        "success": True,
        "message": f"Abatido R$ {abater_data.amount:.2f} da dívida de {customer_name}",
        "previous_debt": total_debt,
        "amount_paid": abater_data.amount,
        "new_debt": new_total_debt,
        "payment_method": abater_data.payment_method,
        "orders_updated": orders_updated,
        "orders_fully_paid": orders_fully_paid
    }
    
    # Add credit info if customer had credit
    if credit_used > 0:
        response["credit_used"] = credit_used
        response["previous_credit"] = previous_credit
        response["new_credit"] = new_credit
        response["message"] = f"Abatido R$ {abater_data.amount:.2f} da dívida de {customer_name} usando Saldo a Favor. Saldo restante: R$ {new_credit:.2f}"
    
    return response

@router.delete("/debt/{customer_name}")
async def delete_prazo_debt(customer_name: str, password: str = None):
    """Delete/clear all prazo debts for a customer (marks as paid without recording payment)"""
    _require_prazo_password(password)
    
    result = await db.orders.update_many(
        {"customer_name": customer_name, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"$set": {"prazo_paid": True, "prazo_paid_at": datetime.now(timezone.utc).isoformat(), "prazo_cleared": True}}
    )
    
    return {
        "success": True,
        "message": f"Dívida de {customer_name} zerada",
        "orders_cleared": result.modified_count
    }

@router.delete("/debt-order/{order_id}")
async def delete_single_prazo_debt(order_id: str, password: str = None):
    """Delete/clear a single prazo debt order"""
    _require_prazo_password(password)
    
    result = await db.orders.update_one(
        {"id": order_id, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"$set": {"prazo_paid": True, "prazo_paid_at": datetime.now(timezone.utc).isoformat(), "prazo_cleared": True}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado ou já pago")
    
    return {"success": True, "message": "Dívida apagada"}

# ==================== HISTORY ROUTES ====================

@router.get("/payments-history")
async def get_prazo_payments_history(store: str = None, limit: int = 100):
    """Get history of prazo payments (full and partial)"""
    query = {}
    if store:
        query["store"] = store
    
    full_payments = await db.prazo_payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    partial_payments = await db.prazo_partial_payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    
    all_payments = full_payments + partial_payments
    all_payments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    totals = {"cash": 0, "pix": 0, "debit": 0, "credit": 0}
    for p in all_payments:
        method = p.get("payment_method", "cash")
        if method in totals:
            totals[method] += p.get("amount", 0)
    
    return {
        "payments": all_payments[:limit],
        "total_count": len(all_payments),
        "totals_by_method": totals,
        "grand_total": sum(totals.values())
    }

# ==================== MANUAL ADJUSTMENTS (ADD / REMOVE) ====================

@router.post("/customers/{customer_id}/debt/add")
async def add_prazo_debt(customer_id: str, data: PrazoDebtAdjust):
    """
    Manually add a monetary value to a customer's prazo debt.
    Creates a synthetic prazo order so the aggregated /debts endpoint sees it,
    and logs the event in prazo_history.
    Requires PRAZO_PASSWORD.
    """
    _require_prazo_password(data.password)
    if data.amount is None or data.amount <= 0:
        raise HTTPException(status_code=400, detail="Valor inválido")

    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    customer_name = customer["name"]
    store = customer.get("store", "runner")
    previous_debt = await _get_customer_total_debt(customer_name)

    # Create a synthetic prazo order representing this manual debt
    synthetic_order = {
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "store": store,
        "items": [{
            "name": data.notes or "Ajuste manual",
            "quantity": 1,
            "price": float(data.amount),
            "manual_debt": True,
        }],
        "total": float(data.amount),
        "partial_paid": 0,
        "payment_method": "prazo",
        "prazo_paid": False,
        "manual_debt": True,
        "notes": data.notes or "",
        "status": "delivered",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.orders.insert_one(synthetic_order)

    new_debt = previous_debt + float(data.amount)
    await _log_prazo_event(
        customer_id=customer_id,
        customer_name=customer_name,
        store=store,
        event_type="debt_added",
        amount=float(data.amount),
        previous_debt=previous_debt,
        new_debt=new_debt,
        notes=data.notes,
    )

    return {
        "success": True,
        "message": f"R$ {data.amount:.2f} adicionado à dívida de {customer_name}",
        "previous_debt": previous_debt,
        "added": float(data.amount),
        "new_debt": new_debt,
    }


@router.post("/customers/{customer_id}/debt/remove")
async def remove_prazo_debt(customer_id: str, data: PrazoDebtAdjust):
    """
    Remove (subtract) a monetary value from a customer's prazo debt.
    If the value exceeds current debt, the excess is converted into customer credit.
    Records the event in prazo_history.
    Requires PRAZO_PASSWORD.
    """
    _require_prazo_password(data.password)
    if data.amount is None or data.amount <= 0:
        raise HTTPException(status_code=400, detail="Valor inválido")

    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    customer_name = customer["name"]
    store = customer.get("store", "runner")
    previous_credit = customer.get("credit", 0) or 0

    # Fetch unpaid prazo orders (oldest first) to apply payment
    prazo_orders = await db.orders.find({
        "customer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"},
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True},
    }, {"_id": 0}).sort("created_at", 1).to_list(2000)

    total_debt = sum(o.get("total", 0) - o.get("partial_paid", 0) for o in prazo_orders)
    amount = float(data.amount)
    remaining_to_apply = min(amount, total_debt)
    excess = max(0.0, amount - total_debt)

    orders_updated = 0
    orders_fully_paid = 0
    to_apply = remaining_to_apply
    for order in prazo_orders:
        if to_apply <= 0:
            break
        order_total = order.get("total", 0)
        current_partial = order.get("partial_paid", 0)
        order_remaining = order_total - current_partial
        if order_remaining <= 0:
            continue
        apply_now = min(to_apply, order_remaining)
        new_partial = current_partial + apply_now
        update = {"partial_paid": new_partial}
        if new_partial >= order_total - 1e-9:
            update.update({
                "prazo_paid": True,
                "prazo_paid_at": datetime.now(timezone.utc).isoformat(),
                "prazo_paid_method": data.payment_method,
            })
            orders_fully_paid += 1
        await db.orders.update_one({"id": order["id"]}, {"$set": update})
        orders_updated += 1
        to_apply -= apply_now

    # Record payment portion (if any) into partial_payments collection (keeps existing analytics working)
    if remaining_to_apply > 0:
        await db.prazo_partial_payments.insert_one({
            "id": str(uuid.uuid4()),
            "customer_name": customer_name,
            "amount": remaining_to_apply,
            "payment_method": data.payment_method,
            "type": "partial_payment",
            "store": store,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    # Convert excess to credit
    new_credit = previous_credit
    if excess > 0:
        new_credit = previous_credit + excess
        await db.prazo_customers.update_one(
            {"id": customer_id}, {"$set": {"credit": new_credit}}
        )

    new_debt = max(0.0, total_debt - remaining_to_apply)

    # Log event(s)
    await _log_prazo_event(
        customer_id=customer_id,
        customer_name=customer_name,
        store=store,
        event_type="debt_removed",
        amount=amount,
        payment_method=data.payment_method,
        previous_debt=total_debt,
        new_debt=new_debt,
        previous_credit=previous_credit,
        new_credit=new_credit,
        credit_generated=excess,
        notes=data.notes,
    )

    message = f"R$ {remaining_to_apply:.2f} removidos da dívida"
    if excess > 0:
        message += f". Excedente de R$ {excess:.2f} convertido em crédito"

    return {
        "success": True,
        "message": message,
        "previous_debt": total_debt,
        "amount_requested": amount,
        "amount_applied_to_debt": remaining_to_apply,
        "excess_to_credit": excess,
        "new_debt": new_debt,
        "previous_credit": previous_credit,
        "new_credit": new_credit,
        "orders_updated": orders_updated,
        "orders_fully_paid": orders_fully_paid,
    }


@router.get("/customers/{customer_id}/history")
async def get_customer_prazo_history(customer_id: str, limit: int = 200):
    """Return the full transaction history for a customer (newest first)."""
    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    customer_name = customer["name"]
    events = await db.prazo_history.find(
        {
            "$or": [
                {"customer_id": customer_id},
                {"customer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}},
            ]
        },
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)

    # Aggregate snapshot
    current_debt = await _get_customer_total_debt(customer_name)
    return {
        "customer": {
            "id": customer_id,
            "name": customer_name,
            "phone": customer.get("phone", ""),
            "credit": customer.get("credit", 0),
            "store": customer.get("store", ""),
            "current_debt": current_debt,
        },
        "events": events,
        "total_count": len(events),
    }


@router.get("/history")
async def get_global_prazo_history(store: str = None, limit: int = 300):
    """Return the global prazo transaction history (newest first), optionally by store."""
    query = {}
    if store:
        query["store"] = store
    events = await db.prazo_history.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"events": events, "total_count": len(events)}
