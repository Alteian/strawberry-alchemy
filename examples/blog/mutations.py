from __future__ import annotations

import uuid

import strawberry
from strawberry.relay import GlobalID
from strawberry.types import Info

from strawberry_alchemy.permissions import IsAuthenticated, OwnerPermission, prepare_mutation_resources

from .deletion import PostDeletionHandler
from .repositories import PostRepository
from .schemas import PostSchema
from .types import PostType


@strawberry.input
class CreatePostInput:
    title: str
    body: str


@strawberry.input
class UpdatePostInput:
    id: GlobalID
    title: str
    body: str


@strawberry.input
class DeletePostInput:
    id: GlobalID


@strawberry.type
class PostMutations:
    @strawberry.mutation
    async def create_post(self, info: Info, input: CreatePostInput) -> PostType:
        session = await info.context.get_session()
        user = await info.context.identity
        schema = PostSchema(title=input.title, body=input.body, user_id=user.id)
        created = await PostRepository(session).create(schema=schema)
        return created.to_type(PostType)

    @strawberry.mutation
    async def update_post(self, info: Info, input: UpdatePostInput) -> PostType:
        session = await info.context.get_session()
        schema = PostSchema(
            id=uuid.UUID(input.id.node_id),
            title=input.title,
            body=input.body,
            user_id=(await info.context.identity).id,
        )
        result = await PostRepository(session).update(schema=schema)
        return result.to_type(PostType)

    @strawberry.mutation
    async def delete_post(self, info: Info, input: DeletePostInput) -> bool:
        session = await info.context.get_session()
        repo = PostRepository(session, deletion_handler=PostDeletionHandler())
        await prepare_mutation_resources(
            info,
            {"post_id": input.id},
            loaders={"post_id": lambda value: repo.get_by_id(value)},
            permissions=[
                IsAuthenticated(),
                OwnerPermission(owner_field="user_id", resource_key="post_id"),
            ],
        )
        report = await repo.delete(id=uuid.UUID(input.id.node_id), strict=False)
        return not report.has_failures


@strawberry.type
class Mutation:
    @strawberry.field
    def posts(self) -> PostMutations:
        return PostMutations()
