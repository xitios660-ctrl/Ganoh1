"""TV capability tests use only a disposable local replica set."""
import hashlib
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from pymongo import MongoClient
from backend.sync_v1.service import create_app
from backend.sync_v1.owner_auth import provision


class TVAccess(unittest.TestCase):
    def setUp(self):
        self.mongo = MongoClient('mongodb://127.0.0.1:27028/?directConnection=true', serverSelectionTimeoutMS=3000)
        self.db = self.mongo['ganoh_sync_test_tv_' + uuid.uuid4().hex]
        self.addCleanup(self.mongo.close)
        self.addCleanup(lambda: self.mongo.drop_database(self.db.name))
        self.client = TestClient(create_app(self.db)); self.addCleanup(self.client.close)
        self.owner = provision(self.db, 'owner-fixture', 'Owner-Fixture-Password-2026', ['runner', 'gym-londres'])
        token = self.client.post('/api/sync/v1/owner/login', json={'username':'owner-fixture','password':'Owner-Fixture-Password-2026'}).json()['access_token']
        self.owner_headers = {'Authorization': 'Bearer ' + token}
        self.data = {'username':'tv-fixture','password':'TV-Fixture-Password-2026','units':['runner']}
        for unit in ('runner','gym-londres'):
            self.db.stock.insert_one({'unit':unit,'sku':'lanche','name':'Fixture','quantity':10,'price_cents':100,'version':1})

    def account(self):
        r = self.client.post('/api/sync/v1/owner/tv-accounts', headers=self.owner_headers, json=self.data)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['account_id']

    def login(self):
        r = self.client.post('/api/sync/v1/tv/login',json=self.data)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['scope'],'tv:read')
        self.assertEqual(r.headers['cache-control'],'no-store')
        return {'Authorization':'Bearer '+r.json()['access_token']}

    def test_tv_reads_only_authorized_units_and_cannot_write_or_manage(self):
        self.account(); headers = self.login()
        r=self.client.get('/api/sync/v1/tv/overview',headers=headers)
        self.assertEqual(r.status_code,200);self.assertEqual([u['unit'] for u in r.json()['units']],['runner'])
        self.assertIsNone(r.json()['units'][0]['local_pending'])
        self.assertEqual(self.client.get('/api/sync/v1/tv/stock?unit=gym-londres',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/api/sync/v1/tv/stock?unit=runner',headers=headers).status_code,200)
        for path in ('/api/sync/v1/batch','/api/sync/v1/conflicts/review','/api/sync/v1/owner/tv-accounts'):
            self.assertEqual(self.client.post(path,headers=headers,json={}).status_code,401,path)
        self.assertEqual(self.client.get('/api/sync/v1/owner/overview',headers=headers).status_code,401)
        self.assertEqual(self.db.ledger.count_documents({}),0)
        self.assertEqual(self.db.sales.count_documents({}),0)

    def test_owner_and_tv_credentials_are_not_interchangeable(self):
        self.account()
        r=self.client.post('/api/sync/v1/tv/login',json={'username':'owner-fixture','password':'Owner-Fixture-Password-2026'})
        self.assertEqual(r.status_code,401)
        denied=self.client.get('/api/sync/v1/tv/overview',headers=self.owner_headers)
        self.assertEqual(denied.status_code,401);self.assertEqual(denied.headers['cache-control'],'no-store')
        headers=self.login()
        digest=hashlib.sha256(headers['Authorization'][7:].encode()).hexdigest()
        self.assertIsNotNone(self.db.tv_sessions.find_one({'token_hash':digest}))
        self.assertIsNone(self.db.owner_sessions.find_one({'token_hash':digest}))
        row=self.db.tv_accounts.find_one({});self.assertNotIn('password',row)
        listed=self.client.get('/api/sync/v1/owner/tv-accounts',headers=self.owner_headers).json()
        self.assertNotIn('password_hash',str(listed));self.assertNotIn(self.data['password'],str(listed))

    def test_revoke_and_logout_expire_sessions_and_are_auditable(self):
        account=self.account(); headers=self.login()
        self.client.post('/api/sync/v1/tv/logout',headers=headers)
        self.assertEqual(self.client.get('/api/sync/v1/tv/overview',headers=headers).status_code,401)
        headers=self.login()
        path='/api/sync/v1/owner/tv-accounts/'+account+'/revoke'
        for _ in range(2):self.assertEqual(self.client.post(path,headers=self.owner_headers).status_code,200)
        self.assertEqual(self.client.get('/api/sync/v1/tv/overview',headers=headers).status_code,401)
        self.assertEqual(self.db.tv_audit.count_documents({'kind':'revoke'}),1)
        self.assertEqual(self.db.tv_sessions.count_documents({}),0)

    def test_parent_scope_and_revocation_apply_without_relogin(self):
        self.data['units']=['runner','gym-londres'];self.account();headers=self.login()
        self.db.reviewers.update_one({'_id':self.owner},{'$set':{'units':['gym-londres']}})
        r=self.client.get('/api/sync/v1/tv/overview',headers=headers)
        self.assertEqual([u['unit'] for u in r.json()['units']],['gym-londres'])
        self.assertEqual(self.client.get('/api/sync/v1/tv/stock?unit=runner',headers=headers).status_code,403)
        self.db.reviewers.update_one({'_id':self.owner},{'$set':{'revoked':True}})
        self.assertEqual(self.client.get('/api/sync/v1/tv/overview',headers=headers).status_code,401)

    def test_lockout_expiry_no_public_provision_or_unit_escalation(self):
        self.assertEqual(self.client.post('/api/sync/v1/owner/tv-accounts',json=self.data).status_code,401)
        self.db.reviewers.update_one({'_id':self.owner},{'$set':{'units':['runner']}})
        invalid={**self.data,'units':['gym-londres']}
        self.assertEqual(self.client.post('/api/sync/v1/owner/tv-accounts',headers=self.owner_headers,json=invalid).status_code,403)
        reused={**self.data,'password':'Owner-Fixture-Password-2026'}
        self.assertEqual(self.client.post('/api/sync/v1/owner/tv-accounts',headers=self.owner_headers,json=reused).status_code,422)
        self.account();headers=self.login()
        self.db.tv_sessions.update_many({}, {'$set':{'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)}})
        self.assertEqual(self.client.get('/api/sync/v1/tv/overview',headers=headers).status_code,401)
        for _ in range(5):self.assertEqual(self.client.post('/api/sync/v1/tv/login',json={**self.data,'password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/api/sync/v1/tv/login',json=self.data).status_code,401)

    def test_snapshot_cursor_cannot_be_shared_between_tv_accounts(self):
        self.account();a=self.login()
        self.db.stock.insert_many([{'unit':'runner','sku':'sku'+str(i),'quantity':1,'price_cents':10,'version':1} for i in range(105)])
        page=self.client.get('/api/sync/v1/tv/stock?unit=runner',headers=a).json()
        self.data['username']='tv-fixture-two';self.account();b=self.login()
        url='/api/sync/v1/tv/stock?unit=runner&cursor='+page['next_cursor']
        self.assertEqual(self.client.get(url,headers=b).status_code,410)
        self.assertEqual(self.client.get(url,headers=a).status_code,200)
        self.assertEqual(self.client.get('/api/sync/v1/owner/stock?unit=runner&cursor='+page['next_cursor'],headers=self.owner_headers).status_code,410)

    def test_account_management_is_owner_scoped_and_duplicate_creation_rolls_back(self):
        account=self.account()
        duplicate=self.client.post('/api/sync/v1/owner/tv-accounts',headers=self.owner_headers,json=self.data)
        self.assertEqual(duplicate.status_code,409)
        self.assertEqual(self.db.tv_accounts.count_documents({}),1)
        self.assertEqual(self.db.tv_audit.count_documents({'kind':'create'}),1)
        provision(self.db,'other-owner','Other-Owner-Fixture-2026',['gym-londres'])
        session=self.client.post('/api/sync/v1/owner/login',json={'username':'other-owner','password':'Other-Owner-Fixture-2026'}).json()['access_token']
        other={'Authorization':'Bearer '+session}
        self.assertEqual(self.client.get('/api/sync/v1/owner/tv-accounts',headers=other).json()['accounts'],[])
        self.assertEqual(self.client.post('/api/sync/v1/owner/tv-accounts/'+account+'/revoke',headers=other).status_code,404)
        self.assertFalse(self.db.tv_accounts.find_one({'_id':account})['revoked'])
