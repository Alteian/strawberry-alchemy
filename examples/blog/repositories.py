from __future__ import annotations

from typing import ClassVar

from strawberry_alchemy import BaseRepository

from .models import Comment, Post
from .schemas import CommentSchema, PostSchema


class PostRepository(BaseRepository[Post, PostSchema]):
    model_cls: ClassVar[type[Post]] = Post
    schema_cls: ClassVar[type[PostSchema]] = PostSchema
    relation_models: ClassVar[dict[str, type]] = {"comments": Comment}
    soft_delete_field: ClassVar[str | None] = "deleted_at"


class CommentRepository(BaseRepository[Comment, CommentSchema]):
    model_cls: ClassVar[type[Comment]] = Comment
    schema_cls: ClassVar[type[CommentSchema]] = CommentSchema
