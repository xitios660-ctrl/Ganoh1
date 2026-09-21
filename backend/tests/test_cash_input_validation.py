"""Regression tests for cash inputs; no database writes are performed."""
import math
import os
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server
from routers import cash


@pytest.mark.parametrize("model", [server.CashWithdrawal, cash.CashWithdrawal])
@pytest.mark.parametrize("amount", [0, -0.01, math.inf, -math.inf, math.nan])
def test_withdrawal_rejects_non_positive_or_non_finite_amount(model, amount):
    with pytest.raises(ValidationError):
        model(amount=amount, category="vt")


@pytest.mark.parametrize("model", [server.CashWithdrawal, cash.CashWithdrawal])
def test_withdrawal_rejects_unknown_category(model):
    with pytest.raises(ValidationError):
        model(amount=10, category="desconhecida")


@pytest.mark.parametrize("model", [server.CashBalanceAdjust, cash.CashBalanceAdjust])
@pytest.mark.parametrize("balance", [-0.01, math.inf, -math.inf, math.nan])
def test_balance_rejects_negative_or_non_finite_value(model, balance):
    with pytest.raises(ValidationError):
        model(balance=balance)


@pytest.mark.parametrize("model", [server.PixAdjustment, cash.PixAdjustment])
@pytest.mark.parametrize("amount", [0, -0.01, math.inf, -math.inf, math.nan])
def test_pix_adjustment_rejects_non_positive_or_non_finite_amount(model, amount):
    with pytest.raises(ValidationError):
        model(amount=amount, store="runner")


@pytest.mark.parametrize("model", [server.PixAdjustment, cash.PixAdjustment])
def test_pix_adjustment_rejects_unknown_store(model):
    with pytest.raises(ValidationError):
        model(amount=10, store="loja-inexistente")


def test_valid_cash_inputs_remain_accepted():
    assert server.CashBalanceAdjust(balance=0).balance == 0
    assert cash.CashWithdrawal(amount=25.5, category="outros").amount == 25.5
    assert server.PixAdjustment(amount=12.75, store="gym-londres").amount == 12.75


def test_api_rejects_invalid_cash_inputs_before_database_write():
    client = TestClient(server.app)

    assert client.post(
        "/api/cash/runner/withdraw",
        json={"amount": -10, "category": "vt"},
    ).status_code == 422
    assert client.post(
        "/api/cash/runner/set-balance",
        json={"balance": -10},
    ).status_code == 422
    assert client.post(
        "/api/pix-adjustments/add",
        json={"amount": 10, "store": "loja-inexistente"},
    ).status_code == 422
