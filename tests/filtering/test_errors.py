from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy.filtering.filter_builder import FilterBuilder


class _Base(DeclarativeBase):
    pass


class Item(_Base):
    __tablename__ = "filter_error_item"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(64))


@pytest.mark.asyncio
async def test_unknown_lookup_raises() -> None:
    builder = FilterBuilder()
    with pytest.raises(ValueError, match="Unsupported lookup"):
        await builder.build_filters(Item, {"name__not_a_real_lookup": "x"})


@pytest.mark.asyncio
async def test_unknown_field_raises() -> None:
    builder = FilterBuilder()
    with pytest.raises(ValueError, match="not found"):
        await builder.build_filters(Item, {"missing__exact": "x"})
