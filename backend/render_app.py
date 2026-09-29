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

    build = _frontend_build()
    notice = ('<style>#ganoh-migration-notice{position:fixed;inset:0;z-index:2147483647;'
              'display:grid;place-items:center;background:rgba(8,12,20,.72);'
              'font-family:system-ui,sans-serif;color:white;padding:24px;text-align:center}'
              '#ganoh-migration-notice div{max-width:480px;padding:32px;border-radius:20px;'
              'background:#17202e;box-shadow:0 20px 70px #0009}'
              '#ganoh-migration-notice h1{font-size:25px;margin:0 0 12px}'
              '#ganoh-migration-notice p{line-height:1.5;margin:0}</style>'
              '<div id="ganoh-migration-notice" role="alert"><div>'
              '<h1>Ganoh em preparação</h1><p>A interface está publicada. '
              'O caixa, os pedidos e o WhatsApp estarão disponíveis após conectar '
              'e conferir o banco de dados.</p></div></div>')

    @app.api_route('/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
    async def pending_api(path: str):
        raise HTTPException(status_code=503, detail='Migração do banco pendente')

    @app.api_route('/{path:path}', methods=['POST', 'PUT', 'PATCH', 'DELETE'])
    async def pending_write(path: str):
        raise HTTPException(status_code=503, detail='Migração do banco pendente')

    @app.get('/{path:path}')
    async def pending_frontend(path: str):
        # Show the real built interface, with an unmistakable blocking notice.
        # No business API is mounted while migration is pending.
        asset = (build / path).resolve()
        if path and asset.is_file() and asset.is_relative_to(build.resolve()):
            return FileResponse(asset)
        if '.' in Path(path).name or not (build / 'index.html').is_file():
            raise HTTPException(status_code=404)
        html = (build / 'index.html').read_text(encoding='utf-8')
        return HTMLResponse(html.replace('</body>', notice + '</body>'),
                            headers={'Cache-Control': 'no-store'})
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
            if os.environ.get('GANOH_RECOVERY_SOURCE') == 'pdf':
                marker = await db.recovery_runs.find_one({'id': 'pdf-2026-09-28'})
                if not marker or marker.get('status') != 'verified':
                    raise HTTPException(status_code=503, detail='Recovery unverified')
        except HTTPException:
            raise
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
