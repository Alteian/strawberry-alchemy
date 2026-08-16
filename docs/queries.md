# Queries

`BaseNodeType` ships four classmethods that turn the incoming GraphQL selection set
into one optimized SQLAlchemy query and map the result back to Strawberry types.
Each registers the type's access filter with the optimizer automatically.

## `resolve_node` — fetch one entity by Relay id

Use it for Relay `node` fields or single-item queries. Returns `None` when not found.

```python
import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

@strawberry.type
class PostQueries:
    @strawberry.field
    async def node(self, info: Info, id: GlobalID) -> PostType | None:
        return await PostType.resolve_node(node_id=id.node_id, info=info)
```

`node_id` is the raw (non-base64) id string from `GlobalID.node_id`. You can also
pass `resolve_node` extra keyword arguments that are forwarded to
`QueryOptimizer.optimize_query` (e.g. `filter_context_user=True`).

## `resolve_nodes` — fetch several entities in one query

Useful for batch loaders and connections you build yourself. Runs one query
(`WHERE id IN (...)`) and returns the found entities as GraphQL types.

```python
types = await PostType.resolve_nodes(info=info, node_ids=[id1, id2, id3])
```

## `resolve_list` — offset/limit list with filters and ordering

Returns `ListResult[PostType]` with `items` and `total_count`. All arguments
(limit, offset, filters, order, and any `optimize_query` kwargs) are optional.

```python
import strawberry
from strawberry.types import Info

from filters import PostFilter
from orders import PostOrder
from strawberry_alchemy import ListResult

@strawberry.type
class PostQueries:
    @strawberry.field
    async def list(
        self,
        info: Info,
        limit: int | None = None,
        offset: int | None = None,
        filters: PostFilter | None = strawberry.UNSET,
        order: PostOrder | None = strawberry.UNSET,
    ) -> ListResult[PostType]:
        return await PostType.resolve_list(
            info=info, limit=limit, offset=offset, filters=filters, order=order
        )
```

`total_count` runs a `SELECT count(*)` over the same filtered query (with joins and
access control applied), so the count reflects what the user may see.

## `resolve_connection` — Relay cursor pagination

Returns `OptimizedListConnection[PostType]` implementing `first` / `last` / `after` /
`before` slicing. Pass `filters` and `order` exactly like `resolve_list`.

```python
import strawberry
from strawberry.types import Info

from strawberry_alchemy import OptimizedListConnection

@strawberry.type
class PostQueries:
    @strawberry.field
    async def connection(
        self,
        info: Info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
        filters: PostFilter | None = strawberry.UNSET,
        order: PostOrder | None = strawberry.UNSET,
    ) -> OptimizedListConnection[PostType]:
        return await PostType.resolve_connection(
            info=info, first=first, after=after, last=last, before=before,
            filters=filters, order=order,
        )
```

## Ordering

Order inputs are plain Strawberry inputs whose fields are `Ordering | None`
(see [Types & models](types-and-models.md#ordering-enum)). The optimizer turns set
fields into `ORDER BY` clauses; unset fields are ignored.

```python
# orders.py
import strawberry

from strawberry_alchemy.enums import Ordering


@strawberry.input
class PostOrder:
    created_at: Ordering | None = strawberry.UNSET
    title: Ordering | None = strawberry.UNSET
```

```python
types = await PostType.resolve_list(info=info, order=PostOrder(created_at=Ordering.DESC, title=Ordering.ASC))
```

Ordering details:

- Field names are matched against model attributes (camelCase fields are converted
  to snake_case automatically).
- When no order is passed, the optimizer defaults to `created_at DESC, updated_at
  DESC, id DESC` (whichever of those columns exist on the model).
- Ordering by relationship fields (a nested input on a relationship attribute) is
  supported and translates into `ORDER BY` on the joined related model's column.

## Filtering via resolvers

Filters are the Strawberry input types built from `IDFilter`, `StringFilter`, etc.
(see [Filtering](filtering.md)). `FilterBuilder` converts them into `WHERE` clauses;
`AND`/`OR` lists nest, and relationship paths produce joins. `strawberry.UNSET` means
"no filter".

```python
@strawberry.input
class PostFilter:
    AND: list["PostFilter"] | None = strawberry.UNSET
    OR: list["PostFilter"] | None = strawberry.UNSET
    title: StringFilter | None = strawberry.UNSET
    created_at: DateTimeFilter | None = strawberry.UNSET
```

## Advanced: using `QueryOptimizer` directly

If you need a query that is not one of the four shapes above (custom joins,
aggregations, arbitrary `target_field_path`), instantiate the optimizer yourself.

```python
from strawberry_alchemy import QueryOptimizer

async def custom_resolver(info: Info) -> list[PostType]:
    session = await info.context.get_session()
    optimizer = QueryOptimizer(info, session)
    optimizer.register_access_filter(Post, PostAccessFilter)

    async with info.context.db_execution_lock:
        result = await optimizer.optimize_query(
            model=Post,
            filters=filters,
            order=order,
            limit=limit,
            offset=offset,
            return_total_count=True,
            return_selected_fields=True,
            strawberry_type=PostType,
        )
    return await map_sqlalchemy_list_to_types(result.items, info, PostType, result.selected_fields)
```

`optimize_query` signature (all keyword arguments are optional):

```python
async def optimize_query(
    self,
    model: type,
    node_ids: Iterable[str] | None = None,          # filter by UUID id list
    filters: dict | StrawberryInput | None = None,  # dict or Strawberry filter input
    return_selected_fields: bool = False,           # include the normalized selection tree in QueryResult
    filter_context_user: bool = False,              # force model.user_id == current user
    apply_access_control: bool = True,              # apply registered AccessControlFilter
    order: Any = None,                              # Strawberry order input
    limit: int | None = None,
    offset: int | None = None,
    return_total_count: bool = False,
    target_field_path: str | None = None,           # "posts.items" — restrict selection tree to a sub-path
    strawberry_type: type | None = None,            # enables @optimize_field hints and custom filters
    exclude_prefetch: set[str] | None = None,       # field names whose prefetch hints are skipped
) -> QueryResult
```

`QueryResult` is a frozen dataclass with `items`, `selected_fields`, and
`total_count`.

## GraphQL queries you can now run

```graphql
query PostPage {
  posts(first: 5, filters: { title: { icontains: "graphql" } }, order: { createdAt: DESC }) {
    edges { cursor node { id title body hasComments } }
    pageInfo { hasNextPage endCursor }
    totalCount
  }
}
```

`hasComments` is satisfied by a SQL `EXISTS` subquery — see
[Query optimizer](query-optimizer.md) for how to declare such computed fields.
