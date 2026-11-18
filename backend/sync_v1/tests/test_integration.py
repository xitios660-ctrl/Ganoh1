"""Requires a disposable local replica set; never reads application env files."""
import hashlib
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from pymongo import MongoClient

from backend.sync_v1.service import create_app
from desktop.offline_store import OfflineJournal, _canonical
from desktop.sync_worker import sync_once


class Integration(unittest.TestCase):
    def setUp(self):
        # Local disposable test server: fail within 3s if the fixture is absent.
        # One client is shared by all concurrent requests and closed at cleanup.
        self.mongo = MongoClient('mongodb://127.0.0.1:27028/?directConnection=true', serverSelectionTimeoutMS=3000)
        self.db = self.mongo['ganoh_sync_test_' + uuid.uuid4().hex]
        self.addCleanup(self.mongo.close)
        self.addCleanup(lambda: self.mongo.drop_database(self.db.name))
        self.client = TestClient(create_app(self.db))
        self.addCleanup(self.client.close)
        for unit in ('runner', 'gym-londres'):
            self.db.devices.insert_one({'_id': unit, 'unit': unit, 'revoked': False, 'token_hash': hashlib.sha256(unit.encode()).hexdigest()})
            self.db.stock.insert_one({'unit': unit, 'sku': 'lanche', 'quantity': 10, 'price_cents': 1000, 'version': 1})
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def event(self, unit='runner', sale='sale-a', payment='cash'):
        journal = OfflineJournal(Path(self.temp.name) / (uuid.uuid4().hex + '.sqlite'), unit)
        journal.record_sale(sale_id=sale, total_cents=1000, payment_method=payment, items=[{'sku': 'lanche', 'quantity': 1, 'base_version': 1}])
        return journal, journal.pending()[0]

    def send(self, item, token=None):
        return self.client.post('/api/sync/v1/batch', headers={'Authorization': 'Bearer ' + (token or item['unit'])}, json={'operations': [item]})

    def test_lost_ack_restart_and_ten_retries(self):
        journal, item = self.event()
        def lost(event):
            self.assertEqual(self.send(event).status_code, 200)
            raise TimeoutError()
        self.assertEqual(sync_once(journal, lost)['retryable'], 1)
        journal = OfflineJournal(journal.path, 'runner')
        replies = [self.send(item).json()['results'][0] for _ in range(10)]
        self.assertEqual(len({r['receipt_id'] for r in replies}), 1)
        self.assertEqual(sync_once(journal, lambda e: self.send(e).json()['results'][0])['synced'], 1)
        self.assertEqual(self.db.sales.count_documents({}), 1)
        self.assertEqual(self.db.stock.find_one({'unit': 'runner'})['quantity'], 9)

    def test_hash_reuse_unit_and_revocation(self):
        _, item = self.event()
        self.assertEqual(self.send(item, 'gym-londres').status_code, 403)
        self.assertEqual(self.send(item).status_code, 200)
        item['payload']['total_cents'] = 2000
        self.assertEqual(self.send(item).status_code, 422)
        item['fingerprint'] = hashlib.sha256(_canonical(item['payload']).encode()).hexdigest()
        self.assertEqual(self.send(item).status_code, 409)
        self.db.devices.update_one({'_id': 'runner'}, {'$set': {'revoked': True}})
        self.assertEqual(self.send(item).status_code, 401)

    def test_simultaneous_units_and_duplicate_requests(self):
        _, a = self.event()
        _, b = self.event('gym-londres')
        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(lambda i: self.send(i).status_code, [a, b] * 8))
        self.assertEqual(set(statuses), {200})
        self.assertEqual(self.db.sales.count_documents({}), 2)
        self.assertEqual(self.db.inbox.count_documents({}), 2)

    def test_stock_and_payment_conflicts_are_durable(self):
        _, a = self.event()
        self.send(a)
        _, b = self.event(sale='sale-b')
        first = self.send(b).json()['results'][0]
        self.assertEqual(first['status'], 'conflict')
        self.assertEqual(first, self.send(b).json()['results'][0])
        _, payment = self.event('gym-londres', payment='prazo')
        self.assertEqual(self.send(payment).json()['results'][0]['status'], 'conflict')
        self.assertEqual(self.db.sales.count_documents({}), 1)

    def test_transaction_rolls_back_stock_when_sale_write_fails(self):
        from unittest.mock import patch
        _, item = self.event()
        original = self.db.sales.__class__.insert_one
        def fail(collection, *args, **kwargs):
            if collection.name == 'sales':
                raise RuntimeError('injected crash')
            return original(collection, *args, **kwargs)
        with patch.object(self.db.sales.__class__, 'insert_one', fail):
            with self.assertRaises(RuntimeError):
                self.send(item)
        self.assertEqual(self.db.stock.find_one({'unit': 'runner'})['quantity'], 10)
        self.assertEqual(self.db.inbox.count_documents({}), 0)
        self.assertEqual(self.send(item).json()['results'][0]['status'], 'applied')

    def test_same_sale_new_uuid_cannot_decrement_stock_twice(self):
        _, first = self.event()
        _, second = self.event()
        self.assertEqual(self.send(first).json()['results'][0]['status'], 'applied')
        second['payload']['items'][0]['base_version'] = 2
        second['fingerprint'] = hashlib.sha256(_canonical(second['payload']).encode()).hexdigest()
        self.assertEqual(self.send(second).json()['results'][0]['status'], 'conflict')
        self.assertEqual(self.db.stock.find_one({'unit': 'runner'})['quantity'], 9)
        self.assertEqual(self.db.sales.count_documents({}), 1)

    def test_unimplemented_payments_never_settle_on_replay(self):
        for method in ('prazo', 'pix', 'debit', 'credit'):
            _, item = self.event(sale=method, payment=method)
            first = self.send(item).json()['results'][0]
            self.assertEqual(first['status'], 'conflict')
            self.assertEqual(first, self.send(item).json()['results'][0])
        self.assertEqual(self.db.sales.count_documents({}), 0)
        self.assertEqual(self.db.stock.find_one({'unit': 'runner'})['quantity'], 10)

    def test_snapshot_immutable_pagination_unit_binding_and_resume(self):
        from desktop.snapshots import pull_once, catalog, cursor
        self.db.stock.insert_many([{'unit': 'runner', 'sku': f'item-{i:03}', 'quantity': 3, 'price_cents': 10, 'version': 1} for i in range(201)])
        journal, _ = self.event()
        def fetch(current):
            response = self.client.get('/api/sync/v1/snapshot', params={'cursor': current or ''}, headers={'Authorization': 'Bearer runner'})
            self.assertEqual(response.status_code, 200)
            return response.json()
        self.assertFalse(pull_once(journal, fetch))
        saved_cursor = cursor(journal)
        self.assertEqual(catalog(journal), [])
        self.db.stock.update_many({'unit': 'runner'}, {'$inc': {'version': 1, 'quantity': 10}})
        other = self.client.get('/api/sync/v1/snapshot', params={'cursor': saved_cursor}, headers={'Authorization': 'Bearer gym-londres'})
        self.assertEqual(other.status_code, 410)
        journal = OfflineJournal(journal.path, 'runner')
        self.assertFalse(pull_once(journal, fetch))
        self.assertTrue(pull_once(journal, fetch))
        self.assertEqual(len(catalog(journal)), 202)
        self.assertEqual({i['version'] for i in catalog(journal)}, {1})
        self.assertIsNone(cursor(journal))

    def test_conflict_review_is_authorized_audited_and_idempotent(self):
        _, item = self.event(payment='prazo')
        self.send(item)
        body = {'unit': 'runner', 'operation_id': item['operation_id'], 'review_id': str(uuid.uuid4()),
                'expected_revision': 0, 'decision': 'reject', 'reason': 'Pagamento não confirmado; análise do proprietário'}
        endpoint = '/api/sync/v1/conflicts/review'
        self.assertEqual(self.client.post(endpoint, json=body, headers={'Authorization': 'Bearer runner'}).status_code, 401)
        self.db.reviewers.insert_one({'_id': 'owner-demo', 'units': ['runner'], 'revoked': False,
                                     'token_hash': hashlib.sha256(b'owner-test').hexdigest()})
        headers = {'Authorization': 'Bearer owner-test'}
        first = self.client.post(endpoint, json=body, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), self.client.post(endpoint, json=body, headers=headers).json())
        self.assertEqual(self.db.review_events.count_documents({}), 1)
        self.assertEqual(self.db.sales.count_documents({}), 0)
        changed = {**body, 'review_id': str(uuid.uuid4())}
        self.assertEqual(self.client.post(endpoint, json=changed, headers=headers).status_code, 409)
        self.assertEqual(self.client.post(endpoint, json={**body, 'unit': 'gym-londres'}, headers=headers).status_code, 403)
        self.assertEqual(self.send(item).json()['results'][0]['status'], 'conflict')

    def test_local_api_restart_then_real_central_sync(self):
        from desktop.local_api import create_local_app
        from desktop.snapshots import apply_page
        local = OfflineJournal(Path(self.temp.name) / 'local-api.sqlite', 'runner')
        snapshot = self.client.get('/api/sync/v1/snapshot', headers={'Authorization': 'Bearer runner'}).json()
        apply_page(local, snapshot, None)
        token = 'local-test-' + 'x' * 32
        headers = {'Authorization': 'Bearer ' + token}
        body = {'operation_id': str(uuid.uuid4()), 'sale_id': 'real-central-test', 'items': [{'sku': 'lanche', 'quantity': 1}]}
        with TestClient(create_local_app(local, token)) as pc:
            self.assertEqual(pc.post('/api/local/sales', json=body, headers=headers).status_code, 200)
        reopened = OfflineJournal(local.path, 'runner')
        parent = self
        class Transport:
            def __call__(self, event):
                return parent.send(event).json()['results'][0]
            def snapshot(self, cursor):
                return parent.client.get('/api/sync/v1/snapshot', params={'cursor': cursor or ''}, headers={'Authorization': 'Bearer runner'}).json()
        with TestClient(create_local_app(reopened, token, Transport(), interval=100)) as pc:
            pc.post('/api/local/sync', headers=headers)
            self.assertEqual(pc.get('/api/local/status', headers=headers).json()['synced'], 1)
        self.assertEqual(self.db.sales.count_documents({}), 1)
        self.assertEqual(self.db.stock.find_one({'unit': 'runner'})['quantity'], 9)

    def test_production_database_rejected(self):
        with self.assertRaises(ValueError):
            create_app(self.mongo['ganoh_production'])
