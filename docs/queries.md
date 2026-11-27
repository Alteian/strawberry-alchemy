# Queries

`BaseNodeType` ships four classmethods that turn the GraphQL selection set into
one optimized SQLAlchemy query and map rows back to Strawberry types. Each
registers the type's `access_filter` with the optimizer automatically.

## Context prerequisites

Resolvers need the [context contract](getting-started.md#context-contract):
`get_session()`, `identity` / `user`, and `db_execution_lock`.

## `resolve_node`

Fetch a single row by UUID string (usually `GlobalID.node_id`).

```python
@strawberry.field
async def node(self, info: Info, id: GlobalID) -> PostType | None:
    return await PostType.resolve_node(node_id=id.node_id, info=info)
```

Optional per-call override:

```python
await PostType.resolve_node(
    node_id=id.node_id,
    info=info,
    access_filter=AdminPostAccessFilter,
)
```

Returns `None` when missing or filtered out by ACL.

## `resolve_nodes`

Batch fetch by IDs (order preserved; missing slots are `None`):

```python
await PostType.resolve_nodes(info=info, node_ids=["…", "…"])
```

Also used internally by `RelationAccessFilter` when falling back from a foreign
key on mutation `to_type` paths.

## `resolve_list`

Offset/limit listing with filters, ordering, and optional total count:

```python
@strawberry.field
async def list(
    self,
    info: Info,
    limit: int | None = None,
    offset: int | None = None,
    filters: PostFilter | None = strawberry.UNSET,
) -> ListResult[PostType]:
    return await PostType.resolve_list(
        info=info,
        limit=limit,
        offset=offset,
        filters=filters,
    )
```

Extra keyword arguments are forwarded to `QueryOptimizer.optimize_query`
(`order=`, `return_total_count=`, `access_filter=`, …).

## `resolve_connection`

Relay connection pagination (`after` / `before` / `first` / `last`) with
`totalCount`:

```python
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
```

## Per-call ACL

All four resolvers accept `access_filter=` to override the type ClassVar for that
call only. Use this for admin/ elevating views without forking the GraphQL type.

## Using `QueryOptimizer` directly

When you need a custom path (shared session, manual mapping), construct the
optimizer yourself:

```python
from strawberry_alchemy import QueryOptimizer, map_sqlalchemy_list_to_types


async def _get_optimized_result(cls, info: Info, **kwargs):
    session = await info.context.get_shared_session()  # app-specific
    optimizer = QueryOptimizer(info, session)
    optimizer.register_access_filter(cls.model_class, cls.access_filter)
    result = await optimizer.optimize_query(
        cls.model_class,
        strawberry_type=cls,
        **kwargs,
    )
    items = await map_sqlalchemy_list_to_types(
        result.items, info, cls, result.selected_fields
    )
    return result, items
```

See [Recipes: shared vs tenant sessions](recipes.md#shared-vs-tenant-sessions).

## Pagination notes

Nested list caps (`NodeConfig` / `MaxItems` / `NestedListResult`) and Relay
connections are **different** mechanisms:

| Surface | How it is restricted |
|---|---|
| Nested to-many (`NestedListResult` / bare `list[T]` via selectin) | `NodeConfig` / `MaxItems` (default 100; N+1 → `hasMore`) |
| Top-level Relay (`resolve_connection` / `OptimizedListConnection`) | Client `first` / `last`, hard-capped by `StrawberryConfig(relay_max_results=…)` (Strawberry default **100**) |
| Top-level list (`resolve_list`) | Explicit `limit=` on the resolve call — no automatic cap |

`NodeConfig` does **not** apply to connections. Connection page size +
`hasNextPage` come from `SliceMetadata` → `optimize_query(..., limit=fetch_limit)`.

```python
import strawberry
from strawberry.schema.config import StrawberryConfig

schema = strawberry.Schema(
    query=Query,
    config=StrawberryConfig(relay_max_results=50),
)
```

**Production pattern**

- Nested collections → `NestedListResult` + `NodeConfig` / `MaxItems`
- Large or scrollable sets → top-level (or dedicated) **connection** field with
  `first` / cursors
- Many-to-many (`secondary=`) nested edges are not capped by `NodeConfig` —
  prefer a connection-style field or an explicit filtered prefetch

Also:

- Prefer Relay connections for infinite scroll; use `ListResult` for simple
  admin tables.
- Soft-deleted rows are not filtered by the optimizer itself — apply
  `deleted_at IS NULL` in your `AccessControlFilter` or repository list helpers
  when needed.
