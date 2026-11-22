# Postgres RLS session context

strawberry-alchemy does **not** invent `CREATE POLICY` DDL. Policies stay
app-owned. This package only sets transaction-local GUCs that policies can read
via `current_setting(...)`.

Row SQL ACL via `AccessControlFilter` is a separate layer — many apps use both
(Alchemy filters for GraphQL-shaped rules, Postgres RLS as a hard tenancy
boundary). See [Recipes](recipes.md#app-tenancy-vs-alchemy-acl).

## Helpers

```python
from strawberry_alchemy import apply_rls_context, clear_rls_context, set_rls_guc

# Single setting (becomes app.company_id unless name already contains a dot)
await set_rls_guc(session, "company_id", str(company_id))

# Batch
await apply_rls_context(session, {"company_id": company_id, "user_id": user_id})

# Clear (sets NULL locally)
await clear_rls_context(session, ["company_id", "user_id"])
```

All use `set_config(..., is_local=true)` so values do not leak past the
transaction. Target may be an `AsyncSession` or `AsyncConnection`.

Default prefix is `app` (`DEFAULT_GUC_PREFIX`). Pass `prefix=` to override.
Bare names become `app.<name>`; dotted names are used as-is.

## Sample policy

```sql
ALTER TABLE employment ENABLE ROW LEVEL SECURITY;

CREATE POLICY employment_tenant ON employment
  USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid);
```

Application code at the start of a request / unit of work:

```python
async with session.begin():
    await apply_rls_context(session, {"company_id": ctx.company_id})
    ...
```

## CI

Postgres-backed tests live under `tests/postgres/` and run with
`make test-postgres` (GitHub Actions Postgres 16 service in CI).
