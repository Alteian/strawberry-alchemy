# Recipes

Production patterns distilled from real apps using strawberry-alchemy. Snippets
are anonymized and illustrative — adapt names to your domain.

## Project repository subclass

Wrap `BaseRepository` once for SAVEPOINT + conflict mapping so domain code stays
thin:

```python
from typing import ClassVar

from sqlalchemy.exc import IntegrityError
from strawberry_alchemy import BaseRepository, NotFoundError as RepoNotFoundError


class ConflictError(Exception):
    ...


class AppRepository(BaseRepository[ModelT, SchemaT]):
    model_cls: ClassVar[type]
    schema_cls: ClassVar[type]

    async def create(self, schema, should_commit=True):
        try:
            async with self.session.begin_nested():
                return await super().create(schema, should_commit=False)
        except IntegrityError as exc:
            raise ConflictError(...) from exc
        finally:
            if should_commit:
                await self.session.commit()
```

Callers then use `EmploymentRepository(session)` with ClassVar `model_cls` /
`schema_cls` / `relation_models` already set. Alias `NotFoundError` at the
boundary so GraphQL layers do not depend on the library exception name.

## Deletion policy layer

Build soft-vs-hard decisions and audit on top of `BaseDeletionHandler` instead of
a second protocol:

```python
class EmploymentDeletionHandler(BaseDeletionHandler[Employment]):
    async def collect_dependents(self, session, entity_id, instance) -> DependentMap:
        ...

    async def handle_cascade(self, session, entity_id, dependents) -> None:
        ...


async def delete_employment(repo, employment_id, *, hard: bool):
    if hard:
        report = await repo.delete(id=employment_id, strict=True)
        audit("hard_delete", report)
        return report
    return await repo.soft_delete(id=employment_id)
```

Keep cascade SQL inside the handler; keep product policy (when hard is allowed)
in the application service.

## App tenancy vs Alchemy ACL

| Layer | Mechanism | Owns |
|---|---|---|
| GraphQL row ACL | `AccessControlFilter` / `RelationAccessFilter` | “What this user may see in this API” |
| DB tenancy | Postgres RLS GUCs / `bind_company`-style helpers | “What this connection may touch at all” |

Typical flow:

1. Bind tenant GUCs at session/transaction start (`apply_rls_context` or your own
   `SET` helper).
2. Keep Alchemy ACL for people-scope / ownership rules that RLS does not encode.
3. When resolving nested fields that join another tenant's data, **rebind** GUCs
   for that tenant before running the nested optimizer query.
4. Do not nest `db_execution_lock` acquisitions — take the lock once per DB burst.

## When to use `RelationAccessFilter`

Use the type-level `access_filter` for the default visibility of a model. Add
`RelationAccessFilter` on a field when **one edge** must be wider or narrower:

- Employment list: people-scope ACL
- `employment.manager`: still readable for reporting line even if that person is
  outside the viewer's people scope

```python
manager: PersonType | None = strawberry.field(
    default=strawberry.UNSET,
    extensions=[RelationAccessFilter(ManagerAccessFilter, foreign_key="manager_id")],
)
```

Prefer `PrefetchRelated(..., access_filter=...)` when the edge is loaded only for
a computed field, not as a normal GraphQL relation.

## Non-column / tab filters

Office UIs often expose a single `listTab` enum. Map it through `CUSTOM_FILTERS`:

```python
def _list_tab_filter(model, value):
    if value == "NEEDS_APPROVAL":
        return model.status == "pending"
    if value == "MINE":
        return model.assignee_id == current_user_id_from_context()
    return True


class TravelType(BaseNodeType):
    CUSTOM_FILTERS = {"list_tab": _list_tab_filter}
```

Keep the GraphQL input field name aligned with the dict key (`list_tab`).

## Custom order columns

Subclass `QueryOptimizer` when sort keys are expressions:

```python
class ListingQueryOptimizer(QueryOptimizer):
    def process_order(self, model, order_input):
        if order_input and order_input.field == "priceSale":
            expr = case((model.listing_type == "sale", model.price), else_=None)
            direction = asc if order_input.direction == Ordering.ASC else desc
            return [direction(expr)], {}
        return super().process_order(model, order_input)
```

Validate that required filters are present when an order key only makes sense for
a subset of rows (e.g. sale vs rent).

## Field optimization toolkit

Common production combo on card / list types:

```python
@strawberry.field
@optimize_field(
    PrefetchRelated("media", filter=lambda m: m.c.kind == "cover"),
    SelectColumns("storage_key", "width", "height"),
    AnnotateCount("favorites"),
)
async def card(self, info: Info) -> CardPayload:
    ...
```

- `PrefetchRelated` — avoid N+1 on related rows needed only for the computed field
- `SelectColumns` — undefer scalars the card needs even if the client did not
  select them as GraphQL fields
- `AnnotateCount` / `AnnotateExists` — cheap aggregates without loading collections

## Mutations: inject actor / tenant

GraphQL inputs rarely include `actor_user_id` / `company_id`. Inject via kwargs:

```python
cmd = schema_from_input(
    CreateEmploymentCommand,
    input,
    actor_user_id=user.id,
    company_id=ctx.company_id,
)
```

Same pattern with `PostSchema.from_input(input, user_id=user.id)`.

## Shared vs tenant sessions

Catalog entities (global users, countries) may live on a shared database while
tenant data uses RLS-bound sessions. Override the optimized-result path on those
types:

```python
@classmethod
async def _get_optimized_result(cls, info, **kwargs):
    session = await info.context.get_shared_session()
    optimizer = QueryOptimizer(info, session)
    optimizer.register_access_filter(cls.model_class, cls.access_filter)
    return await optimizer.optimize_query(cls.model_class, strawberry_type=cls, **kwargs)
```

(Exact hook name depends on whether you subclass `BaseNodeType` methods or wrap
`resolve_list` — keep session choice next to the type that owns the data.)

## Boundary exception aliasing

At GraphQL / HTTP boundaries:

```python
from strawberry_alchemy import NotFoundError as RepoNotFoundError

try:
    return await repo.get_by_id(id)
except RepoNotFoundError:
    raise GraphQLNotFound(...)
```

Keeps library types out of API error schemas while staying explicit at the import.
