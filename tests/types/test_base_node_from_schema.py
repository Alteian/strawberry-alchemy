from __future__ import annotations

from datetime import UTC, date, datetime
from typing import ClassVar
from uuid import UUID, uuid4

import strawberry
from pydantic import BaseModel

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.mapping.sqlalchemy_to_gql import UNSET
from strawberry_alchemy.types.base_node import BaseNodeType


class _DummyModel:
    pass


class _DummyAccessFilter(AccessControlFilter):
    model_class = _DummyModel


class _ThreadSchema(BaseModel):
    id: UUID
    subject: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@strawberry.type
class ThreadType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

    subject: str | None = None


def test_from_schema_missing_audit_timestamps_become_none_not_unset() -> None:
    schema = _ThreadSchema(id=str(uuid4()), subject="hello")

    mapped = ThreadType.from_schema(schema)

    assert mapped.created_at is not UNSET
    assert mapped.created_at is None
    assert mapped.updated_at is not UNSET
    assert mapped.updated_at is None


def test_from_schema_explicit_unset_kwargs_become_none() -> None:
    schema = _ThreadSchema(
        id=str(uuid4()),
        subject="hello",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )

    mapped = ThreadType.from_schema(
        schema,
        created_at=strawberry.UNSET,
        updated_at=strawberry.UNSET,
    )

    assert mapped.created_at is None
    assert mapped.updated_at is None


def test_from_schema_preserves_provided_timestamps() -> None:
    now = datetime.now(tz=UTC)
    schema = _ThreadSchema(
        id=str(uuid4()),
        subject="hello",
        created_at=now,
        updated_at=now,
    )

    mapped = ThreadType.from_schema(schema)

    assert mapped.created_at == now
    assert mapped.updated_at == now


def test_direct_constructor_normalizes_non_nullable_unset_date_field() -> None:
    @strawberry.type
    class BookingLike(BaseNodeType):
        access_filter: ClassVar[type[AccessControlFilter]] = _DummyAccessFilter

        check_in_date: date

    mapped = BookingLike(id=uuid4(), check_in_date=strawberry.UNSET)

    assert mapped.check_in_date is not UNSET
    assert mapped.check_in_date is None
