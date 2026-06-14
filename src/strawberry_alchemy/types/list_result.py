import strawberry


@strawberry.type
class ListResult[T]:
    items: list[T]
    total_count: int | None = strawberry.UNSET
