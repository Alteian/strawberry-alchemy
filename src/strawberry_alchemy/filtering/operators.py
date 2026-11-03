from collections.abc import Callable
from typing import Any, ClassVar

from sqlalchemy import String, and_
from sqlalchemy.sql import operators


class FilterOperators:
    LOOKUP_OPERATORS: ClassVar[dict[str, Callable[..., Any]]] = {
        "exact": operators.eq,
        "iexact": lambda c, v: c.ilike(v) if isinstance(c.type, String) else c == v,
        "contains": lambda c, v: c.contains(v) if isinstance(c.type, String) else c == v,
        "icontains": lambda c, v: c.ilike(f"%{v}%") if isinstance(c.type, String) else c == v,
        "in": lambda c, v: c.in_(v),
        "not_in": lambda c, v: ~c.in_(v),
        "gt": operators.gt,
        "ge": operators.ge,
        "lt": operators.lt,
        "le": operators.le,
        "startswith": lambda c, v: c.startswith(v) if isinstance(c.type, String) else c == v,
        "istartswith": lambda c, v: c.ilike(f"{v}%") if isinstance(c.type, String) else c == v,
        "endswith": lambda c, v: c.endswith(v) if isinstance(c.type, String) else c == v,
        "iendswith": lambda c, v: c.ilike(f"%{v}") if isinstance(c.type, String) else c == v,
        "range": lambda c, v: and_(c >= v[0], c <= v[1]),
        "isnull": lambda c, v: c.is_(None) if v else c.isnot(None),
        # Postgres JSONB (column must use sqlalchemy.dialects.postgresql.JSONB).
        # Names are prefixed to avoid colliding with string ``contains``.
        "jsonb_contains": lambda c, v: c.contains(v),
        "jsonb_contained_by": lambda c, v: c.contained_by(v),
        "jsonb_has_key": lambda c, v: c.has_key(v),
        "jsonb_has_any": lambda c, v: c.has_any(v),
        "jsonb_has_all": lambda c, v: c.has_all(v),
        "jsonb_path": lambda c, v: c.path_exists(v),
    }
