"""Per-type / per-field caps for nested to-many selectin loads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

from strawberry_alchemy.utils import camel_to_snake

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_MAX_ITEMS = 100


def _validate_max_items(value: int | None, label: str) -> None:
    if value is not None and value <= 0:
        raise ValueError(f"{label} must be None (unlimited) or a positive int, got {value!r}")


@dataclass(frozen=True, slots=True)
class NodeConfig:
    """Optimizer knobs for a ``BaseNodeType`` subclass.

    ``max_items`` caps each to-many relationship on this type (per parent row).
    ``fields`` overrides that default per relationship attribute name.
    ``None`` means unlimited.

    Attach via ``node_config: ClassVar[NodeConfig] = NodeConfig(...)`` on the
    type (or assign ``BaseNodeType.node_config = …`` app-wide). Named
    ``node_config`` (not ``config``) so domain GraphQL / ORM fields may use
    ``config`` for payload data — same idea as Pydantic's ``model_config``.
    """

    max_items: int | None = DEFAULT_MAX_ITEMS
    fields: Mapping[str, int | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_max_items(self.max_items, "max_items")
        for name, value in self.fields.items():
            _validate_max_items(value, f"fields[{name!r}]")


def _max_items_extension_for_field(strawberry_type: type[Any], field_name: str) -> int | None | object:
    """Return MaxItems.max_items if the field has the extension, else a sentinel."""
    from strawberry_alchemy.filtering.access_control import MaxItems

    definition = getattr(strawberry_type, "__strawberry_definition__", None)
    if definition is None:
        return _MISSING

    for field_def in definition.fields:
        snake = camel_to_snake(field_def.name)
        if field_def.name != field_name and snake != field_name:
            continue
        for ext in field_def.extensions or ():
            if isinstance(ext, MaxItems):
                return ext.max_items
        break
    return _MISSING


_MISSING = object()


def lookup_node_config(strawberry_type: type[Any]) -> NodeConfig | None:
    """Return ``strawberry_type.node_config`` when it is a ``NodeConfig``."""
    value = getattr(strawberry_type, "node_config", None)
    return value if isinstance(value, NodeConfig) else None


def resolve_max_items(
    strawberry_type: type[Any] | None,
    field_name: str,
    *,
    prefetch_max_items: int | None | object = _MISSING,
) -> int | None:
    """Resolve effective nested-list cap.

    Order (highest wins): ``PrefetchRelated.max_items`` (when passed) →
    ``MaxItems`` field extension → ``NodeConfig.fields[field]`` →
    ``NodeConfig.max_items`` → library default ``100``.
    """
    if prefetch_max_items is not _MISSING:
        value = cast("int | None", prefetch_max_items)
        _validate_max_items(value, "PrefetchRelated.max_items")
        return value

    if strawberry_type is not None:
        ext_value = _max_items_extension_for_field(strawberry_type, field_name)
        if ext_value is not _MISSING:
            return cast("int | None", ext_value)

        node_config = lookup_node_config(strawberry_type)
        if node_config is not None:
            if field_name in node_config.fields:
                return node_config.fields[field_name]
            snake = camel_to_snake(field_name)
            if isinstance(snake, str) and snake in node_config.fields:
                return node_config.fields[snake]
            return node_config.max_items

    return DEFAULT_MAX_ITEMS
