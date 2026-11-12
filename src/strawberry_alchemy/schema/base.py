from __future__ import annotations

from typing import Any, Protocol, Self, cast
from uuid import UUID

import strawberry
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import inspect
from sqlalchemy.orm.state import InstanceState
from strawberry.relay import GlobalID


class _FromSchema(Protocol):
    @classmethod
    def from_schema(cls, schema: Any, **kwargs: Any) -> Any: ...


def _is_global_id_like(value: Any) -> bool:
    if isinstance(value, GlobalID):
        return True
    data = getattr(value, "__dict__", None)
    return isinstance(data, dict) and "node_id" in data


def _uuid_from_global_id(value: Any) -> UUID:
    try:
        node_id = value.node_id
    except Exception as error:
        raise ValueError(f"Invalid GlobalID: {value!r}") from error
    if node_id is None:
        raise ValueError(f"Invalid GlobalID: {value!r}")
    try:
        return UUID(str(node_id))
    except (ValueError, TypeError) as error:
        raise ValueError(f"GlobalID node id is not a UUID: {node_id!r}") from error


def _decode_input_value(value: Any) -> Any:
    """Decode a GraphQL input value for schema construction.

    GlobalIDs become UUIDs. ``UNSET`` / ``None`` / existing UUIDs / other scalars
    are left alone (callers omit ``UNSET`` before construct). Lists are mapped
    item-wise so ``list[GlobalID]`` becomes ``list[UUID]``.
    """
    if value is None or value is strawberry.UNSET:
        return value
    if isinstance(value, UUID):
        return value
    if isinstance(value, list):
        return [_decode_input_value(item) for item in value]
    if _is_global_id_like(value):
        return _uuid_from_global_id(value)
    return value


def schema_from_input[BaseModelT: BaseModel](
    model_cls: type[BaseModelT],
    input: Any,  # noqa: A002
    **kwargs: Any,
) -> BaseModelT:
    """Build a Pydantic model from a Strawberry GraphQL input.

    Same-named fields are copied; ``strawberry.UNSET`` fields are omitted so the
    model's defaults apply. ``GlobalID`` values (on the input or in ``kwargs``)
    become ``uuid.UUID``. Explicit ``None`` is preserved. Kwargs win.
    """
    model_fields = model_cls.model_fields
    data: dict[str, Any] = {}

    definition = getattr(input, "__strawberry_definition__", None)
    if definition is not None:
        for field in definition.fields:
            name = field.python_name
            if name not in model_fields:
                continue
            value = getattr(input, name)
            if value is strawberry.UNSET:
                continue
            data[name] = _decode_input_value(value)
    else:
        for name in model_fields:
            if not hasattr(input, name):
                continue
            value = getattr(input, name)
            if value is strawberry.UNSET:
                continue
            data[name] = _decode_input_value(value)

    for key, value in kwargs.items():
        if value is strawberry.UNSET:
            continue
        data[key] = _decode_input_value(value)

    return model_cls(**data)


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    @model_validator(mode="before")
    @classmethod
    def skip_unloaded_relationships(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        if isinstance(data, BaseModel):
            return data
        try:
            state = inspect(data)
            if not isinstance(state, InstanceState):
                return data
        except Exception:
            return data
        return {prop.key: state.dict[prop.key] for prop in state.mapper.iterate_properties if prop.key in state.dict}

    def dump_for_db(self, exclude: set[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        exclude = exclude or set()
        data = self.model_dump(exclude_unset=True, exclude=exclude, **kwargs)
        return {k: v for k, v in data.items() if v is not strawberry.UNSET}

    def to_type[T](self, target_cls: type[T], **kwargs: Any) -> T:
        if hasattr(target_cls, "from_schema"):
            return cast("T", cast("_FromSchema", target_cls).from_schema(self, **kwargs))
        return target_cls(**self.model_dump(exclude_unset=True), **kwargs)

    @classmethod
    def from_input(cls, input: Any, **kwargs: Any) -> Self:  # noqa: A002
        """Build this schema from a Strawberry GraphQL input (see ``schema_from_input``)."""
        return schema_from_input(cls, input, **kwargs)
