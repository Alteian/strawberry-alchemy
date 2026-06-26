import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, cast

from sqlalchemy import and_, literal, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import RelationshipProperty, defer, selectinload
from sqlalchemy.sql import func, select
from strawberry import UNSET
from strawberry.types import Info
from strawberry.types.nodes import FragmentSpread, InlineFragment

from strawberry_alchemy.enums import Ordering
from strawberry_alchemy.filtering.filter_builder import FilterBuilder
from strawberry_alchemy.utils import camel_to_snake

from .prefetch import (
    AnnotateAncestry,
    AnnotateAnyExists,
    AnnotateCount,
    AnnotateCustom,
    AnnotateExists,
    PrefetchRelated,
    ResolvedDependencies,
    get_prefetch_map,
    merge_dependency_trees,
    normalize_dependency_fields,
)
from .query_analyzer import QueryAnalyzer

logger = logging.getLogger("query_optimizer")


@dataclass(frozen=True, slots=True)
class QueryResult:
    items: list[Any] = field(default_factory=list)
    selected_fields: dict[str, Any] = field(default_factory=dict)
    total_count: int = 0


_ANALYZER_ENABLED = os.environ.get("QUERY_ANALYZER_ENABLED", None)


def _create_analyzer() -> QueryAnalyzer:
    return QueryAnalyzer(log_level=logging.INFO)


@lru_cache(maxsize=512)
def _cached_model_attributes(model: type) -> dict[str, Any]:
    mapper = inspect(model)
    return {column.key: getattr(model, column.key) for column in mapper.columns}


class QueryOptimizer:
    def __init__(
        self,
        info: Info,
        session: AsyncSession,
        *,
        analyzer: QueryAnalyzer | None = None,
    ) -> None:
        self.info = info
        self.session = session
        self.access_filters: dict[type, type] = {}

        if analyzer is not None:
            self.analyzer = analyzer
        elif _ANALYZER_ENABLED:
            self.analyzer = _create_analyzer()
        else:
            self.analyzer = None

        self._register_default_filters()

    def _register_default_filters(self) -> None:
        pass

    async def _get_identity(self) -> Any:
        ctx = self.info.context
        for attr in ("identity", "user"):
            try:
                value = getattr(ctx, attr)
            except Exception:
                continue
            if value is not None:
                if hasattr(value, "__await__"):
                    return await value
                return value
        return None

    def register_access_filter(self, model_class: type, filter_class: type) -> None:
        self.access_filters[model_class] = filter_class

    def register_access_filter_by_name(self, model_name: str, filter_class: type) -> None:
        if not hasattr(self, "_filters_by_name"):
            self._filters_by_name: dict[str, type] = {}
        self._filters_by_name[model_name] = filter_class

    def get_access_filter(self, model: type[Any]) -> Any | None:
        if model in self.access_filters:
            return self.access_filters[model]
        if hasattr(self, "_filters_by_name") and model.__name__ in self._filters_by_name:
            return self._filters_by_name[model.__name__]
        return None

    async def apply_access_control(self, query: Any, model: type[Any]) -> Any:
        access_filter = self.get_access_filter(model)
        if access_filter is not None:
            context_user = await self._get_identity()
            query = await cast("Any", access_filter).apply_filter(query, model, context_user)
        return query

    def normalize_field_name(self, field_name: str) -> str:
        if field_name in ("__typename", "edges", "node", "pageInfo", "totalCount", "items"):
            return field_name
        normalized = camel_to_snake(field_name)
        return normalized if isinstance(normalized, str) else field_name

    def extract_model_fields(self, selected_fields: dict, level: int = 0) -> dict:
        relay_wrapper_keys = {"edges", "cursor", "pageInfo", "totalCount", "__typename", "items"}

        if set(selected_fields.keys()).issubset(relay_wrapper_keys):
            edges = selected_fields.get("edges")
            if isinstance(edges, dict):
                node = edges.get("node")
                if isinstance(node, dict):
                    return self.extract_model_fields(node, level + 1)

            items = selected_fields.get("items")
            if isinstance(items, dict):
                return self.extract_model_fields(items, level + 1)
            if isinstance(items, list):
                return {
                    "items": [
                        self.extract_model_fields(item, level + 1) if isinstance(item, dict) else item for item in items
                    ]
                }
            return {}

        model_fields: dict[str, Any] = {}
        for key, value in selected_fields.items():
            normalized_key = self.normalize_field_name(key)

            if normalized_key in {"__typename", "cursor", "pageInfo", "totalCount"}:
                continue

            if normalized_key == "edges" and isinstance(value, dict):
                node = value.get("node")
                if isinstance(node, dict):
                    nested = self.extract_model_fields(node, level + 1)
                    model_fields.update(nested)
                continue

            if normalized_key == "items":
                if isinstance(value, dict):
                    nested = self.extract_model_fields(value, level + 1)
                    model_fields.update(nested)
                    continue
                if isinstance(value, list):
                    extracted_list = [
                        self.extract_model_fields(item, level + 1) if isinstance(item, dict) else item for item in value
                    ]
                    model_fields[normalized_key] = extracted_list
                    continue

            if isinstance(value, dict):
                nested = self.extract_model_fields(value, level + 1)
                if nested:
                    model_fields[normalized_key] = nested
            else:
                model_fields[normalized_key] = value

        return model_fields

    def process_selected_fields(self, selected_fields: list) -> dict:
        result: dict[str, Any] = {}
        for f in selected_fields:
            if isinstance(f, FragmentSpread | InlineFragment):
                result.update(self.process_selected_fields(f.selections))
                continue

            key = f.alias or f.name
            normalized_key = self.normalize_field_name(key)

            if f.selections:
                result[normalized_key] = self.process_selected_fields(f.selections)
            else:
                result[normalized_key] = True

        return self.extract_model_fields(result)

    @staticmethod
    def is_relationship(attr: Any) -> bool:
        try:
            return isinstance(attr.property, RelationshipProperty)
        except AttributeError:
            return False

    @staticmethod
    def get_model_attribute(model: type[Any], field_name: str) -> tuple[str, Any]:
        if hasattr(model, field_name):
            return field_name, getattr(model, field_name)

        snake_case_raw = camel_to_snake(field_name)
        snake_case = snake_case_raw if isinstance(snake_case_raw, str) else field_name
        if hasattr(model, snake_case):
            return snake_case, getattr(model, snake_case)

        for variation in (field_name, snake_case, f"{field_name}_id", f"{snake_case}_id"):
            if hasattr(model, variation):
                return variation, getattr(model, variation)

        return field_name, None

    @staticmethod
    def get_all_model_attributes(model: type[Any]) -> dict[str, Any]:
        return _cached_model_attributes(model)

    @staticmethod
    def get_ordering_attributes(model: type[Any]) -> list:
        ordering_candidates = ["created_at", "updated_at", "id"]
        return [getattr(model, attr) for attr in ordering_candidates if hasattr(model, attr)]

    def process_order(self, model: type[Any], order_input: Any) -> tuple[list, dict]:
        if order_input is None or order_input is UNSET:
            return [], {}

        order_clauses: list[Any] = []
        relationship_configs: dict[str, dict[str, Any]] = {}

        for field_name, order_value in order_input.__dict__.items():
            if order_value is None or order_value is UNSET:
                continue

            column_name = self.normalize_field_name(field_name)
            attr = getattr(model, column_name, None)
            if attr is None:
                continue

            if self.is_relationship(attr):
                if hasattr(order_value, "__dict__"):
                    related_model = attr.property.mapper.class_
                    for nested_field, nested_order in order_value.__dict__.items():
                        if nested_order is None or nested_order is UNSET:
                            continue
                        nested_column = self.normalize_field_name(nested_field)
                        if hasattr(related_model, nested_column):
                            relationship_configs[attr.property.key] = {
                                "column": nested_column,
                                "direction": nested_order,
                            }
            else:
                order_clause = attr.desc() if order_value == Ordering.DESC else attr.asc()
                order_clauses.append(order_clause)

        return order_clauses, relationship_configs

    def collect_requested_fields(self, selected_fields: dict[str, Any], model: type[Any]) -> set:
        requested_scalar_attributes: set[Any] = set()
        all_model_attributes = self.get_all_model_attributes(model)

        for field_name, field_value in selected_fields.items():
            if field_name in ("__typename", "edges", "pageInfo", "totalCount", "cursor"):
                continue
            if field_value is not True:
                continue

            column_name, attr = self.get_model_attribute(model, field_name)
            if attr is None:
                continue

            if not self.is_relationship(attr) and column_name in all_model_attributes:
                requested_scalar_attributes.add(all_model_attributes[column_name])

        return requested_scalar_attributes

    def collect_requested_fields_recursive(
        self, selected_fields: dict[str, Any], model: type[Any], path: str = ""
    ) -> dict:
        result: dict[str, Any] = {"scalar_fields": set(), "relationships": {}}
        all_model_attributes = self.get_all_model_attributes(model)
        current_path = f"{path}.{model.__name__}" if path else model.__name__

        for field_name, field_value in selected_fields.items():
            if field_name in ("__typename", "edges", "pageInfo", "totalCount", "cursor"):
                continue

            column_name, attr = self.get_model_attribute(model, field_name)
            if attr is None:
                continue

            if not self.is_relationship(attr):
                if column_name in all_model_attributes:
                    result["scalar_fields"].add(all_model_attributes[column_name])
            elif isinstance(field_value, dict):
                related_model = attr.property.mapper.class_
                relationship_info: dict[str, Any] = {
                    "attr": attr,
                    "related_model": related_model,
                    "selected_fields": field_value,
                }
                nested_result = self.collect_requested_fields_recursive(field_value, related_model, current_path)
                relationship_info["nested"] = nested_result
                result["relationships"][field_name] = relationship_info

        return result

    def get_deferred_attributes(self, selected_fields: dict[str, Any], model: type[Any]) -> list:
        requested_attributes = self.collect_requested_fields(selected_fields, model)
        all_attributes = self.get_all_model_attributes(model)
        return [
            attr
            for attr in all_attributes.values()
            if attr not in requested_attributes and not self.is_relationship(attr)
        ]

    def _resolve_all_dependencies(
        self,
        strawberry_type: type | None,
        selected_fields: dict[str, Any],
        model: type[Any],
        exclude_prefetch: set[str] | None = None,
    ) -> ResolvedDependencies:
        result = ResolvedDependencies(augmented_fields=dict(selected_fields))

        if strawberry_type is None:
            return result

        prefetch_map = get_prefetch_map(strawberry_type)
        if not prefetch_map:
            return result

        for field_name, hints in prefetch_map.items():
            if field_name not in selected_fields:
                continue
            if exclude_prefetch and field_name in exclude_prefetch:
                continue

            for hint in hints:
                if isinstance(
                    hint, (AnnotateExists, AnnotateAnyExists, AnnotateCount, AnnotateCustom, AnnotateAncestry)
                ):
                    result.annotations.append(hint)
                elif isinstance(hint, PrefetchRelated):
                    self._resolve_prefetch_hint(hint, result, model)

        return result

    def _resolve_prefetch_hint(
        self,
        hint: PrefetchRelated,
        result: ResolvedDependencies,
        model: type[Any],
    ) -> None:
        dep_name = hint.relationship

        _, attr = self.get_model_attribute(model, dep_name)
        if attr is None or not self.is_relationship(attr):
            return

        if hint.fields:
            sub_fields = normalize_dependency_fields(hint.fields)
        else:
            related_model = attr.property.mapper.class_
            related_attrs = self.get_all_model_attributes(related_model)
            sub_fields = {key: True for key in related_attrs}

        existing_fields = result.augmented_fields.get(dep_name)
        if isinstance(existing_fields, dict):
            merged_fields = merge_dependency_trees(cast("dict[str, Any]", existing_fields), sub_fields)
        elif existing_fields is True:
            merged_fields = sub_fields
        else:
            merged_fields = sub_fields

        result.augmented_fields[dep_name] = merged_fields

        if hint.has_custom_loading and not any(
            prefetch.relationship == dep_name for prefetch in result.filtered_prefetches
        ):
            result.filtered_prefetches.append(hint)

    def _build_annotation_subquery(
        self,
        model: type[Any],
        annotation: AnnotateExists | AnnotateAnyExists | AnnotateCount | AnnotateCustom | AnnotateAncestry,
        user_id: Any | None,
    ) -> Any:
        if isinstance(annotation, AnnotateAncestry):
            return self._build_ancestry_annotation_subquery(model, annotation)

        if isinstance(annotation, AnnotateAnyExists):
            return self._build_any_exists_annotation_subquery(model, annotation, user_id)

        _, attr = self.get_model_attribute(model, annotation.relationship)
        if attr is None or not self.is_relationship(attr):
            return None

        if isinstance(annotation, AnnotateCustom):
            return self._annotation_custom(model, annotation, attr, user_id)

        rel_prop = attr.property
        parent_table = inspect(model).mapped_table

        if annotation.filter_current_user and user_id is None:
            if isinstance(annotation, AnnotateExists):
                return literal(False)
            return literal(0)

        if rel_prop.secondary is not None:
            return self._annotation_m2m(model, rel_prop, parent_table, annotation, user_id)
        return self._annotation_fk(model, rel_prop, parent_table, annotation, user_id)

    def _build_any_exists_annotation_subquery(
        self,
        model: type[Any],
        annotation: AnnotateAnyExists,
        user_id: Any | None,
    ) -> Any:
        if annotation.filter_current_user and user_id is None:
            return literal(False)

        expressions: list[Any] = []

        for relationship in annotation.relationships:
            exists_annotation = AnnotateExists(
                relationship=relationship,
                filter_current_user=annotation.filter_current_user,
                filter=annotation.filter,
            )
            expression = self._build_annotation_subquery(model, exists_annotation, user_id)
            if expression is not None:
                expressions.append(expression)

        if not expressions:
            return literal(False)

        if len(expressions) == 1:
            return expressions[0]

        return or_(*expressions)

    def _annotation_custom(
        self,
        model: type[Any],
        annotation: AnnotateCustom,
        attr: Any,
        user_id: Any | None,
    ) -> Any | None:
        if annotation.expression is None:
            return None

        rel_prop = attr.property
        related_model = rel_prop.mapper.class_

        try:
            if annotation.filter_current_user:
                return annotation.expression(model, related_model, rel_prop, user_id)
            return annotation.expression(model, related_model, rel_prop)
        except Exception:
            logger.warning(
                "AnnotateCustom expression failed for %s.%s",
                model.__name__,
                annotation.relationship,
                exc_info=True,
            )
            return None

    def _annotation_m2m(
        self,
        model: type,
        rel_prop: Any,
        parent_table: Any,
        annotation: Any,
        user_id: Any,
    ) -> Any:
        secondary = rel_prop.secondary
        parent_fk_col = None
        remote_fk_col = None

        for col in secondary.columns:
            for fk in col.foreign_keys:
                if fk.column.table.fullname == parent_table.fullname:
                    parent_fk_col = col
                else:
                    remote_fk_col = col

        if parent_fk_col is None:
            return None

        model_id_attr = cast("Any", model).id
        conditions = [parent_fk_col == model_id_attr]
        if annotation.filter_current_user and user_id is not None and remote_fk_col is not None:
            conditions.append(remote_fk_col == user_id)

        custom_filter = self._resolve_custom_filter(annotation, rel_prop.mapper.class_)

        if isinstance(annotation, AnnotateExists):
            subq = select(parent_fk_col).where(and_(*conditions)).correlate(model)
            if custom_filter is not None:
                remote_model = rel_prop.mapper.class_
                remote_table = inspect(remote_model).mapped_table
                subq = subq.join(remote_table, remote_fk_col == remote_model.id)
                subq = subq.where(custom_filter)
            return subq.exists()

        subq = select(func.count()).select_from(secondary).where(and_(*conditions)).correlate(model)
        if custom_filter is not None:
            remote_model = rel_prop.mapper.class_
            remote_table = inspect(remote_model).mapped_table
            subq = subq.join(remote_table, remote_fk_col == remote_model.id)
            subq = subq.where(custom_filter)
        return subq.scalar_subquery()

    def _annotation_fk(
        self,
        model: type,
        rel_prop: Any,
        parent_table: Any,
        annotation: Any,
        user_id: Any,
    ) -> Any:
        related_model = rel_prop.mapper.class_
        related_table = inspect(related_model).mapped_table

        fk_attr = None
        for col in related_table.columns:
            for fk in col.foreign_keys:
                if fk.column.table.fullname == parent_table.fullname:
                    fk_attr = getattr(related_model, col.name, None)
                    break
            if fk_attr is not None:
                break

        if fk_attr is None:
            return None

        model_id_attr = cast("Any", model).id
        conditions = [fk_attr == model_id_attr]
        if annotation.filter_current_user and user_id is not None:
            if hasattr(related_model, "user_id"):
                conditions.append(related_model.user_id == user_id)
            elif hasattr(related_model, "id"):
                conditions.append(related_model.id == user_id)

        custom_filter = self._resolve_custom_filter(annotation, related_model)
        if custom_filter is not None:
            conditions.append(custom_filter)

        if isinstance(annotation, AnnotateExists):
            return select(related_model.id).where(and_(*conditions)).correlate(model).exists()

        return select(func.count()).where(and_(*conditions)).correlate(model).scalar_subquery()

    @staticmethod
    def _resolve_custom_filter(
        hint: PrefetchRelated | AnnotateExists | AnnotateCount,
        related_model: type[Any],
    ) -> Any | None:
        filter_fn = getattr(hint, "filter", None)
        if filter_fn is None:
            return None
        return filter_fn(related_model)

    def _build_filtered_selectinload(
        self,
        model: type[Any],
        prefetch: PrefetchRelated,
        user_id: Any | None,
    ) -> Any | None:
        _, attr = self.get_model_attribute(model, prefetch.relationship)
        if attr is None or not self.is_relationship(attr):
            return None

        rel_prop = attr.property
        related_model = rel_prop.mapper.class_

        conditions: list[Any] = []

        if prefetch.filter_current_user:
            if user_id is None:
                return None
            if rel_prop.secondary is not None:
                conditions.append(related_model.id == user_id)
            elif hasattr(related_model, "user_id"):
                conditions.append(related_model.user_id == user_id)
            else:
                conditions.append(related_model.id == user_id)

        custom = self._resolve_custom_filter(prefetch, related_model)
        if custom is not None:
            conditions.append(custom)

        if not conditions:
            return selectinload(attr)

        return selectinload(attr.and_(*conditions))

    def _get_strawberry_type_for_model(self, model: type[Any]) -> type[Any] | None:
        type_name = model.__name__
        possible_names = [f"{type_name}Type", type_name]
        for name in possible_names:
            type_obj = self.info.schema.get_type_by_name(name)
            if type_obj is not None and hasattr(type_obj, "origin"):
                origin: type[Any] = type_obj.origin
                return origin
        return None

    async def build_query_with_selected_fields(
        self,
        model: type[Any],
        selected_fields: dict[str, Any],
        relationship_configs: dict | None = None,
        skip_relationships: set[str] | None = None,
        strawberry_type: type | None = None,
    ) -> list:
        load_options: list[Any] = []
        all_attributes = self.get_all_model_attributes(model)
        requested_attrs = self.collect_requested_fields(selected_fields, model)
        _analyzer = self.analyzer
        _skip_keys = frozenset(("__typename", "edges", "pageInfo", "totalCount"))

        for field_name, subfields in selected_fields.items():
            if field_name in _skip_keys:
                continue

            column_name, attr = self.get_model_attribute(model, field_name)
            if attr is None:
                continue

            if self.is_relationship(attr):
                if skip_relationships and field_name in skip_relationships:
                    continue

                if isinstance(subfields, dict):
                    related_model = attr.property.mapper.class_

                    nested_strawberry_type = self._get_strawberry_type_for_model(related_model)
                    if nested_strawberry_type:
                        nested_deps = self._resolve_all_dependencies(nested_strawberry_type, subfields, related_model)
                        subfields = nested_deps.augmented_fields
                        selected_fields[field_name] = subfields
                    else:
                        nested_strawberry_type = None

                    if relationship_configs and attr.property.key in relationship_configs:
                        config = relationship_configs[attr.property.key]
                        order_col = getattr(related_model, config["column"])
                        attr.property.order_by = [
                            order_col.desc() if config["direction"] == Ordering.DESC else order_col.asc()
                        ]

                    relationship_loader = selectinload(attr)

                    nested_load_options = await self.build_query_with_selected_fields(
                        related_model, subfields, relationship_configs, strawberry_type=nested_strawberry_type
                    )
                    relationship_loader = relationship_loader.options(*nested_load_options)
                    load_options.append(relationship_loader)

                    if _analyzer:
                        _analyzer.record_relationship(field_name)
                        _analyzer.record_load_strategy(field_name, "selectinload")

        deferred_keys: list[str] = []
        for key, attr in all_attributes.items():
            if attr not in requested_attrs:
                load_options.append(defer(attr))
                deferred_keys.append(key)

        if _analyzer and deferred_keys:
            _analyzer.record_deferred(deferred_keys)

        return load_options

    async def optimize_query(
        self,
        model: type[Any],
        node_ids: Iterable[str] | None = None,
        filters: dict[str, Any] | Any | None = None,
        return_selected_fields: bool = False,
        filter_context_user: bool = False,
        apply_access_control: bool = True,
        order: Any = None,
        limit: int | None = None,
        offset: int | None = None,
        return_total_count: bool = False,
        target_field_path: str | None = None,
        strawberry_type: type | None = None,
        exclude_prefetch: set[str] | None = None,
    ) -> QueryResult:
        if filters is not None and filters is not UNSET and not isinstance(filters, dict):
            filters = FilterBuilder().build_filter_dict(filters)
        elif filters is UNSET:
            filters = None

        if self.analyzer:
            self.analyzer.begin(model)

        raw_selected_fields = self.process_selected_fields(self.info.selected_fields[0].selections)

        if target_field_path:
            field_parts = target_field_path.split(".")
            target_fields = raw_selected_fields
            for part in field_parts:
                if isinstance(target_fields, dict) and part in target_fields:
                    target_fields = target_fields[part]
                else:
                    target_fields = {}
                    break
            if target_fields:
                raw_selected_fields = target_fields

        deps = self._resolve_all_dependencies(strawberry_type, raw_selected_fields, model, exclude_prefetch)
        raw_selected_fields = deps.augmented_fields

        if self.analyzer:
            self.analyzer.record_selected_fields(raw_selected_fields, model)

        context_user = None
        if deps.needs_current_user or filter_context_user or apply_access_control:
            context_user = await self._get_identity()

        user_id = None
        if deps.needs_current_user and context_user and hasattr(context_user, "id"):
            user_id = context_user.id

        order_clauses, relationship_configs = self.process_order(model, order)

        skip_rels = {p.relationship for p in deps.filtered_prefetches} if deps.filtered_prefetches else None
        load_options = await self.build_query_with_selected_fields(
            model,
            raw_selected_fields,
            relationship_configs,
            skip_relationships=skip_rels,
            strawberry_type=strawberry_type,
        )

        for prefetch in deps.filtered_prefetches:
            filtered_opt = self._build_filtered_selectinload(model, prefetch, user_id)
            if filtered_opt is not None:
                load_options.append(filtered_opt)
                if self.analyzer:
                    self.analyzer.record_relationship(prefetch.relationship)
                    filter_desc = ""
                    if prefetch.filter_current_user:
                        filter_desc = "current_user"
                    if prefetch.filter:
                        filter_desc += "+custom" if filter_desc else "custom"
                    self.analyzer.record_load_strategy(prefetch.relationship, "selectinload+filter", filter_desc)

        annotation_configs: list[
            tuple[AnnotateExists | AnnotateAnyExists | AnnotateCount | AnnotateCustom | AnnotateAncestry, Any]
        ] = []
        for ann in deps.annotations:
            subq = self._build_annotation_subquery(model, ann, user_id)
            if subq is not None:
                annotation_configs.append((ann, subq))
                if self.analyzer:
                    if isinstance(ann, AnnotateExists):
                        kind = "EXISTS"
                        name = ann.debug_name
                    elif isinstance(ann, AnnotateAnyExists):
                        kind = "ANY_EXISTS"
                        name = ann.debug_name
                    elif isinstance(ann, AnnotateCount):
                        kind = "COUNT"
                        name = ann.debug_name
                    elif isinstance(ann, AnnotateAncestry):
                        kind = "ANCESTRY"
                        name = ann.debug_name
                    elif isinstance(ann, AnnotateCustom):
                        kind = "CUSTOM"
                        name = ann.debug_name
                    else:
                        kind = "UNKNOWN"
                        name = ann.resolved_attr
                    self.analyzer.record_annotation(name, kind)

        query = select(model)

        if apply_access_control:
            query = await self.apply_access_control(query, model)

        if node_ids is not None:
            import uuid as _uuid

            try:
                ids = [_uuid.UUID(nid) for nid in node_ids]
            except (ValueError, AttributeError):
                ids = list(node_ids)
            query = query.where(model.id.in_(ids))

        if filter_context_user:
            query = (
                query.where(model.user_id == context_user.id)
                if context_user and hasattr(context_user, "id")
                else query.where(model.id == -1)
            )

        if filters:
            custom_filters = getattr(strawberry_type, "_custom_filters_registry", {}) if strawberry_type else {}
            builder = FilterBuilder(custom_filters=custom_filters)
            filter_expression = await builder.build_filters(model, filters)

            if filter_expression is not None:
                sorted_paths = sorted(builder.alias_map.keys(), key=lambda p: p.count("."))
                joined_paths: set[str] = set()

                for path in sorted_paths:
                    if path in joined_paths:
                        continue

                    if path in builder._join_paths:
                        join_chain = builder._join_paths[path]
                        current_model = model
                        current_path = ""
                        for i, (rel_name, _rel_model) in enumerate(join_chain):
                            current_path = f"{current_path}.{rel_name}" if current_path else rel_name

                            is_last_segment = i == len(join_chain) - 1
                            actual_alias_key = path if is_last_segment else current_path

                            if actual_alias_key in joined_paths:
                                current_model = builder.alias_map.get(actual_alias_key, current_model)
                                continue

                            rel_attr = getattr(current_model, rel_name)
                            target_alias = builder.alias_map.get(actual_alias_key, _rel_model)
                            query = query.outerjoin(target_alias, rel_attr)
                            joined_paths.add(actual_alias_key)
                            current_model = target_alias
                    else:
                        rel_parts = path.split(".")
                        rel_attr = getattr(model, rel_parts[0])
                        query = query.outerjoin(builder.alias_map[path], rel_attr)
                        joined_paths.add(path)

                query = query.where(filter_expression)

        total_count = 0
        if return_total_count:
            count_query = select(func.count()).select_from(query.subquery())

            if self.analyzer:
                try:
                    compiled_sql = str(
                        count_query.compile(
                            dialect=self.session.bind.dialect,
                            compile_kwargs={"literal_binds": True},
                        )
                    )
                    self.analyzer.record_query("count", compiled_sql)
                except Exception:
                    self.analyzer.record_query("count", "<compilation failed>")

            total_count = await self.session.scalar(count_query) or 0

        query = query.options(*load_options)

        for ann, subq in annotation_configs:
            query = query.add_columns(subq.label(ann.resolved_attr))

        if order_clauses:
            query = query.order_by(*order_clauses)
        else:
            default_ordering = self.get_ordering_attributes(model)
            if default_ordering:
                query = query.order_by(*[attr.desc() for attr in default_ordering])

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        if self.analyzer:
            try:
                compiled_sql = str(
                    query.compile(
                        dialect=self.session.bind.dialect,
                        compile_kwargs={"literal_binds": True},
                    )
                )
                self.analyzer.record_query("data", compiled_sql)
            except Exception:
                self.analyzer.record_query("data", "<compilation failed>")

        result_proxy = await self.session.execute(query)

        if annotation_configs:
            rows = result_proxy.unique().all()
            result: list[Any] = []
            for row in rows:
                instance = row[0]
                instance._optimizer_annotations = {}
                for i, (ann, _) in enumerate(annotation_configs):
                    raw_value = row[i + 1]
                    if isinstance(ann, AnnotateCustom) and ann.mapper is not None:
                        try:
                            raw_value = ann.mapper(raw_value)
                        except Exception:
                            logger.warning(
                                "AnnotateCustom mapper failed for %s",
                                ann.resolved_attr,
                                exc_info=True,
                            )
                    instance._optimizer_annotations[ann.resolved_attr] = raw_value
                result.append(instance)
        else:
            result = list(result_proxy.unique().scalars().all())

        if self.analyzer:
            self.analyzer.record_result(
                count=len(result),
                total_count=total_count if return_total_count else None,
            )
            self.analyzer.end()
            self.analyzer.log_report()

        return QueryResult(
            items=list(result),
            selected_fields=raw_selected_fields if return_selected_fields else {},
            total_count=total_count if return_total_count else 0,
        )

    def _build_ancestry_annotation_subquery(
        self,
        model: type[Any],
        annotation: AnnotateAncestry,
    ) -> Any:
        return None
