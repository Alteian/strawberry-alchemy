"""Transaction-local Postgres RLS session variables (GUCs).

Policies stay app-owned DDL (``CREATE POLICY`` / ``FORCE ROW LEVEL SECURITY``).
This module only sets ``SET LOCAL`` / ``set_config(..., is_local=true)`` values
that policies can read via ``current_setting('app.user_id', true)``.

Python ``AccessControlFilter`` remains available as optional defense-in-depth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

DEFAULT_GUC_PREFIX = "app"


def _normalize_guc_name(name: str, *, prefix: str = DEFAULT_GUC_PREFIX) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("GUC name must be non-empty")
    if "." in cleaned:
        return cleaned
    return f"{prefix}.{cleaned}"


async def set_rls_guc(
    target: AsyncSession | AsyncConnection,
    name: str,
    value: str | None,
    *,
    prefix: str = DEFAULT_GUC_PREFIX,
) -> None:
    """Set one transaction-local GUC (``SET LOCAL`` semantics via ``set_config``)."""
    guc = _normalize_guc_name(name, prefix=prefix)
    # set_config(name, value, is_local=true) → transaction-scoped.
    await target.execute(
        text("SELECT set_config(:name, :value, true)"),
        {"name": guc, "value": "" if value is None else str(value)},
    )


async def apply_rls_context(
    target: AsyncSession | AsyncConnection,
    values: Mapping[str, Any],
    *,
    prefix: str = DEFAULT_GUC_PREFIX,
) -> None:
    """Apply many GUCs from a mapping (e.g. ``{\"user_id\": user.id, \"tenant_id\": ...}``)."""
    for key, raw in values.items():
        if raw is None:
            await set_rls_guc(target, key, None, prefix=prefix)
        else:
            await set_rls_guc(target, key, str(raw), prefix=prefix)


async def clear_rls_context(
    target: AsyncSession | AsyncConnection,
    names: list[str],
    *,
    prefix: str = DEFAULT_GUC_PREFIX,
) -> None:
    """Clear listed GUCs for the current transaction (empty string)."""
    for name in names:
        await set_rls_guc(target, name, None, prefix=prefix)
