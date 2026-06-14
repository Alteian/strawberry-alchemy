# strawberry-alchemy

<p align="center">
  <em>Batteries-included toolkit for building <strong>Strawberry GraphQL</strong> APIs backed by <strong>SQLAlchemy</strong></em>
</p>

<p align="center">
  <a href="https://github.com/Alteian/strawberry-alchemy/actions/workflows/ci.yml"><img src="https://github.com/Alteian/strawberry-alchemy/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/strawberry-alchemy"><img src="https://img.shields.io/pypi/v/strawberry-alchemy?color=%2334D058&label=pypi" alt="PyPI version"></a>
  <a href="https://pypi.org/project/strawberry-alchemy"><img src="https://img.shields.io/pypi/pyversions/strawberry-alchemy.svg?color=%2334D058" alt="Python versions"></a>
  <a href="https://github.com/Alteian/strawberry-alchemy/blob/master/LICENSE"><img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

**Source Code**: [https://github.com/Alteian/strawberry-alchemy](https://github.com/Alteian/strawberry-alchemy)

---

## Features

| Module | What it does |
|---|---|
| **QueryOptimizer** | Analyzes Strawberry selection sets and builds a single optimized SQLAlchemy query — automatic `joinedload` / `selectinload`, column deferral, annotation injection |
| **FilterBuilder** | Translates Strawberry input types into SQLAlchemy `WHERE` clauses using a declarative operator system |
| **Repository** | Generic async CRUD with delete, dependent-map cascading, and lifecycle hooks |
| **Types** | Relay `Connection` / `Edge` / `PageInfo` pagination, `ListResult`, `BaseNodeType` |
| **Mapping** | Async helpers to convert SQLAlchemy instances → Strawberry types respecting the selected field tree |
| **Permissions** | Protocol-based permission primitives: `IsAuthenticated`, `RolePermission`, `OwnerPermission`, `ObjectAccessPermission`, plus resolver pattern and resource-bag |
| **Models** | Tiny SQLAlchemy `DeclarativeBase` with UUID primary key, timestamps, and automatic table naming |
| **Utilities** | `camel_to_snake`, `DateTimeProcessor`, `Ordering` enum, common exceptions |

## Installation

```bash
pip install strawberry-alchemy
# or with uv
uv add strawberry-alchemy
```

## Quick Start

```python
import strawberry
from sqlalchemy.ext.asyncio import AsyncSession

from strawberry_alchemy import (
    BaseNodeType,
    BaseRepository,
    FilterBuilder,
    OptimizedListConnection,
    QueryOptimizer,
)

# 1. Define your SQLAlchemy model (or use the provided Base)
from strawberry_alchemy.models import Base

# 2. Define your Strawberry type
@strawberry.type
class BookType(BaseNodeType):
    title: str
    author: str

# 3. Use QueryOptimizer in your resolver
@strawberry.type
class Query:
    @strawberry.field
    async def books(self, info: strawberry.Info) -> list[BookType]:
        optimizer = QueryOptimizer(session=info.context.db, info=info)
        result = await optimizer.optimize_query(model=Book)
        return result.items
```

## Development

```bash
git clone https://github.com/Alteian/strawberry-alchemy.git
cd strawberry-alchemy
uv sync

# Lint & test
uv run ruff check .
uv run pytest -v

# Build
uv build
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
