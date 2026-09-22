"""Financial maintenance endpoints must never be available anonymously."""
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server


def test_financial_maintenance_routes_require_gestor_login():
    client = TestClient(server.app)
    routes = (
        "/api/cash/runner/fix-cleared",
        "/api/admin/fix-payment-method/payment-id",
        "/api/admin/fix-zero-stock/runner",
        "/api/admin/clear-withdrawals/runner",
    )

    for route in routes:
        assert client.post(route).status_code == 401


def test_store_maintenance_rejects_unknown_store_before_database_access():
    client = TestClient(server.app)
    server.app.dependency_overrides[server.verify_gestor] = lambda: "test-manager"
    try:
        routes = (
            "/api/admin/fix-zero-stock/unknown-store",
            "/api/admin/clear-withdrawals/unknown-store",
        )
        for route in routes:
            assert client.post(route).status_code == 422
    finally:
        server.app.dependency_overrides.clear()
