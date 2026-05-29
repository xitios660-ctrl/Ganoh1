"""
Live Dashboard Router - Real-time KPIs for in-store cinematic display
"""
from fastapi import APIRouter
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import pytz

router = APIRouter(prefix="/live", tags=["live"])

db = None
BRAZIL_TZ = None


def set_dependencies(database, tz):
    global db, BRAZIL_TZ
    db = database
    BRAZIL_TZ = tz


@router.get("/{store}/snapshot")
async def live_snapshot(store: str):
    """
    Cinematic live dashboard snapshot.
    Returns: today's KPIs + hourly sales + top items + recent activity.
    Lightweight & cached-friendly — designed to be polled every 5-10s on a TV display.
    """
    now_brazil = datetime.now(BRAZIL_TZ)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_brazil.astimezone(pytz.UTC)
    yesterday_utc = (today_brazil - timedelta(days=1)).astimezone(pytz.UTC)

    # Today's orders (ready/delivered count as sales)
    orders = await db.orders.find({
        "store": store,
        "status": {"$in": ["received", "preparing", "ready", "delivered"]},
        "created_at": {"$gte": today_utc.isoformat()}
    }, {"_id": 0}).to_list(2000)

    # Yesterday for comparison
    yesterday_orders = await db.orders.find({
        "store": store,
        "status": {"$in": ["ready", "delivered"]},
        "created_at": {"$gte": yesterday_utc.isoformat(), "$lt": today_utc.isoformat()}
    }, {"_id": 0}).to_list(2000)

    # ── KPIs ────────────────────────────────────────────────
    sales_orders = [o for o in orders if o.get("status") in ("ready", "delivered")
                    and o.get("payment_method") != "prazo"]
    total_today = sum(o.get("total", 0) for o in sales_orders)
    count_today = len(sales_orders)
    avg_ticket = total_today / count_today if count_today else 0

    total_yesterday = sum(o.get("total", 0) for o in yesterday_orders
                         if o.get("payment_method") != "prazo")
    growth_pct = ((total_today - total_yesterday) / total_yesterday * 100) if total_yesterday else 0

    # ── Hourly sales (current shift) ───────────────────────
    hourly = defaultdict(lambda: {"total": 0, "count": 0})
    for o in sales_orders:
        try:
            t = datetime.fromisoformat(o.get("created_at", "").replace("Z", "+00:00"))
            hour = t.astimezone(BRAZIL_TZ).hour
            hourly[hour]["total"] += o.get("total", 0)
            hourly[hour]["count"] += 1
        except Exception:
            continue
    hourly_chart = [
        {"hour": h, "total": round(hourly[h]["total"], 2), "count": hourly[h]["count"]}
        for h in range(6, 23)
    ]

    # ── Top items ──────────────────────────────────────────
    item_counter = defaultdict(lambda: {"name": "", "qty": 0, "revenue": 0})
    for o in sales_orders:
        for item in o.get("items", []):
            key = item.get("name", "?")
            item_counter[key]["name"] = key
            item_counter[key]["qty"] += item.get("quantity", 1)
            item_counter[key]["revenue"] += item.get("price", 0) * item.get("quantity", 1)
    top_items = sorted(item_counter.values(), key=lambda x: x["qty"], reverse=True)[:6]

    # ── By payment method ──────────────────────────────────
    by_payment = defaultdict(float)
    for o in sales_orders:
        by_payment[o.get("payment_method", "cash")] += o.get("total", 0)

    # ── Recent activity feed (last 8) ──────────────────────
    recent = sorted(orders, key=lambda o: o.get("created_at", ""), reverse=True)[:8]
    activity = [
        {
            "id": o.get("id"),
            "customer": o.get("customer_name", "Cliente"),
            "items_count": len(o.get("items", [])),
            "total": o.get("total", 0),
            "status": o.get("status"),
            "payment_method": o.get("payment_method"),
            "created_at": o.get("created_at"),
        }
        for o in recent
    ]

    # ── Active orders (cozinha) ────────────────────────────
    pending = len([o for o in orders if o.get("status") in ("received", "preparing")])
    ready = len([o for o in orders if o.get("status") == "ready"])

    return {
        "store": store,
        "timestamp": now_brazil.isoformat(),
        "kpis": {
            "total_today": round(total_today, 2),
            "orders_today": count_today,
            "avg_ticket": round(avg_ticket, 2),
            "growth_pct": round(growth_pct, 1),
            "total_yesterday": round(total_yesterday, 2),
            "pending_orders": pending,
            "ready_orders": ready,
        },
        "hourly_chart": hourly_chart,
        "top_items": top_items,
        "by_payment": {k: round(v, 2) for k, v in by_payment.items()},
        "activity": activity,
    }
