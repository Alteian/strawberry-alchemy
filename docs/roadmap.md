# Roadmap

Planned work for upcoming releases. Items may move between releases as scope
is refined.

## 0.2.0 — deps, bugfixes, hardening, small features

- Raise dependency floors to current PyPI majors (`strawberry-graphql`,
  `sqlalchemy[asyncio]`, `pydantic`, `python-dateutil`) and fix compatibility.
- **Fix `AND` / `OR` filter semantics** (root and nested): multi-field branches
  must combine with `and_` inside each arm; serialize `AND`/`OR` as lists of
  branch dicts (see failing tests under `tests/filtering/`).
- **Typed selection tree** for Relay `edges` / `node` / connection wrappers and
  field paths (replace stringly dict keys and `"."`-joined paths).
- Apply `db_execution_lock` on connection resolve (parity with node/list).
- First-class `CUSTOM_FILTERS` on `BaseNodeType`.
- Repository ClassVar constructor (`model_cls` / `schema_cls` →
  `SomeRepository(session)`).
- Harden errors: unknown filter lookups, invalid GlobalIDs, missing context
  contract fields.
- Clear mypy debt so CI typecheck can become a hard gate (`make ci-strict`).

## 0.2.1 — docs and examples

- Self-contained `examples/` walkthrough: `BaseNodeType`, access filters,
  filters (including `OR`), `@optimize_field`, repository + `relation_models`,
  `BaseDeletionHandler`.
- README / getting-started rewrite aligned with that example.

## 0.2.2 — scan and regressions

- Broader bugfix scan under new deps and the typed selection tree.
- Expand operator / resolve_* / deletion-handler coverage.

## Later candidates

- Optional soft-delete helpers on `BaseRepository`.
- Generic `AnnotateAncestry` CTE (replace experimental stub).
- Deletion reporting / partial-failure mode.
- Per-call `access_filter` override on `resolve_*`.
- QueryAnalyzer UX improvements.
- JSONB / structured filter helpers.
