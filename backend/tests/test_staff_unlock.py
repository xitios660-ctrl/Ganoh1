"""Regression tests for the fixed staff password, separate from Gestor."""
import asyncio
import os
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.update(
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="test_only",
    LITELLM_LOCAL_MODEL_COST_MAP="True",
)

import server


def test_staff_password_is_accepted():
    result = asyncio.run(
        server.unlock_staff(server.StaffUnlockRequest(password="ganoh2025"))
    )
    assert result == {"success": True}


def test_gestor_password_does_not_unlock_staff():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.unlock_staff(server.StaffUnlockRequest(password="ganoh2024"))
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Senha incorreta"


def test_wrong_staff_password_returns_401():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            server.unlock_staff(server.StaffUnlockRequest(password="senha-errada"))
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Senha incorreta"
