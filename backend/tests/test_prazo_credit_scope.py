"""Regression tests for store-scoped prazo credit application."""
import os
from pathlib import Path
import sys


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server


def test_credit_debt_query_is_scoped_to_customer_store():
    query = server._unpaid_prazo_orders_query({"name": "Cliente Teste", "store": "runner"})

    assert query["store"] == "runner"
    assert query["customer_name"]["$regex"] == "^Cliente\\ Teste$"


def test_legacy_customer_without_store_keeps_compatible_query():
    query = server._unpaid_prazo_orders_query({"name": "Cliente Antigo"})

    assert "store" not in query
