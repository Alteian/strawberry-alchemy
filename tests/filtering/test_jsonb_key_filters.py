"""JSONB key-path filters: column['cs'].astext + StringFilter operators."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import String
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy.filtering.filter_builder import FilterBuilder
from strawberry_alchemy.filtering.inputs import JSONFilter, StringFilter


class _JsonbFilterBase(DeclarativeBase):
    pass


class DocModel(_JsonbFilterBase):
    __tablename__ = "jsonb_key_filter_docs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    name: Mapped[str] = mapped_column(String(50), default="")


@strawberry.input
class LocalizedStringFilter:
    cs: StringFilter | None = strawberry.UNSET
    en: StringFilter | None = strawberry.UNSET


@strawberry.input
class DocFilter:
    title: LocalizedStringFilter | None = strawberry.UNSET
    name: StringFilter | None = strawberry.UNSET


def _compile(expr: Any) -> str:
    return str(expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.asyncio
async def test_jsonb_key_icontains_via_build_field_filter() -> None:
    builder = FilterBuilder()
    expr = await builder.build_field_filter(
        DocModel,
        "title",
        LocalizedStringFilter(cs=StringFilter(icontains="byt")),
    )
    assert expr is not None
    sql = _compile(expr)
    assert "title" in sql
    assert "cs" in sql
    assert "->>" in sql or "astext" in sql.lower()
    assert "byt" in sql.lower()
    assert "ilike" in sql.lower() or "like" in sql.lower()


@pytest.mark.asyncio
async def test_jsonb_key_via_build_filter_dict_and_build_filters() -> None:
    builder = FilterBuilder()
    filt = DocFilter(title=LocalizedStringFilter(cs=StringFilter(icontains="byt")))
    filter_dict = builder.build_filter_dict(filt)
    expr = await builder.build_filters(DocModel, filter_dict)
    assert expr is not None
    sql = _compile(expr)
    assert "cs" in sql
    assert "->>" in sql or "astext" in sql.lower()


@pytest.mark.asyncio
async def test_jsonb_key_multiple_keys_anded() -> None:
    builder = FilterBuilder()
    expr = await builder.build_field_filter(
        DocModel,
        "title",
        LocalizedStringFilter(
            cs=StringFilter(icontains="byt"),
            en=StringFilter(isnull=False),
        ),
    )
    assert expr is not None
    sql = _compile(expr)
    assert " AND " in sql
    assert sql.count("->>") >= 2 or sql.lower().count("astext") >= 2


@pytest.mark.asyncio
async def test_json_filter_operators_still_apply_to_column() -> None:
    """JSONFilter containment ops must target the column, not a fake key path."""
    builder = FilterBuilder()
    expr = await builder.build_field_filter(
        DocModel,
        "title",
        JSONFilter(jsonb_has_key="en"),
    )
    assert expr is not None
    sql = _compile(expr)
    assert "title" in sql
    assert "?" in sql
    assert "->>" not in sql
