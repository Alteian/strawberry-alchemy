# Getting Started

This page walks through building a minimal blog API (Post / Comment) with
strawberry-alchemy, step by step.

The app exposes: a Relay `node` query, a `list` query with filters and pagination,
a Relay `connection` query, and `create` / `update` / `delete` mutations.

## 1. Define your SQLAlchemy models

Use the provided `Base` (PostgreSQL-only; it uses `sqlalchemy.dialects.postgresql.UUID`).
It supplies a UUID primary key, `created_at` / `updated_at` timestamps, and automatic
snake_case table names.

```python
# models.py
import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from strawberry_alchemy.models import Base


class Post(Base):
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str]

    comments: Mapped[list["Comment"]] = relationship(back_populates="post", cascade="all, delete-orphan")


class Comment(Base):
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("post.id"))
    body: Mapped[str]

    post: Mapped["Post"] = relationship(back_populates="comments")
```

For non-PostgreSQL databases (e.g. SQLite for tests) write your own base with
`sqlalchemy.Uuid` instead, keeping the same `id` / `created_at` / `updated_at`
columns.

## 2. Define an access filter (row-level security)

Every `BaseNodeType` subclass needs an access filter. It is applied to every query
the optimizer builds for that model, so rows the current user must not see are
filtered out at the SQL level.

```python
# access_filters.py
from typing import Any

from models import Post

from strawberry_alchemy.filtering import AccessControlFilter


class PostAccessFilter(AccessControlFilter):
    model_class = Post

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        # Allow everything in this example. Real apps scope by tenant/owner here,
        # e.g.: return query.where(model.user_id == context_user.id)
        return query
```

Note: subclasses must be named `*AccessFilter` (enforced by a metaclass) and must
declare `model_class`. See [Filtering → Access-control filters](filtering.md#access-control-filters)
for production patterns.

## 3. Define your GraphQL types

Subclass `BaseNodeType` and declare the access filter as a `ClassVar`. Scalar fields
that map to columns default to `strawberry.UNSET` so the optimizer can defer columns
the client did not request. Relationship fields point at other `BaseNodeType`
subclasses using `strawberry.lazy`.

```python
# types.py
import uuid
from typing import Annotated, ClassVar

import strawberry
from strawberry.types import Info

from access_filters import PostAccessFilter
from strawberry_alchemy import BaseNodeType, AnnotateExists, optimize_field


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar = PostAccessFilter()

    user_id: uuid.UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
    comments: list[Annotated["CommentType", strawberry.lazy(".types")]] | None = strawberry.UNSET

    @strawberry.field
    @optimize_field(AnnotateExists("comments"))
    async def has_comments(self, info: Info) -> bool:
        # Value was computed by a SQL EXISTS subquery; see query-optimizer.md
        return getattr(self, "_comments_exists", False)


@strawberry.type
class CommentType(BaseNodeType):
    access_filter: ClassVar = PostAccessFilter()

    post_id: uuid.UUID | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
    post: Annotated["PostType", strawberry.lazy(".types")] | None = strawberry.UNSET
```

## 4. Define filter inputs

Compose the provided filter inputs and add `AND` / `OR` lists for nesting.

```python
# filters.py
import strawberry

from strawberry_alchemy.filtering import DateTimeFilter, IDFilter, StringFilter


@strawberry.input
class PostFilter:
    AND: list["PostFilter"] | None = strawberry.UNSET
    OR: list["PostFilter"] | None = strawberry.UNSET
    id: IDFilter | None = strawberry.UNSET
    title: StringFilter | None = strawberry.UNSET
    body: StringFilter | None = strawberry.UNSET
    created_at: DateTimeFilter | None = strawberry.UNSET
```

## 5. Define a deletion handler (cascade deletes)

If a model has dependent rows that are not handled by database-level `ON DELETE
CASCADE`, collect their ids here; the repository calls the handler hooks around
`session.delete`.

```python
# deletion.py
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Comment, Post
from strawberry_alchemy.repository import BaseDeletionHandler, DependentMap


class PostDeletionHandler(BaseDeletionHandler[Post]):
    async def collect_dependents(
        self, session: AsyncSession, entity_id: UUID, instance: Post
    ) -> DependentMap:
        result = await session.execute(select(Comment.id).where(Comment.post_id == entity_id))
        return {"comments": [row[0] for row in result.fetchall()]}
```

## 6. Define your repository and schema

`BaseSchema` is a Pydantic model with `from_attributes` enabled, so it validates
directly from ORM instances. `BaseRepository` needs the model and schema classes.

```python
# repositories.py
import uuid
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from models import Comment, Post
from strawberry_alchemy import BaseRepository, BaseSchema


class PostSchema(BaseSchema):
    id: uuid.UUID | None = None
    title: str
    body: str
    user_id: uuid.UUID


class PostRepository(BaseRepository[Post, PostSchema]):
    model_cls: ClassVar[type[Any]] = Post
    schema_cls: ClassVar[type[Any]] = PostSchema
    relation_models: ClassVar[dict[str, type[Any]]] = {"comments": Comment}

    def __init__(self, session: AsyncSession, **kwargs: Any) -> None:
        super().__init__(session, model_cls=Post, schema_cls=PostSchema, **kwargs)
```

## 7. Write your queries

Queries delegate to `BaseNodeType` classmethods. The optimizer reads the actual
selection set of the incoming GraphQL query — no N+1 queries, unrequested columns
are deferred.

```python
# queries.py
import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

from filters import PostFilter
from types import PostType
from strawberry_alchemy import ListResult, OptimizedListConnection
from strawberry_alchemy.permissions import IsAuthenticated


@strawberry.type
class PostQueries:
    @strawberry.field(permission_classes=[IsAuthenticated])
    async def node(self, info: Info, id: GlobalID) -> PostType | None:
        return await PostType.resolve_node(node_id=id.node_id, info=info)

    @strawberry.field(permission_classes=[IsAuthenticated])
    async def list(
        self,
        info: Info,
        limit: int | None = None,
        offset: int | None = None,
        filters: PostFilter | None = strawberry.UNSET,
    ) -> ListResult[PostType]:
        return await PostType.resolve_list(info=info, limit=limit, offset=offset, filters=filters)

    @strawberry.field(permission_classes=[IsAuthenticated])
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
            info=info, after=after, before=before, first=first, last=last, filters=filters
        )


@strawberry.type
class Query:
    @strawberry.field
    def posts(self) -> PostQueries:
        return PostQueries()
```

## 8. Write your mutations

Mutations go through the repository. `create` returns a validated schema; use
`result.to_type(PostType)` (which calls `PostType.from_schema`) to build the
GraphQL type. `delete` runs the deletion handler hooks when one is passed.

```python
# mutations.py
import uuid

import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

from deletion import PostDeletionHandler
from repositories import PostRepository, PostSchema
from types import PostType
from strawberry_alchemy.permissions import IsAuthenticated


@strawberry.input
class CreatePostInput:
    title: str
    body: str


@strawberry.input
class UpdatePostInput:
    id: GlobalID
    title: str
    body: str


@strawberry.input
class DeletePostInput:
    id: GlobalID


@strawberry.type
class PostMutations:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def create_post(self, info: Info, input: CreatePostInput) -> PostType:
        session = await info.context.get_session()
        user = await info.context.identity
        schema = PostSchema(title=input.title, body=input.body, user_id=user.id)
        created = await PostRepository(session).create(schema=schema)
        return created.to_type(PostType)

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def update_post(self, info: Info, input: UpdatePostInput) -> PostType:
        session = await info.context.get_session()
        schema = PostSchema(id=uuid.UUID(input.id.node_id), title=input.title, body=input.body)
        result = await PostRepository(session).update(schema=schema)
        return result.to_type(PostType)

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    async def delete_post(self, info: Info, input: DeletePostInput) -> bool:
        session = await info.context.get_session()
        await PostRepository(session, deletion_handler=PostDeletionHandler()).delete(
            id=uuid.UUID(input.id.node_id)
        )
        return True


@strawberry.type
class Mutation:
    @strawberry.field
    def posts(self) -> PostMutations:
        return PostMutations()
```

## 9. Assemble the schema

The `relay_max_results` config value caps `first` / `last` in connections.

```python
# schema.py
import strawberry
from strawberry.schema.config import StrawberryConfig

from mutations import Mutation
from queries import Query

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    config=StrawberryConfig(auto_camel_case=True, relay_max_results=100),
)
```

## Context contract

`BaseNodeType` resolvers rely on your request context providing a few attributes.
This is the only wiring the library needs from your framework layer:

```python
# context.py
import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from strawberry.fastapi import BaseContext


class Context(BaseContext):
    def __init__(self) -> None:
        super().__init__()
        # current_user / identity: plain value, property, or awaitable are all fine
        self.current_user = {"id": "00000000-0000-0000-0000-000000000000", "role": "admin"}
        self.identity = self.current_user
        self._engine = create_async_engine("postgresql+asyncpg://...")
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        # Serializes concurrent SQL on the request session (required by resolvers)
        self.db_execution_lock = asyncio.Lock()

    async def get_session(self) -> AsyncSession:
        return self._session_factory()
```

Required attributes:

| Attribute | Type | Purpose |
|---|---|---|
| `get_session()` | async → `AsyncSession` | Session used by the optimizer |
| `identity` or `user` | value or awaitable | Current user; read by access filters and `filter_current_user` hints |
| `current_user` | value or property | Read by permission classes |
| `db_execution_lock` | `asyncio.Lock` | Serializes DB access on the request session |

## What happens behind the scenes

When `resolve_list` runs, `QueryOptimizer` inspects the selection set of the
incoming GraphQL operation, registers the type's access filter, and builds one
query: nested relationships become `selectinload`, unrequested scalar columns
become `defer()`ed, and `has_comments` is satisfied by an `EXISTS` subquery
annotation instead of loading all comments. See
[Query optimizer](query-optimizer.md) for the full details.
