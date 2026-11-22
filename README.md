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

<p align="center">
  <a href="https://deepwiki.com/Alteian/strawberry-alchemy"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
</p>

---

**Source Code**: [https://github.com/Alteian/strawberry-alchemy](https://github.com/Alteian/strawberry-alchemy)

**Documentation**: [https://alteian.github.io/strawberry-alchemy/](https://alteian.github.io/strawberry-alchemy/) · [docs/](docs/index.md)

---

## What is it?

strawberry-alchemy turns Strawberry GraphQL selection sets into a single optimized
SQLAlchemy query — automatic `selectinload` for relationships, column deferral, and
SQL `EXISTS`/`COUNT`/ancestry annotations — and ships filters, Relay pagination,
CRUD repositories, row-level ACL, permissions helpers, and mapping utilities.

- No N+1: nested selections become eager loads
- Unrequested columns are deferred
- Declarative computed fields via `@optimize_field`
- `AND`/`OR` filters, relation joins, custom filters, Postgres JSONB lookups
- Relay `Connection` pagination with `totalCount`
- Async repositories with deletion reports, cascade hooks, optional soft-delete
- Row-level `AccessControlFilter` (+ per-edge `RelationAccessFilter`) and optional Postgres RLS GUCs

## Installation

```bash
pip install strawberry-alchemy
# or
uv add strawberry-alchemy
```

Requires Python `>= 3.13`, Strawberry GraphQL `>= 0.339.1`,
`sqlalchemy[asyncio] >= 2.1.6`, Pydantic `>= 2.14`.

## Quick example

```python
# access_filters.py
from typing import Any
from models import Post
from strawberry_alchemy import AccessControlFilter


class PostAccessFilter(AccessControlFilter):
    model_class = Post

    @staticmethod
    async def apply_filter(query: Any, model: type[Any], context_user: Any) -> Any:
        return query.where(model.user_id == context_user.id)
```

```python
# types.py
import strawberry
from typing import ClassVar
from strawberry_alchemy import BaseNodeType
from access_filters import PostAccessFilter


@strawberry.type
class PostType(BaseNodeType):
    access_filter: ClassVar[type[PostAccessFilter]] = PostAccessFilter

    title: str | None = strawberry.UNSET
    body: str | None = strawberry.UNSET
```

```python
# queries.py
import strawberry
from strawberry.types import Info
from strawberry_alchemy import ListResult
from types import PostType


@strawberry.type
class Query:
    @strawberry.field
    async def posts(self, info: Info, limit: int | None = None) -> ListResult[PostType]:
        return await PostType.resolve_list(info=info, limit=limit)
```

Your request context needs `get_session()`, an `identity` / `user`, and a
`db_execution_lock` — see
[Context contract](docs/getting-started.md#context-contract).

## Documentation

| Page | Topic |
|---|---|
| [docs/index.md](docs/index.md) | Overview and architecture |
| [docs/getting-started.md](docs/getting-started.md) | Full walkthrough |
| [docs/types-and-models.md](docs/types-and-models.md) | `Base`, `BaseNodeType`, connections |
| [docs/queries.md](docs/queries.md) | `resolve_*`, pagination, ordering |
| [docs/filtering.md](docs/filtering.md) | Filters, ACL, `RelationAccessFilter` |
| [docs/query-optimizer.md](docs/query-optimizer.md) | Hints, analyzer, custom order |
| [docs/mapping-and-schema.md](docs/mapping-and-schema.md) | `BaseSchema`, `schema_from_input` |
| [docs/repository.md](docs/repository.md) | CRUD, soft-delete, deletion handlers |
| [docs/permissions.md](docs/permissions.md) | Permission helpers for mutations |
| [docs/postgres-rls.md](docs/postgres-rls.md) | Session GUC helpers |
| [docs/recipes.md](docs/recipes.md) | Production wrapping patterns |
| [docs/api-reference.md](docs/api-reference.md) | Public exports |

## Example

Runnable core patterns (ACL, `OR` filters, `@optimize_field`, ClassVar repos,
deletion handler, soft-delete, `prepare_mutation_resources`) live in
[`examples/blog`](examples/blog).

```bash
make test ARGS="tests/examples"
```

## Development

Tool versions are pinned in [`mise.toml`](mise.toml) (same pins CI uses). Tasks
stay in Make.

```bash
git clone https://github.com/Alteian/strawberry-alchemy.git
cd strawberry-alchemy
mise install
make sync && make doctor
make ci
```

Docs: `make docs` / `make docs-serve`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
