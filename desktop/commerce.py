"""Immutable local commercial events and double-entry ledger, atomic with outbox."""
import hashlib
import json
from contextlib import closing
from desktop.business_rules import BusinessError, KINDS, customer_name, identifier, plan
from desktop.offline_store import OfflineError, _canonical, _utc_now


def initialize(db):
    # Executed inside OfflineJournal's migration transaction. No destructive DDL.
    statements = [
        'CREATE TABLE IF NOT EXISTS event_order (position INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL)',
        '''CREATE TABLE IF NOT EXISTS business_operations (
          sequence INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL UNIQUE,
          business_id TEXT NOT NULL UNIQUE, unit TEXT NOT NULL, kind TEXT NOT NULL,
          payload_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
          state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','synced','conflict')),
          created_at TEXT NOT NULL, synced_at TEXT, central_receipt_id TEXT, last_error TEXT)''',
        '''CREATE TABLE IF NOT EXISTS ledger (
          operation_id TEXT NOT NULL REFERENCES event_order(operation_id), line INTEGER NOT NULL,
          account TEXT NOT NULL, amount_cents INTEGER NOT NULL,
          PRIMARY KEY(operation_id,line))''',
        '''CREATE TABLE IF NOT EXISTS customers (
          customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
          operation_id TEXT NOT NULL UNIQUE REFERENCES event_order(operation_id))''',
    ]
    statements.append('CREATE INDEX IF NOT EXISTS idx_ledger_account ON ledger(account)')
    statements.append('CREATE TABLE IF NOT EXISTS payment_refs (reference TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE REFERENCES event_order(operation_id))')
    for statement in statements:
        db.execute(statement)
    # Old sale journal entries keep their IDs, payloads, states and ordering.
    db.execute("INSERT OR IGNORE INTO event_order(operation_id,kind) SELECT operation_id,kind FROM operations WHERE operation_id NOT IN (SELECT operation_id FROM event_order) ORDER BY sequence")
    for row in db.execute("SELECT operation_id,total_cents FROM local_sales WHERE payment_method='cash'").fetchall():
        post(db, row['operation_id'], [('cash', row['total_cents']), ('revenue', -row['total_cents'])], backfill=True)


def post(db, operation_id, postings, *, backfill=False):
    if sum(amount for _, amount in postings) != 0:
        raise OfflineError('Lançamento financeiro desbalanceado')
    for line, (account, amount) in enumerate(postings):
        command = 'INSERT OR IGNORE' if backfill else 'INSERT'
        db.execute(command + ' INTO ledger VALUES(?,?,?,?)', (operation_id, line, account, amount))


def balance(db, account):
    return db.execute('SELECT COALESCE(SUM(amount_cents),0) FROM ledger WHERE account=?', (account,)).fetchone()[0]


def record(journal, *, operation_id, kind, data):
    try:
        identifier(operation_id)
        if not isinstance(kind, str) or kind not in KINDS:
            raise BusinessError('Operação comercial não suportada')
        if not isinstance(data, dict) or set(data) & {'operation_id', 'unit', 'kind'}:
            raise BusinessError('Dados comerciais inválidos')
        payload = {**data, 'operation_id': operation_id, 'unit': journal.unit, 'kind': kind}
        if kind == 'customer.create':
            payload['name'] = customer_name(payload.get('name'))
        raw = _canonical(payload)
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        with closing(journal._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                prior = db.execute('SELECT * FROM business_operations WHERE operation_id=?', (operation_id,)).fetchone()
                if prior:
                    if prior['payload_json'] != raw:
                        raise BusinessError('UUID reutilizado com dados diferentes')
                    db.execute('COMMIT')
                    return {'operation_id': operation_id, 'fingerprint': fingerprint, 'state': prior['state'], 'already_exists': True}
                customer_id = payload.get('customer_id')
                exists = db.execute('SELECT 1 FROM customers WHERE customer_id=?', (customer_id,)).fetchone() is not None
                postings = plan(payload, cash_cents=balance(db, 'cash'),
                                debt_cents=balance(db, 'receivable/' + str(customer_id)), customer_exists=exists)
                db.execute('INSERT INTO event_order(operation_id,kind) VALUES(?,?)', (operation_id, kind))
                db.execute('''INSERT INTO business_operations(operation_id,business_id,unit,kind,payload_json,fingerprint,created_at)
                              VALUES(?,?,?,?,?,?,?)''', (operation_id, payload['business_id'], journal.unit, kind, raw, fingerprint, _utc_now()))
                if kind == 'customer.create':
                    db.execute('INSERT INTO customers VALUES(?,?,?,?)',
                               (payload['customer_id'], payload['name'], payload['name'].casefold(), operation_id))
                if kind == 'prazo.receive':
                    db.execute('INSERT INTO payment_refs VALUES(?,?)', (payload['payment_reference'].strip().casefold(), operation_id))
                post(db, operation_id, postings)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
    except (BusinessError, journal._driver.IntegrityError) as exc:
        raise OfflineError(str(exc) if isinstance(exc, BusinessError) else 'Identificador ou cliente já registrado; revisão necessária') from exc
    return {'operation_id': operation_id, 'fingerprint': fingerprint, 'state': 'pending', 'already_exists': False}


def summary(journal):
    with closing(journal._connect()) as db:
        accounts = {row['account']: row['amount'] for row in db.execute('SELECT account,SUM(amount_cents) amount FROM ledger GROUP BY account')}
        clients = [dict(row) for row in db.execute('SELECT customer_id,name FROM customers ORDER BY name')]
        for customer in clients:
            customer['debt_cents'] = accounts.get('receivable/' + customer['customer_id'], 0)
        events = [dict(row) for row in db.execute('SELECT operation_id,kind,payload_json,state,last_error,created_at FROM business_operations ORDER BY sequence DESC LIMIT 100')]
        for event in events:
            event['payload'] = json.loads(event.pop('payload_json'))
    return {'unit': journal.unit, 'provisional': True, 'cash_cents': accounts.get('cash', 0),
            'revenue_cents': -accounts.get('revenue', 0), 'expense_cents': accounts.get('expense', 0),
            'balanced': sum(accounts.values()) == 0, 'customers': clients, 'events': events}
