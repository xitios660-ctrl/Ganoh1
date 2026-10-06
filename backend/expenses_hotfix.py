"""Production hotfix for the Gestor expense list.

Keeps the existing expense data intact while making the read path deterministic
and non-cacheable so recent entries cannot appear to disappear behind stale data.
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from server import verify_gestor

router = APIRouter()
db = None


def set_database(database):
    global db
    db = database


def _sort_key(value):
    """Return a comparable UTC timestamp for ISO and legacy date strings."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            dt = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw[:10], fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                return 0.0
    else:
        return 0.0

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).timestamp()


@router.get("/api/expenses")
async def fresh_expenses(
    response: Response,
    store: Optional[str] = None,
    category: Optional[str] = None,
    username: str = Depends(verify_gestor),
):
    """Return the live expense list newest-first with caching disabled."""
    if db is None:
        raise HTTPException(status_code=503, detail="Banco indisponível")

    query = {}
    if store and store != "all":
        query["$or"] = [{"store": store}, {"store": "all"}]
    if category:
        query["category"] = category

    # Read the live collection directly. Python sorting is intentional here: it
    # also handles legacy rows whose created_at type/format differs from newer rows.
    expenses = await db.expenses.find(query, {"_id": 0}).to_list(5000)
    expenses.sort(key=lambda item: _sort_key(item.get("created_at")), reverse=True)

    totals_by_category = {}
    total = 0.0
    for exp in expenses:
        amount = float(exp.get("amount", 0) or 0)
        total += amount
        cat = exp.get("category", "outros") or "outros"
        totals_by_category[cat] = round(totals_by_category.get(cat, 0.0) + amount, 2)

    # Prevent browser/PWA/proxy caches from serving an old list after new gastos
    # are registered on another device or in a previous session.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    latest_created_at = expenses[0].get("created_at") if expenses else None
    return {
        "expenses": expenses,
        "total": round(total, 2),
        "by_category": totals_by_category,
        "count": len(expenses),
        "latest_created_at": latest_created_at,
    }
