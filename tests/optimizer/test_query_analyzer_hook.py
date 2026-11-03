from __future__ import annotations

from strawberry_alchemy import QueryAnalyzer


def test_on_report_hook_receives_query_report() -> None:
    seen: list[object] = []

    analyzer = QueryAnalyzer(log_sql=False, on_report=seen.append)
    analyzer.begin(type("Post", (), {}))
    analyzer.record_result(3, total_count=10)
    analyzer.end()
    report = analyzer.log_report()

    assert seen == [report]
    assert report.result_count == 3
    assert report.total_count == 10


def test_query_analyzer_reset_clears_state() -> None:
    analyzer = QueryAnalyzer(log_sql=False)
    analyzer.begin(type("Post", (), {}))
    analyzer.record_query("data", "SELECT 1", row_count=1, duration_ms=1.5)
    analyzer.record_deferred(["body"])
    analyzer.add_warning("slow")
    analyzer.record_result(1)
    analyzer.end()
    analyzer.reset()
    report = analyzer.report()
    assert report.model_name == ""
    assert report.query_count == 0
    assert report.warnings == []
    assert report.deferred_fields == []
    assert report.result_count == 0
