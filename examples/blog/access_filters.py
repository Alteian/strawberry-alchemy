from __future__ import annotations

from typing import Any

from strawberry_alchemy.filtering import AccessControlFilter

from .models import Comment, Post


class PostAccessFilter(AccessControlFilter):
    model_class = Post

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        return query.where(model.user_id == context_user.id)


class CommentAccessFilter(AccessControlFilter):
    model_class = Comment

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        if context_user is None:
            return query.where(False)
        # Comments visible when the parent post is owned by the user.
        return query.join(Post, model.post_id == Post.id).where(Post.user_id == context_user.id)
