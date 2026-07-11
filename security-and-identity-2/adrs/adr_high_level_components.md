# High-level components — ADR index for security & identity phase 2

**Status**: Proposed
**Date**: 2026-07-11

This document indexes the architecture decisions required for the second security-and-identity phase. It replaces the phase-1 index ([adr_high_level_components](../../security-and-identity/adrs/adr_high_level_components.md)) as the map of open decisions; it identifies each component, its scope, and the options it must weigh — without fleshing any of them out. Each component below becomes its own `adr_NNNN_*.md` when picked up.

All options cited here are grounded in the [research/](../research/) folder; the ADRs should cite research docs rather than re-derive evidence.

## Evolution from phase 1

Phase 1 ([../security-and-identity/](../../security-and-identity/)) delivered gateway identity (dual JWT providers), the authorization projection pipeline, presets, and NetworkPolicy bypass prevention — all of which carry forward. Its central bet, however, failed: [ADR 0001](../../security-and-identity/adrs/adr_0001_enforcement-topology-and-policy-engine.md) placed the authorization decision inside AIB's token-exchange ext_proc, and the investigation concluded that AIB structurally cannot authorize internal traffic — the decision is coupled to an RFC 8693 exchange KAOS does not perform and cannot skip, with no workaround at config, policy, or data level ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)).

Phase 2 therefore re-decides the enforcement topology and, at the same time, fixes a modeling flaw phase 1 never addressed: the implemented authorization is **agent → resource only**; there is no workflow for the full **user + agent + resource** triple ([research/003](../research/003-user-agent-resource-authz-gap.md)).

The framing choice between the two directions the project owner set out — Option 1 (make AIB itself authorize) vs Option 2 (AIB for agent authn only; Keycloak + KAOS-run OPA for authz) — is not a separate ADR: it **is** the decision of ADR 0001 below, and the research verdict weights it heavily toward Option 2.

## Components requiring an ADR

### ADR 0001 — Enforcement topology and decision point (supersedes phase-1 ADR 0001)

**Scope**: where the internal-traffic authorization decision runs, which Envoy filter invokes it, and who owns the deciding component.

**Options to weigh**:
- **KAOS-run OPA behind the gateway `ext_authz` seam** — the Option 2 target; no exchange coupling, evaluates unconditionally (closes G1 by construction), fully KAOS-owned ([research/004](../research/004-keycloak-and-kaos-run-opa-authz-path.md)). Primary candidate.
- **AIB OPA-in-ext_proc (`#222`)** — the Option 1 path; blocked structurally and at deployment level ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)). Recorded for completeness with the three known unblock paths (upstream skip-exchange change, vault seeding, none viable).
- **Fork access-check ext_authz service** — functionally sound and the only existing component modeling the full triple, but a permanent AIB fork-maintenance burden already cancelled once ([research/001](../research/001-why-aib-cannot-authorize-internal-traffic.md)).
- **In-runtime enforcement (pais middleware)** — rejected in phase 1 as not a trust boundary; re-record only as a defense-in-depth complement, not a decision point.

**Key decisions**: filter choice and ordering after `jwt_authn`; OPA deployment shape (sidecar vs standalone, gRPC vs HTTP); fail-closed semantics; coexistence with (or removal of) AIB's ext_proc on the enforcement path; hot-reload of policy/data.

### ADR 0002 — Agent identity and authentication

**Scope**: who issues agent (actor) credentials and tokens, how workloads obtain them, and where actor tokens are verified.

**Options to weigh** (per [research/002](../research/002-aib-agent-authn-surface.md)):
- **AIB client_credentials + JWKS, excluding token exchange** — the proven phase-1 subset (registration, credential mint/rotate, LocalClient token minting, JWKS); keeps the F9 consent path open. Primary candidate.
- **Keycloak client-per-agent** — one fewer system in the Keycloak posture; requires operator-side Keycloak sync.
- **Kubernetes projected ServiceAccount tokens** — no external issuer; identity mapping (`sub` ≠ `kaos://agent/...`) moves into policy data.

**Key decisions**: whether options are exclusive or preset-selectable issuers behind one abstraction; gateway `jwt_authn` verification vs in-policy verification of the actor token (or both); credential rotation and delivery to workloads; the `iss`/`public_url` consistency mechanism (F0).

### ADR 0003 — Authorization model: user + agent + resource

**Scope**: the decision semantics — what facts constitute an authorization decision and how the user dimension enters it ([research/003](../research/003-user-agent-resource-authz-gap.md)).

**Options to weigh** (composable, not exclusive):
- **Keycloak claims as user facts** — user→agent authorization as roles/groups in the subject token; no KAOS storage.
- **KAOS-owned user-grant data** — a user dimension in the projected data document, authored via existing manual modes or a future CRD.
- **UserGrant-shaped schema** — adopt the fork access-check *model* (platform grant on the actor AND user grant on the (user, agent) pair, independently deniable, with expiry and resource subsets) as the schema either source populates.

**Key decisions**: the rego conjunction (subject-condition AND actor→resource grant); the autonomous "no subject" stance per posture (allow-on-agent-grants vs deny); granularity (resource-level now, tool/route-level later); where user grants are administered.

### ADR 0004 — Policy data projection and delivery

**Scope**: how decision facts reach the decision point — the evolution of the phase-1 projection pipeline and its published contract.

**Key decisions**: extending the `data.kaos.*` schema with the user dimension without breaking the published `grants`/`jwks` contract; whether user facts are projected (from what source) or read live from token claims only; ConfigMap-vs-OPA-bundle delivery and reload latency (F4); preservation of the automated / bring-your-own / operator-rego modes and the never-prune safety rule; JWKS injection for multi-issuer setups (ADR 0002 options).

### ADR 0005 — AIB scope and integration boundary

**Scope**: the explicit contract of what KAOS uses AIB for, so scope creep toward the blocked surfaces cannot recur.

**Key decisions**: AIB is used for agent registration, credential lifecycle, token minting, and JWKS only (the [research/002](../research/002-aib-agent-authn-surface.md) surface); token exchange and OPA-in-ext_proc are out of the enforcement path; whether AIB's ext_proc is deployed at all under the new presets; the conditions for re-engaging exchange/consent later (F9 — delegated third-party access), kept as a forward-compatible extension rather than a dependency; fate of the cancelled upstream-contribution and fork tracks.

## Cross-cutting concerns (sections within ADRs, not standalone ADRs)

- **G1 closure** — the no-subject bypass must be eliminated by the topology (ADR 0001) and given semantics by the model (ADR 0003); every ADR states its G1 impact.
- **Preset mapping and migration** — `kaos-internal` / `aib-only` / `aib-keycloak` remain the CLI surface; each ADR maps its options onto the presets and states the migration from the P13–P17 implementation (what is removed, what is re-wired).
- **Fail-closed defaults** — enforcement components fail closed; demo conveniences (`agentJwtVerification=skip`) stay clearly quarantined.
- **Documentation and contract stability** — `docs/security/*` and the published data schema are updated in lockstep with each accepted ADR.

## Dependency and sequencing

ADR 0001 (topology) unblocks everything and should be decided first. ADR 0002 (identity) and ADR 0003 (model) can proceed in parallel once 0001 lands, since they bind to the decision point it selects. ADR 0004 (projection) depends on 0003's schema and 0002's issuer set. ADR 0005 (AIB boundary) is mostly a consequence of 0001+0002 and can be drafted alongside them to lock scope early.

Suggested order: **0001 → (0002 ∥ 0003 ∥ 0005) → 0004**.

## ADR conventions

Same as phase 1: files named `adr_NNNN_slug.md` in this folder; statuses Proposed / Accepted / Superseded; each ADR records context, options considered, decision, and consequences; evidence lives in [research/](../research/) and is cited, not duplicated; no hard line wraps inside paragraphs or list items.
