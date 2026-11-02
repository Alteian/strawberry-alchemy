"""Selection-tree / path handling."""

from __future__ import annotations

from typing import Any

from strawberry_alchemy.mapping.sqlalchemy_to_gql import extract_fields_at_path
from strawberry_alchemy.optimizer.prefetch import source_path_to_dependency_tree
from strawberry_alchemy.optimizer.query_optimizer import QueryOptimizer
from strawberry_alchemy.optimizer.selection import (
    FieldPath,
    FieldSelection,
    RelayConnectionSelection,
    parse_selection_tree,
)


class _FakeInfo:
    context: Any = None
    selected_fields: list[Any] = []


def test_extract_fields_at_path_uses_dotted_strings() -> None:
    selected = {
        "edges": {
            "node": {
                "title": True,
                "comments": {"body": True},
            }
        }
    }

    nested = extract_fields_at_path(selected, "edges.node.comments")
    assert nested == {"body": True}
    assert extract_fields_at_path(selected, "edges.nodes.comments") == {}


def test_field_path_is_typed_sequence_not_dotted_string() -> None:
    path = FieldPath(("edges", "node", "comments"))
    assert tuple(path) == ("edges", "node", "comments")
    assert path != FieldPath(("comments",))
    assert FieldPath("edges.node.comments") == path


def test_selection_tree_distinguishes_relay_edges_from_domain_field() -> None:
    relay = parse_selection_tree(
        {
            "edges": {"node": {"title": True}},
            "pageInfo": {"hasNextPage": True},
            "totalCount": True,
        }
    )
    assert isinstance(relay, RelayConnectionSelection)
    assert "title" in relay.node_fields

    domain = parse_selection_tree({"edges": {"id": True, "label": True}, "name": True})
    assert isinstance(domain, FieldSelection)
    assert "edges" in domain.children


def test_source_path_to_dependency_tree_splits_on_dots() -> None:
    tree = source_path_to_dependency_tree("market_details.listing_code")
    assert tree == {"market_details": {"listing_code": True}}
    assert source_path_to_dependency_tree(FieldPath(("market_details", "listing_code"))) == tree


def test_extract_model_fields_relay_unwrap_vs_domain_edges() -> None:
    optimizer = QueryOptimizer(_FakeInfo(), session=object())  # type: ignore[arg-type]

    relay = optimizer.extract_model_fields(
        {
            "edges": {"node": {"title": True}},
            "pageInfo": {"hasNextPage": True},
            "totalCount": True,
        }
    )
    assert relay == {"title": True}

    domain = optimizer.extract_model_fields(
        {
            "edges": {"id": True, "label": True},
            "name": True,
        }
    )
    assert domain == {"edges": {"id": True, "label": True}, "name": True}
