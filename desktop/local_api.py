"""Loopback-only demo API; no import of production server or environment files."""
import secrets
import threading
from contextlib import asynccontextmanager, closing
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from desktop.offline_store import OfflineJournal, OfflineError
from desktop.snapshots import catalog, pull_once, restart
from desktop.sync_worker import sync_once


def create_local_app(journal: OfflineJournal, session_token: str, transport=None, frontend=None, interval=10):
    if len(session_token) < 32:
        raise ValueError('Local session token must contain at least 32 characters')
    with closing(journal._connect()) as db:
        db.execute('CREATE TABLE IF NOT EXISTS sync_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, connection TEXT NOT NULL, message TEXT)')
    lock = threading.Lock()
    stop = threading.Event()
    state = {'connection': 'offline', 'last_error': None}

    def remember():
        from datetime import datetime, timezone
        with closing(journal._connect()) as db:
            db.execute('INSERT INTO sync_events(created_at,connection,message) VALUES(?,?,?)',
                       (datetime.now(timezone.utc).isoformat(), state['connection'], state['last_error']))

    def synchronize():
        with lock:
            if transport is None:
                state.update(connection='offline', last_error='Dispositivo sem servidor de homologação configurado')
                return
            try:
                result = sync_once(journal, transport)
                # Finish/resume a bounded generation; failure keeps durable cursor.
                for _ in range(11):
                    if pull_once(journal, transport.snapshot):
                        break
                state.update(connection='online', last_error=None if not result['retryable'] else 'Operações aguardam confirmação')
            except Exception:
                # Do not expose URLs, credentials or arbitrary remote error bodies.
                state.update(connection='offline', last_error='Sincronização interrompida; dados preservados para nova tentativa')
            remember()

    def worker():
        while not stop.is_set():
            synchronize()
            stop.wait(interval)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=worker, daemon=True, name='ganoh-sync')
        thread.start()
        yield
        stop.set()
        thread.join(timeout=20)

    app = FastAPI(lifespan=lifespan)

    @app.middleware('http')
    async def authorize(request: Request, call_next):
        from fastapi.responses import JSONResponse
        host = request.headers.get('host', '').split(':')[0]
        origin = request.headers.get('origin')
        if host not in ('127.0.0.1', 'localhost', 'testserver'):
            return JSONResponse({'detail': 'Loopback host required'}, status_code=403)
        if origin and origin != 'http://' + request.headers.get('host', ''):
            return JSONResponse({'detail': 'Cross-origin request rejected'}, status_code=403)
        supplied = request.headers.get('authorization', '')
        if request.url.path.startswith('/api/') and not secrets.compare_digest(supplied, 'Bearer ' + session_token):
            return JSONResponse({'detail': 'Local session required'}, status_code=401)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        return response

    @app.get('/api/local/status')
    def status():
        return {**journal.status(), **state, 'demo': True}

    @app.get('/api/local/sync-history')
    def sync_history():
        with closing(journal._connect()) as db:
            return {'items': [dict(row) for row in db.execute('SELECT * FROM sync_events ORDER BY sequence DESC LIMIT 100')]}

    @app.post('/api/local/snapshot/restart')
    def restart_snapshot():
        with lock:
            restart(journal)
        return {'restarted': True}

    @app.get('/api/local/catalog')
    def products():
        return {'items': catalog(journal)}

    @app.get('/api/local/sales')
    def sales():
        with closing(journal._connect()) as db:
            rows = db.execute('SELECT operation_id,payload_json,state,last_error,created_at FROM operations ORDER BY sequence DESC LIMIT 100').fetchall()
        import json
        return {'items': [{**dict(r), 'payload': json.loads(r['payload_json']), 'payload_json': None} for r in rows]}

    @app.post('/api/local/sales')
    def sell(body: dict):
        import uuid
        try:
            if str(uuid.UUID(body['operation_id'])) != body['operation_id']:
                raise ValueError()
        except (ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(422, 'Identificador UUID estável obrigatório')
        with lock:
            with closing(journal._connect()) as db:
                old = db.execute('SELECT operation_id,payload_json,fingerprint,state FROM operations WHERE operation_id=?', (body.get('operation_id'),)).fetchone()
            if old:
                import json
                payload = json.loads(old['payload_json'])
                expected = [{'sku': i['sku'], 'quantity': i['quantity']} for i in payload['items']]
                if payload['sale_id'] != body.get('sale_id') or expected != body.get('items'):
                    raise HTTPException(409, 'Identificador reutilizado com dados diferentes')
                return {'operation_id': old['operation_id'], 'fingerprint': old['fingerprint'], 'state': old['state'], 'already_exists': True}
            items_by_sku = {item['sku']: item for item in catalog(journal)}
            selections = body.get('items')
            if not isinstance(selections, list) or not selections:
                raise HTTPException(422, 'Selecione itens do catálogo sincronizado')
            items, total, seen = [], 0, set()
            for selection in selections:
                if not isinstance(selection, dict):
                    raise HTTPException(422, 'Item inválido')
                sku, quantity = selection.get('sku'), selection.get('quantity')
                if not isinstance(sku, str) or sku in seen or sku not in items_by_sku or type(quantity) is not int or quantity < 1:
                    raise HTTPException(422, 'Item ou quantidade inválida')
                seen.add(sku)
                entry = items_by_sku[sku]
                if quantity > entry['quantity']:
                    raise HTTPException(409, 'Estoque do snapshot insuficiente')
                items.append({'sku': sku, 'quantity': quantity, 'base_version': entry['version']})
                total += quantity * entry['price_cents']
            try:
                return journal.record_sale(sale_id=body.get('sale_id'), operation_id=body.get('operation_id'),
                                           total_cents=total, items=items, payment_method='cash')
            except OfflineError as exc:
                raise HTTPException(409, str(exc))

    @app.post('/api/local/sync')
    def sync():
        synchronize()
        return status()

    if frontend:
        root = Path(frontend).resolve()
        @app.get('/{path:path}')
        def asset(path: str):
            file = (root / path).resolve()
            if not file.is_relative_to(root):
                raise HTTPException(404)
            if not file.is_file():
                file = root / 'index.html'
            if not file.is_file():
                raise HTTPException(503, 'React build unavailable')
            return FileResponse(file)
    return app
