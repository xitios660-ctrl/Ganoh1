from contextlib import closing
import tempfile
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from desktop.offline_store import OfflineJournal
from desktop.local_api import create_local_app
from desktop import auth


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.journal=OfflineJournal(Path(self.temp.name)/'auth.sqlite','runner')
        self.token='x'*40
        self.api=TestClient(create_local_app(self.journal,self.token,require_operator=True))
        self.api.__enter__();self.addCleanup(self.api.__exit__,None,None,None)
        self.api.headers['Authorization']='Bearer '+self.token
        self.owner={'username':'owner-demo','password':'A-Long-Fixture-Password-2026'}

    def test_setup_once_cookie_http_only_and_logout_revokes(self):
        self.assertEqual(self.api.get('/api/local/status').status_code,401)
        result=self.api.post('/api/local/auth/setup',json=self.owner)
        self.assertEqual(result.status_code,200)
        self.assertIn('HttpOnly',result.headers['set-cookie'])
        self.assertIn('SameSite=strict',result.headers['set-cookie'])
        self.assertEqual(self.api.get('/api/local/status').status_code,200)
        self.assertEqual(self.api.post('/api/local/auth/setup',json=self.owner).status_code,409)
        self.api.post('/api/local/auth/logout')
        self.assertEqual(self.api.get('/api/local/status').status_code,401)
        self.assertEqual(self.api.post('/api/local/auth/login',json=self.owner).status_code,200)

    def test_cashier_cannot_withdraw_or_escalate_to_owner(self):
        self.api.post('/api/local/auth/setup',json=self.owner)
        staff={'username':'cashier-demo','password':'Another-Fixture-Password-2026','role':'cashier'}
        self.assertEqual(self.api.post('/api/local/auth/accounts',json=staff).status_code,200)
        self.api.post('/api/local/auth/logout')
        self.assertEqual(self.api.post('/api/local/auth/login',json=staff).status_code,200)
        body={'operation_id':str(uuid.uuid4()),'kind':'cash.withdraw','data':{'business_id':str(uuid.uuid4()),'amount_cents':1,'description':'Tentativa inválida'}}
        self.assertEqual(self.api.post('/api/local/commerce',json=body).status_code,403)
        self.assertEqual(self.api.post('/api/local/auth/accounts',json={**staff,'username':'escalation','role':'owner'}).status_code,403)
        self.assertEqual(self.journal.status()['pending'],0)

    def test_lockout_and_no_plaintext_password(self):
        auth.create(self.journal,**self.owner,first=True)
        for _ in range(5):
            with self.assertRaises(auth.AuthError):auth.login(self.journal,self.owner['username'],'wrong-password')
        with self.assertRaises(auth.AuthError):auth.login(self.journal,**self.owner)
        with closing(self.journal._connect()) as db:
            row=db.execute('SELECT * FROM operators').fetchone()
            self.assertNotEqual(row['password_hash'],self.owner['password'].encode())
            self.assertEqual(row['failures'],5)
            self.assertGreater(row['locked_until'],0)

    def test_operator_audit_commits_with_business_event(self):
        self.api.post('/api/local/auth/setup',json=self.owner)
        operation=str(uuid.uuid4())
        body={'operation_id':operation,'kind':'cash.deposit','data':{'business_id':str(uuid.uuid4()),'amount_cents':100,'description':'Entrada autorizada'}}
        self.assertEqual(self.api.post('/api/local/commerce',json=body).status_code,200)
        from contextlib import closing
        with closing(self.journal._connect()) as db:
            row=db.execute('SELECT * FROM event_actors WHERE operation_id=?',(operation,)).fetchone()
            self.assertEqual(row['role'],'owner')
        self.assertTrue(self.api.post('/api/local/commerce',json=body).json()['already_exists'])

    def test_owner_disables_staff_and_cannot_remove_last_owner(self):
        self.api.post('/api/local/auth/setup',json=self.owner)
        owner_id=self.api.get('/api/local/auth').json()['actor']['actor_id']
        staff={'username':'disable-staff','password':'Staff-Password-Fixture-2026','role':'cashier'}
        actor_id=self.api.post('/api/local/auth/accounts',json=staff).json()['actor_id']
        old=auth.login(self.journal,staff['username'],staff['password'])
        self.assertEqual(self.api.post(f'/api/local/auth/accounts/{actor_id}/disable',json={}).status_code,200)
        self.assertIsNone(auth.actor(self.journal,old))
        with self.assertRaises(auth.AuthError):auth.login(self.journal,staff['username'],staff['password'])
        self.assertEqual(self.api.post(f'/api/local/auth/accounts/{owner_id}/disable',json={}).status_code,409)
        new='Fresh-Staff-Fixture-Password-2026'
        self.assertEqual(self.api.post(f'/api/local/auth/accounts/{actor_id}/activate',json={'password':new}).status_code,200)
        self.assertIsNotNone(auth.login(self.journal,staff['username'],new))
