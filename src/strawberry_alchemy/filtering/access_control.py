from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, get_args, get_origin
from uuid import UUID

from strawberry import UNSET
from strawberry.extensions import FieldExtension

if TYPE_CHECKING:
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


def _unwrap_strawberry_type(type_hint: Any) -> Any:
    """Unwrap Strawberry Optional/List/Lazy/Annotated wrappers to the node class."""
    if type_hint is None:
        return None

    # strawberry.types.base.StrawberryOptional / StrawberryList
    of_type = getattr(type_hint, "of_type", None)
    if of_type is not None:
        return _unwrap_strawberry_type(of_type)

    # LazyType — resolve to the concrete class
    if hasattr(type_hint, "resolve_type") and callable(type_hint.resolve_type):
        try:
            return _unwrap_strawberry_type(type_hint.resolve_type())
        except Exception:  # noqa: BLE001 — fall through to other unwraps
            pass

    origin = get_origin(type_hint)
    if origin is not None:
        args = [a for a in get_args(type_hint) if a is not type(None)]
        if args:
            return _unwrap_strawberry_type(args[0])

    # StrawberryType / type wrapper with .origin
    wrapped = getattr(type_hint, "origin", None) or getattr(type_hint, "__origin__", None)
    if wrapped is not None and wrapped is not type_hint:
        return _unwrap_strawberry_type(wrapped)

    return type_hint


def _related_node_type(info: Info) -> Any | None:
    return_type = getattr(info, "return_type", None)
    if return_type is None:
        return None
    unwrapped = _unwrap_strawberry_type(return_type)
    if unwrapped is not None and hasattr(unwrapped, "resolve_nodes"):
        return unwrapped
    return None


class RelationAccessFilter(FieldExtension):
    """Per-relationship ACL override for nested ``selectinload`` (edge-local).

    Attach to a ``strawberry.UNSET`` relationship field when that edge must use a
    different ``AccessControlFilter`` than the related type's ClassVar — e.g.
    reporting-line manager vs SEC-020 people scope on the same Employment model.

    The optimizer reads this extension when building ``selectinload`` for the
    field and applies the filter's ``whereclause`` via ``.and_(...)``. It does
    **not** re-register the override on the model-keyed ACL map (sibling edges
    keep the ClassVar filter).

    When ``foreign_key`` is set, the extension also acts as a resolve fallback for
    mutation ``to_type()`` paths: if the attribute is missing/None but the FK is
    present, it loads the related node via ``resolve_nodes`` with this edge's
    ACL (same as a DataLoader would). Optimizer-prefetched values are returned
    as-is (no second query).
    """

    def __init__(
        self,
        access_filter: type[AccessControlFilter] | AccessControlFilter,
        *,
        foreign_key: str | None = None,
    ) -> None:
        self.access_filter = access_filter
        self.foreign_key = foreign_key

    # Async-only: do not override ``resolve`` so Strawberry promotes the field
    # to async and FK fallback can call ``resolve_nodes``.

    async def resolve_async(self, next_: Any, source: Any, info: Info, **kwargs: Any) -> Any:
        value = next_(source, info, **kwargs)
        if inspect.isawaitable(value):
            value = await value
        if value is not None and value is not UNSET:
            return value
        if self.foreign_key is None:
            return None if value is UNSET else value

        fk = getattr(source, self.foreign_key, None)
        if fk is None or fk is UNSET:
            return None
        if not isinstance(fk, UUID):
            try:
                fk = UUID(str(fk))
            except (TypeError, ValueError):
                return None

        related_type = _related_node_type(info)
        if related_type is None:
            return None

        nodes = await related_type.resolve_nodes(
            info=info,
            node_ids=[str(fk)],
            access_filter=self.access_filter,
        )
        return nodes[0] if nodes else None
