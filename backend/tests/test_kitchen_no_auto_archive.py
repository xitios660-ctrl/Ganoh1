"""Kitchen reads retain ready orders regardless of age and never mutate data."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MONGO_URL='mongodb://127.0.0.1:27017', DB_NAME='test_only',
                  LITELLM_LOCAL_MODEL_COST_MAP='True')
import server


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, *_args):
        return self

    async def to_list(self, limit):
        return deepcopy(self.rows[:limit])


class ReadOnlyOrders:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, *_args):
        # Reject hidden date conditions: all ready orders must remain visible.
        assert set(query) <= {'store', 'status'}
        return Cursor([r for r in self.rows if all(r.get(k) == v for k, v in query.items())])

    async def count_documents(self, query):
        return len(await self.find(query).to_list(5000))


@pytest.mark.parametrize('store', list(server.StoreLocation))
@pytest.mark.parametrize('status', [None, 'ready'])
def test_poll_keeps_old_ready_orders_and_stats_count_them(monkeypatch, store, status):
    now = datetime.now(timezone.utc)
    rows = [dict(id=str(i), store=store.value, status='ready', total=1,
                 created_at=(now-timedelta(hours=30)).isoformat(),
                 updated_at=(now-timedelta(hours=30)).isoformat()) for i in range(105)]
    rows.append(dict(id='other-store', store='other-store', status='ready'))
    before = deepcopy(rows)
    # No history collection or mutation methods: any archive attempt fails.
    monkeypatch.setattr(server, 'db', SimpleNamespace(orders=ReadOnlyOrders(rows)))
    result = asyncio.run(server.get_orders(store, status))
    stats = asyncio.run(server.get_kitchen_stats(store))
    assert len(result['orders']) == 105
    assert stats == {'pending': 0, 'preparing': 0, 'ready': 105}
    assert rows == before
    assert all(o['status'] == 'ready' for o in result['orders'])
