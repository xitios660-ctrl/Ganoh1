"""Shared deterministic rules for the isolated commercial ledger (integer cents)."""
import unicodedata
import uuid

KINDS = frozenset({'cash.deposit', 'cash.withdraw', 'expense.create', 'customer.create', 'prazo.receive', 'cash.open', 'cash.close', 'stock.adjust', 'order.status', 'customer.limit', 'catalog.upsert', 'cash.reconcile'})


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
    if kind in ('cash.open', 'cash.close','cash.reconcile'):
        allowed |= {'shift_id', 'counted_cents'}
        if kind in ('cash.close','cash.reconcile'):
            allowed.add('expected_cents')
        if kind=='cash.reconcile':allowed.add('description')
    elif kind == 'catalog.upsert':
        allowed |= {'sku','name','description','category','price_cents','prep_time','available','base_version'}
    elif kind == 'customer.limit':
        allowed |= {'customer_id','limit_cents','base_version','description'}
    elif kind == 'order.status':
        allowed |= {'sale_id','status','base_version'}
    elif kind == 'stock.adjust':
        allowed |= {'sku', 'delta', 'base_version', 'description'}
    else:
        allowed |= {'customer_id', 'name'} if kind == 'customer.create' else {'amount_cents', 'description'}
    if kind in ('cash.withdraw', 'expense.create', 'prazo.receive'):
        allowed.add('cash_shift_id')
    if kind == 'prazo.receive':
        allowed |= {'customer_id', 'payment_method', 'payment_reference', 'customer_version'}
    if set(payload) - allowed:
        raise BusinessError('Campos comerciais não suportados')
    identifier(payload.get('business_id'))
    if kind=='catalog.upsert':
        if (not isinstance(payload.get('sku'),str) or not 1<=len(payload['sku'])<=100
            or not isinstance(payload.get('name'),str) or not 1<=len(payload['name'].strip())<=120
            or not isinstance(payload.get('description'),str) or len(payload['description'])>1000
            or not isinstance(payload.get('category'),str) or not 1<=len(payload['category'].strip())<=100
            or type(payload.get('price_cents')) is not int or not 0<=payload['price_cents']<=9_000_000_000_000
            or type(payload.get('prep_time')) is not int or not 1<=payload['prep_time']<=240
            or type(payload.get('available')) is not bool or type(payload.get('base_version')) is not int or payload['base_version']<0):
            raise BusinessError('Produto exige SKU, nome, categoria, preço em centavos, disponibilidade e versão válidos')
        return []
    if kind == 'customer.limit':
        identifier(payload.get('customer_id'))
        if (type(payload.get('limit_cents')) is not int or not 0<=payload['limit_cents']<=9_000_000_000_000
                or type(payload.get('base_version')) is not int or payload['base_version']<1
                or not isinstance(payload.get('description'),str) or not 3<=len(payload['description'].strip())<=200):
            raise BusinessError('Limite exige valor inteiro, versão e motivo')
        if not customer_exists or debt_cents>payload['limit_cents']:
            raise BusinessError('Cliente não existe ou limite é menor que a dívida atual')
        return []
    if kind == 'order.status':
        if (not isinstance(payload.get('sale_id'),str) or not 1<=len(payload['sale_id'])<=128
                or type(payload.get('base_version')) is not int or payload['base_version']<1
                or payload.get('status') not in ('preparing','ready','delivered')):
            raise BusinessError('Pedido, versão e estado válidos são obrigatórios')
        return []
    if kind in ('cash.open', 'cash.close','cash.reconcile'):
        identifier(payload.get('shift_id'))
        counted = payload.get('counted_cents')
        if type(counted) is not int or not 0 <= counted <= 9_000_000_000_000:
            raise BusinessError('Contagem deve ser não negativa, em centavos inteiros')
        if kind == 'cash.open' and counted != cash_cents:
            raise BusinessError('Contagem inicial difere do livro; registre suprimento/retirada com motivo antes de abrir')
        if kind in ('cash.close','cash.reconcile') and (type(payload.get('expected_cents')) is not int or payload['expected_cents'] != cash_cents):
            raise BusinessError('Saldo esperado do caixa mudou; confira novamente antes de fechar')
        if kind=='cash.reconcile':
            if not isinstance(payload.get('description'),str) or not 10<=len(payload['description'].strip())<=200:raise BusinessError('Conciliação exige motivo de 10 a 200 caracteres')
            return [('cash',counted-cash_cents),('cash_variance',cash_cents-counted)]
        return []
    if kind == 'stock.adjust':
        if (not isinstance(payload.get('sku'), str) or not 1 <= len(payload['sku']) <= 100
                or type(payload.get('delta')) is not int or not 1 <= abs(payload['delta']) <= 100000
                or type(payload.get('base_version')) is not int or payload['base_version'] < 0
                or not isinstance(payload.get('description'), str) or not 3 <= len(payload['description'].strip()) <= 200):
            raise BusinessError('Ajuste de estoque exige SKU, quantidade inteira, versão e motivo')
        return []
    if payload.get('cash_shift_id') is not None:
        identifier(payload['cash_shift_id'])
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
    if type(payload.get('customer_version')) is not int or payload['customer_version']<1:
        raise BusinessError('Versão do cliente obrigatória no recebimento')
    reference = payload.get('payment_reference')
    if not isinstance(reference, str) or not 3 <= len(reference.strip()) <= 100:
        raise BusinessError('Número de recibo obrigatório para impedir baixa duplicada')
    if not customer_exists or debt_cents < amount:
        raise BusinessError('Cliente inexistente ou recebimento acima da dívida; revisão necessária')
    # This increment accepts cash receipts only. PIX/card require bank confirmation.
    if payload.get('payment_method') != 'cash':
        raise BusinessError('Recebimento offline permitido somente em dinheiro nesta etapa')
    return [('cash', amount), ('receivable/' + payload['customer_id'], -amount)]
