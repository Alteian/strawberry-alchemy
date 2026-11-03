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

## Done in 0.2.3

- Cleared mypy debt; CI typecheck is a hard gate.
- Per-call `access_filter` override on `resolve_*`.
- QueryAnalyzer `end()` + per-query `duration_ms`.
- Broader `resolve_*` / access-filter-on-`totalCount` integration tests.

## Done in 0.3.0

- Generic `AnnotateAncestry` recursive CTE (`ids` / `chain`).
- `DeletionReport` / `strict` / `DeletionPartialFailure` on `delete`.
- Optional soft-delete helpers (`SoftDeleteMixin`, `soft_delete_field`).
- JSONB filter lookups + `JSONFilter` input.

## Later — 0.4.0

- Postgres RLS session GUC plumbing (`SET LOCAL` / `set_config` from GraphQL
  context); app-owned `CREATE POLICY` docs/example; keep Python
  `AccessControlFilter` as optional defense-in-depth.
