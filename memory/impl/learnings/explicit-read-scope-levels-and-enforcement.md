# Explicit read-scope levels, plane enforcement, and the session-binding gap

Captured from the spec discussion (2026-07-21) refining the parked recall/group-read spec ([plan](../../plan/recall-ergonomics-and-group-read-spec.md)). Related: [multi-tenancy isolation](./multi-tenancy-isolation-dsn-and-rls.md), [scoping v2](./memory-v2-scoping-attribution-and-oidc.md).

## The core redesign (Option A, approved direction)

The current `agent` read level means two things depending on posture: the agent's whole pool (identity off) or a silent `{agent_id, user_id}` narrowing (identity on, via `user_scoping_required`). The redesign makes the level name the visibility, with no posture-dependent meaning changes:

| Level | Meaning (invariant) | Auth ON data plane | Auth OFF data plane |
|---|---|---|---|
| `session` | this conversation (principal-bound when a principal is present) | yes | yes |
| `agent-user` | this agent × verified user | yes | rejected at reconcile |
| `user` | verified user across agents | yes | rejected at reconcile |
| `agent` | this agent's whole pool | admin-only | yes (no user boundary exists) |
| `store` | everything on the store (rename of `group`) | admin-only | admin-only |

A level never changes meaning; posture changes only which levels an agent config may use, enforced loudly at reconcile (extending the existing `user`-posture check). `user_scoping_required` dies; the narrowing becomes the `agent-user` level's definition.

## The enforcement model (grants gate doors, the service gates questions)

- The user→agent and agent→store AccessGrants authorize reachability only; they say nothing about request parameters.
- Parameter policy lives in the memory service, keyed on the identities the gateway attaches (same pattern as the ADR 0006 write-path 403s): a request carrying an agent actor context is data-plane and may only use `session | agent-user | user`; `agent` and `store` are refused on it regardless of grants.
- The PDP requires a valid actor token on internal hops, so every gateway-path request necessarily carries the data-plane marker; under strict NetworkPolicy the gateway is the only network path to the store. The only actor-context-free path is `kubectl port-forward`, which traverses the API server and is gated by Kubernetes RBAC. That remainder is the admin plane.
- The admin plane is purely conceptual: same service, same endpoints; "admin-only" means "refused on actor-context requests". Admin trust = namespace RBAC, the same privilege class that could read the store's DSN secret or PVC.
- Non-strict clusters lose the positional separation; compensating control is an opt-in ServiceAccount TokenReview (audience-bound) on admin-level requests.

## The session-binding gap (found during this discussion; easy fix)

The service receives the principal on every session read but its lookup filters by session id alone (`search_filters` SESSION: `{"user_id": "*", "kaos_run": sid}`; conversational key `group|run`), so the principal is never checked against stored rows. Legitimate traffic is unaffected (the runtime always derives the session id from the live conversation), but a compromised container crafting a raw body with a guessed or leaked session id could read another user's session tier. Rows already carry full attribution (erasure indexes on it), so the fix is one added predicate: when a principal is present, require it to match; return empty on mismatch (consistent with reads, unlike the loud write 403s). Principal-less admin reads stay unchanged, so the CLI needs no new mandatory flag; optionally the CLI may later accept `--session` plus `--user` together for narrowed inspection.

## Compromised-container blast radius (established during the walkthrough)

- A bare user token cannot reach the store (internal hops require an actor; strict network admits only Envoy).
- An agent credential reaches only the stores that agent is granted, and within them only partitions derivable from its own identity; autonomous self-subjecting means its principal is itself, so `user`-level reads resolve to its own pool, never a human's.
- In-flight user tokens passing through a compromised container remain harvestable for their TTL; a property of any service architecture, not memory-specific.
- With the session binding added, every data-plane level is principal-bound and the model is watertight under strict posture; strict posture is the default a secured install already implies.

## Consequences for the parked spec

- Q1 resolved: keep group as whole-store view, no group ownership reintroduction; renamed `store`, admin-only.
- Q2 simplified: `MemoryStore.spec.allowedReadScopes` (default `[session, agent-user, user]`) becomes a store-owner policy knob (chiefly whether agents may take the cross-agent `user` view), reconcile-enforced with service-side depth, no longer a leak preventer.
- Q3 original consent knob: explicitly deferred; visibility plus store-owner control cover the near-term concern.
- Q6 closed: no admin write command.
