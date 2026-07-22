# Multi-tenancy isolation: cross-store DSN vs intra-store RLS

Captured while answering a reader question on the memory blog (Alexander: "isn't app-level `WHERE tenant_id = X` fragile? couldn't RLS enforce it on the DB side?"). Verified against KAOS source before asserting. Feeds the isolation framing for the memory blog (part 2/3). Related: [scoping/attribution](./memory-v2-scoping-attribution-and-oidc.md).

## The two isolation boundaries are different mechanisms

They are **not** alternatives for the same thing — they protect different boundaries:

- **Between MemoryStores** → connection / **DSN** level.
- **Within one MemoryStore** (agent × user × session) → app-level `WHERE scope_key`, hardenable with **RLS**.

## Intra-store: app-level `WHERE scope_key` on fixed tables

- Short- and medium-term tiers are **fixed-name tables** — `short_term_memory_window`, `medium_term_memory_summaries` (`kaos-memory/kaos_memory/stores.py:144,154`) — with a `scope_key` column, filtered by `WHERE scope_key = ?` on every read/write/delete (`stores.py:281,319,344`).
- The vector tier goes through **Mem0**, which pre-filters by scope **metadata** inside the vector query (not a DB predicate).
- `scope_key` is hierarchical: `ScopeLevel` = `AGENT` / `USER` / `GROUP` / `SESSION` (`kaos-memory/kaos_memory/contract.py`).

This is the tier where the "forgotten predicate leaks" risk actually lives.

## Cross-store: it is the DSN, NOT "different tables in the same DB"

Correction to an earlier framing ("same instance, same db, different tables"): the code does **no per-store table/collection namespacing**.

- Each `MemoryStore` CRD → the operator deploys **its own memory-service Deployment** (`operator/controllers/memorystore_controller.go`, `constructDeployment`), wired with its own `KAOS_MEMORY_EXTERNAL_DSN` (external/pgvector) or its own PVC (local).
- Table names are hardcoded and `collection_name` defaults to `"kaos_memory"` with no per-store derivation (`kaos-memory/kaos_memory/config.py:37,39`). Two stores pointed at the **same** DSN would land in the **same** tables and only be separated by `scope_key`.
- So real cross-store isolation is **connection-level**: point stores at different databases (often same instance) or different instances via their DSN. External mode is **bring-your-own-DSN** per store (from a Secret, `ConnectionSecretRef`).

Blog framing: *"a store maps to a connection/database, not a table; multi-tenancy is a control-plane dial — shared-instance-different-DB → separate-instance."*

## RLS as the intra-store hardening (relational tiers only)

RLS is the right tool for the `WHERE scope_key` risk, and it's cheap on the relational tiers:

```sql
ALTER TABLE short_term_memory_window ENABLE ROW LEVEL SECURITY;
ALTER TABLE short_term_memory_window FORCE  ROW LEVEL SECURITY;   -- owner would otherwise bypass
CREATE POLICY scope_iso ON short_term_memory_window
  USING      (scope_key = current_setting('kaos.scope', true))
  WITH CHECK (scope_key = current_setting('kaos.scope', true));
```

```python
with self._conn.transaction():
    self._conn.execute("SELECT set_config('kaos.scope', %s, true)", (scope_key,))  # true = LOCAL to txn
    self._conn.execute("INSERT INTO short_term_memory_window ...")
```

Effort: small (migration + `set_config` wrapper + a non-owner DB role). The tables are plain psycopg on one connection (`stores.py:177`), so this is the easy case.

### Gotchas
1. **Owner/superuser bypass** — `ENABLE` alone is bypassed by the table owner; add `FORCE` and connect as a **non-owner** role.
2. **Pooling** — always `SET LOCAL` inside a transaction so scope can't bleed across reused connections.
3. **Scope levels** — exact-equality RLS works only if reads and writes happen at the same level; a read that aggregates *across* levels (e.g. USER wanting all its sessions) needs prefix logic. **Open question to confirm before writing the policy.**

### Vector tier caveat
**Mem0 owns the pgvector connection** and filters by metadata, not a DB session variable — so DB-enforced RLS isn't practical there without wrapping/forking Mem0. That tier stays application-scoped (metadata pre-filter) unless we invest in the plumbing. Be honest about this in the blog.

## Bottom line for the blog
- DSN isolation (between stores) is essentially free and already the model — but does nothing for the intra-store risk.
- RLS (within a store) is the right, cheap hardening on the **relational** tiers; the **vector** tier remains app-scoped.
- Not implemented today — the code trusts the `WHERE`. Frame RLS as recommended hardening, not shipped.
