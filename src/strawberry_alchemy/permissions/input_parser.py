from typing import Any
from uuid import UUID

from strawberry.relay import from_base64

from strawberry_alchemy.permissions.resource_bag import (
    ResourceInstances,
)


def _decode_global_id(raw: Any) -> UUID | str | None:
    if raw is None:
        return None
    if hasattr(raw, "node_id"):
        try:
            return UUID(str(raw.node_id))
        except ValueError:
            return str(raw.node_id)
    if isinstance(raw, str) and ":" in raw:
        try:
            _, node_id = from_base64(raw)
            return UUID(node_id)
        except (ValueError, TypeError):
            return raw
    return raw


def extract_global_ids_from_info(
    data: dict[str, Any],
    id_fields: list[str] | None = None,
) -> dict[str, UUID | str | None]:
    result: dict[str, UUID | str | None] = {}
    if id_fields is None:
        id_fields = [k for k in data if k.endswith("_id")]
    for key in id_fields:
        raw = data.get(key)
        result[key] = _decode_global_id(raw)
    return result


async def map_ids_to_models(
    ids: dict[str, UUID | str | None],
    loaders: dict[str, Any],
    bag: ResourceInstances | None = None,
) -> ResourceInstances:
    if bag is None:
        bag = ResourceInstances()
    for field_name, id_value in ids.items():
        if id_value is None:
            continue
        loader = loaders.get(field_name)
        if loader is None:
            continue
        instance = await loader(id_value)
        if instance is not None:
            bag.add(field_name, instance)
    return bag
