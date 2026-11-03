from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("query_analyzer")


@dataclass
class QueryEvent:
    label: str
    sql: str
    params: dict[str, Any] | None = None
    duration_ms: float = 0.0
    row_count: int = 0


@dataclass
class LoadStrategyEvent:
    relationship: str
    strategy: str
    filter_desc: str = ""


@dataclass
class QueryReport:
    model_name: str = ""
    total_duration_ms: float = 0.0
    query_count: int = 0
    queries: list[QueryEvent] = field(default_factory=list)

    requested_fields: list[str] = field(default_factory=list)
    deferred_fields: list[str] = field(default_factory=list)
    relationships_loaded: list[str] = field(default_factory=list)
    annotations: list[str] = field(default_factory=list)

    load_strategies: list[LoadStrategyEvent] = field(default_factory=list)

    warnings: list[str] = field(default_factory=list)

    result_count: int = 0
    total_count: int | None = None

    def summary(self) -> str:
        parts = [
            f"model={self.model_name}",
            f"queries={self.query_count}",
            f"rows={self.result_count}",
            f"fields={len(self.requested_fields)}",
            f"deferred={len(self.deferred_fields)}",
            f"rels={len(self.relationships_loaded)}",
            f"annotations={len(self.annotations)}",
            f"duration={self.total_duration_ms:.1f}ms",
        ]
        if self.warnings:
            parts.append(f"warnings={len(self.warnings)}")
        return " | ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model_name,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "query_count": self.query_count,
            "result_count": self.result_count,
            "total_count": self.total_count,
            "requested_fields": self.requested_fields,
            "deferred_fields": self.deferred_fields,
            "relationships_loaded": self.relationships_loaded,
            "annotations": self.annotations,
            "load_strategies": [
                {
                    "relationship": ls.relationship,
                    "strategy": ls.strategy,
                    "filter": ls.filter_desc,
                }
                for ls in self.load_strategies
            ],
            "queries": [
                {
                    "label": q.label,
                    "sql": q.sql,
                    "duration_ms": round(q.duration_ms, 2),
                    "row_count": q.row_count,
                }
                for q in self.queries
            ],
            "warnings": self.warnings,
        }


ReportHook = Callable[[QueryReport], None]


class QueryAnalyzer:
    def __init__(
        self,
        *,
        log_sql: bool = True,
        log_level: int = logging.INFO,
        on_report: ReportHook | None = None,
    ) -> None:
        self.log_sql = log_sql
        self.log_level = log_level
        # Optional sink for OTel / metrics / custom exporters (receives QueryReport).
        self.on_report = on_report

        self._model_name: str = ""
        self._start_time: float = 0.0
        self._end_time: float | None = None

        self._queries: list[QueryEvent] = []
        self._load_strategies: list[LoadStrategyEvent] = []

        self._requested_fields: list[str] = []
        self._deferred_fields: list[str] = []
        self._relationships: list[str] = []
        self._annotations: list[str] = []
        self._warnings: list[str] = []

        self._result_count: int = 0
        self._total_count: int | None = None

    def begin(self, model: type) -> None:
        self._model_name = model.__name__
        self._start_time = time.perf_counter()
        self._end_time = None

    def record_selected_fields(self, fields: dict[str, Any], model: type) -> None:
        self._requested_fields = list(fields.keys())

    def record_deferred(self, deferred_keys: list[str]) -> None:
        self._deferred_fields = deferred_keys

    def record_relationship(self, name: str) -> None:
        self._relationships.append(name)

    def record_load_strategy(self, relationship: str, strategy: str, filter_desc: str = "") -> None:
        self._load_strategies.append(
            LoadStrategyEvent(relationship=relationship, strategy=strategy, filter_desc=filter_desc)
        )

    def record_annotation(self, name: str, kind: str) -> None:
        self._annotations.append(f"{kind}({name})")

    def record_query(
        self,
        label: str,
        sql: str,
        params: dict[str, Any] | None = None,
        row_count: int = 0,
        duration_ms: float = 0.0,
    ) -> None:
        self._queries.append(
            QueryEvent(
                label=label,
                sql=sql if self.log_sql else "<sql logging disabled>",
                params=params if self.log_sql else None,
                duration_ms=duration_ms,
                row_count=row_count,
            )
        )

    def record_result(self, count: int, total_count: int | None = None) -> None:
        self._result_count = count
        self._total_count = total_count

    def add_warning(self, message: str) -> None:
        self._warnings.append(message)

    def end(self) -> None:
        """Stamp wall-clock end time used by ``report()`` for ``total_duration_ms``."""
        if self._start_time and self._end_time is None:
            self._end_time = time.perf_counter()

    def report(self) -> QueryReport:
        if self._start_time:
            end = self._end_time if self._end_time is not None else time.perf_counter()
            elapsed = (end - self._start_time) * 1000
        else:
            elapsed = 0.0

        return QueryReport(
            model_name=self._model_name,
            total_duration_ms=round(elapsed, 2),
            query_count=len(self._queries),
            queries=list(self._queries),
            requested_fields=list(self._requested_fields),
            deferred_fields=list(self._deferred_fields),
            relationships_loaded=list(self._relationships),
            annotations=list(self._annotations),
            load_strategies=list(self._load_strategies),
            warnings=list(self._warnings),
            result_count=self._result_count,
            total_count=self._total_count,
        )

    def log_report(self) -> QueryReport:
        report = self.report()
        logger.log(self.log_level, "QueryAnalyzer: %s", report.summary())
        if self._warnings:
            for warning in self._warnings:
                logger.warning("QueryAnalyzer [%s]: %s", self._model_name, warning)
        if self.log_sql:
            for q in report.queries:
                logger.log(
                    self.log_level,
                    "  [%s] %s (%d rows, %.1fms)",
                    q.label,
                    q.sql,
                    q.row_count,
                    q.duration_ms,
                )
        if self.on_report is not None:
            self.on_report(report)
        return report

    def reset(self) -> None:
        self._model_name = ""
        self._start_time = 0.0
        self._end_time = None
        self._queries.clear()
        self._load_strategies.clear()
        self._requested_fields.clear()
        self._deferred_fields.clear()
        self._relationships.clear()
        self._annotations.clear()
        self._warnings.clear()
        self._result_count = 0
        self._total_count = None
