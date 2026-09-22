"""Deployment regression tests; no live database or WhatsApp messages."""
import importlib
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, MagicMock
import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(MONGO_URL='mongodb://127.0.0.1:27017', DB_NAME='test_only',
                  GESTOR_PASSWORD='test-only-value', PRAZO_PASSWORD='test-only-value',
                  CLEAR_DATA_PASSWORD='test-only-value', LITELLM_LOCAL_MODEL_COST_MAP='True')
from fastapi.testclient import TestClient
import server


def test_whatsapp_admin_routes_require_login():
    client = TestClient(server.app)
    for route in ('status', 'qr', 'groups'):
        assert client.get('/api/whatsapp/' + route).status_code == 401
    for route in ('connect', 'set-target', 'join-group'):
        assert client.post('/api/whatsapp/' + route, json={}).status_code == 401


def test_startup_preserves_imported_accounts(monkeypatch):
    import asyncio
    fake = MagicMock()
    fake.tenants.find_one = AsyncMock(return_value={'username': 'gestor', 'password_hash': 'original'})
    fake.tenants.update_one = AsyncMock()
    fake.tenants.insert_one = AsyncMock()
    monkeypatch.setattr(server, 'db', fake)
    monkeypatch.setenv('SYNC_GESTOR_PASSWORD', 'false')
    asyncio.run(server.ensure_default_tenant())
    fake.tenants.update_one.assert_not_called()
    fake.tenants.insert_one.assert_not_called()


def test_startup_does_not_insert_historical_sales_or_start_scheduler(monkeypatch):
    import asyncio
    fake = MagicMock()
    fake.settings.find_one = AsyncMock(return_value=None)
    for name in ('orders', 'stock', 'pix_adjustments', 'prazo_debts', 'prazo_payments',
                 'prazo_partial_payments', 'cash_withdrawals', 'tenants'):
        getattr(fake, name).create_index = AsyncMock()
    fake.orders.insert_many = AsyncMock()
    monkeypatch.setattr(server, 'db', fake)
    monkeypatch.setattr(server, 'ensure_default_tenant', AsyncMock())
    historical = AsyncMock()
    monkeypatch.setattr(server, '_register_manual_morning_sales_runner_v1', historical)
    scheduler = MagicMock()
    monkeypatch.setattr(server, 'scheduler', scheduler)
    monkeypatch.setenv('SCHEDULER_ENABLED', 'false')
    asyncio.run(server.startup_db_client())
    historical.assert_not_called()
    fake.orders.insert_many.assert_not_called()
    scheduler.start.assert_not_called()


def test_maintenance_blocks_business_writes(monkeypatch):
    monkeypatch.setenv('MIGRATION_PENDING', 'true')
    sys.modules.pop('render_app', None)
    app = importlib.import_module('render_app').app
    client = TestClient(app)
    assert client.get('/healthz').json()['migration_pending'] is True
    for response in (client.get('/'), client.get('/gestor'),
                     client.post('/api/orders/runner', json={})):
        assert response.status_code == 503
        assert response.headers['Cache-Control'] == 'no-store'
        assert response.headers['Retry-After'] == '300'


def test_spa_reload_works_and_unknown_api_does_not_return_html(monkeypatch):
    if not (BACKEND.parent / 'frontend/build/index.html').exists():
        pytest.skip('Build frontend before running SPA integration check')
    monkeypatch.setenv('MIGRATION_PENDING', 'false')
    monkeypatch.setattr(server, 'db', MagicMock(command=AsyncMock(return_value={'ok': 1})))
    sys.modules.pop('render_app', None)
    app = importlib.import_module('render_app').app
    client = TestClient(app)
    assert client.get('/gestor').status_code == 200
    assert client.get('/api/not-a-route').status_code == 404
    assert client.get('/static/missing.js').status_code == 404
    assert client.get('/healthz').json()['status'] == 'ok'
