# ADR-008: AIB, IdP, OPA, Gateway, and mesh responsibility matrix

**Status**: Accepted.
**Date**: 2026-06-20

---

## Context

ADR-001 through ADR-007 establish the core KAOS security target:

- KAOS owns logical identities and topology.
- AIB owns approved KAOS resource grants and user-delegated third-party grants.
- KAOS uses SDK-first request context propagation and enforcement for 1.0.
- GatewayAPI resource-boundary enforcement and NetworkPolicy are bundled into 1.1.
- Authorization is data-first and grant-table-based in 1.0.
- User consent and third-party re-authentication use fail-with-URL-and-retry.
- The transport baseline is external TLS in production, with native intra-service TLS, mTLS, SPIFFE, and mesh deferred.

This ADR consolidates those decisions into a responsibility matrix so KAOS does not overuse AIB for problems better solved by IdPs, Gateway, OPA, LiteLLM, cert-manager, or service mesh.

The core question is:

```text
Which component owns which part of KAOS security, and where should KAOS adopt, build, upstream, or defer?
```

---

## Source facts from accepted ADRs

### AIB is not the human IdP

ADR-004 accepts:

- External IdP such as Keycloak, Dex, or another OIDC provider owns human authentication and user identity.
- AIB answers whether a principal has delegated access to an agent, whether an agent can access a KAOS logical resource, and whether a third-party token can be returned.
- AIB does not replace Keycloak/Dex/OIDC for SSO.

### AIB is not the general policy platform in 1.0

ADR-005 accepts:

- KAOS 1.0 authorization is data-first and grant-table-based.
- AIB CEL remains internal bounded expression support.
- OPA/Rego is deferred.
- Keycloak Authorization Services is deferred.
- MCP tool/argument policy is deferred.

### AIB is not the transport security layer

ADR-007 accepts:

- Production external traffic must use TLS at ingress, Gateway, load balancer, or trusted reverse proxy.
- Gateway + NetworkPolicy boundary hardening is bundled into 1.1.
- Native Agent/MCPServer/ModelAPI TLS is a future configurable hardening layer.
- SPIFFE, service mesh, and cryptographic workload binding are deferred advanced-profile features.

### LiteLLM remains the ModelAPI internal authorization surface

ADR-002 and ADR-005 accept:

- LiteLLM is the preferred ModelAPI surface for model allowlists, provider credentials, budgets, and rate limits.
- AIB may authorize root access to a ModelAPI resource, but ModelAPI internals remain LiteLLM-owned.
- Ollama/Hosted mode is backend-only or wrapped because it does not provide the same rich native auth model.

---

## Options

### Option A: AIB-centered security platform

This option makes AIB own nearly everything:

```text
human identity bridge
KAOS resource grants
user delegated grants
policy language
approval workflows
runtime token issuance
ModelAPI model/budget policy
MCP tool/argument policy
Gateway route authorization
transport/security posture
```

This is conceptually simple because one component becomes the security brain. It is also too broad for KAOS 1.0. It would require AIB to duplicate IdP, OPA, Gateway, LiteLLM, cert-manager, and service-mesh responsibilities.

Pros:

- One product boundary to explain.
- Strong centralization if AIB eventually becomes a broad platform.

Cons:

- Over-engineers 1.0.
- Expands AIB beyond its current implementation.
- Duplicates mature tools.
- Creates a large upstream dependency before the simple KAOS/AIB grant model is proven.

Best fit:

- Rejected for 1.0.

### Option B: Existing security platforms own most decisions

This option pushes KAOS security primarily into existing platforms:

```text
Keycloak/AuthZ owns resource authorization
OPA owns policy
Gateway/service mesh owns enforcement
AIB only exchanges delegated third-party tokens
KAOS mostly syncs metadata
```

This minimizes AIB scope, but it loses the agent-specific value of AIB: user-to-agent delegated grants, token vault/session refresh, and agent-specific token exchange. It also forces dynamic KAOS resource-grant data into Keycloak or OPA before KAOS has proven the simpler model.

Pros:

- Uses mature enterprise systems.
- Aligns with organizations already standardized on Keycloak/OPA/mesh.
- Keeps AIB narrow.

Cons:

- Weakens the KAOS/AIB agent-delegation model.
- Requires syncing dynamic KAOS resources into external systems early.
- Makes the default architecture heavier.
- Risks making KAOS security depend on a specific enterprise stack.

Best fit:

- Optional enterprise integration later, not default 1.0.

### Option C: Layered responsibility matrix

This option assigns each concern to the component that is the best fit:

```text
KAOS:
  resource identity, topology, requested access edges

AIB:
  approved KAOS resource grants
  user delegated third-party grants
  consent
  token exchange

IdP:
  human login, SSO, user claims/groups

LiteLLM:
  ModelAPI internal auth, model allowlists, budgets, provider keys

Gateway/NetworkPolicy:
  1.1 resource-boundary enforcement and bypass prevention

OPA/Keycloak AuthZ:
  future optional enterprise PDP/PAP

cert-manager/native TLS/mesh/SPIFFE:
  transport and workload hardening layers
```

This preserves the simple 1.0 model while leaving room for advanced enterprise integrations. It also prevents AIB from becoming an all-purpose security platform.

Pros:

- Keeps each component in its natural domain.
- Matches accepted ADRs.
- Avoids premature OPA/Keycloak/mesh dependencies.
- Keeps AIB focused on agent-specific delegation and grants.
- Leaves extension points for 1.1+ hardening.

Cons:

- More components to explain.
- Requires clear integration contracts between KAOS, AIB, IdP, LiteLLM, and Gateway.
- Some enterprise deployments may still want a more centralized PDP later.

Best fit:

- KAOS 1.0 target architecture.

---

## Decision

Adopt **Option C: Layered responsibility matrix**.

### Responsibility matrix

| Concern | 1.0 owner | Future/optional owner | Notes |
|---|---|---|---|
| KAOS resource existence | KAOS CRDs/operator | N/A | Kubernetes remains source of truth for resources. |
| KAOS logical identity | KAOS CRDs/operator | N/A | `spec.security.id` / default logical identity from ADR-001. |
| Requested access edges | KAOS CRDs/operator | KAOS-AIB sync service mirrors to AIB | CRD wiring is request, not approval. |
| Approved KAOS resource grants | AIB | AIB first-class resource grant model | Bootstrap may use synthetic internal PermissionSet encoding. |
| User authentication | Keycloak/Dex/OIDC provider | Enterprise IdP | AIB does not replace SSO. |
| User claims/groups | Keycloak/Dex/OIDC provider | Enterprise IdP | AIB may consume claims/context, not own identity. |
| User delegated third-party grants | AIB | AIB | UserGrant + PermissionSet domain. |
| Third-party OAuth sessions/token vault | AIB | AIB | Not KAOS runtime state. |
| Token exchange for third-party APIs | AIB | AIB ExtProc/Gateway integration later | SDK-first in 1.0, Gateway path later. |
| SDK request context propagation | KAOS/AIB SDK | Upstreamable AIB SDK core + KAOS adapters | Detailed in later SDK ADR. |
| Agent/MCPServer root authorization | AIB grant checks through SDK | Gateway/NetworkPolicy enforcement in 1.1 | Resource-level, not tool-level. |
| MCP tool/argument authorization | Deferred | Future KAOS tool permission model + AIB/OPA approval | Not modeled in 1.0. |
| ModelAPI root authorization | AIB resource grants | Gateway resource-boundary enforcement | Root access only. |
| ModelAPI model/budget/rate policy | LiteLLM | LiteLLM/enterprise controls | Not AIB PermissionSets. |
| Gateway routes | KAOS GatewayAPI integration | Gateway + NetworkPolicy in 1.1 | AIB does not own route config. |
| Human approval/pause-resume | Deferred | KAOS task/UI approval model | A2A `input-required` future. |
| General policy language/PDP | Simple AIB grant lookup | OPA/Rego or Keycloak AuthZ optional | Not mandatory in 1.0. |
| Transport TLS | Deployment ingress/Gateway/reverse proxy | Gateway TLS/cert-manager/native TLS | ADR-007. |
| Network bypass prevention | Deferred | Gateway + NetworkPolicy 1.1 | Not solved by AIB. |
| Workload identity/mTLS | Deferred | SPIFFE/service mesh/K8s SA binding | Advanced profile. |

### Adopt/build/upstream recommendations

| Area | Recommendation |
|---|---|
| KAOS logical identity and requested-edge extraction | Build in KAOS |
| KAOS-AIB sync service | Build in KAOS initially; upstream generic AIB reconciliation patterns only if reusable |
| AIB first-class resource grants | Upstream/build in AIB |
| AIB user consent and token exchange | Adopt from AIB |
| AIB SDK generic client pieces | Upstream to AIB where generic |
| KAOS runtime SDK adapters | Build in KAOS |
| Gateway/NetworkPolicy enforcement | Build in KAOS 1.1 |
| LiteLLM model/budget integration | Adopt LiteLLM; build KAOS config wiring only |
| Keycloak/Dex OIDC integration | Adopt existing IdP tooling |
| OPA/Keycloak AuthZ PDP integration | Defer; optional enterprise extension |
| Native TLS/service mesh/SPIFFE | Defer; optional hardening profile |

---

## Host questions resolved for ADR-008

### Q1. Should KAOS use a layered responsibility matrix instead of making AIB the all-purpose security platform?

Decision:

- Yes. AIB should stay focused on KAOS resource grants, user delegated grants, consent, and token exchange.

Tradeoff:

- More integration boundaries, but much less over-engineering.

### Q2. Should Keycloak/Dex remain human identity/SSO only in 1.0?

Decision:

- Yes. Keycloak/Dex/OIDC should authenticate humans and provide claims/groups. Keycloak Authorization Services remains optional future work.

Tradeoff:

- Avoids syncing dynamic KAOS resources into Keycloak in 1.0.

### Q3. Should OPA/Rego remain optional and deferred?

Decision:

- Yes. OPA is useful if simple grants become insufficient, but should not be mandatory for 1.0.

Tradeoff:

- Simpler initial model, less enterprise policy expressiveness.

### Q4. Should LiteLLM remain the ModelAPI internal policy owner?

Decision:

- Yes. AIB may decide root ModelAPI access, but LiteLLM should own model-level allowlists, budgets, and provider auth.

Tradeoff:

- Keeps AIB simpler, but splits ModelAPI root access from ModelAPI internal policy.

### Q5. Should Gateway/NetworkPolicy be explicitly 1.1, not 1.0?

Decision:

- Yes. Bundle Gateway resource-boundary enforcement and NetworkPolicy bypass prevention into 1.1.

Tradeoff:

- 1.0 remains SDK-first; network bypass prevention is not complete until 1.1.

### Q6. Which features should be upstreamed to AIB?

Decision:

- Upstream generic agent-identity broker features: first-class resource grants, resource-grant approval lifecycle, generic SDK client pieces, and token-exchange/consent improvements.

Tradeoff:

- Upstreaming increases reuse but can slow KAOS-specific delivery if done too early.

---

## Accepted ADR-008 decision

1. KAOS adopts a layered responsibility matrix rather than an AIB-centered or enterprise-platform-centered security model.
2. KAOS owns resource existence, topology, logical identity, requested access edges, and runtime wiring.
3. AIB owns approved KAOS resource grants, user delegated grants, consent, third-party sessions, and token exchange.
4. Keycloak/Dex/OIDC owns human authentication and user claims/groups in 1.0.
5. Keycloak Authorization Services is deferred as optional future enterprise PDP/PAP integration.
6. OPA/Rego is deferred as optional future enterprise PDP integration.
7. LiteLLM owns ModelAPI internals: model allowlists, provider keys, budgets, and rate limits.
8. Gateway + NetworkPolicy owns 1.1 resource-boundary enforcement and bypass prevention.
9. cert-manager, native service TLS, SPIFFE, and service mesh are transport/workload hardening layers, not AIB responsibilities.
10. KAOS-specific orchestration wiring is built in KAOS first.
11. Generic AIB concepts should be upstreamed to AIB when they are not KAOS-specific, especially first-class resource grants and reusable SDK/client pieces.

## Decision status

Accepted.
