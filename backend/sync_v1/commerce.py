"""Commercial effects for the disposable central API; caller owns transaction."""
from desktop.business_rules import BusinessError, plan


def balance(db, session, unit, account):
    rows = list(db.ledger.aggregate([
        {'$match': {'unit': unit, 'account': account}},
        {'$group': {'_id': None, 'amount': {'$sum': '$amount_cents'}}},
    ], session=session))
    return rows[0]['amount'] if rows else 0


def post(db, session, unit, operation_id, postings):
    if sum(amount for _, amount in postings) != 0:
        raise ValueError('Unbalanced ledger')
    if postings:
        db.ledger.insert_many([{'unit': unit, 'operation_id': operation_id, 'line': line,
                                'account': account, 'amount_cents': amount}
                               for line, (account, amount) in enumerate(postings)], session=session)


def apply_business(db, session, payload):
    unit, operation_id = payload['unit'], payload['operation_id']
    if db.business_events.find_one({'unit': unit, 'business_id': payload.get('business_id')}, session=session):
        return 'Identificador comercial já confirmado por outra operação; revisão necessária'
    customer_id = payload.get('customer_id')
    if payload['kind'] in ('customer.create', 'prazo.receive','customer.limit'):
        from desktop.business_rules import identifier
        try:
            identifier(customer_id)
        except BusinessError as exc:
            return str(exc)
    exists = db.customers.find_one({'unit': unit, 'customer_id': customer_id}, session=session) is not None
    try:
        postings = plan(payload, cash_cents=balance(db, session, unit, 'cash'),
                        debt_cents=balance(db, session, unit, 'receivable/' + str(customer_id)),
                        customer_exists=exists)
    except BusinessError as exc:
        return str(exc)
    reason = operational_effect(db, session, payload)
    if reason:
        return reason
    if payload['kind'] == 'prazo.receive':
        reference = payload['payment_reference'].strip().casefold()
        if db.payment_refs.find_one({'unit': unit, 'reference': reference}, session=session):
            return 'Recibo já utilizado; recebimento duplicado exige revisão'
        db.payment_refs.insert_one({'unit': unit, 'reference': reference, 'operation_id': operation_id}, session=session)
    if payload['kind'] == 'customer.create':
        if exists or db.customers.find_one({'unit': unit, 'name_key': payload['name'].casefold()}, session=session):
            return 'Cliente já registrado; revisão necessária'
        db.customers.insert_one({'unit': unit, 'customer_id': customer_id, 'name': payload['name'],
                                 'name_key': payload['name'].casefold(), 'operation_id': operation_id,'version':1,'credit_limit_cents':0}, session=session)
    if payload['kind']=='prazo.receive':
        db.customers.update_one({'unit':unit,'customer_id':customer_id},{'$inc':{'version':1}},session=session)
    post(db, session, unit, operation_id, postings)
    db.business_events.insert_one({'unit': unit, 'business_id': payload['business_id'],
                                   'operation_id': operation_id, 'payload': payload}, session=session)
    return None


def cash_guard(db, session, unit, payload):
    from desktop.business_rules import identifier
    control = db.unit_state.find_one({'_id': unit}, session=session) or {}
    if not control.get('cash_control_enabled'):
        return None
    try:
        identifier(payload.get('cash_shift_id'))
    except BusinessError:
        return 'Operação exige vínculo com um caixa aberto'
    active = db.cash_shifts.find_one({'unit': unit, 'shift_id': payload['cash_shift_id'], 'status': 'open'}, session=session)
    return None if active else 'Caixa encerrado, alterado ou em revisão; revisão obrigatória'


def operational_effect(db, session, payload):
    unit, kind = payload['unit'], payload['kind']
    if kind in ('customer.limit','prazo.receive'):
        customer=db.customers.find_one({'unit':unit,'customer_id':payload['customer_id']},session=session)
        version=payload.get('base_version') if kind=='customer.limit' else payload.get('customer_version')
        if not customer or customer.get('version',1)!=version:return 'Versão do cliente divergente; revisão obrigatória'
        if kind=='customer.limit':
            db.customers.update_one({'_id':customer['_id']},{'$set':{'credit_limit_cents':payload['limit_cents'],'approved_limit':True},'$inc':{'version':1}},session=session)
    if kind == 'order.status':
        from desktop.orders import TRANSITIONS
        order=db.sales.find_one({'unit':unit,'sale_id':payload['sale_id']},session=session)
        if not order or order.get('order_version',1)!=payload['base_version'] or TRANSITIONS.get(order.get('status','received'))!=payload['status']:
            return 'Pedido alterado ou transição inválida; revisão obrigatória'
        db.sales.update_one({'_id':order['_id']},{'$set':{'status':payload['status']},'$inc':{'order_version':1}},session=session)
    elif kind=='catalog.upsert':
        stock=db.stock.find_one({'unit':unit,'sku':payload['sku']},session=session)
        if (stock and stock['version']!=payload['base_version']) or (not stock and payload['base_version']!=0):
            return 'Produto alterado; revisão de versão obrigatória'
        fields={key:payload[key] for key in ('name','description','category','price_cents','prep_time','available')}
        if stock:db.stock.update_one({'_id':stock['_id']},{'$set':fields,'$inc':{'version':1}},session=session)
        else:db.stock.insert_one({'unit':unit,'sku':payload['sku'],'quantity':0,'version':1,**fields},session=session)
    elif kind == 'stock.adjust':
        stock = db.stock.find_one({'unit': unit, 'sku': payload['sku']}, session=session)
        if not stock or stock['version'] != payload['base_version'] or stock['quantity'] + payload['delta'] < 0:
            return 'Versão/quantidade de estoque divergente; ajuste exige revisão'
        db.stock.update_one({'_id': stock['_id'], 'version': stock['version']},
                            {'$inc': {'quantity': payload['delta'], 'version': 1}}, session=session)
    elif kind == 'cash.open':
        active = db.cash_shifts.find_one({'unit': unit, 'status': {'$in': ['open', 'needs_review']}}, session=session)
        previous = db.cash_shifts.find_one({'unit': unit, 'shift_id': payload['shift_id']}, session=session)
        if active or previous:
            return 'Já existe caixa aberto, em revisão ou turno com esse identificador'
        db.cash_shifts.insert_one({'unit': unit, 'shift_id': payload['shift_id'], 'status': 'open',
                                   'opening_cents': payload['counted_cents'], 'open_operation_id': payload['operation_id']}, session=session)
        db.unit_state.update_one({'_id': unit}, {'$set': {'cash_control_enabled': True}}, session=session)
    elif kind=='cash.reconcile':
        active=db.cash_shifts.find_one({'unit':unit,'shift_id':payload['shift_id'],'status':'needs_review'},session=session)
        if not active:return 'Conciliação exige turno com diferença pendente'
        db.cash_shifts.update_one({'_id':active['_id']},{'$set':{'status':'closed','reconcile_operation_id':payload['operation_id'],'reconciled_cents':payload['counted_cents']}},session=session)
    elif kind == 'cash.close':
        active = db.cash_shifts.find_one({'unit': unit, 'shift_id': payload['shift_id'], 'status': 'open'}, session=session)
        if not active:
            return 'Caixa não está aberto ou foi alterado'
        status = 'closed' if payload['expected_cents'] == payload['counted_cents'] else 'needs_review'
        db.cash_shifts.update_one({'_id': active['_id']}, {'$set': {'status': status,
                                  'expected_cents': payload['expected_cents'], 'counted_cents': payload['counted_cents'],
                                  'close_operation_id': payload['operation_id']}}, session=session)
    elif kind in ('cash.withdraw', 'expense.create', 'prazo.receive'):
        return cash_guard(db, session, unit, payload)
    return None
