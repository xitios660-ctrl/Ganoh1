"""Payment corrections must succeed when the requested value is already saved."""
import asyncio
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)
import server


@pytest.mark.parametrize("collection", ["prazo_payments", "prazo_partial_payments"])
@pytest.mark.parametrize("modified", [0, 1])
def test_existing_payment_succeeds_even_when_unchanged(monkeypatch, collection, modified):
    collections = {
        name: SimpleNamespace(update_one=AsyncMock(return_value=SimpleNamespace(
            matched_count=int(name == collection),
            modified_count=modified if name == collection else 0,
        )))
        for name in ("prazo_payments", "prazo_partial_payments")
    }
    monkeypatch.setattr(server, "db", SimpleNamespace(**collections))
    result = asyncio.run(server.fix_payment_method("test-id", "pix", "test-manager"))
    assert result["success"] is True
    assert collection in result["message"]
    collections[collection].update_one.assert_awaited_once_with(
        {"id": "test-id"}, {"$set": {"payment_method": "pix"}}
    )
    if collection == "prazo_payments":
        collections["prazo_partial_payments"].update_one.assert_not_awaited()


def test_missing_payment_still_reports_not_found(monkeypatch):
    missing = SimpleNamespace(matched_count=0, modified_count=0)
    monkeypatch.setattr(server, "db", SimpleNamespace(
        prazo_payments=SimpleNamespace(update_one=AsyncMock(return_value=missing)),
        prazo_partial_payments=SimpleNamespace(update_one=AsyncMock(return_value=missing)),
    ))
    result = asyncio.run(server.fix_payment_method("missing-id", "pix", "test-manager"))
    assert result == {"success": False, "message": "Pagamento não encontrado"}
