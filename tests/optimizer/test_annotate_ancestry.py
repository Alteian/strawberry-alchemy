from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, cast
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import Info  # noqa: TC002

from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.optimizer.prefetch import AnnotateAncestry, optimize_field
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer
from strawberry_alchemy.types.base_node import BaseNodeType
from strawberry_alchemy.types.list_result import ListResult  # noqa: TC001

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def test_annotate_ancestry_resolved_attr_defaults() -> None:
    assert AnnotateAncestry("parent").resolved_attr == "_parent_ancestry"
    assert AnnotateAncestry("folder", to_attr="folder_path").resolved_attr == "folder_path"
    assert AnnotateAncestry("parent").parent_field == "parent_id"
    assert AnnotateAncestry("parent").id_field == "id"
    assert AnnotateAncestry("parent").include_self is True
    assert AnnotateAncestry("parent").root_first is True
    assert AnnotateAncestry("parent").value_mode == "ids"
    assert AnnotateAncestry("parent").cte_name == "ancestry"


class _TestBase(DeclarativeBase):
    pass


class FolderModel(_TestBase):
    __tablename__ = "ancestry_test_folders"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("ancestry_test_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[FolderModel | None] = relationship(
        remote_side="FolderModel.id",
        foreign_keys=[parent_id],
    )


class FolderAccessFilter(AccessControlFilter):
    model_class = FolderModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type
class FolderType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = FolderAccessFilter

    name: str

    @strawberry.field
    @optimize_field(
        AnnotateAncestry(
            "parent",
            value_mode="chain",
            to_attr="_folder_ancestry",
            include_self=True,
            root_first=True,
            cte_name="folder_ancestry",
        )
    )
    def ancestry_path(self) -> str | None:
        return getattr(self, "_folder_ancestry", None)


class GraphQLContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.db_execution_lock = asyncio.Lock()

    async def get_session(self) -> AsyncSession:
        return self._session


@strawberry.type
class Query:
    @strawberry.field
    async def folders(self, info: Info) -> ListResult[FolderType]:
        return await FolderType.resolve_list(info)


@pytest.fixture
async def folder_tree_session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    root_id = uuid4()
    child_id = uuid4()
    leaf_id = uuid4()
    now = datetime.now(tz=UTC)

    async with session_factory() as db:
        db.add_all(
            [
                FolderModel(id=root_id, parent_id=None, name="root", created_at=now, updated_at=now),
                FolderModel(id=child_id, parent_id=root_id, name="child", created_at=now, updated_at=now),
                FolderModel(id=leaf_id, parent_id=child_id, name="leaf", created_at=now, updated_at=now),
            ]
        )
        await db.commit()
        db.info["root_id"] = root_id
        db.info["child_id"] = child_id
        db.info["leaf_id"] = leaf_id
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_annotate_ancestry_chain_self_ref_via_schema(folder_tree_session: AsyncSession) -> None:
    root_id = cast("UUID", folder_tree_session.info["root_id"])
    child_id = cast("UUID", folder_tree_session.info["child_id"])
    leaf_id = cast("UUID", folder_tree_session.info["leaf_id"])

    context = GraphQLContext(folder_tree_session)
    schema = strawberry.Schema(query=Query)

    result = await schema.execute(
        """
        query Folders {
            folders {
                items {
                    name
                    ancestryPath
                }
                totalCount
            }
        }
        """,
        context_value=context,
    )

    assert result.errors is None
    assert result.data is not None
    items = {item["name"]: item["ancestryPath"] for item in result.data["folders"]["items"]}

    def _uuid_token(value: UUID) -> str:
        # SQLite stores UUID PKs as 32-char hex without hyphens.
        return value.hex

    # root_first=True → level DESC: root / child / leaf
    assert items["root"] == _uuid_token(root_id)
    assert items["child"] == f"{_uuid_token(root_id)}/{_uuid_token(child_id)}"
    assert items["leaf"] == f"{_uuid_token(root_id)}/{_uuid_token(child_id)}/{_uuid_token(leaf_id)}"


@pytest.mark.asyncio
async def test_build_ancestry_subquery_returns_none_for_missing_relationship(
    folder_tree_session: AsyncSession,
) -> None:
    optimizer = QueryOptimizer(info=cast("Any", object()), session=folder_tree_session)
    subq = optimizer._build_ancestry_annotation_subquery(
        FolderModel,
        AnnotateAncestry("missing_rel", value_mode="chain"),
    )
    assert subq is None


@pytest.mark.asyncio
async def test_build_ancestry_subquery_sqlite_group_concat_compile(
    folder_tree_session: AsyncSession,
) -> None:
    optimizer = QueryOptimizer(info=cast("Any", object()), session=folder_tree_session)
    subq = optimizer._build_ancestry_annotation_subquery(
        FolderModel,
        AnnotateAncestry("parent", value_mode="chain", cte_name="folder_ancestry"),
    )
    assert subq is not None

    compiled = str(
        select(FolderModel, subq.label("_folder_ancestry")).compile(
            dialect=folder_tree_session.bind.dialect,  # type: ignore[union-attr]
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "group_concat" in compiled.lower()
    assert "folder_ancestry" in compiled.lower()
