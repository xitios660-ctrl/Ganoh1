"""Experimental durable offline journal for GANOH Windows (NOT production-integrated).

This module deliberately has NO MongoDB credentials, remote requests, automatic
financial settlement or live backend dependency. Only sale drafts are supported
in phase 1. Do not use this prototype to take real payments until the central
idempotent sync endpoint, authorization and operational tests are completed.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UNITS = frozenset({"runner", "gym-londres"})
PAYMENT_METHODS = frozenset({"cash", "pix", "debit", "credit", "prazo"})


class OfflineError(ValueError):
    """Invalid data, conflicting identifiers or a rejected synchronization ack."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def require_legacy_baseline(db):
    imported=db.execute("SELECT value FROM metadata WHERE key IN ('legacy_active','legacy_staging') LIMIT 1").fetchone()
    approved=db.execute("SELECT value FROM metadata WHERE key='legacy_operational_baseline'").fetchone()
    if imported and not (approved and approved[0]):
        raise OfflineError('Conclua a conferência dos saldos importados antes de registrar novas operações')


class OfflineJournal:
    """A single-unit SQLite journal; each PC must have its own DB and device identity.

    Every sale and its outbox event are committed in the SAME SQLite transaction.
    An operation_id is never regenerated on a retry or after a reboot.
    """

    def __init__(self, path: str | Path, unit: str, *, encryption_key: bytes | None = None):
        if unit not in UNITS:
            raise OfflineError("Unidade inválida")
        self._driver = sqlite3
        self._key = encryption_key
        if encryption_key is not None:
            if not isinstance(encryption_key, bytes) or len(encryption_key) != 32:
                raise OfflineError('SQLCipher requires a 32-byte key')
            from sqlcipher3 import dbapi2
            self._driver = dbapi2
        self.unit = unit
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = self._driver.connect(str(self.path), timeout=5, isolation_level=None)
        try:
            connection.row_factory = self._driver.Row
            if self._key is not None:
                connection.execute('PRAGMA key = "x\'' + self._key.hex() + '\'"')
                if not connection.execute('PRAGMA cipher_version').fetchone():
                    raise OfflineError('SQLCipher unavailable; refusing plaintext fallback')
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            return connection
        except Exception:
            connection.close()
            raise

    def _initialize(self) -> None:
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("BEGIN IMMEDIATE")
            try:
                schema_version = db.execute('PRAGMA user_version').fetchone()[0]
                if schema_version not in (0, 1, 2, 3, 4):
                    raise OfflineError('Versão do banco mais recente; atualização compatível necessária')
                db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS operations (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation_id TEXT NOT NULL UNIQUE,
                        unit TEXT NOT NULL CHECK(unit IN ('runner','gym-londres')),
                        kind TEXT NOT NULL CHECK(kind = 'sale.create'),
                        payload_json TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'pending'
                            CHECK(state IN ('pending','synced','conflict')),
                        created_at TEXT NOT NULL,
                        synced_at TEXT,
                        central_receipt_id TEXT,
                        last_error TEXT
                    )
                """)
                db.execute("CREATE INDEX IF NOT EXISTS idx_offline_pending ON operations(state,sequence)")
                db.execute("""
                    CREATE TABLE IF NOT EXISTS local_sales (
                        sale_id TEXT PRIMARY KEY,
                        operation_id TEXT NOT NULL UNIQUE REFERENCES operations(operation_id),
                        unit TEXT NOT NULL CHECK(unit IN ('runner','gym-londres')),
                        total_cents INTEGER NOT NULL CHECK(total_cents >= 0),
                        payment_method TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                bound = db.execute("SELECT value FROM metadata WHERE key='unit'").fetchone()
                if bound is None:
                    db.execute("INSERT INTO metadata(key,value) VALUES('unit',?)", (self.unit,))
                elif bound["value"] != self.unit:
                    raise OfflineError("Este banco local pertence a outra unidade")
            except Exception:
                db.execute("ROLLBACK")
                raise
            else:
                from desktop.commerce import initialize
                try:
                    initialize(db)
                    db.execute("PRAGMA user_version = " + str(max(3, schema_version)))
                except Exception:
                    db.execute('ROLLBACK')
                    raise
                db.execute("COMMIT")

    def record_sale(
        self,
        *,
        sale_id: str,
        total_cents: int,
        payment_method: str,
        items: list[dict[str, Any]],
        operation_id: str | None = None,
        cash_shift_id: str | None = None,
        actor: dict | None = None,
        customer_name: str | None = None,
        customer_id: str | None = None,
        customer_version: int | None = None,
    ) -> dict[str, Any]:
        """Record a local draft and the exact retryable outbox event atomically.

        A matching operation_id is idempotent. The same ID with different data
        is rejected; a reused sale_id with another operation is also rejected.
        No stock or customer credit is adjusted by this phase-1 prototype.
        """
        if not isinstance(sale_id, str) or not sale_id.strip():
            raise OfflineError("sale_id obrigatório")
        if type(total_cents) is not int or total_cents < 0:
            raise OfflineError("total_cents deve ser inteiro não negativo")
        if payment_method not in PAYMENT_METHODS:
            raise OfflineError("Forma de pagamento inválida")
        if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
            raise OfflineError("Lista de itens inválida")
        candidate = operation_id or str(uuid.uuid4())
        try:
            operation_key = str(uuid.UUID(candidate))
        except (ValueError, AttributeError, TypeError) as exc:
            raise OfflineError("operation_id deve ser um UUID") from exc

        payload = {
            "operation_id": operation_key,
            "unit": self.unit,
            "kind": "sale.create",
            "sale_id": sale_id,
            "total_cents": total_cents,
            "payment_method": payment_method,
            "items": items,
        }
        if payment_method=='prazo':
            payload['customer_id']=customer_id
            payload['customer_version']=customer_version
        if customer_name is not None:
            if not isinstance(customer_name,str) or len(customer_name)>120:
                raise OfflineError('Nome do cliente inválido')
            payload['customer_name'] = customer_name
        if cash_shift_id is not None:
            payload['cash_shift_id'] = cash_shift_id
        raw = _canonical(payload)
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                existing = db.execute(
                    "SELECT payload_json,fingerprint,state FROM operations WHERE operation_id=?",
                    (operation_key,),
                ).fetchone()
                if existing is not None:
                    if existing["fingerprint"] != fingerprint or existing["payload_json"] != raw:
                        raise OfflineError("operation_id reutilizado com dados diferentes")
                    result = {"operation_id": operation_key, "state": existing["state"],
                              "fingerprint": fingerprint, "already_exists": True}
                else:
                    require_legacy_baseline(db)
                    if actor:
                        from desktop.auth import check_actor
                        check_actor(db,actor,'sale.create')
                    from desktop.operations import enabled, current
                    if enabled(db):
                        active = current(db)
                        if not active or active['status'] != 'open' or cash_shift_id != active['shift_id']:
                            raise OfflineError('Venda exige caixa aberto e vínculo com o turno atual')
                    if payment_method=='prazo':
                        from desktop.business_rules import identifier,BusinessError
                        try: identifier(customer_id)
                        except BusinessError as exc: raise OfflineError(str(exc)) from exc
                        customer=db.execute('SELECT * FROM customers WHERE customer_id=?',(customer_id,)).fetchone()
                        approval=db.execute('SELECT state FROM business_operations WHERE operation_id=?',
                            ((customer['approval_operation_id'] if customer else None),)).fetchone()
                        from desktop.commerce import balance
                        if (not customer or not approval or approval['state']!='synced' or customer['version']!=customer_version
                                or balance(db,'receivable/'+customer_id)+total_cents>customer['credit_limit_cents']):
                            raise OfflineError('Prazo exige limite confirmado pelo servidor, versão válida e saldo disponível')
                    from desktop.inventory import project
                    projected = {entry['sku']: entry for entry in project(db)}
                    for item in items:
                        entry = projected.get(item.get('sku'))
                        if entry and 'base_version' in item:
                            if entry['blocked'] or entry['version'] != item['base_version'] or type(item.get('quantity')) is not int or not 1 <= item['quantity'] <= entry['quantity']:
                                raise OfflineError('Estoque local alterado ou insuficiente')
                    timestamp = _utc_now()
                    db.execute('INSERT INTO event_order(operation_id,kind) VALUES(?,?)', (operation_key, 'sale.create'))
                    db.execute(
                        """INSERT INTO operations
                        (operation_id,unit,kind,payload_json,fingerprint,created_at)
                        VALUES (?,?,?,?,?,?)""",
                        (operation_key, self.unit, "sale.create", raw, fingerprint, timestamp),
                    )
                    db.execute(
                        """INSERT INTO local_sales
                        (sale_id,operation_id,unit,total_cents,payment_method,created_at)
                        VALUES (?,?,?,?,?,?)""",
                        (sale_id, operation_key, self.unit, total_cents, payment_method, timestamp),
                    )
                    db.execute("INSERT INTO order_progress VALUES(?,'received',1,?,?)",(sale_id,timestamp,operation_key))
                    if actor:
                        db.execute('INSERT INTO event_actors VALUES(?,?,?)',(operation_key,actor['actor_id'],actor['role']))
                    if payment_method in ('cash','prazo'):
                        from desktop.commerce import post
                        account='cash' if payment_method=='cash' else 'receivable/'+customer_id
                        post(db,operation_key,[(account,total_cents),('revenue',-total_cents)])
                        if payment_method=='prazo': db.execute('UPDATE customers SET version=version+1 WHERE customer_id=?',(customer_id,))
                    result = {"operation_id": operation_key, "state": "pending",
                              "fingerprint": fingerprint, "already_exists": False}
            except self._driver.IntegrityError as exc:
                db.execute("ROLLBACK")
                raise OfflineError("Venda ou operação já registrada com identificador diferente") from exc
            except Exception:
                db.execute("ROLLBACK")
                raise
            else:
                db.execute("COMMIT")
        return result

    def pending(self, limit: int = 100) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise OfflineError("Limite inválido")
        with closing(self._connect()) as db:
            rows = db.execute(
                """SELECT e.position AS sequence,o.operation_id,o.unit,o.kind,o.payload_json,o.fingerprint,o.created_at
                   FROM (SELECT * FROM operations UNION ALL
                         SELECT sequence,operation_id,unit,kind,payload_json,fingerprint,state,created_at,synced_at,central_receipt_id,last_error FROM business_operations) o
                   JOIN event_order e ON e.operation_id=o.operation_id
                   WHERE o.state='pending' ORDER BY e.position LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {"sequence": row["sequence"], "operation_id": row["operation_id"],
             "unit": row["unit"], "kind": row["kind"],
             "payload": json.loads(row["payload_json"]),
             "fingerprint": row["fingerprint"], "created_at": row["created_at"]}
            for row in rows
        ]

    @staticmethod
    def _operation_table(db, operation_id):
        row = db.execute('SELECT kind FROM event_order WHERE operation_id=?', (operation_id,)).fetchone()
        return 'operations' if not row or row['kind'] == 'sale.create' else 'business_operations'

    def acknowledge(self, operation_id: str, fingerprint: str, central_receipt_id: str) -> None:
        """Ack ONLY a central receipt for the exact content and UUID.

        Network timeouts must keep the operation pending; a durable central
        receipt with the same UUID/hash can safely be acknowledged on retry.
        """
        if not central_receipt_id or not isinstance(central_receipt_id, str):
            raise OfflineError("Comprovante central obrigatório")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                table = self._operation_table(db, operation_id)
                row = db.execute(
                    f"SELECT fingerprint,state,central_receipt_id FROM {table} WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                if not row or row["fingerprint"] != fingerprint or row["state"] == "conflict":
                    raise OfflineError("Confirmação inválida ou operação em conflito")
                if row["state"] == "synced" and row["central_receipt_id"] != central_receipt_id:
                    raise OfflineError("Comprovante central diferente do confirmado")
                if row["state"] == "pending":
                    db.execute(
                        f"""UPDATE {table}
                        SET state='synced',central_receipt_id=?,synced_at=?,last_error=NULL
                        WHERE operation_id=?""",
                        (central_receipt_id, _utc_now(), operation_id),
                    )
            except Exception:
                db.execute("ROLLBACK")
                raise
            else:
                db.execute("COMMIT")

    def flag_conflict(self, operation_id: str, reason: str) -> None:
        if not reason or not reason.strip():
            raise OfflineError("Motivo obrigatório")
        with closing(self._connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                table = self._operation_table(db, operation_id)
                row = db.execute(
                    f"SELECT state FROM {table} WHERE operation_id=?", (operation_id,)
                ).fetchone()
                if not row or row["state"] == "synced":
                    raise OfflineError("Não é possível sinalizar essa operação")
                db.execute(
                    f"UPDATE {table} SET state='conflict',last_error=? WHERE operation_id=?",
                    (reason[:500], operation_id),
                )
            except Exception:
                db.execute("ROLLBACK")
                raise
            else:
                db.execute("COMMIT")

    def status(self) -> dict[str, Any]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT state,COUNT(*) AS amount FROM (SELECT state FROM operations UNION ALL SELECT state FROM business_operations) GROUP BY state"
            ).fetchall()
            last = db.execute(
                "SELECT MAX(synced_at) AS last_synced_at FROM (SELECT synced_at FROM operations UNION ALL SELECT synced_at FROM business_operations)"
            ).fetchone()["last_synced_at"]
            check = db.execute("PRAGMA quick_check").fetchone()[0]
        totals = {row["state"]: row["amount"] for row in rows}
        return {"unit": self.unit, "pending": totals.get("pending", 0),
                "synced": totals.get("synced", 0), "conflicts": totals.get("conflict", 0),
                "last_synced_at": last, "sqlite_integrity": check}
