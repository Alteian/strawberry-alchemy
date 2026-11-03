from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import String, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy import FilterOperators, apply_rls_context, set_rls_guc
from strawberry_alchemy.filtering import FilterBuilder, StringFilter

pytestmark = pytest.mark.postgres


class _PgBase(DeclarativeBase):
    pass


class Doc(_PgBase):
    __tablename__ = "sa_pg_docs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    owner_id: Mapped[str] = mapped_column(String(64))


@strawberry.input
class LocalizedStringFilter:
    cs: StringFilter | None = strawberry.UNSET
    en: StringFilter | None = strawberry.UNSET


@pytest.fixture
async def docs_table(pg_engine: AsyncEngine) -> None:
    async with pg_engine.begin() as conn:
        await conn.run_sync(_PgBase.metadata.drop_all)
        await conn.run_sync(_PgBase.metadata.create_all)
    yield
    async with pg_engine.begin() as conn:
        await conn.run_sync(_PgBase.metadata.drop_all)


@pytest.mark.asyncio
async def test_set_config_guc_roundtrip(pg_session: AsyncSession) -> None:
    await set_rls_guc(pg_session, "user_id", "alice")
    value = (await pg_session.execute(text("SELECT current_setting('app.user_id', true)"))).scalar_one()
    assert value == "alice"

    await apply_rls_context(pg_session, {"tenant_id": "t1"})
    tenant = (await pg_session.execute(text("SELECT current_setting('app.tenant_id', true)"))).scalar_one()
    assert tenant == "t1"


@pytest.mark.asyncio
async def test_jsonb_key_filter_executes(pg_session: AsyncSession, docs_table: None) -> None:
    pg_session.add_all(
        [
            Doc(id=uuid4(), title={"cs": "Prodej bytu", "en": "Sale"}, owner_id="a"),
            Doc(id=uuid4(), title={"cs": "Dům", "en": "House"}, owner_id="b"),
        ]
    )
    await pg_session.commit()

    builder = FilterBuilder()
    expr = await builder.build_field_filter(
        Doc,
        "title",
        LocalizedStringFilter(cs=StringFilter(icontains="byt")),
    )
    assert expr is not None
    rows = (await pg_session.execute(select(Doc).where(expr))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title["cs"] == "Prodej bytu"


def test_jsonb_has_key_operator_registered() -> None:
    assert "jsonb_has_key" in FilterOperators.LOOKUP_OPERATORS
