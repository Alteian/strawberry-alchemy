from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from strawberry_alchemy import apply_rls_context, clear_rls_context, set_rls_guc
from strawberry_alchemy.postgres.rls import _normalize_guc_name


def test_normalize_guc_name_adds_prefix() -> None:
    assert _normalize_guc_name("user_id") == "app.user_id"
    assert _normalize_guc_name("app.tenant_id") == "app.tenant_id"
    assert _normalize_guc_name("tenant_id", prefix="maxxus") == "maxxus.tenant_id"


def test_normalize_guc_name_rejects_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _normalize_guc_name("  ")


@pytest.mark.asyncio
async def test_set_rls_guc_executes_set_config() -> None:
    session = MagicMock()
    session.execute = AsyncMock()

    await set_rls_guc(session, "user_id", "abc-123")

    session.execute.assert_awaited_once()
    _sql, params = session.execute.await_args.args[0], session.execute.await_args.args[1]
    assert "set_config" in str(_sql)
    assert params == {"name": "app.user_id", "value": "abc-123"}


@pytest.mark.asyncio
async def test_apply_and_clear_rls_context() -> None:
    session = MagicMock()
    session.execute = AsyncMock()

    await apply_rls_context(session, {"user_id": "u1", "tenant_id": 42})
    assert session.execute.await_count == 2

    await clear_rls_context(session, ["user_id", "tenant_id"])
    assert session.execute.await_count == 4
    last_params: dict[str, Any] = session.execute.await_args.args[1]
    assert last_params["value"] == ""
