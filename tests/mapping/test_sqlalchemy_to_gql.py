from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, ClassVar, cast
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, defer, mapped_column

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.mapping.sqlalchemy_to_gql import UNSET, map_sqlalchemy_to_type
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer
from strawberry_alchemy.types.base_node import BaseNodeType

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _TestBase(DeclarativeBase):
    pass


class PersonModel(_TestBase):
    __tablename__ = "mapper_test_people"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PersonAccessFilter(AccessControlFilter):
    model_class = PersonModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type
class PersonType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = PersonAccessFilter

    name: str


class FakeInfo:
    schema = SimpleNamespace(get_type_by_name=lambda _name: None)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        db.add(
            PersonModel(
                id=uuid4(),
                name="Alice",
                created_at=now,
                updated_at=now,
            )
        )
        await db.commit()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_map_sqlalchemy_to_type_requested_deferred_scalar(session: AsyncSession) -> None:
    result = await session.execute(select(PersonModel).options(defer(PersonModel.created_at)))
    instance = result.scalar_one()
    assert "created_at" in sa_inspect(instance).unloaded

    mapped = await map_sqlalchemy_to_type(
        instance,
        cast("Any", FakeInfo()),
        PersonType,
        {"id": True, "name": True, "created_at": True},
    )

    assert mapped is not None
    assert mapped.created_at is not UNSET
    assert mapped.created_at is None


@pytest.mark.asyncio
async def test_map_sqlalchemy_to_type_unrequested_field_stays_unset(session: AsyncSession) -> None:
    result = await session.execute(select(PersonModel).options(defer(PersonModel.created_at)))
    instance = result.scalar_one()

    mapped = await map_sqlalchemy_to_type(
        instance,
        cast("Any", FakeInfo()),
        PersonType,
        {"id": True, "name": True},
    )

    assert mapped is not None
    assert mapped.created_at is not UNSET
    assert mapped.created_at is None


def test_direct_constructor_normalizes_nullable_unset_audit_fields() -> None:
    mapped = PersonType(id=uuid4(), name="Bob")

    assert mapped.created_at is not UNSET
    assert mapped.created_at is None
    assert mapped.updated_at is not UNSET
    assert mapped.updated_at is None

    optimizer = QueryOptimizer(info=cast("Any", object()), session=cast("Any", object()))
    selected_fields = {
        "name": True,
        "created_at": True,
        "organization": {"id": True},
    }

    requested = optimizer.collect_requested_fields(selected_fields, PersonModel)
    all_attributes = optimizer.get_all_model_attributes(PersonModel)

    assert all_attributes["name"] in requested
    assert all_attributes["created_at"] in requested
    assert all_attributes["updated_at"] not in requested

    deferred = optimizer.get_deferred_attributes(selected_fields, PersonModel)
    assert all_attributes["created_at"] not in deferred
    assert all_attributes["updated_at"] in deferred
