from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from strawberry.types import Info  # noqa: TC002
from strawberry.types.nodes import FragmentSpread, InlineFragment, SelectedField

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer
from strawberry_alchemy.types.base_node import BaseNodeType
from strawberry_alchemy.types.list_result import ListResult  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _leaf(name: str, *, alias: str | None = None) -> SelectedField:
    return SelectedField(name=name, directives={}, arguments={}, selections=[], alias=alias)


def _nested(name: str, *selections: SelectedField) -> SelectedField:
    return SelectedField(name=name, directives={}, arguments={}, selections=list(selections))


@pytest.fixture
def optimizer() -> QueryOptimizer:
    return QueryOptimizer(info=cast("Any", object()), session=cast("Any", object()))


def test_process_selected_fields_plain_fields(optimizer: QueryOptimizer) -> None:
    selections = [_leaf("firstName"), _leaf("lastName")]
    assert optimizer.process_selected_fields(selections) == {
        "first_name": True,
        "last_name": True,
    }


def test_process_selected_fields_fragment_spread(optimizer: QueryOptimizer) -> None:
    fragment = FragmentSpread(
        name="UserFields",
        type_condition="UserType",
        directives={},
        selections=[_leaf("name"), _leaf("city")],
    )

    assert optimizer.process_selected_fields([fragment]) == {
        "name": True,
        "city": True,
    }


def test_process_selected_fields_inline_fragment(optimizer: QueryOptimizer) -> None:
    inline_fragment = InlineFragment(
        type_condition="UserType",
        selections=[_leaf("name"), _leaf("city")],
        directives={},
    )

    assert optimizer.process_selected_fields([inline_fragment]) == {
        "name": True,
        "city": True,
    }


def test_process_selected_fields_mixed_selection(optimizer: QueryOptimizer) -> None:
    fragment = FragmentSpread(
        name="UserFields",
        type_condition="UserType",
        directives={},
        selections=[_leaf("city")],
    )
    selections = [_leaf("name"), fragment]

    assert optimizer.process_selected_fields(selections) == {
        "name": True,
        "city": True,
    }


def test_process_selected_fields_nested_fields_in_fragment(optimizer: QueryOptimizer) -> None:
    fragment = FragmentSpread(
        name="UserFields",
        type_condition="UserType",
        directives={},
        selections=[_leaf("name"), _nested("address", _leaf("city"), _leaf("zipCode"))],
    )

    assert optimizer.process_selected_fields([fragment]) == {
        "name": True,
        "address": {"city": True, "zip_code": True},
    }


class _TestBase(DeclarativeBase):
    pass


class CityModel(_TestBase):
    __tablename__ = "fragment_test_cities"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CityAccessFilter(AccessControlFilter):
    model_class = CityModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type
class CityType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = CityAccessFilter

    name: str
    city: str


class GraphQLContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.db_execution_lock = asyncio.Lock()

    async def get_session(self) -> AsyncSession:
        return self._session


@strawberry.type
class Query:
    @strawberry.field
    async def cities(self, info: Info) -> ListResult[CityType]:
        return await CityType.resolve_list(info)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        db.add(
            CityModel(
                id=uuid4(),
                name="Alice",
                city="Prague",
                created_at=now,
                updated_at=now,
            )
        )
        await db.commit()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_optimize_query_with_fragment_spread(session: AsyncSession) -> None:
    context = GraphQLContext(session)
    schema = strawberry.Schema(query=Query)

    query = """
        fragment CityFields on CityType {
            name
            city
        }

        query Cities {
            cities {
                items {
                    ...CityFields
                }
                totalCount
            }
        }
    """

    result = await schema.execute(
        query,
        context_value=context,
    )

    assert result.errors is None
    assert result.data == {
        "cities": {
            "items": [{"name": "Alice", "city": "Prague"}],
            "totalCount": 1,
        }
    }
