"""AND/OR filter semantics."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy.filtering.filter_builder import FilterBuilder
from strawberry_alchemy.filtering.inputs import StringFilter


class _FilterBase(DeclarativeBase):
    pass


class PostModel(_FilterBase):
    __tablename__ = "filter_or_post"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(String(255), default="")


@strawberry.input
class PostFilter:
    title: StringFilter | None = strawberry.UNSET
    status: StringFilter | None = strawberry.UNSET
    body: StringFilter | None = strawberry.UNSET
    AND: list[PostFilter] | None = strawberry.UNSET
    OR: list[PostFilter] | None = strawberry.UNSET


def _clause_as_str(expr: Any) -> str:
    return str(expr.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_root_or_multi_field_branch_ands_fields_inside_arm() -> None:
    """One OR arm with two fields must be OR(AND(title, status), title)."""
    builder = FilterBuilder()
    filters = {
        "OR": [
            {"title__exact": "Hello", "status__exact": "draft"},
            {"title__exact": "World"},
        ]
    }

    expr = await builder.build_filters(PostModel, filters)
    assert expr is not None
    sql = _clause_as_str(expr)

    assert " OR " in sql
    assert " AND " in sql
    assert sql.count("title") >= 2


def test_build_filter_dict_preserves_and_as_list_of_branches() -> None:
    builder = FilterBuilder()
    filt = PostFilter(
        AND=[
            PostFilter(title=StringFilter(exact="A")),
            PostFilter(title=StringFilter(exact="B")),
        ]
    )

    data = builder.build_filter_dict(filt)

    assert isinstance(data.get("AND"), list)
    assert len(data["AND"]) == 2


@pytest.mark.asyncio
async def test_strawberry_root_or_round_trip_multi_field_branch() -> None:
    builder = FilterBuilder()
    filt = PostFilter(
        OR=[
            PostFilter(
                title=StringFilter(exact="Hello"),
                status=StringFilter(exact="draft"),
            ),
            PostFilter(title=StringFilter(exact="World")),
        ]
    )
    data = builder.build_filter_dict(filt)
    expr = await builder.build_filters(PostModel, data)
    assert expr is not None

    stmt = select(PostModel).where(expr)
    sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "draft" in sql
    assert "Hello" in sql
    assert "World" in sql
    assert " AND " in sql
