from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated, Any, ClassVar

import strawberry
from sqlalchemy import or_
from strawberry.types import Info

from strawberry_alchemy import AnnotateExists, BaseNodeType, optimize_field

from .access_filters import CommentAccessFilter, PostAccessFilter


def _title_search_filter(model: type[Any], value: Any) -> Any:
    term = f"%{value}%"
    return or_(model.title.ilike(term), model.body.ilike(term))


@strawberry.type
class CommentType(BaseNodeType):
    access_filter: ClassVar[type[CommentAccessFilter]] = CommentAccessFilter

    post_id: uuid.UUID | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
    post: Annotated[PostType | None, strawberry.lazy(".types")] = strawberry.UNSET


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar[type[PostAccessFilter]] = PostAccessFilter
    CUSTOM_FILTERS: ClassVar[dict[str, Callable[..., Any]]] = {
        "title_search": _title_search_filter,
    }

    user_id: uuid.UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
    comments: list[Annotated[CommentType, strawberry.lazy(".types")]] | None = strawberry.UNSET

    @strawberry.field
    @optimize_field(AnnotateExists("comments"))
    async def has_comments(self, info: Info) -> bool:
        return bool(getattr(self, "_comments_exists", False))
