# Filtering

`FilterBuilder` translates Strawberry filter inputs into SQLAlchemy `WHERE` clauses.
Filter inputs are plain `@strawberry.input` classes composed from the provided
operator inputs, plus `AND` / `OR` lists for nesting.

## Built-in filter inputs

| Input | Operators |
|---|---|
| `IDFilter` | `exact`, `in` (`in_`), `not_in` (`not_in_`), `isnull` — values are Relay `GlobalID`s |
| `StringFilter` | `exact`, `iexact`, `contains`, `icontains`, `startswith`, `istartswith`, `endswith`, `iendswith`, `in`, `not_in`, `isnull` |
| `IntFilter` | `exact`, `gt`, `ge`, `lt`, `le`, `in`, `not_in`, `isnull`, `range` (2-element list) |
| `BooleanFilter` | `exact`, `isnull` |
| `DateTimeFilter` | `exact`, `ge`, `gt`, `lt`, `le`, `in`, `not_in`, `isnull`, `range` — accepts ISO-8601 strings, parsed via `dateutil` |
| `EnumFilter[T]` | `exact`, `in`, `not_in`, `isnull` — generic over a Strawberry enum |

## Declaring a filter input

Every field defaults to `strawberry.UNSET` (unset = "no condition"). Field names must
match model attribute names; camelCase GraphQL fields are converted to snake_case
automatically.

```python
# filters.py
import strawberry

from strawberry_alchemy.filtering import DateTimeFilter, EnumFilter, IDFilter, IntFilter, StringFilter


@strawberry.input
class PostFilter:
    AND: list["PostFilter"] | None = strawberry.UNSET
    OR: list["PostFilter"] | None = strawberry.UNSET
    id: IDFilter | None = strawberry.UNSET
    title: StringFilter | None = strawberry.UNSET
    body: StringFilter | None = strawberry.UNSET
    like_count: IntFilter | None = strawberry.UNSET
    status: EnumFilter[PostStatusEnum] | None = strawberry.UNSET
    created_at: DateTimeFilter | None = strawberry.UNSET
```

Pass the input to `resolve_list` / `resolve_connection` (or to
`QueryOptimizer.optimize_query(filters=...)`, which calls `FilterBuilder` for you):

```python
result = await PostType.resolve_list(
    info=info,
    filters=PostFilter(
        title=StringFilter(icontains="graphql"),
        created_at=DateTimeFilter(ge="2026-01-01T00:00:00Z"),
    ),
)
```

All conditions on the same field are `AND`ed; different fields are `AND`ed together.

## Nesting with `AND` / `OR`

```graphql
{
  posts(
    filters: {
      OR: [
        { title: { icontains: "graphql" } }
        { body: { icontains: "sqlalchemy" } }
      ]
      AND: [
        { status: { exact: PUBLISHED } }
        { likeCount: { gt: 10 } }
      ]
    }
  ) {
    items { id title }
  }
}
```

## Filtering across relationships

Relationship attributes on the filter input (or dotted `__` keys in raw dicts) produce
`OUTER JOIN`s to aliased related models, so you can filter a model by its related
rows.

```python
@strawberry.input
class CommentFilter:
    body: StringFilter | None = strawberry.UNSET
    post: PostFilter | None = strawberry.UNSET  # nested filter on the related Post
```

Or programmatically with dicts:

```python
from strawberry_alchemy.filtering import FilterBuilder

builder = FilterBuilder()
expr = await builder.build_filters(User, {"organization__name__icontains": "acme"})
```

## Custom filter fields

Register custom filter handlers on the Strawberry type via the `_custom_filters_registry`
class variable, keyed by model class and filter field name. Each handler receives the
model (possibly an alias) and the raw input value, and returns a SQL expression. This
is how you expose filters that do not map 1:1 to columns (search across JSONB, etc.).

```python
# custom_filters.py
from sqlalchemy import Text, cast, or_


def title_search_filter(model, value):
    if not value:
        return None
    pattern = f"%{' '.join(str(value).split())}%"
    return or_(
        cast(model.title, Text).ilike(pattern),
        cast(model.description, Text).ilike(pattern),
    )


PROPERTY_CUSTOM_FILTERS = {
    Property: {
        "title_search": title_search_filter,
    }
}
```

```python
# types.py
@strawberry.type
class PropertyType(BaseNodeType):
    access_filter: ClassVar = PropertyAccessFilter()
    _custom_filters_registry: ClassVar = PROPERTY_CUSTOM_FILTERS
```

```python
# filters.py — declare the field on the input type too
@strawberry.input
class PropertyFilter:
    title_search: str | None = strawberry.UNSET
```

The registry is read automatically by `QueryOptimizer` when `strawberry_type` is
passed, so `resolve_list` / `resolve_connection` pick it up. `FilterBuilder` also
accepts `custom_filters` directly: `FilterBuilder(custom_filters={User: {"is_active": handler}})`.

## Using `FilterBuilder` standalone

You can build SQL expressions without the optimizer:

```python
from strawberry_alchemy.filtering import FilterBuilder

builder = FilterBuilder()
expression = await builder.build_filters(Post, {"title__icontains": "graphql", "like_count__gt": 10})
stmt = select(Post).where(expression)
```

`build_filter_dict(filter_input)` converts a Strawberry input object into the flat
`{"field__lookup": value}` dict format (handling `AND`/`OR`, nested inputs, and
`GlobalID` decoding) — useful when you need the intermediate representation.

## Access-control filters (row-level security)

`AccessControlFilter` is a per-model filter applied to *every* query the optimizer
builds for that model. Subclasses:

- must be named `*AccessFilter` (metaclass-enforced),
- declare `model_class`,
- implement `async apply_filter(query, model, context_user) -> query`.

The `context_user` comes from `info.context.identity` (or `info.context.user`, either
plain values or awaitables).

```python
# access_filters.py
from typing import Any

from models import Post
from strawberry_alchemy.filtering import AccessControlFilter


class PostAccessFilter(AccessControlFilter):
    model_class = Post

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)  # anonymous users see nothing
        if getattr(context_user, "is_admin", False):
            return query               # admins see everything
        return query.where(model.user_id == context_user.id)  # owners see their rows
```

Registration is automatic through `BaseNodeType` (it passes the type's
`access_filter` to `QueryOptimizer.register_access_filter`). For raw optimizer use:

```python
optimizer = QueryOptimizer(info, session)
optimizer.register_access_filter(Post, PostAccessFilter)
# or by model name:
optimizer.register_access_filter_by_name("Post", PostAccessFilter)
```

Production patterns seen in real apps:

- **Admin-only**: `return query.where(False)` unless the user has an admin role.
- **Owner scoping**: `query.where(model.user_id == context_user.id)`.
- **Published-or-assigned**: `or_(model.is_published.is_(True), model.assigned_agent_id == user.id)`.
- **Child entities**: reuse the parent model's filter to inherit visibility rules.

Note: access control applies to the data query *and* the `total_count` query, so
counts never leak rows the user cannot see.

## Operator reference

`FilterOperators.LOOKUP_OPERATORS` maps lookup names to SQL expressions. The full set:
`exact`, `iexact`, `contains`, `icontains`, `in`, `not_in`, `gt`, `ge`, `lt`, `le`,
`startswith`, `istartswith`, `endswith`, `iendswith`, `range`, `isnull`.
Case-insensitive/string operators fall back to equality on non-string columns, and
`parse_filter_value` coerces incoming strings to the column's SQLAlchemy type.
