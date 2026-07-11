# High-level components — ADR index for security & identity phase 2

**Status**: Proposed
**Date**: 2026-07-11

This document indexes the architecture decisions required for the second security-and-identity phase. It replaces the phase-1 index ([adr_high_level_components](../../security-and-identity/adrs/adr_high_level_components.md)) as the map of open decisions; it identifies each component, its scope, and the options it must weigh — without fleshing any of them out. Each component below becomes its own `adr_NNNN_*.md` when picked up.

All options cited here are grounded in the [research/](../research/) folder; the ADRs should cite research docs rather than re-derive evidence.

## Evolution from phase 1

Phase 1 ([../security-and-identity/](../../security-and-identity/)) delivered gateway identity (dual JWT providers), the authorization projection pipeline, presets, and NetworkPolicy bypass prevention — all of which carry forward. Its central bet, however, failed: [ADR 0001](../../security-and-identity/adrs/adr_0001_enforcement-topology-and-policy-engine.md) placed the authorization decision inside AIB's token-exchange ext_proc, and the investigation concluded that AIB structurally cannot authorize internal traffic — the decision is coupled to an RFC 8693 exchange KAOS does not perform and cannot skip, with no workaround at config, policy, or data level ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)).

Phase 2 therefore re-decides the enforcement topology and, at the same time, fixes a modeling flaw phase 1 never addressed: the implemented authorization is **agent → resource only**; there is no workflow for the full **user + agent + resource** triple ([research/003](../research/003-user-agent-resource-authz-gap.md)).

The framing choice between the two directions the project owner set out — Option 1 (make AIB itself authorize) vs Option 2 (AIB for agent authn only; Keycloak + KAOS-run OPA for authz) — is not a separate ADR: it **is** the decision of ADR 0001 below, and the research verdict weights it heavily toward Option 2.

A subsequent cross-cutting design discussion converged the overall shape — three planes (identity / relationship / decision), CRDs as the relationship source of truth with the ConfigMap as compile target, IdP projection reduced to credential provisioning, preset-selectable agent issuers, and honestly scoped preset semantics — recorded in [research/005](../research/005-control-plane-pdp-and-relationship-model.md). The options below reflect those outcomes; the individual ADRs formalize them.

## Components requiring an ADR

### ADR 0001 — Enforcement topology and decision point (supersedes phase-1 ADR 0001)

**Scope**: where the internal-traffic authorization decision runs, which Envoy filter invokes it, and who owns the deciding component.

**Options to weigh**:
- **KAOS-run OPA behind the gateway `ext_authz` seam** — the Option 2 target; no exchange coupling, evaluates unconditionally (closes G1 by construction), fully KAOS-owned ([research/004](../research/004-keycloak-and-kaos-run-opa-authz-path.md)). Primary candidate.
- **AIB OPA-in-ext_proc (`#222`)** — the Option 1 path; blocked structurally and at deployment level ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)). Recorded for completeness with the three known unblock paths (upstream skip-exchange change, vault seeding, none viable).
- **Fork access-check ext_authz service** — functionally sound and the only existing component modeling the full triple, but a permanent AIB fork-maintenance burden already cancelled once ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)).
- **Authorino (Kuadrant) as an off-the-shelf ext_authz backend** — can evaluate Keycloak Authorization Services and inline rego; the buy option if live IdP-side policy evaluation is ever wanted ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)).
- **A small KAOS-authored Go ext_authz server** — typed decisions, one fewer image; costs owning a security-critical server and loses bring-your-own-rego.
- **In-runtime enforcement (pais middleware)** — rejected in phase 1 as not a trust boundary; re-record only as a defense-in-depth complement, not a decision point.

**Key decisions**: filter choice and ordering after `jwt_authn`; PDP deployment shape — converged on a separate lightweight Deployment rather than operator in-process/sidecar, so the control plane stays off the data path ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)); gRPC vs HTTP; fail-closed semantics; coexistence with (or removal of) AIB's ext_proc on the enforcement path; hot-reload of policy/data; publishing the KAOS request conventions (`x-agent-authorization`, `x-kaos-target-resource`, `kaos://` scheme) as the contract that makes any conforming ext_authz backend drop-in.

### ADR 0002 — Agent identity and authentication

**Scope**: who issues agent (actor) credentials and tokens, how workloads obtain them, and where actor tokens are verified.

**Options to weigh** (per [research/002](../research/002-aib-agent-authn-surface.md), converged direction in [research/005](../research/005-control-plane-pdp-and-relationship-model.md)):
- **Kubernetes projected ServiceAccount tokens** — no external issuer, auto-rotated, zero IdP projection; identity mapping (`sub` ≠ `kaos://agent/...`) moves into policy data. Converged default for the in-cluster-only posture (`kaos-internal`).
- **OIDC provider clients provisioned via RFC 7591/7592 Dynamic Client Registration** — provider-generic `OIDCProjector` behind the existing `PolicyProjector` seam; Keycloak supports DCR natively. Converged default when agent identity must participate in the broader OAuth world (external callers, third-party APIs, multi-cluster, F9).
- **AIB client_credentials + JWKS, excluding token exchange** — the proven phase-1 subset (registration, credential mint/rotate, LocalClient token minting, JWKS) via its admin API as a per-provider adapter behind the same seam; keeps the F9 consent path open.

**Key decisions**: issuers are preset-selectable behind one abstraction (converged: the gateway JWT provider and the policy see only an issuer, a JWKS, and a mapped identity); IdP projection reduced to credential provisioning only — client create/rotate/delete plus Secret delivery, with all authorization state out of the IdP; gateway `jwt_authn` verification vs in-policy verification of the actor token (or both); the `iss`/`public_url` consistency mechanism (F0).

### ADR 0003 — Authorization model: user + agent + resource

**Scope**: the decision semantics — what facts constitute an authorization decision and how the user dimension enters it ([research/003](../research/003-user-agent-resource-authz-gap.md)).

**Options to weigh** (composable, not exclusive):
- **`AccessGrant` CRD referencing IdP groups (converged direction)** — a small CRD binding subjects (user `sub`/email or a Keycloak role/group reference) to resources (`kaos://` ids or a label selector); the edge is declarative and GitOps-reviewable while membership is administered in the IdP UI and arrives as a token claim — the Kubernetes RoleBinding analogue ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)).
- **Keycloak claims as user facts** — user→agent authorization purely as roles/groups in the subject token; no KAOS storage.
- **KAOS-owned user-grant data** — a user dimension in the projected data document, authored via existing manual modes.
- **UserGrant-shaped schema** — adopt the fork access-check *model* (platform grant on the actor AND user grant on the (user, agent) pair, independently deniable, with expiry and resource subsets) as the schema either source populates.

**Key decisions**: the rego conjunction (subject-condition AND actor→resource grant); the autonomous "no subject" stance per posture (allow-on-agent-grants vs deny); granularity (resource-level now, tool/route-level later — agentgateway demonstrates the tool-level dimension); behavior of `AccessGrant` when no user IdP is enabled (converged: accept, mark `Enforced=False` with `reason=NoUserIdentityProvider` status condition and warning event, skip projection — never silently ignore); a dedicated ReBAC store (SpiceDB/OpenFGA) recorded as the growth path only, not the starting point.

### ADR 0004 — Policy data projection and delivery

**Scope**: how decision facts reach the decision point — the evolution of the phase-1 projection pipeline and its published contract.

**Key decisions**: the framing that CRDs are the source of truth and the ConfigMap is a *compile target* — a derived artifact the operator regenerates, never a second store; PDP-watches-CRDs-directly (e.g. OPA kube-mgmt) rejected because derivation logic would move into rego, the PDP would need K8s API permissions on the data path, and the manual modes plus atomic-snapshot property would be lost ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)); extending the `data.kaos.*` schema with the user dimension without breaking the published `grants`/`jwks` contract; whether user facts are projected (from what source) or read live from token claims only; ConfigMap-vs-OPA-bundle delivery and reload latency (F4); preservation of the automated / bring-your-own / operator-rego modes and the never-prune safety rule; JWKS injection for multi-issuer setups (ADR 0002 options, including the K8s API server as issuer).

### ADR 0005 — AIB scope and integration boundary

**Scope**: the explicit contract of what KAOS uses AIB for, so scope creep toward the blocked surfaces cannot recur.

**Key decisions**: AIB becomes an *optional* agent-identity adapter behind the ADR 0002 abstraction rather than a required component — used, when selected, for agent registration, credential lifecycle, token minting, and JWKS only (the [research/002](../research/002-aib-agent-authn-surface.md) surface); token exchange and OPA-in-ext_proc are out of the enforcement path; **permission sets are exchange-scoped** — they are AIB's token-exchange-time concept, so permission-set binding in the AIB adapter is enabled only with the F9 exchange feature and never leaks into the PDP path ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)); whether AIB's ext_proc is deployed at all under the new presets; explicit re-entry criteria for deeper AIB integration — (a) AIB ships an authorization surface decoupled from exchange, or (b) KAOS adopts consent-based third-party delegation (F9) and AIB's consent/vault UX is the best implementation — kept as a forward-compatible extension rather than a dependency; fate of the cancelled upstream-contribution and fork tracks.

## Cross-cutting concerns (sections within ADRs, not standalone ADRs)

- **G1 closure** — the no-subject bypass must be eliminated by the topology (ADR 0001) and given semantics by the model (ADR 0003); every ADR states its G1 impact.
- **Preset mapping and migration** — `kaos-internal` / `aib-only` / `aib-keycloak` remain the CLI surface; each ADR maps its options onto the presets and states the migration from the P13–P17 implementation (what is removed, what is re-wired). Converged semantics ([research/005](../research/005-control-plane-pdp-and-relationship-model.md)): `kaos-internal` graduates from demo-grade to an honestly scoped **agent-plane security** posture (ServiceAccount identity, PDP-enforced agent→resource, fail-closed, no user dimension — user access governed by cluster credentials, as Kubernetes itself without OIDC); Keycloak-backed presets add the user plane (subject verification, `AccessGrant` enforcement) over the same PDP and graph.
- **Fail-closed defaults** — enforcement components fail closed; demo conveniences (`agentJwtVerification=skip`) are quarantined flags, not preset properties.
- **Documentation and contract stability** — `docs/security/*` and the published data schema are updated in lockstep with each accepted ADR.

## Dependency and sequencing

ADR 0001 (topology) unblocks everything and should be decided first. ADR 0002 (identity) and ADR 0003 (model) can proceed in parallel once 0001 lands, since they bind to the decision point it selects. ADR 0004 (projection) depends on 0003's schema and 0002's issuer set. ADR 0005 (AIB boundary) is mostly a consequence of 0001+0002 and can be drafted alongside them to lock scope early.

Suggested order: **0001 → (0002 ∥ 0003 ∥ 0005) → 0004**.

## ADR conventions

Same as phase 1: files named `adr_NNNN_slug.md` in this folder; statuses Proposed / Accepted / Superseded; each ADR records context, options considered, decision, and consequences; evidence lives in [research/](../research/) and is cited, not duplicated; no hard line wraps inside paragraphs or list items.
