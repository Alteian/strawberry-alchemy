# Types and models

## `Base` (SQLAlchemy)

`strawberry_alchemy.models.Base` is an abstract declarative base aimed at Postgres:

- UUID primary key (`sqlalchemy.dialects.postgresql.UUID`)
- `created_at` / `updated_at` (`DateTime(timezone=True)` with server defaults)
- Automatic `__tablename__` from the class name (`Post` → `post`)

```python
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from strawberry_alchemy import Base


class Post(Base):
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"))
    title: Mapped[str]
    body: Mapped[str]
```

!!! note "Non-Postgres databases"
    For SQLite (tests) or other dialects, define your own `DeclarativeBase` with
    `sqlalchemy.Uuid` (or equivalent) and the same column names. The blog example
    does this. GraphQL types and the optimizer only require those columns to exist
    on the mapped class — they do not require library `Base`.

## `SoftDeleteMixin`

Adds a nullable, indexed `deleted_at` column. Pair it with
`BaseRepository.soft_delete_field = "deleted_at"` so `get_by_id` / list queries
exclude soft-deleted rows by default and `soft_delete()` works.

```python
from strawberry_alchemy import SoftDeleteMixin

class Post(SoftDeleteMixin, Base):
    ...
```

## `BaseNodeType`

Relay `Node` GraphQL type that owns the read path into the optimizer.

**Built-in fields:** `id` (`NodeID[UUID]`), `created_at`, `updated_at` (default
`strawberry.UNSET`).

**Required ClassVar**

| ClassVar | Purpose |
|---|---|
| `access_filter` | `AccessControlFilter` subclass (or instance) — sets `model_class` |

**Optional ClassVars**

| ClassVar | Purpose |
|---|---|
| `config` | `NodeConfig` — nested to-many caps (`max_items`, per-field `fields`) |
| `CUSTOM_FILTERS` | `dict[str, Callable]` — non-column filter keys → SQL clause builders |
| `model_class` | Filled from `access_filter.model_class` |

Declare selected columns and relationships as Strawberry fields defaulting to
`UNSET`. Nested types often use `strawberry.lazy` to break cycles. Prefer
`NestedListResult` for to-many relations so clients get `hasMore` when the
default cap (100) truncates.

```python
from strawberry_alchemy import MaxItems, NestedListResult, NodeConfig

@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar[type[PostAccessFilter]] = PostAccessFilter
    config: ClassVar[NodeConfig] = NodeConfig(max_items=50, fields={"tags": None})

    title: str | None = strawberry.UNSET
    comments: NestedListResult[CommentType] | None = strawberry.UNSET
    tags: NestedListResult[TagType] | None = strawberry.field(
        default=strawberry.UNSET,
        extensions=[MaxItems(20)],
    )
```

Cap resolution (highest wins): `MaxItems` → `config.fields[name]` →
`config.max_items` → `100`. Pass `None` for unlimited. App-wide default:
`BaseNodeType.config = NodeConfig(max_items=50)` at import time, or subclass
once. Many-to-many (`secondary=`) collections are not capped; use Relay /
`resolve_list` for large pages.

### Construction helpers

- `PostType.from_schema(schema, **overrides)` — build from a `BaseSchema` /
  Pydantic model (nested schemas become related Strawberry types).
- Schema side: `schema.to_type(PostType)` prefers `from_schema` when available.

### Resolve classmethods

See [Queries](queries.md) for `resolve_node`, `resolve_nodes`, `resolve_list`,
and `resolve_connection`.

## `ListResult`

Offset/limit list wrapper:

```python
@strawberry.type
class ListResult[T]:
    items: list[T]
    total_count: int | None = strawberry.UNSET
```

Returned by `BaseNodeType.resolve_list`.

## `NestedListResult`

Capped nested to-many wrapper (selectin loads fetch `max_items + 1`):

```python
@strawberry.type
class NestedListResult[T]:
    items: list[T]
    has_more: bool = False
```

GraphQL selection: `comments { items { … } hasMore }`.

## Relay connection types

| Symbol | Role |
|---|---|
| `OptimizedListConnection[NodeType]` | Connection with `edges`, `page_info`, `total_count` |
| `Edge` / `PageInfo` | Re-exported from `strawberry.relay` |
| `SliceMetadata` | Cursor / first / last → start / end / `fetch_limit` math |

`resolve_connection` on `BaseNodeType` delegates to
`OptimizedListConnection.resolve_connection`, which uses the same optimizer path
as lists.

## `Ordering`

```python
from strawberry_alchemy import Ordering  # enum: ASC, DESC
```

Pass order inputs through to `resolve_list` / `resolve_connection` /
`QueryOptimizer.optimize_query` as your app's order input shape; the optimizer
maps known model columns (and subclasses can override `process_order` — see
[Recipes](recipes.md#custom-order-columns)).
