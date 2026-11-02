# Roadmap

## Done in 0.2.0

- Latest dependency floors (Strawberry, SQLAlchemy asyncio, Pydantic, dateutil).
- Fixed root/nested `AND` / `OR` filter semantics.
- Typed selection helpers (`FieldPath`, Relay vs domain `edges`).
- `CUSTOM_FILTERS` on `BaseNodeType`, repository ClassVar constructor, connection lock.

## Done in 0.2.1

- `examples/blog` + `tests/examples` covering the full feature surface.
- README / getting-started point at the example.

## Done in 0.2.2

- Hardened GlobalID decode in permissions input parsing.
- Added repository relation and FilterBuilder error regression tests.

## Later candidates

- Clear remaining mypy debt so CI typecheck can become a hard gate.
- Optional soft-delete helpers on `BaseRepository`.
- Generic `AnnotateAncestry` CTE (replace experimental stub).
- Deletion reporting / partial-failure mode.
- Per-call `access_filter` override on `resolve_*`.
- QueryAnalyzer UX improvements.
- JSONB / structured filter helpers.
- Broader `resolve_*` / access-filter-on-`totalCount` integration tests.
