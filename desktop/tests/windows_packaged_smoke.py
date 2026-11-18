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
                    if client.get('/api/local/status').status_code == 200:
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
            operation = {'operation_id': str(uuid.uuid4()), 'sale_id': 'restart-smoke', 'items': [{'sku': 'lanche-demo', 'quantity': 1}]}
            response = client.post('/api/local/sales', json=operation)
            assert response.status_code == 200, response.text
            assert client.get('/api/local/status').json()['pending'] == 1
        finally:
            stop(child, client)
        if args.installer:
            install()  # Reinstall/upgrade must preserve the existing encrypted journal and key.
        child, client = run()
        try:
            status = client.get('/api/local/status').json()
            assert status['pending'] == 1 and status['sqlite_integrity'] == 'ok', status
            assert client.post('/api/local/sales', json=operation).json()['already_exists']
            assert len(client.get('/api/local/sales').json()['items']) == 1
        finally:
            stop(child, client)
        dbfile = Path(folder) / 'GANOH-Demo' / 'runner' / 'journal.sqlite3'
        assert not dbfile.read_bytes().startswith(b'SQLite format')
        if args.installer:
            uninstallers = list(install_dir.glob('Uninstall*.exe'))
            assert len(uninstallers) == 1
            subprocess.run([str(uninstallers[0]), '/S'], env=env, check=True, timeout=180)
            assert dbfile.exists() and dbfile.with_name('database-key.dpapi').exists()
        print('PASS: encrypted Windows backend, DPAPI, hard restart, idempotent retry and data preservation')


if __name__ == '__main__':
    main()
