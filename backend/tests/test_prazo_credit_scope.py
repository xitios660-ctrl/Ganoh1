"""Regression tests for store-scoped prazo credit application."""
import os
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server


def test_debt_reduction_requires_store_to_avoid_homonym_mixups():
    with pytest.raises(ValidationError):
        server.PrazoAbaterRequest(amount=10, password="test")

    request = server.PrazoAbaterRequest(amount=10, password="test", store="gym-londres")
    assert request.store == server.StoreLocation.GYM_LONDRES


def test_order_credit_customer_lookup_is_scoped_to_order_store():
    query = server._prazo_customer_lookup_query("Cliente Teste", server.StoreLocation.RUNNER)

    assert query["store"] == "runner"
    assert query["name"]["$regex"] == "^Cliente\\ Teste$"


def test_credit_debt_query_is_scoped_to_customer_store():
    query = server._unpaid_prazo_orders_query({"name": "Cliente Teste", "store": "runner"})

    assert query["store"] == "runner"
    assert query["customer_name"]["$regex"] == "^Cliente\\ Teste$"


def test_legacy_customer_without_store_keeps_compatible_query():
    query = server._unpaid_prazo_orders_query({"name": "Cliente Antigo"})

    assert "store" not in query
