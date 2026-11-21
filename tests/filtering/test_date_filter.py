"""DateFilter against SQLAlchemy Date columns."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import Date, DateTime, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy.filtering.filter_builder import FilterBuilder
from strawberry_alchemy.filtering.inputs import DateFilter, DateTimeFilter


class _FilterBase(DeclarativeBase):
    pass


class HolidayModel(_FilterBase):
    __tablename__ = "filter_date_holiday"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    day: Mapped[date] = mapped_column(Date)


@strawberry.input
class HolidayFilter:
    day: DateFilter | None = strawberry.UNSET
    AND: list[HolidayFilter] | None = strawberry.UNSET
    OR: list[HolidayFilter] | None = strawberry.UNSET


def _clause_as_str(expr: Any) -> str:
    return str(expr.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_date_filter_ge_lt_half_open_range() -> None:
    builder = FilterBuilder()
    filt = HolidayFilter(
        day=DateFilter(ge=date(2026, 11, 1), lt=date(2026, 12, 1)),
    )
    expr = await builder.build_filters(HolidayModel, builder.build_filter_dict(filt))
    assert expr is not None
    sql = _clause_as_str(expr)
    assert "2026-11-01" in sql
    assert "2026-12-01" in sql


@pytest.mark.asyncio
async def test_date_filter_parses_iso_string() -> None:
    builder = FilterBuilder()
    expr = await builder.build_field_filter(
        HolidayModel,
        "day__exact",
        "2026-01-01",
    )
    assert expr is not None
    assert "2026-01-01" in _clause_as_str(expr)


@pytest.mark.asyncio
async def test_date_filter_round_trip_select() -> None:
    """Compiled clause is valid SQLAlchemy against the model column."""
    builder = FilterBuilder()
    filt = HolidayFilter(day=DateFilter(ge=date(2026, 1, 1), le=date(2026, 1, 31)))
    expr = await builder.build_filters(HolidayModel, builder.build_filter_dict(filt))
    assert expr is not None
    stmt = select(HolidayModel).where(expr)
    assert "filter_date_holiday" in str(stmt)


class EventModel(_FilterBase):
    __tablename__ = "filter_dt_isnull_event"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)


@strawberry.input
class EventFilter:
    published_at: DateTimeFilter | None = strawberry.UNSET


@pytest.mark.asyncio
async def test_datetime_isnull_bool_not_coerced() -> None:
    builder = FilterBuilder()
    filt = EventFilter(published_at=DateTimeFilter(isnull=True))
    expr = await builder.build_filters(EventModel, builder.build_filter_dict(filt))
    assert expr is not None
    assert "IS NULL" in _clause_as_str(expr).upper()
