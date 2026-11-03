# Blog example

Minimal end-to-end sketch of core strawberry-alchemy patterns: models, row-level
access filters, `BaseNodeType` resolvers, `OR` filters, `@optimize_field`,
ClassVar repositories, and a real `BaseDeletionHandler`.

Demonstrates core patterns plus `prepare_mutation_resources`, `DeletionReport` on
hard delete, and soft-delete via `SoftDeleteMixin` / `PostRepository.soft_delete_field`.
Broader APIs (`AnnotateAncestry`, JSONB key filters, Postgres RLS GUCs) are covered
in unit/integration tests under `tests/` (including `tests/postgres`).

Uses SQLite-friendly declarative models (the library `Base` is PostgreSQL-oriented).

## Layout

| File | Role |
|---|---|
| `models.py` | SQLAlchemy `Post` / `Comment` |
| `access_filters.py` | `AccessControlFilter` |
| `filters.py` | Filter inputs with `AND` / `OR` |
| `schemas.py` | `BaseSchema` DTOs |
| `repositories.py` | ClassVar `BaseRepository` subclasses |
| `deletion.py` | Cascade comments on post delete |
| `types.py` | `BaseNodeType` + `optimize_field` / `CUSTOM_FILTERS` |
| `queries.py` / `mutations.py` | Thin GraphQL surface |
| `context.py` / `schema.py` | Context contract + schema assembly |

## Run the tests that cover this example

```bash
make test ARGS="tests/examples"
```
