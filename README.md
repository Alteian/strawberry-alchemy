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

**Documentation**: [docs/index.md](docs/index.md) · [API reference](docs/api-reference.md)

---

## What is it?

strawberry-alchemy turns Strawberry GraphQL selection sets into a single optimized
SQLAlchemy query — automatic `selectinload` for relationships, column deferral, and
SQL `EXISTS`/`COUNT` annotations — and ships the supporting cast: filter inputs,
Relay pagination, CRUD repositories, row-level security, permissions, and mapping
helpers.

- No N+1 queries: nested selections become eager loads automatically
- Unrequested columns are deferred — you only fetch what the client asked for
- Declarative computed fields (`hasComments`, counts, ancestry CTEs) via `@optimize_field`
- `AND`/`OR` filters, relationship joins, custom filters, and Postgres JSONB lookups
- Relay `Connection` pagination with `totalCount`
- Async repositories with deletion reports, cascade hooks, and optional soft-delete
- Row-level `AccessControlFilter` on root queries / `totalCount`, plus Postgres RLS session GUCs

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
# models.py
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from strawberry_alchemy.models import Base


class Post(Base):
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id"))
    title: Mapped[str]
    body: Mapped[str]
```

```python
# access_filters.py
from typing import Any
from models import Post
from strawberry_alchemy.filtering import AccessControlFilter


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


@strawberry.type
class Query:
    @strawberry.field
    async def posts(self, info: Info, limit: int | None = None) -> ListResult[PostType]:
        return await PostType.resolve_list(info=info, limit=limit)
```

```python
# schema.py
import strawberry
from strawberry.schema.config import StrawberryConfig

schema = strawberry.Schema(
    query=Query,
    config=StrawberryConfig(auto_camel_case=True, relay_max_results=100),
)
```

```graphql
query {
  posts(limit: 10) {
    items { id title body }
    totalCount
  }
}
```

Your request context needs three things: `get_session()`, an `identity`/`user`
attribute, and a `db_execution_lock` (see
[docs/getting-started.md#context-contract](docs/getting-started.md)).

## Documentation

| Page | Topic |
|---|---|
| [docs/index.md](docs/index.md) | Overview, features, architecture |
| [docs/getting-started.md](docs/getting-started.md) | Full walkthrough: models, types, filters, queries, mutations |
| [docs/types-and-models.md](docs/types-and-models.md) | `Base`, `BaseNodeType`, `ListResult`, connections, ordering |
| [docs/queries.md](docs/queries.md) | `resolve_node` / `resolve_list` / `resolve_connection`, pagination |
| [docs/query-optimizer.md](docs/query-optimizer.md) | Load strategies, `@optimize_field` hints, `QueryAnalyzer` |
| [docs/filtering.md](docs/filtering.md) | Filter inputs, operators, `AND`/`OR`, custom & access-control filters |
| [docs/repository.md](docs/repository.md) | CRUD, soft-delete, deletion reports / handlers |
| [docs/mapping-and-schema.md](docs/mapping-and-schema.md) | `BaseSchema`, SQLAlchemy → Strawberry mapping |
| [docs/permissions.md](docs/permissions.md) | Permission classes, resource checks |
| [docs/postgres-rls.md](docs/postgres-rls.md) | Session GUC helpers for app-owned RLS policies |
| [docs/api-reference.md](docs/api-reference.md) | Every public export with signatures |

## Example

A runnable blog sketch covering core patterns (models, ACL, `OR` filters,
`@optimize_field`, ClassVar repositories, deletion handler) lives in
[`examples/blog`](examples/blog). It is a focused walkthrough — not every 0.3/0.4
API (ancestry, soft-delete, JSONB, RLS) is demonstrated there yet.

```bash
make test ARGS="tests/examples"
```

## Development

Tool versions are pinned in [`mise.toml`](mise.toml) (same pins CI uses via
[`jdx/mise-action`](https://github.com/jdx/mise-action)). Tasks stay in Make.

```bash
git clone https://github.com/Alteian/strawberry-alchemy.git
cd strawberry-alchemy
# https://mise.jdx.dev — then:
mise install
make sync
make doctor

# Lint, typecheck, test, build (same Make targets CI runs)
make ci
```

See [docs/roadmap.md](docs/roadmap.md) for planned work. See `make help` for targets.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
