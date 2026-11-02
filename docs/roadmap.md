# Roadmap

## Done in 0.2.0

- Latest dependency floors (Strawberry, SQLAlchemy asyncio, Pydantic, dateutil).
- Fixed root/nested `AND` / `OR` filter semantics.
- Typed selection helpers (`FieldPath`, Relay vs domain `edges`).
- `CUSTOM_FILTERS` on `BaseNodeType`, repository ClassVar constructor, connection lock.

## 0.2.1 — docs and examples

- Self-contained `examples/` walkthrough: `BaseNodeType`, access filters, filters
  (including `OR`), `@optimize_field`, repository + `relation_models`,
  `BaseDeletionHandler`.
- README / getting-started aligned with that example.

## 0.2.2 — scan and regressions

- Broader bugfix scan under new deps and typed selection.
- Expand operator / resolve_* / deletion-handler coverage.
- Clear remaining mypy debt so CI typecheck can become a hard gate.

## Later candidates

- Optional soft-delete helpers on `BaseRepository`.
- Generic `AnnotateAncestry` CTE (replace experimental stub).
- Deletion reporting / partial-failure mode.
- Per-call `access_filter` override on `resolve_*`.
- QueryAnalyzer UX improvements.
- JSONB / structured filter helpers.
