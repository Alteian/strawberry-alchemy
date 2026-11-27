"""Per-parent max_items cap on to-many selectin loads."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import Info  # noqa: TC002

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.types.base_node import BaseNodeType
from strawberry_alchemy.types.list_result import ListResult  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _TestBase(DeclarativeBase):
    pass


class Parent(_TestBase):
    __tablename__ = "max_items_parents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    children: Mapped[list[Child]] = relationship(back_populates="parent")


class Child(_TestBase):
    __tablename__ = "max_items_children"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("max_items_parents.id"))
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[Parent | None] = relationship(back_populates="children")


class OpenAccessFilter(AccessControlFilter):
    model_class = Parent

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


class ChildOpenAccessFilter(AccessControlFilter):
    model_class = Child

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type
class ChildType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = ChildOpenAccessFilter

    title: str | None = strawberry.UNSET
    parent_id: UUID | None = strawberry.UNSET


@strawberry.type
class ParentType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = OpenAccessFilter
    max_items: ClassVar[int] = 2

    title: str | None = strawberry.UNSET
    children: list[ChildType] | None = strawberry.UNSET


class GraphQLContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.identity = None
        self.db_execution_lock = asyncio.Lock()

    async def get_session(self) -> AsyncSession:
        return self._session


@strawberry.type
class Query:
    @strawberry.field
    async def parents(self, info: Info) -> ListResult[ParentType]:
        return await ParentType.resolve_list(info)


PARENT_A = uuid4()
PARENT_B = uuid4()


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        for parent_id, prefix in ((PARENT_A, "a"), (PARENT_B, "b")):
            db.add(
                Parent(
                    id=parent_id,
                    title=f"parent-{prefix}",
                    created_at=now,
                    updated_at=now,
                    children=[
                        Child(
                            id=uuid4(),
                            title=f"child-{prefix}{i}",
                            created_at=now,
                            updated_at=now,
                        )
                        for i in range(5)
                    ],
                )
            )
        await db.commit()
        db.expire_all()
        yield db

    await engine.dispose()


def test_base_node_default_max_items() -> None:
    assert BaseNodeType.max_items == 100


@pytest.mark.asyncio
async def test_selectinload_caps_list_fields_per_parent(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session)

    result = await schema.execute(
        """
        query {
          parents {
            items {
              title
              children { title }
            }
            totalCount
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    parents = result.data["parents"]["items"]
    assert len(parents) == 2
    for parent in parents:
        assert len(parent["children"]) == 2
