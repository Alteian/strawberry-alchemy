# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-11-03

### Added

- **Postgres RLS session GUCs** — `apply_rls_context`, `set_rls_guc`, and
  `clear_rls_context` set transaction-local `app.*` settings for app-owned
  `CREATE POLICY` DDL. See [docs/postgres-rls.md](docs/postgres-rls.md).

## [0.3.0] — 2026-11-03

### Added

- **`AnnotateAncestry`** — generic recursive parent-walk CTE (`value_mode`
  `"ids"` / `"chain"`, dialect-aware aggregates).
- **`DeletionReport` / `DeletionFailure` / `DeletionPartialFailure`** —
  `BaseRepository.delete` always returns a report; `strict=True` raises on
  recorded handler failures; handlers expose `report` / `reset_report`.
- **Soft-delete helpers** — optional `soft_delete_field` ClassVar,
  `soft_delete()`, `include_deleted` on reads, and `SoftDeleteMixin`.
- **JSONB filter lookups** — `jsonb_contains`, `jsonb_contained_by`,
  `jsonb_has_key`, `jsonb_has_any`, `jsonb_has_all`, `jsonb_path` plus
  `JSONFilter` input (Postgres JSONB columns).

## [0.2.3] — 2026-11-03

### Added

- Per-call `access_filter` override on `resolve_node` / `resolve_nodes` /
  `resolve_list` / `resolve_connection` (class or instance).
- `QueryAnalyzer.end()` stamps wall-clock duration; `record_query` accepts
  `duration_ms`, and the optimizer records per-statement execute timing.

### Fixed

- Cleared remaining mypy `strict` debt across the public package surface.

### Changed

- CI `typecheck` is now a hard gate; `build` requires lint, typecheck, and test.

### Tests

- `resolve_*` ClassVar ACL vs per-call override, including `totalCount`.

## [0.2.2] — 2026-11-02

### Fixed

- GlobalID decoding in permissions input parsing now tolerates Strawberry
  `InvalidGlobalIDError` (and related decode failures) without raising.

### Tests

- Repository `add_related` / `remove_related` coverage.
- FilterBuilder unknown lookup / unknown field error coverage.

## [0.2.1] — 2026-11-02

### Added

- **`examples/blog`** — self-contained Post/Comment sketch covering access filters,
  `OR` filters, `CUSTOM_FILTERS`, `@optimize_field`, ClassVar repositories, and
  `BaseDeletionHandler`, with tests under `tests/examples/`.

### Documentation

- README and getting-started link to the blog example as the canonical walkthrough.

## [0.2.0] — 2026-11-02

### Added

- **Typed selection helpers** — `FieldPath`, `FieldSelection`, `RelayConnectionSelection`,
  `parse_selection_tree`, `extract_at_path` (Relay `edges`/`node` vs domain fields).
- **`CUSTOM_FILTERS` on `BaseNodeType`** — auto-wires `_custom_filters_registry` for the
  query optimizer when set on a subclass.
- **`BaseRepository` ClassVar constructor** — declare `model_cls` / `schema_cls` on the
  subclass and construct with `SomeRepository(session)` (explicit ctor args still work).

### Changed

- Dependency floors: `strawberry-graphql>=0.339.1`, `sqlalchemy[asyncio]>=2.1.6`,
  `pydantic>=2.14.2`, `python-dateutil>=4.0`.
- `resolve_connection` now takes `db_execution_lock` like node/list resolve.
- `access_filter` accepts a filter **class** or instance.

### Fixed

- **Root / nested `OR` and `AND`** — multi-field branches are `and_`-combined inside each
  arm instead of being flattened into sibling OR/AND clauses; `build_filter_dict`
  preserves `AND` as a list of branch dicts.

## [0.1.6] — 2026-11-02

### Added

- Make DX targets: `help`, `sync` / `sync-frozen`, `doctor`, `check-versions`,
  `hooks`, and `test ARGS=…` (Make + uv; no Mise).
- `.pre-commit-config.yaml` (ruff).
- CI runs `pytest-cov` and a non-blocking `mypy` job (hard gate once typing
  debt is cleared); Dependabot watches `uv` instead of npm.
- Release workflow uses `--frozen` sync, uploads `dist/` between jobs, and
  attaches built artifacts to the GitHub Release.
- [docs/roadmap.md](docs/roadmap.md) for planned fixes, hardening, and features.
- Regression fixtures (expected failures) for root `OR`/`AND` filter bugs and
  typed selection-tree work targeted at 0.2.0.

### Fixed

- Documentation now treats `access_filter` as a **class** `ClassVar` (instances
  remain supported).
- Clarified that **soft-delete** and **`DateTimeProcessor`** were never part of
  the public API despite older changelog wording.

## [0.1.5] — 2026-08-19

### Fixed

- **GlobalID mapping is now annotation-driven.** `map_sqlalchemy_to_type` converted
  scalar fields to `GlobalID` only when the field name ended in `_id`, so fields
  annotated as `GlobalID` with another suffix (e.g. `locked_by`) leaked the raw
  UUID into the constructed type. Conversion now keys off the field's type
  annotation, and `create_global_id_from_field` no longer assumes an `_id` suffix.
- **Real `edges` fields are no longer dropped as Relay connection wrappers.**
  `extract_model_fields`, `collect_requested_fields`, `collect_requested_fields_recursive`
  and `build_query_with_selected_fields` treated every field literally named
  `edges` as Relay connection syntax, so a domain relationship named `edges`
  (e.g. `Workflow.edges`) was never eager-loaded or mapped and always resolved
  to `[]`. Only `edges` selections containing a `node` subfield are now treated
  as a connection.

## [0.1.4] — 2026-08-16

### Documentation

- Added a `docs/` site covering models, types, queries, the query optimizer,
  `@optimize_field` hints, filtering, repositories, mapping, permissions, and a
  full API reference.
- Rewrote the README with a plain quick-start example and links to the docs.

## [0.1.3] — 2026-08-15

### Added

- **`SelectColumns`** — `@optimize_field(SelectColumns("col_a", "col_b"))` undeferrs
  same-model scalar columns when a computed GraphQL field is selected, so resolvers
  can read deferred storage columns without per-row repository hydrates.

## [0.1.2] — 2026-06-25

### Fixed

- Datetime serialization
- coercing unsets
- optional exclude

## [0.1.1] — 2026-06-14

### Added

- Added a complete usage example to the README.

### Documentation

- Improved setup and usage documentation.
- Documented automatic query optimization features.

## [0.1.0] — 2026-06-13

### Added

- **QueryOptimizer** — automatic join/load strategy selection from Strawberry selection sets.
- **FilterBuilder** — declarative SQLAlchemy filter generation from Strawberry inputs.
- **BaseRepository** — generic async CRUD with soft-/hard-delete and lifecycle hooks.
- **Relay pagination** — `OptimizedListConnection`, `Edge`, `PageInfo`, `SliceMetadata`.
- **ListResult** — `items + total_count` wrapper type.
- **BaseNodeType** — Strawberry Relay `Node` with UUID id.
- **Mapping helpers** — `map_sqlalchemy_to_type`, `map_sqlalchemy_list_to_types`.
- **Filtering inputs** — `IDFilter`, `StringFilter`, `IntFilter`, `BooleanFilter`, `DateTimeFilter`, `EnumFilter`.
- **Access-control filters** — `AccessControlFilter`, `AccessControlMeta`.
- **Models** — `Base` declarative base with UUID PK, `created_at`, `updated_at`.
- **Utilities** — `camel_to_snake`, `DateTimeProcessor`, `Ordering` enum, `NotFoundError`.
- **Permissions module** — `IsAuthenticated`, `RolePermission`, `OwnerPermission`, `ObjectAccessPermission`, `BasePermissionResolver`, `ResourceInstances`, input parsing helpers, `fetch_and_check_permissions`.
- **Schema module** — `BaseSchema` Pydantic base with `dump_for_db()`, `to_type()`, and skip-unloaded-relationships validator.
- **CI workflow** — lint, test, build via GitHub Actions.

[Unreleased]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Alteian/strawberry-alchemy/releases/tag/v0.1.0
