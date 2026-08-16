# Permissions

The `strawberry_alchemy.permissions` module provides Strawberry-compatible
permission classes (plain classes with `has_permission`) and helpers for checking
permissions against *loaded resource instances* inside resolvers.

## Built-in permission classes

Use these in `@strawberry.field(permission_classes=[...])` or call their
`has_permission` directly. All of them resolve the user from
`info.context.current_user` or `info.context.identity`.

### `IsAuthenticated`

Passes when a user is present.

```python
@strawberry.field(permission_classes=[IsAuthenticated])
async def posts(self, info: Info) -> ListResult[PostType]:
    return await PostType.resolve_list(info=info)
```

### `RolePermission`

Passes when the user's `role` attribute equals the configured role.

```python
@strawberry.field(permission_classes=[IsAuthenticated, RolePermission(role="admin")])
async def admin_stats(self, info: Info) -> Stats:
    ...
```

The `message` attribute (`"Role 'admin' is required."`) is raised as a
`PermissionError` when a check fails via `fetch_and_check_permissions`.

### `OwnerPermission` and `ObjectAccessPermission`

These check a *resource instance* rather than just the user. They accept
`resource_instances: ResourceInstances` as a kwarg (normally built with
`map_ids_to_models`, see below) plus an `owner_field` / `access_field` and optional
`resource_key` to select which instance to check.

```python
from strawberry_alchemy.permissions import OwnerPermission, ObjectAccessPermission

OwnerPermission(owner_field="user_id")                    # instance.user_id == user.id
OwnerPermission(owner_field="user_id", resource_key="post")

ObjectAccessPermission(access_field="allowed_user_ids")   # user.id in instance.allowed_user_ids
```

Example mutation using the manual check pattern:

```python
@strawberry.mutation
async def delete_post(self, info: Info, input: DeletePostInput) -> bool:
    session = await info.context.get_session()
    ids = extract_global_ids_from_info({"post_id": input.id})
    bag = await map_ids_to_models(
        ids,
        loaders={"post_id": lambda post_id: PostRepository(session).get_by_id(post_id)},
    )
    await fetch_and_check_permissions(info, [IsAuthenticated(), OwnerPermission(owner_field="user_id", resource_key="post_id")], bag)

    await PostRepository(session, deletion_handler=PostDeletionHandler()).delete(id=uuid.UUID(input.id.node_id))
    return True
```

## Resource-instance helpers

`ResourceInstances` is a simple keyed bag for the instances a mutation operates on:

```python
from strawberry_alchemy.permissions import ResourceInstances

bag = ResourceInstances()
bag.add("post", post_schema)          # single instance
bag.add_list("comments", [c1, c2])    # list of instances
bag.get("post")                       # -> instance | None
bag.get_id("post")                    # -> instance.id | None
```

`extract_global_ids_from_info` decodes Relay `GlobalID`s from an input dict:

```python
from strawberry_alchemy.permissions import extract_global_ids_from_info

ids = extract_global_ids_from_info(
    {"post_id": input.id, "user_id": input.user_id},
    id_fields=["post_id", "user_id"],   # defaults to keys ending in "_id"
)
# ids == {"post_id": UUID(...), "user_id": UUID(...)}
```

`map_ids_to_models` runs loader callables per id and fills a `ResourceInstances` bag:

```python
from strawberry_alchemy.permissions import map_ids_to_models

bag = await map_ids_to_models(
    ids,
    loaders={
        "post_id": lambda value: PostRepository(session).get_by_id(value),
    },
)
```

`fetch_and_check_permissions` runs a list of permission objects (sync or async
`has_permission`) and raises `PermissionError` with the permission's `message` on the
first denial:

```python
from strawberry_alchemy.permissions import fetch_and_check_permissions

await fetch_and_check_permissions(info, [IsAuthenticated(), RolePermission(role="admin")], bag)
```

## Writing your own permissions

Any class with `has_permission(self, info, **kwargs) -> bool` (sync or async) and an
optional `message` attribute works — with Strawberry's `permission_classes` and with
`fetch_and_check_permissions`.

```python
class IsAdmin:
    message = "Administrator access required."

    def has_permission(self, info, **kwargs) -> bool:
        user = info.context.current_user or getattr(info.context, "identity", None)
        return user is not None and getattr(user, "role", None) == "admin"
```

## `BasePermissionResolver`

`BasePermissionResolver` is an ABC for services that map an operation name (plus
input data) to a list of permission objects — e.g. per-mutation permission
resolution stored in a single place:

```python
from strawberry_alchemy.permissions import BasePermissionResolver


class MyPermissionResolver(BasePermissionResolver):
    def resolve(self, operation: str, *, data: dict | None = None, **kwargs):
        if operation == "delete_post":
            return [IsAuthenticated(), OwnerPermission(owner_field="user_id")]
        return [IsAuthenticated()]
```

## Protocols

Typing-only protocols are exported for context/user contracts:
`HasId`, `IdentityLike`, `UserLike` (id + role), `PermissionContextLike`
(current_user / identity), and `ModelRegistryLike`. Context objects may satisfy these
protocols structurally — no inheritance required.

## Which user is used?

Permission classes read `info.context.current_user` first, then
`info.context.identity`. Access filters inside the optimizer use `identity` then
`user`. All four forms work: plain attribute, `@property`, or awaitable (the value is
awaited when necessary).
