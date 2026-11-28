"""Helpers for loading optimized nodes from mutation resolvers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from strawberry_alchemy.types.base_node import BaseNodeType

if TYPE_CHECKING:
    from uuid import UUID

    from strawberry.types import Info

    from strawberry_alchemy.filtering.access_control import AccessControlFilter


async def resolve_mutation_node[TNode: BaseNodeType](
    info: Info,
    strawberry_type: type[TNode],
    node_id: str | UUID,
    *,
    field: str | None = None,
    access_filter: type[AccessControlFilter] | AccessControlFilter | None = None,
) -> TNode | None:
    """Resolve a node for a mutation return selection without taking the DB lock.

    Use after a CQRS/use-case write when the mutation member already holds
    ``db_execution_lock`` (or otherwise serializes session access).

    ``field``
        GraphQL field name of the node under the mutation payload
        (e.g. ``\"company\"`` for ``Success { company { … } }``). Omit when the
        mutation returns the node type directly.
    """
    return await strawberry_type.resolve_node(
        str(node_id),
        info=info,
        access_filter=access_filter,
        target_field_path=field,
        acquire_lock=False,
    )


async def resolve_mutation_nodes[TNode: BaseNodeType](
    info: Info,
    strawberry_type: type[TNode],
    node_ids: list[str | UUID],
    *,
    field: str | None = None,
    access_filter: type[AccessControlFilter] | AccessControlFilter | None = None,
) -> list[TNode | None]:
    """Batch variant of :func:`resolve_mutation_node`."""
    return await strawberry_type.resolve_nodes(
        info=info,
        node_ids=[str(node_id) for node_id in node_ids],
        access_filter=access_filter,
        target_field_path=field,
        acquire_lock=False,
    )


__all__ = ("resolve_mutation_node", "resolve_mutation_nodes")
