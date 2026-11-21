from typing import Any

from strawberry.extensions import FieldExtension
from strawberry.types import Info


class AccessControlMeta(type):
    def __init__(
        cls,
        name: str,
        bases: tuple[type, ...],
        dct: dict[str, Any],
    ) -> None:
        # NOTE: We can remove this in the future and come up with better solution. This is opinionated convention.
        if name != "AccessControlFilter" and not name.endswith("AccessFilter"):
            raise TypeError(f"Subclass {name} must end with 'AccessFilter'")
        super().__init__(name, bases, dct)


class AccessControlFilter(metaclass=AccessControlMeta):
    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        raise NotImplementedError("Subclasses must implement the apply_filter method")


class RelationAccessFilter(FieldExtension):
    """Per-relationship ACL override for nested ``selectinload`` (edge-local).

    Attach to a ``strawberry.UNSET`` relationship field when that edge must use a
    different ``AccessControlFilter`` than the related type's ClassVar — e.g.
    reporting-line manager vs SEC-020 people scope on the same Employment model.

    The optimizer reads this extension when building ``selectinload`` for the
    field and applies the filter's ``whereclause`` via ``.and_(...)``. It does
    **not** re-register the override on the model-keyed ACL map (sibling edges
    keep the ClassVar filter).
    """

    def __init__(
        self,
        access_filter: type[AccessControlFilter] | AccessControlFilter,
    ) -> None:
        self.access_filter = access_filter

    def resolve(self, next_: Any, source: Any, info: Info, **kwargs: Any) -> Any:
        return next_(source, info, **kwargs)

    async def resolve_async(self, next_: Any, source: Any, info: Info, **kwargs: Any) -> Any:
        return await next_(source, info, **kwargs)
