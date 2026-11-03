# Postgres RLS session context

strawberry-alchemy does **not** invent `CREATE POLICY` DDL. Policies stay
app-owned. This package sets transaction-local GUCs that policies can read via
`current_setting(...)`.

Python `AccessControlFilter` remains available as optional defense-in-depth.

## Helpers

```python
from strawberry_alchemy import apply_rls_context, clear_rls_context, set_rls_guc

# After acquiring a session / starting a transaction:
await apply_rls_context(session, {
    "user_id": str(info.context.identity.id),
    "tenant_id": str(info.context.identity.tenant_id),
})
# → SELECT set_config('app.user_id', '...', true);  (is_local=true)
# → SELECT set_config('app.tenant_id', '...', true);

await set_rls_guc(session, "role", "admin")          # app.role
await clear_rls_context(session, ["user_id", "role"])
```

Names without a dot get the `app.` prefix (override with `prefix=`).

## Typical GraphQL wiring

Call `apply_rls_context` once when the request opens its DB session (context
factory / middleware), **before** resolvers run. Use the same transaction the
optimizer and repository share so `SET LOCAL` applies to every query.

## Example policy (app-owned)

```sql
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE posts FORCE ROW LEVEL SECURITY;

CREATE POLICY posts_owner ON posts
  USING (user_id::text = current_setting('app.user_id', true));
```

Use a non-bypass role for the application connection so RLS is enforced.

## Testing

CI uses sqlite and does not execute `set_config`. Unit tests mock
`session.execute`. Integration against a real Postgres is left to consuming apps.
