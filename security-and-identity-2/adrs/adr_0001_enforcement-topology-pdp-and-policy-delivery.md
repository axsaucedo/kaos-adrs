# ADR 0001 — Enforcement topology, the PDP, and policy delivery

**Status**: Proposed
**Date**: 2026-07-11
**Supersedes**: phase-1 [ADR 0001](../../security-and-identity/adrs/adr_0001_enforcement-topology-and-policy-engine.md) (enforcement topology and policy engine)
**Research**: [001](../research/001-why-aib-cannot-authorize-internal-traffic.md), [004](../research/004-keycloak-and-kaos-run-opa-authz-path.md), [005](../research/005-control-plane-pdp-and-relationship-model.md)

## Context

Phase 1 placed the internal-traffic authorization decision inside AIB's token-exchange ext_proc filter. The investigation concluded this is structurally unworkable: AIB's OPA evaluation is coupled to an RFC 8693 exchange that internal KAOS traffic cannot perform (no third-party vault session exists for internal resources), the decision document cannot express "allow but do not exchange", the no-bearer path skips evaluation entirely (the G1 autonomous bypass), and the feature is off by default with no chart surface to enable it ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)). No configuration-, policy-, or data-level workaround exists.

This ADR re-decides the topology: where the authorization decision runs (the policy decision point, PDP), which Envoy filter invokes it (the policy enforcement point, PEP), who owns the deciding component, and how policy and data reach it. The foundational claim from [research/005](../research/005-control-plane-pdp-and-relationship-model.md) frames the space: identity providers authenticate and issue claims; the PDP for a platform's internal traffic is owned by the platform itself (as in Kubernetes RBAC, Istio, agentgateway, and Google's Agent Gateway). KAOS owning the decision point is the standard architecture, not a workaround.

What carries over from phase 1 unchanged ([research/004](../research/004-keycloak-and-kaos-run-opa-authz-path.md)): gateway `jwt_authn` with dual providers (`user` on `Authorization`, `agent` on `x-agent-authorization`), per-route resource stamping (`x-kaos-target-resource: kaos://<slug>/<ns>/<name>`), the `AuthzProjectionReconciler` and its policy ConfigMap (`policy.rego` + `data.json`) with automated / bring-your-own / operator-rego modes, and the published `data.kaos.*` contract. Only the *consumer* of that ConfigMap changes.

## Options considered

### Topology (whose decision point, behind which filter)

1. **KAOS-run OPA behind the gateway `ext_authz` seam** — a KAOS-deployed OPA answering Envoy Gateway's `SecurityPolicy.spec.extAuth`, fed by the phase-1 identity plumbing and the projected ConfigMap. Inverts every research/001 blocker: ext_authz is a pure check with no exchange coupling, evaluates every request on the route (bearer or not — G1 closes by construction), and is fully KAOS-owned (policy content, data, upgrade cadence, enablement). Phase-1 ADR 0001 deliberately retained this seam as a default-off escape hatch; this option promotes it to the primary decision point.
2. **AIB OPA-in-ext_proc (`#222`)** — the phase-1 bet. Blocked structurally (exchange coupling, no allow-without-exchange, G1 pass-through) and at deployment level (off by default, no chart surface). The three theoretical unblock paths — upstream skip-exchange change (not planned, outside KAOS control), fake-third-party vault seeding (impossible to do cleanly, actively harmful when forced), fork revival (below) — were each assessed and fail ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)).
3. **Revive the fork's access-check ext_authz service** — the KAOS-authored decision service on the AIB fork (`cmd/access-check-grpc/`) speaks the right protocol, fails closed, and is the only existing component already modeling the user + agent + resource triple. But it lives on a branch 43 commits diverged from upstream with no convergence path; reviving it means permanently maintaining a security-critical AIB fork — a track phase 1 already cancelled for exactly this reason. Its decision *model* is reused in ADR 0003; its code is not.
4. **Authorino (Kuadrant)** — an off-the-shelf ext_authz backend that can evaluate Keycloak Authorization Services and inline rego. The buy option if live IdP-side policy evaluation is ever wanted; today it would add a heavier component and a second policy language surface for capabilities KAOS does not need.
5. **A small KAOS-authored Go ext_authz server** — typed decisions, one fewer third-party image. Costs owning (writing, auditing, patching) a security-critical network server, and loses the bring-your-own-rego mode that the phase-1 pipeline already supports.
6. **In-runtime enforcement (pais middleware)** — rejected in phase 1 as not a trust boundary (the workload enforcing on itself); remains valid only as defense-in-depth, not as the decision point.

### PDP deployment shape

- **Separate lightweight Deployment (chosen)** — 2 replicas with a PodDisruptionBudget, deployed by the KAOS chart alongside the gateway. The data path depends only on data-path components.
- **In-operator (in-process or sidecar)** — rejected: puts the control plane on the data path; with fail-closed semantics, every operator restart or upgrade would 403 all inter-agent traffic.
- **Sidecar on the gateway** — couples PDP lifecycle to gateway rollouts and multiplies instances without independent scaling; no benefit over a Deployment reachable via a Service, since ext_authz is a network call either way.

### Transport

- **gRPC ext_authz (`envoy.service.auth.v3.Authorization`) (chosen)** — what OPA's built-in `envoy_ext_authz_grpc` plugin speaks natively; the standard, widely deployed pairing, and the same protocol the fork's access-check server implements ([research/004](../research/004-keycloak-and-kaos-run-opa-authz-path.md)).
- **HTTP ext_authz** — would require a translation layer or OPA's generic HTTP API with hand-built input mapping; no advantage.

### Token verification placement

- **In-policy verification (chosen)** — ext_authz forwards the raw `Authorization` / `x-agent-authorization` headers; the rego decodes and verifies both JWTs against `data.kaos.jwks`, which the projection already injects. `jwt_authn` stays in front as the authentication layer (early 401 with specific reasons, signature/expiry/issuer checks). Both halves already exist from phase 1. The decisive property: the PDP's integrity does not depend on gateway filter-chain configuration — a forged or stale claims header is cryptographically useless because the PDP checks signatures itself. Cost: double verification per request (negligible for HMAC/RSA verify at KAOS's scale) and JWKS freshness becoming a projection concern (already handled for multi-issuer in phase 1).
- **Claim forwarding (`jwt_authn` `claimToHeaders`)** — verify once at the filter, forward extracted claims as trusted headers. Pros: single verification, no JWKS distribution to the PDP, Envoy owns key rotation. Cons: the trust chain rests on every request provably traversing the sanitizing filter; any route added without the `jwt_authn` provider, or a header not stripped from external input, silently becomes a claim-spoofing hole. Recorded as the simplification path if measured latency ever demands it; not chosen now.

### Policy and data delivery (hot-reload)

- **ConfigMap volume mount (chosen)** — the PDP mounts the projected ConfigMap; the kubelet updates mounted keys via an atomic symlink swap and OPA re-reads on change. Zero new code and no new network surface. Cost: propagation is bounded by the kubelet sync period — up to ~90s (phase-1 F4) — and this applies to revocations as much as grants; there is also no per-replica feedback of which revision is loaded.
- **OPA bundle polling** — the operator serves the compiled policy+data as a bundle tarball over HTTP; each OPA replica polls (e.g. every 10–15s) and reports the loaded revision via its status API; bundles are signable. Better revocation latency and per-replica observability, at the cost of an HTTP surface on the operator, operator availability affecting policy freshness (degrades to stale-but-serving), and bundle build/signing code. Recorded as the documented evolution when revocation latency or load observability becomes a requirement; the migration is additive (same compiled artifact, different transport).
- **PDP watches CRDs directly (e.g. OPA kube-mgmt)** — rejected: derivation logic (specs → grant graph) would move from tested Go into rego, the PDP would need Kubernetes API permissions and API-server availability on the data path, and the manual/bring-your-own-data modes plus the atomic-snapshot property (one reconcile = one consistent document) would be lost ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)).

## Decision

1. **The PDP is a KAOS-deployed stock OPA** (upstream image, built-in `envoy_ext_authz_grpc` plugin) running as a **separate lightweight Deployment** (2 replicas, PodDisruptionBudget) installed by the KAOS chart. No KAOS service code: only the rego and the data document are KAOS-authored, and both already exist from phase 1. The PDP is present in **every preset**, including `kaos-internal`.
2. **The PEP is Envoy Gateway ext_authz over gRPC**: the `SecurityPolicy.spec.extAuth` seam retained in phase 1 is promoted from default-off escape hatch to the primary enforcement point on all internal resource routes. It evaluates **every** request on those routes, with or without tokens — "no subject" and "no actor" arrive at the policy as facts to reason about, closing G1 by construction (semantics per ADR 0003).
3. **Fail closed**: ext_authz `failOpen: false`. PDP unavailable → 403. Demo conveniences that weaken this are quarantined flags, never preset properties.
4. **Token verification stays in-policy**: the rego verifies both subject and actor JWTs against `data.kaos.jwks`; `jwt_authn` remains in front for authentication-layer 401 semantics. Claim forwarding is the recorded fallback for latency, not the default.
5. **Delivery is the projected ConfigMap, volume-mounted into the PDP**. CRDs remain the single source of truth; the ConfigMap is a compile target the operator regenerates — never a second store. The automated / bring-your-own-policy / operator-rego modes and the never-prune safety rule carry over unchanged. The ~90s propagation bound (F4) is accepted and documented — explicitly including that **revocations** are subject to the same bound; OPA bundle polling is the named evolution when that bound stops being acceptable.
6. **AIB's ext_proc is removed from the enforcement path.** No enforcement semantics may ever depend on it. If ADR 0004 adopts token exchange, ext_proc returns as an *additional* filter scoped strictly to third-party egress routes, ordered after `jwt_authn` and ext_authz, and its absence must never weaken internal authorization.
7. **The KAOS request conventions are published as a contract**: `Authorization` (subject), `x-agent-authorization` (actor), `x-kaos-target-resource` with the `kaos://<slug>/<ns>/<name>` scheme, and the `data.kaos.*` document shape. Any conforming ext_authz backend (Authorino, a Go server, the fork's access-check model) is drop-in behind the same seam.

## Consequences

- **G1 is closed by topology.** Evaluation is unconditional on internal routes; the remaining work is policy semantics for token-absent requests (ADR 0003), not enforcement coverage.
- **The control plane stays off the data path.** Operator restarts, upgrades, or crashes do not affect in-flight authorization; the worst case is stale policy data until the next reconcile (bounded staleness, never fail-open).
- **New failure mode: PDP outage denies all internal traffic.** This is the accepted cost of fail-closed; mitigated by 2 replicas + PDB, and surfaced in runbooks. Sizing/HPA guidance belongs to the chart work, not this ADR.
- **Latency**: one gRPC round-trip per internal request plus in-policy JWT verification. Expected to be well within budget at KAOS scale; measurement during implementation is the trigger for the recorded claim-forwarding fallback.
- **Grant and revocation changes propagate within ~90s**, not immediately. Documentation must state this; workloads must not assume instant revocation. Bundle polling is the upgrade path if this becomes unacceptable.
- **The AIB chart's ext_proc gaps (F0) stop blocking enforcement** — under this topology the ext_proc sidecar need not be deployed at all outside the ADR 0004 feature, deleting rather than fixing that problem for the enforcement path.
- **Preset re-mapping** (detailed in ADR 0002/0003 and the chart work): all presets gain the PDP Deployment and the ext_authz `SecurityPolicy`; `kaos-internal` becomes an honestly scoped agent-plane security posture rather than demo-grade.
- **What is deleted from phase 1**: the expectation that AIB's ext_proc authorizes anything, and any chart/config surface that existed solely to enable `#222`-style evaluation.
