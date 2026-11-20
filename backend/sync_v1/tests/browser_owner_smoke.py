"""Mobile Chromium + compiled owner UI + isolated central API (no deployment).
Build with REACT_APP_OWNER_PANEL=true and REACT_APP_SYNC_ORIGIN=https://central.example
into frontend/build-owner, then python -m backend.sync_v1.tests.browser_owner_smoke.
"""
import hashlib
import mimetypes
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlsplit, unquote

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from pymongo import MongoClient
from backend.sync_v1.service import create_app
from backend.sync_v1.owner_auth import provision
from desktop.offline_store import OfflineJournal


def main():
    mongo = MongoClient('mongodb://127.0.0.1:27028/?directConnection=true', serverSelectionTimeoutMS=3000)
    db = mongo['ganoh_sync_test_owner_browser_' + uuid.uuid4().hex]
    try:
        with TestClient(create_app(db, owner_origins=('https://owner.example',))) as central, tempfile.TemporaryDirectory() as directory:
            for unit in ('runner', 'gym-londres'):
                db.devices.insert_one({'_id': unit, 'unit': unit, 'revoked': False,
                                       'token_hash': hashlib.sha256(unit.encode()).hexdigest()})
                db.stock.insert_one({'unit': unit, 'sku': 'lanche', 'name': 'Lanche fictício',
                                     'quantity': 10, 'price_cents': 1000, 'version': 1})
                journal = OfflineJournal(Path(directory) / (unit + '.sqlite'), unit)
                journal.record_sale(sale_id='mobile-fixture', total_cents=1000, payment_method='cash',
                                    items=[{'sku': 'lanche', 'quantity': 1, 'base_version': 1}])
                response = central.post('/api/sync/v1/batch', headers={'Authorization': 'Bearer ' + unit},
                                        json={'operations': journal.pending()})
                assert response.json()['results'][0]['status'] == 'applied'
            provision(db, 'mobile-owner', 'Fixture-Owner-Password-2026', ['runner'])
            bundle = Path('frontend/build-owner').resolve()
            assert (bundle / 'index.html').is_file(), 'Build owner panel first'
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                try:
                    page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, device_scale_factor=1)
                    failures = []
                    page.on('pageerror', lambda error: failures.append(str(error)))
                    def route(request):
                        parsed = urlsplit(request.request.url)
                        if parsed.netloc == 'central.example':
                            response = central.request(request.request.method, request.request.url,
                                                       headers=request.request.all_headers(), content=request.request.post_data_buffer)
                            request.fulfill(status=response.status_code, headers=dict(response.headers), body=response.content)
                        elif parsed.netloc == 'owner.example':
                            path = (bundle / unquote(parsed.path).lstrip('/')).resolve()
                            if not path.is_relative_to(bundle):
                                request.abort(); return
                            if not path.is_file():
                                path = bundle / 'index.html'
                            request.fulfill(status=200, content_type=mimetypes.guess_type(str(path))[0] or 'application/octet-stream', body=path.read_bytes())
                        else:
                            failures.append('Unexpected network target: ' + parsed.netloc)
                            request.abort()
                    page.route('**/*', route)
                    page.goto('https://owner.example/')
                    page.get_by_label('Usuário do gestor').fill('mobile-owner')
                    page.get_by_label('Senha do gestor').fill('Fixture-Owner-Password-2026')
                    page.get_by_role('button', name='Entrar no gestor', exact=True).click()
                    page.get_by_text('Somente operações confirmadas no servidor.', exact=False).wait_for()
                    assert page.get_by_text('GYM LONDRES', exact=True).count() == 0
                    page.get_by_role('button', name='Ver estoque de RUNNER', exact=True).click()
                    page.get_by_text('Lanche fictício: 9', exact=False).wait_for()
                    assert page.get_by_text('Quantidade de operações ainda offline: desconhecida pelo servidor.', exact=True).is_visible()
                    page.get_by_label('Usuário da TV', exact=True).fill('mobile-tv-fixture')
                    page.get_by_label('Senha exclusiva da TV', exact=True).fill('Dedicated-TV-Fixture-2026')
                    page.get_by_label('RUNNER', exact=True).check()
                    page.get_by_role('button', name='Criar acesso da TV', exact=True).click()
                    revoke = page.get_by_role('button', name='Revogar mobile-tv-fixture', exact=True)
                    revoke.wait_for()
                    television = central.post('/api/sync/v1/tv/login', json={'username':'mobile-tv-fixture','password':'Dedicated-TV-Fixture-2026'})
                    assert television.status_code == 200
                    tv_headers = {'Authorization':'Bearer ' + television.json()['access_token']}
                    assert central.get('/api/sync/v1/tv/overview', headers=tv_headers).status_code == 200
                    assert central.post('/api/sync/v1/conflicts/review', headers=tv_headers, json={}).status_code == 401
                    revoke.click()
                    page.get_by_text('Revogado', exact=False).wait_for()
                    assert central.get('/api/sync/v1/tv/overview', headers=tv_headers).status_code == 401
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                    assert page.evaluate('Object.keys(localStorage)') == ['ganoh_theme']
                    assert page.evaluate('sessionStorage.length') == 0
                    page.screenshot(path='/tmp/ganoh-owner-mobile.png', full_page=True)
                    page.get_by_role('button', name='Sair', exact=True).click()
                    page.get_by_role('button', name='Entrar no gestor', exact=True).wait_for()
                    assert db.owner_sessions.count_documents({}) == 0
                    assert not failures, failures
                finally:
                    browser.close()
        print('PASS mobile Chromium: owner login, authorized unit only, confirmed stock, unknown offline count, logout; no persistent browser token')
    finally:
        mongo.drop_database(db.name)
        mongo.close()


if __name__ == '__main__':
    main()
