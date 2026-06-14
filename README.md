# strawberry-alchemy

<p align="center">
  <em>Batteries-included toolkit for building <strong>Strawberry GraphQL</strong> APIs backed by <strong>SQLAlchemy</strong></em>
</p>

<p align="center">
  <a href="https://github.com/Alteian/strawberry-alchemy/actions/workflows/ci.yml"><img src="https://github.com/Alteian/strawberry-alchemy/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/strawberry-alchemy"><img src="https://img.shields.io/pypi/v/strawberry-alchemy?color=%2334D058&label=pypi" alt="PyPI version"></a>
  <a href="https://pypi.org/project/strawberry-alchemy"><img src="https://img.shields.io/pypi/pyversions/strawberry-alchemy.svg?color=%2334D058" alt="Python versions"></a>
  <a href="https://github.com/Alteian/strawberry-alchemy/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

**Source Code**: [https://github.com/Alteian/strawberry-alchemy](https://github.com/Alteian/strawberry-alchemy)

---

## Features

| Module | What it does |
|---|---|
| **QueryOptimizer** | Analyzes Strawberry selection sets and builds a single optimized SQLAlchemy query — automatic `joinedload` / `selectinload`, column deferral, annotation injection |
| **FilterBuilder** | Translates Strawberry input types into SQLAlchemy `WHERE` clauses using a declarative operator system |
| **Repository** | Generic async CRUD with hard-delete, dependent-map cascading, and lifecycle hooks |
| **Types** | Relay `Connection` / `Edge` / `PageInfo` pagination, `ListResult`, `BaseNodeType` |
| **Mapping** | Async helpers to convert SQLAlchemy instances to Strawberry types respecting the selected field tree |
| **Permissions** | Protocol-based permission primitives: `IsAuthenticated`, `RolePermission`, `OwnerPermission`, `ObjectAccessPermission`, plus resolver pattern and resource-bag |
| **Models** | Tiny SQLAlchemy `DeclarativeBase` with UUID primary key, timestamps, and automatic table naming |
| **Utilities** | `camel_to_snake`, `Ordering` enum, common exceptions |

## Installation

```bash
pip install strawberry-alchemy
# or with uv
uv add strawberry-alchemy
```

## Quick Start

### 1. Define your SQLAlchemy model

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

### 2. Define an access filter (per-row security)

```python
# access_filters.py
from strawberry_alchemy.filtering import AccessControlFilter

class PostAccessFilter(AccessControlFilter):
    model_class = Post
    # Default: all users can see all posts. Override to scope by user_id.
```

### 3. Define your GraphQL types

```python
# types.py
import uuid
from typing import Annotated, ClassVar

import strawberry
from strawberry.types import Info

from strawberry_alchemy import BaseNodeType
from strawberry_alchemy.optimizer import AnnotateExists, optimize_field

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
        return getattr(self, "_comments_exists", False)


@strawberry.type
class CommentType(BaseNodeType):
    access_filter: ClassVar = PostAccessFilter()

    post_id: uuid.UUID | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
    post: Annotated["PostType", strawberry.lazy(".types")] | None = strawberry.UNSET
```

### 4. Define filter inputs

```python
# filters.py
import strawberry
from strawberry_alchemy.filtering import IDFilter, StringFilter, DateTimeFilter

@strawberry.input
class PostFilter:
    AND: list["PostFilter"] | None = strawberry.UNSET
    OR: list["PostFilter"] | None = strawberry.UNSET
    id: IDFilter | None = strawberry.UNSET
    title: StringFilter | None = strawberry.UNSET
    body: StringFilter | None = strawberry.UNSET
    created_at: DateTimeFilter | None = strawberry.UNSET
```

### 5. Define a deletion handler (cascade deletes)

```python
# deletion.py
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry_alchemy.repository import BaseDeletionHandler, DependentMap

class PostDeletionHandler(BaseDeletionHandler[Post]):
    async def collect_dependents(
        self, session: AsyncSession, entity_id: UUID, instance: Post
    ) -> DependentMap:
        result = await session.execute(select(Comment.id).where(Comment.post_id == entity_id))
        return {"comments": [row[0] for row in result.fetchall()]}
```

### 6. Define your repository and schema

```python
# repositories.py
from pydantic import BaseModel
from strawberry_alchemy import BaseRepository

class PostSchema(BaseModel):
    id: uuid.UUID | None = None
    title: str
    body: str
    user_id: uuid.UUID
    model_config = {"from_attributes": True}

class PostRepository(BaseRepository[Post, PostSchema]):
    relation_models = {"comments": Comment}

    def __init__(self, session: AsyncSession, **kwargs):
        super().__init__(session, model_cls=Post, schema_cls=PostSchema, **kwargs)
```

### 7. Write your queries

```python
# queries.py
import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

from strawberry_alchemy import OptimizedListConnection, ListResult
from strawberry_alchemy.permissions import IsAuthenticated

@strawberry.type
class PostQueries:
    @strawberry.field(permission_classes=[IsAuthenticated])
    async def node(self, info: Info, id: GlobalID) -> PostType | None:
        return await PostType.resolve_node(node_id=id.node_id, info=info)

    @strawberry.field(permission_classes=[IsAuthenticated])
    async def list(
        self, info: Info,
        limit: int | None = None,
        offset: int | None = None,
        filters: PostFilter | None = strawberry.UNSET,
    ) -> ListResult[PostType]:
        return await PostType.resolve_list(info=info, limit=limit, offset=offset, filters=filters)

    @strawberry.field(permission_classes=[IsAuthenticated])
    async def connection(
        self, info: Info,
        after: str | None = None,
        first: int | None = None,
        filters: PostFilter | None = strawberry.UNSET,
    ) -> OptimizedListConnection[PostType]:
        return await PostType.resolve_connection(info=info, after=after, first=first, filters=filters)


@strawberry.type
class Query:
    @strawberry.field
    def posts(self) -> PostQueries:
        return PostQueries()
```

### 8. Write your mutations

```python
# mutations.py
import uuid
import strawberry
from strawberry.types import Info
from strawberry.relay import GlobalID

from strawberry_alchemy.permissions import IsAuthenticated, OwnerPermission

@strawberry.input
class CreatePostInput:
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
        user = await info.context.user
        schema = PostSchema(title=input.title, body=input.body, user_id=user.id)
        result = await PostRepository(session).create(schema=schema)
        return result.to_type(PostType)

    @strawberry.mutation(permission_classes=[IsAuthenticated, OwnerPermission])
    async def delete_post(self, info: Info, input: DeletePostInput) -> bool:
        session = await info.context.get_session()
        await PostRepository(
            session, deletion_handler=PostDeletionHandler()
        ).delete(id=uuid.UUID(input.node_id))
        return True


@strawberry.type
class Mutation:
    @strawberry.field
    def posts(self) -> PostMutations:
        return PostMutations()
```

### 9. Assemble the schema

```python
# schema.py
import strawberry
from strawberry.schema.config import StrawberryConfig

schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    config=StrawberryConfig(auto_camel_case=True, relay_max_results=100),
)
```

The `QueryOptimizer` runs automatically behind the scenes — no N+1 queries, columns are deferred when not requested, and `has_comments` is resolved via a SQL `EXISTS` subquery instead of loading all comments.

## Development

```bash
git clone https://github.com/Alteian/strawberry-alchemy.git
cd strawberry-alchemy
uv sync

# Lint & test
uv run ruff check .
uv run pytest -v

# Build
uv build
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
