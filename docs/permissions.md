# Permissions

The `strawberry_alchemy.permissions` module provides Strawberry-compatible
permission check classes (plain objects with `has_permission`) and helpers for
loading mutation targets into a resource bag before checking them.

!!! note "What production apps typically do"
    Many codebases keep **field-level GraphQL auth** on Strawberry's own
    `BasePermission` (or an app equivalent) and still use
    `prepare_mutation_resources` / the resource bag for **mutation-time**
    ownership checks. Using the library permission classes is optional.

## Permission classes

All expose `has_permission(self, info, **kwargs) -> bool` and a `message` on
deny. Helpers raise `PermissionError` when a check fails.

### `IsAuthenticated`

Requires a non-null current user on the context (`identity` / `current_user` /
`user`, depending on what your context provides).

### `RolePermission(role=...)`

Requires `user.role == role` (see `UserLike` protocol: `id`, `role`).

### `OwnerPermission(owner_field="user_id", resource_key=...)`

Compares the current user's id to `getattr(resource, owner_field)`. Pass
`resource_key` when using a `ResourceInstances` bag.

### `ObjectAccessPermission(access_field="allowed_user_ids", resource_key=...)`

Allows access when the current user id is in a collection field on the resource.

## Resource bag and mutation helpers

```python
from strawberry_alchemy import (
    IsAuthenticated,
    OwnerPermission,
    ResourceInstances,
    extract_global_ids_from_info,
    fetch_and_check_permissions,
    map_ids_to_models,
    prepare_mutation_resources,
)
```

### `prepare_mutation_resources`

One-shot helper for mutation resolvers:

1. Decode GlobalIDs from `input_data`
2. Load models via `loaders`
3. Run `permissions` against the bag
4. Return `ResourceInstances`

```python
await prepare_mutation_resources(
    info,
    {"post_id": input.id},
    loaders={"post_id": lambda value: repo.get_by_id(value)},
    permissions=[
        IsAuthenticated(),
        OwnerPermission(owner_field="user_id", resource_key="post_id"),
    ],
)
```

Optional `id_fields=` overrides which keys are treated as IDs (default: keys
ending with `_id`).

### Returning optimized nodes after a write

CQRS-style mutations often call a use case, then need a GraphQL node that
respects the **payload** selection (`AnnotateCount`, selected columns, …).
Bare `to_type()` skips the optimizer; default `resolve_node` takes
`db_execution_lock` again and deadlocks when the mutation member already holds
it.

Use `resolve_mutation_node` (or `resolve_node(..., acquire_lock=False,
target_field_path=...)`):

```python
from strawberry_alchemy import resolve_mutation_node, schema_from_input

@strawberry.mutation
async def update_company(self, info: Info, input: UpdateInput) -> Payload:
    command = schema_from_input(UpdateSchema, input)
    company = await use_case.execute(command)  # application write
    node = await resolve_mutation_node(
        info,
        CompanyType,
        company.id,
        field="company",  # Success { company { id employmentCount … } }
    )
    return Success(company=node, message="ok")
```

- Omit `field` when the mutation returns the node type directly (`-> PostType`).
- Call resolve **after** the write unit of work commits (so the request session
  sees the new row state).
- Tenancy / RLS bind stays application-side when annotations need it.

### Lower-level pieces

| Helper | Role |
|---|---|
| `extract_global_ids_from_info(data, id_fields=None)` | `GlobalID` / strings → UUIDs |
| `map_ids_to_models(ids, loaders, bag=None)` | Fill a `ResourceInstances` bag |
| `fetch_and_check_permissions(info, permissions, resource_instances=None)` | Run checks; raise on deny |
| `ResourceInstances` | `add` / `add_list` / `get` / `get_id` / `all` |

## `BasePermissionResolver`

ABC for apps that map an operation name (+ data) to a list of permission
objects:

```python
class PostPermissionResolver(BasePermissionResolver):
    def resolve(self, operation: str, *, data=None, **kwargs):
        if operation == "delete":
            return [IsAuthenticated(), OwnerPermission(resource_key="post_id")]
        return [IsAuthenticated()]
```

## Protocols

| Protocol | Shape |
|---|---|
| `HasId` | `.id` |
| `IdentityLike` | `.id` |
| `UserLike` | `.id`, `.role` |
| `PermissionContextLike` | `.current_user`, `.identity` |
| `ModelRegistryLike` | `.get_model(label)` |

These exist so permission helpers stay typed without depending on your User
model class.
