from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.repository.test_base_repository import (
    ChildModel,
    ParentModel,
    ParentRepository,
    ParentSchema,
    _TestBase,
)


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_add_and_remove_related(session: AsyncSession) -> None:
    repo = ParentRepository(session, ParentModel, ParentSchema)
    parent = await repo.create(ParentSchema(name="p"))
    assert parent.id is not None

    c1 = ChildModel(name="c1")
    c2 = ChildModel(name="c2")
    session.add_all([c1, c2])
    await session.commit()

    updated = await repo.add_related(id=parent.id, relation_name="children", related_ids=[c1.id, c2.id])
    assert updated.id == parent.id

    refreshed = await session.get(ParentModel, parent.id)
    assert refreshed is not None
    await session.refresh(refreshed, attribute_names=["children"])
    assert {c.id for c in refreshed.children} == {c1.id, c2.id}

    await repo.remove_related(id=parent.id, relation_name="children", related_ids=[c1.id])
    await session.refresh(refreshed, attribute_names=["children"])
    assert {c.id for c in refreshed.children} == {c2.id}


@pytest.mark.asyncio
async def test_add_related_rejects_unknown_relation(session: AsyncSession) -> None:
    repo = ParentRepository(session, ParentModel, ParentSchema)
    parent = await repo.create(ParentSchema(name="p"))
    assert parent.id is not None
    with pytest.raises(ValueError, match="not configured"):
        await repo.add_related(id=parent.id, relation_name="nope", related_ids=[uuid4()])
