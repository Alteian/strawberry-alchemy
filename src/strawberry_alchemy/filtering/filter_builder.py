from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, cast

import strawberry
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, and_, or_
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB
from sqlalchemy.orm import aliased
from sqlalchemy.orm.util import AliasedClass
from strawberry.relay import GlobalID

from .operators import FilterOperators

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement

SQL_ALCHEMY_TYPE_MAPPING: dict[type[Any], Callable[[Any], Any]] = {
    String: str,
    Integer: int,
    Float: float,
    Boolean: lambda v: v.lower() in ("true", "1", "t", "y", "yes") if isinstance(v, str) else bool(v),
}

_JSONB_TYPES = (JSON, PGJSONB)

type ModelOrAlias = type[Any] | AliasedClass[Any]


class FilterBuilder:
    def __init__(self, custom_filters: dict[type, dict[str, Any]] | None = None) -> None:
        self.alias_map: dict[str, ModelOrAlias] = {}
        self._join_paths: dict[str, list[tuple[str, type[Any]]]] = {}
        self.custom_filters: dict[type, dict[str, Any]] = custom_filters or {}

    @staticmethod
    def _is_jsonb_column(model_field: Any) -> bool:
        """Return True if the SQLAlchemy column attribute is a JSON/JSONB type."""
        try:
            col_type = model_field.property.columns[0].type
            return isinstance(col_type, _JSONB_TYPES)
        except (AttributeError, IndexError):
            return False

    def _is_filter_input(self, val: Any) -> bool:
        return hasattr(val, "__dict__") and not isinstance(val, GlobalID)

    @staticmethod
    def _normalize_lookup_key(key: str) -> str:
        if key == "in_":
            return "in"
        if key == "not_in_":
            return "not_in"
        return key

    async def _apply_ops_to_column(
        self,
        column: Any,
        model_field: Any,
        filter_input: Any,
    ) -> list[ColumnElement[bool]]:
        expressions: list[ColumnElement[bool]] = []
        for op_key, op_val in vars(filter_input).items():
            if op_val is None or op_val is strawberry.UNSET:
                continue
            actual_op = self._normalize_lookup_key(op_key)
            if actual_op not in FilterOperators.LOOKUP_OPERATORS:
                continue
            parsed_val = await self.parse_filter_value(op_val, model_field)
            operator_func = FilterOperators.LOOKUP_OPERATORS[actual_op]
            expressions.append(cast("ColumnElement[bool]", operator_func(column, parsed_val)))
        return expressions

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
                if isinstance(value, datetime):
                    return value
                if isinstance(value, date):
                    return datetime.combine(value, datetime.min.time())
                return datetime.fromisoformat(str(value))
            elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return [await self.parse_filter_value(v, field) for v in value]
            parse_func = SQL_ALCHEMY_TYPE_MAPPING.get(type(field_type))
            if parse_func is not None:
                return parse_func(value)

            return value

        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid value '{value}' for field {field.name}: {e!s}") from e

    async def build_field_filter(
        self,
        model: ModelOrAlias,
        field: str,
        value: Any,
        lookup: str = "exact",
        path_prefix: str = "",
    ) -> ColumnElement[bool] | None:
        if "__" in field:
            field_name, actual_lookup = field.rsplit("__", 1)
        else:
            field_name = field
            actual_lookup = lookup

        original_class: type[Any] = cast("type[Any]", model)
        if hasattr(model, "_aliased_insp"):
            original_class = model._aliased_insp.mapper.class_
        model_custom_filters = self.custom_filters.get(original_class, {})
        if field_name in model_custom_filters:
            handler = model_custom_filters[field_name]
            return cast("ColumnElement[bool] | None", handler(model, value))

        if not hasattr(model, field_name):
            raise ValueError(f"Field '{field_name}' not found in model {model.__name__}")

        model_field = getattr(model, field_name)

        if hasattr(model_field, "property") and hasattr(model_field.property, "mapper"):
            related_model = cast("type[Any]", model_field.property.mapper.class_)
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
            return cast("ColumnElement[bool] | None", operator_func(model_field, parsed_value))

        # Flattened JSONB key path: title__cs + StringFilter(...) or scalar.
        if self._is_jsonb_column(model_field) and actual_lookup not in FilterOperators.LOOKUP_OPERATORS:
            text_expr = model_field[actual_lookup].astext
            if self._is_filter_input(value):
                expressions = await self._apply_ops_to_column(text_expr, model_field, value)
                return and_(*expressions) if expressions else None
            parsed_value = await self.parse_filter_value(value, model_field)
            return cast("ColumnElement[bool]", text_expr == parsed_value)

        if self._is_filter_input(value):
            # Nested LocalizedStringFilter-style keys on a JSONB column.
            if self._is_jsonb_column(model_field):
                expressions = []
                for jsonb_key, nested_value in vars(value).items():
                    if nested_value is None or nested_value == strawberry.UNSET:
                        continue
                    actual_key = self._normalize_lookup_key(jsonb_key)
                    if actual_key in FilterOperators.LOOKUP_OPERATORS:
                        expr = await self.build_field_filter(
                            model,
                            f"{field_name}__{actual_key}",
                            nested_value,
                            path_prefix=path_prefix,
                        )
                        if expr is not None:
                            expressions.append(expr)
                        continue

                    text_expr = model_field[jsonb_key].astext
                    if self._is_filter_input(nested_value):
                        expressions.extend(await self._apply_ops_to_column(text_expr, model_field, nested_value))
                    else:
                        parsed_val = await self.parse_filter_value(nested_value, model_field)
                        expressions.append(cast("ColumnElement[bool]", text_expr == parsed_val))
                return and_(*expressions) if expressions else None

            expressions = []
            for lookup_key, raw_val in vars(value).items():
                if raw_val is None or raw_val == strawberry.UNSET:
                    continue
                actual_lookup_key = self._normalize_lookup_key(lookup_key)
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
        return cast("ColumnElement[bool] | None", operator_func(model_field, parsed_value))

    @staticmethod
    def _combine_expressions(expressions: list[Any], combiner: Any) -> Any | None:
        if not expressions:
            return None
        if len(expressions) == 1:
            return expressions[0]
        return combiner(*expressions)

    async def build_filters(
        self,
        model: ModelOrAlias,
        filters: dict[str, Any],
    ) -> ColumnElement[bool] | None:
        if not filters:
            return None

        async def process_branch(branch: dict[str, Any]) -> Any | None:
            """Build one logical branch: field filters AND nested AND/OR groups."""
            return self._combine_expressions(await process_conditions(branch), and_)

        async def process_combiner_value(value: Any, combiner: Any) -> Any | None:
            """Combine list/dict arms with or_/and_ without flattening multi-field arms."""
            arms: list[Any] = []
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        arm = await process_branch(item)
                    else:
                        continue
                    if arm is not None:
                        arms.append(arm)
            elif isinstance(value, dict):
                arm = await process_branch(value)
                if arm is not None:
                    arms.append(arm)
            return self._combine_expressions(arms, combiner)

        async def process_conditions(conditions: dict[str, Any] | list[dict[str, Any]]) -> list[Any]:
            result: list[Any] = []

            async def process_condition(field: str, value: Any) -> None:
                if field == "AND":
                    expr = await process_combiner_value(value, and_)
                    if expr is not None:
                        result.append(expr)
                elif field == "OR":
                    expr = await process_combiner_value(value, or_)
                    if expr is not None:
                        result.append(expr)
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

        root_conditions: list[Any] = []

        for field, value in filters.items():
            if field == "AND":
                expr = await process_combiner_value(value, and_)
                if expr is not None:
                    root_conditions.append(expr)
            elif field == "OR":
                expr = await process_combiner_value(value, or_)
                if expr is not None:
                    root_conditions.append(expr)
            else:
                expr = await self.build_field_filter(model, field, value)
                if expr is not None:
                    root_conditions.append(expr)

        return self._combine_expressions(root_conditions, and_)

    def build_filter_dict(self, filters: Any | None) -> dict[str, Any]:
        if filters is None or filters == strawberry.UNSET:
            return {}

        filter_dict: dict[str, Any] = {}

        def add_filter(key: str, value: Any) -> None:
            if value is not None and value != strawberry.UNSET:
                filter_dict[key] = value

        self.process_filter_object(filters, filter_dict, add_filter)
        return filter_dict

    def process_filter_object(
        self,
        filter_obj: Any,
        filter_dict: dict[str, Any],
        add_filter: Callable[[str, Any], None],
        parent_key: str = "",
    ) -> None:
        nested_and_filters: list[dict[str, Any]] = []
        nested_or_filters: list[dict[str, Any]] = []

        if hasattr(filter_obj, "OR") and filter_obj.OR is not None and filter_obj.OR != strawberry.UNSET:
            for or_condition in filter_obj.OR:
                nested_or_filters.append(self.build_filter_dict(or_condition))

        if hasattr(filter_obj, "AND") and filter_obj.AND is not None and filter_obj.AND != strawberry.UNSET:
            for and_condition in filter_obj.AND:
                nested_and_filters.append(self.build_filter_dict(and_condition))

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
