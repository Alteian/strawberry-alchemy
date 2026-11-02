from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from strawberry_alchemy.repository import BaseDeletionHandler, DependentMap

from .models import Comment, Post


class PostDeletionHandler(BaseDeletionHandler[Post]):
    async def collect_dependents(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        instance: Post,
    ) -> DependentMap:
        rows = (
            await session.execute(select(Comment.id).where(Comment.post_id == entity_id))
        ).scalars().all()
        return {"comments": list(rows)}

    async def handle_cascade(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        dependents: DependentMap,
    ) -> None:
        comment_ids = dependents.get("comments") or []
        if comment_ids:
            await session.execute(delete(Comment).where(Comment.id.in_(comment_ids)))
