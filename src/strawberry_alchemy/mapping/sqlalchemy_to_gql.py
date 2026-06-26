import asyncio
from typing import Any, TypeVar

import strawberry
from sqlalchemy.inspection import inspect
from strawberry.relay import GlobalID

from strawberry_alchemy.mapping.output_normalization import (
    get_type_init_params,
    prepare_output_constructor_data,
)

T = TypeVar("T")
UNSET = strawberry.UNSET


def _requested_leaf_fields(selected_fields: dict[str, bool | dict]) -> set[str]:
    return {name for name, selected in selected_fields.items() if selected is True}


def _ensure_requested_model_scalars_mapped(
    *,
    type_data: dict[str, Any],
    requested_fields: set[str],
    insp: Any,
) -> None:
    for field_name in requested_fields:
        if field_name in type_data:
            continue
        if field_name not in insp.attrs:
            continue
        if field_name in insp.mapper.relationships:
            continue
        type_data[field_name] = None


def create_global_id_from_field(field_name: str, value: Any) -> GlobalID:
    base_name = field_name[:-3]
    type_name = f"{base_name.replace('_', ' ').title().replace(' ', '')}Type"
    return GlobalID(type_name=type_name, node_id=str(value))


async def map_sqlalchemy_to_type[T](
    instance: Any,
    info: strawberry.Info,
    target_type: type[T],
    selected_fields: dict[str, bool | dict],
) -> T | None:
    if instance is None:
        return None

    insp = inspect(instance)
    type_data: dict[str, Any] = {}
    type_annotations = getattr(target_type, "__annotations__", {})

    fields_to_process = dict(selected_fields)
    if "id" not in fields_to_process:
        fields_to_process["id"] = True
    requested_leaf_fields = _requested_leaf_fields(fields_to_process)

    for field_name, is_selected in fields_to_process.items():
        if is_selected is not True and not isinstance(is_selected, dict):
            continue

        if field_name not in insp.attrs:
            continue

        if field_name in insp.unloaded:
            continue

        value = getattr(instance, field_name)

        if value is UNSET:
            continue

        if field_name in insp.mapper.relationships:
            nested_fields = (
                selected_fields.get(field_name, {}) if isinstance(selected_fields.get(field_name), dict) else {}
            )

            if isinstance(value, list):
                if value:
                    relationship_type = get_graphql_type_from_sqlalchemy(info, value[0])
                    if relationship_type:
                        mapped_items = await asyncio.gather(
                            *(
                                map_sqlalchemy_to_type(item, info, relationship_type, nested_fields)
                                for item in value
                                if item is not None and item is not UNSET
                            )
                        )
                        type_data[field_name] = [item for item in mapped_items if item is not None]
                    else:
                        type_data[field_name] = []
                else:
                    type_data[field_name] = []

            elif value is None:
                type_data[field_name] = None
            elif value is not UNSET:
                relationship_type = get_graphql_type_from_sqlalchemy(info, value)
                if relationship_type:
                    mapped_value = await map_sqlalchemy_to_type(value, info, relationship_type, nested_fields)
                    if mapped_value is not None:
                        type_data[field_name] = mapped_value
                    else:
                        type_data[field_name] = None
                else:
                    type_data[field_name] = None
        else:
            if field_name.endswith("_id") and value is not None and value is not UNSET:
                annotation = type_annotations.get(field_name, "")
                annotation_str = str(annotation)

                if "GlobalID" in annotation_str:
                    type_data[field_name] = create_global_id_from_field(field_name, value)
                else:
                    type_data[field_name] = value
            elif value is not None and value is not UNSET:
                annotation = type_annotations.get(field_name)
                if (
                    isinstance(value, dict)
                    and annotation is not None
                    and hasattr(annotation, "__strawberry_definition__")
                ):
                    try:
                        type_data[field_name] = annotation(**value)
                    except Exception:
                        type_data[field_name] = value
                else:
                    type_data[field_name] = value
            elif value is None:
                type_data[field_name] = None

    _ensure_requested_model_scalars_mapped(
        type_data=type_data,
        requested_fields=requested_leaf_fields,
        insp=insp,
    )

    init_params = get_type_init_params(target_type)
    type_data = prepare_output_constructor_data(
        target_type,
        type_data,
        requested_fields=requested_leaf_fields,
        init_params=init_params,
    )

    try:
        type_instance = target_type(**type_data)
    except TypeError:
        return None

    optimizer_annotations = getattr(instance, "_optimizer_annotations", None)
    if optimizer_annotations:
        for attr_name, attr_value in optimizer_annotations.items():
            object.__setattr__(type_instance, attr_name, attr_value)

    return type_instance


def get_graphql_type_from_sqlalchemy(info: strawberry.Info, instance: Any) -> type[Any] | None:
    type_name = type(instance).__name__

    possible_names = [f"{type_name}Type", type_name, f"{type_name.lower()}Type"]

    for name in possible_names:
        type_obj = info.schema.get_type_by_name(name)
        if type_obj is not None and hasattr(type_obj, "origin"):
            return type_obj.origin

    return None


def extract_fields_at_path(selected_fields: dict, path: str) -> dict:
    if not path:
        return selected_fields

    parts = path.split(".")
    current = selected_fields

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return {}

    return current if isinstance(current, dict) else {}


def extract_nested_fields(selected_fields: dict[str, bool | dict], field_path: str) -> dict[str, bool | dict]:
    if field_path in selected_fields and isinstance(selected_fields[field_path], dict):
        return selected_fields[field_path]
    return {}


async def map_sqlalchemy_to_type_with_path[T](
    instance: Any,
    info: strawberry.Info,
    target_type: type[T],
    selected_fields: dict[str, bool | dict],
    field_path: str = "",
) -> T | None:
    if instance is None:
        return None

    relevant_fields = extract_nested_fields(selected_fields, field_path) if field_path else selected_fields
    return await map_sqlalchemy_to_type(instance, info, target_type, relevant_fields)


async def map_sqlalchemy_list_to_types[T](
    instances: list[Any],
    info: strawberry.Info,
    target_type: type[T],
    selected_fields: dict[str, bool | dict],
) -> list[T]:
    if not instances:
        return []

    mapped_items = await asyncio.gather(
        *(map_sqlalchemy_to_type(instance, info, target_type, selected_fields) for instance in instances)
    )
    return [item for item in mapped_items if item is not None]
