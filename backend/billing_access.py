"""Reversible billing gate. Absolute UTC deadline; never reads or writes business data."""
import json
import os
import posixpath
import time
from datetime import datetime
from urllib.parse import unquote

MESSAGE = 'Acesso indisponível por falta de pagamento. Regularize o quanto antes.'


def restricted():
    return os.environ.get('GANOH_SERVICE_SUSPENDED', 'false').lower() == 'true'


def deadline():
    try:
        value = datetime.fromisoformat(os.environ.get('GANOH_GRACE_UNTIL', '').replace('Z', '+00:00'))
        return value.timestamp() if value.tzinfo else 0
    except (ValueError, OverflowError):
        return 0


def grace_active():
    return restricted() and time.time() < deadline()


def status():
    now = time.time()
    end = deadline()
    mode = 'normal' if not restricted() else ('grace' if now < end else 'suspended')
    return {'mode': mode, 'server_time': now, 'expires_at': end if restricted() else None,
            'manager_blocked': restricted(), 'financials_hidden': restricted()}


def normalized(path):
    return '/' + posixpath.normpath(unquote(path).replace('\\', '/')).lstrip('/').lower()


def blocked_during_grace(path):
    path = normalized(path)
    prefixes = ('/gestor', '/auth', '/api/gestor', '/api/auth', '/api/admin',
                '/api/live', '/api/cash', '/api/expenses', '/api/pix-adjustments',
                '/api/whatsapp', '/docs', '/redoc', '/openapi.json')
    if any(path == p or path.startswith(p + '/') for p in prefixes):
        return True
    if path.endswith('/live') or path.endswith('/history') or path.endswith('/stats'):
        return True
    if path.startswith('/api/prazo') and path != '/api/prazo/customers':
        return True
    return False


def redact(value):
    """Do not expose money or payment evidence in operational list responses."""
    private = {'total', 'price', 'amount', 'credit', 'paid_amount', 'partial_paid',
               'cash_received', 'change', 'change_amount', 'pix_proof', 'payment_proof',
               'proof_image', 'extracted_amount', 'total_prazo', 'balance', 'pix_analysis',
               'credit_used', 'previous_credit', 'new_credit', 'credit_message'}
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()
                if key not in private and not any(word in key for word in ('proof', 'receipt'))}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def page(title):
    return f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#101827;
color:#f8fafc;font:17px/1.6 system-ui}}main{{max-width:520px;margin:24px;padding:40px;
background:#1e293b;border-radius:20px;text-align:center}}a{{color:#fbbf24}}</style>
</head><body><main><h1>{title}</h1><p>{MESSAGE}</p><a href="/">Voltar ao início</a></main></body></html>'''


async def respond(scope, send, code, data, html=False):
    body = data.encode() if html else json.dumps(data, ensure_ascii=False).encode()
    await send({'type': 'http.response.start', 'status': code, 'headers': [
        (b'content-type', b'text/html; charset=utf-8' if html else b'application/json'),
        (b'cache-control', b'no-store, max-age=0'), (b'x-robots-tag', b'noindex, nofollow')]})
    await send({'type': 'http.response.body', 'body': b'' if scope.get('method') == 'HEAD' else body})


class BillingGate:
    def __init__(self, app=None):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            if self.app:
                return await self.app(scope, receive, send)
            return
        state = status()
        if scope['type'] == 'websocket' and restricted():
            return await send({'type': 'websocket.close', 'code': 1008})
        path = normalized(scope.get('path', '/'))
        if path == '/api/billing/status' and scope.get('method') in ('GET', 'HEAD'):
            return await respond(scope, send, 200, state)
        if path == '/healthz' and state['mode'] == 'suspended':
            return await respond(scope, send, 200, {'status': 'suspended'})
        blocked = state['mode'] == 'suspended' or (restricted() and blocked_during_grace(path))
        if blocked:
            code = 503 if state['mode'] == 'suspended' else 403
            if path.startswith('/api/') or path == '/api':
                return await respond(scope, send, code, {'code': 'SERVICE_SUSPENDED' if code == 503 else 'PAYMENT_REQUIRED', 'detail': MESSAGE})
            return await respond(scope, send, code, page('Sistema temporariamente suspenso' if code == 503 else 'Acesso bloqueado'), html=True)
        if not self.app:
            return await respond(scope, send, 503, {'detail': MESSAGE})
        # Remove monetary fields from kitchen lists, including requests made directly.
        sanitize = restricted() and (path == '/api/prazo/customers' or
            path == '/api/orders' or path.startswith('/api/orders/'))
        if sanitize:
            messages = []
            async def collect(message):
                messages.append(message)
            await self.app(scope, receive, collect)
            start = next(m for m in messages if m['type'] == 'http.response.start')
            body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
            try:
                data = redact(json.loads(body))
            except (ValueError, UnicodeDecodeError):
                return await respond(scope, send, 503, {'detail': 'Resposta indisponível'})
            return await respond(scope, send, start['status'], data)
        async def no_cache(message):
            if message['type'] == 'http.response.start' and restricted():
                message['headers'] = [(k, v) for k, v in message.get('headers', []) if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store')]
            await send(message)
        return await self.app(scope, receive, no_cache)
