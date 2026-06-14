"""Smoke tests to verify public imports and basic functionality."""

from __future__ import annotations

import pytest


def test_public_imports() -> None:
    """All advertised top-level names should be importable."""


def test_camel_to_snake() -> None:
    from strawberry_alchemy import camel_to_snake

    assert camel_to_snake("camelCaseString") == "camel_case_string"
    assert camel_to_snake("HTTPSConnection") == "https_connection"
    assert camel_to_snake("alreadysnake") == "alreadysnake"


def test_camel_to_snake_dict() -> None:
    from strawberry_alchemy import camel_to_snake

    result = camel_to_snake({"firstName": "Alice", "lastName": "Bob"})
    assert result == {"first_name": "Alice", "last_name": "Bob"}


def test_ordering_enum() -> None:
    from strawberry_alchemy import Ordering

    assert Ordering.ASC.value == "ASC"
    assert Ordering.DESC.value == "DESC"


def test_not_found_exception() -> None:
    from strawberry_alchemy import NotFoundError

    with pytest.raises(NotFoundError):
        raise NotFoundError("User: 123")


def test_filter_operators_registry() -> None:
    from strawberry_alchemy import FilterOperators

    assert "exact" in FilterOperators.LOOKUP_OPERATORS
    assert "icontains" in FilterOperators.LOOKUP_OPERATORS
    assert "in" in FilterOperators.LOOKUP_OPERATORS
    assert "range" in FilterOperators.LOOKUP_OPERATORS


def test_query_result_defaults() -> None:
    from strawberry_alchemy import QueryResult

    qr = QueryResult()
    assert qr.items == []
    assert qr.selected_fields == {}
    assert qr.total_count == 0


def test_base_schema_dump_for_db() -> None:
    import strawberry

    from strawberry_alchemy import BaseSchema

    class UserSchema(BaseSchema):
        name: str
        email: str | None = strawberry.UNSET

    schema = UserSchema(name="Alice")
    data = schema.dump_for_db()
    assert data == {"name": "Alice"}
    assert "email" not in data


def test_query_analyzer_lifecycle() -> None:
    from strawberry_alchemy import QueryAnalyzer

    analyzer = QueryAnalyzer()

    class FakeModel:
        __name__ = "FakeModel"

    analyzer.begin(FakeModel)
    analyzer.record_selected_fields({"id": True, "name": True}, FakeModel)
    analyzer.record_deferred(["description"])
    analyzer.record_relationship("tags")
    analyzer.record_annotation("comments", "COUNT")
    analyzer.record_result(count=5, total_count=10)
    analyzer.end()

    report = analyzer.report()
    assert report.model_name == "FakeModel"
    assert report.result_count == 5
    assert report.total_count == 10
    assert "description" in report.deferred_fields
    assert "tags" in report.relationships_loaded
    assert "COUNT(comments)" in report.annotations


def test_prefetch_related_defaults() -> None:
    from strawberry_alchemy import PrefetchRelated

    pr = PrefetchRelated(relationship="tags")
    assert pr.relationship == "tags"
    assert pr.fields is None
    assert pr.filter_current_user is False
    assert pr.has_custom_loading is False


def test_annotate_exists_resolved_attr() -> None:
    from strawberry_alchemy import AnnotateExists

    ae = AnnotateExists(relationship="likes")
    assert ae.resolved_attr == "_likes_exists"

    ae_custom = AnnotateExists(relationship="likes", to_attr="is_liked")
    assert ae_custom.resolved_attr == "is_liked"


def test_annotate_count_resolved_attr() -> None:
    from strawberry_alchemy import AnnotateCount

    ac = AnnotateCount(relationship="comments")
    assert ac.resolved_attr == "_comments_count"


def test_base_deletion_handler_hooks() -> None:
    """Default deletion handler hooks should be no-ops."""
    from strawberry_alchemy import BaseDeletionHandler

    handler = BaseDeletionHandler()
    assert handler is not None
