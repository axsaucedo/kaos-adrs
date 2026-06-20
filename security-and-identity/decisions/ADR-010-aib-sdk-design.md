# ADR-010: AIB SDK design

**Status**: Accepted.
**Date**: 2026-06-20

---

## Context

ADR-002 accepts SDK-first Agent/MCPServer enforcement for KAOS 1.0. ADR-003 defines the request security context that must flow through Agent, A2A, MCP, ModelAPI, and autonomous execution paths. ADR-004 through ADR-008 define AIB as the grant, consent, and delegated-token broker, while keeping policy, transport, IdP, and ModelAPI internals in their own layers. ADR-009 splits upstreamable AIB core capabilities from KAOS-local adapters.

The SDK must therefore be a narrow integration layer, not a new policy platform. It should make the accepted architecture easy to implement consistently across KAOS runtimes while keeping reusable broker logic upstreamable.

---

## Decision

Adopt a **generic SDK core plus KAOS adapters** design.

1. **AIB SDK core** provides reusable request-context, client, grant-check, token-exchange, error, and redaction primitives that can be upstreamed to AIB.
2. **KAOS SDK adapters** bind those primitives to KAOS resource identities, CRD-derived requested edges, Pydantic AI/FastAPI runtime hooks, FastMCP runtime hooks, A2A propagation, and ModelAPI/LiteLLM integration.
3. **KAOS operator/sync code** remains outside the SDK except for shared typed clients or generated configuration contracts.
4. **The SDK does not own policy definitions**. KAOS CRDs define requested topology, AIB stores approved grants, and future OPA/Keycloak integrations remain optional external PDPs.

---

## SDK responsibilities

### Request security context

The SDK owns a typed context model aligned with ADR-003:

```text
RequestSecurityContext
  request_id
  session_id
  user_principal
  inbound_subject_token
  scopes
  kaos_agent_identity
  parent_agent_identity
  delegation_chain
  approval_context
  auth_source
```

The initial implementation can support the smaller subset needed for 1.0:

```text
request_id
session_id
user_principal
inbound_subject_token
scopes
kaos_agent_identity
```

The SDK must provide explicit safe-to-persist views that exclude raw bearer tokens and sensitive third-party session material.

### AIB client operations

The SDK core should expose high-level AIB operations:

| Operation | Purpose |
|---|---|
| `check_resource_grant(source, target, action, context)` | Verify approved KAOS resource access. |
| `exchange_user_token(agent, permission_set, subject_token, context)` | Retrieve delegated third-party access token through AIB token exchange. |
| `build_consent_url(agent, permission_set, context)` | Surface user-consent action when AIB reports missing grant. |
| `parse_token_exchange_error(error)` | Normalize AIB `invalid_grant`, missing consent, and re-authentication outcomes. |
| `redact_security_context(context)` | Produce log/memory-safe metadata. |

The SDK should prefer result types over broad exceptions for expected authorization outcomes.

### Structured denial model

The SDK should normalize protected-call outcomes into explicit result codes:

| Code | Meaning | Source |
|---|---|---|
| `allowed` | Grant/session/token check succeeded | SDK/AIB |
| `platform_approval_required` | KAOS resource grant missing or not approved | AIB resource grant |
| `user_consent_required` | User delegated grant missing/revoked/expired | AIB UserGrant |
| `third_party_reauth_required` | Third-party session missing, expired, or lacks scopes | AIB token exchange |
| `authorization_denied` | AIB or future PDP explicitly denies access | AIB/future PDP |
| `misconfigured` | Runtime lacks required identity, AIB endpoint, client credentials, or trust config | KAOS adapter |

These codes are the contract between runtime adapters, UI/CLI clients, A2A tasks, and future Gateway integrations.

---

## KAOS runtime adapters

### Agent runtime adapter

The Agent adapter should provide:

- FastAPI middleware/dependency helpers to build `RequestSecurityContext`.
- `AgentDeps` integration so tools, A2A delegation, MCP calls, and ModelAPI calls can access context.
- A2A outbound propagation helpers for non-secret context and delegation chain metadata.
- Grant-check helpers before Agent-to-MCPServer, Agent-to-ModelAPI, and Agent-to-Agent calls.
- Structured failure responses for ADR-006 consent/re-auth retry flows.
- Redaction helpers for memory, telemetry, logs, and task metadata.

### MCPServer runtime adapter

The MCP adapter should provide:

- inbound context parsing and validation for trusted KAOS calls,
- resource-grant enforcement for Agent-to-MCPServer access,
- delegated token exchange helpers for third-party APIs,
- safe token injection into tool execution without persisting tokens,
- normalized denial errors that map back to Agent/UI/A2A behavior.

MCP tool and argument authorization remain outside the 1.0 SDK contract until KAOS models tool permissions explicitly.

### A2A adapter

The A2A adapter should provide:

- context propagation in A2A message metadata,
- parent/child agent identity tracking,
- delegation-chain updates,
- safe persistence of non-secret context metadata,
- denial payloads compatible with current fail-fast behavior.

Durable `input-required` pause/resume remains future work from ADR-006.

### ModelAPI adapter

The ModelAPI adapter should provide only root resource access checks and context propagation into the chosen ModelAPI surface.

LiteLLM remains the owner of model allowlists, provider keys, budgets, and rate limits. Ollama remains backend-only or behind a wrapper/LiteLLM surface.

---

## Package boundary

Target package split:

| Package/layer | Ownership | Contents |
|---|---|---|
| AIB SDK core | Upstream AIB | generic context types, AIB client, token exchange helpers, result codes, redaction helpers |
| KAOS Python adapter | KAOS | FastAPI/Pydantic AI/FastMCP/A2A hooks, KAOS identity mapping, runtime config loading |
| KAOS Go client/sync helpers | KAOS | sync-service client use, CRD-to-requested-edge conversion, operator config contracts |
| KAOS Gateway adapter | KAOS 1.1 | route identity mapping, Gateway/NetworkPolicy integration, optional ExtProc wiring |

The SDK core must not import KAOS CRD types. KAOS adapters may import SDK core types.

---

## Configuration model

Runtime SDK configuration should be injected by KAOS operator/sync wiring and represented as explicit runtime settings:

```text
AIB endpoint
runtime client identity/credentials
resolved KAOS resource identity
trusted inbound context mode
expected issuer/audience, if JWT validation is local
redaction/logging settings
feature flags for grant checks and token exchange
```

Configuration should fail closed when security is enabled and required AIB or identity settings are missing.

---

## Annex: Alternatives considered

### Option A: KAOS-only SDK

This would be fastest to implement but would duplicate generic AIB client and token-exchange behavior inside KAOS.

Rejected as the target. KAOS adapters should be local, but generic SDK core should be upstreamable per ADR-009.

### Option B: Fully generic AIB SDK with no KAOS adapters

This would keep AIB clean but would leave every KAOS runtime to reimplement identity mapping, context propagation, FastAPI/FastMCP/A2A hooks, and error mapping.

Rejected. KAOS needs first-class adapters so the architecture is consistently enforced across Agent and MCP runtimes.

### Option C: SDK as policy engine

This would make the SDK evaluate policies, own policy definitions, or expose plugin hooks for OPA/Keycloak/CEL policy decisions.

Rejected for 1.0. ADR-005 keeps authorization data-first and grant-table-based. Future PDP integrations should evaluate normalized inputs but not become mandatory SDK dependencies.

### Option D: Gateway/ExtProc-only SDK

This would put most SDK effort into proxy integration and minimize runtime hooks.

Rejected for 1.0. ADR-002 keeps Gateway resource-boundary enforcement for 1.1, while runtime adapters are needed immediately for semantic Agent/MCP context and token exchange.

---

## Consequences

### Positive

- Provides one consistent programming model for Agent, MCPServer, A2A, and ModelAPI integration.
- Keeps AIB reusable by separating generic SDK core from KAOS adapters.
- Preserves no-permission-by-default through explicit grant checks and fail-closed configuration.
- Aligns runtime errors with ADR-006 user consent and re-authentication behavior.
- Keeps raw tokens out of memory, telemetry, logs, and task metadata by default.

### Negative

- Requires new runtime integration work in Python Agent and MCP code paths.
- Dynamic per-request MCP context may require changes to MCP client lifecycle.
- Non-Python/custom runtimes need wrappers, ports, or Gateway enforcement.
- SDK package boundaries must be maintained carefully to avoid leaking KAOS CRD semantics upstream.

### Risks

- If adapters diverge, Agent, MCPServer, A2A, and ModelAPI paths may enforce different semantics.
- If result codes are too generic, UI/CLI clients will not know whether to show admin approval, user consent, or re-authentication flows.
- If redaction is optional or inconsistent, raw tokens could leak into memory or logs.
- If the SDK grows policy features too early, it will conflict with ADR-005 and make future OPA/Keycloak integration harder.

---

## Decision summary

1. Build an upstreamable AIB SDK core plus KAOS-specific runtime adapters.
2. Make request context, AIB client calls, grant-check results, token-exchange helpers, structured denial codes, and redaction helpers the SDK core.
3. Keep KAOS identity mapping, CRD requested-edge extraction, operator wiring, Gateway/NetworkPolicy generation, and runtime adapters in KAOS.
4. Implement Python Agent, FastMCP, and A2A adapters first; add Go sync/operator helpers only where needed for reconciliation and configuration.
5. Do not make the SDK a policy engine, task approval system, IdP, LiteLLM replacement, Gateway controller, or transport-security layer.
6. Fail closed when security is enabled and required identity/AIB configuration is missing.
