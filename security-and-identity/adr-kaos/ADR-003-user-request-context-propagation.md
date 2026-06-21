# ADR-003: User and request context propagation

**Status**: Accepted
**Date**: 2026-06-19
---

## Decision

Introduce an application-level **request security context** and a **propagation-only SDK**. The SDK carries verified identity/context across hops so the gateway can enforce end-to-end (ADR-011); it does **not** authenticate users and does **not** make authorization decisions — enforcement is gateway-centric.

The SDK should be separable from KAOS where possible, so it can be contributed upstream or reused by non-KAOS agentic runtimes. KAOS-specific code should mostly be adapters for KAOS identity formats, CRD-derived configuration, and AIB resource naming. The concrete SDK API is specified in [ADR-009](../adr-aib/ADR-009-aib-python-sdk-design.md).

### Two propagated identities

A protected call carries two distinct identities, which the SDK keeps separate and forwards on outbound calls so the gateway can validate both:

- **User principal (subject)** — the inbound Keycloak/OIDC user token (`Authorization: Bearer`), propagated unchanged on outbound calls.
- **Calling agent (actor)** — the workload's own AIB-issued machine token (`x-agent-authorization: Bearer`), attached by the SDK from the agent's credential.

The actor is the calling agent's own identity, never the user token's `azp`. This is what makes multi-agent delegation correct (ADR-004): when Agent B calls a resource, the gateway sees actor = B.

### Concrete SDK functions

Propagation mirrors OpenTelemetry ergonomics — instrument once, propagate automatically:

```python
import aib

aib.ctx                       # request-local context (ContextVar-backed dict)

aib.instrument_fastapi(app)   # extract verified identity at the server boundary
aib.instrument_httpx()        # inject subject + actor on outbound calls
aib.instrument_requests()
aib.instrument_fastmcp(mcp)
aib.instrument_asgi(app)

aib.ctx.to_headers()          # manual escape hatch for non-instrumented transports
```

The instrumented HTTP clients attach the agent actor token and forward the user subject token transparently (including the machine-token refresh/retry described in ADR-009), so application code does not hand-pass auth pieces.

### RequestSecurityContext

The target context model is:

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
  grant_or_reauth_context
  auth_source
```

The initial implementation can start with:

```text
RequestSecurityContext
  request_id
  session_id
  user_principal
  inbound_subject_token
  scopes
  kaos_agent_identity
```

This context should be attached to `AgentDeps` or an equivalent per-run dependency object.

### Propagation responsibilities

The SDK owns:

1. Parsing trusted inbound identity/context (forwarded by the gateway) into `RequestSecurityContext`.
2. Normalizing header names and claim names used between Agent, A2A, MCPServer, and ModelAPI calls.
3. Propagating the user subject token and attaching the agent actor token on outbound A2A/MCP/ModelAPI calls.
4. Managing the agent machine-token lifecycle (acquire/cache/refresh; see ADR-009).
5. Persisting non-secret context metadata for audit/correlation.

The SDK must not persist raw bearer tokens in memory events or durable task metadata.

### Request classes

| Request class | Context source | Initial treatment |
|---|---|---|
| User chat request | Inbound UI/API/Gateway request | Extract user principal, scopes, and subject token if present |
| A2A delegated request | Parent Agent call | Propagate original user context plus delegation metadata |
| Async A2A task | A2A task metadata | Persist non-secret correlation and delegation metadata |
| Startup autonomous run | Agent CRD config | Agent identity only, no live user context |
| MCP tool call | Agent runtime to MCP | Use request context if available; otherwise agent-only |
| ModelAPI call | Agent runtime to ModelAPI | Propagate agent/request context when ModelAPI enforcement is enabled |

### Scope of Agent custom code

Agent custom code is required for context propagation, but not necessarily for inbound JWT verification.

If a Gateway, trusted UI, or another boundary validates JWTs first, the Agent runtime can trust normalized identity headers from that boundary. The Agent still needs SDK code because the runtime is the only component that understands session, task, delegation, and multi-step reasoning context.

### Scope of MCPServer custom code

MCPServer custom code is broader than Agent custom code. MCP runtimes may need to:

- validate incoming context if not fully trusted from Gateway,
- authorize tool calls against scopes/grants,
- call AIB for token exchange or approval checks,
- expose delegated third-party tokens safely to tool code.

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) defines stable KAOS security identities through `spec.security.id`, resolving to:

| Case | Resolved identity |
|---|---|
| `spec.security.id` omitted | `kaos://{kind}/{namespace}/{name}` |
| `spec.security.id` provided | `kaos://{kind}/{id}` |

KAOS needs a way for authenticated request context to survive agent execution, A2A delegation, MCP calls, async tasks, autonomous runs, and AIB grant/token-exchange flows.

Current source behavior:

- Agent `/v1/chat/completions` reads `X-Session-ID` and OpenTelemetry headers, but does not extract user principal, authorization token, scopes, grant/re-auth context, or delegation chain.
- Memory currently records static actor values such as `app_name="agent"` and `user_id="user"`.
- `AgentDeps` contains only `session_id` and `memory`.
- A2A `RemoteAgent` injects tracing headers only and sends metadata `{"delegation": true}`.
- Agent-to-MCP uses `MCPServerStreamableHTTP(mcp_url)` with no headers or dynamic per-request context.
- Startup autonomous runs are created from `AUTONOMOUS_GOAL` with metadata `{"trigger":"startup"}` and no user request context.

This means KAOS currently has session/correlation context, not security context.

---

## Annex: Alternatives considered

### Gateway-only propagation

Gateway/Envoy/AIB ExtProc validates or exchanges tokens and forwards requests upstream.

**Rejected as the only propagation mechanism** because Gateway only sees individual HTTP hops. It does not understand agent run state, A2A delegation semantics, tool intent, or autonomous task correlation unless the application passes that context.

Gateway remains useful as the optional resource-boundary enforcement layer; see ADR-002.

### Sidecar-only propagation

A sidecar receives local Agent/MCP traffic, validates/exchanges tokens, and forwards requests.

**Rejected for the initial implementation** because sidecars add deployment complexity and still require the Agent runtime to pass user/request context to the sidecar. Sidecars remain an optional hardening mechanism for production internal enforcement or egress token injection.

### Minimal context capture only

Capture principal/session context but do not propagate or enforce it.

**Rejected as the target** because it is not a security implementation. It may be a useful implementation milestone, but the accepted architecture requires propagation to A2A/MCP/ModelAPI call paths.

---

## Consequences

### Positive

- Keeps the first implementation focused on code paths KAOS owns directly.
- Provides the semantic context that Gateway or sidecars cannot infer.
- Establishes a reusable SDK boundary that can be contributed upstream and used outside KAOS.
- Keeps the SDK focused on propagation, with enforcement owned by the gateway.
- Provides the foundation for AIB grant checks, token exchange, user-grant-required responses, third-party re-auth-required responses, and audit metadata.

### Negative

- Requires Python runtime changes in the Agent framework and KAOS MCP runtimes.
- SDK-only enforcement cannot prevent direct ClusterIP bypass for services that do not adopt the SDK.
- Non-Python/custom runtimes require SDK ports, wrappers, or Gateway enforcement.
- Dynamic per-request MCP headers may require lifecycle changes because MCP clients are currently constructed at startup.

### Risks

- Raw tokens could leak into logs or memory if the SDK boundary is not strict. Mitigation: persist non-secret metadata only and provide explicit redaction helpers.
- Context propagation could diverge between Agent, A2A, MCP, and ModelAPI if header/claim conventions are not centralized.
- Without the gateway (the development state) there is no resource-boundary enforcement; the secured target requires it.

---

## Follow-up

1. Define SDK package boundaries:
   - security context model,
   - header/claim conventions,
   - FastAPI middleware,
   - A2A propagation helpers,
   - MCP client/server helpers,
   - AIB client hooks.
2. Define which fields are safe to persist.
3. Define token redaction and logging rules.
4. Use ADR-006's fail-with-URL-and-retry behavior for consent and re-authentication, while leaving durable pause/resume to future task approval work.
