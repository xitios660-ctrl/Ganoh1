"""Credit input regression checks with database access forbidden."""
import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(MONGO_URL="mongodb://127.0.0.1:27017", DB_NAME="test_only",
                  LITELLM_LOCAL_MODEL_COST_MAP="True")
import server
from routers import prazo


class ForbiddenDatabase:
    def __getattr__(self, name):
        raise AssertionError("Invalid credit request reached the database")


@pytest.mark.parametrize("implementation", [server, prazo])
@pytest.mark.parametrize("operation", ["add-credit", "use-credit"])
@pytest.mark.parametrize("amount", [-10, 0, "NaN", "Infinity", "-Infinity"])
def test_invalid_credit_amount_rejected_before_database(implementation, operation, amount, monkeypatch):
    monkeypatch.setattr(implementation, "db", ForbiddenDatabase())
    if implementation is server:
        app = server.app
    else:
        app = FastAPI()
        app.include_router(prazo.router, prefix="/api")
    response = TestClient(app).post(
        f"/api/prazo/customers/test-customer/{operation}", json={"amount": amount}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("implementation", [server, prazo])
def test_positive_credit_amount_remains_valid(implementation):
    assert implementation.PrazoCreditAdd(amount=12.50).amount == 12.50
