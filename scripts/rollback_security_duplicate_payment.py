"""One-shot, guarded reversal of the duplicate 16 Oct payment for Segurança noite.

Run only when GANOH_SECURITY_DUPLICATE_ROLLBACK_ONCE=true. All preconditions
are checked inside a Mongo transaction; if any amount, timestamp, record, or
store differs from the audited snapshot, the transaction aborts without changes.
"""
from copy import deepcopy
from datetime import datetime, timezone
import os
import re

from pymongo import MongoClient

ROLLBACK_ID = "rollback-security-night-duplicate-13000-2026-10-16-v1"
CUSTOMER = "Segurança noite"
STORE = "gym-londres"
PAYMENT_ID = "eea3d1c2-ea94-4c67-8759-05b8f7401586"
HISTORY_ID = "dc3d36bc-6a71-48b9-bd75-3c061ae4a572"
VALID_PAYMENT_ID = "33674511-71a6-4322-a090-24ae19f77b6b"
DUPLICATE_CREATED_AT = "2026-10-16T08:01:45.719437-03:00"
LATER_MISTAKEN_FLAGS_AT = "2026-10-16T08:09:32.463761-03:00"
VALID_PAYMENT_AT = "2026-10-13T19:00:16.114652-03:00"

# The five order records paid by the real 13 Oct payment must remain untouched.
VALID_ORDERS = {
    "229dd0bf-4b2e-40f8-9109-696569992d43": 43.50,
    "e8e73688-a1e0-476b-97af-8227fb8e9ebe": 20.00,
    "b5bc13be-e8c2-4ffb-940d-22ff26433bb7": 21.60,
    "71665f2d-47d2-4fde-8afa-ef241dce1158": 37.00,
    "c58450d0-375d-4fc7-9229-05100ba3ddc2": 8.00,
}

# Exactly these six orders made up the R$144.10 debt before the duplicate.
# The first four received R$80.50 of the payment, and R$49.50 was applied
# to the fifth order. The remaining R$5.10 + R$9.00 was then wrongly flagged
# paid without a corresponding recorded payment.
TARGET_ORDERS = {
    "b17be5f0-3ceb-4f55-8cda-beb63b43243b": {
        "total": 28.00, "partial_paid": 28.00, "paid_at": DUPLICATE_CREATED_AT,
        "paid_amount": 28.00,
    },
    "a7504ae4-4407-4034-be96-9390e7936ba9": {
        "total": 15.00, "partial_paid": 15.00, "paid_at": DUPLICATE_CREATED_AT,
        "paid_amount": 15.00,
    },
    "073951df-123a-4846-ac8e-c681b1150687": {
        "total": 16.50, "partial_paid": 16.50, "paid_at": DUPLICATE_CREATED_AT,
        "paid_amount": 16.50,
    },
    "cebab7bb-3ba2-4ac7-82df-c5243d8f035c": {
        "total": 21.00, "partial_paid": 21.00, "paid_at": DUPLICATE_CREATED_AT,
        "paid_amount": 21.00,
    },
    "5ea5b82c-6c8f-4c38-97c9-2fb4f4b5e0c4": {
        "total": 54.60, "partial_paid": 49.50, "paid_at": LATER_MISTAKEN_FLAGS_AT,
        "paid_amount": 0.00,
    },
    "0ef7d132-6137-46f8-a4c5-667c3786e670": {
        "total": 9.00, "partial_paid": 0.00, "paid_at": LATER_MISTAKEN_FLAGS_AT,
        "paid_amount": 0.00,
    },
}

def as_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None

def same_time(actual, expected):
    a, e = as_time(actual), as_time(expected)
    return a is not None and e is not None and a == e

def money(value):
    return round(float(value or 0), 2)

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def main():
    require(os.environ.get("GANOH_SECURITY_DUPLICATE_ROLLBACK_ONCE", "").lower() == "true",
            "Rollback flag is not enabled; refusing to run.")
    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=15000)
    database = client[os.environ["DB_NAME"]]
    client.admin.command("ping")

    marker = database.prazo_payment_reversals.find_one({"id": ROLLBACK_ID}, {"_id": 0})
    if marker and marker.get("status") == "completed":
        print("SECURITY_DUPLICATE_ROLLBACK already_completed debt_restored=144.10", flush=True)
        client.close()
        return

    session = client.start_session()
    try:
        with session:
            with session.start_transaction():
                existing = database.prazo_payment_reversals.find_one({"id": ROLLBACK_ID}, session=session)
                require(not existing, "Rollback marker already exists in an unexpected state; refusing to repeat.")

                name_rx = {"$regex": "^" + re.escape(CUSTOMER) + "$", "$options": "i"}
                payment = database.prazo_partial_payments.find_one({"id": PAYMENT_ID}, session=session)
                require(payment is not None, "Duplicate payment record not found.")
                require(payment.get("customer_name", "").lower() == CUSTOMER.lower(), "Wrong customer on payment.")
                require(payment.get("store") == STORE, "Wrong store on payment.")
                require(payment.get("type") == "partial_payment", "Unexpected payment type.")
                require(money(payment.get("amount")) == 130.00, "Unexpected payment amount.")
                require(money(payment.get("previous_debt")) == 144.10, "Unexpected previous debt.")
                require(money(payment.get("new_debt")) == 14.10, "Unexpected remaining debt.")
                require(same_time(payment.get("created_at"), DUPLICATE_CREATED_AT), "Unexpected duplicate payment timestamp.")

                event = database.prazo_history.find_one({"id": HISTORY_ID}, session=session)
                require(event is not None, "Corresponding debt history event not found.")
                require(event.get("customer_name", "").lower() == CUSTOMER.lower(), "Wrong customer on history event.")
                require(event.get("store") == STORE, "Wrong store on history event.")
                require(event.get("event_type") == "payment_partial", "Unexpected debt history event.")
                require(money(event.get("amount")) == 130.00, "Unexpected history amount.")
                require(money(event.get("previous_debt")) == 144.10 and money(event.get("new_debt")) == 14.10,
                        "Unexpected history balance values.")

                # Verify the genuine 13 Oct R$130.10 payment and its five paid orders.
                valid_payment = database.prazo_payments.find_one({"id": VALID_PAYMENT_ID}, session=session)
                require(valid_payment is not None, "Real 13 Oct payment is missing.")
                require(valid_payment.get("customer_name", "").lower() == CUSTOMER.lower(), "Real payment has wrong customer.")
                require(valid_payment.get("store") == STORE and valid_payment.get("type") == "full_payment",
                        "Real payment has unexpected store/type.")
                require(money(valid_payment.get("amount")) == 130.10, "Real payment amount differs.")
                require(same_time(valid_payment.get("created_at"), VALID_PAYMENT_AT), "Real payment timestamp differs.")

                valid_order_sum = 0.0
                for order_id, expected_total in VALID_ORDERS.items():
                    row = database.order_history.find_one({"id": order_id}, session=session)
                    require(row is not None, "A genuine 13 Oct paid order is missing: " + order_id)
                    require(row.get("customer_name", "").lower() == CUSTOMER.lower() and row.get("store") == STORE,
                            "A genuine paid order has wrong customer/store: " + order_id)
                    require(money(row.get("total")) == expected_total and money(row.get("partial_paid")) == expected_total,
                            "A genuine paid order amount/state differs: " + order_id)
                    require(row.get("prazo_paid") is True and same_time(row.get("prazo_paid_at") or row.get("paid_at"), VALID_PAYMENT_AT),
                            "A genuine 13 Oct order is not in its expected paid state: " + order_id)
                    valid_order_sum += expected_total
                require(money(valid_order_sum) == 130.10, "The genuine payment's order sum does not match.")

                # All six duplicate-affected orders must still match the audited snapshot,
                # and must not already exist in the active collection.
                snapshots = []
                for order_id, expected in TARGET_ORDERS.items():
                    row = database.order_history.find_one({"id": order_id}, {"_id": 0}, session=session)
                    require(row is not None, "An affected historical order is missing: " + order_id)
                    require(row.get("customer_name", "").lower() == CUSTOMER.lower() and row.get("store") == STORE,
                            "An affected order has wrong customer/store: " + order_id)
                    require(row.get("payment_method") == "prazo", "An affected order is not prazo: " + order_id)
                    require(money(row.get("total")) == expected["total"], "Order total changed since audit: " + order_id)
                    require(money(row.get("partial_paid")) == expected["partial_paid"],
                            "Order partial payment changed since audit: " + order_id)
                    require(row.get("prazo_paid") is True and same_time(row.get("prazo_paid_at") or row.get("paid_at"), expected["paid_at"]),
                            "Order paid flag/timestamp changed since audit: " + order_id)
                    require(money(row.get("prazo_paid_amount")) == expected["paid_amount"],
                            "Order recorded paid amount changed since audit: " + order_id)
                    require(database.orders.find_one({"id": order_id}, {"_id": 1}, session=session) is None,
                            "An affected order already exists in active orders: " + order_id)
                    snapshots.append(deepcopy(row))

                # Snapshot the exact records before removal so the operation remains auditable.
                marker_doc = {
                    "id": ROLLBACK_ID,
                    "status": "started",
                    "customer_name": CUSTOMER,
                    "store": STORE,
                    "reason": "Duplicate R$130.00 partial payment recorded on 16/10/2026",
                    "amount_reversed": 130.00,
                    "previous_debt_restored": 144.10,
                    "duplicate_payment": deepcopy(payment),
                    "duplicate_history_event": deepcopy(event),
                    "affected_orders_before": snapshots,
                    "valid_payment_preserved": deepcopy(valid_payment),
                    "valid_payment_order_ids_preserved": list(VALID_ORDERS.keys()),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                database.prazo_payment_reversals.insert_one(marker_doc, session=session)

                now = datetime.now(timezone.utc).isoformat()
                unset_fields = {
                    "prazo_paid_at": "", "paid_at": "", "prazo_paid_amount": "",
                    "prazo_paid_method": "", "prazo_cleared": "",
                }
                restored_sum = 0.0
                for order_id, expected in TARGET_ORDERS.items():
                    update = database.order_history.update_one(
                        {"id": order_id, "store": STORE, "customer_name": name_rx},
                        {
                            "$set": {
                                "partial_paid": 0.0,
                                "prazo_paid": False,
                                "restored_prazo_debt": True,
                                "restored_from_history_at": now,
                                "prazo_payment_rollback_id": ROLLBACK_ID,
                            },
                            "$unset": unset_fields,
                        },
                        session=session,
                    )
                    require(update.matched_count == 1, "Could not restore affected order: " + order_id)
                    active_copy = database.order_history.find_one({"id": order_id}, {"_id": 0}, session=session)
                    require(active_copy is not None, "Restored history copy missing: " + order_id)
                    active_copy["status"] = "delivered"
                    active_copy["restored_prazo_debt"] = True
                    active_copy["restored_from_history_at"] = now
                    active_copy["prazo_payment_rollback_id"] = ROLLBACK_ID
                    database.orders.insert_one(active_copy, session=session)
                    restored_sum += money(expected["total"])

                require(money(restored_sum) == 144.10, "Restored order sum is not R$144.10.")
                deleted_payment = database.prazo_partial_payments.delete_one({"id": PAYMENT_ID}, session=session)
                require(deleted_payment.deleted_count == 1, "Duplicate payment was not removed from payment history.")
                deleted_event = database.prazo_history.delete_one({"id": HISTORY_ID}, session=session)
                require(deleted_event.deleted_count == 1, "Duplicate payment was not removed from customer history.")

                # Verify the visible unpaid balance and prove the genuine payment is still present.
                live_payment = database.prazo_payments.find_one({"id": VALID_PAYMENT_ID}, session=session)
                require(live_payment is not None and money(live_payment.get("amount")) == 130.10,
                        "Real 13 Oct payment changed unexpectedly.")
                live_orders = list(database.orders.find({
                    "customer_name": name_rx, "store": STORE, "payment_method": "prazo",
                    "prazo_paid": {"$ne": True},
                }, {"_id": 0, "total": 1, "partial_paid": 1}, session=session))
                debt_after = round(sum(max(0.0, money(o.get("total")) - money(o.get("partial_paid"))) for o in live_orders), 2)
                require(all(database.orders.find_one({"id": oid, "prazo_paid": {"$ne": True}}, {"_id": 1}, session=session)
                            for oid in TARGET_ORDERS),
                        "One or more restored debts are not visible as unpaid.")
                database.prazo_payment_reversals.update_one(
                    {"id": ROLLBACK_ID},
                    {"$set": {
                        "status": "completed",
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "restored_order_count": len(TARGET_ORDERS),
                        "restored_debt": 144.10,
                        "live_debt_after": debt_after,
                        "duplicate_payment_removed": True,
                        "real_13_oct_payment_preserved": True,
                    }},
                    session=session,
                )

        print("SECURITY_DUPLICATE_ROLLBACK PASS duplicate=removed restored=144.10 "
              "real_13_oct_payment=preserved", flush=True)
    finally:
        session.end_session()
        client.close()

if __name__ == "__main__":
    main()
