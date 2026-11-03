"""Helpers that codify GlobalID → load → permission check for mutations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from uuid import UUID

from strawberry.types import Info

from strawberry_alchemy.permissions.checker import fetch_and_check_permissions
from strawberry_alchemy.permissions.input_parser import extract_global_ids_from_info, map_ids_to_models
from strawberry_alchemy.permissions.resource_bag import ResourceInstances


async def prepare_mutation_resources(
    info: Info,
    input_data: Mapping[str, Any],
    *,
    loaders: Mapping[str, Callable[[UUID], Awaitable[Any]]],
    permissions: Sequence[Any],
    id_fields: list[str] | None = None,
) -> ResourceInstances:
    """Decode GlobalIDs, load resources, and run permission checks.

    Typical mutation body::

        bag = await prepare_mutation_resources(
            info,
            {"post_id": input.id},
            loaders={"post_id": lambda v: PostRepository(session).get_by_id(v)},
            permissions=[IsAuthenticated(), OwnerPermission(owner_field="user_id", resource_key="post_id")],
        )
        post = bag.get("post_id")
    """
    ids = extract_global_ids_from_info(dict(input_data), id_fields=id_fields)
    bag = await map_ids_to_models(ids, loaders=dict(loaders))
    await fetch_and_check_permissions(info, list(permissions), bag)
    return bag
