# Query optimizer

`QueryOptimizer` is the core of the library. It reads `info.selected_fields`,
compiles them into load options and annotations, applies filters and ACL, and
returns a `QueryResult`.

```python
from strawberry_alchemy import QueryOptimizer, QueryResult

optimizer = QueryOptimizer(info, session)
optimizer.register_access_filter(Post, PostAccessFilter)
result: QueryResult = await optimizer.optimize_query(
    Post,
    filters=filters,
    limit=limit,
    offset=offset,
    return_total_count=True,
    strawberry_type=PostType,
)
# result.items, result.selected_fields, result.total_count
```

`BaseNodeType.resolve_*` constructs this for you. Use the class directly when you
need a custom session, mapping path, or subclass (custom order expressions).

## What it does automatically

| Behavior | Effect |
|---|---|
| Column deferral | Unrequested scalar columns are `defer()`'d |
| Relationship loading | Selected relations use `selectinload` (with nested ACL when registered) |
| Access control | Registered `AccessControlFilter` on root + nested loads |
| Filters / order / limit | Via `optimize_query` kwargs |
| Hints | `@optimize_field` dependencies merge into the load plan |

## `@optimize_field` hints

Decorate computed Strawberry fields so the optimizer knows what SQL to emit
before the resolver runs.

```python
from strawberry_alchemy import (
    AnnotateAncestry,
    AnnotateAnyExists,
    AnnotateCount,
    AnnotateCustom,
    AnnotateExists,
    PrefetchRelated,
    SelectColumns,
    optimize_field,
)
```

### `PrefetchRelated`

Eager-load a relationship (optionally a subset of fields, a SQL filter, and an
edge ACL):

```python
@strawberry.field
@optimize_field(PrefetchRelated("cover_images", filter=lambda rel: rel.c.is_primary.is_(True)))
async def cover_thumb_url(self, info: Info) -> str | None:
    ...
```

Constructor: `PrefetchRelated(relationship, fields=None, filter_current_user=False, filter=None, access_filter=None)`.

Shorthand: `@optimize_field("comments")` ≡ `PrefetchRelated("comments")`.

### `SelectColumns`

Undefer same-row scalar columns needed by a computed field:

```python
@optimize_field(SelectColumns("storage_key", "bucket"))
async def public_url(self, info: Info) -> str:
    ...
```

### `AnnotateExists` / `AnnotateAnyExists`

Correlated `EXISTS` → boolean attribute (default `_comments_exists` from
relationship name):

```python
@strawberry.field
@optimize_field(AnnotateExists("comments"))
async def has_comments(self, info: Info) -> bool:
    return bool(getattr(self, "_comments_exists", False))
```

`AnnotateAnyExists(["a", "b"])` ORs multiple EXISTS checks.

### `AnnotateCount`

Correlated `COUNT` annotation:

```python
@optimize_field(AnnotateCount("comments"))
async def comment_count(self, info: Info) -> int:
    return int(getattr(self, "_comments_count", 0))
```

### `AnnotateCustom`

Attach an arbitrary SQL expression (optional `mapper` to transform the value):

```python
@optimize_field(AnnotateCustom("comments", expression=..., to_attr="_custom", mapper=...))
```

### `AnnotateAncestry`

Recursive parent-walk CTE for trees:

```python
AnnotateAncestry(
    "parent",
    parent_field="parent_id",
    id_field="id",
    value_mode="ids",  # or "chain"
    include_self=True,
    root_first=True,
)
```

Dialect-aware aggregates; useful for breadcrumbs / path queries.

## Combining hints

Pass multiple hints to one decorator:

```python
@optimize_field(
    PrefetchRelated("media"),
    SelectColumns("slug"),
    AnnotateCount("likes"),
)
async def card(self, info: Info) -> Card:
    ...
```

## Subclassing for custom order

Override `process_order` when sort keys are computed expressions rather than
plain columns:

```python
class PropertyQueryOptimizer(QueryOptimizer):
    def process_order(self, model, order_input):
        # return (order_by_list, extra_dependency_tree)
        ...
```

See [Recipes](recipes.md#custom-order-columns).

## `QueryAnalyzer`

Optional diagnostics. Enable with env `QUERY_ANALYZER_ENABLED=1`, or pass an
instance:

```python
from strawberry_alchemy import QueryAnalyzer, QueryOptimizer

analyzer = QueryAnalyzer(
    log_sql=True,
    on_report=lambda report: metrics.emit(report.as_dict()),
)
optimizer = QueryOptimizer(info, session, analyzer=analyzer)
```

`QueryReport` exposes `.summary()` / `.as_dict()` for logging or OpenTelemetry
export via `on_report`.

## Selection-tree helpers

Advanced tooling re-exported at the package root:

| Helper | Role |
|---|---|
| `parse_selection_tree` | Raw selection dict → typed tree |
| `FieldPath` / `FieldSelection` / `LeafSelection` / `RelayConnectionSelection` | Typed nodes |
| `extract_at_path` | Drill into a selection by path |
| `selection_to_model_fields` | Tree → model field dict |
| `build_recursive_dependency_tree` / `merge_dependency_trees` / `normalize_dependency_fields` / `source_path_to_dependency_tree` | Hint dependency merging |
