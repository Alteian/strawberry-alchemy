from __future__ import annotations

import strawberry

from strawberry_alchemy.filtering import IDFilter, StringFilter


@strawberry.input
class PostFilter:
    title: StringFilter | None = strawberry.UNSET
    body: StringFilter | None = strawberry.UNSET
    user_id: IDFilter | None = strawberry.UNSET
    title_search: str | None = strawberry.UNSET
    AND: list[PostFilter] | None = strawberry.UNSET
    OR: list[PostFilter] | None = strawberry.UNSET
