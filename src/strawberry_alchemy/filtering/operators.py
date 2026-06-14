from sqlalchemy import String, and_
from sqlalchemy.sql import operators


class FilterOperators:
    LOOKUP_OPERATORS = {
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
    }
