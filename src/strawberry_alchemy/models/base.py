import re
import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    __abstract__ = True

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        return re.sub("(?!^)([A-Z][a-z]+)", r"_\\1", cls.__name__).lower()

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
