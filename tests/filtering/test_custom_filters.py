from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from strawberry_alchemy.filtering.filter_builder import FilterBuilder
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    organization: Mapped[Organization | None] = relationship(back_populates="users")


class FakeSelection:
    def __init__(self, name: str, selections: list[FakeSelection] | None = None) -> None:
        self.name = name
        self.alias = None
        self.selections = selections or []


class FakeContext:
    @property
    async def user(self) -> None:
        return None


class FakeInfo:
    def __init__(self) -> None:
        self.context = FakeContext()
        self.selected_fields = [SimpleNamespace(selections=[FakeSelection("id"), FakeSelection("name")])]


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        org_a = Organization(id=1, name="Alpha")
        org_b = Organization(id=2, name="Beta")
        db.add_all(
            [
                org_a,
                org_b,
                User(id=1, name="Alice", status="active", organization=org_a),
                User(id=2, name="Bob", status="inactive", organization=org_a),
                User(id=3, name="Carol", status="active", organization=org_b),
            ]
        )
        await db.commit()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_filter_builder_applies_custom_filter_on_model_field() -> None:
    def active_only(model: type[User], value: bool):
        return model.status == ("active" if value else "inactive")

    builder = FilterBuilder(custom_filters={User: {"is_active": active_only}})

    expr = await builder.build_filters(User, {"is_active": True})
    assert expr is not None
    stmt = select(User).where(expr)
    compiled = str(stmt)

    assert "status" in compiled
    assert "is_active" not in compiled


@pytest.mark.asyncio
async def test_filter_builder_applies_custom_filter_on_related_alias() -> None:
    def organization_name(model: type[Organization], value: str):
        return model.name.ilike(f"%{value}%")

    builder = FilterBuilder(custom_filters={Organization: {"display_name": organization_name}})

    expr = await builder.build_filters(User, {"organization__display_name": "alp"})
    assert expr is not None
    stmt = select(User).where(expr)
    compiled = str(stmt)

    assert "organizations" in compiled.lower() or "name" in compiled.lower()
    assert "display_name" not in compiled


@pytest.mark.asyncio
async def test_query_optimizer_uses_custom_filters_registry(session: AsyncSession) -> None:
    def active_only(model: type[User], value: bool):
        return model.status == ("active" if value else "inactive")

    class StrawberryUserType:
        _custom_filters_registry = {User: {"is_active": active_only}}

    optimizer = QueryOptimizer(info=cast("Any", FakeInfo()), session=session)

    result = await optimizer.optimize_query(
        model=User,
        filters={"is_active": True},
        strawberry_type=StrawberryUserType,
    )

    names = sorted(user.name for user in result.items)
    assert names == ["Alice", "Carol"]


@pytest.mark.asyncio
async def test_query_optimizer_combines_custom_and_standard_filters(session: AsyncSession) -> None:
    def active_only(model: type[User], value: bool):
        return model.status == ("active" if value else "inactive")

    class StrawberryUserType:
        _custom_filters_registry = {User: {"is_active": active_only}}

    optimizer = QueryOptimizer(info=cast("Any", FakeInfo()), session=session)

    result = await optimizer.optimize_query(
        model=User,
        filters={"is_active": True, "name__icontains": "ali"},
        strawberry_type=StrawberryUserType,
    )

    names = [user.name for user in result.items]
    assert names == ["Alice"]


@pytest.mark.asyncio
async def test_query_optimizer_ignores_missing_registry_when_not_provided(session: AsyncSession) -> None:
    optimizer = QueryOptimizer(info=cast("Any", FakeInfo()), session=session)

    result = await optimizer.optimize_query(
        model=User,
        filters={"name__icontains": "bo"},
        strawberry_type=None,
    )

    names = [user.name for user in result.items]
    assert names == ["Bob"]
