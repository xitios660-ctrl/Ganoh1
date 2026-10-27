"""Billing boundary tests use a fake app; never connect to production data."""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import billing_access as billing

class BillingTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'GANOH_SERVICE_SUSPENDED':'true', 'GANOH_GRACE_UNTIL':'2030-01-02T00:00:00Z'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls = []
        self.data = {'orders':[{'id':'order-1','status':'received','total':99,'items':[{'name':'Cafe','price':99,'quantity':1}], 'pix_proof_base64':'secret'}]}
        async def app(scope, receive, send):
            self.calls.append(scope['path'])
            await send({'type':'http.response.start','status':200,'headers':[(b'content-type', b'application/json')]})
            await send({'type':'http.response.body','body':json.dumps(self.data).encode()})
        self.gate = billing.BillingGate(app)

    def request(self, path, method='GET', now=None):
        async def run():
            result=[]
            async def send(message): result.append(message)
            await self.gate({'type':'http','path':path,'method':method},None,send)
            return result
        with patch.object(billing.time,'time',return_value=now if now is not None else billing.deadline()-1):
            return asyncio.run(run())

    def test_manager_and_financials_blocked_even_with_valid_session(self):
        for path in ['/gestor/dashboard','/GESTOR/dashboard','/api/%67estor/dashboard','/api/gestor/../cash/runner/today','//api//gestor/dashboard','/auth','/api/auth/login','/api/cash/runner/drawer','/api/admin/clear-data','/api/expenses/export-contador','/api/whatsapp/inbound','/api/live/runner/snapshot','/runner/live','/api/prazo/debts','/api/orders/runner/history','/docs','/openapi.json']:
            for method in ['GET','POST','PUT','PATCH','DELETE','OPTIONS','HEAD']:
                self.assertEqual(self.request(path,method)[0]['status'],403,(path,method))
        self.assertEqual(self.calls,[])

    def test_operational_routes_pass_through(self):
        for path,method in [('/api/menu/runner','GET'),('/api/prazo/customers/lookup','GET'),('/api/staff/unlock','POST'),('/api/orders','POST'),('/api/orders/runner/id/status','PUT'),('/api/stock/runner','GET'),('/runner/cozinha','GET'),('/api/kitchen/runner/stats','GET'),('/api/cash/runner/today','GET')]:
            self.assertEqual(self.request(path,method)[0]['status'],200)
        self.assertEqual(len(self.calls),9)

        for path in ['/api/cash/runner/today', '/api/kitchen/runner/stats']:
            for method in ['POST', 'PUT', 'PATCH', 'DELETE']:
                self.assertEqual(self.request(path, method)[0]['status'],403)

    def test_kitchen_lists_expose_only_order_values_without_modifying_source(self):
        for path in ['/api/orders/runner','/api/orders/runner/pending-pix']:
            response=self.request(path)
            body=json.loads(response[1]['body'])
            self.assertEqual(body['orders'][0],{'id':'order-1','status':'received','total':99,'items':[{'name':'Cafe','price':99,'quantity':1}]})
            self.assertEqual(self.data['orders'][0]['total'],99)
            self.assertIn((b'cache-control',b'no-store, max-age=0'), response[0]['headers'])
        for path in ['/api/orders/runner/order-1','/api/prazo/customers']:
            body=json.loads(self.request(path)[1]['body'])
            self.assertEqual(body['orders'][0],{'id':'order-1','status':'received','items':[{'name':'Cafe','quantity':1}]})

    def test_exact_deadline_blocks_reads_and_writes_without_restart(self):
        end=billing.deadline()
        self.assertEqual(self.request('/api/orders','POST',end-0.01)[0]['status'],200)
        self.calls.clear()
        for path in ['/','/api/orders','/api/orders/sync','/runner/cozinha','/static/js/main.js']:
            for method in ['GET','POST','PUT','DELETE']:
                self.assertEqual(self.request(path,method,end)[0]['status'],503)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.request('/healthz',now=end)[0]['status'],200)

    def test_status_contains_server_time_and_fixed_deadline(self):
        end=billing.deadline()
        first=json.loads(self.request('/api/billing/status',now=end-100)[1]['body'])
        second=json.loads(self.request('/api/billing/status',now=end-10)[1]['body'])
        self.assertEqual(first['expires_at'],second['expires_at'])
        self.assertEqual(second['mode'],'grace')
        self.assertTrue(second['financials_hidden'])
        self.assertTrue(second['kitchen_values_visible'])
        ended=json.loads(self.request('/api/billing/status',now=end)[1]['body'])
        self.assertFalse(ended['kitchen_values_visible'])

    def test_invalid_or_missing_deadline_fails_closed(self):
        for value in ['', 'invalid', '2030-01-02T00:00:00']:
            os.environ['GANOH_GRACE_UNTIL']=value
            self.assertEqual(self.request('/api/orders',now=100)[0]['status'],503)

    def test_reactivation_restores_original_response(self):
        os.environ['GANOH_SERVICE_SUSPENDED']='false'
        response=self.request('/api/gestor/dashboard')
        self.assertEqual(json.loads(response[1]['body']),self.data)

    def test_websockets_denied_during_grace(self):
        messages=[]
        async def send(message): messages.append(message)
        asyncio.run(self.gate({'type':'websocket','path':'/ws'},None,send))
        self.assertEqual(messages,[{'type':'websocket.close','code':1008}])

if __name__=='__main__': unittest.main()
