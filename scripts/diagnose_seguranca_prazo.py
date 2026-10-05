"""One-shot, read-only diagnosis for the migrated 'Segurança noite' prazo balance.

Prints only the known customer's debt/order bookkeeping, never credentials or connection data.
"""
import os
from pymongo import MongoClient

TARGET = "Segurança noite"
ORDER_IDS = [
    "9cbfedb9-0cc4-4058-84b7-a76777638f94",
    "ff3fe498-837c-43a3-acc3-53503e1ef18c",
    "36de7de8-44e3-425d-b0bf-7e5603bc5067",
    "87fa1a3d-3bdd-4aaf-9c69-c816e1670d75",
    "e67cb908-ba5e-48e1-9295-e562cfb7bb55",
    "9f9206e6-af94-4a0e-82fe-015423f53f9c",
]


def money(v):
    try:
        return round(float(v or 0), 2)
    except Exception:
        return 0.0


def compact_order(doc):
    if not doc:
        return None
    return {
        "id": doc.get("id"),
        "store": doc.get("store"),
        "total": money(doc.get("total")),
        "partial_paid": money(doc.get("partial_paid")),
        "due": round(max(0.0, money(doc.get("total")) - money(doc.get("partial_paid"))), 2),
        "prazo_paid": bool(doc.get("prazo_paid", False)),
        "prazo_cleared": bool(doc.get("prazo_cleared", False)),
        "status": doc.get("status"),
        "source": doc.get("source"),
        "auto_archived": bool(doc.get("auto_archived", False)),
        "restored_prazo_debt": bool(doc.get("restored_prazo_debt", False)),
        "created_at": doc.get("created_at"),
        "prazo_paid_at": doc.get("prazo_paid_at") or doc.get("paid_at"),
    }


def main():
    with MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=10000) as client:
        db = client[os.environ["DB_NAME"]]
        db.command("ping")

        customers = list(db.prazo_customers.find(
            {"name": {"$regex": "seguran", "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1, "store": 1, "credit": 1, "source": 1},
        ))
        print("PRAZO_DIAG customers=", customers, flush=True)

        active = list(db.orders.find({"id": {"$in": ORDER_IDS}}, {"_id": 0}))
        history = list(db.order_history.find({"id": {"$in": ORDER_IDS}}, {"_id": 0}))
        active_map = {d.get("id"): d for d in active}
        hist_map = {d.get("id"): d for d in history}

        print("PRAZO_DIAG known_orders:", flush=True)
        for oid in ORDER_IDS:
            print("PRAZO_DIAG order", oid, "active=", compact_order(active_map.get(oid)), "history=", compact_order(hist_map.get(oid)), flush=True)

        # Current API-equivalent debt by exact customer name (active orders only).
        current = list(db.orders.find({
            "customer_name": {"$regex": f"^{TARGET}$", "$options": "i"},
            "payment_method": "prazo",
            "prazo_paid": {"$ne": True},
        }, {"_id": 0, "id": 1, "total": 1, "partial_paid": 1, "store": 1, "status": 1, "source": 1}))
        current_due = round(sum(max(0.0, money(o.get("total")) - money(o.get("partial_paid"))) for o in current), 2)
        print("PRAZO_DIAG api_equivalent_count=", len(current), "api_equivalent_due=", current_due, flush=True)

        # All current/history records by customer, including paid/cleared ones.
        for cname in ("orders", "order_history"):
            coll = db[cname]
            docs = list(coll.find({"customer_name": {"$regex": "seguran", "$options": "i"}}, {"_id": 0}).sort("created_at", 1))
            print("PRAZO_DIAG", cname, "matches=", len(docs), flush=True)
            for d in docs:
                print("PRAZO_DIAG", cname, compact_order(d), flush=True)

        full = list(db.prazo_payments.find({"customer_name": {"$regex": "seguran", "$options": "i"}}, {"_id": 0, "customer_name": 1, "amount": 1, "payment_method": 1, "created_at": 1, "type": 1}))
        partial = list(db.prazo_partial_payments.find({"customer_name": {"$regex": "seguran", "$options": "i"}}, {"_id": 0, "customer_name": 1, "amount": 1, "payment_method": 1, "created_at": 1, "type": 1, "source": 1}))
        events = list(db.prazo_history.find({"customer_name": {"$regex": "seguran", "$options": "i"}}, {"_id": 0, "event_type": 1, "amount": 1, "previous_debt": 1, "new_debt": 1, "previous_credit": 1, "new_credit": 1, "created_at": 1, "notes": 1}).sort("created_at", 1))
        print("PRAZO_DIAG full_payments=", full, flush=True)
        print("PRAZO_DIAG partial_payments=", partial, flush=True)
        print("PRAZO_DIAG history_events=", events, flush=True)


if __name__ == "__main__":
    main()
