"""Production order reads must not launch jobs when automation is disabled."""
import ast
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch


def handler(name, db):
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text())
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    node.decorator_list = []
    node.returns = None
    for arg in node.args.args:
        arg.annotation = None
    namespace = {'os': os, 'db': db, 'restricted': lambda: False}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<handler>', 'exec'), namespace)
    return namespace[name]


class MigrationOrderReadsTests(TestCase):
    def db_with_orders(self, rows):
        db = MagicMock()
        cursor = db.orders.find.return_value
        cursor.sort.return_value = cursor
        cursor.to_list = AsyncMock(return_value=rows)
        db.orders.update_one = AsyncMock(side_effect=AssertionError('payment write'))
        db.orders.delete_many = AsyncMock(side_effect=AssertionError('order deletion'))
        db.order_history.insert_one = AsyncMock(side_effect=AssertionError('history write'))
        return db

    def test_default_kitchen_poll_does_not_archive(self):
        rows = [{'id': 'existing', 'status': 'ready'}]
        db = self.db_with_orders(rows)
        with patch.dict(os.environ, SCHEDULER_ENABLED='false'):
            result = asyncio.run(handler('get_orders', db)(SimpleNamespace(value='runner')))
        self.assertEqual(result, {'orders': rows})
        db.orders.find.assert_called_once_with({'store': 'runner'}, {'_id': 0})
        db.orders.delete_many.assert_not_awaited()
        db.order_history.insert_one.assert_not_awaited()

    def test_pending_pix_poll_does_not_trigger_payment_verification(self):
        rows = [{'id': 'existing', 'pix_proof': 'existing-proof'}]
        db = self.db_with_orders(rows)
        with patch.dict(os.environ, SCHEDULER_ENABLED='false'):
            result = asyncio.run(handler('get_pending_pix_orders', db)(SimpleNamespace(value='gym-londres')))
        self.assertEqual(result, {'orders': rows})
        db.orders.update_one.assert_not_awaited()
