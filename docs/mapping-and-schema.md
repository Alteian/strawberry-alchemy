# Mapping and schema

This page covers the Pydantic DTO layer (`BaseSchema`) and the helpers that map
SQLAlchemy instances into Strawberry types while respecting the selection tree.

## `BaseSchema`

Pydantic model configured with `from_attributes=True`, safe to validate from ORM
instances and from GraphQL inputs.

```python
from strawberry_alchemy import BaseSchema
import uuid


class PostSchema(BaseSchema):
    id: uuid.UUID | None = None
    user_id: uuid.UUID
    title: str
    body: str
```

### `dump_for_db`

```python
data = schema.dump_for_db(exclude={"comments"})
```

`model_dump(exclude_unset=True)` plus dropping any remaining `strawberry.UNSET`
values — suitable for `session.merge` / column assignment.

### `to_type`

```python
post_type = schema.to_type(PostType)
# or with overrides:
post_type = schema.to_type(PostType, title="Override")
```

Prefers `PostType.from_schema(schema, **kwargs)` when available; otherwise
constructs from dumped fields. Nested `BaseSchema` values (and lists of them)
become related Strawberry types, including `Annotated` / `strawberry.lazy`
fields. Cyclic back-references resolve to `None`.

### `from_input` / `schema_from_input`

Build a schema (or any Pydantic `BaseModel`) from a Strawberry input object:

```python
from strawberry_alchemy import schema_from_input

schema = PostSchema.from_input(input, user_id=actor.id)
# equivalent:
schema = schema_from_input(PostSchema, input, user_id=actor.id)
```

Rules:

- Same-named fields are copied
- `relay.GlobalID` → `uuid.UUID` (lists decoded item-wise)
- Omitted / `UNSET` fields keep model defaults
- Explicit `None` is preserved
- Keyword arguments always win (inject `actor_user_id`, `company_id`, …)

Use plain `BaseModel` command objects via `schema_from_input` in application
adapters when you do not want `BaseSchema`.

## SQLAlchemy → Strawberry mapping

Used by `resolve_*` after the optimizer runs:

```python
from strawberry_alchemy import map_sqlalchemy_to_type, map_sqlalchemy_list_to_types

item = await map_sqlalchemy_to_type(instance, info, PostType, selected_fields)
items = await map_sqlalchemy_list_to_types(instances, info, PostType, selected_fields)
```

Only requested fields are populated; nested selections drive nested mapping.

### Submodule helpers (`strawberry_alchemy.mapping`)

| Helper | Role |
|---|---|
| `map_sqlalchemy_to_type_with_path` | Mapping at a nested field path |
| `extract_fields_at_path` / `extract_nested_fields` | Selection-tree slicing |
| `get_graphql_type_from_sqlalchemy` | Resolve GraphQL type for an instance |
| `register_global_id_type` / `clear_global_id_type_registry` | Encode-side registry for non-`*_id` FK fields |
| `create_global_id_from_field` | Build a `GlobalID` from a registered field |

```python
from strawberry_alchemy.mapping import register_global_id_type

register_global_id_type("author", "User")
```

Register once at startup when foreign keys do not follow the `*_id` naming
convention the default encoder expects.

## Mutation flow (typical)

```python
session = await info.context.get_session()
schema = PostSchema.from_input(input, user_id=(await info.context.identity).id)
created = await PostRepository(session).create(schema=schema)
return created.to_type(PostType)
```

For deletes / updates that need permission checks first, see
[Permissions](permissions.md) (`prepare_mutation_resources`).
