from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

PREFETCH_ATTR = "__optimizer_prefetch__"


@dataclass(frozen=True)
class PrefetchRelated:
    relationship: str
    fields: list[str] | dict[str, Any] | None = None
    filter_current_user: bool = False
    filter: Callable[[type], Any] | None = None

    @property
    def has_custom_loading(self) -> bool:
        return self.filter_current_user or self.filter is not None


@dataclass(frozen=True)
class AnnotateExists:
    relationship: str
    filter_current_user: bool = False
    to_attr: str = ""
    filter: Callable[[type], Any] | None = None

    @property
    def resolved_attr(self) -> str:
        return self.to_attr or f"_{self.relationship}_exists"

    @property
    def debug_name(self) -> str:
        return self.relationship


@dataclass(frozen=True)
class AnnotateAnyExists:
    relationships: list[str]
    filter_current_user: bool = False
    to_attr: str = ""
    filter: Callable[[type], Any] | None = None

    @property
    def resolved_attr(self) -> str:
        if self.to_attr:
            return self.to_attr
        joined_relationships = "_".join(self.relationships)
        return f"_{joined_relationships}_any_exists"

    @property
    def debug_name(self) -> str:
        return ",".join(self.relationships)


@dataclass(frozen=True)
class AnnotateCount:
    relationship: str
    filter_current_user: bool = False
    to_attr: str = ""
    filter: Callable[[type], Any] | None = None

    @property
    def resolved_attr(self) -> str:
        return self.to_attr or f"_{self.relationship}_count"

    @property
    def debug_name(self) -> str:
        return self.relationship


@dataclass(frozen=True)
class AnnotateCustom:
    relationship: str
    expression: Callable[..., Any] = None  # type: ignore[assignment]
    to_attr: str = ""
    mapper: Callable[[Any], Any] | None = None
    filter_current_user: bool = False

    @property
    def resolved_attr(self) -> str:
        return self.to_attr or f"_{self.relationship}_custom"

    @property
    def debug_name(self) -> str:
        return self.relationship


@dataclass(frozen=True)
class AnnotateAncestry:
    relationship: str
    parent_field: str = "parent_id"
    id_field: str = "id"
    to_attr: str = ""
    include_self: bool = True
    root_first: bool = True
    value_mode: str = "ids"
    cte_name: str = "ancestry"

    @property
    def resolved_attr(self) -> str:
        return self.to_attr or f"_{self.relationship}_ancestry"

    @property
    def debug_name(self) -> str:
        return self.relationship


OptimizerHint = (
    str | PrefetchRelated | AnnotateExists | AnnotateAnyExists | AnnotateCount | AnnotateCustom | AnnotateAncestry
)


@dataclass
class ResolvedDependencies:
    augmented_fields: dict[str, Any]
    filtered_prefetches: list[PrefetchRelated] = field(default_factory=list)
    annotations: list[AnnotateExists | AnnotateAnyExists | AnnotateCount | AnnotateCustom | AnnotateAncestry] = field(
        default_factory=list
    )

    @property
    def needs_current_user(self) -> bool:
        return any(p.filter_current_user for p in self.filtered_prefetches) or any(
            getattr(a, "filter_current_user", False) for a in self.annotations
        )


def normalize_dependency_fields(fields: list[str] | dict[str, Any]) -> dict[str, Any]:
    if isinstance(fields, list):
        return {field_name: True for field_name in fields}

    normalized: dict[str, Any] = {}
    for key, value in fields.items():
        if value is True:
            normalized[key] = True
        elif isinstance(value, dict):
            normalized[key] = normalize_dependency_fields(value)
        else:
            normalized[key] = bool(value)
    return normalized


def merge_dependency_trees(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)

    for key, value in extra.items():
        existing = merged.get(key)

        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = merge_dependency_trees(existing, value)
        elif isinstance(existing, dict):
            merged[key] = existing
        elif isinstance(value, dict):
            merged[key] = value
        else:
            merged[key] = True

    return merged


def build_recursive_dependency_tree(
    relationship: str,
    *,
    fields: list[str] | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    node_fields: dict[str, Any] = {field_name: True for field_name in (fields or ["id"])}

    if depth <= 0:
        return node_fields

    node_fields[relationship] = build_recursive_dependency_tree(
        relationship,
        fields=fields,
        depth=depth - 1,
    )
    return node_fields


def source_path_to_dependency_tree(source_path: str) -> dict[str, Any]:
    parts = [part for part in source_path.split(".") if part]
    if not parts:
        return {}

    tree: dict[str, Any] = {parts[-1]: True}
    for part in reversed(parts[:-1]):
        tree = {part: tree}
    return tree


def optimize_field(
    *args: str
    | PrefetchRelated
    | AnnotateExists
    | AnnotateAnyExists
    | AnnotateCount
    | AnnotateCustom
    | AnnotateAncestry,
    **kwargs: list[str] | dict[str, Any],
) -> Callable:
    def decorator(func: Callable) -> Callable:
        hints: list[OptimizerHint] = []
        for arg in args:
            if isinstance(arg, str):
                hints.append(PrefetchRelated(relationship=arg))
            elif isinstance(
                arg,
                (PrefetchRelated, AnnotateExists, AnnotateAnyExists, AnnotateCount, AnnotateCustom, AnnotateAncestry),
            ):
                hints.append(arg)
            else:
                raise TypeError(
                    f"Invalid argument type for optimize_field: {type(arg)}. "
                    f"Expected str, PrefetchRelated, AnnotateExists, AnnotateAnyExists, "
                    f"AnnotateCount, AnnotateCustom, or AnnotateAncestry."
                )
        for rel, fields in kwargs.items():
            hints.append(PrefetchRelated(relationship=rel, fields=fields))

        setattr(func, PREFETCH_ATTR, hints)
        return func

    return decorator


def get_prefetch_map(strawberry_type: type) -> dict[str, list[OptimizerHint]]:
    prefetch_map: dict[str, list[OptimizerHint]] = {}

    definition = getattr(strawberry_type, "__strawberry_definition__", None)
    if not definition:
        return prefetch_map

    for field_def in definition.fields:
        resolver = getattr(field_def, "base_resolver", None)
        if resolver is None:
            continue

        func = getattr(resolver, "wrapped_func", None)
        if func is None:
            continue

        hints = getattr(func, PREFETCH_ATTR, None)
        if hints:
            prefetch_map[field_def.name] = hints

    return prefetch_map
