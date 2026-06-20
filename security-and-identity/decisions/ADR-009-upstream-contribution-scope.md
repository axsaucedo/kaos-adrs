# ADR-009: Upstream contribution scope

**Status**: Proposed.
**Date**: 2026-06-20

---

## Decision

Proposed decision: adopt a **split upstream model**:

1. **Contribute generic broker capabilities upstream to AIB** when they are useful for agentic runtimes beyond KAOS.
2. **Keep KAOS-specific adapters in KAOS** when they depend on KAOS CRDs, Kubernetes reconciliation, Gateway route generation, Helm chart behavior, or KAOS runtime conventions.
3. **Do not move responsibilities into AIB** when a mature component already owns the concern, such as IdP/OIDC for human authentication, LiteLLM for model internals, Gateway/NetworkPolicy for traffic boundaries, or service mesh/SPIFFE for workload identity.

The upstream boundary should optimize for reuse without blocking KAOS delivery. KAOS can implement a thin local integration first, then upstream generic pieces once the contract is proven.

---

## Context

ADR-001 through ADR-008 establish a layered KAOS security model:

- KAOS owns Kubernetes resource existence, logical identity, topology, requested access edges, runtime wiring, and Gateway/NetworkPolicy hardening.
- AIB owns approved KAOS resource grants, user-delegated third-party grants, consent, third-party OAuth sessions, and token exchange.
- IdP/OIDC owns human authentication and claims.
- LiteLLM owns ModelAPI model/provider/budget/rate-limit internals.
- OPA, Keycloak Authorization Services, cert-manager, native TLS, SPIFFE, and service mesh remain optional/future integrations in their natural domains.

That boundary creates a contribution question: KAOS should not permanently fork generic agent-identity-broker capabilities, but it also should not upstream KAOS-specific CRD, operator, or deployment behavior into AIB.

---

## Upstream to AIB

The following should be proposed upstream because they are generic agent identity broker capabilities:

| Area | Upstream contribution |
|---|---|
| Resource grants | First-class grant model for agent/resource/action access distinct from user-delegated OAuth grants. |
| Grant lifecycle | Requested, approved, denied, revoked, expired states with audit metadata and approval actor metadata. |
| Resource identity registry | Generic external resource identity records that can represent non-KAOS resources through `external_id` without requiring Kubernetes concepts. |
| Token exchange helpers | Stable client/server helpers for RFC 8693 token exchange, missing-grant errors, re-auth URLs, and consent URLs. |
| Consent flow improvements | Generic user-consent and re-auth response shapes that clients can present consistently. |
| SDK core | Reusable types for request security context, AIB client calls, grant-check results, token redaction, and structured denial errors. |
| ExtProc/Gateway integration | Generic resource-level ExtProc behavior where it does not depend on KAOS Gateway route conventions. |

These contributions should be generic enough to support other agentic orchestration systems, not only KAOS.

---

## Keep KAOS-local

The following should remain in KAOS because they are KAOS orchestration concerns:

| Area | KAOS-local responsibility |
|---|---|
| CRD schema | `spec.security.id`, Agent/MCPServer/ModelAPI references, and future KAOS security fields. |
| Identity resolution | `kaos://{kind}/{namespace}/{name}` and `kaos://{kind}/{id}` resolution rules. |
| Requested-edge extraction | Translating `spec.modelAPI`, `spec.mcpServers`, and `spec.agentNetwork.access` into requested access edges. |
| KAOS-AIB sync service | Watching KAOS CRDs and reconciling AIB records for KAOS resources and requested edges. |
| Operator wiring | Injecting service URLs, Gateway URLs, environment variables, Secrets, and SDK configuration into workloads. |
| Runtime adapters | FastAPI/Pydantic AI, FastMCP, A2A, and KAOS ModelAPI/LiteLLM integration adapters. |
| Gateway/NetworkPolicy generation | KAOS GatewayAPI routes, URL rewrites, route identity mapping, and future bypass-prevention NetworkPolicies. |
| Docs and chart profiles | KAOS deployment profiles for minimal/dev, recommended production, and advanced hardening. |

KAOS-local code may depend on upstream AIB SDK/core packages, but it should not force Kubernetes or KAOS CRD semantics into AIB core.

---

## Explicit non-goals for AIB upstreaming

The following should not be upstreamed into AIB as part of this integration:

- Human authentication, SSO, group management, or IdP lifecycle management.
- Keycloak Authorization Services administration.
- OPA/Rego policy bundle management.
- LiteLLM provider-key, model allowlist, budget, or rate-limit policy.
- KAOS Gateway chart/controller behavior.
- Kubernetes NetworkPolicy generation.
- cert-manager certificate lifecycle management.
- Native service TLS configuration for KAOS Agent/MCPServer/ModelAPI workloads.
- SPIFFE/SPIRE, service mesh, or Kubernetes ServiceAccount workload identity binding.
- MCP tool/argument policy until KAOS models tool permissions explicitly.

These concerns remain owned by their natural platform components or by future KAOS-specific integrations.

---

## Sequencing

1. Implement KAOS integration against the smallest stable AIB surface that can support SDK-first grant checks and token exchange.
2. Keep temporary KAOS workarounds explicit, especially synthetic PermissionSet encodings for resource grants.
3. Propose first-class AIB resource grants upstream once KAOS has validated the required data shape.
4. Propose generic SDK core types and AIB client behavior upstream after KAOS adapters prove the runtime contract.
5. Keep Gateway/NetworkPolicy hardening in KAOS 1.1 and upstream only the generic AIB ExtProc/resource-check pieces.

---

## Annex: Alternatives considered

### Option A: Keep all AIB-related work inside KAOS

This would let KAOS move fastest initially, but it would duplicate generic agent-identity-broker capabilities and risk a long-lived KAOS fork of AIB behavior.

Rejected as the target. KAOS-specific adapters can start locally, but generic broker concepts should converge upstream.

### Option B: Upstream all integration code into AIB first

This would maximize reuse but would slow KAOS delivery and force AIB to absorb Kubernetes, CRD, Gateway, LiteLLM, and KAOS runtime details.

Rejected. AIB should gain generic broker capabilities, not KAOS orchestration code.

### Option C: Make AIB own the whole security platform

This would centralize identity, policy, transport, Gateway, model policy, and workload identity in AIB.

Rejected by ADR-008. It duplicates mature tools and overextends AIB beyond agent-specific delegation, grants, consent, and token exchange.

---

## Consequences

### Positive

- Keeps KAOS delivery practical while avoiding unnecessary long-term forks.
- Gives AIB a clear upstream roadmap based on reusable agent broker capabilities.
- Prevents KAOS-specific CRD/operator details from leaking into AIB core.
- Aligns SDK design with a generic core plus KAOS adapters.

### Negative

- Requires discipline to keep temporary KAOS workarounds from becoming permanent.
- Some useful AIB changes may take longer if they are upstreamed through review rather than kept local.
- The SDK package boundary must be carefully designed so generic code is not polluted by KAOS-specific identity and topology assumptions.

### Risks

- If upstreaming is attempted too early, KAOS integration may stall on generic design debates.
- If upstreaming is delayed too long, KAOS may accumulate incompatible local AIB semantics.
- If the boundary is unclear, AIB could become responsible for Gateway, LiteLLM, IdP, or Kubernetes concerns it should not own.

---

## Decision summary

1. Upstream generic agent identity broker capabilities to AIB.
2. Keep KAOS CRD, operator, runtime adapter, Gateway, NetworkPolicy, and deployment-profile behavior in KAOS.
3. Prioritize upstream AIB first-class resource grants, grant lifecycle, reusable SDK core, token exchange helpers, and consent/re-auth response shapes.
4. Do not upstream IdP, OPA, LiteLLM, cert-manager, native TLS, service mesh, or Kubernetes-specific responsibilities into AIB.
5. Use KAOS-local implementations to validate contracts, then upstream stable generic pieces without blocking KAOS integration.
