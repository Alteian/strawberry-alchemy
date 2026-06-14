from typing import Any

import strawberry

from strawberry_alchemy.permissions.resource_bag import ResourceInstances


async def fetch_and_check_permissions(
    info: strawberry.Info,
    permissions: list[Any],
    resource_instances: ResourceInstances | None = None,
) -> None:
    kwargs: dict[str, Any] = {}
    if resource_instances is not None:
        kwargs["resource_instances"] = resource_instances

    for perm in permissions:
        allowed: bool
        if hasattr(perm, "has_permission"):
            result = perm.has_permission(info, **kwargs)
            if hasattr(result, "__await__"):
                allowed = await result
            else:
                allowed = result
        else:
            allowed = False

        if not allowed:
            message = getattr(perm, "message", "Permission denied.")
            raise PermissionError(message)
