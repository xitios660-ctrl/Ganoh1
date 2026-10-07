"""Ensure the verified Café com Leite price stays at R$ 8,00.

This is intentionally small and idempotent. Public menu rendering prefers DB
overrides over the legacy hard-coded MENU_DATA fallback, so keeping one canonical
override prevents the price from drifting after restarts/deploys.
"""
from datetime import datetime, timezone
import re

db = None
TARGET_ID = "50"
TARGET_NAME = "Café com Leite"
TARGET_PRICE = 8.00


def set_database(database):
    global db
    db = database


async def ensure_cafe_com_leite_price():
    if db is None:
        return {"status": "no_db"}

    now = datetime.now(timezone.utc).isoformat()
    query = {
        "$or": [
            {"id": TARGET_ID},
            {"name": {"$regex": f"^{re.escape(TARGET_NAME)}$", "$options": "i"}},
        ]
    }

    # Bring every existing override for this product to the same verified price.
    result = await db.menu.update_many(
        query,
        {"$set": {"price": TARGET_PRICE, "updated_at": now}},
    )

    canonical = await db.menu.find_one({"id": TARGET_ID, "store": "all"})
    if not canonical:
        await db.menu.insert_one({
            "id": TARGET_ID,
            "name": TARGET_NAME,
            "description": "Café coado com leite vaporizado",
            "price": TARGET_PRICE,
            "category": "Bebidas Quentes",
            "store": "all",
            "prep_time": 15,
            "available": True,
            "created_at": now,
            "updated_at": now,
            "price_verified": True,
        })

    return {
        "status": "ok",
        "matched": result.matched_count,
        "modified": result.modified_count,
        "price": TARGET_PRICE,
    }
