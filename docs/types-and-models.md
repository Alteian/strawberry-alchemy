# Types & Models

This page covers the SQLAlchemy model base, the `BaseNodeType` GraphQL type, and the
pagination/result wrapper types.

## The `Base` model

`strawberry_alchemy.models.Base` is a `DeclarativeBase` for PostgreSQL with a UUID
primary key, `created_at` / `updated_at` timestamps, and automatic snake_case table
naming.

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

    comments: Mapped[list["Comment"]] = relationship(back_populates="post")
```

What `Base` provides for you:

- `id` — `UUID(as_uuid=True)` primary key with `default=uuid.uuid4` and an index
- `created_at`, `updated_at` — `DateTime(timezone=True)` with server-side `now()`
  defaults; `updated_at` also has `onupdate=func.now()`
- `__tablename__` — derived from the class name: `Post` → `post`,
  `PostComment` → `post_comment`

> Note: the base is PostgreSQL-specific (it imports `sqlalchemy.dialects.postgresql.UUID`).
> For SQLite or other dialects, define your own base using `sqlalchemy.Uuid` — the rest
> of the library does not depend on `Base`; any declarative model works.

## `BaseNodeType`

`BaseNodeType` is a Strawberry Relay `Node` with `id: NodeID[uuid.UUID]` plus
`created_at` / `updated_at`. Subclass it for every type that is resolved through the
optimizer.

```python
# types.py
import uuid
from typing import Annotated, ClassVar

import strawberry

from access_filters import PostAccessFilter
from strawberry_alchemy import BaseNodeType


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar[type[PostAccessFilter]] = PostAccessFilter

    user_id: uuid.UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
    comments: list[Annotated["CommentType", strawberry.lazy(".types")]] | None = strawberry.UNSET
```

### Rules and conventions

- **`access_filter` is required.** Every subclass must declare an `access_filter`
  `ClassVar` (an `AccessControlFilter` subclass or instance). The class is also
  derived from it automatically (`model_class = access_filter.model_class`), but you
  can declare `model_class` explicitly as well.
- **Scalar fields default to `strawberry.UNSET`.** This lets the optimizer defer
  columns the client did not request and lets `from_schema` distinguish
  "not provided" from `None`. Fields that are nullable (`| None`) or temporal
  (`datetime`, `date`, `time`) are automatically normalized from `UNSET` to `None`
  in `__post_init__` and `from_schema`.
- **Relationship fields** point to other `BaseNodeType` subclasses. Use
  `strawberry.lazy` to avoid circular imports; the optimizer resolves nested load
  strategies and the mapper walks the selected field tree.
- **Naming convention:** the mapper resolves GraphQL types from model class names by
  convention `<ModelName>Type` (e.g. `Post` → `PostType`), also matching camelCase
  `*_id` columns to `GlobalID` fields (see [Mapping](mapping-and-schema.md)).

### Building types from schemas: `from_schema`

`from_schema` converts a Pydantic schema (typically from `BaseRepository` or your
service layer) into the GraphQL type. Extra keyword arguments override schema values,
which is how you inject computed fields like localized variants or GlobalID-encoded
foreign keys.

```python
from repositories import PostSchema
from types import PostType

schema = PostSchema(id=..., title="Hello", body="...", user_id=...)
gql_type = PostType.from_schema(schema)                       # plain mapping
gql_type = PostType.from_schema(schema, title="Overridden")   # kwargs win
gql_type = PostType.from_schema(schema, exclude={"body"})     # skip fields
```

Under the hood it dumps the schema with `exclude_unset=True`, keeps only attributes
matching the type's `__init__` parameters, applies your kwargs, coerces `UNSET` →
`None` for nullable/temporal fields, and constructs the instance. This is also what
`BaseSchema.to_type()` calls.

### Direct construction

You can construct types directly — useful in mutations where you already hold the
ORM instance. UNSET scalars are normalized to `None` for nullable/temporal fields.

```python
gql_type = PostType(
    id=db_obj.id,
    title=db_obj.title,
    body=db_obj.body,
    user_id=db_obj.user_id,
    comments=[...],
    created_at=db_obj.created_at,
    updated_at=db_obj.updated_at,
)
```

## `ListResult`

`ListResult[T]` is the plain list-pagination wrapper: `items` plus `total_count`.
Use it for offset/limit list queries; use `OptimizedListConnection` for Relay
cursor pagination.

```python
import strawberry

from strawberry_alchemy import ListResult

@strawberry.type
class Queries:
    @strawberry.field
    async def posts(self, info, limit: int | None = None, offset: int | None = None) -> ListResult[PostType]:
        return await PostType.resolve_list(info=info, limit=limit, offset=offset)
```

GraphQL shape:

```graphql
{
  posts(limit: 10) {
    items { id title }
    totalCount
  }
}
```

## `OptimizedListConnection`

`OptimizedListConnection[NodeType]` is a Relay `Connection` with `edges`,
`page_info`, and `total_count`, implementing the cursor slicing (`first` / `last` /
`after` / `before`) against the optimized query. You normally do not construct it
directly — return it from `BaseNodeType.resolve_connection`.

```python
from strawberry_alchemy import OptimizedListConnection

@strawberry.type
class Queries:
    @strawberry.field
    async def posts(
        self,
        info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> OptimizedListConnection[PostType]:
        return await PostType.resolve_connection(
            info=info, first=first, after=after, last=last, before=before
        )
```

GraphQL shape:

```graphql
{
  posts(first: 2) {
    edges {
      cursor
      node { id title }
    }
    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
    totalCount
  }
}
```

Details:

- Cursors are base64 `arrayconnection:<index>` offsets — the same format Strawberry
  Relay uses, so `first`/`after` round-trips work.
- `first` / `last` are validated against `info.schema.config.relay_max_results`.
- `SliceMetadata` is exported for callers that want to compute the slice arguments
  themselves (`SliceMetadata.from_arguments(info, before, after, first, last, max_results)`).
- The one extra row (`requested_count + 1`) is fetched internally to compute
  `has_next_page` / `has_previous_page` without a second query.

## `Ordering` enum

`Ordering` is a Strawberry enum (`ASC` / `DESC`) used inside order input types:

```python
import strawberry

from strawberry_alchemy.enums import Ordering


@strawberry.input
class PostOrder:
    created_at: Ordering | None = strawberry.UNSET
    title: Ordering | None = strawberry.UNSET
    updated_at: Ordering | None = strawberry.UNSET
```

Pass it to any resolver that accepts `order=` (see [Queries](queries.md#ordering)).
