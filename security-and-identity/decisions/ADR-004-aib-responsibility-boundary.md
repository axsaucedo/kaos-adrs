# ADR-004: AIB responsibility boundary

**Status**: Proposed. Requires host decisions before acceptance.
**Date**: 2026-06-19

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) establishes that KAOS owns resource identity and topology, while AIB can mirror KAOS identities through `external_id`.

[ADR-002](./ADR-002-user-request-context-propagation.md) establishes an SDK-first request context propagation layer for Agents and MCPServers.

[ADR-003](./ADR-003-enforcement-topology.md) establishes an SDK-first 1.0 topology, LiteLLM as the preferred ModelAPI auth surface, GatewayAPI as a 1.1 resource-boundary extension, and sidecars as deferred.

The next decision is what AIB itself should own in this architecture.

The core question is:

```text
Is AIB the delegated OAuth/token broker for KAOS, or is it the central authorization platform for all KAOS resources?
```

---

## Source facts

### AIB Agent registry

Source file:

- `agentic-identity-broker/internal/domain/storage/agent.go`

AIB `Agent` has:

- internal UUID `ID`,
- optional `ClientID`,
- optional `ExternalID`,
- display and documentation fields,
- `ServiceRequirements`,
- `PermissionSets`,
- redirect URIs,
- allowed scopes,
- client metadata document URIs.

Implication:

- AIB can represent KAOS Agents through `ExternalID`, using the identity format from ADR-001.
- AIB is not the source of truth for KAOS resource existence; it stores broker-side records used for consent, OAuth, and token exchange.

### AIB PermissionSets

Source file:

- `agentic-identity-broker/internal/domain/storage/permission_set.go`

AIB `PermissionSet` is an admin-defined bundle of OAuth2 scopes spanning one or more third-party services:

```text
PermissionSet
  service_scopes[]
    service_id
    scopes[]
    requirement_type
```

Implication:

- Current PermissionSets are naturally aligned with third-party OAuth/service scopes.
- They are not currently modeled around MCP tool names, MCP arguments, ModelAPI models, or KAOS resource routes.

### AIB UserGrants

Source file:

- `agentic-identity-broker/internal/domain/storage/user_grant.go`

AIB `UserGrant` binds:

```text
principal + agent_id + granted_permission_sets + optional valid_until
```

Implication:

- AIB is well suited to be authoritative for user-delegated grants from a principal to an agent.
- Grant survival across KAOS Agent delete/recreate is possible if the KAOS-AIB sync service preserves the same AIB agent record for the same `external_id`.

### AIB consent service

Source file:

- `agentic-identity-broker/internal/domain/consent/service.go`

AIB consent:

- resolves an Agent's service requirements and permission sets,
- checks active third-party OAuth sessions for the principal,
- creates or updates grants,
- validates mandatory permission sets and included service IDs,
- enforces active session requirements for grant submission.

Implication:

- AIB already owns a useful user-consent and delegated-grant workflow.
- This maps well to "agent needs user-granted access to third-party services."

### AIB token exchange

Source file:

- `agentic-identity-broker/internal/domain/tokenexchange/service.go`

AIB token exchange:

1. validates RFC 8693 request structure,
2. validates `subject_token`,
3. validates `client_assertion`,
4. extracts principal and agent ID via CEL,
5. authorizes privileged client via CEL,
6. resolves target service from `resource`,
7. verifies user grant before checking token session,
8. retrieves and refreshes stored third-party tokens,
9. validates permission-set scope coverage,
10. returns token exchange response or re-auth/approval hints.

Implication:

- AIB is already a strong fit for delegated third-party token exchange.
- AIB token exchange can be called directly by an SDK or indirectly by Gateway/ExtProc.
- Current AIB token exchange is service/resource oriented, not MCP-tool semantic.

### AIB ExtProc

Source file:

- `agentic-identity-broker/internal/extproc/server/server.go`

AIB ExtProc:

- extracts Bearer tokens at a proxy boundary,
- builds a resource URI,
- exchanges tokens,
- replaces the upstream `Authorization` header,
- returns error/reauth URI responses in some failure cases,
- passes request/response bodies through.

Implication:

- ExtProc fits Gateway or sidecar token exchange.
- Per ADR-003, this should be treated as a later Gateway/resource-boundary integration, not required for SDK-first 1.0.

---

## Decision problem

KAOS needs to decide whether AIB owns:

1. only delegated OAuth grants and token exchange,
2. broader Agent/MCP/ModelAPI authorization,
3. runtime/session token issuance,
4. approval workflows,
5. policy language/evaluation,
6. or some combination.

This boundary matters because AIB overlaps conceptually with:

- KAOS CRDs and SDK,
- LiteLLM ModelAPI auth,
- GatewayAPI resource-boundary auth,
- external IdPs such as Keycloak/Dex,
- external PDP/policy engines such as OPA.

---

## Options

### Option A: AIB as delegated OAuth/token broker

AIB owns:

- mirrored Agent records needed for broker flows,
- third-party OAuth service registry,
- PermissionSets for third-party service scopes,
- user consent and grants,
- OAuth2 session/token vault,
- RFC 8693 token exchange,
- re-auth/approval-required hints for missing/expired sessions or grants.

KAOS/SDK owns:

- request context propagation,
- MCP tool semantics,
- Agent/A2A delegation semantics,
- KAOS resource topology and CRD source of truth.

Gateway/LiteLLM/IdP own:

- resource-boundary enforcement,
- ModelAPI enforcement,
- human authentication.

Pros:

- Closest to current AIB implementation.
- Keeps 1.0 scope simple.
- Avoids duplicating Keycloak/OPA/Gateway responsibilities.
- Gives KAOS the most immediately useful AIB capability: delegated third-party access.
- Fits ADR-002/ADR-003 SDK-first architecture.

Cons:

- AIB is not the central authorization brain for all KAOS actions.
- MCP tool-level policy remains in SDK/MCP runtime.
- ModelAPI policy remains in LiteLLM/Gateway/wrapper.
- Future approval semantics may require more AIB or KAOS work.

Best fit:

- 1.0.

### Option B: AIB as broad agent authorization platform

AIB owns:

- delegated OAuth grants,
- Agent/MCPServer/ModelAPI authorization,
- policy definitions,
- approval workflows,
- token exchange,
- perhaps runtime/session token issuance.

Pros:

- Stronger centralized governance story.
- Could eventually unify consent, approval, grants, and agent authorization.
- Reduces policy fragmentation if implemented fully.

Cons:

- Not what current AIB fully implements.
- Risks duplicating mature IdP/PDP/Gateway capabilities.
- Requires AIB to understand KAOS-specific MCP/ModelAPI/topology semantics.
- Larger 1.0 scope and higher integration risk.
- Harder to keep KAOS CRDs authoritative for topology.

Best fit:

- Long-term product exploration, not initial target.

### Option C: AIB only as token vault/token exchange service

AIB does not own consent/grants in the KAOS target; KAOS or an external platform owns policy and grants, and AIB only stores third-party sessions and exchanges tokens.

Pros:

- Very narrow AIB integration.
- KAOS or external IdP/PDP remains policy authority.
- Could simplify AIB usage in environments with existing governance systems.

Cons:

- Underuses AIB's implemented consent and grant model.
- KAOS would need to implement or integrate another user-grant workflow.
- Weakens the "agent delegated access" product boundary.

Best fit:

- Enterprises that already have a complete external consent/grant platform.

---

## Provisional recommendation

Adopt **Option A: AIB as delegated OAuth/token broker** for 1.0.

Initial responsibility split:

| Component | Owns |
|---|---|
| KAOS CRDs/operator | Resource existence, topology, service wiring, `spec.security.id` |
| KAOS-AIB sync service | Mirroring KAOS identity-bearing resources into AIB records |
| KAOS/AIB SDK | Runtime context propagation, AIB client calls, SDK-native enforcement hooks |
| AIB | Agent broker records, third-party services, PermissionSets, user grants, consent, token vault, token exchange |
| External IdP | Human authentication and OIDC identity source |
| LiteLLM | ModelAPI keys, model access, budgets/rate limits where used |
| GatewayAPI 1.1 | Resource-boundary auth, JWT validation, bypass prevention with NetworkPolicy |
| OPA/Keycloak AuthZ | Future optional policy/PDP integration if requirements outgrow AIB CEL/PermissionSets |

This means AIB is not the source of truth for KAOS topology, not the primary ModelAPI auth layer, and not the initial policy engine for MCP tool/argument-level authorization.

---

## Host questions required to finalize ADR-004

### Q1. Should AIB 1.0 be scoped to delegated OAuth/token broker responsibilities?

Recommended answer:

- Yes. AIB should own delegated user grants, third-party OAuth sessions, consent, and token exchange.

Tradeoff:

- This keeps 1.0 simple, but means AIB is not the central policy platform for every KAOS action.

### Q2. Should AIB be authoritative for user grants?

Recommended answer:

- Yes. AIB should be authoritative for `principal + agent + permission set` grants.
- KAOS remains authoritative for resource existence/topology.

Tradeoff:

- Grants can survive KAOS delete/recreate through stable `external_id`, but resource lifecycle and grant lifecycle must be reconciled carefully.

### Q3. Should AIB PermissionSets initially represent third-party OAuth/service scopes only?

Recommended answer:

- Yes. Do not use AIB PermissionSets for MCP tool names, MCP arguments, ModelAPI models, or Gateway routes in 1.0.

Tradeoff:

- Clean fit with current AIB model, but MCP/ModelAPI authorization remains outside AIB initially.

### Q4. Should AIB issue KAOS runtime/session tokens in 1.0?

Recommended answer:

- No. AIB should exchange existing subject/context tokens for third-party tokens, not become the KAOS runtime token issuer in 1.0.

Tradeoff:

- Avoids making AIB an IdP replacement, but means KAOS/SDK/Gateway must define the trusted inbound token/header model.

### Q5. Should the SDK call AIB directly in 1.0?

Recommended answer:

- Yes. SDK-native calls should be the first integration path for grants, token exchange, and approval-required handling.

Tradeoff:

- Faster path for Agent/MCP integration, but proxy-based ExtProc benefits are deferred.

### Q6. Should AIB ExtProc be deferred to GatewayAPI 1.1?

Recommended answer:

- Yes. Keep ExtProc as an important future integration for Gateway/resource-boundary token exchange, but do not require it for 1.0.

Tradeoff:

- 1.0 does not get transparent proxy token rewriting, but avoids blocking SDK-first work on Gateway-specific configuration.

### Q7. Should ADR-004 explicitly say AIB does not replace Keycloak/Dex/OIDC for human authentication?

Recommended answer:

- Yes. AIB should rely on an external IdP/trusted authentication boundary for human identity.

Tradeoff:

- Clear separation of concerns, but environments still need an IdP or trusted UI/backend authentication layer.

### Q8. Should OPA/Rego be part of AIB 1.0?

Recommended answer:

- No. Defer OPA/Rego until the authorization-policy ADR. AIB CEL and PermissionSets are sufficient for current token-exchange grant checks.

Tradeoff:

- Avoids adding a policy-engine dependency too early, but may need revisiting for complex enterprise policies.

---

## Proposed ADR-004 decision if host agrees

1. AIB is the delegated OAuth/token broker for KAOS 1.0.
2. AIB is authoritative for user delegated grants and third-party OAuth sessions.
3. KAOS remains authoritative for CRDs, topology, resource identity, and runtime orchestration.
4. AIB PermissionSets initially represent third-party service scopes only.
5. AIB does not issue KAOS runtime/session tokens in 1.0.
6. SDK-native AIB calls are the first integration path.
7. AIB ExtProc is deferred to the GatewayAPI 1.1 resource-boundary extension.
8. AIB does not replace Keycloak/Dex/OIDC for human authentication.
9. OPA/Rego integration is deferred to the authorization-policy decision.

## Decision status

Awaiting host answers.
