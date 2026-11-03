from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from strawberry.types import Info  # noqa: TC002

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.types.base_node import BaseNodeType
from strawberry_alchemy.types.connection import OptimizedListConnection  # noqa: TC001
from strawberry_alchemy.types.list_result import ListResult  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _TestBase(DeclarativeBase):
    pass


class NoteModel(_TestBase):
    __tablename__ = "acl_override_notes"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column()
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class NoteAccessFilter(AccessControlFilter):
    model_class = NoteModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.owner_id == context_user.id)


class OpenNoteAccessFilter(AccessControlFilter):
    """Per-call override that intentionally returns every row."""

    model_class = NoteModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type
class NoteType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = NoteAccessFilter

    owner_id: UUID | None = strawberry.UNSET
    title: str | None = strawberry.UNSET


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


@strawberry.type
class Query:
    @strawberry.field
    async def notes(self, info: Info) -> ListResult[NoteType]:
        return await NoteType.resolve_list(info)

    @strawberry.field
    async def notes_open(self, info: Info) -> ListResult[NoteType]:
        return await NoteType.resolve_list(info, access_filter=OpenNoteAccessFilter)

    @strawberry.field
    async def notes_connection(
        self,
        info: Info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> OptimizedListConnection[NoteType]:
        return await NoteType.resolve_connection(
            info,
            first=first,
            after=after,
            last=last,
            before=before,
            return_total_count=True,
        )

    @strawberry.field
    async def notes_connection_open(
        self,
        info: Info,
        first: int | None = None,
        after: str | None = None,
        last: int | None = None,
        before: str | None = None,
    ) -> OptimizedListConnection[NoteType]:
        return await NoteType.resolve_connection(
            info,
            first=first,
            after=after,
            last=last,
            before=before,
            return_total_count=True,
            access_filter=OpenNoteAccessFilter,
        )

    @strawberry.field
    async def note(self, info: Info, note_id: strawberry.ID) -> NoteType | None:
        return await NoteType.resolve_node(str(note_id), info=info)

    @strawberry.field
    async def note_open(self, info: Info, note_id: strawberry.ID) -> NoteType | None:
        return await NoteType.resolve_node(str(note_id), info=info, access_filter=OpenNoteAccessFilter)


# GraphQL fields above take the raw UUID string (not a Relay GlobalID).


OWNER_A = uuid4()
OWNER_B = uuid4()
NOTE_B_ID = uuid4()


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        db.add_all(
            [
                NoteModel(id=uuid4(), owner_id=OWNER_A, title="a1", created_at=now, updated_at=now),
                NoteModel(id=uuid4(), owner_id=OWNER_A, title="a2", created_at=now, updated_at=now),
                NoteModel(id=NOTE_B_ID, owner_id=OWNER_B, title="b1", created_at=now, updated_at=now),
            ]
        )
        await db.commit()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_list_applies_classvar_access_filter_to_items_and_total_count(
    session: AsyncSession,
) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    result = await schema.execute(
        """
        query {
          notes {
            items { title }
            totalCount
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    notes = result.data["notes"]
    assert sorted(item["title"] for item in notes["items"]) == ["a1", "a2"]
    assert notes["totalCount"] == 2


@pytest.mark.asyncio
async def test_resolve_list_per_call_access_filter_override(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    result = await schema.execute(
        """
        query {
          notesOpen {
            items { title }
            totalCount
          }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    notes = result.data["notesOpen"]
    assert sorted(item["title"] for item in notes["items"]) == ["a1", "a2", "b1"]
    assert notes["totalCount"] == 3


@pytest.mark.asyncio
async def test_resolve_connection_access_filter_and_override(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))

    scoped = await schema.execute(
        """
        query {
          notesConnection(first: 10) {
            totalCount
            edges { node { title } }
          }
        }
        """,
        context_value=context,
    )
    assert scoped.errors is None
    assert scoped.data is not None
    assert scoped.data["notesConnection"]["totalCount"] == 2
    assert sorted(e["node"]["title"] for e in scoped.data["notesConnection"]["edges"]) == ["a1", "a2"]

    opened = await schema.execute(
        """
        query {
          notesConnectionOpen(first: 10) {
            totalCount
            edges { node { title } }
          }
        }
        """,
        context_value=context,
    )
    assert opened.errors is None
    assert opened.data is not None
    assert opened.data["notesConnectionOpen"]["totalCount"] == 3
    assert sorted(e["node"]["title"] for e in opened.data["notesConnectionOpen"]["edges"]) == [
        "a1",
        "a2",
        "b1",
    ]


@pytest.mark.asyncio
async def test_resolve_node_per_call_override(session: AsyncSession) -> None:
    schema = strawberry.Schema(query=Query)
    context = GraphQLContext(session, identity=_User(OWNER_A))
    note_id = str(NOTE_B_ID)

    hidden = await schema.execute(
        """
        query ($noteId: ID!) {
          note(noteId: $noteId) { title }
        }
        """,
        variable_values={"noteId": note_id},
        context_value=context,
    )
    assert hidden.errors is None
    assert hidden.data is not None
    assert hidden.data["note"] is None

    opened = await schema.execute(
        """
        query ($noteId: ID!) {
          noteOpen(noteId: $noteId) { title }
        }
        """,
        variable_values={"noteId": note_id},
        context_value=context,
    )
    assert opened.errors is None
    assert opened.data is not None
    assert opened.data["noteOpen"] == {"title": "b1"}
