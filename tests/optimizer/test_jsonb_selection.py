"""JSONB partial key selection must keep the column requested (not deferred)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer


class _JsonbOptBase(DeclarativeBase):
    pass


class ListingModel(_JsonbOptBase):
    __tablename__ = "jsonb_selection_listings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    slug: Mapped[str] = mapped_column(default="")


def test_collect_requested_fields_includes_jsonb_with_key_selection() -> None:
    optimizer = QueryOptimizer(info=cast("Any", object()), session=cast("Any", object()))
    selected = {"title": {"cs": True}, "slug": True}

    requested = optimizer.collect_requested_fields(selected, ListingModel)
    all_attrs = optimizer.get_all_model_attributes(ListingModel)

    assert all_attrs["title"] in requested
    assert all_attrs["slug"] in requested

    deferred = optimizer.get_deferred_attributes(selected, ListingModel)
    assert all_attrs["title"] not in deferred
    assert all_attrs["slug"] not in deferred


def test_collect_requested_fields_defers_unselected_jsonb() -> None:
    optimizer = QueryOptimizer(info=cast("Any", object()), session=cast("Any", object()))
    selected = {"slug": True}

    requested = optimizer.collect_requested_fields(selected, ListingModel)
    all_attrs = optimizer.get_all_model_attributes(ListingModel)

    assert all_attrs["title"] not in requested
    deferred = optimizer.get_deferred_attributes(selected, ListingModel)
    assert all_attrs["title"] in deferred
