# Filtering

`FilterBuilder` turns Strawberry filter inputs (and plain dicts) into SQLAlchemy
`WHERE` clauses. Filters support nested `AND` / `OR`, relationship traversal,
custom callables, and Postgres JSONB operators.

## Operator inputs

Import from `strawberry_alchemy` (or `strawberry_alchemy.filtering`):

| Input | Typical operators |
|---|---|
| `IDFilter` | `exact`, `in_`, `not_in_`, `isnull` |
| `StringFilter` | `exact`, `iexact`, `contains`, `icontains`, `startswith`, `istartswith`, `endswith`, `iendswith`, `in_`, `not_in_`, `isnull` |
| `IntFilter` | `exact`, `gt`, `ge`, `lt`, `le`, `in_`, `not_in_`, `isnull`, `range` |
| `BooleanFilter` | `exact`, `isnull` |
| `DateFilter` | `exact`, `ge`, `gt`, `lt`, `le`, `in_`, `not_in_`, `isnull`, `range` (ISO date strings; for SQL `Date` columns) |
| `DateTimeFilter` | same comparison set as `DateFilter` (ISO datetimes; for `DateTime` columns) |
| `EnumFilter[T]` | `exact`, `in_`, `not_in_`, `isnull` |
| `JSONFilter` | `jsonb_contains`, `jsonb_contained_by`, `jsonb_has_key`, `jsonb_has_any`, `jsonb_has_all`, `jsonb_path`, `isnull` |

GraphQL field names use trailing underscores where needed (`in_`, `not_in_`);
`FilterBuilder` maps them to lookups `in` / `not_in`.

Boolean operator values such as `isnull: true` are **not** coerced to the column
type (fixed in 0.7.2), so `DateTimeFilter(isnull=True)` works.

## Composing a filter input

```python
import strawberry
from strawberry_alchemy import DateFilter, IDFilter, StringFilter


@strawberry.input
class PostFilter:
    title: StringFilter | None = strawberry.UNSET
    user_id: IDFilter | None = strawberry.UNSET
    published_on: DateFilter | None = strawberry.UNSET
    AND: list[PostFilter] | None = strawberry.UNSET
    OR: list[PostFilter] | None = strawberry.UNSET
```

Example GraphQL:

```graphql
query {
  posts {
    list(filters: {
      OR: [
        { title: { icontains: "alchemy" } }
        { userId: { exact: "…" } }
      ]
    }) {
      items { id title }
      totalCount
    }
  }
}
```

## Relationship filters

Nested filter objects on relationship field names become joins. The related
model's columns use the same operator inputs.

## Custom filters (`CUSTOM_FILTERS`)

For non-column keys (full-text shortcuts, office “tabs”, etc.), register callables
on the GraphQL type:

```python
from collections.abc import Callable
from typing import Any, ClassVar

def _title_search_filter(model: type[Any], value: Any) -> Any:
    term = f"%{value}%"
    return or_(model.title.ilike(term), model.body.ilike(term))


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar[...] = PostAccessFilter
    CUSTOM_FILTERS: ClassVar[dict[str, Callable[..., Any]]] = {
        "title_search": _title_search_filter,
    }
```

The filter input exposes `title_search: str | None`; `FilterBuilder` invokes the
callable instead of treating it as a column.

!!! tip "Older apps"
    Pre-0.2 code sometimes used `_custom_filters_registry` directly. Prefer
    `CUSTOM_FILTERS` on the type; the registry is wired automatically.

## JSONB key filters (Postgres)

Nested keys under a JSON/JSONB column compile to `column['key'].astext` lookups.
Partial JSONB selections stay undeferred and trim output keys to the selection
tree.

```python
@strawberry.input
class LocalizedStringFilter:
    cs: StringFilter | None = strawberry.UNSET
    en: StringFilter | None = strawberry.UNSET


@strawberry.input
class ListingFilter:
    title: LocalizedStringFilter | None = strawberry.UNSET  # JSONB column
```

`JSONFilter` covers containment / key existence operators on the whole document.

## `AccessControlFilter`

Row-level ACL applied to root queries, `totalCount`, and nested `selectinload`s
for that model. Subclass names **must** end with `AccessFilter`.

```python
class PostAccessFilter(AccessControlFilter):
    model_class = Post

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.user_id == context_user.id)
```

Attach via `BaseNodeType.access_filter` ClassVar, or pass `access_filter=` into
`resolve_*` / `PrefetchRelated`.

This is **application SQL ACL**, orthogonal to Postgres RLS policies — see
[Postgres RLS](postgres-rls.md) and [Recipes](recipes.md#app-tenancy-vs-alchemy-acl).

## `RelationAccessFilter`

`FieldExtension` for when a **nested edge** needs a different ACL than the
model's default registry entry (e.g. reporting-line manager still readable when
people-scope employment ACL would hide them).

```python
from strawberry_alchemy import RelationAccessFilter


@strawberry.type
class EmploymentType(BaseNodeType):
    ...
    manager: PersonType | None = strawberry.field(
        default=strawberry.UNSET,
        extensions=[RelationAccessFilter(ManagerPersonAccessFilter)],
    )
```

Optional `foreign_key=` enables a mutation `to_type()` fallback: if the
relationship attribute is missing but the FK is set, load via `resolve_nodes`
with the edge ACL.

```python
extensions=[RelationAccessFilter(ManagerPersonAccessFilter, foreign_key="manager_id")]
```

The override is **edge-local** — it does not overwrite the model-keyed ACL
registry used by other edges or root queries.

`PrefetchRelated(..., access_filter=...)` provides the same edge-local ACL for
`@optimize_field` prefetches (AND-ed with any `filter` / `filter_current_user`
conditions).
