import tempfile
import unittest
import uuid
from pathlib import Path
from pymongo import MongoClient
from backend.data_bridge.archive import ArchiveError,Reader
from backend.data_bridge.mongo_backup import capture,validate_restore
from backend.data_bridge.unit_export import export_unit,UNIT_FORMAT


class UnitExportTests(unittest.TestCase):
    def setUp(self):
        self.client=MongoClient('mongodb://127.0.0.1:27028/?directConnection=true',serverSelectionTimeoutMS=3000)
        self.db=self.client['ganoh_sync_test_unit_'+uuid.uuid4().hex]
        self.restore=self.client['ganoh_restore_test_unit_'+uuid.uuid4().hex]
        self.addCleanup(self.client.close);self.addCleanup(lambda:self.client.drop_database(self.db.name))
        self.addCleanup(lambda:self.client.drop_database(self.restore.name))
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.phrase='Full-Fixture-Recovery-Phrase-2026';self.unit_phrase='Unit-Fixture-Recovery-Phrase-2026'
        self.db.orders.insert_many([{'_id':'old','store':'runner','created_at':'2020-01-01','total':10},
            {'_id':'saturday','store':'runner','created_at':'2026-11-21T23:59:00-03:00','total':20},
            {'_id':'other-store','store':'gym-londres','total':99}])
        self.db.tenants.insert_one({'username':'fixture-admin','password_hash':'SECRET-ADMIN-DO-NOT-COPY'})
        self.db.settings.insert_one({'key':'fixture-api-key','value':'SECRET-API-DO-NOT-COPY'})
        self.db.adicionais.insert_one({'id':'extra','name':'Shared fixture'})

    def export(self):
        full=self.root/'full.ganoh';capture(self.db,full,self.phrase)
        destination=self.root/'runner.ganoh'
        receipt=validate_restore(full,self.phrase,self.restore)
        export_unit(full,self.phrase,destination,self.unit_phrase,'runner',validated_backup=receipt)
        return destination

    def test_business_history_has_no_date_cutoff_no_admin_secrets_and_no_other_store(self):
        with Reader(self.export(),self.unit_phrase,kind=UNIT_FORMAT) as reader:
            self.assertEqual(reader.manifest['unit'],'runner')
            self.assertEqual({c['name'] for c in reader.manifest['collections']},{'orders','adicionais'})
            orders=next(c for c in reader.manifest['collections'] if c['name']=='orders')
            rows=list(reader.documents(orders))
            self.assertEqual({d['_id'] for d in rows},{'old','saturday'})
            self.assertEqual(reader.validate()['documents'],3)

    def test_unmapped_or_unscoped_documents_are_not_silently_discarded(self):
        self.db.orders.insert_one({'_id':'ambiguous-unit','total':500})
        with self.assertRaises(ArchiveError):self.export()
        self.assertFalse((self.root/'runner.ganoh').exists())
        (self.root/'full.ganoh').unlink()
        self.client.drop_database(self.restore.name)
        self.db.orders.delete_one({'_id':'ambiguous-unit'})
        self.db.unmapped_business.insert_one({'id':'unknown'})
        with self.assertRaises(ArchiveError):self.export()
        self.assertFalse((self.root/'runner.ganoh').exists())

    def test_full_database_archive_cannot_be_relabelled_as_a_unit_package(self):
        import json,zipfile
        full=self.root/'full.ganoh';capture(self.db,full,self.phrase)
        forged=self.root/'forged.ganoh'
        with zipfile.ZipFile(full) as src,zipfile.ZipFile(forged,'w',compression=zipfile.ZIP_STORED) as dst:
            for name in src.namelist():
                data=src.read(name)
                if name=='envelope.json':
                    value=json.loads(data);value['format']=UNIT_FORMAT;data=json.dumps(value).encode()
                dst.writestr(name,data)
        with self.assertRaises(ArchiveError):Reader(forged,self.phrase,kind=UNIT_FORMAT)

    def test_unit_export_requires_successful_restore_of_the_exact_encrypted_file(self):
        full=self.root/'full.ganoh';capture(self.db,full,self.phrase)
        destination=self.root/'runner.ganoh'
        with self.assertRaises(ArchiveError):export_unit(full,self.phrase,destination,self.unit_phrase,'runner')
        receipt=validate_restore(full,self.phrase,self.restore)
        receipt['archive_sha256']='0'*64
        with self.assertRaises(ArchiveError):export_unit(full,self.phrase,destination,self.unit_phrase,'runner',validated_backup=receipt)
        self.assertFalse(destination.exists())


    def test_debts_and_reversal_audit_are_preserved_but_server_inboxes_are_not_distributed(self):
        self.db.prazo_debts.insert_one({'_id':'debt-fixture','store':'runner','amount':23.25})
        self.db.prazo_payment_reversals.insert_many([
            {'_id':'reverse-fixture','store':'runner','amount_reversed':10,
             'duplicate_payment':{'store':'runner','amount':10},
             'affected_orders_before':[{'store':'runner','total':10}]},
            {'_id':'other-reversal','store':'gym-londres','amount_reversed':99}])
        for name in ('repair_runs','recovery_runs','baileys_inbound','baileys_processed_messages'):
            self.db[name].insert_one({'_id':'server-only','payload':'FIXTURE-PRIVATE-SERVER-AUDIT'})
        with Reader(self.export(),self.unit_phrase,kind=UNIT_FORMAT) as reader:
            collections={c['name']:c for c in reader.manifest['collections']}
            self.assertEqual(set(collections),{'orders','adicionais','prazo_debts','prazo_payment_reversals'})
            reversal=list(reader.documents(collections['prazo_payment_reversals']))
            self.assertEqual(len(reversal),1)
            self.assertEqual(reversal[0]['duplicate_payment']['amount'],10)
            self.assertEqual(reversal[0]['affected_orders_before'][0]['store'],'runner')
            self.assertEqual(list(reader.documents(collections['prazo_debts']))[0]['amount'],23.25)

    def test_top_level_unit_cannot_hide_another_stores_embedded_financial_records(self):
        self.db.prazo_payment_reversals.insert_one({'_id':'cross-unit-fixture','store':'runner',
            'affected_orders_before':[{'store':'gym-londres','total':150}]})
        with self.assertRaises(ArchiveError):self.export()
        self.assertFalse((self.root/'runner.ganoh').exists())
