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
    exists = db.customers.find_one({'unit': unit, 'customer_id': customer_id}, session=session) is not None
    try:
        postings = plan(payload, cash_cents=balance(db, session, unit, 'cash'),
                        debt_cents=balance(db, session, unit, 'receivable/' + str(customer_id)),
                        customer_exists=exists)
    except BusinessError as exc:
        return str(exc)
    if payload['kind'] == 'prazo.receive':
        reference = payload['payment_reference'].strip().casefold()
        if db.payment_refs.find_one({'unit': unit, 'reference': reference}, session=session):
            return 'Recibo já utilizado; recebimento duplicado exige revisão'
        db.payment_refs.insert_one({'unit': unit, 'reference': reference, 'operation_id': operation_id}, session=session)
    if payload['kind'] == 'customer.create':
        if exists or db.customers.find_one({'unit': unit, 'name_key': payload['name'].casefold()}, session=session):
            return 'Cliente já registrado; revisão necessária'
        db.customers.insert_one({'unit': unit, 'customer_id': customer_id, 'name': payload['name'],
                                 'name_key': payload['name'].casefold(), 'operation_id': operation_id}, session=session)
    post(db, session, unit, operation_id, postings)
    db.business_events.insert_one({'unit': unit, 'business_id': payload['business_id'],
                                   'operation_id': operation_id, 'payload': payload}, session=session)
    return None
