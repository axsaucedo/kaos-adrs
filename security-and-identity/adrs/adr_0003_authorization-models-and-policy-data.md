# ADR 0003 — Authorization models and policy data

- **Status.** Accepted
- **Date.** 2026-07-07
- **Component.** 3 of 4 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md), [ADR 0002](./adr_0002_identity-and-authentication.md), [model-parity learnings](../impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md)
- **Resolved by.** [ADR 0004](./adr_0004_component-architecture-and-projection.md) (who produces and delivers the data)

## Context

The engine and hook are fixed ([ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md)) and the identities are fixed ([ADR 0002](./adr_0002_identity-and-authentication.md)). What remains is the authorization content: which grant facts OPA reads, who owns them, and how a deployment can override the default source of truth. Two models were validated: a KAOS-owned data model keyed by the actor identity, and a broker-owned permission-set model returned by token-exchange. This ADR commits both, establishes their parity, and settles the source-of-truth (populator) modes.

## Decision

### Both models are in scope, at coarse granularity

- **Model 1 — KAOS-owned OPA data.** A generic static rego keys on the actor identity ([ADR 0002](./adr_0002_identity-and-authentication.md)) and reads a grant graph KAOS derives from CRDs (agent network access edges, MCP server references, model-API references), delivered as `data.kaos.grants`. Model 1 is decoupled from the broker admin model and matches the validated experiment.
- **Model 2 — broker permission-sets.** KAOS projects services, permission-sets, and agents into the AIB admin model; token-exchange returns `context.granted_permission_sets`; the rego checks the requested resource against the granted sets. The broker is the source of truth for authorization content.

Both enforce at **coarse** granularity (subject × actor × resource), never MCP tool-level.

### Parity by construction

Because the OPA input carries all four fact sources at once ([ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md)), the two models differ **only in where the grant facts live** — KAOS CRD-derived static data versus broker permission-sets — not in what can be expressed. Both can key on subject **and** actor **and** resource, so **"can user A reach resource X via agent B?"** is answerable by either model with the same mechanism (the validated experiment keyed only on the actor, but adding the subject dimension is a data-shape and rego change, not a new mechanism). This parity is a first-class requirement, not an accident: neither model is a coarser subset of the other.

Both inherit the **G1 autonomous gap** from [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md): enforcement requires a subject bearer, so pure-autonomous flows are unprotected in this version.

### Populator / source-of-truth modes

The **default and authoritative** source of truth is **CRD projection (P-crd)** for both models: KAOS reads the CRDs and produces the grant facts. Explicit manual overrides are in scope for alpha (breaking changes are acceptable):

- **Model 1 — M1-a, bring-your-own ConfigMap.** The operator points `policy.path` at an admin-provided ConfigMap (rego plus data) and does not manage its contents. Trivial, no schema lock-in.
- **Model 1 — M1-b, operator-rego plus admin data.** The operator owns the `policy.rego` key (server-side-apply field ownership) while the admin authors the `data.kaos.grants` key. There is no active prune for Model-1 data (nothing to delete; the operator simply does not write the data key, so it never clobbers admin content). Alpha accepts **freezing the `data.kaos.grants` schema as a published public contract**.
- **Model 2 — external off-switch.** Authorization projection is disabled and prune is **forced off**; the admin configures grants in the AIB UI, and enforcement reads AIB live via token-exchange `granted_permission_sets` (no KAOS mirror). KAOS still owns **identity** (agent registration and the credential Secret). The seam is clean: KAOS owns identity, AIB owns authorization.

### Prune-safety invariant

Apply and prune are **mode-gated from the start**. External and manual modes must **never** prune or clobber admin-owned configuration. Model 2's projection prune is an active delete sweep and must be gated off in the external off-switch; Model 1 has no delete step (it only skips writing the data key). Tests must prove the operator leaves admin-owned data untouched across reconciles.

### Published schema and documentation

The `data.kaos.grants` schema (and the `data.kaos.jwks` verification key surface from [ADR 0002](./adr_0002_identity-and-authentication.md)) is **published** as a public contract, and every mode ships with worked examples and tests.

## Consequences

Positive: both models are supported without divergent engines, and parity means a deployment can switch source-of-truth without losing the "user A via agent B" question; the CRD-default-plus-manual-override design lets platform teams keep KAOS authoritative or hand authorization to AIB/infra without special cases; the prune-safety invariant prevents the operator from destroying hand-authored policy. Negative: committing to a published `data.kaos.grants` schema is a contract cost (mitigated by alpha's freedom to break); supporting four populator modes multiplies the test matrix; both models remain blind to autonomous flows (G1). Follow-on: [ADR 0004](./adr_0004_component-architecture-and-projection.md) decides who produces the data and how it is delivered and pruned.

## Alternatives considered

Model 1 only — rejected: Model 2 reuses the built broker projection and lets AIB be the authoritative UI when wanted. Model 2 only — rejected: Model 1 is broker-independent, matches the validated experiment, and is the basis for AIB-less enforcement. Position Model 2 as "user consent only" (coarser than Model 1) — rejected: the four-fact-source input gives full parity, so this framing understates Model 2. Keep source-of-truth CRD-only with no manual override — rejected: platform teams need an AIB-authoritative or infra-authoritative path, cheap to offer in alpha. MCP tool-level granularity — out of scope for this version.
