# Repository

`BaseRepository` is a generic async CRUD layer over `AsyncSession`. Pair it with
`BaseSchema` so you can move data both ways: schema → DB row and DB row → schema.

## Declaring a repository

```python
from typing import ClassVar
from strawberry_alchemy import BaseRepository

from .models import Comment, Post
from .schemas import CommentSchema, PostSchema


class PostRepository(BaseRepository[Post, PostSchema]):
    model_cls: ClassVar[type[Post]] = Post
    schema_cls: ClassVar[type[PostSchema]] = PostSchema
    relation_models: ClassVar[dict[str, type]] = {"comments": Comment}
    soft_delete_field: ClassVar[str | None] = "deleted_at"
```

With ClassVars set: `PostRepository(session)`. You can still pass
`model_cls=` / `schema_cls=` to the constructor for one-off use.

Optional: `deletion_handler=PostDeletionHandler()` for cascade / cleanup on
`delete()`.

## CRUD

| Method | Behavior |
|---|---|
| `get_by_id(id, *, include_deleted=False)` | Load one; raises `NotFoundError` if missing |
| `get_by_ids(ids, *, include_deleted=False)` | Batch load |
| `create(schema, should_commit=True)` | Insert from schema dump |
| `update(schema, should_commit=True, instance=None)` | Patch by `schema.id` |
| `delete(id, *, strict=False)` | Hard delete → `DeletionReport` |
| `soft_delete(id)` | Sets `soft_delete_field` timestamp |
| `add_related` / `remove_related` | M2M / collection membership via `relation_models` |

`apply_not_deleted(stmt)` adds the soft-delete predicate when
`soft_delete_field` is configured.

```python
repo = PostRepository(session)
created = await repo.create(schema=PostSchema(user_id=..., title="Hi", body="…"))
updated = await repo.update(schema=PostSchema(id=created.id, user_id=..., title="Yo", body="…"))
await repo.soft_delete(id=updated.id)
```

## Soft delete

1. Mix `SoftDeleteMixin` into the model (or add your own `deleted_at` column).
2. Set `soft_delete_field = "deleted_at"` on the repository.
3. Prefer `soft_delete()` for user-facing deletes; use `delete()` for hard
   cascades / admin cleanup.
4. Mirror the predicate in `AccessControlFilter` if list/node queries should hide
   soft-deleted rows.

## Deletion reports and handlers

`delete()` returns a `DeletionReport` instead of raising on every soft failure:

```python
report = await repo.delete(id=post_id, strict=False)
if report.has_failures:
    ...  # inspect report.failures / DeletionPartialFailure
```

`strict=True` raises when the handler reports failures.

### `BaseDeletionHandler`

```python
from strawberry_alchemy import BaseDeletionHandler, DependentMap


class PostDeletionHandler(BaseDeletionHandler[Post]):
    async def collect_dependents(self, session, entity_id, instance) -> DependentMap:
        ...
        return {"comments": list(comment_ids)}

    async def handle_cascade(self, session, entity_id, dependents: DependentMap) -> None:
        ...
```

`DependentMap` is `dict[str, list[uuid.UUID]]`. Collect first, then cascade (and
optionally block delete based on dependents in an app-level policy — see
[Recipes](recipes.md#deletion-policy-layer)).

## Production wrapping

Most apps subclass `BaseRepository` once for SAVEPOINT + integrity-error mapping.
See [Recipes: project repository subclass](recipes.md#project-repository-subclass).
