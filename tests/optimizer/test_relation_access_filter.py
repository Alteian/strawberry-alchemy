"""Per-relationship ACL override (RelationAccessFilter / PrefetchRelated.access_filter)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import Info  # noqa: TC002

from strawberry_alchemy.filtering.access_control import AccessControlFilter, RelationAccessFilter
from strawberry_alchemy.optimizer.prefetch import PrefetchRelated, optimize_field
from strawberry_alchemy.types.base_node import BaseNodeType
from strawberry_alchemy.types.list_result import ListResult  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _TestBase(DeclarativeBase):
    pass


class Employee(_TestBase):
    __tablename__ = "relation_acl_employees"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(100))
    manager_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("relation_acl_employees.id"),
        nullable=True,
    )
    buddy_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("relation_acl_employees.id"),
        nullable=True,
    )
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    manager: Mapped[Employee | None] = relationship(
        remote_side="Employee.id",
        foreign_keys=[manager_id],
    )
    buddy: Mapped[Employee | None] = relationship(
        remote_side="Employee.id",
        foreign_keys=[buddy_id],
    )


class EmployeeAccessFilter(AccessControlFilter):
    """Strict: only own rows (SEC-020 analogue)."""

    model_class = Employee

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.owner_id == context_user.id)


class ReportingLineEmployeeAccessFilter(AccessControlFilter):
    """Loose: any row (company RLS analogue — no owner narrowing)."""

    model_class = Employee

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query


@strawberry.type
class EmployeeType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = EmployeeAccessFilter

    owner_id: UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET
    manager_id: UUID | None = strawberry.UNSET
    buddy_id: UUID | None = strawberry.UNSET

    # Sibling edge: same related model, ClassVar ACL (owner-scoped) — must stay strict.
    buddy: EmployeeType | None = strawberry.UNSET

    # Reporting-line edge: same related model, looser ACL via RelationAccessFilter.
    manager: EmployeeType | None = strawberry.field(
        default=strawberry.UNSET,
        extensions=[
            RelationAccessFilter(
                ReportingLineEmployeeAccessFilter,
                foreign_key="manager_id",
            )
        ],
    )

    @strawberry.field
    @optimize_field(
        PrefetchRelated(
            "manager",
            fields=["id", "title", "owner_id"],
            access_filter=ReportingLineEmployeeAccessFilter,
        )
    )
    async def manager_title_via_prefetch(self) -> str | None:
        manager = getattr(self, "manager", None)
        if manager is None or manager is strawberry.UNSET:
            return None
        return getattr(manager, "title", None)


class _User:
    def __init__(self, user_id: UUID) -> None:
        self.id = user_id


class GraphQLContext:
    def __init__(self, session: AsyncSession, identity: Any = None) -> None:
        self._session = session
        self.identity = identity
        self.db_execution_lock = asyncio.Lock()

    async def get_session(self) -> AsyncSession:
        return self._session


OWNER_A = uuid4()
OWNER_B = uuid4()
EMP_A_ID = uuid4()
MANAGER_B_ID = uuid4()
BUDDY_B2_ID = uuid4()


@strawberry.type
class Query:
    @strawberry.field
    async def employees(self, info: Info) -> ListResult[EmployeeType]:
        return await EmployeeType.resolve_list(info)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        manager_b = Employee(
            id=MANAGER_B_ID,
            owner_id=OWNER_B,
            title="manager-b",
            created_at=now,
            updated_at=now,
        )
        buddy_b2 = Employee(
            id=BUDDY_B2_ID,
            owner_id=OWNER_B,
            title="buddy-b2",
            created_at=now,
            updated_at=now,
        )
        emp_a = Employee(
            id=EMP_A_ID,
            owner_id=OWNER_A,
            title="emp-a",
            manager_id=MANAGER_B_ID,
            buddy_id=BUDDY_B2_ID,
            created_at=now,
            updated_at=now,
        )
        db.add_all([manager_b, buddy_b2, emp_a])
        await db.commit()
        db.expire_all()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_relation_access_filter_loads_manager_outside_owner_scope(
    session: AsyncSession,
) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    result = await schema.execute(
        """
        query {
          employees {
            items {
              title
              manager { title }
            }
            totalCount
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    items = result.data["employees"]["items"]
    assert len(items) == 1
    assert items[0]["title"] == "emp-a"
    assert items[0]["manager"] == {"title": "manager-b"}


@pytest.mark.asyncio
async def test_sibling_edge_still_uses_classvar_acl(session: AsyncSession) -> None:
    """buddy uses ClassVar EmployeeAccessFilter — OWNER_B buddy must not load for OWNER_A."""
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    result = await schema.execute(
        """
        query {
          employees {
            items {
              title
              buddy { title }
              manager { title }
            }
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    item = result.data["employees"]["items"][0]
    assert item["title"] == "emp-a"
    assert item["buddy"] is None
    assert item["manager"] == {"title": "manager-b"}


@pytest.mark.asyncio
async def test_foreign_key_fallback_when_relation_not_mapped(session: AsyncSession) -> None:
    """Mutation-style to_type path: FK set, relationship attribute None → resolve via FK."""
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    # Build a GraphQL instance as to_type would (scalars only, no nested manager).
    emp = EmployeeType(
        id=EMP_A_ID,
        created_at=None,
        updated_at=None,
        owner_id=OWNER_A,
        title="emp-a",
        manager_id=MANAGER_B_ID,
        buddy_id=None,
        manager=None,
        buddy=None,
    )

    @strawberry.type
    class Root:
        @strawberry.field
        def employee(self) -> EmployeeType:
            return emp

    schema = strawberry.Schema(query=Root)
    result = await schema.execute(
        """
        query {
          employee {
            title
            manager { title }
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    assert result.data["employee"]["title"] == "emp-a"
    assert result.data["employee"]["manager"] == {"title": "manager-b"}


@pytest.mark.asyncio
async def test_prefetch_related_access_filter(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    result = await schema.execute(
        """
        query {
          employees {
            items {
              title
              managerTitleViaPrefetch
            }
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    item = result.data["employees"]["items"][0]
    assert item["title"] == "emp-a"
    assert item["managerTitleViaPrefetch"] == "manager-b"
