# KAOS security & identity ADRs — high-level components

This document opens a **fresh, simplified** architecture-decision phase for KAOS identity and authorization. It supersedes the earlier `adr-kaos/` and `adr-aib/` sets, which are kept only as historical record (see [Evolution](#evolution-what-changed-and-why)). The research stages ([research/001](../research/001-initial-aib-kaos-usefulness.md) through [research/008](../research/008-pre-design-gap-analysis.md)) and the target picture ([target-picture/007](../target-picture/007-decision-identity-model-and-source-of-truth.md)) established the problem space; the parity and OAuth-path facts that anchor these decisions are recorded in [the model-parity learnings](../impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md). This index decomposes the settled design into the **components that each require an ADR**, so the design stays small and coherent.

The intent is deliberately coarse: four bundled components rather than many narrow records. Each becomes one ADR, and this document is the index that anchors them.

## Evolution — what changed and why

The earlier ADR set assumed two AIB capabilities that KAOS no longer builds against: a standalone **ext_authz access-check decision service** (AIB PR #398) and a separate **Python SDK** (AIB PR #399). Both are abandoned. AIB `main` now embeds **OPA inside its ext_proc token-exchange filter** (AIB #222), so a single gateway hook does both token-exchange and authorization. This collapses the previous "gateway ext_authz + separate decision service" topology into one enforcement point and removes the upstream-SDK track entirely (the runtime token client is vendored in KAOS and folds into the KAOS Python SDK — see [followups](../plan/followups.md)). The ADRs below are written from scratch against this reality rather than patched onto the old records. The superseded records remain in `adr-kaos/` and `adr-aib/` for provenance; a short historical note is folded into [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md).

KAOS is in **alpha**, so these ADRs elect clean breaks over backward compatibility where useful, and do not document migrations.

## Components requiring an ADR

### 1. Enforcement topology and policy engine — [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md)

- **Scope.** Where the authorization decision is made and by what engine: OPA embedded in AIB ext_proc (#222) as the single decision point for both authorization models, invoked on the gateway request path via the ext_proc `EnvoyExtensionPolicy`; the fact-source surface OPA sees; the fate of the standalone ext_authz `SecurityPolicy` (retained as an optional, default-off generic seam rather than deleted, so a KAOS-run OPA can enforce in AIB-less/standalone setups); policy/data reload posture; and the **G1 autonomous gap** (OPA only runs when a subject bearer is present).
- **Key decisions.** One engine, one hook, both models; ext_authz generalised (not removed); coarse granularity; static rego with hot-reloadable data deferred; autonomous-mode enforcement deferred as unsupported.

### 2. Identity and authentication — [ADR 0002](./adr_0002_identity-and-authentication.md)

- **Scope.** The one logical identity that threads agents, resources, AIB records, OPA data keys, and token subjects; the two token dimensions (user **subject** token via Keycloak OIDC, agent **actor** token via AIB `client_credentials`); the trust model for the actor token (real signed JWT, not header-trust) and its **optional, config-gated signature verification** (demo vs verified posture); and where token issuance comes from today (AIB-only) with an AIB-less issuer deferred.
- **Key decisions.** Single logical-identity contract; subject already gateway-verified, actor verification added via rego JWKS (V1) or gateway JWT provider (V2); demo mode is spoofable and non-production; AIB-less issuer is a followup.

### 3. Authorization models and policy data — [ADR 0003](./adr_0003_authorization-models-and-policy-data.md)

- **Scope.** The two authorization models and their **full parity**: Model 1 (KAOS-owned OPA data keyed by actor identity, grant graph derived from CRDs in `data.kaos.grants`) and Model 2 (broker permission-sets with `granted_permission_sets` from token-exchange); the four simultaneous fact sources that give both models parity on "can user A reach resource X via agent B"; coarse granularity; and the **populator / source-of-truth modes** (default CRD projection, Model-1 manual variants M1-a and M1-b, Model-2 external off-switch) with the prune-safety invariant and the published `data.kaos.grants` schema.
- **Key decisions.** Both models in scope; parity by construction; coarse only; CRD projection is the authoritative default with explicit manual overrides; external/manual modes never clobber admin-owned config.

### 4. Component architecture and projection — [ADR 0004](./adr_0004_component-architecture-and-projection.md)

- **Scope.** Folding the standalone sync-service into the operator as a **whole-world projection controller**; two-controller failure isolation (workload reconciler never calls AIB; projection reconciler is the sole AIB caller, ConfigMap writer, and credential minter); the shared projection core (`Project() → DesiredState`) with the Model-2 AIB-admin adapter as the **only bespoke integration** and the Model-1 emitter as a pure serialisation step; prune/GC strategy; and the ConfigMap-plus-`policy.path` data-delivery posture.
- **Key decisions.** One binary, typed CRD inputs; shared pure core, thin per-model adapters; whole-world sweep for AIB records plus owner-reference GC for credential Secrets; broker outage stalls only projection, never workloads.

## Cross-cutting concerns

- **Framework enablement.** Chart values and CLI flags (`kaos system install`) select the model(s), enforcement posture, verification mode, and populator mode. Each ADR states the surface it exposes; the concrete flags are settled in the [plan](../plan/proposed-split.md).
- **Testing, docs, examples.** Every mode (both models, demo vs verified, manual overrides, off-switch) is covered by tests, documented with worked examples, and the `data.kaos.grants` schema is published. Manual-override tests must prove the operator leaves admin-owned config untouched across reconciles.
- **Prune-safety invariant.** Apply and prune are mode-gated; external and manual modes never prune or clobber admin-owned configuration. Stated in [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) and realised in [ADR 0004](./adr_0004_component-architecture-and-projection.md).

## Dependency and sequencing

The components form a chain: [ADR 0001](./adr_0001_enforcement-topology-and-policy-engine.md) fixes where and by what the decision is made; [ADR 0002](./adr_0002_identity-and-authentication.md) fixes who the subjects and actors are and how they are trusted; [ADR 0003](./adr_0003_authorization-models-and-policy-data.md) fixes what facts the policy reads and who owns them; [ADR 0004](./adr_0004_component-architecture-and-projection.md) fixes how KAOS produces and delivers those facts. Authoring and implementation order is 1, 2, 3, 4, with cross-cutting concerns settled inside each.

## ADR conventions

- New records live in this folder as `adr_NNNN_slug.md`, mirroring the memory ADR set ([memory/adrs](../../memory/adrs/adr_high_level_components.md)). The `adr-kaos/` and `adr-aib/` prefixes are frozen historical sets.
- Cross-reference every other ADR as a Markdown link. No hard line wraps inside paragraphs or list items (see [CONVENTIONS](../CONVENTIONS.md)).
- Each ADR records what was chosen, why, and the consequences, citing research and learnings rather than repeating them.
