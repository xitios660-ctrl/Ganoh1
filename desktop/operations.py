"""Stock and cash-shift state changes inside the journal transaction."""
from contextlib import closing
from desktop.business_rules import BusinessError
from desktop.offline_store import _utc_now

CASH_KINDS = frozenset({'cash.withdraw', 'expense.create', 'prazo.receive'})


def enabled(db):
    return db.execute("SELECT value FROM metadata WHERE key='cash_control_enabled'").fetchone()[0] == '1'


def current(db):
    return db.execute("SELECT * FROM cash_shifts WHERE status IN ('open','needs_review') ORDER BY opened_at DESC LIMIT 1").fetchone()


def prepare(db, payload):
    kind = payload['kind']
    active = current(db)
    if kind in ('customer.limit','prazo.receive'):
        customer=db.execute('SELECT * FROM customers WHERE customer_id=?',(payload['customer_id'],)).fetchone()
        version=payload.get('base_version') if kind=='customer.limit' else payload.get('customer_version')
        if not customer or customer['version']!=version:raise BusinessError('Cliente foi alterado; versão deve ser revisada')
    if kind == 'order.status':
        from desktop.orders import prepare as prepare_order
        prepare_order(db,payload)
    elif kind == 'cash.open':
        if active:
            raise BusinessError('Já existe caixa aberto ou com diferença pendente de revisão')
    elif kind=='cash.reconcile':
        if not active or active['status']!='needs_review' or active['shift_id']!=payload['shift_id']:
            raise BusinessError('Conciliação exige turno com diferença pendente')
    elif kind == 'cash.close':
        if not active or active['status'] != 'open' or active['shift_id'] != payload['shift_id']:
            raise BusinessError('Caixa não está aberto ou foi alterado')
    elif kind in CASH_KINDS and enabled(db):
        if not active or active['status'] != 'open':
            raise BusinessError('Abra o caixa antes de registrar movimentações')
        if payload.get('cash_shift_id', active['shift_id']) != active['shift_id']:
            raise BusinessError('Movimentação pertence a outro turno de caixa')
        payload['cash_shift_id'] = active['shift_id']
    elif kind=='catalog.upsert':
        from desktop.inventory import project
        entry=next((item for item in project(db) if item['sku']==payload['sku']),None)
        if (entry and (entry['blocked'] or entry['version']!=payload['base_version'])) or (not entry and payload['base_version']!=0):
            raise BusinessError('Versão do produto divergente; revisão obrigatória')
    elif kind == 'stock.adjust':
        from desktop.inventory import project
        entry = next((item for item in project(db) if item['sku'] == payload['sku']), None)
        if not entry or entry['blocked'] or entry['version'] != payload['base_version'] or entry['quantity'] + payload['delta'] < 0:
            raise BusinessError('Estoque alterado, insuficiente ou em conflito; revisão necessária')
    return payload


def apply_local(db, payload):
    if payload['kind']=='customer.limit':
        db.execute('UPDATE customers SET credit_limit_cents=?,version=version+1,approval_operation_id=? WHERE customer_id=?',
                   (payload['limit_cents'],payload['operation_id'],payload['customer_id']))
    elif payload['kind']=='prazo.receive':
        db.execute('UPDATE customers SET version=version+1 WHERE customer_id=?',(payload['customer_id'],))
    elif payload['kind'] == 'order.status':
        from desktop.orders import apply_local as apply_order
        apply_order(db,payload)
    elif payload['kind'] == 'cash.open':
        db.execute('''INSERT INTO cash_shifts(shift_id,status,opening_cents,opened_at,open_operation_id)
                      VALUES(?,'open',?,?,?)''', (payload['shift_id'], payload['counted_cents'], _utc_now(), payload['operation_id']))
        db.execute("UPDATE metadata SET value='1' WHERE key='cash_control_enabled'")
    elif payload['kind']=='cash.reconcile':
        db.execute("UPDATE cash_shifts SET status='closed',reconcile_operation_id=?,reconciled_cents=?,reconciled_at=? WHERE shift_id=?",
                   (payload['operation_id'],payload['counted_cents'],_utc_now(),payload['shift_id']))
    elif payload['kind'] == 'cash.close':
        status = 'closed' if payload['counted_cents'] == payload['expected_cents'] else 'needs_review'
        db.execute('''UPDATE cash_shifts SET status=?,expected_cents=?,counted_cents=?,closed_at=?,close_operation_id=? WHERE shift_id=?''',
                   (status, payload['expected_cents'], payload['counted_cents'], _utc_now(), payload['operation_id'], payload['shift_id']))


def state(journal):
    with closing(journal._connect()) as db:
        active = current(db)
        return {'cash_control_enabled': enabled(db), 'active_shift': dict(active) if active else None,
                'shifts': [dict(row) for row in db.execute('SELECT * FROM cash_shifts ORDER BY opened_at DESC LIMIT 30')]}
