import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from fastapi.testclient import TestClient
from desktop.offline_store import OfflineJournal, OfflineError
from desktop.commerce import record, summary
from desktop.snapshots import apply_page, catalog
from desktop.operations import state
from desktop.local_api import create_local_app


class OperationalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ops.sqlite'
        self.journal = OfflineJournal(self.path, 'runner')
        apply_page(self.journal, {'unit': 'runner', 'generation': 'seed', 'done': True, 'next_cursor': None,
            'items': [{'sku': 'lanche', 'quantity': 5, 'price_cents': 100, 'version': 1}]}, None)

    def event(self, kind, **data):
        return record(self.journal, operation_id=str(uuid.uuid4()), kind=kind,
                      data={'business_id': str(uuid.uuid4()), **data})

    def sale(self, number, shift=None):
        entry = catalog(self.journal)[0]
        return self.journal.record_sale(sale_id=str(number), total_cents=100, payment_method='cash',
            cash_shift_id=shift, items=[{'sku': 'lanche', 'quantity': 1, 'base_version': entry['version']}])

    def test_multiple_offline_sales_reserve_quantity_and_successive_versions(self):
        for n in range(5):
            self.sale(n)
        self.assertEqual(catalog(self.journal)[0]['quantity'], 0)
        self.assertEqual([i['payload']['items'][0]['base_version'] for i in self.journal.pending()], [1, 2, 3, 4, 5])
        with self.assertRaises(OfflineError):
            self.sale(6)
        self.assertEqual(self.journal.status()['pending'], 5)

    def test_snapshot_coverage_prevents_double_stock_decrement(self):
        saved = self.sale(1)
        self.assertEqual(catalog(self.journal)[0]['quantity'], 4)
        apply_page(self.journal, {'unit': 'runner', 'generation': 'central', 'done': True, 'next_cursor': None,
            'covered_operations': [{'operation_id': saved['operation_id'], 'fingerprint': saved['fingerprint']}],
            'items': [{'sku': 'lanche', 'quantity': 4, 'price_cents': 100, 'version': 2}]}, None)
        self.assertEqual(catalog(self.journal)[0]['quantity'], 4)
        self.assertEqual(catalog(self.journal)[0]['version'], 2)
        self.sale(2)
        self.assertEqual(catalog(self.journal)[0]['quantity'], 3)
        self.journal.flag_conflict(self.journal.pending()[1]['operation_id'], 'Version conflict')
        self.assertTrue(catalog(self.journal)[0]['blocked'])

    def test_stock_adjustment_is_projected_audited_and_cannot_go_negative(self):
        self.event('stock.adjust', sku='lanche', delta=2, base_version=1, description='Entrada fictícia')
        self.assertEqual(catalog(self.journal)[0]['quantity'], 7)
        self.sale(1)
        self.assertEqual(self.journal.pending()[1]['payload']['items'][0]['base_version'], 2)
        with self.assertRaises(OfflineError):
            self.event('stock.adjust', sku='lanche', delta=-7, base_version=3, description='Perda fictícia')
        self.assertEqual(catalog(self.journal)[0]['quantity'], 6)

    def test_open_close_restart_preserves_cash_without_adding_revenue(self):
        shift = str(uuid.uuid4())
        self.event('cash.open', shift_id=shift, counted_cents=0)
        self.sale(1, shift)
        self.event('expense.create', amount_cents=20, description='Despesa fictícia')
        self.event('cash.close', shift_id=shift, expected_cents=80, counted_cents=80)
        reopened = OfflineJournal(self.path, 'runner')
        self.assertIsNone(state(reopened)['active_shift'])
        self.assertEqual(summary(reopened)['cash_cents'], 80)
        with self.assertRaises(OfflineError):
            self.sale(2, shift)
        next_shift = str(uuid.uuid4())
        self.event('cash.open', shift_id=next_shift, counted_cents=80)
        self.assertEqual(summary(reopened)['cash_cents'], 80)
        self.assertEqual(summary(reopened)['revenue_cents'], 100)

    def test_count_difference_is_retained_without_overwriting_cash(self):
        shift = str(uuid.uuid4())
        self.event('cash.open', shift_id=shift, counted_cents=0)
        self.sale(1, shift)
        self.event('cash.close', shift_id=shift, expected_cents=100, counted_cents=90)
        self.assertEqual(state(self.journal)['active_shift']['status'], 'needs_review')
        self.assertEqual(summary(self.journal)['cash_cents'], 100)
        with self.assertRaises(OfflineError):
            self.event('cash.open', shift_id=str(uuid.uuid4()), counted_cents=100)

    def test_required_shift_api_blocks_sale_before_open(self):
        headers = {'Authorization': 'Bearer ' + 'x'*40}
        with TestClient(create_local_app(self.journal, 'x'*40, require_shift=True)) as api:
            body = {'operation_id': str(uuid.uuid4()), 'sale_id': 'api-sale', 'items': [{'sku': 'lanche', 'quantity': 1}]}
            self.assertEqual(api.post('/api/local/sales', headers=headers, json=body).status_code, 409)
            self.event('cash.open', shift_id=str(uuid.uuid4()), counted_cents=0)
            self.assertEqual(api.post('/api/local/sales', headers=headers, json=body).status_code, 200)

    def test_new_product_entry_and_sale_can_be_queued_completely_offline(self):
        self.event('catalog.upsert',sku='new-product',name='Produto fictício',description='Cadastro local',category='Lanches',
                   price_cents=200,prep_time=10,available=True,base_version=0)
        self.event('stock.adjust',sku='new-product',delta=3,base_version=1,description='Entrada inicial')
        item=next(i for i in catalog(self.journal) if i['sku']=='new-product')
        self.assertEqual(item['quantity'],3);self.assertEqual(item['version'],2)
        self.journal.record_sale(sale_id='new-product-sale',total_cents=200,payment_method='cash',items=[{'sku':'new-product','quantity':1,'base_version':2}])
        self.assertEqual(next(i for i in catalog(self.journal) if i['sku']=='new-product')['quantity'],2)

    def test_owner_reconciliation_is_a_new_balanced_event_not_a_sale_overwrite(self):
        shift=str(uuid.uuid4());self.event('cash.open',shift_id=shift,counted_cents=0);self.sale('one',shift)
        self.event('cash.close',shift_id=shift,expected_cents=100,counted_cents=90)
        self.event('cash.reconcile',shift_id=shift,expected_cents=100,counted_cents=90,description='Falta confirmada pelo proprietário')
        self.assertIsNone(state(self.journal)['active_shift'])
        value=summary(self.journal)
        self.assertEqual(value['cash_cents'],90);self.assertEqual(value['revenue_cents'],100)
        self.assertEqual(value['cash_variance_cents'],10);self.assertTrue(value['balanced'])
        row=state(self.journal)['shifts'][0]
        self.assertEqual(row['counted_cents'],90);self.assertEqual(row['reconciled_cents'],90)
        self.assertTrue(row['reconcile_operation_id'])
        self.event('cash.open',shift_id=str(uuid.uuid4()),counted_cents=90)
        self.assertEqual(summary(self.journal)['cash_cents'],90)

    def test_sale_does_not_wait_for_slow_sync_network(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        blocked=threading.Event();release=threading.Event()
        saved=self.sale('before-network')
        class SlowTransport:
            def __call__(inner,item):
                blocked.set();release.wait(10)
                return {**{k:item[k] for k in ('unit','operation_id','fingerprint')},'status':'applied','receipt_id':'slow-receipt'}
            def snapshot(inner,current):
                return {'unit':'runner','generation':'slow','done':True,'next_cursor':None,'items':[{'sku':'lanche','quantity':4,'price_cents':100,'version':2}],
                        'covered_operations':[{'operation_id':saved['operation_id'],'fingerprint':saved['fingerprint']}]}
        token='x'*40;headers={'Authorization':'Bearer '+token}
        with TestClient(create_local_app(self.journal,token,SlowTransport(),interval=100)) as api:
            self.assertTrue(blocked.wait(2))
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    job=pool.submit(lambda:api.post('/api/local/sales',headers=headers,json={'operation_id':str(uuid.uuid4()),'sale_id':'during-network','items':[{'sku':'lanche','quantity':1}]}))
                    self.assertEqual(job.result(timeout=2).status_code,200)
            finally:release.set()
