import base64
from typing import Any

import strawberry
from strawberry import relay
from strawberry.relay import Edge, PageInfo
from strawberry.relay.utils import from_base64
from strawberry.types import Info

from strawberry_alchemy.mapping import map_sqlalchemy_list_to_types
from strawberry_alchemy.optimizer.query_optimizer import (
    QueryOptimizer,
)


class SliceMetadata:
    def __init__(self, start: int, end: int | None, requested_count: int | None) -> None:
        self.start = start
        self.end = end
        self.requested_count = requested_count

    @property
    def fetch_limit(self) -> int | None:
        if self.requested_count is not None:
            return self.requested_count + 1
        return None

    @classmethod
    def from_arguments(
        cls,
        info: Info,
        before: str | None = None,
        after: str | None = None,
        first: int | None = None,
        last: int | None = None,
        max_results: int | None = None,
    ) -> "SliceMetadata":
        max_results = max_results or info.schema.config.relay_max_results
        start = 0
        end: int | None = None
        requested_count: int | None = None

        if after:
            _, after_parsed = from_base64(after)
            start = int(after_parsed) + 1

        if before:
            _, before_parsed = from_base64(before)
            end = int(before_parsed)

        if first is not None:
            if first < 0:
                raise ValueError("Argument 'first' must be a non-negative integer.")
            if first > max_results:
                raise ValueError(f"Argument 'first' cannot be higher than {max_results}.")
            requested_count = first
            if end is not None:
                start = max(start, end - first)
            else:
                end = start + first
        elif last is not None:
            if last < 0:
                raise ValueError("Argument 'last' must be a non-negative integer.")
            if last > max_results:
                raise ValueError(f"Argument 'last' cannot be higher than {max_results}.")
            requested_count = last
            start = max(start, end - last) if end is not None else None

        if end is None and requested_count is None:
            end = start + max_results

        return cls(start=start, end=end, requested_count=requested_count)


@strawberry.type
class OptimizedListConnection[NodeType](relay.Connection[NodeType]):
    edges: list[Edge[NodeType]]
    page_info: PageInfo
    total_count: int

    @classmethod
    async def resolve_connection(
        cls,
        optimizer: QueryOptimizer,
        model: type[Any],
        graphql_type: type[Any],
        info: Info,
        filters: dict[str, Any] | Any | None = None,
        order: Any = None,
        after: str | None = None,
        before: str | None = None,
        first: int | None = None,
        last: int | None = None,
        return_total_count: bool = False,
        strawberry_type: type | None = None,
        exclude_prefetch: set[str] | None = None,
    ) -> "OptimizedListConnection[NodeType]":
        slice_metadata = SliceMetadata.from_arguments(
            info=info,
            before=before,
            after=after,
            first=first,
            last=last,
        )

        total_count: int | None = None

        if last is not None and slice_metadata.start is None:
            count_result = await optimizer.optimize_query(
                model=model,
                filters=filters,
                return_total_count=True,
                strawberry_type=strawberry_type,
                exclude_prefetch=exclude_prefetch,
            )
            total_count = count_result.total_count

            if total_count > 0:
                slice_metadata.start = max(0, total_count - last)
                slice_metadata.end = total_count
            else:
                slice_metadata.start = 0
                slice_metadata.end = 0

        if slice_metadata.start is None:
            slice_metadata.start = 0

        fetch_limit = slice_metadata.fetch_limit
        query_result = await optimizer.optimize_query(
            model=model,
            filters=filters,
            order=order,
            offset=slice_metadata.start,
            limit=fetch_limit,
            return_selected_fields=True,
            return_total_count=return_total_count or (last is not None and before is None),
            strawberry_type=strawberry_type,
            exclude_prefetch=exclude_prefetch,
        )
        instances = query_result.items
        total_count = query_result.total_count

        instance_types = await map_sqlalchemy_list_to_types(
            query_result.items,
            info,
            graphql_type,
            query_result.selected_fields,
        )

        if slice_metadata.requested_count is not None and len(instance_types) > slice_metadata.requested_count:
            if last is not None:
                instance_types = instance_types[-slice_metadata.requested_count :]
            else:
                instance_types = instance_types[: slice_metadata.requested_count]

        edges = [
            Edge(
                node=item,
                cursor=base64.b64encode(
                    f"arrayconnection:{idx + slice_metadata.start}".encode(),
                ).decode(),
            )
            for idx, item in enumerate(instance_types)
        ]

        has_next_page = len(instances) > len(edges) if slice_metadata.requested_count else False
        has_previous_page = slice_metadata.start > 0

        page_info = PageInfo(
            has_next_page=has_next_page,
            has_previous_page=has_previous_page,
            start_cursor=edges[0].cursor if edges else None,
            end_cursor=edges[-1].cursor if edges else None,
        )

        return cls(
            edges=edges,
            page_info=page_info,
            total_count=total_count if return_total_count else len(instances),
        )
