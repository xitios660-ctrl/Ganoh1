#!/usr/bin/env python3
"""Safely mirror operational GANOH data from the legacy Emergent API.

Design goals:
- Source is read-only.
- Destination writes are upserts only; nothing is deleted.
- Dry-run is the default.
- Every fetched endpoint gets a latest raw snapshot for audit/recovery.
- Reconstructed prazo orders are explicitly marked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from pymongo import MongoClient, UpdateOne
from requests.auth import HTTPBasicAuth

DEFAULT_SOURCE = "https://charts-3.emergent.host"
STORES = ("runner", "gym-londres")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class FetchResult:
    key: str
    path: str
    payload: Dict[str, Any]
    protected: bool = False


class SourceClient:
    def __init__(self, base_url: str, username: Optional[str], password: Optional[str]):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.auth = HTTPBasicAuth(username, password) if username and password else None

    def get(self, key: str, path: str, protected: bool = False) -> FetchResult:
        auth = self.auth if protected else None
        if protected and auth is None:
            raise RuntimeError(f"protected endpoint skipped because source gestor credentials are missing: {path}")
        url = f"{self.base_url}{path}"
        response = self.session.get(url, auth=auth, timeout=(10, 45))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"unexpected JSON payload from {path}: expected object")
        return FetchResult(key=key, path=path, payload=payload, protected=protected)


def payload_hash(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def strip_computed_stock_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(item)
    doc.pop("low_stock", None)
    doc.pop("type", None)
    return doc


def bulk_upsert(collection, docs: Iterable[Dict[str, Any]], key_fields: Tuple[str, ...], dry_run: bool) -> int:
    docs = [dict(d) for d in docs if isinstance(d, dict)]
    valid: List[Dict[str, Any]] = []
    for doc in docs:
        if all(doc.get(k) not in (None, "") for k in key_fields):
            valid.append(doc)
    if dry_run or not valid:
        return len(valid)

    synced_at = utc_now()
    ops = []
    for doc in valid:
        query = {k: doc[k] for k in key_fields}
        doc["_source_sync"] = {
            "source": "charts-3.emergent.host",
            "synced_at": synced_at,
        }
        ops.append(UpdateOne(query, {"$set": doc}, upsert=True))
    if ops:
        collection.bulk_write(ops, ordered=False)
    return len(ops)


def sync_live_orders(db, payloads: Dict[str, FetchResult], dry_run: bool) -> int:
    total = 0
    for store in STORES:
        result = payloads.get(f"orders:{store}")
        if not result:
            continue
        orders = result.payload.get("orders") or []
        total += bulk_upsert(db.orders, orders, ("id",), dry_run)
    return total


def sync_debts(db, payloads: Dict[str, FetchResult], dry_run: bool) -> int:
    """Rebuild enough of unpaid prazo orders to preserve current debt continuity.

    The source debts endpoint exposes unpaid order IDs and remaining values,
    but not every historical order field. Existing destination orders are only
    patched with authoritative debt fields. Missing orders are inserted as
    explicitly reconstructed records.
    """
    result = payloads.get("prazo:debts")
    if not result:
        return 0

    writes = 0
    now = utc_now()
    for customer in result.payload.get("debts") or []:
        if not isinstance(customer, dict):
            continue
        customer_name = customer.get("name") or "Desconhecido"
        customer_phone = customer.get("phone") or ""
        for debt in customer.get("orders") or []:
            if not isinstance(debt, dict) or not debt.get("id"):
                continue
            order_id = debt["id"]
            patch = {
                "customer_name": customer_name,
                "store": debt.get("store") or customer.get("store") or "runner",
                "total": float(debt.get("total") or 0),
                "partial_paid": float(debt.get("partial_paid") or 0),
                "payment_method": "prazo",
                "prazo_paid": False,
                "created_at": debt.get("date") or now,
                "items": debt.get("items") or [],
                "_source_sync": {
                    "source": "charts-3.emergent.host",
                    "synced_at": now,
                    "debt_reconstructed": True,
                    "customer_phone": customer_phone,
                },
            }
            if dry_run:
                writes += 1
                continue

            existing = db.orders.find_one({"id": order_id}, {"_id": 1})
            if existing:
                db.orders.update_one(
                    {"id": order_id},
                    {"$set": {
                        "customer_name": patch["customer_name"],
                        "store": patch["store"],
                        "total": patch["total"],
                        "partial_paid": patch["partial_paid"],
                        "payment_method": "prazo",
                        "prazo_paid": False,
                        "_source_sync": patch["_source_sync"],
                    }},
                )
            else:
                patch.update({
                    "status": "delivered",
                    "updated_at": patch["created_at"],
                    "synced": True,
                    "mirror_reconstructed": True,
                })
                db.orders.insert_one(patch)
            writes += 1
    return writes


def sync_payments(db, payloads: Dict[str, FetchResult], dry_run: bool) -> Tuple[int, int]:
    result = payloads.get("prazo:payments")
    if not result:
        return (0, 0)
    full, partial = [], []
    for payment in result.payload.get("payments") or []:
        if not isinstance(payment, dict) or not payment.get("id"):
            continue
        if payment.get("type") == "partial_payment":
            partial.append(payment)
        else:
            full.append(payment)
    a = bulk_upsert(db.prazo_payments, full, ("id",), dry_run)
    b = bulk_upsert(db.prazo_partial_payments, partial, ("id",), dry_run)
    return a, b


def sync_snapshots(db, fetched: Iterable[FetchResult], dry_run: bool) -> int:
    fetched = list(fetched)
    if dry_run:
        return len(fetched)
    now = utc_now()
    for result in fetched:
        db.source_sync_latest.update_one(
            {"key": result.key},
            {"$set": {
                "key": result.key,
                "path": result.path,
                "protected": result.protected,
                "payload": result.payload,
                "payload_sha256": payload_hash(result.payload),
                "fetched_at": now,
            }},
            upsert=True,
        )
    return len(fetched)


def collect_source(client: SourceClient) -> Tuple[Dict[str, FetchResult], Dict[str, str]]:
    payloads: Dict[str, FetchResult] = {}
    errors: Dict[str, str] = {}

    endpoints = [
        ("prazo:customers", "/api/prazo/customers", False),
        ("prazo:debts", "/api/prazo/debts", False),
        ("prazo:payments", "/api/prazo/payments-history?limit=10000", False),
        ("adicionais", "/api/kitchen/adicionais", False),
        ("expenses", "/api/expenses", True),
        ("manual-sales", "/api/gestor/manual-sales?limit=10000", True),
    ]
    for store in STORES:
        endpoints.extend([
            (f"orders:{store}", f"/api/orders/{store}", False),
            (f"stock:{store}", f"/api/stock/{store}", False),
            (f"menu:{store}", f"/api/kitchen/menu/{store}", False),
            (f"cash:{store}", f"/api/cash/{store}/today", False),
        ])

    for key, path, protected in endpoints:
        try:
            payloads[key] = client.get(key, path, protected=protected)
        except Exception as exc:
            errors[key] = f"{type(exc).__name__}: {exc}"
    return payloads, errors


def apply_operational_sync(db, payloads: Dict[str, FetchResult], dry_run: bool) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    customers = payloads.get("prazo:customers")
    counts["prazo_customers"] = bulk_upsert(
        db.prazo_customers,
        (customers.payload.get("customers") or []) if customers else [],
        ("id",),
        dry_run,
    )

    stock_count = 0
    menu_count = 0
    for store in STORES:
        stock = payloads.get(f"stock:{store}")
        stock_docs = [strip_computed_stock_fields(x) for x in (stock.payload.get("stock") or [])] if stock else []
        stock_count += bulk_upsert(db.stock, stock_docs, ("store", "menu_item_id"), dry_run)

        menu = payloads.get(f"menu:{store}")
        menu_docs = []
        if menu:
            menu_docs = menu.payload.get("menu") or menu.payload.get("items") or []
        for item in menu_docs:
            if isinstance(item, dict) and not item.get("store"):
                item["store"] = store
        menu_count += bulk_upsert(db.menu, menu_docs, ("store", "id"), dry_run)

    counts["stock"] = stock_count
    counts["menu"] = menu_count

    adicionais = payloads.get("adicionais")
    counts["adicionais"] = bulk_upsert(
        db.adicionais,
        (adicionais.payload.get("adicionais") or []) if adicionais else [],
        ("id",),
        dry_run,
    )

    expenses = payloads.get("expenses")
    counts["expenses"] = bulk_upsert(
        db.expenses,
        (expenses.payload.get("expenses") or []) if expenses else [],
        ("id",),
        dry_run,
    )

    counts["live_orders"] = sync_live_orders(db, payloads, dry_run)
    counts["debt_orders"] = sync_debts(db, payloads, dry_run)
    full, partial = sync_payments(db, payloads, dry_run)
    counts["prazo_payments"] = full
    counts["prazo_partial_payments"] = partial
    counts["snapshots"] = sync_snapshots(db, payloads.values(), dry_run)
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mirror operational GANOH data from Emergent.")
    parser.add_argument("--apply", action="store_true", help="Write to destination MongoDB. Default is dry-run.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_base = os.getenv("SOURCE_BASE_URL", DEFAULT_SOURCE).rstrip("/")
    source_user = os.getenv("SOURCE_GESTOR_USERNAME")
    source_password = os.getenv("SOURCE_GESTOR_PASSWORD")
    mongo_url = os.getenv("MONGO_URL")
    db_name = os.getenv("DB_NAME", "ganohdb")
    dry_run = not args.apply or env_bool("SYNC_DRY_RUN", default=False)

    client = SourceClient(source_base, source_user, source_password)
    payloads, errors = collect_source(client)

    critical = [
        "prazo:customers",
        "prazo:debts",
        "prazo:payments",
        "stock:runner",
        "stock:gym-londres",
        "menu:runner",
        "menu:gym-londres",
    ]
    missing_critical = [key for key in critical if key not in payloads]
    if missing_critical:
        print(json.dumps({
            "ok": False,
            "dry_run": dry_run,
            "error": "critical source endpoints unavailable",
            "missing": missing_critical,
            "endpoint_errors": errors,
        }, ensure_ascii=False))
        return 2

    mongo_client = None
    if dry_run:
        class DryDB:
            def __getattr__(self, name):
                return None
        db = DryDB()
    else:
        if not mongo_url:
            print(json.dumps({"ok": False, "error": "MONGO_URL is required with --apply"}, ensure_ascii=False))
            return 2
        mongo_client = MongoClient(mongo_url, serverSelectionTimeoutMS=10000)
        mongo_client.admin.command("ping")
        db = mongo_client[db_name]

    try:
        counts = apply_operational_sync(db, payloads, dry_run)
        run_doc = {
            "ok": True,
            "source": source_base,
            "dry_run": dry_run,
            "finished_at": utc_now(),
            "counts": counts,
            "endpoint_errors": errors,
            "warning": (
                "Legacy API does not expose a complete historical order export. "
                "Operational state and unpaid prazo continuity are mirrored; latest raw snapshots are retained."
            ),
        }
        if not dry_run:
            db.source_sync_runs.insert_one(dict(run_doc))
        print(json.dumps(run_doc, ensure_ascii=False, default=str))
        return 0
    finally:
        if mongo_client is not None:
            mongo_client.close()


if __name__ == "__main__":
    sys.exit(main())
