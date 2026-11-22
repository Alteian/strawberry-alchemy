# Getting started

This walkthrough builds a minimal blog API (Post / Comment) with strawberry-alchemy.

A complete, importable version lives in
[`examples/blog`](https://github.com/Alteian/strawberry-alchemy/tree/master/examples/blog)
and is covered by `make test ARGS="tests/examples"`. Prefer that tree when you want
copy-pasteable modules that stay in sync with the library.

The app exposes: a Relay `node` query, a filtered `list` query, a Relay
`connection` query, and `create` / `update` / `delete` mutations.

## Context contract

Every resolver that uses `BaseNodeType.resolve_*` expects `info.context` to provide:

| Attribute | Role |
|---|---|
| `async get_session() -> AsyncSession` | DB session for the request |
| `identity` (awaitable) or `user` | Current user for ACL / permissions |
| `db_execution_lock` | `asyncio.Lock` serializing optimizer DB work on the shared session |

```python
# context.py
import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ExampleUser:
    id: UUID
    role: str = "user"


@dataclass
class ExampleContext:
    session: AsyncSession
    user: ExampleUser | None
    db_execution_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get_session(self) -> AsyncSession:
        return self.session

    @property
    def identity(self) -> Any:
        async def _identity() -> ExampleUser | None:
            return self.user

        return _identity()
```

Wire this into your ASGI / FastAPI context getter the same way you would any
Strawberry context.

## 1. Models

The library `Base` uses Postgres `UUID` dialect types. For SQLite tests (as in the
blog example), define your own declarative base with `sqlalchemy.Uuid` and the same
`id` / `created_at` / `updated_at` columns. Soft-delete is optional via
`SoftDeleteMixin`.

```python
# models.py
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from strawberry_alchemy import SoftDeleteMixin


class ExampleBase(DeclarativeBase):
    pass


class Post(SoftDeleteMixin, ExampleBase):
    __tablename__ = "post"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    comments: Mapped[list["Comment"]] = relationship(back_populates="post")


class Comment(ExampleBase):
    __tablename__ = "comment"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("post.id"), index=True)
    body: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    post: Mapped[Post] = relationship(back_populates="comments")
```

## 2. Access filters

Every `BaseNodeType` needs an `AccessControlFilter` subclass (name must end with
`AccessFilter`). It is applied to root queries and nested `selectinload`s for that
model.

```python
# access_filters.py
from typing import Any

from strawberry_alchemy import AccessControlFilter

from .models import Comment, Post


class PostAccessFilter(AccessControlFilter):
    model_class = Post

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.user_id == context_user.id)


class CommentAccessFilter(AccessControlFilter):
    model_class = Comment

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.join(Post, model.post_id == Post.id).where(Post.user_id == context_user.id)
```

## 3. Filter inputs

Compose operator inputs (`StringFilter`, `IDFilter`, …) into a `@strawberry.input`.
`AND` / `OR` lists nest; non-column fields can be handled via `CUSTOM_FILTERS` on
the type (see next section).

```python
# filters.py
import strawberry

from strawberry_alchemy import IDFilter, StringFilter


@strawberry.input
class PostFilter:
    title: StringFilter | None = strawberry.UNSET
    body: StringFilter | None = strawberry.UNSET
    user_id: IDFilter | None = strawberry.UNSET
    title_search: str | None = strawberry.UNSET
    AND: list["PostFilter"] | None = strawberry.UNSET
    OR: list["PostFilter"] | None = strawberry.UNSET
```

## 4. GraphQL types

```python
# types.py
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
```

Scalar / relationship fields default to `strawberry.UNSET` so unrequested values
are not required on construction. `BaseNodeType` already provides Relay `id`,
`created_at`, and `updated_at`.

## 5. Queries

```python
# queries.py
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
        return await PostType.resolve_list(
            info=info, limit=limit, offset=offset, filters=filters
        )

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
```

## 6. Schemas and repositories

```python
# schemas.py
import uuid
from datetime import datetime

from strawberry_alchemy import BaseSchema


class CommentSchema(BaseSchema):
    id: uuid.UUID | None = None
    post_id: uuid.UUID | None = None
    body: str


class PostSchema(BaseSchema):
    id: uuid.UUID | None = None
    user_id: uuid.UUID
    title: str
    body: str
    deleted_at: datetime | None = None
    comments: list[CommentSchema] | None = None
```

```python
# repositories.py
from typing import ClassVar

from strawberry_alchemy import BaseRepository

from .models import Comment, Post
from .schemas import CommentSchema, PostSchema


class PostRepository(BaseRepository[Post, PostSchema]):
    model_cls: ClassVar[type[Post]] = Post
    schema_cls: ClassVar[type[PostSchema]] = PostSchema
    relation_models: ClassVar[dict[str, type]] = {"comments": Comment}
    soft_delete_field: ClassVar[str | None] = "deleted_at"


class CommentRepository(BaseRepository[Comment, CommentSchema]):
    model_cls: ClassVar[type[Comment]] = Comment
    schema_cls: ClassVar[type[CommentSchema]] = CommentSchema
```

With ClassVars set, callers use `PostRepository(session)` without repeating model /
schema types.

## 7. Deletion handler

```python
# deletion.py
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from strawberry_alchemy import BaseDeletionHandler, DependentMap

from .models import Comment, Post


class PostDeletionHandler(BaseDeletionHandler[Post]):
    async def collect_dependents(
        self, session: AsyncSession, entity_id: uuid.UUID, instance: Post
    ) -> DependentMap:
        rows = (
            await session.execute(select(Comment.id).where(Comment.post_id == entity_id))
        ).scalars().all()
        return {"comments": list(rows)}

    async def handle_cascade(
        self, session: AsyncSession, entity_id: uuid.UUID, dependents: DependentMap
    ) -> None:
        comment_ids = dependents.get("comments") or []
        if comment_ids:
            await session.execute(delete(Comment).where(Comment.id.in_(comment_ids)))
```

## 8. Mutations

```python
# mutations.py
import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

from strawberry_alchemy import IsAuthenticated, OwnerPermission, prepare_mutation_resources

from .deletion import PostDeletionHandler
from .repositories import PostRepository
from .schemas import PostSchema
from .types import PostType


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
    @strawberry.mutation
    async def create_post(self, info: Info, input: CreatePostInput) -> PostType:
        session = await info.context.get_session()
        user = await info.context.identity
        schema = PostSchema.from_input(input, user_id=user.id)
        created = await PostRepository(session).create(schema=schema)
        return created.to_type(PostType)

    @strawberry.mutation
    async def update_post(self, info: Info, input: UpdatePostInput) -> PostType:
        session = await info.context.get_session()
        schema = PostSchema.from_input(
            input, user_id=(await info.context.identity).id
        )
        result = await PostRepository(session).update(schema=schema)
        return result.to_type(PostType)

    @strawberry.mutation
    async def delete_post(self, info: Info, input: DeletePostInput) -> bool:
        session = await info.context.get_session()
        repo = PostRepository(session, deletion_handler=PostDeletionHandler())
        schema = PostSchema.from_input(input)
        await prepare_mutation_resources(
            info,
            {"post_id": input.id},
            loaders={"post_id": lambda value: repo.get_by_id(value)},
            permissions=[
                IsAuthenticated(),
                OwnerPermission(owner_field="user_id", resource_key="post_id"),
            ],
        )
        report = await repo.delete(id=schema.id, strict=False)
        return not report.has_failures
```

`from_input` / `schema_from_input` copy same-named fields, decode `GlobalID` →
`UUID`, skip `UNSET`, and let kwargs (like `user_id`) win.

## 9. Schema

```python
# schema.py
import strawberry

from .mutations import Mutation
from .queries import Query

schema = strawberry.Schema(query=Query, mutation=Mutation)
```

## Next steps

- [Types and models](types-and-models.md) — `Base`, connections, ordering
- [Filtering](filtering.md) — operators, JSONB, `RelationAccessFilter`
- [Query optimizer](query-optimizer.md) — all `@optimize_field` hints
- [Recipes](recipes.md) — production wrapping patterns
