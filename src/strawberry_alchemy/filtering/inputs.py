from datetime import datetime

import strawberry
from strawberry.relay import GlobalID
from strawberry.scalars import JSON


@strawberry.input
class IDFilter:
    exact: GlobalID | None = strawberry.UNSET
    in_: list[GlobalID] | None = strawberry.field(default=strawberry.UNSET)
    not_in_: list[GlobalID] | None = strawberry.field(default=strawberry.UNSET)
    isnull: bool | None = strawberry.UNSET


@strawberry.input
class StringFilter:
    exact: str | None = strawberry.UNSET
    iexact: str | None = strawberry.UNSET
    contains: str | None = strawberry.UNSET
    icontains: str | None = strawberry.UNSET
    startswith: str | None = strawberry.UNSET
    istartswith: str | None = strawberry.UNSET
    endswith: str | None = strawberry.UNSET
    iendswith: str | None = strawberry.UNSET
    in_: list[str] | None = strawberry.field(default=strawberry.UNSET)
    not_in_: list[str] | None = strawberry.field(default=strawberry.UNSET)
    isnull: bool | None = strawberry.UNSET


@strawberry.input
class IntFilter:
    exact: int | None = strawberry.UNSET
    gt: int | None = strawberry.UNSET
    ge: int | None = strawberry.UNSET
    lt: int | None = strawberry.UNSET
    le: int | None = strawberry.UNSET
    in_: list[int] | None = strawberry.field(default=strawberry.UNSET)
    not_in_: list[int] | None = strawberry.field(default=strawberry.UNSET)
    isnull: bool | None = strawberry.UNSET
    range: list[int] | None = strawberry.UNSET


@strawberry.input
class BooleanFilter:
    exact: bool | None = strawberry.UNSET
    isnull: bool | None = strawberry.UNSET


@strawberry.input
class DateTimeFilter:
    exact: datetime | None = strawberry.UNSET
    ge: datetime | None = strawberry.UNSET
    gt: datetime | None = strawberry.UNSET
    lt: datetime | None = strawberry.UNSET
    le: datetime | None = strawberry.UNSET
    in_: list[datetime] | None = strawberry.field(default=strawberry.UNSET)
    not_in_: list[datetime] | None = strawberry.field(default=strawberry.UNSET)
    isnull: bool | None = strawberry.UNSET
    range: list[datetime] | None = strawberry.UNSET


@strawberry.input
class EnumFilter[EnumType]:
    exact: EnumType | None = strawberry.UNSET
    in_: list[EnumType] | None = strawberry.field(default=strawberry.UNSET)
    not_in_: list[EnumType] | None = strawberry.field(default=strawberry.UNSET)
    isnull: bool | None = strawberry.UNSET


@strawberry.input
class JSONFilter:
    """Postgres JSONB lookups (requires JSONB columns). Prefixed to avoid string ``contains`` clashes."""

    jsonb_contains: JSON | None = strawberry.UNSET
    jsonb_contained_by: JSON | None = strawberry.UNSET
    jsonb_has_key: str | None = strawberry.UNSET
    jsonb_has_any: list[str] | None = strawberry.UNSET
    jsonb_has_all: list[str] | None = strawberry.UNSET
    jsonb_path: str | None = strawberry.UNSET
    isnull: bool | None = strawberry.UNSET
