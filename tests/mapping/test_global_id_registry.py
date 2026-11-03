from __future__ import annotations

from strawberry_alchemy.mapping import (
    clear_global_id_type_registry,
    create_global_id_from_field,
    register_global_id_type,
)


def test_register_global_id_type_overrides_heuristic() -> None:
    clear_global_id_type_registry()
    try:
        default = create_global_id_from_field("locked_by", "abc")
        assert default.type_name == "LockedByType"

        register_global_id_type("locked_by", "UserType")
        registered = create_global_id_from_field("locked_by", "abc")
        assert registered.type_name == "UserType"
        assert registered.node_id == "abc"
    finally:
        clear_global_id_type_registry()
