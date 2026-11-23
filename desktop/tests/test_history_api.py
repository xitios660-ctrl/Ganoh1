"""Encrypted fixture packages only. Never connects to Atlas."""
import base64
import hashlib
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bson import BSON, Decimal128
from bson.timestamp import Timestamp
from fastapi.testclient import TestClient
from backend.data_bridge.archive import Writer, new_file
from backend.data_bridge.unit_export import UNIT_FORMAT
from desktop.local_api import create_local_app
from desktop.offline_store import OfflineJournal

PHRASE='Fixture-history-import-phrase-2026'


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.journal=OfflineJournal(self.root/'local.sqlite','runner',encryption_key=secrets.token_bytes(32))
        self.api=TestClient(create_local_app(self.journal,'x'*40,require_operator=True))
        self.api.headers['Authorization']='Bearer '+'x'*40
        self.owner={'username':'history-owner','password':'Fixture-owner-password-2026'}
        self.api.post('/api/local/auth/setup',json=self.owner)

    def package(self,unit='runner',clock=100):
        path=self.root/(unit+str(clock)+'.ganoh')
        data=b''.join(BSON.encode({'_id':str(i),'store':unit,'id':'sale-fixture-'+str(i),
            'customer_name':'PRIVATE-FIXTURE-NAME','total':Decimal128('10.25')}) for i in range(3))
        with new_file(path) as file:
            writer=Writer(file,PHRASE,kind=UNIT_FORMAT)
            page=writer.page(data)
            writer.finish({'archive_id':writer.id,'unit':unit,'source_database':'fixture-source',
                'read_timestamp':Timestamp(clock,1),'collections':[{'name':'orders','count':3,
                'sha256':hashlib.sha256(data).hexdigest(),'pages':[page]}]})
        return {'archive':base64.b64encode(path.read_bytes()).decode(),'passphrase':PHRASE}

    def test_owner_imports_once_and_reopens_paginated_history_without_revenue(self):
        body=self.package()
        with patch('pymongo.MongoClient',side_effect=AssertionError('No Mongo in Windows')):
            result=self.api.post('/api/local/history/import',json=body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['documents'],3)
        repeated=self.api.post('/api/local/history/import',json=body)
        self.assertTrue(repeated.json()['already_imported'])
        state=self.api.get('/api/local/history').json()
        self.assertTrue(state['active']['history_complete'])
        self.assertFalse(state['active']['operational_baseline_ready'])
        self.assertFalse(state['import_incomplete'])
        page=self.api.get('/api/local/history/orders?limit=2')
        self.assertEqual(page.headers['cache-control'],'no-store')
        self.assertEqual(len(page.json()['items']),2)
        self.assertEqual(page.json()['items'][0]['total'],{'$numberDecimal':'10.25'})
        rest=self.api.get('/api/local/history/orders',params={'after':page.json()['next_cursor'],'limit':2})
        self.assertEqual(len(rest.json()['items']),1)
        self.assertEqual(self.journal.status()['pending'],0)
        self.assertEqual(self.api.get('/api/local/commerce').json()['revenue_cents'],0)
        self.assertNotIn(b'PRIVATE-FIXTURE-NAME',self.journal.path.read_bytes())
        self.assertEqual(list(self.root.glob('.history-*')),[])

    def test_bad_phrase_wrong_unit_and_arbitrary_path_do_not_publish_or_leave_files(self):
        body=self.package();body['passphrase']='Wrong-fixture-phrase-2026'
        self.assertEqual(self.api.post('/api/local/history/import',json=body).status_code,409)
        self.assertEqual(self.api.post('/api/local/history/import',json=self.package('gym-londres')).status_code,409)
        self.assertEqual(self.api.post('/api/local/history/import',json={'path':'/etc/passwd'}).status_code,422)
        self.assertEqual(self.api.get('/api/local/history/tenants').status_code,409)
        self.assertEqual(self.api.get('/api/local/history/orders?limit=1000').status_code,409)
        self.assertIsNone(self.api.get('/api/local/history').json()['active'])
        self.assertEqual(list(self.root.glob('.history-*')),[])

    def test_staff_cannot_read_or_import_financial_history(self):
        body=self.package()
        for role in ('cashier','kitchen'):
            self.api.post('/api/local/auth/login',json=self.owner)
            staff={'username':'history-'+role,'password':'Fixture-staff-password-2026','role':role}
            self.api.post('/api/local/auth/accounts',json=staff)
            self.api.post('/api/local/auth/logout')
            self.api.post('/api/local/auth/login',json=staff)
            for url in ('/api/local/history','/api/local/history/orders'):
                self.assertEqual(self.api.get(url).status_code,403)
            self.assertEqual(self.api.post('/api/local/history/import',json=body).status_code,403)
        self.api.post('/api/local/auth/logout')
        self.assertEqual(self.api.get('/api/local/history').status_code,401)
