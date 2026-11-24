"""No production connections: disposable loopback MongoDB replica set only."""
import hashlib
import tempfile
import unittest
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bson import ObjectId, Decimal128, Binary, Int64
from pymongo import MongoClient
from pymongo.monitoring import CommandListener
from backend.data_bridge.archive import ArchiveError, Reader
from backend.data_bridge.mongo_backup import capture, validate_restore


class Commands(CommandListener):
    def __init__(self): self.names = []
    def started(self, event): self.names.append(event.command_name)
    def succeeded(self, event): pass
    def failed(self, event): pass


class MongoBackupTests(unittest.TestCase):
    def setUp(self):
        self.commands = Commands()
        self.client = MongoClient('mongodb://127.0.0.1:27028/?directConnection=true',
                                  serverSelectionTimeoutMS=3000, event_listeners=[self.commands])
        self.source = self.client['ganoh_sync_test_backup_' + uuid.uuid4().hex]
        self.target = self.client['ganoh_restore_test_' + uuid.uuid4().hex]
        self.addCleanup(self.client.close)
        self.addCleanup(lambda: self.client.drop_database(self.source.name))
        self.addCleanup(lambda: self.client.drop_database(self.target.name))
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'snapshot.ganoh'
        self.phrase = 'Fixture-only-recovery-phrase-2026'
        self.source.a_customers.insert_one({'_id': ObjectId(), 'store':'runner', 'name':'SECRET-FIXTURE-NAME',
            'debt':Decimal128('10.25'),'legacy_big':Int64(123),'binary':Binary(b'0123456789abcdef',4),
            'created_at':datetime(2020,1,1,tzinfo=timezone.utc)})
        self.source.b_orders.insert_many([{'_id':str(i),'id':'old-'+str(i),'store':'runner',
            'created_at':'2026-11-21T23:00:00-03:00','total':10.0} for i in range(235)])
        self.source.b_orders.create_index([('store',1),('id',1)],unique=True,name='unit_order')
        self.source.empty.create_index('expires_at',expireAfterSeconds=0)
        self.source.create_collection('runner_view',viewOn='b_orders',pipeline=[{'$match':{'store':'runner'}}])

    def test_full_encrypted_restore_preserves_history_types_indexes_and_empty_collections(self):
        result=capture(self.source,self.path,self.phrase,page_bytes=1024)
        self.assertEqual(result['documents'],236)
        self.assertNotIn(b'SECRET-FIXTURE-NAME',self.path.read_bytes())
        self.assertNotIn(b'old-234',self.path.read_bytes())
        with Reader(self.path,self.phrase) as reader:
            self.assertEqual(reader.validate()['documents'],236)
            self.assertGreater(len(next(c for c in reader.manifest['collections'] if c['name']=='b_orders')['pages']),1)
        restored=validate_restore(self.path,self.phrase,self.target)
        self.assertEqual(restored['integrity'],'restored_and_verified')
        self.assertEqual(self.target.b_orders.count_documents({}),235)
        self.assertEqual(self.target.runner_view.count_documents({}),235)
        self.assertEqual(self.target.a_customers.find_one()['debt'],Decimal128('10.25'))
        self.assertIn('empty',self.target.list_collection_names())
        self.assertTrue(self.target.b_orders.index_information()['unit_order']['unique'])
        self.assertEqual(self.target.empty.index_information()['expires_at_1']['expireAfterSeconds'],0)

    def test_capture_issues_no_source_write_commands(self):
        self.commands.names.clear()
        capture(self.source,self.path,self.phrase)
        self.assertFalse(set(self.commands.names)&{'insert','update','delete','drop','create','createIndexes','collMod'})

    def test_one_snapshot_across_collections_despite_concurrent_changes(self):
        def concurrent(name,count):
            if name=='a_customers':
                self.source.b_orders.update_one({'_id':'0'},{'$set':{'total':999}})
                self.source.b_orders.insert_one({'_id':'new-after-snapshot','total':123})
        capture(self.source,self.path,self.phrase,on_collection=concurrent)
        validate_restore(self.path,self.phrase,self.target)
        self.assertEqual(self.target.b_orders.find_one({'_id':'0'})['total'],10.0)
        self.assertIsNone(self.target.b_orders.find_one({'_id':'new-after-snapshot'}))
        self.assertEqual(self.source.b_orders.find_one({'_id':'0'})['total'],999)

    def test_wrong_password_tampering_and_existing_target_never_replace_records(self):
        capture(self.source,self.path,self.phrase)
        with self.assertRaises(ArchiveError): Reader(self.path,'Wrong-but-long-phrase-2026')
        corrupt=Path(self.temp.name)/'corrupt.ganoh'
        with zipfile.ZipFile(self.path) as original,zipfile.ZipFile(corrupt,'w',compression=zipfile.ZIP_STORED) as output:
            for name in original.namelist():
                data=original.read(name)
                if name.startswith('pages/'):
                    data=data[:-1]+bytes([data[-1]^1])
                output.writestr(name,data)
        with self.assertRaises(ArchiveError):validate_restore(corrupt,self.phrase,self.target)
        self.assertEqual(self.target.list_collection_names(),[])
        self.target.keep.insert_one({'_id':'existing','amount':123})
        with self.assertRaises(ArchiveError):validate_restore(self.path,self.phrase,self.target)
        self.assertEqual(self.target.keep.find_one()['amount'],123)

    def test_refuses_production_and_remote_restore_targets(self):
        capture(self.source,self.path,self.phrase)
        with self.assertRaises(ArchiveError):validate_restore(self.path,self.phrase,self.client['ganoh_production'])
        remote=SimpleNamespace(name='ganoh_restore_test_remote',client=SimpleNamespace(address=('example.invalid',27017)))
        with self.assertRaises(ArchiveError):validate_restore(self.path,self.phrase,remote)

    def test_interruption_never_publishes_partial_archive_or_overwrites_backup(self):
        def interrupt(name,count):raise RuntimeError('Fixture interrupted')
        with self.assertRaises(RuntimeError):capture(self.source,self.path,self.phrase,on_collection=interrupt)
        self.assertFalse(self.path.exists())
        self.assertFalse(list(Path(self.temp.name).glob('.ganoh-encrypted-*')))
        capture(self.source,self.path,self.phrase)
        old=hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(FileExistsError):capture(self.source,self.path,self.phrase)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),old)

    def test_metadata_changes_abort_the_archive_instead_of_claiming_consistency(self):
        def change_options(name,count):
            if name=='a_customers':self.source.command('collMod','b_orders',validator={'total':{'$type':'number'}},validationLevel='off')
        with self.assertRaises(ArchiveError):capture(self.source,self.path,self.phrase,on_collection=change_options)
        self.assertFalse(self.path.exists())
        def change_index(name,count):
            if name=='b_orders':self.source.b_orders.create_index('total',name='changed_during_capture')
        with self.assertRaises(ArchiveError):capture(self.source,self.path,self.phrase,on_collection=change_index)
        self.assertFalse(self.path.exists())

    def test_restore_keeps_old_documents_that_predate_a_stricter_validator(self):
        self.source.command('collMod','b_orders',validator={'total':{'$gt':1000}},validationLevel='strict')
        capture(self.source,self.path,self.phrase)
        validate_restore(self.path,self.phrase,self.target)
        self.assertEqual(self.target.b_orders.count_documents({}),235)
        options=next(c for c in self.target.list_collections() if c['name']=='b_orders')['options']
        self.assertEqual(options['validator'],{'total':{'$gt':1000}})
