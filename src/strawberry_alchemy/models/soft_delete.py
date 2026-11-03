"""Optional mixin for models that support repository soft-delete."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


class SoftDeleteMixin:
    """Add ``deleted_at`` to a model and set ``Repository.soft_delete_field = \"deleted_at\"``."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=True,
    )
