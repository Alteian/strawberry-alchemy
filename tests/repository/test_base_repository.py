from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
from sqlalchemy import ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from strawberry_alchemy.repository.base import BaseRepository
from strawberry_alchemy.schema.base import BaseSchema


class _TestBase(DeclarativeBase):
    pass


class ParentModel(_TestBase):
    __tablename__ = "test_parent_model"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    children: Mapped[list[ChildModel]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )


class ChildModel(_TestBase):
    __tablename__ = "test_child_model"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("test_parent_model.id"))
    name: Mapped[str] = mapped_column(String(255))
    parent: Mapped[ParentModel | None] = relationship(back_populates="children")


class ChildSchema(BaseSchema):
    id: UUID | None = None
    name: str


class ParentSchema(BaseSchema):
    id: UUID | None = None
    name: str
    children: list[ChildSchema] | None = None


class ParentRepository(BaseRepository[ParentModel, ParentSchema]):
    relation_models = {"children": ChildModel}


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_by_ids_returns_matching_schemas(session: AsyncSession) -> None:
    repo = ParentRepository(session, ParentModel, ParentSchema)

    first = ParentModel(name="first")
    second = ParentModel(name="second")
    third = ParentModel(name="third")
    session.add_all([first, second, third])
    await session.commit()

    result = await repo.get_by_ids([first.id, third.id])

    assert {item.id for item in result} == {first.id, third.id}
    assert {item.name for item in result} == {"first", "third"}


@pytest.mark.asyncio
async def test_process_relations_creates_missing_items_with_explicit_ids(session: AsyncSession) -> None:
    repo = ParentRepository(session, ParentModel, ParentSchema)

    missing_child_id = uuid4()
    schema = ParentSchema(
        name="parent",
        children=[
            ChildSchema(id=missing_child_id, name="created-from-missing-id"),
            ChildSchema(name="created-without-id"),
        ],
    )

    created = await repo.create(schema)
    parent = await session.get(ParentModel, created.id)

    assert parent is not None
    await session.refresh(parent, attribute_names=["children"])
    children = list(parent.children)

    assert len(children) == 2
    assert {child.name for child in children} == {
        "created-from-missing-id",
        "created-without-id",
    }
    assert any(child.id == missing_child_id for child in children)


@pytest.mark.asyncio
async def test_update_relations_updates_loaded_items_and_adds_missing_ones(session: AsyncSession) -> None:
    repo = ParentRepository(session, ParentModel, ParentSchema)

    existing_child = ChildModel(name="before")
    parent = ParentModel(name="parent", children=[existing_child])
    session.add(parent)
    await session.commit()
    await session.refresh(parent, attribute_names=["children"])

    missing_child_id = uuid4()
    updated_schema = ParentSchema(
        id=parent.id,
        name="parent-updated",
        children=[
            ChildSchema(id=existing_child.id, name="after"),
            ChildSchema(id=missing_child_id, name="new-from-missing-id"),
            ChildSchema(name="new-without-id"),
        ],
    )

    updated = await repo.update(updated_schema)
    assert updated.id == parent.id
    assert updated.name == "parent-updated"

    refreshed_parent = await session.get(ParentModel, parent.id)
    assert refreshed_parent is not None
    await session.refresh(refreshed_parent, attribute_names=["children"])

    assert len(refreshed_parent.children) == 3
    by_name = {child.name: child for child in refreshed_parent.children}

    assert "after" in by_name
    assert by_name["after"].id == existing_child.id

    assert "new-from-missing-id" in by_name
    assert by_name["new-from-missing-id"].id == missing_child_id

    assert "new-without-id" in by_name
    assert by_name["new-without-id"].id is not None
