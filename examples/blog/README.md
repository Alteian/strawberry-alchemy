# Blog example

Minimal end-to-end sketch of strawberry-alchemy: models, row-level access filters,
`BaseNodeType` resolvers, `OR` filters, `@optimize_field`, ClassVar repositories,
and a real `BaseDeletionHandler`.

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
