from __future__ import annotations

from sqlalchemy import Column, MetaData, Table, column, table
from sqlalchemy.dialects import postgresql

from strawberry_alchemy import FilterOperators, JSONFilter


def test_jsonb_lookups_registered() -> None:
    for key in (
        "jsonb_contains",
        "jsonb_contained_by",
        "jsonb_has_key",
        "jsonb_has_any",
        "jsonb_has_all",
        "jsonb_path",
    ):
        assert key in FilterOperators.LOOKUP_OPERATORS


def test_jsonb_contains_compiles_on_postgresql() -> None:
    metadata = MetaData()
    docs = Table(
        "docs",
        metadata,
        Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        Column("payload", postgresql.JSONB),
    )
    expr = FilterOperators.LOOKUP_OPERATORS["jsonb_contains"](docs.c.payload, {"a": 1})
    sql = str(expr.compile(dialect=postgresql.dialect()))
    assert "payload" in sql
    assert "@>" in sql


def test_json_filter_input_fields() -> None:
    # Instantiable strawberry input with expected attributes.
    assert hasattr(JSONFilter, "__strawberry_definition__")
    fields = {f.name for f in JSONFilter.__strawberry_definition__.fields}
    assert "jsonb_contains" in fields
    assert "jsonb_has_key" in fields


def test_jsonb_has_key_compiles() -> None:
    payload = table("docs", column("payload", postgresql.JSONB))
    expr = FilterOperators.LOOKUP_OPERATORS["jsonb_has_key"](payload.c.payload, "owner")
    sql = str(expr.compile(dialect=postgresql.dialect()))
    assert "payload" in sql
