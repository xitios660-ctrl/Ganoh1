"""Immutable local commercial events and double-entry ledger, atomic with outbox."""
import hashlib
import json
from contextlib import closing
from desktop.business_rules import BusinessError, KINDS, customer_name, identifier, plan
from desktop.offline_store import OfflineError, _canonical, _utc_now


def initialize(db):
    # Executed inside OfflineJournal's migration transaction. No destructive DDL.
    statements = [
        '''CREATE TABLE IF NOT EXISTS order_progress (
           sale_id TEXT PRIMARY KEY,status TEXT NOT NULL,version INTEGER NOT NULL,
           updated_at TEXT NOT NULL,last_operation_id TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS cash_shifts (
          shift_id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('open','closed','needs_review')),
          opening_cents INTEGER NOT NULL, opened_at TEXT NOT NULL, open_operation_id TEXT NOT NULL UNIQUE,
          expected_cents INTEGER, counted_cents INTEGER, closed_at TEXT, close_operation_id TEXT UNIQUE)''',
        "INSERT OR IGNORE INTO metadata VALUES('cash_control_enabled','0')",
        'CREATE TABLE IF NOT EXISTS inventory_coverage (operation_id TEXT PRIMARY KEY)',
        'CREATE TABLE IF NOT EXISTS inventory_coverage_staging (operation_id TEXT PRIMARY KEY)',
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
    from desktop.auth import initialize as initialize_auth
    initialize_auth(db)
    shift_columns={row['name'] for row in db.execute('PRAGMA table_info(cash_shifts)')}
    for column,declaration in [('reconcile_operation_id','TEXT'),('reconciled_cents','INTEGER'),('reconciled_at','TEXT')]:
        if column not in shift_columns: db.execute(f'ALTER TABLE cash_shifts ADD COLUMN {column} {declaration}')
    columns={row['name'] for row in db.execute('PRAGMA table_info(customers)')}
    for column,declaration in [('credit_limit_cents','INTEGER NOT NULL DEFAULT 0'),('version','INTEGER NOT NULL DEFAULT 1'),('approval_operation_id','TEXT')]:
        if column not in columns: db.execute(f'ALTER TABLE customers ADD COLUMN {column} {declaration}')
    # Old sale journal entries keep their IDs, payloads, states and ordering.
    db.execute("INSERT OR IGNORE INTO event_order(operation_id,kind) SELECT operation_id,kind FROM operations WHERE operation_id NOT IN (SELECT operation_id FROM event_order) ORDER BY sequence")
    db.execute("INSERT OR IGNORE INTO order_progress SELECT sale_id,'received',1,created_at,operation_id FROM local_sales")
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


def record(journal, *, operation_id, kind, data, actor=None):
    try:
        identifier(operation_id)
        if not isinstance(kind, str) or kind not in KINDS:
            raise BusinessError('Operação comercial não suportada')
        if not isinstance(data, dict) or set(data) & {'operation_id', 'unit', 'kind'}:
            raise BusinessError('Dados comerciais inválidos')
        payload = {**data, 'operation_id': operation_id, 'unit': journal.unit, 'kind': kind}
        if kind in ('customer.create', 'prazo.receive','customer.limit'):
            identifier(payload.get('customer_id'))
        if kind == 'customer.create':
            payload['name'] = customer_name(payload.get('name'))
        with closing(journal._connect()) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                prior = db.execute('SELECT * FROM business_operations WHERE operation_id=?', (operation_id,)).fetchone()
                if prior:
                    old = json.loads(prior['payload_json'])
                    for field in ('cash_shift_id','customer_version'):
                        if field in old and field not in payload: payload[field]=old[field]
                    raw = _canonical(payload)
                    fingerprint = hashlib.sha256(raw.encode()).hexdigest()
                    if prior['payload_json'] != raw:
                        raise BusinessError('UUID reutilizado com dados diferentes')
                    db.execute('COMMIT')
                    return {'operation_id': operation_id, 'fingerprint': fingerprint, 'state': prior['state'], 'already_exists': True}
                if actor:
                    from desktop.auth import check_actor
                    check_actor(db,actor,kind)
                customer_id = payload.get('customer_id')
                exists = db.execute('SELECT 1 FROM customers WHERE customer_id=?', (customer_id,)).fetchone() is not None
                if kind=='prazo.receive' and exists:
                    payload.setdefault('customer_version',db.execute('SELECT version FROM customers WHERE customer_id=?',(customer_id,)).fetchone()[0])
                postings = plan(payload, cash_cents=balance(db, 'cash'),
                                debt_cents=balance(db, 'receivable/' + str(customer_id)), customer_exists=exists)
                from desktop.operations import prepare
                payload = prepare(db, payload)
                raw = _canonical(payload)
                fingerprint = hashlib.sha256(raw.encode()).hexdigest()
                db.execute('INSERT INTO event_order(operation_id,kind) VALUES(?,?)', (operation_id, kind))
                db.execute('''INSERT INTO business_operations(operation_id,business_id,unit,kind,payload_json,fingerprint,created_at)
                              VALUES(?,?,?,?,?,?,?)''', (operation_id, payload['business_id'], journal.unit, kind, raw, fingerprint, _utc_now()))
                if kind == 'customer.create':
                    db.execute('INSERT INTO customers(customer_id,name,name_key,operation_id) VALUES(?,?,?,?)',
                               (payload['customer_id'], payload['name'], payload['name'].casefold(), operation_id))
                if kind == 'prazo.receive':
                    db.execute('INSERT INTO payment_refs VALUES(?,?)', (payload['payment_reference'].strip().casefold(), operation_id))
                if actor:
                    db.execute('INSERT INTO event_actors VALUES(?,?,?)', (operation_id,actor['actor_id'],actor['role']))
                from desktop.operations import apply_local
                apply_local(db, payload)
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
        db.execute('BEGIN')
        accounts = {row['account']: row['amount'] for row in db.execute('SELECT account,SUM(amount_cents) amount FROM ledger GROUP BY account')}
        clients = [dict(row) for row in db.execute('SELECT customer_id,name,credit_limit_cents,version,approval_operation_id FROM customers ORDER BY name')]
        for customer in clients:
            approved=db.execute('SELECT state FROM business_operations WHERE operation_id=?',(customer['approval_operation_id'],)).fetchone()
            customer['credit_approved']=bool(approved and approved['state']=='synced')
            customer['debt_cents'] = accounts.get('receivable/' + customer['customer_id'], 0)
            customer['credit_available_cents']=max(0,customer['credit_limit_cents']-customer['debt_cents']) if customer['credit_approved'] else 0
        events = [dict(row) for row in db.execute('SELECT operation_id,kind,payload_json,state,last_error,created_at FROM business_operations ORDER BY sequence DESC LIMIT 100')]
        for event in events:
            event['payload'] = json.loads(event.pop('payload_json'))
    return {'unit': journal.unit, 'provisional': True, 'cash_cents': accounts.get('cash', 0),
            'revenue_cents': -accounts.get('revenue', 0), 'cash_variance_cents':accounts.get('cash_variance',0), 'expense_cents': accounts.get('expense', 0),
            'balanced': sum(accounts.values()) == 0, 'customers': clients, 'events': events}
