from __future__ import annotations

import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

from strawberry_alchemy import ListResult, OptimizedListConnection

from .filters import PostFilter
from .types import PostType


@strawberry.type
class PostQueries:
    @strawberry.field
    async def node(self, info: Info, id: GlobalID) -> PostType | None:
        return await PostType.resolve_node(node_id=id.node_id, info=info)

    @strawberry.field
    async def list(
        self,
        info: Info,
        limit: int | None = None,
        offset: int | None = None,
        filters: PostFilter | None = strawberry.UNSET,
    ) -> ListResult[PostType]:
        return await PostType.resolve_list(info=info, limit=limit, offset=offset, filters=filters)

    @strawberry.field
    async def connection(
        self,
        info: Info,
        after: str | None = None,
        before: str | None = None,
        first: int | None = None,
        last: int | None = None,
        filters: PostFilter | None = strawberry.UNSET,
    ) -> OptimizedListConnection[PostType]:
        return await PostType.resolve_connection(
            info=info,
            after=after,
            before=before,
            first=first,
            last=last,
            filters=filters,
        )


@strawberry.type
class Query:
    @strawberry.field
    def posts(self) -> PostQueries:
        return PostQueries()
