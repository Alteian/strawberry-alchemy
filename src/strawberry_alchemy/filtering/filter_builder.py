from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

import dateutil.parser
import strawberry
from sqlalchemy import BinaryExpression, Boolean, DateTime, Float, Integer, String, and_, or_
from sqlalchemy.orm import aliased
from strawberry.relay import GlobalID

if TYPE_CHECKING:
    from sqlalchemy.orm.util import AliasedClass

from .operators import FilterOperators

SQL_ALCHEMY_TYPE_MAPPING = {
    String: str,
    Integer: int,
    Float: float,
    Boolean: lambda v: v.lower() in ("true", "1", "t", "y", "yes") if isinstance(v, str) else bool(v),
}


class FilterBuilder:
    def __init__(self, custom_filters: dict[type, dict[str, Any]] | None = None) -> None:
        self.alias_map: dict[str, AliasedClass | type] = {}
        self._join_paths: dict[str, list[tuple[str, type]]] = {}
        self.custom_filters: dict[type, dict[str, Any]] = custom_filters or {}

    def _is_filter_input(self, val: Any) -> bool:
        return hasattr(val, "__dict__") and not isinstance(val, GlobalID)

    async def parse_filter_value(self, value: Any, field: Any) -> Any:
        if not hasattr(field, "type"):
            return value
        if value is None:
            return None
        if isinstance(value, GlobalID):
            return value.node_id.strip()

        try:
            field_type = field.type

            if isinstance(field_type, DateTime):
                return dateutil.parser.parse(str(value))
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [await self.parse_filter_value(v, field) for v in value]
            parse_func = SQL_ALCHEMY_TYPE_MAPPING.get(type(field_type))
            if parse_func:
                return parse_func(value)

            return value

        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid value '{value}' for field {field.name}: {e!s}") from e

    async def build_field_filter(
        self,
        model: type[Any],
        field: str,
        value: Any,
        lookup: str = "exact",
        path_prefix: str = "",
    ) -> BinaryExpression | None:
        if "__" in field:
            field_name, actual_lookup = field.rsplit("__", 1)
        else:
            field_name = field
            actual_lookup = lookup

        original_class = model
        if hasattr(model, "_aliased_insp"):
            original_class = model._aliased_insp.mapper.class_
        model_custom_filters = self.custom_filters.get(original_class, {})
        if field_name in model_custom_filters:
            handler = model_custom_filters[field_name]
            return handler(model, value)

        if not hasattr(model, field_name):
            raise ValueError(f"Field '{field_name}' not found in model {model.__name__}")

        model_field = getattr(model, field_name)

        if hasattr(model_field, "property") and hasattr(model_field.property, "mapper"):
            related_model = model_field.property.mapper.class_
            current_path = f"{path_prefix}.{field_name}" if path_prefix else field_name

            if related_model is model and field_name in ("parent", "children"):
                alias_key = f"{current_path}_{id(value)}"
                if alias_key not in self.alias_map:
                    self.alias_map[alias_key] = aliased(related_model)
                    self._join_paths[alias_key] = [(field_name, related_model)]
                aliased_model = self.alias_map[alias_key]
                return await self.build_field_filter(aliased_model, actual_lookup, value, path_prefix=current_path)

            if current_path not in self.alias_map:
                self.alias_map[current_path] = aliased(related_model)
                if path_prefix and path_prefix in self._join_paths:
                    self._join_paths[current_path] = [
                        *self._join_paths[path_prefix],
                        (field_name, related_model),
                    ]
                else:
                    self._join_paths[current_path] = [(field_name, related_model)]

            aliased_model = self.alias_map[current_path]
            return await self.build_field_filter(aliased_model, actual_lookup, value, path_prefix=current_path)

        if actual_lookup in FilterOperators.LOOKUP_OPERATORS and not self._is_filter_input(value):
            parsed_value = await self.parse_filter_value(value, model_field)
            operator_func = FilterOperators.LOOKUP_OPERATORS[actual_lookup]
            return operator_func(model_field, parsed_value)

        if self._is_filter_input(value):
            expressions = []
            for lookup_key, raw_val in vars(value).items():
                if raw_val is None or raw_val == strawberry.UNSET:
                    continue
                if lookup_key == "in_":
                    actual_lookup_key = "in"
                elif lookup_key == "not_in_":
                    actual_lookup_key = "not_in"
                else:
                    actual_lookup_key = lookup_key
                expr = await self.build_field_filter(
                    model, f"{field_name}__{actual_lookup_key}", raw_val, path_prefix=path_prefix
                )
                if expr is not None:
                    expressions.append(expr)
            return and_(*expressions) if expressions else None

        if actual_lookup not in FilterOperators.LOOKUP_OPERATORS:
            raise ValueError(f"Unsupported lookup: {actual_lookup}")

        parsed_value = await self.parse_filter_value(value, model_field)

        operator_func = FilterOperators.LOOKUP_OPERATORS[actual_lookup]
        return operator_func(model_field, parsed_value)

    async def build_filters(
        self,
        model: type[Any],
        filters: dict[str, Any],
    ) -> BinaryExpression | None:
        if not filters:
            return None

        async def process_conditions(conditions: dict[str, Any] | list[dict[str, Any]]) -> list[BinaryExpression]:
            result = []

            async def process_condition(field: str, value: Any) -> None:
                if field == "AND":
                    and_conditions = []
                    if isinstance(value, list):
                        for and_item in value:
                            and_expr = await process_conditions(and_item)
                            if isinstance(and_expr, list):
                                and_conditions.extend(and_expr)
                            else:
                                and_conditions.append(and_expr)
                    elif isinstance(value, dict):
                        and_expr = await process_conditions(value)
                        if isinstance(and_expr, list):
                            and_conditions.extend(and_expr)
                        else:
                            and_conditions.append(and_expr)
                    if and_conditions:
                        result.append(and_(*and_conditions))
                elif field == "OR":
                    or_conditions = []
                    if isinstance(value, list):
                        for or_item in value:
                            or_expr = await process_conditions(or_item)
                            if isinstance(or_expr, list):
                                or_conditions.extend(or_expr)
                            else:
                                or_conditions.append(or_expr)
                    elif isinstance(value, dict):
                        or_expr = await process_conditions(value)
                        if isinstance(or_expr, list):
                            or_conditions.extend(or_expr)
                        else:
                            or_conditions.append(or_expr)
                    if or_conditions:
                        result.append(or_(*or_conditions))
                else:
                    expr = await self.build_field_filter(model, field, value)
                    if expr is not None:
                        result.append(expr)

            if isinstance(conditions, list):
                for item in conditions:
                    for field, value in item.items():
                        await process_condition(field, value)
            elif isinstance(conditions, dict):
                for field, value in conditions.items():
                    await process_condition(field, value)

            return result

        root_conditions = []

        for field, value in filters.items():
            if field == "AND":
                and_conditions = await process_conditions(value)
                if and_conditions:
                    root_conditions.append(and_(*and_conditions))
            elif field == "OR":
                or_conditions = await process_conditions(value)
                if or_conditions:
                    root_conditions.append(or_(*or_conditions))
            else:
                expr = await self.build_field_filter(model, field, value)
                if expr is not None:
                    root_conditions.append(expr)

        if root_conditions:
            if len(root_conditions) == 1:
                return root_conditions[0]
            else:
                return and_(*root_conditions)

        return None

    def build_filter_dict(self, filters: Any | None) -> dict[str, Any]:
        if filters is None or filters == strawberry.UNSET:
            return {}

        filter_dict = {}

        def add_filter(key: str, value: Any):
            if value is not None and value != strawberry.UNSET:
                filter_dict[key] = value

        self.process_filter_object(filters, filter_dict, add_filter)
        return filter_dict

    def process_filter_object(
        self, filter_obj: Any, filter_dict: dict[str, Any], add_filter: Callable, parent_key: str = ""
    ) -> None:
        nested_and_filters = {}
        nested_or_filters = []

        if hasattr(filter_obj, "OR") and filter_obj.OR is not None and filter_obj.OR != strawberry.UNSET:
            or_conditions = filter_obj.OR
            [nested_or_filters.append(self.build_filter_dict(or_condition)) for or_condition in or_conditions]

        if hasattr(filter_obj, "AND") and filter_obj.AND is not None and filter_obj.AND != strawberry.UNSET:
            and_conditions = filter_obj.AND
            for and_condition in and_conditions:
                nested_and_filters.update(self.build_filter_dict(and_condition))

        _excluded_attrs = {
            "type_name",
            "__dict__",
            "__module__",
            "__weakref__",
            "__class__",
            "__doc__",
            "__str__",
            "__repr__",
            "__hash__",
            "__eq__",
            "__ne__",
            "__typename",
            "_state",
            "AND",
            "OR",
        }

        if hasattr(filter_obj, "__dict__"):
            for attr, field_value in vars(filter_obj).items():
                if (
                    attr.startswith("_")
                    or attr in _excluded_attrs
                    or field_value is strawberry.UNSET
                    or field_value is None
                ):
                    continue

                if hasattr(field_value, "__dict__") and not isinstance(
                    field_value, (str, int, float, bool, list, GlobalID)
                ):
                    for filter_attr, filter_value in vars(field_value).items():
                        if (
                            filter_attr.startswith("_")
                            or filter_attr in _excluded_attrs
                            or filter_value is None
                            or filter_value is strawberry.UNSET
                        ):
                            continue

                        if filter_attr == "in_":
                            key = f"{parent_key}{attr}__in"
                        elif filter_attr == "not_in_":
                            key = f"{parent_key}{attr}__not_in"
                        else:
                            key = f"{parent_key}{attr}__{filter_attr}"

                        if isinstance(filter_value, list) and all(isinstance(g, GlobalID) for g in filter_value):
                            filter_value = [g.node_id.strip() for g in filter_value]
                        elif isinstance(filter_value, GlobalID):
                            filter_value = filter_value.node_id.strip()
                        elif hasattr(filter_value, "value"):
                            filter_value = filter_value.value
                        add_filter(key, filter_value)

                elif isinstance(field_value, list):
                    if all(isinstance(g, GlobalID) for g in field_value):
                        filter_value = [g.node_id.strip() for g in field_value]
                        add_filter(attr, filter_value)
                    else:
                        add_filter(attr, field_value)

                elif isinstance(field_value, (str, int, float, bool)):
                    add_filter(attr, field_value)

        if nested_and_filters:
            filter_dict["AND"] = nested_and_filters
        if nested_or_filters:
            filter_dict["OR"] = nested_or_filters
