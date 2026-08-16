# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Alteian/strawberry-alchemy/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Alteian/strawberry-alchemy/releases/tag/v0.1.0
