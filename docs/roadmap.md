# Roadmap

## Done (through 0.7.x)

See [CHANGELOG](https://github.com/Alteian/strawberry-alchemy/blob/master/CHANGELOG.md)
for the full history. Highlights:

- **0.2.x** — OR/AND semantics, typed selection, blog example, per-call
  `access_filter`, QueryAnalyzer timing, `CUSTOM_FILTERS`
- **0.3.0** — `AnnotateAncestry`, `DeletionReport` / `strict`, soft-delete helpers,
  JSONB operators
- **0.4.0** — Postgres RLS session GUC helpers
- **0.5.x** — nested relation ACL, JSONB key filters + selection trim, Postgres CI,
  `prepare_mutation_resources`, GlobalID encode registry, MkDocs,
  QueryAnalyzer `on_report`, nested schema→type conversion
- **0.6.0** — `BaseSchema.from_input` / `schema_from_input`
- **0.7.x** — `RelationAccessFilter` (+ `foreign_key=`), `PrefetchRelated.access_filter`,
  `DateFilter`, FilterBuilder boolean/`isnull` coercion fix
- **0.8.0** — `NodeConfig` / `MaxItems` / `NestedListResult` nested to-many caps
  (default 100, `has_more`, field-level overrides, composite PK)
- **0.9.1** — mutation payload resolve: `target_field_path` + `acquire_lock=False`,
  `resolve_mutation_node` helpers

## Later

- Optional OpenTelemetry auto-instrumentation beyond the `on_report` callback
- More Relay cursor edge-case and permissions mutation e2e coverage as consumers
  surface gaps
- CI job to deploy MkDocs to GitHub Pages on release (manual `mkdocs gh-deploy`
  works today)
