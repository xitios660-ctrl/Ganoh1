"""Same-origin production entrypoint; do not open the business app before migration."""
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

def _frontend_build() -> Path:
    override = os.environ.get('FRONTEND_BUILD_DIR')
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / 'frontend' / 'build'


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

    build = _frontend_build()

    class SPAFiles(StaticFiles):
        """Serve CRA assets; unknown extension-less paths fall back to index.html (SPA deep links)."""

        async def get_response(self, path, scope):
            # Never treat API as static / SPA — leave a real 404 for unmatched /api/*.
            if path == 'api' or path.startswith('api/') or path == 'healthz':
                raise StarletteHTTPException(status_code=404)
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404 or '.' in Path(path).name:
                    raise
                index = build / 'index.html'
                if not index.is_file():
                    raise
                return FileResponse(index, headers={'Cache-Control': 'no-cache'})

    # Mount last so /api/* and /healthz registered above win.
    app.mount('/', SPAFiles(directory=build, html=True), name='frontend')
