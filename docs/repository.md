# Repository

`BaseRepository` is a generic async CRUD layer over `AsyncSession`. Pair it with
`BaseSchema` (a Pydantic model with `from_attributes=True`) so you can validate both
directions: schema → DB row and DB row → schema.

## Subclassing

```python
# repositories.py
import uuid
from typing import Any, ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from models import Comment, Post
from strawberry_alchemy import BaseRepository, BaseSchema


class PostSchema(BaseSchema):
    id: uuid.UUID | None = None
    title: str
    body: str
    user_id: uuid.UUID


class PostRepository(BaseRepository[Post, PostSchema]):
    model_cls: ClassVar[type[Any]] = Post
    schema_cls: ClassVar[type[Any]] = PostSchema

    # Relations managed by create/update nested processing and add_related/remove_related
    relation_models: ClassVar[dict[str, type[Any]]] = {"comments": Comment}

    def __init__(self, session: AsyncSession, **kwargs: Any) -> None:
        super().__init__(session, model_cls=Post, schema_cls=PostSchema, **kwargs)
```

The base constructor signature is
`BaseRepository(session, model_cls, schema_cls, *, deletion_handler=None)`.

## Reads

```python
schema = await PostRepository(session).get_by_id(post_id)          # raises NotFoundError if missing
schemas = await PostRepository(session).get_by_ids([id1, id2])     # missing ids are simply absent
```

- `get_by_id(id, options=None)` — accepts SQLAlchemy loader options, e.g.
  `options=[selectinload(Post.comments)]`.
- `get_by_ids(ids, options=None)` — same, for batches.
- Both return schema instances, not ORM instances.

## Create

```python
schema = PostSchema(title="Hello", body="World", user_id=user.id)
created = await PostRepository(session).create(schema=schema)
```

`create` builds the ORM instance from `schema.dump_for_db()` (excluding fields listed
in `relation_models`), flushes, validates the result back into the schema, and
commits unless `should_commit=False`. An `IntegrityError` is rolled back and re-raised
as `ValueError`.

## Update

```python
schema = PostSchema(id=post_id, title="Updated", body="...")
updated = await PostRepository(session).update(schema=schema)
```

`update` requires `schema.id`; it loads the row (or merges `instance=` when passed),
applies non-relation fields, refreshes/updates managed relations, validates, and
commits. Raises `NotFoundError` when the row does not exist. Sparse schemas work:
fields left unset are skipped by `dump_for_db`'s `exclude_unset=True` behavior.

## Delete

```python
report = await PostRepository(session).delete(id=post_id)
# report: DeletionReport — empty failures on success

# Handlers can record soft external failures; raise if you care:
await PostRepository(session, deletion_handler=handler).delete(id=post_id, strict=True)
```

Raises `NotFoundError` if missing. Always returns a `DeletionReport`. When a
`deletion_handler` is provided, the hook sequence below runs around
`session.delete`; commit happens at the end unless `should_commit=False`.
With `strict=True`, a non-empty failure list raises `DeletionPartialFailure`
(the DB delete still completed). Handlers record failures via
`self.report.record(component, operation, target, error)`.

## Soft delete (opt-in)

Hard `delete` is unchanged. For soft-delete, declare a timestamp column on the
model (or use `SoftDeleteMixin`) and set `soft_delete_field` on the repository:

```python
from strawberry_alchemy import SoftDeleteMixin, BaseRepository

class Post(Base, SoftDeleteMixin):
    ...

class PostRepository(BaseRepository[Post, PostSchema]):
    soft_delete_field = "deleted_at"

await repo.soft_delete(id=post_id)
await repo.get_by_id(post_id)                      # NotFoundError if soft-deleted
await repo.get_by_id(post_id, include_deleted=True)
```

## Relation management

For many-to-many style updates, declare the relationship in `relation_models` and use:

```python
await PostRepository(session).add_related(id=post_id, relation_name="comments", related_ids=[c1, c2])
await PostRepository(session).remove_related(id=post_id, relation_name="comments", related_ids=[c1])
```

Both raise `ValueError` for undeclared relations and `NotFoundError` for a missing
parent; `add_related` skips ids already present.

Nested create/update: if the schema carries data for a key in `relation_models`
(a list of schemas or a single schema), `create`/`update` process it recursively —
items with ids are loaded and updated, items without ids are created.

## Deletion handlers and cascade deletes

`BaseDeletionHandler[ModelT]` gives you explicit control over dependent rows when the
database does not (or should not) cascade. Subclass it, override
`collect_dependents`, and pass an instance to the repository.

```python
# deletion.py
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Comment, Post
from strawberry_alchemy.repository import BaseDeletionHandler, DependentMap


class PostDeletionHandler(BaseDeletionHandler[Post]):
    async def collect_dependents(
        self, session: AsyncSession, entity_id: UUID, instance: Post
    ) -> DependentMap:
        # DependentMap is dict[str, list[uuid.UUID]] — one key per dependent kind
        result = await session.execute(select(Comment.id).where(Comment.post_id == entity_id))
        return {"comments": [row[0] for row in result.fetchall()]}

    async def cleanup_external(self, session, entity_id, instance, dependents) -> None:
        # e.g. delete files in S3, clear caches, publish events — before the row is gone
        ...

    async def handle_cascade(self, session, entity_id, dependents) -> None:
        comment_ids = dependents.get("comments", [])
        if comment_ids:
            await session.execute(delete(Comment).where(Comment.id.in_(comment_ids)))
```

Hook order during `BaseRepository.delete`:

1. `collect_dependents(session, entity_id, instance) -> DependentMap`
2. `pre_delete(session, entity_id, instance, dependents)`
3. `cleanup_external(session, entity_id, instance, dependents)` — external side effects
4. `handle_cascade(session, entity_id, dependents)` — delete dependents in-session
5. `session.delete(instance)`
6. `post_delete(session, entity_id, dependents)`

All hooks default to no-ops, so you only override what you need. The dependents map is
passed through every hook, letting later hooks see what was collected.

## Commit control

Every mutating method accepts `should_commit: bool = True`. Pass `False` when you
want to batch operations in a larger transaction and commit yourself.
