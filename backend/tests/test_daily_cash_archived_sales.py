"""Both daily cash endpoints must retain archived revenue without duplicates."""
import ast
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytz


class Collection:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, *_args):
        self.result = [r for r in self.rows if r.get('store') == query['store']
                       and ('status' not in query or r.get('status') in query['status']['$in'])]
        return self

    def sort(self, *_args):
        return self

    async def to_list(self, _limit):
        return list(self.result)


@pytest.mark.parametrize('filename', ['server.py', 'routers/cash.py'])
def test_archived_sale_retained_and_delivered_copy_counted_once(filename):
    # Load the actual endpoint and date helpers without starting the application.
    tree = ast.parse((Path(__file__).resolve().parents[1] / filename).read_text())
    names = {'get_today_cash', '_filter_since', '_parse_iso_utc'}
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
    tz = pytz.timezone('America/Sao_Paulo')
    today = datetime.now(tz).replace(hour=10, minute=0, second=0, microsecond=0)
    def sale(oid, amount, days=0):
        from datetime import timedelta
        return dict(id=oid, store='gym-londres', status='delivered', payment_method='credit',
                    total=amount, created_at=(today-timedelta(days=days)).isoformat())
    live = sale('live', 507.10)
    archived = sale('archived', 51.50)
    db = SimpleNamespace(orders=Collection([live]),
                         order_history=Collection([live, archived, archived, sale('yesterday', 80, 1)]),
                         pix_adjustments=Collection([]))
    namespace = dict(datetime=datetime, pytz=pytz, BRAZIL_TZ=tz, db=db)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), namespace)
    store = SimpleNamespace(value='gym-londres') if filename == 'server.py' else 'gym-londres'
    summary = asyncio.run(namespace['get_today_cash'](store))
    assert summary['total'] == pytest.approx(558.60)
    assert summary['order_count'] == 2
    assert summary['shifts']['morning']['total'] == pytest.approx(558.60)
    assert summary['shifts']['morning']['by_payment']['credit'] == pytest.approx(558.60)
