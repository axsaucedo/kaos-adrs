# Proposed work split and sequencing — security & identity phase 2

**Status**: Proposed (v1 — for review; becomes the living plan once approved)
**Date**: 2026-07-11
**Scope**: implementation phasing for [ADR 0001](../adrs/adr_0001_enforcement-topology-pdp-and-policy-delivery.md) (PDP + ext_authz + delivery), [ADR 0002](../adrs/adr_0002_agent-identity-issuers-and-aib-boundary.md) (issuers + AIB boundary), and [ADR 0003](../adrs/adr_0003_authorization-model-and-data-schema.md) (user + agent + resource model). [ADR 0004](../adrs/adr_0004_aib-token-exchange-and-consent.md) (token exchange) is adopted-but-gated and **out of scope here** — it gets its own plan (starting with its spike) after this stack ships.

---

## Purpose

This document proposes how the work is chunked and in what order. One phase = one plan-implement iteration = one PR, merged sequentially into `main`, each building on the previous. Detailed per-phase task breakdowns come after this split is approved.

Phase numbers continue the phase-1 sequence (P0–P17 shipped there); this stack is **P18–P22**.

## Guiding principles

- **Pre-alpha: redesign, don't migrate.** No backwards compatibility is kept anywhere. The phase-1 enforcement wiring (ext_proc-based authorization, the `authorization.provider` knob, AIB-as-enforcement config) is **deleted, not deprecated** — removed in the same PR that replaces it. No compatibility shims, no migration paths, no dual-mode support.
- **No historical documentation.** `docs/security/*` is rewritten to describe the new architecture as if it were the only one that ever existed. Nothing in the KAOS repo references the old design; all historical record lives in this kaos-ai-docs repo. Docs ship in lockstep inside each phase's PR, covering exactly what that phase made true.
- **Build on main.** Each phase starts from merged main (which already contains the phase-1 substrate this design keeps: gateway `jwt_authn` dual providers, `x-kaos-target-resource` stamping, the projection reconciler + policy ConfigMap, NetworkPolicy/strict-gateway, presets). What carries over is the substrate; what gets replaced is the decision point and the model.
- **Enforcement swap first, identity and model on top.** P18 swaps the decision point with the *existing* actor-only rego so it is a like-for-like enforcement change validated in isolation; the model change (P20) then lands on a proven enforcement path. One variable at a time.
- **Every phase is live-demoable in KIND** with a concrete allow/deny matrix, and CI-green before merge.

## Current-state baseline (what main has, relevant to this stack)

- Gateway `jwt_authn` with `user`/`agent` providers; per-route resource stamping; `SecurityPolicy` generation with an optional default-off ext_authz seam.
- `AuthzProjectionReconciler` producing the policy ConfigMap (`policy.rego` + `data.json`, actor-only `data.kaos.grants` + `data.kaos.jwks`), with automated/manual/operator-rego modes and never-prune.
- AIB projection adapter (registration, permission sets, credentials) and the pais propagation SDK (subject propagated unchanged, actor always local).
- `Agent.spec.autonomous` on the CRD; presets `kaos-internal`/`aib-only`/`aib-keycloak`; NetworkPolicy + `strictGatewayApi`.

## The proposed phases

### P18 — PDP and ext_authz enforcement core (ADR 0001)

**Goal**: the KAOS-run OPA is the enforcement point; the old enforcement path no longer exists.

**Scope**: chart deploys the stock-OPA PDP (separate Deployment, 2 replicas + PDB, `envoy_ext_authz_grpc`, ConfigMap volume-mounted); operator generates the ext_authz `SecurityPolicy` (gRPC, `failOpen: false`) on all internal routes, with `extAuthzUrl` defaulting to the chart's own PDP Service; `security.pdp.enabled` becomes the authorization switch. **Deleted in the same PR**: the ext_proc enforcement path, the `authorization.provider` knob, and all AIB-as-enforcement config/codepaths. The existing actor-only rego and data schema are kept unchanged — this phase swaps *where* the decision runs, not *what* it decides.

**Demoable**: granted agent→resource allowed; ungranted denied; no-token request denied (G1 closed by topology); PDP down → 403 (fail-closed); ConfigMap edit propagates within the F4 bound.

### P19 — ServiceAccount issuer and the AIB shrink (ADR 0002)

**Goal**: `kaos-internal` is a zero-external-dependency, honestly scoped agent-plane security posture.

**Scope**: the `agentAuth.identity.provider` abstraction (`serviceaccount | oidc | aib`); the ServiceAccount issuer end to end — per-agent SA projected tokens (single audience, kubelet-rotated), file-based token provider in the pais runtime, API-server JWKS injected into `data.kaos.jwks` by the projection, identity mapping (`data.kaos.agents[id].issuer_sub`); the AIB adapter reduced to credential provisioning only (registration + credential lifecycle; permission-set projection removed from the default path); the single-issuer-value F0 mechanism. Presets rewired: `kaos-internal` = SA issuer + PDP, fail-closed, no demo skips.

**Demoable**: full enforcement in KIND with no AIB and no Keycloak installed; agent tokens rotate without operator involvement; `aib`-issuer variation still passes the same matrix.

### P20 — The authorization model: subject-required conjunction and AccessGrant (ADR 0003)

**Goal**: the user + agent + resource model is live; no subject-less traffic exists.

**Scope**: the new rego — subject always required (user, or agent-identity with the CRD-projected `autonomous` flag), in-policy verification of both tokens, entry-edge vs internal-hop semantics (AccessGrant gates entry; agent grants gate movement); autonomous self-subjecting in the pais runtime (seed own token as subject at loop start); the `AccessGrant` CRD + compiler into `data.kaos.user_grants` + the `Enforced=False/NoUserIdentityProvider` status condition; `data.kaos.agents` projection; entry vs internal route policy attachment. The old actor-only rego is deleted.

**Demoable**: user with a group AccessGrant reaches the agent, user without is denied at entry; autonomous agent operates end to end self-subjected; non-autonomous agent self-subjecting is denied; internal hops carry and verify the propagated subject; AccessGrant in `kaos-internal` shows `Enforced=False` with the warning event.

### P21 — User plane completion: Keycloak preset with DCR (ADR 0002 + 0003)

**Goal**: the Keycloak-backed posture works end to end on the new stack.

**Scope**: the provider-generic `OIDCProjector` (RFC 7591/7592 DCR client-per-agent, Secret delivery, bootstrap token wiring); Keycloak preset provisioning gains the group-membership protocol mapper (and documents it as a hard requirement for bring-your-own-Keycloak); full user-plane validation — Keycloak-issued subject tokens, group claims matched against AccessGrants, `Enforced` flipping when the user plane is enabled on an existing install.

**Demoable**: the ADR 0002 appendix "Keycloak + DCR" configuration passes the complete user+agent+resource matrix in KIND; the same AccessGrant objects flip from unenforced to enforced by enabling `userAuth`.

### P22 — Coherence sweep and final validation

**Goal**: the repo tells one story — the new one.

**Scope**: a deletion-and-docs pass across the whole repo: remove every remaining reference to the old architecture (flags, dead code, stale comments, old doc pages); rewrite `docs/security/*` as the single coherent description of the shipped design (topology, issuers, AccessGrant guide, published `data.kaos.*` and request-conventions contracts, the honest "does not support" list from ADR 0003); final cross-preset e2e validation (`kaos-internal`, Keycloak+DCR, Keycloak+AIB-issuer) and the CI invariant that externally attached routes always carry the entry policy.

**Demoable**: all three preset configurations green on one validation matrix; grep for old-architecture terms returns nothing.

## Dependency structure

Strictly linear: P18 → P19 → P20 → P21 → P22. Each is independently mergeable and leaves main in a working, demoable state. If pressure demands parallelism, P19 and P20 touch mostly disjoint code (issuer/runtime vs rego/CRD) and could stack, but the default is sequential.

## Out of scope (tracked, not planned here)

- **ADR 0004 exchange** — own plan after P22, opening with the KIND spike (mock third-party provider) whose go/no-go is recorded against the ADR.
- **KAOS UI workflows** (consent loop surfacing, AccessGrant management) — after the API-level behavior ships.
- The ADR 0003 deferred list (per-user downstream authorization, grant expiry, tool-level granularity) and the OPA bundle-polling evolution from ADR 0001 — revisited on their named triggers.
