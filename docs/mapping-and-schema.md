# Mapping & Schema

This page covers `BaseSchema` (the Pydantic layer) and the async mapping helpers that
convert SQLAlchemy instances into Strawberry types while respecting the selected
field tree.

## `BaseSchema`

`BaseSchema` is a Pydantic `BaseModel` with `from_attributes=True`, so you can
validate directly from ORM instances — including ones with lazy-loaded relationships.

```python
import uuid

from strawberry_alchemy import BaseSchema


class PostSchema(BaseSchema):
    id: uuid.UUID | None = None
    title: str
    body: str
    user_id: uuid.UUID
```

Key behaviors:

- **Safe from ORM instances**: a `model_validator` (mode `before`) dumps only the
  attributes actually loaded on the instance, so
  `PostSchema.model_validate(db_obj)` never triggers lazy loads or raises
  `MissingGreenlet` in async code.
- **`dump_for_db(exclude=None)`**: dumps the schema with `exclude_unset=True`,
  minus the excluded fields, and strips any remaining `strawberry.UNSET` values —
  exactly what `BaseRepository.create/update` use to build ORM instances.

```python
schema = PostSchema(title="Hello", body="...")     # user_id not set yet
data = schema.dump_for_db()                        # {"title": "Hello", "body": "..."}
data = schema.dump_for_db(exclude={"id", "created_at"})
```

- **`to_type(TargetType, **kwargs)`**: converts the schema into a Strawberry type.
  If the target has `from_schema` (all `BaseNodeType` subclasses do), it is used;
  otherwise the target is constructed from `model_dump(exclude_unset=True)`.

```python
gql_type = created_schema.to_type(PostType)            # == PostType.from_schema(created_schema)
gql_type = created_schema.to_type(PostType, title="Overridden")
```

Sparse schemas work for partial updates: unset fields are excluded from
`dump_for_db`, so `BaseRepository.update` only touches the fields you provided.

## Mapping SQLAlchemy → Strawberry

`map_sqlalchemy_to_type` and `map_sqlalchemy_list_to_types` convert ORM instances
into GraphQL types using the selected-fields dict the optimizer produces. They are
used internally by `resolve_node` / `resolve_list` / connections, but you can call
them from custom resolvers.

```python
import strawberry
from strawberry.types import Info

from strawberry_alchemy import map_sqlalchemy_list_to_types
from strawberry_alchemy import QueryOptimizer


@strawberry.field
async def search_posts(self, info: Info) -> list[PostType]:
    session = await info.context.get_session()
    optimizer = QueryOptimizer(info, session)
    optimizer.register_access_filter(Post, PostAccessFilter)

    async with info.context.db_execution_lock:
        result = await optimizer.optimize_query(
            model=Post,
            filters={"title__icontains": query},
            return_selected_fields=True,
            strawberry_type=PostType,
        )
    return await map_sqlalchemy_list_to_types(result.items, info, PostType, result.selected_fields)
```

Mapping rules:

- Only fields present in `selected_fields` are copied (`id` is always included);
  unloaded attributes are skipped — no lazy loads in async context.
- Relationship values are mapped recursively using the nested selection tree; the
  related Strawberry type is resolved from the schema by the `<ModelName>Type`
  convention (e.g. `Comment` → `CommentType`).
- `*_id` columns are converted to `GlobalID`s when the type annotation is a
  `GlobalID` (e.g. `user_id: GlobalID` → `GlobalID(type_name="UserType", node_id=...)`).
- Values produced by optimizer annotations (`instance._optimizer_annotations`, from
  `AnnotateExists` / `AnnotateCount` / etc.) are copied onto the type instance, which
  is how `@optimize_field` resolvers read `self._comments_exists`.
- Requested scalar fields missing from the instance are filled with `None` so the
  GraphQL response is stable.

Individual mapping:

```python
from strawberry_alchemy import map_sqlalchemy_to_type

gql_type = await map_sqlalchemy_to_type(db_obj, info, PostType, selected_fields)
```

## Related helpers

Also exported from `strawberry_alchemy.mapping`:

- `map_sqlalchemy_to_type_with_path(instance, info, target_type, selected_fields, field_path)` —
  maps using only the sub-tree at a dotted path (`"posts.items"`).
- `get_graphql_type_from_sqlalchemy(info, instance)` — resolves the Strawberry type
  for an ORM instance by naming convention.
- `extract_fields_at_path(selected_fields, path)` / `extract_nested_fields(selected_fields, field_path)` —
  slice the selection dict.
- `create_global_id_from_field(field_name, value)` — builds a `GlobalID` from a
  `*_id` field (`user_id` → `UserType`).

## The schema → type flow in mutations

The typical mutation flow chains `BaseSchema` → `BaseRepository` → `to_type`:

```python
@strawberry.mutation
async def create_post(self, info: Info, input: CreatePostInput) -> PostType:
    session = await info.context.get_session()
    schema = PostSchema(title=input.title, body=input.body, user_id=user.id)
    created = await PostRepository(session).create(schema=schema)   # returns PostSchema
    return created.to_type(PostType)                                # PostType.from_schema(created)
```

Overriding `from_schema` on your type is the extension point for computed values —
localized strings, GlobalID encoding, derived booleans:

```python
@strawberry.type
class TaskType(BaseNodeType):
    access_filter: ClassVar = TaskAccessFilter()

    title: str = strawberry.UNSET
    is_overdue: bool = False  # computed, not a column

    @classmethod
    def from_schema(cls, schema: TaskSchema, **kwargs: object) -> TaskType:
        return super().from_schema(
            schema,
            is_overdue=schema.due_at is not None and schema.due_at < datetime.now(tz=UTC),
            **kwargs,
        )
```
