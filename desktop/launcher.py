"""Packaged local backend entry point. No central database credentials."""
import argparse
import json
import os
import secrets
import socket
import sys
from pathlib import Path

import uvicorn
from desktop.local_api import create_local_app
from desktop.offline_store import OfflineJournal
from desktop.snapshots import apply_page, catalog
from desktop.sync_transport import SyncTransport
from desktop.windows_secrets import load_secret, save_secret


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--unit', required=True, choices=['runner', 'gym-londres'])
    parser.add_argument('--demo', action='store_true', help='Fictitious catalog, no real transactions')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Packaged launcher requires Windows and DPAPI')
    directory = Path(os.environ['LOCALAPPDATA']) / 'GANOH-Demo' / args.unit
    key_file = directory / 'database-key.dpapi'
    if not key_file.exists():
        if (directory / 'journal.sqlite3').exists():
            raise RuntimeError('Database key missing; restore protected key before continuing')
        save_secret(key_file, secrets.token_bytes(32))
    journal = OfflineJournal(directory / 'journal.sqlite3', args.unit, encryption_key=load_secret(key_file))
    # Stable device identifier is stored in the encrypted database, not recreated on restart.
    from contextlib import closing
    import uuid
    with closing(journal._connect()) as db:
        db.execute("INSERT OR IGNORE INTO metadata VALUES('device_id',?)", (str(uuid.uuid4()),))
    if args.demo and not catalog(journal):
        apply_page(journal, {'unit': args.unit, 'generation': 'demo-seed-v1', 'items': [
            {'sku': 'lanche-demo', 'name': 'Lanche demonstração', 'quantity': 100,
             'price_cents': 1000, 'version': 1}], 'done': True, 'next_cursor': None,
            'created_at': None}, None)
    transport = None
    # Provisioned separately by support, with device token protected by DPAPI.
    settings = directory / 'sync.json'
    if settings.exists():
        origin = json.loads(settings.read_text())['origin']
        transport = SyncTransport(origin, load_secret(directory / 'device-token.dpapi').decode())
    token = sys.stdin.readline().strip()
    if len(token) < 32:
        raise RuntimeError('Desktop session missing')
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'frontend' / 'build'
    app = create_local_app(journal, token, transport=transport, frontend=root)
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(128)
    print(json.dumps({'port': listener.getsockname()[1]}), flush=True)
    try:
        uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='warning')).run(sockets=[listener])
    finally:
        if transport:
            transport.close()
        listener.close()


if __name__ == '__main__':
    main()
