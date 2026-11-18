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

    def test_production_database_rejected(self):
        with self.assertRaises(ValueError):
            create_app(self.mongo['ganoh_production'])
