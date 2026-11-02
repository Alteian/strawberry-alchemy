from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from examples.blog.deletion import PostDeletionHandler
from examples.blog.filters import PostFilter
from examples.blog.models import Comment, ExampleBase, Post
from examples.blog.repositories import PostRepository
from examples.blog.schemas import CommentSchema, PostSchema
from examples.blog.types import PostType
from strawberry_alchemy.filtering import FilterBuilder, StringFilter


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ExampleBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_create_with_nested_comments(session: AsyncSession) -> None:
    user_id = uuid4()
    repo = PostRepository(session)
    created = await repo.create(
        PostSchema(
            user_id=user_id,
            title="Hello",
            body="World",
            comments=[CommentSchema(body="Nice")],
        )
    )
    assert created.id is not None
    assert created.title == "Hello"

    comments = (await session.execute(select(Comment).where(Comment.post_id == created.id))).scalars().all()
    assert len(comments) == 1
    assert comments[0].body == "Nice"


@pytest.mark.asyncio
async def test_deletion_handler_cascades_comments(session: AsyncSession) -> None:
    user_id = uuid4()
    repo = PostRepository(session, deletion_handler=PostDeletionHandler())
    created = await repo.create(
        PostSchema(
            user_id=user_id,
            title="Bye",
            body="Soon",
            comments=[CommentSchema(body="c1"), CommentSchema(body="c2")],
        )
    )
    assert created.id is not None
    await repo.delete(id=created.id)

    assert (await session.get(Post, created.id)) is None
    leftover = (await session.execute(select(Comment))).scalars().all()
    assert leftover == []


@pytest.mark.asyncio
async def test_or_filter_multi_field_branch(session: AsyncSession) -> None:
    builder = FilterBuilder(custom_filters={Post: dict(PostType.CUSTOM_FILTERS)})
    filt = PostFilter(
        OR=[
            PostFilter(title=StringFilter(exact="Alpha"), body=StringFilter(contains="x")),
            PostFilter(title_search="beta"),
        ]
    )
    data = builder.build_filter_dict(filt)
    expr = await builder.build_filters(Post, data)
    assert expr is not None
    sql = str(expr.compile(compile_kwargs={"literal_binds": True}))
    assert " OR " in sql


def test_post_type_wires_custom_filters_registry() -> None:
    assert Post in PostType._custom_filters_registry
    assert "title_search" in PostType._custom_filters_registry[Post]
