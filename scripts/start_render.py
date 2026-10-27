"""Supervise one API process and one loopback-only Baileys process."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

# Keep suspension separate from migration and the business application. In this
# mode no database client, recovery job, scheduler or WhatsApp process is started.
# To resume, set GANOH_SERVICE_SUSPENDED=false and deploy this same revision.
if os.environ.get('GANOH_SERVICE_SUSPENDED', 'false').lower() == 'true':
    import json
    import uvicorn

    notice = """<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sistema temporariamente suspenso</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#101827;
color:#f8fafc;font:17px/1.6 system-ui,sans-serif}main{max-width:520px;margin:24px;
padding:40px;background:#1e293b;border-radius:20px;text-align:center}h1{font-size:28px;
line-height:1.25}p{color:#cbd5e1}</style></head><body><main role="alert">
<h1>Sistema temporariamente suspenso</h1><p>O acesso está suspenso por pendência de pagamento.</p>
<p>Entre em contato com o responsável para regularização e reativação.</p>
</main></body></html>"""

    async def suspended_app(scope, receive, send):
        if scope['type'] == 'websocket':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if scope['type'] != 'http':
            return
        path = scope.get('path', '/')
        healthy = path == '/healthz' and scope.get('method') in ('GET', 'HEAD')
        api = path == '/api' or path.startswith('/api/')
        if healthy:
            body = b'{"status":"suspended"}'
        elif api:
            body = json.dumps({'code': 'SERVICE_SUSPENDED',
                               'detail': 'Sistema suspenso por pendência de pagamento.'}).encode()
        else:
            body = notice.encode('utf-8')
        headers = [(b'content-type', b'application/json' if healthy or api else b'text/html; charset=utf-8'),
                   (b'cache-control', b'no-store, max-age=0'),
                   (b'x-content-type-options', b'nosniff'),
                   (b'x-robots-tag', b'noindex, nofollow')]
        await send({'type': 'http.response.start', 'status': 200 if healthy else 503,
                    'headers': headers})
        await send({'type': 'http.response.body',
                    'body': b'' if scope.get('method') == 'HEAD' else body})

    uvicorn.run(suspended_app, host='0.0.0.0', port=int(os.environ.get('PORT', '10000')),
                lifespan='off', access_log=False)
    sys.exit(0)

ROOT = Path(__file__).resolve().parent.parent
children = []
stopping = False

def stop(*_):
    global stopping
    stopping = True
    for child in children:
        if child.poll() is None:
            child.terminate()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    recovery = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() == 'true' and \
       os.environ.get('GANOH_RECOVERY_CUSTOMERS'):
        # Keep the maintenance page healthy during a slow Atlas import.
        recovery = subprocess.Popen([sys.executable, 'scripts/recover_pdf.py'], cwd=ROOT)
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and os.environ.get('WHATSAPP_PROVIDER') == 'baileys':
        children.append(subprocess.Popen(['node', 'server.mjs'], cwd=ROOT / 'whatsapp'))
    children.append(subprocess.Popen([sys.executable, '-m', 'uvicorn', 'render_app:app',
                                     '--host', '0.0.0.0', '--port', os.environ.get('PORT', '10000'),
                                     '--no-access-log'], cwd=ROOT / 'backend'))
    smoke = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_RECOVERY_SOURCE') == 'pdf':
        smoke = subprocess.Popen([sys.executable, 'scripts/smoke_render.py'], cwd=ROOT)
    e2e = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_E2E_ONCE', 'false').lower() == 'true':
        e2e = subprocess.Popen([sys.executable, 'scripts/e2e_production.py'], cwd=ROOT)
    routing_test = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_STORE_ROUTING_TEST_ONCE', 'false').lower() == 'true':
        routing_test = subprocess.Popen([sys.executable, 'scripts/store_routing_e2e.py'], cwd=ROOT)
    value_audit = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_VALUE_AUDIT_ONCE', 'false').lower() == 'true':
        value_audit = subprocess.Popen([sys.executable, 'scripts/value_audit_e2e.py'], cwd=ROOT)
    cashflow_export = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_CASHFLOW_EXPORT_ONCE', 'false').lower() == 'true':
        cashflow_export = subprocess.Popen([sys.executable, 'scripts/export_cashflow_snapshot.py'], cwd=ROOT)
    gym_debug = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_GYM_DEBUG_ONCE', 'false').lower() == 'true':
        gym_debug = subprocess.Popen([sys.executable, 'scripts/debug_gym_today.py'], cwd=ROOT)
    prazo_named_audit = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_PRAZO_NAMED_AUDIT_ONCE', 'false').lower() == 'true':
        prazo_named_audit = subprocess.Popen([sys.executable, 'scripts/debug_prazo_named_customers.py'], cwd=ROOT)
    security_rollback = None
    if os.environ.get('MIGRATION_PENDING', 'true').lower() != 'true' and \
       os.environ.get('GANOH_SECURITY_DUPLICATE_ROLLBACK_ONCE', 'false').lower() == 'true':
        security_rollback = subprocess.Popen([sys.executable, 'scripts/rollback_security_duplicate_payment.py'], cwd=ROOT)
    while not stopping and all(child.poll() is None for child in children):
        if recovery and recovery.poll() is not None:
            print('GANOH recovery process finished' if recovery.returncode == 0 else
                  'GANOH recovery process failed; maintenance remains active', flush=True)
            recovery = None
        if smoke and smoke.poll() is not None:
            print('GANOH read-only smoke finished' if smoke.returncode == 0 else
                  'GANOH read-only smoke failed', flush=True)
            smoke = None
        if e2e and e2e.poll() is not None:
            print('GANOH full E2E finished' if e2e.returncode == 0 else
                  'GANOH full E2E failed', flush=True)
            e2e = None
        if routing_test and routing_test.poll() is not None:
            print('GANOH store routing test finished' if routing_test.returncode == 0 else
                  'GANOH store routing test failed', flush=True)
            routing_test = None
        if value_audit and value_audit.poll() is not None:
            print('GANOH value audit finished' if value_audit.returncode == 0 else
                  'GANOH value audit failed', flush=True)
            value_audit = None
        if cashflow_export and cashflow_export.poll() is not None:
            print('GANOH cashflow export finished' if cashflow_export.returncode == 0 else
                  'GANOH cashflow export failed', flush=True)
            cashflow_export = None
        if gym_debug and gym_debug.poll() is not None:
            print('GANOH GYM debug finished' if gym_debug.returncode == 0 else
                  'GANOH GYM debug failed', flush=True)
            gym_debug = None
        if prazo_named_audit and prazo_named_audit.poll() is not None:
            print('GANOH prazo named audit finished' if prazo_named_audit.returncode == 0 else
                  'GANOH prazo named audit failed', flush=True)
            prazo_named_audit = None
        if security_rollback and security_rollback.poll() is not None:
            print('GANOH Security duplicate-payment rollback finished' if security_rollback.returncode == 0 else
                  'GANOH Security duplicate-payment rollback failed', flush=True)
            security_rollback = None
        time.sleep(0.5)
    failed = any(child.poll() not in (None, 0) for child in children)
finally:
    if 'recovery' in locals() and recovery and recovery.poll() is None:
        recovery.terminate()
    if 'smoke' in locals() and smoke and smoke.poll() is None:
        smoke.terminate()
    if 'e2e' in locals() and e2e and e2e.poll() is None:
        e2e.terminate()
    if 'routing_test' in locals() and routing_test and routing_test.poll() is None:
        routing_test.terminate()
    if 'value_audit' in locals() and value_audit and value_audit.poll() is None:
        value_audit.terminate()
    if 'cashflow_export' in locals() and cashflow_export and cashflow_export.poll() is None:
        cashflow_export.terminate()
    if 'gym_debug' in locals() and gym_debug and gym_debug.poll() is None:
        gym_debug.terminate()
    if 'prazo_named_audit' in locals() and prazo_named_audit and prazo_named_audit.poll() is None:
        prazo_named_audit.terminate()
    if 'security_rollback' in locals() and security_rollback and security_rollback.poll() is None:
        security_rollback.terminate()
    stop()
    for child in children:
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
sys.exit(1 if failed else 0)
