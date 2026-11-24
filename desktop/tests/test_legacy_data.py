import hashlib
import secrets
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from bson import BSON, Decimal128
from bson.timestamp import Timestamp
from backend.data_bridge.archive import Writer,new_file
from backend.data_bridge.unit_export import UNIT_FORMAT
from desktop.offline_store import OfflineJournal,OfflineError
from desktop.legacy_data import import_bundle,active,records

PHRASE='Fixture-Unit-Recovery-Phrase-2026'


class LegacyDataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.key=secrets.token_bytes(32)
        self.journal=OfflineJournal(self.root/'encrypted.sqlite','runner',encryption_key=self.key)

    def bundle(self,name='unit.ganoh',*,unit='runner',clock=100,total=205,rows=3,collection='orders',extra=None):
        path=self.root/name
        with new_file(path) as file:
            writer=Writer(file,PHRASE,kind=UNIT_FORMAT)
            pages=[];fingerprint=hashlib.sha256()
            for i in range(rows):
                document={'_id':str(i),'store':unit,'customer_name':'SECRET-LOCAL-CUSTOMER',
                    'total':Decimal128(str(total/100)),'created_at':'2020-01-01T00:00:00Z'}
                document.update(extra or {})
                data=BSON.encode(document)
                fingerprint.update(data);pages.append(writer.page(data))
            writer.finish({'archive_id':writer.id,'unit':unit,'source_database':'fixture-source',
                'read_timestamp':Timestamp(clock,1),'collections':[{'name':collection,'count':rows,
                'sha256':fingerprint.hexdigest(),'pages':pages}]})
        return path

    def test_old_history_survives_reopen_without_creating_any_revenue_or_outbox(self):
        saved=self.journal.record_sale(sale_id='existing-pending',total_cents=100,payment_method='cash',items=[{'sku':'fixture'}])
        bundle=self.bundle(rows=205)
        with patch('pymongo.MongoClient',side_effect=AssertionError('Windows must not connect to MongoDB')):
            result=import_bundle(self.journal,bundle,PHRASE)
        self.assertEqual(result['documents'],205)
        reopened=OfflineJournal(self.journal.path,'runner',encryption_key=self.key)
        cursor='';count=0
        while True:
            page=records(reopened,'orders',after=cursor,limit=100);count+=len(page['items'])
            self.assertEqual(page['items'][0]['total'],{'$numberDecimal':'2.05'})
            cursor=page['next_cursor']
            if not cursor:break
        self.assertEqual(count,205)
        self.assertEqual(reopened.pending()[0]['operation_id'],saved['operation_id'])
        self.assertEqual(reopened.status()['pending'],1)
        from desktop.commerce import summary
        self.assertEqual(summary(reopened)['revenue_cents'],100)
        self.assertNotIn(b'SECRET-LOCAL-CUSTOMER',self.journal.path.read_bytes())
        self.assertTrue(import_bundle(reopened,bundle,PHRASE)['already_imported'])
        with closing(reopened._connect()) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM legacy_versions').fetchone()[0],205)

    def test_interruption_keeps_published_history_and_resumes_without_duplicate_rows(self):
        import_bundle(self.journal,self.bundle('old.ganoh',clock=100,rows=1),PHRASE)
        new=self.bundle('new.ganoh',clock=200,rows=3)
        def interrupted(page):raise RuntimeError('Power loss fixture')
        with self.assertRaises(RuntimeError):import_bundle(self.journal,new,PHRASE,after_page=interrupted)
        self.assertEqual(len(records(self.journal,'orders')['items']),1)
        reopened=OfflineJournal(self.journal.path,'runner',encryption_key=self.key)
        result=import_bundle(reopened,new,PHRASE)
        self.assertEqual(result['documents'],3)
        self.assertEqual(len(records(reopened,'orders')['items']),3)
        with closing(reopened._connect()) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM legacy_versions').fetchone()[0],3)

    def test_wrong_unit_private_collections_plaintext_and_version_forks_are_blocked(self):
        for path in (self.bundle('wrong.ganoh',unit='gym-londres'),self.bundle('private.ganoh',collection='tenants')):
            with self.assertRaises(OfflineError):import_bundle(self.journal,path,PHRASE)
        self.assertIsNone(active(self.journal))
        data=self.bundle('valid.ganoh',clock=100)
        plain=OfflineJournal(self.root/'plain.sqlite','runner')
        with self.assertRaises(OfflineError):import_bundle(plain,data,PHRASE)
        import_bundle(self.journal,data,PHRASE)
        for path in (self.bundle('older.ganoh',clock=99),self.bundle('fork.ganoh',clock=100,total=999)):
            with self.assertRaises(OfflineError):import_bundle(self.journal,path,PHRASE)
        self.assertEqual(records(self.journal,'orders')['items'][0]['total'],{'$numberDecimal':'2.05'})

    def test_cursor_is_generation_bound_and_replaced_source_versions_remain_preserved(self):
        import_bundle(self.journal,self.bundle('one.ganoh',clock=100),PHRASE)
        old=records(self.journal,'orders',limit=1)['next_cursor']
        import_bundle(self.journal,self.bundle('two.ganoh',clock=200,total=999),PHRASE)
        with self.assertRaises(OfflineError):records(self.journal,'orders',after=old)
        with closing(self.journal._connect()) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM legacy_versions').fetchone()[0],6)
        self.assertEqual(records(self.journal,'orders')['items'][0]['total'],{'$numberDecimal':'9.99'})

    def test_history_only_import_blocks_new_financial_operations_until_balances_are_verified(self):
        import uuid
        from desktop.commerce import record
        import_bundle(self.journal,self.bundle(),PHRASE)
        self.assertFalse(active(self.journal)['operational_baseline_ready'])
        with self.assertRaises(OfflineError):
            self.journal.record_sale(sale_id='must-not-sell-yet',total_cents=100,payment_method='cash',items=[{'sku':'fixture'}])
        with self.assertRaises(OfflineError):
            record(self.journal,operation_id=str(uuid.uuid4()),kind='customer.create',data={'business_id':str(uuid.uuid4()),'customer_id':str(uuid.uuid4()),'name':'Must not duplicate imported customers'})
        self.assertEqual(self.journal.status()['pending'],0)
        with closing(self.journal._connect()) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
        reopened=OfflineJournal(self.journal.path,'runner',encryption_key=self.key)
        with closing(reopened._connect()) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)

    def test_first_interrupted_load_cannot_mix_unverified_history_with_new_sales(self):
        def interrupt(page):raise RuntimeError('Fixture interrupted during first load')
        bundle=self.bundle('first.ganoh',rows=3)
        with self.assertRaises(RuntimeError):import_bundle(self.journal,bundle,PHRASE,after_page=interrupt)
        self.assertIsNone(active(self.journal))
        with self.assertRaises(OfflineError):self.journal.record_sale(sale_id='must-wait',total_cents=100,payment_method='cash',items=[{'sku':'fixture'}])
        import_bundle(self.journal,bundle,PHRASE)
        self.assertTrue(active(self.journal)['history_complete'])
        self.assertFalse(active(self.journal)['operational_baseline_ready'])
        with closing(self.journal._connect()) as db:self.assertIsNone(db.execute("SELECT value FROM metadata WHERE key='legacy_staging'").fetchone())


    def test_reversal_history_is_read_only_and_embedded_cross_unit_data_is_rejected(self):
        path=self.bundle('reversal.ganoh',rows=1,collection='prazo_payment_reversals',
                         extra={'duplicate_payment':{'store':'runner','amount':10}})
        import_bundle(self.journal,path,PHRASE)
        row=records(self.journal,'prazo_payment_reversals')['items'][0]
        self.assertEqual(row['duplicate_payment']['store'],'runner')
        self.assertEqual(self.journal.status()['pending'],0)
        from desktop.commerce import summary
        self.assertEqual(summary(self.journal)['revenue_cents'],0)
        bad=self.bundle('cross-unit-reversal.ganoh',clock=200,rows=1,
                        collection='prazo_payment_reversals',
                        extra={'duplicate_payment':{'store':'gym-londres','amount':10}})
        with self.assertRaises(OfflineError):import_bundle(self.journal,bad,PHRASE)
        self.assertEqual(records(self.journal,'prazo_payment_reversals')['items'][0]['duplicate_payment']['store'],'runner')
