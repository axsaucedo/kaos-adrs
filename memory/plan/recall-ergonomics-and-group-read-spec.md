# Working spec: recall ergonomics and read-scope model (DRAFT)

Status: decided in discussion, not yet implemented. Implementation explicitly on hold; do not start executors on this until approved. The Codex brief for the ergonomics half exists at `kaos/tmp/brief-recall-ergonomics.md` and must be updated to match part B before running. Related learnings: [explicit read-scope levels and enforcement](../impl/learnings/explicit-read-scope-levels-and-enforcement.md), [multi-tenancy isolation](../impl/learnings/multi-tenancy-isolation-dsn-and-rls.md), [scoping v2](../impl/learnings/memory-v2-scoping-attribution-and-oidc.md).

## Part A — recall ergonomics (decided earlier)

1. Response keys become self-describing and flat: `facts` -> `long_term_facts`; `medium_term.summary` -> `medium_term_summary` (string); `short_term.recent` -> `short_term_window` (list of [role, content]). `block` and `degraded` keep their names. A tier's key is present only when requested.
2. Tier selection through one option: `--include` accepting `a|all|s|short-term|m|medium-term|l|long-term`, repeatable and comma-splitting, defaulting to `all`. Wire: `include: [...]` list replaces `include_short_term`; the service fetches only requested tiers (short and medium share the conversational store, so selective fetch is two queries on one backend).
3. Query optional: `--query` present means semantic recall (`/v1/recall`); absent means list (`/v1/list`). `--all` and `--short-term` flags are removed. `--query` without long-term in `--include` is an error.
4. The automatic baseline recall in the runtime keeps requesting all tiers; agent behaviour unchanged.

## Part B — read-scope model (decided in this discussion)

### B1. A three-level principal-bound hierarchy on the data plane

Read levels are concentric radii of one always-principal-bound view. The level chooses the radius; the identity always comes from the gateway-verified headers, never from the request body.

```
session  ⊂  agent  ⊂  user
```

| Level | Meaning (invariant) | Auth on | Auth off |
| --- | --- | --- | --- |
| `session` | the current conversation | current agent × user × session | current agent × session |
| `agent` | this agent's memory of the current verified context | current agent × user | this agent's whole pool (no user boundary exists) |
| `user` | the current verified user across all agents on the store | current user across agents | rejected at reconcile (no user identity) |

- `agent` narrows to `{agent, user}` when user identity is on because the verified context includes the user; it is the pool only when there is no user identity to bind to. Same word, one documented meaning, no env-driven surprise.
- `user` stays in the vocabulary always; configuring it on an identity-less cluster is rejected at reconcile with a clear posture message (extends today's existing check). Loud failure, not silent no-op.
- Cross-user levels (`agent`-as-pool-across-users, and the whole-store view) are NOT data-plane levels; see B4.

### B2. Session reads bind to the principal (gap fix)

Today the service receives the principal on every session read but filters by session id alone (`search_filters` SESSION returns `{"user_id": "*", "kaos_run": sid}`; conversational key is `group|run`), so the principal is never checked against stored rows. Fix: when a principal is present on the request, AND it into the session-level predicate; return empty on mismatch (consistent with reads, unlike the write-path 403s). Legitimate traffic is unaffected (the runtime derives the session id from the live conversation). Principal-less admin reads stay unchanged, so no new mandatory CLI flag. `user_scoping_required` is removed; the `{agent, user}` narrowing becomes the definition of `agent` under identity.

### B3. Ceilings instead of sets

Because the levels are totally ordered, entitlements collapse from set-membership lists to a single maximum:

- Agent: `maxReadScope` (one of `session|agent|user`) replaces the `readScopes` list. The `search_memory` tool enum becomes every level up to and including the max. `defaultReadScope` must be `<= maxReadScope`.
- MemoryStore: `maxReadScope` (default `agent`) replaces the proposed `allowedReadScopes`. A store owner raises it to `user` to permit cross-agent reads; an agent's `maxReadScope` may not exceed the store's. This is the answer to "should we even allow user": only where the store owner raised the ceiling.
- No set-membership CEL; simpler validation and a cleaner boundary demo (an agent capped at `session` versus one at `user`).

### B4. Enforcement model (grants gate doors, the service gates questions)

- The user->agent and agent->store AccessGrants authorize reachability only; they say nothing about request parameters.
- Parameter policy lives in the memory service, keyed on identities the gateway attaches (same pattern as the ADR 0006 write-path 403s): a request carrying an agent actor context is data-plane and may only use `session|agent|user` within the effective ceiling; admin-only levels are refused on it regardless of grants.
- The PDP requires a valid actor token on internal hops, so every gateway-path request carries the data-plane marker; under strict NetworkPolicy the gateway is the only network path to the store. The only actor-context-free path is `kubectl port-forward`, which traverses the API server and is gated by Kubernetes RBAC. That remainder is the admin plane.
- The admin plane is purely conceptual: same service, same endpoints; "admin-only" means "refused on actor-context requests". Admin trust = namespace RBAC, the same privilege class that could read the store's DSN secret or PVC. Admin-only levels: `agent`-pool-across-users and `store` (see B5); the admin CLI is where whole-store inspection and erasure live.
- Non-strict clusters lose the positional separation; compensating control is an opt-in ServiceAccount TokenReview (audience-bound) on admin-level requests, default off (strict posture already closes the route).

### B5. Rename `group` -> `store`

The whole-store view is renamed `store` ("everything on the store"), admin-plane only, and is the rename of today's `group` level. `kaos_group` stays as internal metadata. This kills the identity-group vs memory-group conflation: identity groups (token `groups` claim, AccessGrant entry) and the memory store are now lexically distinct.

## Resolved questions

- **Group ownership:** not reintroduced; the store view is the whole-store admin read, not a publication partition.
- **Store ceiling:** becomes `MemoryStore.spec.maxReadScope` (default `agent`), reconcile-enforced with service-side depth.
- **Per-user consent knob:** explicitly deferred; visibility plus the store ceiling cover the near-term concern.
- **Admin write command:** not added; no data-plane story requires seeded shared knowledge.

## Worked-example rework (still to propose in detail; tracked separately)

Part 2/4 of the blog reworks to bob writing through the agent (mutual isolation: alice's recall lacks bob's facts and the reverse; forget stops at the principal), the whole-store view shown once as an explicit admin (`kaos memory recall --scope store`), and the sample AccessGrant granting `kind: User` subjects (alice, bob) rather than the `researchers` identity group. Needs a targeted re-capture. Detailed proposal pending.

## Terminology note

Two unrelated "groups" existed and must never be conflated: identity groups (token `groups` claim, AccessGrant entry authorization) and the memory store (formerly the `group` scope, now `store`).

## Migration surface (for the eventual brief)

Breaking `v1alpha1` change, same class as ADR 0006. Touches: `ScopeLevel` semantics (`agent` redefined, `user_scoping_required` removed, `group`->`store`), the Agent CRD (`readScopes` list -> `maxReadScope`), the MemoryStore CRD (`maxReadScope`), the service (session-principal predicate, admin-plane level gating, `store` rename), the runtime and `search_memory` enum, the admin CLI (`--scope store`, optional `--session`+`--user`), plus Part A's response-key and `--include` changes. Docs, sample, and the worked example follow.
