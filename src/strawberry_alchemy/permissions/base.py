from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import strawberry

    from strawberry_alchemy.permissions.resource_bag import ResourceInstances
    from strawberry_alchemy.permissions.types import PermissionContextLike


class IsAuthenticated:
    message: str = "Authentication required."

    def has_permission(self, info: strawberry.Info, **_kwargs: Any) -> bool:
        ctx: PermissionContextLike = info.context
        return ctx.current_user is not None or getattr(ctx, "identity", None) is not None


class RolePermission:
    def __init__(self, *, role: str) -> None:
        self.role = role
        self.message = f"Role '{role}' is required."

    def has_permission(self, info: strawberry.Info, **_kwargs: Any) -> bool:
        ctx: PermissionContextLike = info.context
        user = ctx.current_user or getattr(ctx, "identity", None)
        if user is None:
            return False
        return getattr(user, "role", None) == self.role


class OwnerPermission:
    def __init__(
        self,
        *,
        owner_field: str = "user_id",
        resource_key: str | None = None,
    ) -> None:
        self.owner_field = owner_field
        self.resource_key = resource_key
        self.message = "You do not own this resource."

    def has_permission(
        self,
        info: strawberry.Info,
        resource_instances: ResourceInstances | None = None,
        **_kwargs: Any,
    ) -> bool:
        ctx: PermissionContextLike = info.context
        user = ctx.current_user or getattr(ctx, "identity", None)
        if user is None:
            return False

        if resource_instances is None:
            return False

        if self.resource_key is not None:
            instance = resource_instances.get(self.resource_key)
        else:
            all_instances = resource_instances.all()
            instance = next(iter(all_instances.values()), None) if all_instances else None

        if instance is None:
            return False

        resource_owner = getattr(instance, self.owner_field, None)
        return str(resource_owner) == str(user.id)


class ObjectAccessPermission:
    def __init__(
        self,
        *,
        access_field: str = "allowed_user_ids",
        resource_key: str | None = None,
    ) -> None:
        self.access_field = access_field
        self.resource_key = resource_key
        self.message = "You do not have access to this resource."

    def has_permission(
        self,
        info: strawberry.Info,
        resource_instances: ResourceInstances | None = None,
        **_kwargs: Any,
    ) -> bool:
        ctx: PermissionContextLike = info.context
        user = ctx.current_user or getattr(ctx, "identity", None)
        if user is None:
            return False
        if resource_instances is None:
            return False

        if self.resource_key is not None:
            instance = resource_instances.get(self.resource_key)
        else:
            all_instances = resource_instances.all()
            instance = next(iter(all_instances.values()), None) if all_instances else None

        if instance is None:
            return False

        access_list = getattr(instance, self.access_field, None)
        if access_list is None:
            return False

        user_id_str = str(user.id)
        for entry in access_list:
            entry_id = str(getattr(entry, "id", entry))
            if entry_id == user_id_str:
                return True

        return False
