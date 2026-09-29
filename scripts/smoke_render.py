"""Read-only production smoke checks on loopback after a PDF recovery release."""
import base64
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = 'http://127.0.0.1:' + os.environ.get('PORT', '10000')
USER = 'gestor'
PASSWORD = os.environ['GESTOR_PASSWORD']


def get(path, auth=False):
    headers = {}
    if auth:
        value = base64.b64encode(f'{USER}:{PASSWORD}'.encode()).decode()
        headers['Authorization'] = 'Basic ' + value
    with urlopen(Request(ROOT + path, headers=headers), timeout=12) as response:
        body = response.read()
        return json.loads(body) if path != '/' else body.decode()


def main():
    for _ in range(60):
        try:
            if get('/healthz').get('status') == 'ok':
                break
        except (HTTPError, URLError):
            time.sleep(2)
    else:
        raise RuntimeError('Health check did not become ready')

    assert 'Ganoh em preparação' not in get('/'), 'Preparation notice still visible'
    customers = get('/api/prazo/customers')['customers']
    debts = get('/api/prazo/debts')
    expenses = get('/api/expenses', True)['expenses']
    assert len(customers) >= 93 and len(expenses) >= 301
    assert len(debts['debts']) >= 64 and debts['total_prazo'] >= 6943.15 - .01
    for store in ('runner', 'gym-londres'):
        assert get('/api/menu/' + store)['items'], 'Public menu empty'
        assert len(get('/api/kitchen/menu/' + store)['items']) >= 160
        assert 'current_balance' in get('/api/cash/' + store + '/drawer')
    year = get('/api/gestor/chart/yearly?year=2026', True)
    result = get('/api/gestor/chart/yearly-with-expenses?year=2026', True)
    assert year['total_year'] >= 368856.69 - .01 and year['total_orders'] >= 8778
    assert result['total_revenue'] >= 368856.69 - .01
    assert result['total_expenses'] >= 56008.18 - .01
    assert len(get('/api/gestor/chart/weekly?date=2026-09-28', True)['data']) == 7
    print('GANOH smoke verified: site, gestor, 2 menus, customers, debts, expenses, yearly/weekly charts, cash drawers', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('GANOH smoke failed: ' + str(exc)[:180], file=sys.stderr, flush=True)
        sys.exit(1)
