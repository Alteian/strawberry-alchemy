# Query Optimizer

`QueryOptimizer` is the heart of the library. It reads the selection set of the
incoming GraphQL operation from `info.selected_fields` and compiles it into one
SQLAlchemy query:

- **Nested relationships** → `selectinload` (recursively, per relationship)
- **Unrequested scalar columns** → `defer()` (columns the client did not ask for are
  never loaded)
- **Computed fields** → SQL `EXISTS` / `COUNT` subquery annotations attached to each row
- **Filtered prefetches** → `selectinload(rel.and_(...))` when a hint declares
  per-user or custom conditions
- **Access control** → the registered `AccessControlFilter` is applied to the query

You rarely construct it directly: `BaseNodeType.resolve_node/resolve_nodes/resolve_list/resolve_connection`
do it for you (see [Queries](queries.md)). This page covers the declarative hints you
attach to computed fields.

## Declaring computed fields with `@optimize_field`

Apply `@optimize_field(...)` under `@strawberry.field` on methods of `BaseNodeType`
subclasses. The decorator records *hints* on the resolver; when the client selects
that field, the optimizer augments the query accordingly.

```python
from strawberry_alchemy import BaseNodeType, AnnotateExists, optimize_field


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar = PostAccessFilter()

    comments: list[Annotated["CommentType", strawberry.lazy(".types")]] | None = strawberry.UNSET

    @strawberry.field
    @optimize_field(AnnotateExists("comments"))
    async def has_comments(self, info) -> bool:
        return getattr(self, "_comments_exists", False)
```

Supported hint types (any combination may be passed):

| Hint | What it does |
|---|---|
| `"relationship_name"` (plain `str`) | Shorthand for `PrefetchRelated("relationship_name")` |
| `PrefetchRelated(relationship, fields=None, filter_current_user=False, filter=None)` | Merges extra columns into the selection tree for that relationship (even if the client did not select them); `filter_current_user` / `filter` turn it into a filtered `selectinload` |
| `SelectColumns(*column_names)` | Un-deferrs scalar columns of the *current* model so a resolver can read them even though the client did not select them |
| `AnnotateExists(relationship, filter_current_user=False, to_attr="", filter=None)` | Adds a correlated `EXISTS` subquery; the bool lands on the ORM instance as `_<relationship>_exists` (or `to_attr`) |
| `AnnotateAnyExists(relationships, ...)` | OR of `EXISTS` over several relationships; attribute `_<r1>_<r2>_any_exists` |
| `AnnotateCount(relationship, filter_current_user=False, to_attr="", filter=None)` | Adds a correlated `COUNT` scalar subquery; lands on `_<relationship>_count` (or `to_attr`) |
| `AnnotateCustom(relationship, expression, to_attr="", mapper=None, filter_current_user=False)` | Runs a custom SQL expression against the relationship; `mapper` post-processes the raw SQL value per row |
| Keyword args: `@optimize_field(comments=["id", "body"])` | Shorthand for `PrefetchRelated(relationship=name, fields=...)` |

Hints only fire when the client actually selects the decorated field. The optimizer
attaches annotation values to each ORM instance under `instance._optimizer_annotations`,
and the mapper copies them onto the GraphQL type instance — read them in the resolver
via `getattr(self, "_comments_exists", False)`.

## `AnnotateExists` — boolean computed fields without loading rows

Use for `has_comments`, `is_liked`, and similar flags. The value is a single `bool`
per row; the related table is never loaded.

```python
@strawberry.field
@optimize_field(AnnotateExists("comments", filter_current_user=True))
async def has_comments_from_me(self, info) -> bool:
    # with filter_current_user, the EXISTS also checks comments.user_id == current user
    return getattr(self, "_comments_exists", False)
```

`filter_current_user` resolves the current user from `info.context.identity`
(or `info.context.user`) and adds `related_model.user_id == user.id` to the subquery;
if there is no logged-in user the annotation evaluates to `False` without error.
A `filter=` callable adds arbitrary conditions:

```python
@optimize_field(AnnotateExists("comments", filter=lambda comment: comment.is_visible.is_(True)))
```

## `AnnotateCount` — counts without loading rows

```python
@strawberry.field
@optimize_field(AnnotateCount("comments", to_attr="comment_count"))
async def comment_count(self, info) -> int:
    return getattr(self, "comment_count", 0)
```

## `AnnotateCustom` — arbitrary SQL expressions

For anything beyond EXISTS/COUNT, provide an expression callable that receives
`(model, related_model, rel_property, [user_id])` and returns a SQL expression, plus
an optional `mapper` to convert the raw SQL value per row.

```python
from sqlalchemy import func

def latest_comment_date(model, related_model, rel_prop, user_id=None):
    return (
        select(func.max(related_model.created_at))
        .where(related_model.post_id == model.id)
        .scalar_subquery()
    )

@strawberry.field
@optimize_field(AnnotateCustom("comments", expression=latest_comment_date, to_attr="latest_comment_at"))
async def latest_comment_at(self, info) -> datetime | None:
    return getattr(self, "latest_comment_at", None)
```

## `PrefetchRelated` — computed fields that read related rows

Use when a resolver needs related rows the client might not have selected, or needs
a *filtered* view of a relationship. The example below prefetches only images that
are not excluded from a portal export, so the resolver can compute a cover thumbnail
without a per-row repository call.

```python
from strawberry_alchemy import BaseNodeType, PrefetchRelated, optimize_field

_COVER_IMAGE_PREFETCH = PrefetchRelated(
    "images",
    fields=["id", "s3_key", "variants", "position", "upload_status", "exclude_from_portal_export"],
    filter=lambda image: image.exclude_from_portal_export.is_(False),
)


@strawberry.type
class PropertyType(BaseNodeType):
    access_filter: ClassVar = PropertyAccessFilter()

    images: list[Annotated["PropertyImageType", strawberry.lazy(".types")]] | None = strawberry.UNSET

    @strawberry.field
    @optimize_field(_COVER_IMAGE_PREFETCH)
    async def cover_thumb_url(self, info) -> str | None:
        # self.images is already loaded (filtered) — just compute the URL
        cover = min(
            (img for img in (self.images or []) if img is not None),
            key=lambda img: getattr(img, "position", 10**9),
            default=None,
        )
        return presigned_download_url(getattr(cover, "s3_key", None)) if cover else None
```

Behavior notes:

- `fields` merge into the relationship's selection tree (existing client selections
  are preserved; dict trees merge recursively).
- `filter_current_user=True` scopes the prefetch to rows owned by the current user;
  `filter=` adds SQL conditions.
- When `filter_current_user` / `filter` are set, the relationship is loaded with
  `selectinload(rel.and_(*conditions))` instead of a plain `selectinload`.
- With no `fields`, all columns of the related model are selected.

## `SelectColumns` — un-defer storage columns for a resolver

Because unrequested scalar columns are `defer()`ed, reading them from a resolver
would trigger per-row lazy loads (which fail in async sessions). `SelectColumns`
un-deferrs named columns on the *current* model when the decorated field is selected,
so the resolver can read them safely.

```python
@strawberry.type
class UserType(BaseNodeType):
    access_filter: ClassVar = UserAccessFilter()

    avatar_s3_key: str | None = strawberry.UNSET  # not selected by client

    @strawberry.field
    @optimize_field(SelectColumns("avatar_s3_key"))
    async def avatar_url(self, info) -> str | None:
        key = getattr(self, "avatar_s3_key", None)
        if not key:
            return None
        return await presigned_download_url(key)
```

This is the pattern for computed fields that depend on same-row storage columns
(`s3_key`, `metadata_`, `variants`, etc.) — no extra query and no lazy loads.

## Dependency-tree helpers

These utilities build and combine the field-selection dictionaries used by
`PrefetchRelated(fields=...)` and are exported for advanced use:

```python
from strawberry_alchemy import build_recursive_dependency_tree, merge_dependency_trees, source_path_to_dependency_tree

# {"id": True, "children": {"id": True, "children": {"id": True}}}
tree = build_recursive_dependency_tree("children", fields=["id"], depth=2)

# {"post": {"user": {"email": True}}}
path_tree = source_path_to_dependency_tree("post.user.email")

merged = merge_dependency_trees({"id": True}, {"user": {"name": True}})
```

## `QueryAnalyzer` — see what the optimizer did

Set the environment variable `QUERY_ANALYZER_ENABLED` to any value to log a report
per optimized query: compiled SQL (data + count), duration, requested/deferred
fields, loaded relationships, load strategies, and annotation kinds.

```bash
QUERY_ANALYZER_ENABLED=1 uvicorn main:app
```

Sample output (logger `query_analyzer` at INFO):

```text
QueryAnalyzer: model=Post | queries=2 | rows=5 | fields=3 | deferred=2 | rels=1 | annotations=1 | duration=12.3ms
  [count] SELECT count(*) AS count_1 FROM (SELECT ...) AS anon_1 (1 rows, 3.1ms)
  [data]  SELECT post.id, post.title, ... (5 rows, 9.2ms)
```

You can also pass your own analyzer into `QueryOptimizer`:

```python
from strawberry_alchemy import QueryAnalyzer, QueryOptimizer

optimizer = QueryOptimizer(info, session, analyzer=QueryAnalyzer(log_sql=True, log_level=logging.INFO))
result = await optimizer.optimize_query(model=Post, strawberry_type=PostType)
report = optimizer.analyzer.report()  # QueryReport dataclass (summary(), as_dict())
```

## Behind the scenes: selection-set processing

The optimizer:

1. Reads `info.selected_fields[0].selections` (fragments included) and normalizes
   field names with `camel_to_snake`; Relay wrapper keys (`edges`, `node`,
   `pageInfo`, `items`, `totalCount`, `__typename`) are unwrapped.
2. Merges `@optimize_field` hints from the Strawberry type (`get_prefetch_map`).
3. Builds load options: relationships → recursive `selectinload` with nested options;
   scalar columns not requested → `defer()`.
4. Builds annotation subqueries for `AnnotateExists` / `AnnotateAnyExists` /
   `AnnotateCount` / `AnnotateCustom` and attaches them via `query.add_columns(...)`.
5. Applies access control, filters, ordering, limit/offset, and runs the query.
6. Copies per-row annotation values to `instance._optimizer_annotations`; the mapper
   moves them onto the GraphQL type instance (see [Mapping](mapping-and-schema.md)).

Result rows are deduplicated with `.unique()` so `selectinload` collections do not
produce duplicate objects.
