import os
from contextlib import closing
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from desktop.local_api import create_local_app
from desktop.offline_store import OfflineJournal, OfflineError
from desktop.snapshots import apply_page, catalog, cursor, pull_once
from desktop.windows_secrets import save_secret, load_secret

TOKEN = 'local-session-' + 'x' * 32
HEADERS = {'Authorization': 'Bearer ' + TOKEN}


class LocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'journal.sqlite'
        self.journal = OfflineJournal(self.path, 'runner')

    def page(self, sku='lanche', done=True):
        return {'unit': 'runner', 'generation': 'generation-a', 'items': [
            {'sku': sku, 'quantity': 10, 'price_cents': 1000, 'version': 1}],
            'done': done, 'next_cursor': None if done else 'generation-a:100', 'created_at': '2026-11-18'}

    def test_snapshot_resume_and_atomic_publish(self):
        apply_page(self.journal, self.page('old'), None)
        apply_page(self.journal, self.page('new', False), None)
        reopened = OfflineJournal(self.path, 'runner')
        self.assertEqual(catalog(reopened)[0]['sku'], 'old')
        self.assertEqual(cursor(reopened), 'generation-a:100')
        pull_once(reopened, lambda c: self.page('last'))
        self.assertEqual([r['sku'] for r in catalog(reopened)], ['last', 'new'])
        self.assertIsNone(cursor(reopened))

    def test_bad_page_rolls_back_items_and_cursor(self):
        page = self.page(done=False)
        page['items'].append({'sku': 'bad'})
        with self.assertRaises(OfflineError):
            apply_page(self.journal, page, None)
        self.assertEqual(catalog(self.journal), [])
        self.assertIsNone(cursor(self.journal))
        wrong = self.page(); wrong['unit'] = 'gym-londres'
        with self.assertRaises(OfflineError):
            apply_page(self.journal, wrong, None)

    def test_offline_sale_restart_reconnect_and_response_retry(self):
        apply_page(self.journal, self.page(), None)
        body = {'operation_id': str(uuid.uuid4()), 'sale_id': 'local-sale', 'items': [{'sku': 'lanche', 'quantity': 1}]}
        with TestClient(create_local_app(self.journal, TOKEN)) as client:
            first = client.post('/api/local/sales', headers=HEADERS, json=body)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(client.get('/api/local/status', headers=HEADERS).json()['pending'], 1)
        reopened = OfflineJournal(self.path, 'runner')
        class Transport:
            def __call__(self, event):
                return {**{k: event[k] for k in ('unit', 'operation_id', 'fingerprint')}, 'status': 'applied', 'receipt_id': 'receipt-demo'}
            def snapshot(inner, current):
                return self.page()
        with TestClient(create_local_app(reopened, TOKEN, Transport(), interval=100)) as client:
            self.assertEqual(client.post('/api/local/sales', headers=HEADERS, json=body).json()['already_exists'], True)
            client.post('/api/local/sync', headers=HEADERS)
            import time
            deadline=time.monotonic()+5
            while client.get('/api/local/status',headers=HEADERS).json()['synced']!=1 and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(client.get('/api/local/status', headers=HEADERS).json()['synced'], 1)
            self.assertEqual(len(client.get('/api/local/sales', headers=HEADERS).json()['items']), 1)
            changed = {**body, 'items': [{'sku': 'lanche', 'quantity': 2}]}
            self.assertEqual(client.post('/api/local/sales', headers=HEADERS, json=changed).status_code, 409)

    def test_snapshot_version_downgrade_rejected_and_restart_preserves_catalog(self):
        from desktop.snapshots import restart
        page = self.page()
        page['items'][0]['version'] = 3
        apply_page(self.journal, page, None)
        with self.assertRaises(OfflineError):
            apply_page(self.journal, self.page(), None)
        restart(self.journal)
        self.assertEqual(catalog(self.journal)[0]['version'], 3)

    def test_sync_errors_survive_restart_without_secret_text(self):
        class Unavailable:
            def __call__(self, event):
                raise TimeoutError('secret remote token')
            def snapshot(self, current):
                raise TimeoutError('secret remote token')
        with TestClient(create_local_app(self.journal, TOKEN, Unavailable(), interval=100)) as client:
            client.post('/api/local/sync', headers=HEADERS)
        with TestClient(create_local_app(OfflineJournal(self.path, 'runner'), TOKEN)) as client:
            events = client.get('/api/local/sync-history', headers=HEADERS).json()['items']
            self.assertGreaterEqual(len(events), 1)
            self.assertNotIn('secret remote token', str(events))

    def test_future_schema_refused_without_data_loss(self):
        self.journal.record_sale(sale_id='future-test', total_cents=1, payment_method='cash', items=[{'sku': 'a'}])
        with closing(self.journal._connect()) as db:
            db.execute('PRAGMA user_version = 999')
        with self.assertRaises(OfflineError):
            OfflineJournal(self.path, 'runner')
        with closing(self.journal._connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM local_sales').fetchone()[0], 1)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 999)

    def test_local_sale_requires_canonical_uuid(self):
        with TestClient(create_local_app(self.journal, TOKEN)) as client:
            for value in ('', 'bad', None):
                self.assertEqual(client.post('/api/local/sales', headers=HEADERS, json={'operation_id': value}).status_code, 422)
        self.assertEqual(self.journal.status()['pending'], 0)

    def test_local_auth_origin_and_host(self):
        with TestClient(create_local_app(self.journal, TOKEN)) as client:
            self.assertEqual(client.get('/api/local/status').status_code, 401)
            self.assertEqual(client.get('/api/local/status', headers={**HEADERS, 'Host': 'evil.example'}).status_code, 403)
            self.assertEqual(client.post('/api/local/sync', headers={**HEADERS, 'Origin': 'https://evil.example'}).status_code, 403)

    def test_sqlcipher_reopen_wrong_key_and_plaintext_denied(self):
        try:
            import sqlcipher3
        except ImportError:
            self.skipTest('SQLCipher integration runs in dedicated Linux job')
        path = Path(self.tmp.name) / 'encrypted.sqlite'
        journal = OfflineJournal(path, 'runner', encryption_key=b'k'*32)
        journal.record_sale(sale_id='secret-sale', total_cents=1000, payment_method='cash', items=[{'sku': 'secret-sku', 'quantity': 1}])
        self.assertEqual(OfflineJournal(path, 'runner', encryption_key=b'k'*32).status()['pending'], 1)
        with self.assertRaises(Exception):
            OfflineJournal(path, 'runner', encryption_key=b'z'*32)
        with self.assertRaises(sqlite3.DatabaseError):
            with closing(sqlite3.connect(path)) as db:
                db.execute('SELECT * FROM operations').fetchall()
        for file in path.parent.glob('encrypted.sqlite*'):
            self.assertNotIn(b'secret-sale', file.read_bytes())

    @unittest.skipUnless(os.name == 'nt', 'DPAPI requires Windows')
    def test_dpapi_round_trip_and_no_overwrite(self):
        file = Path(self.tmp.name) / 'secret.dpapi'
        save_secret(file, b'secret-token')
        self.assertNotIn(b'secret-token', file.read_bytes())
        self.assertEqual(load_secret(file), b'secret-token')
        with self.assertRaises(FileExistsError):
            save_secret(file, b'replacement')
