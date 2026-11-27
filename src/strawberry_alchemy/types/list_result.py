import strawberry


@strawberry.type
class ListResult[T]:
    items: list[T]
    total_count: int | None = strawberry.UNSET


@strawberry.type
class NestedListResult[T]:
    """Capped nested to-many collection with truncation signal."""

    items: list[T]
    has_more: bool = False
