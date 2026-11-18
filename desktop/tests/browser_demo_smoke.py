"""Real Chromium + local HTTP + SQLCipher + disposable central MongoDB demo.
Run from repository root: python -m desktop.tests.browser_demo_smoke
Requires Playwright and a built desktop React bundle; never reads .env files.
"""
import hashlib
import secrets
import socket
import tempfile
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright
from pymongo import MongoClient
from backend.sync_v1.service import create_app
from desktop.local_api import create_local_app
from desktop.offline_store import OfflineJournal
from desktop.snapshots import apply_page


def main():
    # Disposable loopback fixture; short deadline makes missing fixtures fail fast.
    mongo = MongoClient('mongodb://127.0.0.1:27028/?directConnection=true', serverSelectionTimeoutMS=3000)
    db = mongo['ganoh_sync_test_browser_' + uuid.uuid4().hex]
    central = None
    try:
        central = TestClient(create_app(db))
        db.devices.insert_one({'_id': 'runner-browser-test', 'unit': 'runner', 'revoked': False,
                               'token_hash': hashlib.sha256(b'fixture-only').hexdigest()})
        db.stock.insert_one({'unit': 'runner', 'sku': 'lanche', 'name': 'Lanche demonstração', 'quantity': 10, 'price_cents': 1000, 'version': 1})
        online = threading.Event()
        class Transport:
            def __call__(self, operation):
                if not online.is_set():
                    raise TimeoutError('Fixture network disabled')
                response = central.post('/api/sync/v1/batch', json={'operations': [operation]}, headers={'Authorization': 'Bearer fixture-only'})
                response.raise_for_status()
                return response.json()['results'][0]
            def snapshot(self, current):
                if not online.is_set():
                    raise TimeoutError('Fixture network disabled')
                response = central.get('/api/sync/v1/snapshot', params={'cursor': current or ''}, headers={'Authorization': 'Bearer fixture-only'})
                response.raise_for_status()
                return response.json()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'demo.sqlite'
            key = secrets.token_bytes(32)
            token = secrets.token_hex(32)
            journal = OfflineJournal(path, 'runner', encryption_key=key)
            initial = central.get('/api/sync/v1/snapshot', headers={'Authorization': 'Bearer fixture-only'}).json()
            apply_page(journal, initial, None)
            def start():
                app = create_local_app(OfflineJournal(path, 'runner', encryption_key=key), token, Transport(),
                                       frontend=Path('frontend/build'), interval=100)
                listener = socket.socket()
                listener.bind(('127.0.0.1', 0)); listener.listen(128)
                origin = 'http://127.0.0.1:' + str(listener.getsockname()[1])
                server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
                thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
                thread.start()
                for _ in range(100):
                    if server.started:
                        return server, thread, listener, origin
                    time.sleep(.05)
                raise RuntimeError('Local server did not start')
            def stop(server, thread, listener):
                server.should_exit = True; thread.join(timeout=20); listener.close()
                if thread.is_alive():
                    raise RuntimeError('Local server did not stop')
            server, thread, listener, origin = start()
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
                    try:
                        def open_page(url):
                            page = browser.new_page(viewport={'width': 1200, 'height': 1000})
                            def route(request):
                                if urlsplit(request.request.url).netloc == urlsplit(url).netloc:
                                    request.continue_(headers={**request.request.headers, 'Authorization': 'Bearer ' + token})
                                else:
                                    request.abort()
                            page.route('**/*', route)
                            page.goto(url + '/desktop-demo')
                            return page
                        page = open_page(origin)
                        page.get_by_label('Produto').select_option('lanche')
                        page.get_by_role('button', name='Salvar venda em dinheiro').click()
                        page.locator('li').filter(has_text='• Pendente').wait_for()
                        page.close()
                        stop(server, thread, listener)
                        server, thread, listener, origin = start()
                        page = open_page(origin)
                        page.locator('li').filter(has_text='• Pendente').wait_for()
                        online.set()
                        page.get_by_role('button', name='Sincronizar agora', exact=True).click()
                        page.locator('li').filter(has_text='• Sincronizada').wait_for()
                        assert db.sales.count_documents({}) == 1
                        assert db.stock.find_one({'unit': 'runner'})['quantity'] == 9
                        page.screenshot(path='/tmp/ganoh-desktop-demo.png', full_page=True)
                        page.close()
                    finally:
                        browser.close()
            finally:
                stop(server, thread, listener)
        print('PASS Chromium: save offline, stop/reopen backend, restore network, sync exactly one sale; screenshot /tmp/ganoh-desktop-demo.png')
    finally:
        if central:
            central.close()
        mongo.drop_database(db.name)
        mongo.close()


if __name__ == '__main__':
    main()
