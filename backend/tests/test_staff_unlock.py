"""Regression tests for staff access without a dedicated Render STAFF_PASSWORD."""
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


def test_staff_unlock_uses_gestor_account_when_staff_password_missing(monkeypatch):
    monkeypatch.delenv("STAFF_PASSWORD", raising=False)
    monkeypatch.setenv("GESTOR_PASSWORD", "fallback-only")

    async def fake_credentials(username, password):
        if username == "gestor" and password == "correct-manager-password":
            return {"id": "tenant_default", "username": "gestor"}
        return None

    monkeypatch.setattr(server, "get_tenant_by_credentials", fake_credentials)

    result = asyncio.run(
        server.unlock_staff(server.StaffUnlockRequest(password="correct-manager-password"))
    )
    assert result == {"success": True}


def test_staff_unlock_wrong_password_returns_401(monkeypatch):
    monkeypatch.delenv("STAFF_PASSWORD", raising=False)
    monkeypatch.delenv("GESTOR_PASSWORD", raising=False)

    async def fake_credentials(_username, _password):
        return None

    monkeypatch.setattr(server, "get_tenant_by_credentials", fake_credentials)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(server.unlock_staff(server.StaffUnlockRequest(password="wrong")))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Senha incorreta"
