import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

type DependentMap = dict[str, list[uuid.UUID]]


class BaseDeletionHandler[ModelT]:
    async def collect_dependents(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        instance: ModelT,
    ) -> DependentMap:
        return {}

    async def pre_delete(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        instance: ModelT,
        dependents: DependentMap,
    ) -> None:
        pass

    async def cleanup_external(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        instance: ModelT,
        dependents: DependentMap,
    ) -> None:
        pass

    async def handle_cascade(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        dependents: DependentMap,
    ) -> None:
        pass

    async def post_delete(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        dependents: DependentMap,
    ) -> None:
        pass
