from __future__ import annotations

import inspect as py_inspect
from datetime import date, datetime, time
from typing import Any

import strawberry
from pydantic import BaseModel
from strawberry.types.base import StrawberryList, StrawberryOptional
from strawberry.types.lazy_type import LazyType

UNSET = strawberry.UNSET

_TEMPORAL_PYTHON_TYPES = frozenset({datetime, date, time})


def get_type_init_params(target_type: type[Any]) -> set[str]:
    try:
        return set(py_inspect.signature(target_type.__init__).parameters.keys()) - {"self"}
    except (ValueError, TypeError):
        return {field.name for field in target_type.__strawberry_definition__.fields}


def _field_python_type(field: Any) -> Any:
    if isinstance(field.type, StrawberryOptional):
        return field.type.of_type
    return field.type


def _is_temporal_python_type(value: Any) -> bool:
    return value in _TEMPORAL_PYTHON_TYPES


def nullable_output_field_names(target_type: type[Any]) -> set[str]:
    """Return output field names declared as GraphQL nullable (``T | None``)."""
    return {
        field.name
        for field in target_type.__strawberry_definition__.fields
        if isinstance(field.type, StrawberryOptional)
    }


def temporal_output_field_names(target_type: type[Any]) -> set[str]:
    names: set[str] = set()
    for field in target_type.__strawberry_definition__.fields:
        if _is_temporal_python_type(_field_python_type(field)):
            names.add(field.name)
    return names


def unset_coercible_output_field_names(target_type: type[Any]) -> set[str]:
    return temporal_output_field_names(target_type) | nullable_output_field_names(target_type)


def enrich_mapping_from_schema(
    schema: Any,
    mapped_data: dict[str, Any],
    init_params: set[str],
    *,
    exclude: set[str] | None = None,
) -> None:
    skip = exclude or set()
    for field_name in init_params:
        if field_name in mapped_data or field_name in skip:
            continue
        if hasattr(schema, field_name):
            mapped_data[field_name] = getattr(schema, field_name)


def prepare_output_constructor_data(
    target_type: type[Any],
    data: dict[str, Any],
    *,
    requested_fields: set[str] | None = None,
    init_params: set[str] | None = None,
) -> dict[str, Any]:
    params = init_params if init_params is not None else get_type_init_params(target_type)
    coercible_fields = unset_coercible_output_field_names(target_type)
    normalized = {key: value for key, value in data.items() if key in params}

    for key, value in list(normalized.items()):
        if value is UNSET and key in coercible_fields:
            normalized[key] = None

    if requested_fields is None:
        fields_to_fill = coercible_fields & params
    else:
        fields_to_fill = {name for name in requested_fields if name in coercible_fields and name in params}

    for field_name in fields_to_fill:
        if field_name not in normalized:
            normalized[field_name] = None

    return normalized


def normalize_unset_scalars_on_instance(
    instance: Any,
    target_type: type[Any],
    *,
    requested_fields: set[str] | None = None,
) -> None:
    coercible_fields = unset_coercible_output_field_names(target_type)

    if requested_fields is None:
        candidate_fields = coercible_fields
    else:
        candidate_fields = {name for name in requested_fields if name in coercible_fields}

    for field_name in candidate_fields:
        try:
            value = getattr(instance, field_name)
        except AttributeError:
            continue
        if value is UNSET:
            object.__setattr__(instance, field_name, None)


def _unwrap_strawberry_field_type(field_type: Any) -> tuple[type[Any] | None, bool]:
    """Unwrap Optional / List / LazyType to a concrete Strawberry object type, if any."""
    current = field_type
    is_list = False

    while True:
        if isinstance(current, StrawberryOptional):
            current = current.of_type
            continue
        if isinstance(current, StrawberryList):
            is_list = True
            current = current.of_type
            continue
        if isinstance(current, LazyType):
            current = current.resolve_type()
            continue
        break

    if isinstance(current, type) and hasattr(current, "__strawberry_definition__"):
        return current, is_list
    return None, is_list


def _is_schema_like(value: Any) -> bool:
    return isinstance(value, BaseModel)


def _is_list_of_schema_like(value: Any) -> bool:
    return isinstance(value, list) and all(_is_schema_like(item) for item in value)


def _prefer_live_schema_value(source_schema: Any, field_name: str, current: Any) -> Any:
    if source_schema is None:
        return current
    live = getattr(source_schema, field_name, UNSET)
    if live is UNSET:
        return current
    if live is None:
        return None
    if _is_schema_like(live) or _is_list_of_schema_like(live):
        return live
    return current


def _construct_from_mapping(
    target_type: type[Any],
    data: dict[str, Any],
    *,
    seen: set[int],
) -> Any:
    mapped = dict(data)
    convert_nested_schema_fields(
        target_type,
        mapped,
        source_schema=None,
        skip_keys=set(),
        seen=seen,
    )
    prepared = prepare_output_constructor_data(target_type, mapped)
    return target_type(**prepared)


def _convert_one_nested_value(
    value: Any,
    related_type: type[Any],
    *,
    seen: set[int],
) -> Any:
    if value is None or value is UNSET:
        return None
    if hasattr(value, "__strawberry_definition__"):
        return value
    if _is_schema_like(value):
        if id(value) in seen:
            return None
        if hasattr(related_type, "from_schema"):
            return related_type.from_schema(value, _nested_conversion_seen=seen)
        dumped = value.model_dump(exclude_unset=True)
        return _construct_from_mapping(related_type, dumped, seen=seen | {id(value)})
    if isinstance(value, dict):
        return _construct_from_mapping(related_type, value, seen=seen)
    return value


def convert_nested_schema_fields(
    target_type: type[Any],
    mapped_data: dict[str, Any],
    *,
    source_schema: Any,
    skip_keys: set[str],
    seen: set[int],
) -> None:
    """Convert nested Pydantic schemas (or their dumped dicts) into related Strawberry types."""
    definition = getattr(target_type, "__strawberry_definition__", None)
    if definition is None:
        return

    for field in definition.fields:
        field_name = field.name
        if field_name not in mapped_data or field_name in skip_keys:
            continue

        related_type, is_list = _unwrap_strawberry_field_type(field.type)
        if related_type is None:
            continue

        value = _prefer_live_schema_value(source_schema, field_name, mapped_data[field_name])
        if value is None or value is UNSET:
            mapped_data[field_name] = None
            continue

        if is_list:
            if not isinstance(value, list):
                mapped_data[field_name] = value
                continue
            mapped_data[field_name] = [_convert_one_nested_value(item, related_type, seen=seen) for item in value]
        else:
            mapped_data[field_name] = _convert_one_nested_value(value, related_type, seen=seen)
