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
    __tablename__ = "nested_acl_parents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    children: Mapped[list[Child]] = relationship(back_populates="parent")


class Child(_TestBase):
    __tablename__ = "nested_acl_children"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("nested_acl_parents.id"))
    owner_id: Mapped[UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[Parent | None] = relationship(back_populates="children")


class ParentAccessFilter(AccessControlFilter):
    model_class = Parent

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.owner_id == context_user.id)


class ChildAccessFilter(AccessControlFilter):
    model_class = Child

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.owner_id == context_user.id)


@strawberry.type
class ChildType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = ChildAccessFilter

    owner_id: UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    parent_id: UUID | None = strawberry.UNSET


@strawberry.type
class ParentType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = ParentAccessFilter

    owner_id: UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    children: list[ChildType] | None = strawberry.UNSET


class _User:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id


class GraphQLContext:
    def __init__(self, session: AsyncSession, identity: Any = None) -> None:
        self._session = session
        self.identity = identity
        self.db_execution_lock = asyncio.Lock()

    async def get_session(self) -> AsyncSession:
        return self._session


@strawberry.type
class Query:
    @strawberry.field
    async def parents(self, info: Info) -> ListResult[ParentType]:
        return await ParentType.resolve_list(info)


OWNER_A = uuid4()
OWNER_B = uuid4()
PARENT_ID = uuid4()


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        db.add(
            Parent(
                id=PARENT_ID,
                owner_id=OWNER_A,
                title="parent-a",
                created_at=now,
                updated_at=now,
                children=[
                    Child(
                        id=uuid4(),
                        owner_id=OWNER_A,
                        title="child-a1",
                        created_at=now,
                        updated_at=now,
                    ),
                    Child(
                        id=uuid4(),
                        owner_id=OWNER_A,
                        title="child-a2",
                        created_at=now,
                        updated_at=now,
                    ),
                    Child(
                        id=uuid4(),
                        owner_id=OWNER_B,
                        title="child-b1",
                        created_at=now,
                        updated_at=now,
                    ),
                ],
            )
        )
        await db.commit()
        # expire_on_commit=False keeps seeded collections loaded; filtered
        # selectinload will not replace an already-populated relationship.
        db.expire_all()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_nested_selectinload_applies_child_access_filter(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

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
    parents = result.data["parents"]
    assert parents["totalCount"] == 1
    assert len(parents["items"]) == 1
    parent = parents["items"][0]
    assert parent["title"] == "parent-a"
    assert sorted(child["title"] for child in parent["children"]) == ["child-a1", "child-a2"]
