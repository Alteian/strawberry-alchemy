from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy import BaseSchema, NotFoundError, SoftDeleteMixin
from strawberry_alchemy.repository import BaseRepository


class _Base(DeclarativeBase):
    pass


class Doc(_Base):
    __tablename__ = "soft_delete_docs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(50))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)


class DocSchema(BaseSchema):
    id: UUID | None = None
    title: str
    deleted_at: datetime | None = None


class DocRepository(BaseRepository[Doc, DocSchema]):
    model_cls: ClassVar[type[Any]] = Doc
    schema_cls: ClassVar[type[Any]] = DocSchema
    soft_delete_field: ClassVar[str | None] = "deleted_at"


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def test_soft_delete_mixin_declares_deleted_at() -> None:
    assert "deleted_at" in SoftDeleteMixin.__annotations__


@pytest.mark.asyncio
async def test_soft_delete_hides_from_get_by_id(session: AsyncSession) -> None:
    repo = DocRepository(session)
    created = await repo.create(DocSchema(title="secret"))
    assert created.id is not None

    soft = await repo.soft_delete(id=created.id)
    assert soft.deleted_at is not None

    with pytest.raises(NotFoundError):
        await repo.get_by_id(created.id)

    found = await repo.get_by_id(created.id, include_deleted=True)
    assert found.deleted_at is not None


@pytest.mark.asyncio
async def test_soft_delete_requires_classvar(session: AsyncSession) -> None:
    class BareRepo(BaseRepository[Doc, DocSchema]):
        model_cls: ClassVar[type[Any]] = Doc
        schema_cls: ClassVar[type[Any]] = DocSchema

    with pytest.raises(TypeError, match="soft_delete_field"):
        await BareRepo(session).soft_delete(id=uuid4())
