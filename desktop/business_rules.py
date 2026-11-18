"""Shared deterministic rules for the isolated commercial ledger (integer cents)."""
import unicodedata
import uuid

KINDS = frozenset({'cash.deposit', 'cash.withdraw', 'expense.create', 'customer.create', 'prazo.receive'})


class BusinessError(ValueError):
    pass


def identifier(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise BusinessError('Identificador UUID canônico obrigatório')
    return value


def customer_name(value):
    if not isinstance(value, str):
        raise BusinessError('Nome de cliente obrigatório')
    value = ' '.join(unicodedata.normalize('NFKC', value).split())
    if not 1 <= len(value) <= 120:
        raise BusinessError('Nome de cliente inválido')
    return value


def plan(payload, *, cash_cents=0, debt_cents=0, customer_exists=False):
    """Return balanced immutable postings; never infer PIX/card settlement."""
    kind = payload.get('kind')
    if kind not in KINDS:
        raise BusinessError('Operação comercial não suportada')
    allowed = {'operation_id', 'unit', 'kind', 'business_id'}
    allowed |= {'customer_id', 'name'} if kind == 'customer.create' else {'amount_cents', 'description'}
    if kind == 'prazo.receive':
        allowed |= {'customer_id', 'payment_method', 'payment_reference'}
    if set(payload) - allowed:
        raise BusinessError('Campos comerciais não suportados')
    identifier(payload.get('business_id'))
    if kind == 'customer.create':
        identifier(payload.get('customer_id'))
        name = customer_name(payload.get('name'))
        if payload.get('name') != name:
            raise BusinessError('Normalize o nome antes de salvar')
        return []
    amount = payload.get('amount_cents')
    if type(amount) is not int or not 1 <= amount <= 9_000_000_000_000:
        raise BusinessError('Valor deve ser positivo, em centavos inteiros')
    description = payload.get('description')
    if not isinstance(description, str) or not 3 <= len(description.strip()) <= 200:
        raise BusinessError('Descrição entre 3 e 200 caracteres obrigatória')
    if kind == 'cash.deposit':
        return [('cash', amount), ('equity', -amount)]
    if kind in ('cash.withdraw', 'expense.create'):
        if cash_cents < amount:
            raise BusinessError('Saldo de caixa insuficiente; revisão necessária')
        return [('cash', -amount), ('expense' if kind == 'expense.create' else 'equity', amount)]
    identifier(payload.get('customer_id'))
    reference = payload.get('payment_reference')
    if not isinstance(reference, str) or not 3 <= len(reference.strip()) <= 100:
        raise BusinessError('Número de recibo obrigatório para impedir baixa duplicada')
    if not customer_exists or debt_cents < amount:
        raise BusinessError('Cliente inexistente ou recebimento acima da dívida; revisão necessária')
    # This increment accepts cash receipts only. PIX/card require bank confirmation.
    if payload.get('payment_method') != 'cash':
        raise BusinessError('Recebimento offline permitido somente em dinheiro nesta etapa')
    return [('cash', amount), ('receivable/' + payload['customer_id'], -amount)]
