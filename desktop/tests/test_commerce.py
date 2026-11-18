import tempfile
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from desktop.commerce import record, summary, post
from desktop.offline_store import OfflineJournal, OfflineError
from desktop.sync_worker import sync_once


def event(journal, kind, **fields):
    return record(journal, operation_id=str(uuid.uuid4()), kind=kind,
                  data={'business_id': str(uuid.uuid4()), **fields})


class CommerceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'commerce.sqlite'
        self.journal = OfflineJournal(self.path, 'runner')

    def test_sale_expense_withdraw_restart_and_balanced_ledger(self):
        event(self.journal, 'cash.deposit', amount_cents=500, description='Suprimento inicial')
        self.journal.record_sale(sale_id='a', total_cents=1000, payment_method='cash', items=[{'sku': 'a'}])
        event(self.journal, 'expense.create', amount_cents=200, description='Material de limpeza')
        event(self.journal, 'cash.withdraw', amount_cents=300, description='Retirada do proprietário')
        reopened = OfflineJournal(self.path, 'runner')
        result = summary(reopened)
        self.assertEqual(result['cash_cents'], 1000)
        self.assertEqual(result['expense_cents'], 200)
        self.assertEqual(result['revenue_cents'], 1000)
        self.assertTrue(result['balanced'])
        self.assertTrue(result['provisional'])
        self.assertEqual([i['kind'] for i in reopened.pending()], ['cash.deposit', 'sale.create', 'expense.create', 'cash.withdraw'])

    def test_idempotent_business_event_and_changed_uuid_business_id(self):
        data = {'business_id': str(uuid.uuid4()), 'amount_cents': 1000, 'description': 'Entrada de teste'}
        operation = str(uuid.uuid4())
        record(self.journal, operation_id=operation, kind='cash.deposit', data=data)
        self.assertTrue(record(self.journal, operation_id=operation, kind='cash.deposit', data=data)['already_exists'])
        with self.assertRaises(OfflineError):
            record(self.journal, operation_id=str(uuid.uuid4()), kind='cash.deposit', data=data)
        with self.assertRaises(OfflineError):
            record(self.journal, operation_id=operation, kind='cash.deposit', data={**data, 'amount_cents': 2000})
        self.assertEqual(summary(self.journal)['cash_cents'], 1000)
        self.assertEqual(self.journal.status()['pending'], 1)

    def test_insufficient_balance_rolls_back_queue_and_postings(self):
        event(self.journal, 'cash.deposit', amount_cents=100, description='Entrada de teste')
        with self.assertRaises(OfflineError):
            event(self.journal, 'expense.create', amount_cents=101, description='Despesa sem saldo')
        self.assertEqual(self.journal.status()['pending'], 1)
        self.assertEqual(summary(self.journal)['cash_cents'], 100)
        self.assertTrue(summary(self.journal)['balanced'])

    def test_customer_and_receipt_cannot_exceed_debt_or_settle_pix(self):
        customer = str(uuid.uuid4())
        event(self.journal, 'customer.create', customer_id=customer, name='Cliente fictício')
        with self.assertRaises(OfflineError):
            event(self.journal, 'customer.create', customer_id=str(uuid.uuid4()), name=' cliente FICTÍCIO ')
        # Isolated fictitious historical debt; no endpoint fabricates customer debt.
        with closing(self.journal._connect()) as db:
            op = str(uuid.uuid4())
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO event_order(operation_id,kind) VALUES(?,?)', (op, 'test.fixture'))
            post(db, op, [('receivable/' + customer, 500), ('revenue', -500)])
            db.execute('COMMIT')
        for amount, method in [(501, 'cash'), (100, 'pix')]:
            with self.assertRaises(OfflineError):
                event(self.journal, 'prazo.receive', customer_id=customer, amount_cents=amount,
                      payment_method=method, payment_reference='receipt-test', description='Recebimento fictício')
        receipt = {'business_id': str(uuid.uuid4()), 'customer_id': customer, 'amount_cents': 200,
                   'payment_method': 'cash', 'payment_reference': 'receipt-test', 'description': 'Recebimento fictício'}
        op = str(uuid.uuid4())
        record(self.journal, operation_id=op, kind='prazo.receive', data=receipt)
        record(self.journal, operation_id=op, kind='prazo.receive', data=receipt)
        with self.assertRaises(OfflineError):
            record(self.journal, operation_id=str(uuid.uuid4()), kind='prazo.receive',
                   data={**receipt, 'business_id': str(uuid.uuid4())})
        result = summary(self.journal)
        self.assertEqual(result['customers'][0]['debt_cents'], 300)
        self.assertEqual(result['cash_cents'], 200)
        self.assertTrue(result['balanced'])

    def test_failed_parent_does_not_send_dependent_operation(self):
        event(self.journal, 'cash.deposit', amount_cents=1000, description='Entrada teste')
        event(self.journal, 'cash.withdraw', amount_cents=500, description='Retirada teste')
        called = []
        def unavailable(item):
            called.append(item['kind'])
            raise TimeoutError()
        sync_once(self.journal, unavailable)
        self.assertEqual(called, ['cash.deposit'])
        self.assertEqual(self.journal.status()['pending'], 2)
        def deliver(item):
            return {**{k: item[k] for k in ('operation_id', 'unit', 'fingerprint')}, 'status': 'applied', 'receipt_id': item['operation_id']}
        self.assertEqual(sync_once(self.journal, deliver)['synced'], 2)
        self.assertEqual(self.journal.status()['pending'], 0)

    def test_concurrent_local_withdrawals_do_not_overdraw(self):
        from concurrent.futures import ThreadPoolExecutor
        event(self.journal, 'cash.deposit', amount_cents=1000, description='Suprimento teste')
        def withdraw(_):
            try:
                event(OfflineJournal(self.path, 'runner'), 'cash.withdraw', amount_cents=800, description='Retirada concorrente')
                return 'applied'
            except OfflineError:
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(withdraw, range(2))), ['applied', 'rejected'])
        self.assertEqual(summary(self.journal)['cash_cents'], 200)

    def test_v1_migration_preserves_payload_receipts_and_cash_once(self):
        saved = self.journal.record_sale(sale_id='before-upgrade', total_cents=1000,
                                          payment_method='cash', items=[{'sku': 'lanche'}])
        self.journal.acknowledge(saved['operation_id'], saved['fingerprint'], 'original-receipt')
        # Reconstruct the pre-ledger demo schema in this disposable fixture only.
        with closing(self.journal._connect()) as db:
            db.execute('PRAGMA foreign_keys=OFF')
            for table in ('ledger', 'customers', 'payment_refs', 'business_operations', 'event_order'):
                db.execute('DROP TABLE ' + table)
            db.execute('PRAGMA user_version=1')
        upgraded = OfflineJournal(self.path, 'runner')
        self.assertEqual(summary(upgraded)['cash_cents'], 1000)
        reopened = OfflineJournal(self.path, 'runner')
        self.assertEqual(summary(reopened)['cash_cents'], 1000)
        with closing(reopened._connect()) as db:
            row = db.execute('SELECT * FROM operations').fetchone()
            self.assertEqual(row['fingerprint'], saved['fingerprint'])
            self.assertEqual(row['central_receipt_id'], 'original-receipt')
            self.assertEqual(row['state'], 'synced')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)

    def test_same_uuid_across_sale_and_business_cannot_duplicate(self):
        operation = str(uuid.uuid4())
        self.journal.record_sale(operation_id=operation, sale_id='sale', total_cents=500, payment_method='cash', items=[{'sku': 'a'}])
        with self.assertRaises(OfflineError):
            record(self.journal, operation_id=operation, kind='cash.deposit',
                   data={'business_id': str(uuid.uuid4()), 'amount_cents': 500, 'description': 'Entrada teste'})
        self.assertEqual(summary(self.journal)['cash_cents'], 500)

    def test_csv_is_balanced_provisional_and_escapes_spreadsheet_formulas(self):
        from desktop.reports import ledger_csv
        import csv,io
        event(self.journal,'cash.deposit',amount_cents=100,description='=untrusted spreadsheet formula')
        rows=list(csv.DictReader(io.StringIO(ledger_csv(self.journal).lstrip('\ufeff'))))
        self.assertEqual(sum(int(row['amount_cents']) for row in rows),0)
        self.assertTrue(all(row['scope']=='LOCAL_PROVISIONAL' for row in rows))
        self.assertTrue(all(row['description'].startswith("'=") for row in rows))
