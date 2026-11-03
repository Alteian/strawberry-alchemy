from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

type DependentMap = dict[str, list[uuid.UUID]]


@dataclass(slots=True)
class DeletionFailure:
    component: str
    operation: str
    target: str
    error: str

    def __str__(self) -> str:
        return f"[{self.component}] {self.operation} on {self.target}: {self.error}"


@dataclass(slots=True)
class DeletionReport:
    entity_id: uuid.UUID | None = None
    failures: list[DeletionFailure] = field(default_factory=list)

    def record(self, component: str, operation: str, target: object, error: object) -> None:
        failure = DeletionFailure(
            component=component,
            operation=operation,
            target=str(target),
            error=str(error),
        )
        self.failures.append(failure)
        logger.warning("Deletion cleanup failure: %s", failure)

    def extend(self, other: DeletionReport) -> None:
        self.failures.extend(other.failures)

    @property
    def has_failures(self) -> bool:
        return bool(self.failures)

    def summary(self) -> str:
        if not self.failures:
            return "no failures"
        by_component: dict[str, int] = {}
        for failure in self.failures:
            by_component[failure.component] = by_component.get(failure.component, 0) + 1
        parts = ", ".join(f"{component}={count}" for component, count in sorted(by_component.items()))
        return f"{len(self.failures)} failure(s): {parts}"


class DeletionPartialFailure(RuntimeError):  # noqa: N818
    def __init__(self, report: DeletionReport) -> None:
        self.report = report
        super().__init__(f"Deletion completed with errors ({report.summary()})")


class BaseDeletionHandler[ModelT]:
    def __init__(self) -> None:
        self._report: DeletionReport | None = None

    @property
    def report(self) -> DeletionReport:
        # Tolerate subclasses that override ``__init__`` without calling super().
        report = getattr(self, "_report", None)
        if report is None:
            report = DeletionReport()
            self._report = report
        return report

    def reset_report(self, entity_id: uuid.UUID | None = None) -> DeletionReport:
        report = DeletionReport(entity_id=entity_id)
        self._report = report
        return report

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
