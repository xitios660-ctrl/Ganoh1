"""Windows-only restart/upgrade smoke test, using an isolated LOCALAPPDATA."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
# The workflow runs this file directly, so explicitly include the project root.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exe')
    parser.add_argument('--installer')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Windows required')
    with tempfile.TemporaryDirectory() as folder:
        env = {**os.environ, 'LOCALAPPDATA': folder}
        token = secrets.token_hex(32)
        install_dir = Path(folder) / 'installed'
        def install():
            subprocess.run([str(Path(args.installer).resolve()), '/S', '/D=' + str(install_dir)],
                           env=env, check=True, timeout=180)
        if args.installer:
            install()
            command = [str(install_dir / 'resources' / 'backend' / 'ganoh-local.exe')]
        else:
            command = [args.exe] if args.exe else [sys.executable, '-m', 'desktop.launcher']
        def run():
            child = subprocess.Popen(command + ['--unit', 'runner', '--demo'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
            child.stdin.write(token + '\n'); child.stdin.flush(); child.stdin.close()
            line = child.stdout.readline()
            if not line:
                child.wait(timeout=5)
                raise RuntimeError('Backend failed to start')
            origin = 'http://127.0.0.1:' + str(json.loads(line)['port'])
            client = httpx.Client(base_url=origin, headers={'Authorization': 'Bearer ' + token}, trust_env=False)
            for _ in range(100):
                try:
                    response=client.get('/api/local/auth')
                    if response.status_code == 200:
                        path='/api/local/auth/login' if response.json()['configured'] else '/api/local/auth/setup'
                        result=client.post(path,json={'username':'demo-owner','password':'Fixture-Only-Password-2026'})
                        assert result.status_code==200, result.text
                        return child, client
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            child.kill(); child.wait(); client.close()
            raise RuntimeError('Backend readiness timed out')
        def stop(child, client):
            client.close(); child.terminate(); child.wait(timeout=10); child.stdout.close()
        child, client = run()
        try:
            opening = {'operation_id': str(uuid.uuid4()), 'kind': 'cash.open', 'data': {
                'business_id': str(uuid.uuid4()), 'shift_id': str(uuid.uuid4()), 'counted_cents': 0}}
            assert client.post('/api/local/commerce', json=opening).status_code == 200
            operation = {'operation_id': str(uuid.uuid4()), 'sale_id': 'restart-smoke', 'items': [{'sku': 'lanche-demo', 'quantity': 1}]}
            if args.exe or args.installer:
                import re
                html = client.get('/desktop-demo')
                assert html.status_code == 200 and 'id="root"' in html.text
                script = re.search(r'<script[^>]+src="(/static/[^"]+)"', html.text)
                assert script and client.get(script.group(1)).status_code == 200
                assert "frame-ancestors 'none'" in html.headers['content-security-policy']
            response = client.post('/api/local/sales', json=operation)
            assert response.status_code == 200, response.text
            assert client.get('/api/local/status').json()['pending'] == 2
            expense = {'operation_id': str(uuid.uuid4()), 'kind': 'expense.create', 'data': {
                'business_id': str(uuid.uuid4()), 'amount_cents': 200, 'description': 'Despesa fictícia smoke'}}
            customer_id = str(uuid.uuid4())
            customer = {'operation_id': str(uuid.uuid4()), 'kind': 'customer.create', 'data': {
                'business_id': str(uuid.uuid4()), 'customer_id': customer_id, 'name': 'Cliente fictício smoke'}}
            assert client.post('/api/local/commerce', json=expense).status_code == 200
            assert client.post('/api/local/commerce', json=customer).status_code == 200
            assert client.get('/api/local/status').json()['pending'] == 4
        finally:
            stop(child, client)
        if args.installer:
            install()  # Reinstall/upgrade must preserve the existing encrypted journal and key.
        child, client = run()
        try:
            status = client.get('/api/local/status').json()
            assert status['pending'] == 4 and status['sqlite_integrity'] == 'ok', status
            assert client.post('/api/local/sales', json=operation).json()['already_exists']
            assert len(client.get('/api/local/sales').json()['items']) == 1
            assert client.post('/api/local/commerce', json=expense).json()['already_exists']
            commercial = client.get('/api/local/commerce').json()
            assert commercial['cash_cents'] == 800 and commercial['balanced']
            assert commercial['customers'][0]['customer_id'] == customer_id
            assert len(commercial['events']) == 3
            closing = {'operation_id': str(uuid.uuid4()), 'kind': 'cash.close', 'data': {
                'business_id': str(uuid.uuid4()), 'shift_id': opening['data']['shift_id'],
                'expected_cents': 800, 'counted_cents': 800}}
            assert client.post('/api/local/commerce', json=closing).status_code == 200
            assert client.get('/api/local/status').json()['active_shift'] is None
            recovery_phrase='Fixture-Recovery-Phrase-2026-Only'
            exported=client.post('/api/local/backup/export',json={'passphrase':recovery_phrase})
            assert exported.status_code==200,exported.text
            import base64
            verified=client.post('/api/local/backup/verify',json={'passphrase':recovery_phrase,'archive':base64.b64encode(exported.content).decode()})
            assert verified.status_code==200,verified.text
            assert verified.json()['verified'] and not verified.json()['active_database_changed']
            assert client.get('/api/local/status').json()['pending']==5
            # Exercise the exact packaged history route and codec dependencies.
            from bson import BSON, Decimal128
            from bson.timestamp import Timestamp
            from backend.data_bridge.archive import Writer,new_file
            from backend.data_bridge.unit_export import UNIT_FORMAT
            import hashlib
            historical=Path(folder)/'fixture-history.ganoh'
            raw=BSON.encode({'_id':'fixture-old-order','store':'runner','total':Decimal128('10.25'),
                             'created_at':'2026-11-21T16:30:00Z'})
            with new_file(historical) as output:
                writer=Writer(output,recovery_phrase,kind=UNIT_FORMAT)
                page=writer.page(raw)
                writer.finish({'archive_id':writer.id,'unit':'runner','source_database':'fixture-source',
                    'read_timestamp':Timestamp(100,1),'collections':[{'name':'orders','count':1,
                    'sha256':hashlib.sha256(raw).hexdigest(),'pages':[page]}]})
            historical_body={'archive':base64.b64encode(historical.read_bytes()).decode(),'passphrase':recovery_phrase}
            imported=client.post('/api/local/history/import',json=historical_body)
            assert imported.status_code==200,imported.text
            assert imported.json()['documents']==1
            assert client.get('/api/local/history/orders').json()['items'][0]['total']=={'$numberDecimal':'10.25'}
            assert not client.get('/api/local/history').json()['active']['operational_baseline_ready']
            assert client.get('/api/local/status').json()['pending']==5
        finally:
            stop(child, client)
        if args.installer:
            install()  # Upgrade preserves schema-4 imported history as well.
        child,client=run()
        try:
            assert client.get('/api/local/history').json()['active']['history_complete']
            assert client.get('/api/local/history/orders').json()['items'][0]['total']=={'$numberDecimal':'10.25'}
            assert client.post('/api/local/history/import',json=historical_body).json()['already_imported']
            assert client.get('/api/local/status').json()['pending']==5
        finally:
            stop(child,client)
        dbfile = Path(folder) / 'GANOH-Demo' / 'runner' / 'journal.sqlite3'
        assert not dbfile.read_bytes().startswith(b'SQLite format')
        if args.installer:
            uninstallers = list(install_dir.glob('Uninstall*.exe'))
            assert len(uninstallers) == 1
            # NSIS _?= disables the asynchronous temporary uninstaller copy;
            # wait() then waits for the actual uninstall before checking data/cleanup.
            subprocess.run([str(uninstallers[0]), '/S', '_?=' + str(install_dir)], env=env, check=True, timeout=180)
            assert dbfile.exists() and dbfile.with_name('database-key.dpapi').exists()
        print('PASS: encrypted Windows backend, DPAPI, hard restart, idempotent retry and commercial data preservation')


if __name__ == '__main__':
    main()
