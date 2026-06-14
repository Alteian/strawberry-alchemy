import logging
import time
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


class QueryAnalyzer:
    def __init__(self, *, log_sql: bool = True, log_level: int = logging.INFO) -> None:
        self.log_sql = log_sql
        self.log_level = log_level

        self._model_name: str = ""
        self._start_time: float = 0.0

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

    def record_query(self, label: str, sql: str, params: dict | None = None, row_count: int = 0) -> None:
        self._queries.append(
            QueryEvent(
                label=label,
                sql=sql if self.log_sql else "<sql logging disabled>",
                params=params if self.log_sql else None,
                row_count=row_count,
            )
        )

    def record_result(self, count: int, total_count: int | None = None) -> None:
        self._result_count = count
        self._total_count = total_count

    def add_warning(self, message: str) -> None:
        self._warnings.append(message)

    def end(self) -> None: ...

    def report(self) -> QueryReport:
        elapsed = (time.perf_counter() - self._start_time) * 1000 if self._start_time else 0.0

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
        return report

    def reset(self) -> None:
        self._model_name = ""
        self._start_time = 0.0
        self._queries.clear()
        self._load_strategies.clear()
        self._requested_fields.clear()
        self._deferred_fields.clear()
        self._relationships.clear()
        self._annotations.clear()
        self._warnings.clear()
        self._result_count = 0
        self._total_count = None
