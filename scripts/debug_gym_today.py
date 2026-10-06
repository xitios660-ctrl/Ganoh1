"""Read-only diagnostic for today's GYM Londres sales.

Prints only financial/order metadata, never customer names or item names.
"""
import json
import os
from datetime import datetime, timezone

import pytz
from pymongo import MongoClient

BRT = pytz.timezone("America/Sao_Paulo")


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


def main():
    client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=15000)
    db = client[os.environ["DB_NAME"]]
    client.admin.command("ping")
    today = datetime.now(BRT).strftime("%Y-%m-%d")
    rows = []
    projection = {
        "_id": 0, "id": 1, "store": 1, "created_at": 1, "updated_at": 1,
        "delivered_at": 1, "total": 1, "payment_method": 1, "status": 1,
        "manual_sale": 1, "auto_archived": 1,
    }
    for source in ("orders", "order_history"):
        for order in db[source].find({"store": "gym-londres"}, projection):
            dt = parse_dt(order.get("created_at"))
            if not dt or dt.strftime("%Y-%m-%d") != today:
                continue
            rows.append({
                "source": source,
                "id_suffix": str(order.get("id") or "")[-8:],
                "time_brt": dt.strftime("%H:%M:%S"),
                "total": round(float(order.get("total") or 0), 2),
                "payment_method": order.get("payment_method"),
                "status": order.get("status"),
                "manual_sale": bool(order.get("manual_sale")),
                "auto_archived": bool(order.get("auto_archived")),
            })
    rows.sort(key=lambda r: (r["time_brt"], r["source"], r["id_suffix"]))
    print("GYM_TODAY_DEBUG " + json.dumps(rows, ensure_ascii=False, separators=(",", ":")), flush=True)
    client.close()


if __name__ == "__main__":
    main()
