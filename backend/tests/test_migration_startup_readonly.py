"""Exercise the actual startup handler without importing the production app."""
import ast
import asyncio
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import unittest


class MigrationStartupTests(unittest.TestCase):
    def run_startup(self, skip):
        source = Path(__file__).resolve().parents[1] / 'server.py'
        tree = ast.parse(source.read_text())
        handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == 'startup_db_client')
        handler.decorator_list = []
        module = ast.Module(body=[handler], type_ignores=[])
        db = MagicMock()
        db.settings.find_one = AsyncMock(return_value=None)
        # Fail on any attempted collection/index mutation.
        for collection in ('orders', 'stock', 'pix_adjustments', 'prazo_debts',
                           'prazo_payments', 'prazo_partial_payments',
                           'cash_withdrawals', 'tenants', 'whatsapp_inbound'):
            getattr(db, collection).create_index = AsyncMock(
                side_effect=AssertionError('unexpected startup index write'))
        tenant = AsyncMock()
        scheduler = MagicMock()
        scope = dict(os=os, db=db, restricted=lambda: False,
                     ensure_default_tenant=tenant, scheduler=scheduler,
                     logger=logging.getLogger(__name__), STORE_WHATSAPP_GROUPS={})
        exec(compile(module, str(source), 'exec'), scope)
        with patch.dict(os.environ, GANOH_SKIP_STARTUP_REPAIRS=skip,
                        SYNC_GESTOR_PASSWORD='false', SCHEDULER_ENABLED='false'):
            asyncio.run(scope['startup_db_client']())
        return db, tenant, scheduler

    def test_migration_flag_prevents_all_startup_writes(self):
        db, tenant, scheduler = self.run_startup('true')
        tenant.assert_not_awaited()
        self.assertEqual(db.mock_calls, [unittest.mock.call.settings.find_one(
            {'key': 'whatsapp_group_id'})])
        scheduler.add_job.assert_not_called()
        scheduler.start.assert_not_called()

    def test_flag_is_case_insensitive(self):
        _, tenant, _ = self.run_startup('TRUE')
        tenant.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
