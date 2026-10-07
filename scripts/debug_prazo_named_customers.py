"""Read-only audit for the named GYM Londres prazo customers.

Prints only financial metadata needed to reconcile debts/payments. No phone data.
"""
import json
import os
import re
from datetime import datetime, timezone
from pymongo import MongoClient
import pytz

BRT = pytz.timezone("America/Sao_Paulo")
TARGETS = ["Segurança noite", "Paulão academia"]


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


def stamp(value):
    dt = parse_dt(value)
    return dt.isoformat() if dt else (str(value) if value else None)


def clean_order(o, source):
    total = round(float(o.get("total") or 0), 2)
    partial = round(float(o.get("partial_paid") or 0), 2)
    return {
        "source": source,
        "id": o.get("id"),
        "created_at_brt": stamp(o.get("created_at")),
        "updated_at_brt": stamp(o.get("updated_at")),
        "total": total,
        "partial_paid": partial,
        "remaining": round(max(0.0, total - partial), 2),
        "prazo_paid": bool(o.get("prazo_paid")),
        "prazo_paid_at_brt": stamp(o.get("prazo_paid_at") or o.get("paid_at")),
        "prazo_paid_amount": round(float(o.get("prazo_paid_amount") or 0), 2),
        "prazo_paid_method": o.get("prazo_paid_method"),
        "prazo_cleared": bool(o.get("prazo_cleared")),
        "restored_prazo_debt": bool(o.get("restored_prazo_debt")),
        "verified_pdf_debt_restored": bool(o.get("verified_pdf_debt_restored")),
        "status": o.get("status"),
    }


def clean_payment(p, source):
    return {
        "source": source,
        "id": p.get("id"),
        "order_id": p.get("order_id"),
        "created_at_brt": stamp(p.get("created_at")),
        "amount": round(float(p.get("amount") or 0), 2),
        "payment_method": p.get("payment_method"),
        "type": p.get("type"),
        "event_type": p.get("event_type"),
        "previous_debt": round(float(p.get("previous_debt") or 0), 2),
        "new_debt": round(float(p.get("new_debt") or 0), 2),
        "applied_to_debt": round(float(p.get("applied_to_debt") or 0), 2),
        "credit_generated": round(float(p.get("credit_generated") or 0), 2),
        "notes": p.get("notes"),
    }


def main():
    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=15000)
    db = client[os.environ["DB_NAME"]]
    client.admin.command("ping")
    result = {}

    for target in TARGETS:
        rx = re.compile(rf"^{re.escape(target)}$", re.I)
        customer = db.prazo_customers.find_one({"name": rx, "store": "gym-londres"}, {"_id": 0})
        orders = []
        for source in ("orders", "order_history"):
            for o in db[source].find({"customer_name": rx, "store": "gym-londres", "payment_method": "prazo"}, {"_id": 0}):
                orders.append(clean_order(o, source))

        partial = [clean_payment(p, "prazo_partial_payments") for p in db.prazo_partial_payments.find({"customer_name": rx, "store": "gym-londres"}, {"_id": 0})]
        full = [clean_payment(p, "prazo_payments") for p in db.prazo_payments.find({"customer_name": rx, "store": "gym-londres"}, {"_id": 0})]
        hist = [clean_payment(p, "prazo_history") for p in db.prazo_history.find({"customer_name": rx}, {"_id": 0})]

        active = [o for o in orders if o["source"] == "orders"]
        active_unpaid = [o for o in active if not o["prazo_paid"] and o["remaining"] > 0]
        current_debt = round(sum(o["remaining"] for o in active_unpaid), 2)

        result[target] = {
            "customer": {
                "id": customer.get("id") if customer else None,
                "name": customer.get("name") if customer else target,
                "store": customer.get("store") if customer else "gym-londres",
                "credit": round(float((customer or {}).get("credit") or 0), 2),
            },
            "current_debt_from_active_orders": current_debt,
            "active_unpaid_count": len(active_unpaid),
            "orders": sorted(orders, key=lambda x: x.get("created_at_brt") or ""),
            "partial_payments": sorted(partial, key=lambda x: x.get("created_at_brt") or ""),
            "full_payments": sorted(full, key=lambda x: x.get("created_at_brt") or ""),
            "prazo_history": sorted(hist, key=lambda x: x.get("created_at_brt") or ""),
        }

    print("PRAZO_NAMED_AUDIT " + json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
    client.close()


if __name__ == "__main__":
    main()
