# strawberry-alchemy

Batteries-included toolkit for building **Strawberry GraphQL** APIs backed by **SQLAlchemy**.
It turns Strawberry selection sets into a single optimized SQLAlchemy query, and ships
ready-made building blocks for filtering, Relay pagination, CRUD repositories,
row-level security, permissions, and output mapping.

## What it gives you

| Module | What it does |
|---|---|
| **QueryOptimizer** | Analyzes the incoming GraphQL selection set and builds one optimized SQLAlchemy query: automatic `selectinload` for nested relationships, `defer()` for unrequested columns, and SQL `EXISTS` / `COUNT` subquery annotations |
| **`optimize_field` hints** | Declarative decorators for computed fields: `PrefetchRelated`, `SelectColumns`, `AnnotateExists`, `AnnotateAnyExists`, `AnnotateCount`, `AnnotateCustom` |
| **FilterBuilder** | Translates Strawberry filter inputs into SQLAlchemy `WHERE` clauses using a declarative operator system, with `AND` / `OR` nesting, relationship traversal, and per-model custom filters |
| **Types** | `BaseNodeType` (Relay `Node` with UUID id + timestamps), `OptimizedListConnection` / `Edge` / `PageInfo` Relay pagination, `ListResult` |
| **Repository** | Generic async CRUD (`create`, `update`, `delete`, relation management) with lifecycle hooks and dependent-map cascade deletion |
| **Mapping** | Async helpers to convert SQLAlchemy instances into Strawberry types while respecting the selected field tree (no over-fetching of lazy attributes) |
| **Permissions** | Protocol-based permission primitives (`IsAuthenticated`, `RolePermission`, `OwnerPermission`, `ObjectAccessPermission`), a resolver base class, and a resource-bag helper |
| **Models & Schema** | Tiny SQLAlchemy `DeclarativeBase` with UUID primary key + timestamps, and `BaseSchema` — a Pydantic base that is safe to validate from ORM instances |
| **Utilities** | `camel_to_snake`, `Ordering` enum, `NotFoundError` |

## Requirements

- Python `>= 3.13`
- `strawberry-graphql >= 0.220`
- `sqlalchemy` (async usage)
- `pydantic >= 2.0`
- `python-dateutil`

## Installation

```bash
pip install strawberry-alchemy
# or
uv add strawberry-alchemy
```

## How the pieces fit together

The library is built around a small contract between your GraphQL types and the
query optimizer:

1. Your GraphQL type subclasses `BaseNodeType`, declares an `access_filter` (row-level
   security) and its scalar/relationship fields.
2. Query resolvers delegate to classmethods — `resolve_node`, `resolve_nodes`,
   `resolve_list`, `resolve_connection` — which read the incoming selection set from
   `info`, build one optimized SQLAlchemy query, and map results back to Strawberry types.
3. Computed fields (e.g. `hasComments`, `coverThumbUrl`) are decorated with
   `@optimize_field(...)` so the optimizer knows what data they need.
4. Filter inputs are built from the provided `IDFilter` / `StringFilter` / etc.
   and passed to the same resolvers; `FilterBuilder` converts them to SQL.
5. Mutations use `BaseRepository` + `BaseSchema` for CRUD, optionally with a
   `BaseDeletionHandler` for cascade deletes.

A complete walkthrough of these pieces working together is in
[Getting started](getting-started.md).

## Documentation index

- [Getting started](getting-started.md) — full walkthrough: models, types, filters, queries, mutations, schema
- [Types & models](types-and-models.md) — `BaseNodeType`, `ListResult`, `OptimizedListConnection`, the `Base` model
- [Queries](queries.md) — `resolve_node`, `resolve_list`, `resolve_connection`, ordering, pagination
- [Query optimizer](query-optimizer.md) — automatic load strategies, `@optimize_field` hints, `QueryAnalyzer`
- [Filtering](filtering.md) — filter inputs, operators, `AND`/`OR`, custom filters, access-control filters
- [Repository](repository.md) — CRUD, relation management, deletion handlers
- [Mapping & schema](mapping-and-schema.md) — `BaseSchema`, `dump_for_db`, `to_type`, mapping helpers
- [Permissions](permissions.md) — permission classes and resource checks
- [API reference](api-reference.md) — every public export with signatures

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

## License

[MIT](../LICENSE)
