from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ExampleUser:
    id: UUID
    role: str = "user"


@dataclass
class ExampleContext:
    """Minimal context matching the library contract used by BaseNodeType."""

    session: AsyncSession
    user: ExampleUser | None
    db_execution_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def get_session(self) -> AsyncSession:
        return self.session

    @property
    def identity(self) -> Any:
        async def _identity() -> ExampleUser | None:
            return self.user

        return _identity()
