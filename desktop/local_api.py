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


def create_local_app(journal: OfflineJournal, session_token: str, transport=None, frontend=None, interval=10, require_shift=False, require_operator=False):
    if len(session_token) < 32:
        raise ValueError('Local session token must contain at least 32 characters')
    with closing(journal._connect()) as db:
        db.execute('CREATE TABLE IF NOT EXISTS sync_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, connection TEXT NOT NULL, message TEXT)')
    if require_shift:
        with closing(journal._connect()) as db:
            db.execute("UPDATE metadata SET value='1' WHERE key='cash_control_enabled'")
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
                if hasattr(transport, 'set_snapshot_operations'):
                    from desktop.inventory import pending_ids
                    transport.set_snapshot_operations(pending_ids(journal))
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
        if require_operator and request.url.path.startswith('/api/') and not request.url.path.startswith('/api/local/auth'):
            from desktop.auth import actor
            identity=actor(journal,request.cookies.get('ganoh_operator'))
            if not identity:
                return JSONResponse({'detail':'Entre com sua conta local'},status_code=401)
            request.state.actor=identity
            if identity['role']=='kitchen' and not (request.method=='POST' and request.url.path=='/api/local/commerce') and request.url.path not in ('/api/local/status','/api/local/catalog','/api/local/sync','/api/local/orders'):
                return JSONResponse({'detail':'Acesso restrito ao responsável financeiro'},status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        return response

    from desktop import auth
    from fastapi.responses import JSONResponse

    @app.get('/api/local/auth')
    def auth_state(request: Request):
        with closing(journal._connect()) as db:
            configured=db.execute('SELECT 1 FROM operators LIMIT 1').fetchone() is not None
        return {'required':require_operator,'configured':configured,'actor':auth.actor(journal,request.cookies.get('ganoh_operator'))}

    @app.post('/api/local/auth/setup')
    def setup(body:dict):
        try:
            auth.create(journal,body.get('username'),body.get('password'),first=True)
            token=auth.login(journal,body.get('username'),body.get('password'))
        except auth.AuthError as exc:
            raise HTTPException(409,str(exc))
        response=JSONResponse({'configured':True})
        response.set_cookie('ganoh_operator',token,httponly=True,samesite='strict',max_age=8*3600)
        return response

    @app.post('/api/local/auth/login')
    def login(body:dict):
        try: token=auth.login(journal,body.get('username'),body.get('password'))
        except auth.AuthError as exc: raise HTTPException(401,str(exc))
        response=JSONResponse({'authenticated':True})
        response.set_cookie('ganoh_operator',token,httponly=True,samesite='strict',max_age=8*3600)
        return response

    @app.post('/api/local/auth/logout')
    def logout(request:Request):
        auth.logout(journal,request.cookies.get('ganoh_operator'))
        response=JSONResponse({'authenticated':False}); response.delete_cookie('ganoh_operator')
        return response

    @app.post('/api/local/auth/accounts')
    def account(body:dict,request:Request):
        identity=auth.actor(journal,request.cookies.get('ganoh_operator'))
        if not identity or identity['role']!='owner': raise HTTPException(403,'Somente o proprietário cadastra usuários')
        try: actor_id=auth.create(journal,body.get('username'),body.get('password'),body.get('role'))
        except auth.AuthError as exc: raise HTTPException(409,str(exc))
        return {'actor_id':actor_id}

    def authorize_kind(request,kind):
        identity=getattr(request.state,'actor',None)
        if require_operator and (not identity or not auth.allowed(identity['role'],kind)):
            raise HTTPException(403,'Seu papel não permite esta operação')
        return identity

    def owner(request):
        identity=auth.actor(journal,request.cookies.get('ganoh_operator'))
        if not identity or identity['role']!='owner': raise HTTPException(403,'Somente o proprietário gerencia backup e acesso')
        return identity

    @app.post('/api/local/backup/export')
    def backup_export(body:dict,request:Request):
        owner(request)
        from desktop.backups import export
        from fastapi.responses import Response
        with lock:
            try: data=export(journal,body.get('passphrase'))
            except OfflineError as exc: raise HTTPException(409,str(exc))
        return Response(data,media_type='application/zip',headers={'Content-Disposition':'attachment; filename="ganoh-backup-encrypted.zip"'})

    @app.post('/api/local/backup/verify')
    async def backup_verify(request:Request):
        owner(request)
        import base64,json,uuid
        from desktop.backups import restore_isolated,MAX_BYTES
        chunks=[];length=0
        async for chunk in request.stream():
            length+=len(chunk)
            if length>90*1024*1024: raise HTTPException(413,'Arquivo excede o limite desta versão')
            chunks.append(chunk)
        try:
            body=json.loads(b''.join(chunks));data=base64.b64decode(body['archive'],validate=True)
            if len(data)>MAX_BYTES+16384:raise ValueError()
        except (ValueError,KeyError,TypeError):raise HTTPException(422,'Arquivo de recuperação inválido')
        root=journal.path.parent/'recovery'
        root.mkdir(exist_ok=True,mode=0o700)
        target=root/str(uuid.uuid4())
        with lock:
            try: restored=restore_isolated(data,body.get('passphrase'),target,journal.unit)
            except OfflineError as exc:raise HTTPException(409,str(exc))
            except OSError:raise HTTPException(409,'Não foi possível proteger a chave da cópia recuperada neste Windows')
        return {'verified':True,'unit':restored.unit,'pending':restored.status()['pending'],
                'sqlite_integrity':restored.status()['sqlite_integrity'],'active_database_changed':False}

    @app.get('/api/local/reports/ledger.csv')
    def report_ledger(request:Request):
        identity=getattr(request.state,'actor',None)
        if require_operator and (not identity or identity['role'] not in ('owner','cashier')):raise HTTPException(403,'Acesso financeiro necessário')
        from desktop.reports import ledger_csv
        from fastapi.responses import Response
        try: data=ledger_csv(journal)
        except OfflineError as exc:raise HTTPException(409,str(exc))
        return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="ganoh-ledger-local-provisional.csv"'})

    @app.get('/api/local/status')
    def status(request: Request):
        from desktop.operations import state as operational_state
        operational=operational_state(journal)
        if getattr(request.state,'actor',{}).get('role')=='kitchen': operational={}
        return {**journal.status(), **state, **operational, 'demo': True}

    @app.get('/api/local/sync-history')
    def sync_history():
        with closing(journal._connect()) as db:
            return {'items': [dict(row) for row in db.execute('SELECT * FROM sync_events ORDER BY sequence DESC LIMIT 100')]}

    @app.post('/api/local/snapshot/restart')
    def restart_snapshot():
        with lock:
            restart(journal)
        return {'restarted': True}

    @app.get('/api/local/commerce')
    def business_summary():
        from desktop.commerce import summary
        return summary(journal)

    @app.post('/api/local/commerce')
    def business_event(body: dict, request: Request):
        identity=authorize_kind(request,body.get('kind'))
        from desktop.commerce import record
        with lock:
            try:
                return record(journal, operation_id=body.get('operation_id'), kind=body.get('kind'), data=body.get('data'),actor=identity)
            except OfflineError as exc:
                raise HTTPException(409, str(exc))

    @app.get('/api/local/catalog')
    def products():
        return {'items': catalog(journal)}

    @app.get('/api/local/orders')
    def kitchen_orders():
        from desktop.orders import list_orders
        return {'items':list_orders(journal)}

    @app.get('/api/local/sales')
    def sales():
        with closing(journal._connect()) as db:
            rows = db.execute('SELECT operation_id,payload_json,state,last_error,created_at FROM operations ORDER BY sequence DESC LIMIT 100').fetchall()
        import json
        return {'items': [{**dict(r), 'payload': json.loads(r['payload_json']), 'payload_json': None} for r in rows]}

    @app.post('/api/local/sales')
    def sell(body: dict,request: Request):
        identity=authorize_kind(request,'sale.create')
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
                if payload['sale_id'] != body.get('sale_id') or expected != body.get('items') or payload.get('customer_name')!=body.get('customer_name') or payload['payment_method']!=body.get('payment_method','cash') or payload.get('customer_id')!=body.get('customer_id'):
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
                if entry.get('available') is False:raise HTTPException(409,'Produto indisponível no cardápio')
                if entry.get('blocked'):
                    raise HTTPException(409, 'Estoque em conflito; revisão obrigatória')
                if quantity > entry['quantity']:
                    raise HTTPException(409, 'Estoque do snapshot insuficiente')
                items.append({'sku': sku, 'quantity': quantity, 'base_version': entry['version'], 'name':entry.get('name',sku)})
                total += quantity * entry['price_cents']
            method=body.get('payment_method','cash')
            if method not in ('cash','prazo'):raise HTTPException(422,'Forma de pagamento exige confirmação online e não está liberada')
            customer_version=None
            if method=='prazo':
                if not isinstance(body.get('customer_id'),str):raise HTTPException(422,'Cliente identificado obrigatório para prazo')
                with closing(journal._connect()) as db:
                    row=db.execute('SELECT version FROM customers WHERE customer_id=?',(body['customer_id'],)).fetchone()
                    customer_version=row['version'] if row else None
            try:
                return journal.record_sale(sale_id=body.get('sale_id'), operation_id=body.get('operation_id'),
                                           total_cents=total, items=items, payment_method=method,customer_id=body.get('customer_id'),customer_version=customer_version,
                                           cash_shift_id=(status(request)['active_shift'] or {}).get('shift_id'),actor=identity,customer_name=body.get('customer_name'))
            except OfflineError as exc:
                raise HTTPException(409, str(exc))

    @app.post('/api/local/sync')
    def sync(request:Request):
        synchronize()
        return status(request)

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
