# ADR 0006 — Posture-derived scope enforcement and read-only agent scope configuration

- **Status.** Proposed
- **Date.** 2026-07-19
- **Depends on.** [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), [ADR 0003](./adr_0003_memory-interface-and-runtime-data-plane.md), [ADR 0005](./adr_0005_multi-tenancy-agent-grouping-and-governance.md), the memory scoping v2 implementation ([learnings](../impl/learnings/memory-v2-scoping-attribution-and-oidc.md))
- **Revises.** The Agent-level `scope` field from ADR 0005 and the write-level portion of the operation contract from ADR 0003.

## Context

Memory scoping v2 replaced single-owner writes with compound attribution: every write attaches every owner key the request context verifiably has (verified user principal, qualified agent identity, session, store group), and reads select one level. Under that model the Agent-level `scope` field retains only two roles: it names the owner key whose absence fails the operation closed, and it seeds the default read scope. The first role duplicates platform knowledge. The operator already knows the cluster's security posture (whether user auth and agent auth are enabled) and already injects `MEMORY_USER_SCOPING=required` when user identity is on, overriding the agent's own declaration. Letting each Agent also declare an identity requirement invites two failure shapes: an agent that under-declares (`scope: session` on a secured cluster, silently skipping an identity check the platform could make) and an agent that over-declares (`scope: user` on a cluster with no user identity, failing at runtime for a reason visible at deploy time).

Autonomous execution removes the last argument for per-agent variation. A self-initiated iteration runs under `autonomous_identity_context`, which self-subjects the agent: the agent's qualified identity is the principal and its minted token is the subject token. Every execution path on a secured cluster therefore carries a verifiable principal — the user's subject for user-originated requests, the agent's own identity for autonomous ones — so a uniform requirement holds with no special case.

## Decision

### Enforcement follows cluster posture, not agent declaration

The identity requirements for memory operations are derived from the cluster's security posture and enforced by the platform:

- **User auth enabled**: every memory operation must carry a verified principal. User-originated requests satisfy this with the gateway-verified subject; autonomous runs with the agent's self-subject.
- **Agent auth enabled**: every memory operation must carry a stable, qualified agent identity.
- **Neither enabled**: operations carry whatever attribution exists; nothing is required beyond the session key for conversational tiers.

The operator projects the posture into the MemoryStore and agent runtimes (generalising today's `MEMORY_USER_SCOPING` into a posture block); the memory service validates attribution completeness on every operation as the authoritative check, and the client-side fail-closed derivation remains as defence in depth. Agents cannot widen or narrow the requirement.

### The Agent memory block configures reads only

The Agent-level `scope` field is removed. The block keeps exactly the client-side concerns:

```yaml
memory:
  memoryStore: support-memory
  defaultReadScope: user       # what automatic recall injects each turn
  readScopes: [session, user, group]   # what search_memory may be asked to search
  tools: read
```

`MemoryStore.defaultScope` is renamed `defaultReadScope` and provides the store-wide default for bound agents that set nothing; the final fallback is `session`. The rename questions for the old field (`homeScope`, `ownerScope`) dissolve with the field.

### Writes carry identities, reads carry a level

The service write contract drops the scope level: a write carries the attribution identities only, which is what compound attribution already made true in practice (the level on a write performed validation, never routing). Reads keep the single-level scope policy unchanged. Erasure and admin operations keep their explicit scope arguments unchanged.

## Consequences

- Deploy-time honesty: a read configuration referencing `user` on a cluster without user identity is rejected by the operator at apply time instead of failing at runtime.
- The sample and worked example simplify: `user-assistant` and `session-assistant` differ only in read configuration, which is the true difference under v2; identity requirements come from the cluster, the same for both.
- The autonomous path needs no carve-out: self-subjecting already satisfies the uniform requirement.
- Migration is a breaking `v1alpha1` change to the Agent CRD (field removal), the MemoryStore CRD (rename), the service write API (level removal), and the operator projection; docs, samples, CLI tests, and the blog worked example follow. The blog re-capture planned for the merged CLI stack absorbs the example changes.

## Rejected alternatives

- **Rename `scope` to `homeScope` and keep it configurable.** Keeps duplicated authority: the platform still overrides the write-side meaning whenever posture demands it, leaving a field whose effective behaviour depends on settings elsewhere.
- **Enforce per-store instead of per-cluster (a MemoryStore-level requirement toggle).** The store does hold the validation, but letting each store choose its requirement re-creates the under/over-declaration mismatch one level up; posture is a cluster property.
- **Keep the write-level in the API as documentation.** A field that neither routes nor validates invites the next misreading; the v2 semantics deserve an API that states them.
