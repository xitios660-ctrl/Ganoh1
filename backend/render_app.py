"""Same-origin production entrypoint; do not open the business app before migration."""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

if os.environ.get('MIGRATION_PENDING', 'true').lower() == 'true':
    app = FastAPI()

    @app.get('/healthz')
    async def pending_health():
        return {'status': 'maintenance', 'migration_pending': True}

    @app.api_route('/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def maintenance(path: str):
        return HTMLResponse('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
                            '<meta name="viewport" content="width=device-width,initial-scale=1">'
                            '<title>Ganoh</title><h1>Ganoh</h1>'
                            '<p>Estamos preparando o sistema. Volte em breve.</p></html>',
                            status_code=503, headers={'Retry-After': '300',
                                                     'Cache-Control': 'no-store'})
else:
    required = ('MONGO_URL', 'DB_NAME', 'GESTOR_PASSWORD', 'PRAZO_PASSWORD', 'CLEAR_DATA_PASSWORD')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError('Missing deployment settings: ' + ', '.join(missing))
    from server import app, db

    @app.get('/healthz')
    async def health():
        try:
            await db.command('ping')
        except Exception:
            raise HTTPException(status_code=503, detail='Database unavailable')
        return {'status': 'ok', 'migration_pending': False}

    build = Path(__file__).resolve().parent.parent / 'frontend' / 'build'

    class SPAFiles(StaticFiles):
        async def get_response(self, path, scope):
            if path == 'api' or path.startswith('api/'):
                raise HTTPException(status_code=404)
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404 or '.' in Path(path).name:
                    raise
                return FileResponse(build / 'index.html', headers={'Cache-Control': 'no-cache'})

    app.mount('/', SPAFiles(directory=build, html=True), name='frontend')
