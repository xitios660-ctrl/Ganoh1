import tempfile
import unittest
import uuid
from pathlib import Path
from fastapi.testclient import TestClient
from desktop.offline_store import OfflineJournal,OfflineError
from desktop.commerce import record,summary
from desktop.orders import list_orders
from desktop.snapshots import apply_page
from desktop.local_api import create_local_app

class OrderTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.journal=OfflineJournal(Path(self.temp.name)/'orders.sqlite','runner')
  self.journal.record_sale(sale_id='sale',total_cents=100,payment_method='cash',items=[{'sku':'lanche','name':'Lanche fictício','quantity':1}])
 def test_progress_is_versioned_idempotent_and_does_not_change_money(self):
  data={'business_id':str(uuid.uuid4()),'sale_id':'sale','base_version':1,'status':'preparing'};op=str(uuid.uuid4())
  record(self.journal,operation_id=op,kind='order.status',data=data)
  record(self.journal,operation_id=op,kind='order.status',data=data)
  self.assertEqual(list_orders(self.journal)[0]['version'],2)
  self.assertEqual(list_orders(self.journal)[0]['status'],'preparing')
  self.assertEqual(summary(self.journal)['cash_cents'],100)
  with self.assertRaises(OfflineError):record(self.journal,operation_id=str(uuid.uuid4()),kind='order.status',data={**data,'business_id':str(uuid.uuid4()),'status':'delivered'})
 def test_kitchen_operator_can_only_change_kitchen_progress(self):
  token='x'*40;headers={'Authorization':'Bearer '+token}
  with TestClient(create_local_app(self.journal,token,require_operator=True)) as api:
   api.post('/api/local/auth/setup',headers=headers,json={'username':'owner-demo','password':'Long-Fixture-Password-2026'})
   api.post('/api/local/auth/accounts',headers=headers,json={'username':'kitchen-demo','password':'Long-Kitchen-Fixture-2026','role':'kitchen'})
   api.post('/api/local/auth/logout',headers=headers)
   api.post('/api/local/auth/login',headers=headers,json={'username':'kitchen-demo','password':'Long-Kitchen-Fixture-2026'})
   self.assertEqual(api.get('/api/local/commerce',headers=headers).status_code,403)
   self.assertEqual(api.get('/api/local/sales',headers=headers).status_code,403)
   rows=api.get('/api/local/orders',headers=headers).json()['items']
   self.assertNotIn('total_cents',rows[0]);self.assertNotIn('price_cents',rows[0]['items'][0])
   self.assertNotIn('active_shift',api.get('/api/local/status',headers=headers).json())
   body={'operation_id':str(uuid.uuid4()),'kind':'order.status','data':{'business_id':str(uuid.uuid4()),'sale_id':'sale','base_version':1,'status':'preparing'}}
   self.assertEqual(api.post('/api/local/commerce',headers=headers,json=body).status_code,200)
   body.update(kind='cash.deposit',operation_id=str(uuid.uuid4()),data={'business_id':str(uuid.uuid4()),'amount_cents':100,'description':'Tentativa proibida'})
   self.assertEqual(api.post('/api/local/commerce',headers=headers,json=body).status_code,403)
