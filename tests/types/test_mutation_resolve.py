"""Mutation payload resolve: acquire_lock=False + target_field_path."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import strawberry
from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from strawberry.types import Info  # noqa: TC002

from strawberry_alchemy import AnnotateCount, optimize_field, resolve_mutation_node
from strawberry_alchemy.filtering.access_control import AccessControlFilter
from strawberry_alchemy.types.base_node import BaseNodeType

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class _TestBase(DeclarativeBase):
    pass


class PostModel(_TestBase):
    __tablename__ = "mutation_resolve_posts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comments: Mapped[list[CommentModel]] = relationship(back_populates="post")


class CommentModel(_TestBase):
    __tablename__ = "mutation_resolve_comments"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    post_id: Mapped[UUID] = mapped_column(ForeignKey("mutation_resolve_posts.id"))
    body: Mapped[str] = mapped_column(String(100))
    post: Mapped[PostModel] = relationship(back_populates="comments")


class PostAccessFilter(AccessControlFilter):
    model_class = PostModel

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar[type[AccessControlFilter]] = PostAccessFilter

    title: str | None = strawberry.UNSET

    @strawberry.field
    @optimize_field(AnnotateCount("comments", to_attr="_comment_count"))
    def comment_count(self) -> int:
        return int(getattr(self, "_comment_count", 0) or 0)


@strawberry.type
class UpdatePostSuccess:
    message: str
    post: PostType


@strawberry.type
class UpdatePostError:
    message: str


UpdatePostPayload = Annotated[
    UpdatePostSuccess | UpdatePostError,
    strawberry.union("UpdatePostPayload"),
]


class GraphQLContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.db_execution_lock = asyncio.Lock()
        self.identity = None

    async def get_session(self) -> AsyncSession:
        return self._session


@strawberry.type
class Query:
    @strawberry.field
    def health(self) -> str:
        return "ok"


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def update_post(
        self,
        info: Info,
        post_id: strawberry.ID,
        title: str,
    ) -> UpdatePostPayload:
        session = await info.context.get_session()
        # Simulate app mutation members that already hold db_execution_lock.
        async with info.context.db_execution_lock:
            post = await session.get(PostModel, UUID(str(post_id)))
            assert post is not None
            post.title = title
            await session.flush()
            node = await resolve_mutation_node(
                info,
                PostType,
                post.id,
                field="post",
            )
            if node is None:
                return UpdatePostError(message="missing")
            return UpdatePostSuccess(message="ok", post=node)


POST_ID = uuid4()


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(_TestBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        now = datetime.now(tz=UTC)
        db.add(
            PostModel(id=POST_ID, title="before", created_at=now, updated_at=now),
        )
        await db.flush()
        db.add_all(
            [
                CommentModel(id=uuid4(), post_id=POST_ID, body="c1"),
                CommentModel(id=uuid4(), post_id=POST_ID, body="c2"),
            ]
        )
        await db.commit()
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_mutation_node_under_held_lock_loads_scalars_and_count(
    session: AsyncSession,
) -> None:
    schema = strawberry.Schema(query=Query, mutation=Mutation)
    context = GraphQLContext(session)

    result = await schema.execute(
        """
        mutation ($postId: ID!, $title: String!) {
          updatePost(postId: $postId, title: $title) {
            __typename
            ... on UpdatePostSuccess {
              message
              post {
                title
                commentCount
              }
            }
            ... on UpdatePostError { message }
          }
        }
        """,
        variable_values={"postId": str(POST_ID), "title": "after"},
        context_value=context,
    )

    assert result.errors is None, result.errors
    assert result.data is not None
    payload = result.data["updatePost"]
    assert payload["__typename"] == "UpdatePostSuccess"
    assert payload["post"]["title"] == "after"
    assert payload["post"]["commentCount"] == 2

    row = (await session.execute(select(PostModel.title).where(PostModel.id == POST_ID))).scalar_one()
    assert row == "after"
