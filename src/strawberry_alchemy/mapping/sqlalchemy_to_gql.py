import asyncio
from typing import Any, TypeVar, cast, get_args, get_origin

import strawberry
from sqlalchemy.inspection import inspect
from strawberry.relay import GlobalID
from strawberry.types.base import StrawberryOptional
from strawberry.types.lazy_type import LazyType

from strawberry_alchemy.mapping.output_normalization import (
    get_type_init_params,
    prepare_output_constructor_data,
)

T = TypeVar("T")
UNSET = strawberry.UNSET

type FieldSelectionDict = dict[str, bool | FieldSelectionDict]

# Optional override: field name → Relay type name used by create_global_id_from_field.
# Example: register_global_id_type("locked_by", "UserType")
_GLOBAL_ID_TYPE_REGISTRY: dict[str, str] = {}


def register_global_id_type(field_name: str, type_name: str) -> None:
    """Register an explicit GraphQL type name for GlobalID encoding of ``field_name``."""
    _GLOBAL_ID_TYPE_REGISTRY[field_name] = type_name


def clear_global_id_type_registry() -> None:
    _GLOBAL_ID_TYPE_REGISTRY.clear()


def _requested_leaf_fields(selected_fields: FieldSelectionDict) -> set[str]:
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
    if field_name in _GLOBAL_ID_TYPE_REGISTRY:
        type_name = _GLOBAL_ID_TYPE_REGISTRY[field_name]
    else:
        base_name = field_name.removesuffix("_id")
        type_name = f"{base_name.replace('_', ' ').title().replace(' ', '')}Type"
    return GlobalID(type_name=type_name, node_id=str(value))


def _annotation_is_nested_list_result(annotation: Any) -> bool:
    from strawberry_alchemy.types.list_result import NestedListResult

    current = annotation
    while True:
        if isinstance(current, StrawberryOptional):
            current = current.of_type
            continue
        if isinstance(current, LazyType):
            current = current.resolve_type()
            continue
        origin = get_origin(current)
        if origin is not None:
            if origin is NestedListResult or getattr(origin, "__name__", "") == "NestedListResult":
                return True
            # Union / | None
            args = get_args(current)
            if args:
                return any(_annotation_is_nested_list_result(arg) for arg in args if arg is not type(None))
            break
        if current is NestedListResult or (
            isinstance(current, type) and getattr(current, "__name__", "") == "NestedListResult"
        ):
            return True
        # Specialized strawberry generic: check definition fields
        definition = getattr(current, "__strawberry_definition__", None)
        if definition is not None:
            names = {f.name for f in definition.fields}
            if "items" in names and "has_more" in names:
                return True
        break
    return False


def _field_uses_nested_list_result(target_type: type[Any], field_name: str) -> bool:
    definition = getattr(target_type, "__strawberry_definition__", None)
    if definition is None:
        annotation = getattr(target_type, "__annotations__", {}).get(field_name)
        return _annotation_is_nested_list_result(annotation) if annotation is not None else False
    for field_def in definition.fields:
        if field_def.name == field_name:
            return _annotation_is_nested_list_result(field_def.type)
    annotation = getattr(target_type, "__annotations__", {}).get(field_name)
    return _annotation_is_nested_list_result(annotation) if annotation is not None else False


def _nested_item_selection(nested_fields: FieldSelectionDict) -> FieldSelectionDict:
    """Unwrap NestedListResult / ListResult ``items { … }`` selection when present."""
    items = nested_fields.get("items")
    if isinstance(items, dict):
        return items
    # After optimizer extract_model_fields, items is already flattened — drop has_more leaf.
    return {k: v for k, v in nested_fields.items() if k not in {"has_more", "hasMore"}}


async def map_sqlalchemy_to_type[T](
    instance: Any,
    info: strawberry.Info,
    target_type: type[T],
    selected_fields: FieldSelectionDict,
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
            nested_raw = selected_fields.get(field_name, {})
            nested_fields: FieldSelectionDict = nested_raw if isinstance(nested_raw, dict) else {}
            item_fields = _nested_item_selection(nested_fields)
            wrap_nested = _field_uses_nested_list_result(target_type, field_name)

            if isinstance(value, list):
                mapped_list: list[Any] = []
                if value:
                    relationship_type = get_graphql_type_from_sqlalchemy(info, value[0])
                    if relationship_type:
                        mapped_items = await asyncio.gather(
                            *(
                                map_sqlalchemy_to_type(item, info, relationship_type, item_fields)
                                for item in value
                                if item is not None and item is not UNSET
                            )
                        )
                        mapped_list = [item for item in mapped_items if item is not None]

                from strawberry_alchemy.types.list_result import NestedListResult
                from strawberry_alchemy.types.node_config import resolve_max_items

                if wrap_nested:
                    max_items = resolve_max_items(target_type, field_name)
                    has_more = False
                    if max_items is not None and len(mapped_list) > max_items:
                        has_more = True
                        mapped_list = mapped_list[:max_items]
                    type_data[field_name] = NestedListResult(items=mapped_list, has_more=has_more)
                else:
                    max_items = resolve_max_items(target_type, field_name)
                    if max_items is not None and len(mapped_list) > max_items:
                        mapped_list = mapped_list[:max_items]
                    type_data[field_name] = mapped_list

            elif value is None:
                type_data[field_name] = None
            elif value is not UNSET:
                relationship_type = get_graphql_type_from_sqlalchemy(info, value)
                if relationship_type:
                    mapped_value = await map_sqlalchemy_to_type(value, info, relationship_type, item_fields)
                    if mapped_value is not None:
                        type_data[field_name] = mapped_value
                    else:
                        type_data[field_name] = None
                else:
                    type_data[field_name] = None
        else:
            annotation = type_annotations.get(field_name)
            annotation_str = str(annotation) if annotation is not None else ""

            if value is not None and value is not UNSET and "GlobalID" in annotation_str:
                type_data[field_name] = create_global_id_from_field(field_name, value)
            elif value is not None and value is not UNSET:
                # Trim JSONB / dict scalars to only keys requested in the selection tree.
                if isinstance(value, dict) and isinstance(is_selected, dict):
                    requested_keys = {k for k, v in is_selected.items() if v is True and k in value}
                    if requested_keys:
                        value = {k: value[k] for k in requested_keys}

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
            return cast("type[Any]", type_obj.origin)

    return None


def extract_fields_at_path(selected_fields: FieldSelectionDict, path: str) -> FieldSelectionDict:
    from strawberry_alchemy.optimizer.selection import extract_at_path

    if not path:
        return selected_fields

    return cast("FieldSelectionDict", extract_at_path(selected_fields, path))


def extract_nested_fields(selected_fields: FieldSelectionDict, field_path: str) -> FieldSelectionDict:
    nested = selected_fields.get(field_path)
    if isinstance(nested, dict):
        return nested
    return {}


async def map_sqlalchemy_to_type_with_path[T](
    instance: Any,
    info: strawberry.Info,
    target_type: type[T],
    selected_fields: FieldSelectionDict,
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
    selected_fields: FieldSelectionDict,
) -> list[T]:
    if not instances:
        return []

    mapped_items = await asyncio.gather(
        *(map_sqlalchemy_to_type(instance, info, target_type, selected_fields) for instance in instances)
    )
    return [item for item in mapped_items if item is not None]
