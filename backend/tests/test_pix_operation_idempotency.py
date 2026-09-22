"""Isolated API tests. SQLite adapter models Mongo's durable unique _id constraint.

This does not replace integration tests against a disposable MongoDB deployment.
No production database or application startup hooks are used.
"""
import asyncio
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MONGO_URL='mongodb://127.0.0.1:27017', DB_NAME='test_only', LITELLM_LOCAL_MODEL_COST_MAP='True')
import server


class DurableCollection:
    def __init__(self, path):
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)')

    async def insert_one(self, document):
        try:
            with sqlite3.connect(self.path) as db:
                db.execute('INSERT INTO documents VALUES (?, ?)',
                           (document.get('_id', document['id']), json.dumps(document)))
        except sqlite3.IntegrityError as exc:
            raise DuplicateKeyError('duplicate operation') from exc

    async def find_one(self, query, projection=None):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT body FROM documents WHERE id=?', (query['_id'],)).fetchone()
        if row is None:
            return None
        document = json.loads(row[0])
        document.pop('_id', None)
        return document

    def find(self, query, projection=None):
        with sqlite3.connect(self.path) as db:
            documents = [json.loads(row[0]) for row in db.execute('SELECT body FROM documents')]
        documents = [d for d in documents if d['store'] == query['store'] and not d.get('removed')]
        for doc in documents:
            doc.pop('_id', None)
        class Cursor:
            async def to_list(self, limit):
                return documents[:limit]
        return Cursor()


def bind_database(path):
    from types import SimpleNamespace
    server.db = SimpleNamespace(pix_adjustments=DurableCollection(path))


def post_in_process(path, payload):
    bind_database(path)
    result = TestClient(server.app).post('/api/pix-adjustments/add', json=payload)
    assert result.status_code == 200


@pytest.fixture
def client(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / 'fake-pix.sqlite'
    monkeypatch.setattr(server, 'db', SimpleNamespace(pix_adjustments=DurableCollection(path)))
    return TestClient(server.app), path


def payload():
    return {'store': 'runner', 'amount': 100, 'description': 'Test PIX', 'operation_id': str(uuid4())}


def test_100_pix_refresh_replay_and_new_process_remain_100(client):
    api, path = client
    request = payload()
    first = api.post('/api/pix-adjustments/add', json=request)
    assert first.status_code == 200
    assert first.json()['adjustment']['amount'] == 100
    for _ in range(4):
        assert api.get('/api/pix-adjustments/runner').json()['total_added'] == 100
    replay = api.post('/api/pix-adjustments/add', json=request)
    assert replay.json()['replayed'] is True
    assert replay.json()['adjustment'] == first.json()['adjustment']
    process = multiprocessing.get_context('spawn').Process(target=post_in_process, args=(str(path), request))
    process.start()
    process.join(20)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail('Restart test timed out')
    assert process.exitcode == 0
    state = api.get('/api/pix-adjustments/runner').json()
    assert state['total_added'] == 100
    assert len(state['adjustments']) == 1


def test_conflicting_replay_is_rejected_and_new_operation_is_allowed(client):
    api, _ = client
    request = payload()
    assert api.post('/api/pix-adjustments/add', json=request).status_code == 200
    assert api.post('/api/pix-adjustments/add', json={**request, 'amount': 101}).status_code == 409
    assert api.post('/api/pix-adjustments/add', json={**request, 'description': 'Changed'}).status_code == 409
    assert api.get('/api/pix-adjustments/runner').json()['total_added'] == 100
    assert api.post('/api/pix-adjustments/add', json={**request, 'operation_id': str(uuid4())}).status_code == 200
    assert api.get('/api/pix-adjustments/runner').json()['total_added'] == 200


def test_parallel_replays_insert_once(client):
    api, path = client
    request = payload()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: api.post('/api/pix-adjustments/add', json=request), range(10)))
    assert all(r.status_code == 200 for r in results)
    assert sum(not r.json().get('replayed', False) for r in results) == 1
    assert api.get('/api/pix-adjustments/runner').json()['total_added'] == 100


def test_removed_operation_cannot_be_resurrected(client):
    api, path = client
    request = payload()
    first = api.post('/api/pix-adjustments/add', json=request).json()['adjustment']
    with sqlite3.connect(path) as db:
        row_id, body = db.execute('SELECT id,body FROM documents').fetchone()
        document = json.loads(body)
        document['removed'] = True
        db.execute('UPDATE documents SET body=? WHERE id=?', (json.dumps(document), row_id))
    replay = api.post('/api/pix-adjustments/add', json=request).json()
    assert replay['replayed'] is True
    assert replay['adjustment']['id'] == first['id']
    assert replay['adjustment']['removed'] is True
    assert api.get('/api/pix-adjustments/runner').json()['total_added'] == 0


def test_legacy_input_still_accepted_and_invalid_key_rejected(client):
    api, _ = client
    assert api.post('/api/pix-adjustments/add', json={'amount': 100, 'store': 'runner'}).status_code == 200
    assert api.post('/api/pix-adjustments/add', json={**payload(), 'operation_id': 'invalid'}).status_code == 422
