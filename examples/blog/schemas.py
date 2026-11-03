from __future__ import annotations

import uuid
from datetime import datetime

from strawberry_alchemy.schema import BaseSchema


class CommentSchema(BaseSchema):
    id: uuid.UUID | None = None
    post_id: uuid.UUID | None = None
    body: str


class PostSchema(BaseSchema):
    id: uuid.UUID | None = None
    user_id: uuid.UUID
    title: str
    body: str
    deleted_at: datetime | None = None
    comments: list[CommentSchema] | None = None
