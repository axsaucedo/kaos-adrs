# 004 - Research readiness review

## Prompt

1. let's tackle this oen in the research phase in more detail vs trying to solve this now. 2.same with this. 3. same with this. 4. same with this, but seems this is an important one to proeprly understand, it seems the main ones to compare are keycloak vs aib for the target picture, but we could tackle it at the end once we have all the requirements too. 5. same, tackle at resaerch. 6. ok in research. -- Now before kicking off the research review the entire work so far, and review whether the current research covers what we need to know.

## Response

## Summary

The current research is sufficient to start the structured research phase. It has identified the right architectural domains, separated settled points from unresolved questions, and captured enough initial external context to avoid starting from a blank page.

It is **not yet sufficient to produce a final target architecture**. Several areas still need evidence-backed decisions, especially:

1. AIB vs Keycloak/OPA/service mesh boundaries.
2. Approval/consent execution model in synchronous KAOS flows.
3. Enforcement topology: Gateway/ExtProc vs sidecar vs native runtime.
4. Workload identity complexity and whether ServiceAccount binding is worth it initially.

## What the research already covers well

### 1. AIB usefulness and fit

Covered by:

- `aib-research/001-initial-aib-kaos-usefulness.md`
- `aib-research/002-direct-usefulness-clarification.md`
- `aib-research/003-current-and-aspirational-features.md`
- `aib-research/004-feature-mapping-to-kaos.md`

Current state:

- Clear distinction between AIB as a useful target direction and AIB as a non-drop-in integration.
- Clear identification that the strongest current AIB fit is token vault + consent + RFC 8693 token exchange.
- Clear enough feature inventory of current AIB surfaces: agent registry, service registry, permission sets, consent UI/API, token vault, OAuth2 server mode, client credentials, signing/JWKS, token exchange, ExtProc, storage, Helm, telemetry, encryption.

Remaining research need:

- Validate exact AIB API behavior and gaps from source before final design.

### 2. Identity model

Covered by:

- `aib-research/005-identity-architecture-and-mcp-gateway.md`
- `target-picture/001-target-picture-components-and-research-domains.md`
- `target-picture/002-identity-boundaries-and-research-plan.md`

Current state:

- Logical identity, workload identity, user/request identity, and service/MCP identity are separated.
- `namespace/name` is accepted as a likely human-facing logical identity, with Kubernetes UID as lifecycle guard.
- Agents, MCPServers, and ModelAPIs can be modeled uniformly as KAOS-managed service identities.

Remaining research need:

- Decide whether workload identity is required initially.
- Compare ServiceAccount binding vs no workload identity vs AIB credentials vs mesh/SPIFFE.

### 3. KAOS/AIB metadata boundaries

Covered by:

- `aib-research/006-crd-sync-identity-gateway-sidecar-and-autonomous.md`
- `target-picture/002-identity-boundaries-and-research-plan.md`
- `target-picture/003-unresolved-topics-before-research.md`

Current state:

- Source-of-truth split is mostly clear:
  - Kubernetes/KAOS own resource existence, topology, status, endpoints.
  - AIB owns policy, grants, consent, token vault.
  - IdP owns human identity.
  - cert-manager/mesh/Gateway own transport security if adopted.

Remaining research need:

- Flesh out grey areas: owner/display metadata, requested permission profiles, route/resource mapping, autonomous run metadata, and tool taxonomy.

### 4. User token propagation

Covered by:

- `aib-research/007-user-token-propagation-idp-sidecar-and-future-deep-dives.md`
- `target-picture/001-target-picture-components-and-research-domains.md`

Current state:

- Correctly established as mostly a KAOS runtime/gateway concern, not an AIB feature.
- Initial required pieces are known: ingress auth, runtime user context, MCP propagation, AIB exchange/enforcement, consent-required handling.

Remaining research need:

- Inspect KAOS runtime code paths to decide where user context can be stored and forwarded.
- Decide whether Gateway, runtime, or sidecar should carry the token into MCP calls.

### 5. Enforcement topology

Covered by:

- `aib-research/005-identity-architecture-and-mcp-gateway.md`
- `aib-research/007-user-token-propagation-idp-sidecar-and-future-deep-dives.md`
- `target-picture/002-identity-boundaries-and-research-plan.md`
- `target-picture/003-unresolved-topics-before-research.md`

Current state:

- Three serious enforcement options are identified:
  - Gateway/Envoy/ExtProc.
  - Sidecar/local proxy.
  - Native FastMCP/runtime enforcement.
- External references have been initially reviewed for Envoy ext_authz, Envoy ExtProc, Gateway API, OPA-Envoy, and FastMCP auth.

Remaining research need:

- Deeper comparison of operational complexity, MCP body parsing, failure behavior, local vs central enforcement, and initial KAOS compatibility.

### 6. Approval and consent

Covered by:

- `aib-research/006-crd-sync-identity-gateway-sidecar-and-autonomous.md`
- `aib-research/008-pre-design-gap-analysis.md`
- `target-picture/001-target-picture-components-and-research-domains.md`
- `target-picture/002-identity-boundaries-and-research-plan.md`
- `target-picture/003-unresolved-topics-before-research.md`

Current state:

- Approval is now first-class, not collapsed into OAuth consent.
- The major flows are identified:
  - admin approval,
  - user consent,
  - runtime/HITL approval,
  - autonomous run authorization,
  - revocation.
- Candidate handling models are identified:
  - preflight,
  - fail-with-approval URL then retry,
  - UI-mediated approve-and-resubmit,
  - blocking wait,
  - async pause/resume.

Remaining research need:

- Inspect KAOS async/A2A/autonomous task capabilities.
- Assess whether KAOS UI/admin UI can approve and resubmit.
- Decide whether preflight is feasible from Agent/MCP metadata.

### 7. External security tooling

Covered by:

- `target-picture/002-identity-boundaries-and-research-plan.md`
- `target-picture/003-unresolved-topics-before-research.md`

Current state:

Initial external references have been reviewed:

- Kubernetes ServiceAccounts and authentication.
- SPIFFE/SPIRE.
- Linkerd mTLS.
- cert-manager.
- Envoy ext_authz, ExtProc, OAuth2 filter.
- Gateway API HTTPRoute.
- Dex.
- Keycloak Authorization Services.
- OPA/Rego and OPA-Envoy.

Remaining research need:

- The important unresolved question is not whether these tools exist; it is whether **AIB is the right place** for authorization/approval/token brokering versus Keycloak/OPA/service mesh.
- Keycloak vs AIB should likely be compared after the requirements are clearer, because Keycloak may cover some generic authz needs but not necessarily AIB's agent-specific token vault/consent model.

## What is not yet covered enough

### 1. Exact KAOS code integration points

Need source-level research for:

- Agent request handlers.
- Pydantic AI MCP client construction and whether headers/auth are injectable.
- A2A `RemoteAgent` header propagation.
- Current async task states and whether "blocked waiting for approval" is realistic.
- Autonomous task run ID/session model.
- Operator env injection, ServiceAccount fields, Gateway HTTPRoute generation.

### 2. Exact AIB behavior and extension points

Need source-level research for:

- Permission set semantics and agent binding.
- Client credential lifecycle and token claims.
- Token exchange request/response and CEL hooks.
- Consent/reauth URL behavior.
- ExtProc body/header capabilities and current assumptions.
- Whether admin approval exists or must be added.

### 3. Keycloak vs AIB vs OPA boundary

This is the largest conceptual gap. Need to compare:

- AIB as token broker/consent vault.
- Keycloak as IdP/AuthZ/UMA platform.
- OPA/Rego as policy engine/PDP.
- Envoy/mesh as enforcement/transport layer.

The output should be a responsibility matrix and recommendation, not just a feature comparison.

### 4. Approval flow feasibility in current KAOS

Need to verify whether:

- preflight can be derived from static MCP/Agent requirements,
- fail-with-URL retry preserves enough context,
- UI approve-and-resubmit is feasible,
- async pause/resume exists or would require new durable state.

### 5. Security baseline levels

Need to define:

- minimal local/dev security,
- initial useful production security,
- advanced production hardening.

This should include cert-manager and avoid over-engineering with mandatory mesh/SPIFFE/secret manager.

## Does the current research cover what we need to know?

It covers enough to proceed into structured research. It does not yet answer all architectural decisions, but it correctly identifies the decisions to make.

The current research is strong on:

- framing,
- domain decomposition,
- AIB feature relevance,
- identity vocabulary,
- open-question inventory,
- initial external reference map.

The next phase should not broaden the topic further. It should go phase-by-phase through the unresolved domains and produce decision-ready notes.

## Recommended research phase order

1. **KAOS code integration points** - establishes what is technically possible in current runtime/operator.
2. **AIB exact capabilities and gaps** - establishes what current AIB can support vs what needs upstream contribution.
3. **Approval/consent execution model** - highest complexity for KAOS synchronous multi-agent flows.
4. **Enforcement topology** - Gateway/ExtProc vs sidecar vs native runtime.
5. **AIB vs Keycloak/OPA/service mesh boundary** - compare after requirements are concrete.
6. **Workload identity and TLS baseline** - decide minimal vs recommended vs advanced.
7. **Metadata/source-of-truth details** - finalize fields after topology and identity decisions.

This differs slightly from the earlier research sequencing by moving **KAOS code integration** and **AIB exact capabilities** first. That should reduce speculation before we compare architecture options.
