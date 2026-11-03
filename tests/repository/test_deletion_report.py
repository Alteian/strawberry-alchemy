from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy import BaseSchema, DeletionPartialFailure, DeletionReport
from strawberry_alchemy.repository import BaseDeletionHandler, BaseRepository


class _Base(DeclarativeBase):
    pass


class Item(_Base):
    __tablename__ = "deletion_report_items"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(50))


class ItemSchema(BaseSchema):
    id: UUID | None = None
    name: str


class RecordingHandler(BaseDeletionHandler[Item]):
    async def cleanup_external(self, session, entity_id, instance, dependents):  # noqa: ANN001
        self.report.record("s3", "delete_object", instance.name, "boom")


class ItemRepository(BaseRepository[Item, ItemSchema]):
    model_cls: ClassVar[type[Any]] = Item
    schema_cls: ClassVar[type[Any]] = ItemSchema


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_delete_returns_empty_report(session: AsyncSession) -> None:
    repo = ItemRepository(session)
    created = await repo.create(ItemSchema(name="x"))
    assert created.id is not None
    report = await repo.delete(id=created.id)
    assert isinstance(report, DeletionReport)
    assert report.entity_id == created.id
    assert report.has_failures is False
    assert report.summary() == "no failures"


@pytest.mark.asyncio
async def test_delete_strict_raises_on_recorded_failures(session: AsyncSession) -> None:
    handler = RecordingHandler()
    repo = ItemRepository(session, deletion_handler=handler)
    created = await repo.create(ItemSchema(name="y"))
    assert created.id is not None

    with pytest.raises(DeletionPartialFailure) as exc:
        await repo.delete(id=created.id, strict=True)
    assert exc.value.report.has_failures
    assert "s3" in exc.value.report.summary()
