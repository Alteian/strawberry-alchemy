from typing import Any, ClassVar, cast
from uuid import UUID, uuid4

import strawberry
from sqlalchemy import String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.optimizer.prefetch import SelectColumns, get_prefetch_map, optimize_field
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer
from strawberry_alchemy.types.base_node import BaseNodeType


class _TestBase(DeclarativeBase):
    pass


class ImageModel(_TestBase):
    __tablename__ = "select_columns_images"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    variants: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position: Mapped[int] = mapped_column(default=1)


class ImageAccessFilter(AccessControlFilter):
    model_class = ImageModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type(name="ImageType")
class ImageType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = ImageAccessFilter
    model_class: ClassVar[type[ImageModel]] = ImageModel

    s3_key: str = strawberry.UNSET
    variants: str | None = None
    position: int = strawberry.UNSET

    @strawberry.field
    @optimize_field(SelectColumns("s3_key", "variants", "position"))
    def thumb_url(self) -> str | None:
        key = None if self.s3_key is strawberry.UNSET else self.s3_key
        return f"https://cdn.example/{key}" if key else None


def test_select_columns_registered_on_field() -> None:
    prefetch_map = get_prefetch_map(ImageType)
    assert "thumb_url" in prefetch_map
    hints = prefetch_map["thumb_url"]
    assert len(hints) == 1
    assert isinstance(hints[0], SelectColumns)
    assert hints[0].fields == ("s3_key", "variants", "position")


def test_select_columns_augments_selected_fields() -> None:
    optimizer = QueryOptimizer(info=cast("Any", object()), session=cast("Any", object()))
    deps = optimizer._resolve_all_dependencies(
        ImageType,
        {"thumb_url": True},
        ImageModel,
    )
    assert deps.augmented_fields["thumb_url"] is True
    assert deps.augmented_fields["s3_key"] is True
    assert deps.augmented_fields["variants"] is True
    assert deps.augmented_fields["position"] is True
