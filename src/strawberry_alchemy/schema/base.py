from typing import Any

import strawberry
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import inspect
from sqlalchemy.orm.state import InstanceState


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
            return target_cls.from_schema(self, **kwargs)
        return target_cls(**self.model_dump(exclude_unset=True), **kwargs)
