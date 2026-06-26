import uuid  # noqa: TC003
from collections.abc import Iterable
from datetime import datetime  # noqa: TC003
from typing import Any, ClassVar, Self

import strawberry
from strawberry.relay import Node, NodeID
from strawberry.types import Info

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.mapping import map_sqlalchemy_list_to_types
from strawberry_alchemy.mapping.output_normalization import (
    enrich_mapping_from_schema,
    get_type_init_params,
    normalize_unset_scalars_on_instance,
    prepare_output_constructor_data,
)
from strawberry_alchemy.optimizer import QueryOptimizer

from .connection import OptimizedListConnection
from .list_result import ListResult


@strawberry.type
class BaseNodeType(Node):
    id: NodeID[uuid.UUID]
    created_at: datetime | None = strawberry.UNSET
    updated_at: datetime | None = strawberry.UNSET

    access_filter: ClassVar[type[AccessControlFilter]]
    model_class: ClassVar[type[Any]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not hasattr(cls, "access_filter"):
            raise NotImplementedError(f"Subclass '{cls.__name__}' must define an 'access_filter' ClassVar.")
        cls.model_class = cls.access_filter.model_class

    def __post_init__(self) -> None:
        normalize_unset_scalars_on_instance(self, type(self))

    @classmethod
    def from_schema(cls, schema: Any, **kwargs: Any) -> Self:
        init_params = get_type_init_params(cls)

        exclude = kwargs.pop("exclude", None)
        schema_data = schema.model_dump(exclude_unset=True, exclude=exclude)
        mapped_data = {k: v for k, v in schema_data.items() if k in init_params}
        mapped_data.update(kwargs)
        enrich_mapping_from_schema(schema, mapped_data, init_params)
        mapped_data = prepare_output_constructor_data(
            cls,
            mapped_data,
            init_params=init_params,
        )
        instance = cls(**mapped_data)
        return instance

    @classmethod
    async def _get_optimized_result(cls, info: Info, **query_kwargs: Any) -> Any:
        session = await info.context.get_session()
        optimizer = QueryOptimizer(info, session)
        optimizer.register_access_filter(cls.model_class, cls.access_filter)

        async with info.context.db_execution_lock:
            return await optimizer.optimize_query(model=cls.model_class, strawberry_type=cls, **query_kwargs)

    @classmethod
    async def resolve_node(cls, node_id: str, *, info: Info) -> Self | None:
        resolved = await cls.resolve_nodes(info=info, node_ids=[node_id])
        return resolved[0] if resolved else None

    @classmethod
    async def resolve_nodes(cls, info: Info, node_ids: Iterable[str], **kwargs: Any) -> list[Self | None]:
        result = await cls._get_optimized_result(info, node_ids=node_ids, return_selected_fields=True, **kwargs)
        return await map_sqlalchemy_list_to_types(result.items, info, cls, result.selected_fields)

    @classmethod
    async def resolve_list(cls, info: Info, filters: Any = strawberry.UNSET, **kwargs: Any) -> ListResult[Self]:
        result = await cls._get_optimized_result(
            info,
            filters=filters,
            return_total_count=True,
            return_selected_fields=True,
            **kwargs,
        )
        types = await map_sqlalchemy_list_to_types(result.items, info, cls, result.selected_fields)
        return ListResult(items=types, total_count=result.total_count)

    @classmethod
    async def resolve_connection(cls, info: Info, **kwargs: Any) -> OptimizedListConnection[Self]:
        session = await info.context.get_session()
        optimizer = QueryOptimizer(info, session)
        optimizer.register_access_filter(cls.model_class, cls.access_filter)
        return await OptimizedListConnection.resolve_connection(
            optimizer=optimizer,
            model=cls.model_class,
            graphql_type=cls,
            info=info,
            strawberry_type=cls,
            **kwargs,
        )
