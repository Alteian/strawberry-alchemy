from __future__ import annotations

import inspect as py_inspect
from datetime import date, datetime, time
from typing import Any

import strawberry
from strawberry.types.base import StrawberryOptional

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


def enrich_mapping_from_schema(schema: Any, mapped_data: dict[str, Any], init_params: set[str]) -> None:
    for field_name in init_params:
        if field_name in mapped_data:
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
