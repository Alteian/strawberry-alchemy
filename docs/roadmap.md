# Roadmap

## Done in 0.2.0–0.5.0

See [CHANGELOG](https://github.com/Alteian/strawberry-alchemy/blob/master/CHANGELOG.md) for the full history. Highlights:

- **0.2.x** — dep floors, OR/AND semantics, typed selection, blog example, mypy hard gate,
  per-call `access_filter`, QueryAnalyzer timing.
- **0.3.0** — `AnnotateAncestry`, `DeletionReport` / `strict`, soft-delete helpers, JSONB lookups.
- **0.4.0** — Postgres RLS session GUC helpers.
- **0.5.0** — nested relation ACL on `selectinload`, maxxus-shaped JSONB key filters + selection
  trim, real Postgres CI, `prepare_mutation_resources`, GlobalID encode registry, coverage gate,
  MkDocs, QueryAnalyzer `on_report` hook, docs honesty.

## Later

- Published docs site hosting (GitHub Pages / Read the Docs) from the MkDocs build.
- Broader mutation helper ergonomics (resolver integration beyond `prepare_mutation_resources`).
- Optional OpenTelemetry auto-instrumentation beyond the `on_report` callback.
- More Relay cursor edge-case and permissions mutation e2e coverage as consumers surface gaps.
