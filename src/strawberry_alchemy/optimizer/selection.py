"""Typed selection-tree helpers for Relay wrappers and field paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeGuard, cast

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence


@dataclass(frozen=True, slots=True)
class FieldPath:
    """Immutable path of GraphQL / model field names (no dotted strings)."""

    parts: tuple[str, ...]

    def __init__(self, parts: Sequence[str] | str) -> None:
        normalized = tuple(p for p in parts.split(".") if p) if isinstance(parts, str) else tuple(parts)
        object.__setattr__(self, "parts", normalized)

    def __iter__(self) -> Iterator[str]:
        return iter(self.parts)

    def __len__(self) -> int:
        return len(self.parts)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldPath):
            return self.parts == other.parts
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.parts)

    def join(self, sep: str = ".") -> str:
        return sep.join(self.parts)

    def child(self, name: str) -> FieldPath:
        return FieldPath((*self.parts, name))

    @classmethod
    def from_dotted(cls, path: str) -> FieldPath:
        return cls(path)


@dataclass(frozen=True, slots=True)
class FieldSelection:
    """A selected object/field with nested children (domain relationships)."""

    name: str
    children: dict[str, FieldSelection | LeafSelection | RelayConnectionSelection] = field(default_factory=dict)
    leaf: bool = False


@dataclass(frozen=True, slots=True)
class LeafSelection:
    """A scalar / leaf field request."""

    name: str = ""


@dataclass(frozen=True, slots=True)
class RelayConnectionSelection:
    """Relay connection wrapper: edges { node { … } } plus page metadata."""

    node_fields: dict[str, Any]
    page_info: dict[str, Any] = field(default_factory=dict)
    total_count: bool = False


def _is_relay_edges(value: Any) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict) and isinstance(value.get("node"), dict)


def parse_selection_tree(
    selected_fields: dict[str, Any],
) -> FieldSelection | RelayConnectionSelection:
    """
    Classify a processed selection dict as a Relay connection or a domain field tree.

    Relay connections are detected when the only meaningful keys are Relay wrappers
    and ``edges`` contains a ``node`` selection. A domain relationship literally
    named ``edges`` (no ``node`` child) stays a normal ``FieldSelection``.
    """
    relay_wrapper_keys = {"edges", "cursor", "pageInfo", "totalCount", "__typename", "items"}

    if selected_fields and set(selected_fields.keys()).issubset(relay_wrapper_keys):
        edges = selected_fields.get("edges")
        if _is_relay_edges(edges):
            node = cast("dict[str, Any]", edges["node"])
            return RelayConnectionSelection(
                node_fields=dict(node),
                page_info=dict(selected_fields["pageInfo"])
                if isinstance(selected_fields.get("pageInfo"), dict)
                else {},
                total_count=bool(selected_fields.get("totalCount")),
            )
        items = selected_fields.get("items")
        if isinstance(items, dict):
            return FieldSelection(name="", children=_parse_children(items))

    return FieldSelection(name="", children=_parse_children(selected_fields))


def _parse_children(
    selected_fields: dict[str, Any],
) -> dict[str, FieldSelection | LeafSelection | RelayConnectionSelection]:
    children: dict[str, FieldSelection | LeafSelection | RelayConnectionSelection] = {}
    for key, value in selected_fields.items():
        if key in {"__typename", "cursor", "pageInfo", "totalCount"}:
            continue
        if key == "edges" and _is_relay_edges(value):
            children[key] = RelayConnectionSelection(node_fields=dict(value["node"]))
        elif isinstance(value, dict):
            children[key] = FieldSelection(name=key, children=_parse_children(value))
        elif value is True:
            children[key] = LeafSelection(name=key)
        else:
            children[key] = LeafSelection(name=key)
    return children


def selection_to_model_fields(tree: FieldSelection | RelayConnectionSelection) -> dict[str, Any]:
    """Convert a typed tree back to the dict shape QueryOptimizer historically used."""
    if isinstance(tree, RelayConnectionSelection):
        return dict(tree.node_fields)

    result: dict[str, Any] = {}
    for name, child in tree.children.items():
        if isinstance(child, LeafSelection):
            result[name] = True
        elif isinstance(child, RelayConnectionSelection):
            result[name] = dict(child.node_fields)
        elif isinstance(child, FieldSelection):
            nested = selection_to_model_fields(child)
            result[name] = nested if nested else True
    return result


def extract_at_path(selected_fields: dict[str, Any], path: FieldPath | Sequence[str] | str) -> dict[str, Any]:
    field_path = path if isinstance(path, FieldPath) else FieldPath(path)
    current: Any = selected_fields
    for part in field_path:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return {}
    return current if isinstance(current, dict) else {}


def source_path_to_dependency_tree(path: FieldPath | Sequence[str] | str) -> dict[str, Any]:
    field_path = path if isinstance(path, FieldPath) else FieldPath(path)
    parts = field_path.parts
    if not parts:
        return {}

    tree: dict[str, Any] = {parts[-1]: True}
    for part in reversed(parts[:-1]):
        tree = {part: tree}
    return tree


def iter_leaf_names(tree: FieldSelection | RelayConnectionSelection) -> Iterable[str]:
    if isinstance(tree, RelayConnectionSelection):
        yield from tree.node_fields.keys()
        return
    for name, child in tree.children.items():
        if isinstance(child, LeafSelection):
            yield name
        elif isinstance(child, FieldSelection):
            yield from iter_leaf_names(child)
        elif isinstance(child, RelayConnectionSelection):
            yield from child.node_fields.keys()
