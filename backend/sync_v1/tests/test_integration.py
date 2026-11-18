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
        journal.record_sale(sale_id=sale, total_cents=1000, payment_method=('cash' if payment=='prazo' else payment), items=[{'sku': 'lanche', 'quantity': 1, 'base_version': 1}])
        item=journal.pending()[0]
        if payment=='prazo':
            # Malformed/unapproved incoming event for API-boundary tests.
            item['payload']['payment_method']='prazo'
            item['fingerprint']=hashlib.sha256(_canonical(item['payload']).encode()).hexdigest()
        return journal,item

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
        self.assertEqual({i['version'] for i in catalog(journal, projected=False)}, {1})
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

    def financial_event(self, kind, unit='runner', **data):
        from desktop.business_rules import KINDS
        from desktop.commerce import record
        self.db.devices.update_one({'_id': unit}, {'$set': {'permissions': list(KINDS)}})
        journal = OfflineJournal(Path(self.temp.name) / (uuid.uuid4().hex + '.sqlite'), unit)
        if kind=='prazo.receive' and 'customer_version' not in data:
            customer=self.db.customers.find_one({'unit':unit,'customer_id':data.get('customer_id')})
            data['customer_version']=customer.get('version',1) if customer else 1
        if kind in ('cash.withdraw', 'expense.create', 'prazo.receive'):
            # The caller supplies complete payloads for conflict scenarios.
            payload = {'operation_id': str(uuid.uuid4()), 'unit': unit, 'kind': kind,
                       'business_id': str(uuid.uuid4()), **data}
            return {'operation_id': payload['operation_id'], 'unit': unit, 'kind': kind,
                    'payload': payload, 'fingerprint': hashlib.sha256(_canonical(payload).encode()).hexdigest()}
        record(journal, operation_id=str(uuid.uuid4()), kind=kind,
               data={'business_id': str(uuid.uuid4()), **data})
        return journal.pending()[0]

    def test_commerce_lost_ack_no_duplicate_and_new_operation_same_business(self):
        from backend.sync_v1.commerce import balance
        deposit = self.financial_event('cash.deposit', amount_cents=1000, description='Entrada de teste')
        self.assertEqual(self.send(deposit).json()['results'][0]['status'], 'applied')
        for _ in range(10):
            self.assertEqual(self.send(deposit).json()['results'][0]['status'], 'already_applied')
        changed = {**deposit, 'operation_id': str(uuid.uuid4()), 'payload': dict(deposit['payload'])}
        changed['payload']['operation_id'] = changed['operation_id']
        changed['fingerprint'] = hashlib.sha256(_canonical(changed['payload']).encode()).hexdigest()
        self.assertEqual(self.send(changed).json()['results'][0]['status'], 'conflict')
        self.assertEqual(balance(self.db, None, 'runner', 'cash'), 1000)
        self.assertEqual(self.db.business_events.count_documents({}), 1)
        self.assertEqual(sum(r['amount_cents'] for r in self.db.ledger.find({})), 0)

    def test_two_devices_same_unit_cannot_overdraw_cash(self):
        from backend.sync_v1.commerce import balance
        from desktop.business_rules import KINDS
        self.send(self.financial_event('cash.deposit', amount_cents=1000, description='Suprimento teste'))
        self.db.devices.insert_one({'_id': 'runner-second', 'unit': 'runner', 'revoked': False,
                                   'permissions': list(KINDS), 'token_hash': hashlib.sha256(b'runner-second').hexdigest()})
        a = self.financial_event('cash.withdraw', amount_cents=800, description='Retirada um')
        b = self.financial_event('cash.withdraw', amount_cents=800, description='Retirada dois')
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(lambda: self.send(a).json()['results'][0]['status'])
            two = pool.submit(lambda: self.send(b, 'runner-second').json()['results'][0]['status'])
            self.assertEqual(sorted([one.result(), two.result()]), ['applied', 'conflict'])
        self.assertEqual(balance(self.db, None, 'runner', 'cash'), 200)
        self.assertEqual(balance(self.db, None, 'gym-londres', 'cash'), 0)

    def test_cash_receipt_duplicate_and_distinct_overpayment(self):
        from backend.sync_v1.commerce import balance
        customer_id = str(uuid.uuid4())
        customer = self.financial_event('customer.create', customer_id=customer_id, name='Cliente fictício')
        self.send(customer)
        # Historical debt fixture; there is no endpoint to invent debt.
        self.db.ledger.insert_many([{'unit': 'runner', 'operation_id': 'fixture', 'line': 0,
                                     'account': 'receivable/' + customer_id, 'amount_cents': 500},
                                    {'unit': 'runner', 'operation_id': 'fixture', 'line': 1,
                                     'account': 'revenue', 'amount_cents': -500}])
        receipt = self.financial_event('prazo.receive', customer_id=customer_id, amount_cents=300,
                                       description='Recebimento teste', payment_method='cash', payment_reference='receipt-a')
        self.assertEqual(self.send(receipt).json()['results'][0]['status'], 'applied')
        self.assertEqual(self.send(receipt).json()['results'][0]['status'], 'already_applied')
        extra = self.financial_event('prazo.receive', customer_id=customer_id, amount_cents=300,
                                     description='Recebimento duplicado distinto', payment_method='cash', payment_reference='receipt-b')
        self.assertEqual(self.send(extra).json()['results'][0]['status'], 'conflict')
        duplicate = self.financial_event('prazo.receive', customer_id=customer_id, amount_cents=100,
                                         description='Mesmo recibo outro UUID', payment_method='cash', payment_reference='RECEIPT-A')
        self.assertEqual(self.send(duplicate).json()['results'][0]['status'], 'conflict')
        self.assertEqual(balance(self.db, None, 'runner', 'receivable/' + customer_id), 200)
        self.assertEqual(balance(self.db, None, 'runner', 'cash'), 300)

    def test_financial_permission_and_atomic_rollback(self):
        from unittest.mock import patch
        event = self.financial_event('cash.deposit', amount_cents=100, description='Entrada teste')
        self.db.devices.update_one({'_id': 'runner'}, {'$set': {'permissions': []}})
        self.assertEqual(self.send(event).status_code, 403)
        self.db.devices.update_one({'_id': 'runner'}, {'$set': {'permissions': ['cash.deposit']}})
        original = self.db.business_events.__class__.insert_one
        def fail(collection, *args, **kwargs):
            if collection.name == 'business_events':
                raise RuntimeError('Injected failure after ledger write')
            return original(collection, *args, **kwargs)
        with patch.object(self.db.business_events.__class__, 'insert_one', fail):
            with self.assertRaises(RuntimeError):
                self.send(event)
        self.assertEqual(self.db.ledger.count_documents({}), 0)
        self.assertEqual(self.db.inbox.count_documents({}), 0)
        self.assertEqual(self.send(event).json()['results'][0]['status'], 'applied')

    def test_offline_shift_three_sales_close_and_snapshot_do_not_duplicate_stock(self):
        from desktop.commerce import record
        from desktop.business_rules import KINDS
        from desktop.snapshots import apply_page, catalog, pull_once
        from desktop.local_api import create_local_app
        from backend.sync_v1.commerce import balance
        self.db.devices.update_one({'_id': 'runner'}, {'$set': {'permissions': list(KINDS)}})
        journal = OfflineJournal(Path(self.temp.name) / 'operational.sqlite', 'runner')
        headers = {'Authorization': 'Bearer runner'}
        apply_page(journal, self.client.get('/api/sync/v1/snapshot', headers=headers).json(), None)
        shift_id = str(uuid.uuid4())
        record(journal, operation_id=str(uuid.uuid4()), kind='cash.open',
               data={'business_id': str(uuid.uuid4()), 'shift_id': shift_id, 'counted_cents': 0})
        local_headers = {'Authorization': 'Bearer ' + 'x'*40}
        with TestClient(create_local_app(journal, 'x'*40, require_shift=True)) as pc:
            for i in range(3):
                response = pc.post('/api/local/sales', headers=local_headers, json={
                    'operation_id': str(uuid.uuid4()), 'sale_id': f'offline-{i}', 'items': [{'sku': 'lanche', 'quantity': 1}]})
                self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(catalog(journal)[0]['quantity'], 7)
        self.assertEqual([e['payload']['items'][0]['base_version'] for e in journal.pending() if e['kind']=='sale.create'], [1,2,3])
        record(journal, operation_id=str(uuid.uuid4()), kind='cash.close', data={
            'business_id': str(uuid.uuid4()), 'shift_id': shift_id, 'expected_cents': 3000, 'counted_cents': 3000})
        self.assertEqual(sync_once(journal, lambda e: self.send(e).json()['results'][0])['synced'], 5)
        self.assertEqual(balance(self.db, None, 'runner', 'cash'), 3000)
        self.assertEqual(self.db.cash_shifts.find_one({'unit':'runner'})['status'], 'closed')
        pull_once(journal, lambda c: self.client.get('/api/sync/v1/snapshot', headers=headers, params={'cursor':c or ''}).json())
        self.assertEqual(catalog(journal)[0]['quantity'], 7)
        self.assertEqual(catalog(journal)[0]['version'], 4)
        self.assertEqual(self.db.sales.count_documents({}), 3)

    def test_stock_adjustment_sync_conflict_is_visible_and_never_overwrites(self):
        from desktop.commerce import record
        from desktop.business_rules import KINDS
        from desktop.snapshots import apply_page, catalog, pull_once
        self.db.devices.update_one({'_id':'runner'}, {'$set':{'permissions':list(KINDS)}})
        journal = OfflineJournal(Path(self.temp.name) / 'stock-adjust.sqlite', 'runner')
        headers={'Authorization':'Bearer runner'}
        apply_page(journal,self.client.get('/api/sync/v1/snapshot',headers=headers).json(),None)
        record(journal,operation_id=str(uuid.uuid4()),kind='stock.adjust',data={
            'business_id':str(uuid.uuid4()),'sku':'lanche','delta':3,'base_version':1,'description':'Entrada fictícia'})
        self.assertEqual(catalog(journal)[0]['quantity'],13)
        self.assertEqual(sync_once(journal,lambda e:self.send(e).json()['results'][0])['synced'],1)
        pull_once(journal,lambda c:self.client.get('/api/sync/v1/snapshot',headers=headers,params={'cursor':c or ''}).json())
        self.assertEqual(catalog(journal)[0]['quantity'],13)
        record(journal,operation_id=str(uuid.uuid4()),kind='stock.adjust',data={
            'business_id':str(uuid.uuid4()),'sku':'lanche','delta':-1,'base_version':2,'description':'Saída fictícia'})
        self.db.stock.update_one({'unit':'runner'},{'$inc':{'version':1}})
        self.assertEqual(sync_once(journal,lambda e:self.send(e).json()['results'][0])['conflicts'],1)
        self.assertTrue(catalog(journal)[0]['blocked'])
        self.assertEqual(self.db.stock.find_one({'unit':'runner'})['quantity'],13)

    def test_approved_prazo_sale_and_cash_receipt_do_not_duplicate_revenue(self):
        from desktop.commerce import record,summary
        from desktop.business_rules import KINDS
        from desktop.snapshots import apply_page,catalog
        from backend.sync_v1.commerce import balance
        self.db.devices.update_one({'_id':'runner'},{'$set':{'permissions':list(KINDS)}})
        journal=OfflineJournal(Path(self.temp.name)/'prazo-cycle.sqlite','runner')
        customer_id=str(uuid.uuid4())
        record(journal,operation_id=str(uuid.uuid4()),kind='customer.create',data={'business_id':str(uuid.uuid4()),'customer_id':customer_id,'name':'Cliente fictício prazo'})
        limit=record(journal,operation_id=str(uuid.uuid4()),kind='customer.limit',data={'business_id':str(uuid.uuid4()),'customer_id':customer_id,'limit_cents':2000,'base_version':1,'description':'Limite autorizado em teste'})
        apply_page(journal,self.client.get('/api/sync/v1/snapshot',headers={'Authorization':'Bearer runner'}).json(),None)
        item={'sku':'lanche','quantity':1,'base_version':1}
        with self.assertRaises(ValueError):journal.record_sale(sale_id='not-approved',total_cents=1000,payment_method='prazo',items=[item],customer_id=customer_id,customer_version=2)
        self.assertEqual(sync_once(journal,lambda e:self.send(e).json()['results'][0])['synced'],2)
        saved=journal.record_sale(sale_id='prazo-sale',total_cents=1000,payment_method='prazo',items=[item],customer_id=customer_id,customer_version=2)
        self.assertEqual(summary(journal)['cash_cents'],0)
        self.assertEqual(summary(journal)['customers'][0]['debt_cents'],1000)
        with self.assertRaises(ValueError):journal.record_sale(sale_id='over-limit',total_cents=2000,payment_method='prazo',items=[{'sku':'lanche','quantity':2,'base_version':2}],customer_id=customer_id,customer_version=3)
        record(journal,operation_id=str(uuid.uuid4()),kind='prazo.receive',data={'business_id':str(uuid.uuid4()),'customer_id':customer_id,'amount_cents':400,'description':'Recebimento parcial','payment_reference':'receipt-prazo-cycle','payment_method':'cash'})
        self.assertEqual(sync_once(journal,lambda e:self.send(e).json()['results'][0])['synced'],2)
        self.assertEqual(balance(self.db,None,'runner','cash'),400)
        self.assertEqual(balance(self.db,None,'runner','receivable/'+customer_id),600)
        self.assertEqual(balance(self.db,None,'runner','revenue'),-1000)
        self.assertEqual(summary(journal)['revenue_cents'],1000)
        self.assertEqual(self.db.stock.find_one({'unit':'runner'})['quantity'],9)

    def test_kitchen_status_sync_is_versioned_without_financial_effect(self):
        from desktop.commerce import record
        from desktop.business_rules import KINDS
        from backend.sync_v1.commerce import balance
        self.db.devices.update_one({'_id':'runner'},{'$set':{'permissions':list(KINDS)}})
        journal,event=self.event()
        self.assertEqual(sync_once(journal,lambda e:self.send(e).json()['results'][0])['synced'],1)
        for version,status in enumerate(('preparing','ready','delivered'),1):
            record(journal,operation_id=str(uuid.uuid4()),kind='order.status',data={'business_id':str(uuid.uuid4()),'sale_id':event['payload']['sale_id'],'base_version':version,'status':status})
        self.assertEqual(sync_once(journal,lambda e:self.send(e).json()['results'][0])['synced'],3)
        order=self.db.sales.find_one({'unit':'runner'})
        self.assertEqual(order['status'],'delivered');self.assertEqual(order['order_version'],4)
        self.assertEqual(balance(self.db,None,'runner','cash'),1000)
        self.assertEqual(self.db.stock.find_one({'unit':'runner'})['quantity'],9)

    def test_owner_overview_only_counts_confirmed_units_and_marks_unknown_pending(self):
        self.send(self.event()[1]);self.send(self.event('gym-londres')[1])
        expense=self.financial_event('expense.create',amount_cents=200,description='Despesa fictícia')
        self.assertEqual(self.send(expense).json()['results'][0]['status'],'applied')
        # Local-only draft must never affect the central consolidated overview.
        self.event(sale='not-synced')
        self.db.reviewers.insert_one({'_id':'owner-report','units':['runner','gym-londres'],'revoked':False,'token_hash':hashlib.sha256(b'owner-report-fixture').hexdigest()})
        url='/api/sync/v1/owner/overview'
        self.assertEqual(self.client.get(url,headers={'Authorization':'Bearer runner'}).status_code,401)
        report=self.client.get(url,headers={'Authorization':'Bearer owner-report-fixture'}).json()
        self.assertEqual(report['consolidated']['revenue_cents'],2000)
        self.assertEqual(report['consolidated']['cash_cents'],1800)
        self.assertEqual(report['consolidated']['expense_cents'],200)
        self.assertFalse(report['includes_unsynced_local_data'])
        self.assertTrue(all(row['local_pending'] is None for row in report['units']))
        self.db.reviewers.update_one({'_id':'owner-report'},{'$set':{'units':['runner']}})
        scoped=self.client.get(url,headers={'Authorization':'Bearer owner-report-fixture'}).json()
        self.assertEqual([r['unit'] for r in scoped['units']],['runner'])
        self.assertEqual(scoped['consolidated']['cash_cents'],800)

    def test_production_database_rejected(self):
        with self.assertRaises(ValueError):
            create_app(self.mongo['ganoh_production'])
