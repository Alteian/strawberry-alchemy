"""Per-parent max_items cap on to-many selectin loads."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import Info  # noqa: TC002

from strawberry_alchemy import MaxItems, NestedListResult, NodeConfig
from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer
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
    tags: Mapped[list[Tag]] = relationship(back_populates="parent")


class Child(_TestBase):
    __tablename__ = "max_items_children"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("max_items_parents.id"))
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[Parent | None] = relationship(back_populates="children")


class Tag(_TestBase):
    __tablename__ = "max_items_tags"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("max_items_parents.id"))
    label: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[Parent | None] = relationship(back_populates="tags")


class CompositeParent(_TestBase):
    __tablename__ = "max_items_composite_parents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(100))

    children: Mapped[list[CompositeChild]] = relationship(back_populates="parent")


class CompositeChild(_TestBase):
    __tablename__ = "max_items_composite_children"

    parent_id: Mapped[UUID] = mapped_column(ForeignKey("max_items_composite_parents.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100))

    parent: Mapped[CompositeParent | None] = relationship(back_populates="children")


class OrderedParent(_TestBase):
    __tablename__ = "max_items_ordered_parents"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    children: Mapped[list[OrderedChild]] = relationship(
        back_populates="parent",
        order_by="OrderedChild.seq",
    )


class OrderedChild(_TestBase):
    __tablename__ = "max_items_ordered_children"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID] = mapped_column(ForeignKey("max_items_ordered_parents.id"))
    seq: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[OrderedParent | None] = relationship(back_populates="children")


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


class TagOpenAccessFilter(AccessControlFilter):
    model_class = Tag

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


class OrderedParentAccessFilter(AccessControlFilter):
    model_class = OrderedParent

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


class OrderedChildAccessFilter(AccessControlFilter):
    """Only seq >= 5 is visible — first five rows by order_by are denied."""

    model_class = OrderedChild

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query.where(model.seq >= 5)


@strawberry.type
class ChildType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = ChildOpenAccessFilter

    title: str | None = strawberry.UNSET
    parent_id: UUID | None = strawberry.UNSET


@strawberry.type
class TagType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = TagOpenAccessFilter

    label: str | None = strawberry.UNSET
    parent_id: UUID | None = strawberry.UNSET


@strawberry.type
class ParentType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = OpenAccessFilter
    node_config: ClassVar[NodeConfig] = NodeConfig(max_items=2, fields={"tags": 1})

    title: str | None = strawberry.UNSET
    children: NestedListResult[ChildType] | None = strawberry.UNSET
    tags: NestedListResult[TagType] | None = strawberry.field(
        default=strawberry.UNSET,
        extensions=[MaxItems(3)],
    )


@strawberry.type
class UnlimitedParentType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = OpenAccessFilter
    node_config: ClassVar[NodeConfig] = NodeConfig(max_items=None)

    title: str | None = strawberry.UNSET
    children: NestedListResult[ChildType] | None = strawberry.UNSET


@strawberry.type
class OrderedChildType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = OrderedChildAccessFilter

    title: str | None = strawberry.UNSET
    seq: int | None = strawberry.UNSET
    parent_id: UUID | None = strawberry.UNSET


@strawberry.type
class OrderedParentType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = OrderedParentAccessFilter
    node_config: ClassVar[NodeConfig] = NodeConfig(max_items=2)

    title: str | None = strawberry.UNSET
    children: NestedListResult[OrderedChildType] | None = strawberry.UNSET


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

    @strawberry.field
    async def unlimited_parents(self, info: Info) -> ListResult[UnlimitedParentType]:
        return await UnlimitedParentType.resolve_list(info)

    @strawberry.field
    async def ordered_parents(self, info: Info) -> ListResult[OrderedParentType]:
        return await OrderedParentType.resolve_list(info)


PARENT_A = uuid4()
PARENT_B = uuid4()
ORDERED_PARENT = uuid4()


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
                    tags=[
                        Tag(
                            id=uuid4(),
                            label=f"tag-{prefix}{i}",
                            created_at=now,
                            updated_at=now,
                        )
                        for i in range(5)
                    ],
                )
            )
        db.add(
            OrderedParent(
                id=ORDERED_PARENT,
                title="ordered",
                created_at=now,
                updated_at=now,
                children=[
                    OrderedChild(
                        id=uuid4(),
                        seq=i,
                        title=f"ord-{i}",
                        created_at=now,
                        updated_at=now,
                    )
                    for i in range(10)
                ],
            )
        )
        await db.commit()
        db.expire_all()
        yield db

    await engine.dispose()


def test_node_config_defaults() -> None:
    assert BaseNodeType.node_config.max_items == 100
    assert BaseNodeType.node_config.fields == {}


def test_node_config_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        NodeConfig(max_items=0)
    with pytest.raises(ValueError, match="positive"):
        MaxItems(0)


def test_config_classvar_is_not_node_config() -> None:
    """A ClassVar named ``config`` is ignored — only ``node_config`` counts."""
    from strawberry_alchemy.types.node_config import lookup_node_config, resolve_max_items

    @strawberry.type
    class MisnamedConfigType(BaseNodeType):
        access_filter: ClassVar[type[AccessControlFilter]] = OpenAccessFilter
        config: ClassVar[NodeConfig] = NodeConfig(max_items=7, fields={"children": 3})

        title: str | None = strawberry.UNSET
        children: NestedListResult[ChildType] | None = strawberry.UNSET

    # Inherited ``BaseNodeType.node_config`` (default 100), not the misnamed ClassVar.
    assert lookup_node_config(MisnamedConfigType).max_items == 100
    assert resolve_max_items(MisnamedConfigType, "children") == 100


def test_domain_field_named_config_does_not_shadow_node_config() -> None:
    """Instance/field ``config`` must not be mistaken for ``NodeConfig``."""
    from strawberry_alchemy.types.node_config import lookup_node_config, resolve_max_items

    @strawberry.type
    class DomainConfigType(BaseNodeType):
        access_filter: ClassVar[type[AccessControlFilter]] = OpenAccessFilter
        node_config: ClassVar[NodeConfig] = NodeConfig(max_items=11)

        title: str | None = strawberry.UNSET
        config: dict[str, object] | None = strawberry.UNSET

    assert lookup_node_config(DomainConfigType).max_items == 11
    assert resolve_max_items(DomainConfigType, "children") == 11


@pytest.mark.asyncio
async def test_selectinload_caps_with_has_more(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session)

    result = await schema.execute(
        """
        query {
          parents {
            items {
              title
              children { items { title } hasMore }
              tags { items { label } hasMore }
            }
            totalCount
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None, result.errors
    assert result.data is not None
    parents = result.data["parents"]["items"]
    assert len(parents) == 2
    for parent in parents:
        # type default max_items=2
        assert len(parent["children"]["items"]) == 2
        assert parent["children"]["hasMore"] is True
        # MaxItems(3) wins over config.fields tags=1
        assert len(parent["tags"]["items"]) == 3
        assert parent["tags"]["hasMore"] is True


@pytest.mark.asyncio
async def test_unlimited_config_loads_all(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session)

    result = await schema.execute(
        """
        query {
          unlimitedParents {
            items {
              title
              children { items { title } hasMore }
            }
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None, result.errors
    assert result.data is not None
    parents = result.data["unlimitedParents"]["items"]
    assert len(parents) == 2
    for parent in parents:
        assert len(parent["children"]["items"]) == 5
        assert parent["children"]["hasMore"] is False


def test_collection_limit_supports_composite_primary_key() -> None:
    rel_prop = CompositeParent.children.property
    criterion = QueryOptimizer._collection_limit_criterion(rel_prop, CompositeChild, fetch_limit=3)
    assert criterion is not None
    # Compiles against SQLite (tuple IN + row_number).
    compiled = criterion.compile(compile_kwargs={"literal_binds": True})
    sql = str(compiled).lower()
    assert "row_number" in sql
    assert "limited_pk_0" in sql
    assert "limited_pk_1" in sql


@pytest.mark.asyncio
async def test_cap_ranks_within_acl_so_has_more_is_honest(session: AsyncSession) -> None:
    """Pre-ACL top-N would load seq 0..2 (all denied) → empty + hasMore false.

    Ranking inside ACL (seq >= 5) should return seq 5,6 with hasMore true.
    """
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session)

    result = await schema.execute(
        """
        query {
          orderedParents {
            items {
              title
              children { items { title seq } hasMore }
            }
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None, result.errors
    assert result.data is not None
    parents = result.data["orderedParents"]["items"]
    assert len(parents) == 1
    children = parents[0]["children"]
    assert [c["seq"] for c in children["items"]] == [5, 6]
    assert children["hasMore"] is True
