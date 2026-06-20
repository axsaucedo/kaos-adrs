# ADR-002: Enforcement topology

**Status**: Accepted
**Date**: 2026-06-19
---

## Decision

Adopt a **layered SDK-first topology**:

1. **1.0: SDK-native Agent and MCPServer security**
   - Implement request context propagation and AIB integration in an application-level SDK.
   - Use the SDK in KAOS Agents and KAOS-owned FastMCP MCPServer runtimes.
   - Use native runtime/MCP logic for semantic authorization, tool-level checks, token exchange, and structured grant/re-auth handling.

2. **1.0: ModelAPI protected through LiteLLM where possible**
   - Prefer LiteLLM as the identity-aware ModelAPI surface.
   - Use LiteLLM custom auth, virtual keys, budgets, and model allowlists where they fit.
   - Treat Ollama as a backend behind LiteLLM or a future KAOS wrapper, not as a direct authz surface.

3. **1.1: GatewayAPI resource-boundary extension**
   - Add Gateway-based protected routing as an isolated follow-up after MCP/Agent SDK foundations.
   - When enabled, operator-injected URLs can use Gateway routes as the primary communication path.
   - Pair Gateway routing with NetworkPolicy where available to block direct ClusterIP bypass.
   - Gateway enforcement should start at JWT validation and resource-level authorization.

4. **Sidecars are deferred**
   - Do not make sidecars part of the 1.0 or 1.1 baseline.
   - Reconsider sidecars only if Gateway hairpinning, egress token injection, or non-SDK runtime support requires local enforcement.

This makes the SDK the primary 1.0 mechanism for Agents and MCPServers, while preserving Gateway as the later resource-boundary control plane for bypass prevention, ModelAPI coverage, and non-SDK/custom runtime protection.

---

## Context

KAOS needs a clear enforcement topology before request context propagation, AIB grant checks, token exchange, and grant/re-auth handling are embedded into runtime code. This ADR fixes where KAOS should enforce authentication, token exchange, and authorization across:

- external user to Agent/MCPServer/ModelAPI,
- Agent to MCPServer,
- Agent to Agent,
- Agent to ModelAPI,
- MCPServer to third-party API,
- autonomous Agent loops.

Current KAOS source facts:

- KAOS can create `HTTPRoute` resources for Agents, MCPServers, and ModelAPIs using paths like `/{namespace}/{resourceType}/{resourceName}`.
- Gateway routing currently handles routing and timeout only. It does not configure authn, authz, TLS, JWT validation, external authorization, ExtProc, or header mutation.
- Agent-to-MCP calls currently use direct ClusterIP service URLs such as `http://mcpserver-{name}.{namespace}.svc.cluster.local:8000`.
- Agent-to-Agent calls also use operator-injected direct service URLs.
- Agent, MCPServer, and ModelAPI expose `spec.podSpec`, so sidecars are technically possible but not first-class.
- Agent runtime does not validate inbound auth.
- MCP runtimes do not configure FastMCP auth/JWT validation.
- ModelAPI `Proxy` mode uses LiteLLM and can support custom auth, virtual keys, budgets, and model allowlists.
- ModelAPI `Hosted` mode uses Ollama, which should be treated as a backend model server rather than an identity-aware enforcement point.

AIB source facts:

- AIB ExtProc extracts Bearer tokens at a proxy boundary, builds a resource URI, exchanges the token, and replaces the upstream `Authorization` header.
- AIB ExtProc is resource/header-oriented today, not MCP-tool-aware.
- AIB token exchange and grant checks are directly useful for SDK-native Agent/MCPServer flows as well as proxy-mediated flows.

---

## Rationale

### Why SDK-first for 1.0

For KAOS-owned Python Agents and FastMCP MCPServers, the SDK can cover most of the functionality that Gateway could provide:

- JWT/token validation when needed,
- scope parsing,
- request context propagation,
- AIB grant checks,
- AIB token exchange,
- structured grant/re-auth handling,
- tool-level MCP authorization,
- audit metadata.

The SDK is also the only layer with full semantic access to agent run state, session, tool call, A2A delegation, and autonomous task context.

### Why still keep Gateway as 1.1

Gateway provides enforcement guarantees that SDK-only cannot:

| Advantage | Why SDK-only is weaker |
|---|---|
| Bypass prevention | SDK only runs if callers reach app code and app code integrates it. Gateway plus NetworkPolicy can block direct ClusterIP access. |
| Non-SDK runtime coverage | Custom containers, external MCP servers, pctx, Slack/Kubernetes MCPs, LiteLLM, and Ollama may not adopt the SDK. |
| Default secure posture | Gateway can protect a service before the app/runtime is security-aware. |
| TLS and ingress centralization | Gateway can own public exposure, TLS, host/path routing, and cert-manager integration. |
| Coarse rejection before work | Unauthorized requests can be rejected before hitting Agent/MCP/ModelAPI pods. |
| Boundary audit | Gateway can log allowed and denied resource-level attempts, including attempts that never reach the app. |
| Defense in depth | Gateway still enforces coarse access if SDK code is misconfigured or bypassed. |

Therefore Gateway is important, but it is not required to deliver the first useful Agent/MCPServer SDK integration.

### Why not Gateway-first in 1.0

Gateway-first would require changing operator URL injection so internal Agent-to-MCP and Agent-to-Agent traffic uses Gateway routes. It would also need Gateway implementation-specific auth policies, JWT validation, ExtAuthz/ExtProc integration, and NetworkPolicy hardening to prevent ClusterIP bypass.

That is valuable but orthogonal to the SDK work. Since Agents and MCPServers need SDK support anyway for semantic context and tool-level decisions, Gateway-first would increase 1.0 scope without removing the need for application code.

### Why not sidecars

Sidecars were considered for internal Agent-to-MCP enforcement and MCP-to-third-party token injection.

They are not selected now because:

- sidecars add pod/container complexity,
- KAOS has no first-class sidecar security configuration today,
- sidecars still need the Agent/MCP runtime to pass request context,
- debugging and failure modes become distributed,
- SDK-native MCP integration is simpler for KAOS-owned runtimes,
- Gateway can cover the resource-boundary use case later with less per-pod machinery.

Sidecars remain a future option for environments that need local egress token injection, cannot route internal traffic through Gateway, or run non-SDK MCP servers that require protection close to the workload.

---

## Enforcement boundaries

| Traffic class | 1.0 decision | 1.1/future extension |
|---|---|---|
| External user to Agent | SDK/trusted inbound context; Gateway optional | Gateway JWT validation and resource authz |
| Agent runtime execution | SDK `RequestSecurityContext` | Same |
| Agent to Agent | SDK A2A context propagation | Gateway route + NetworkPolicy if enabled |
| Agent to MCPServer | SDK context + AIB integration | Gateway route + resource authz if enabled |
| MCPServer tool authorization | SDK/native MCP logic | MCP-aware proxy only if needed |
| MCPServer to third-party API | SDK/AIB token exchange | Sidecar/egress proxy if needed |
| Agent to ModelAPI | LiteLLM custom auth where possible | Gateway resource-boundary authz |
| Ollama | Backend-only behind LiteLLM/wrapper | Gateway protects wrapper/LiteLLM, not Ollama semantics |
| Autonomous runs | Agent identity plus correlation | Future grant/approval model |

---

## Consequences

### Positive

- Keeps 1.0 focused on Agent/MCPServer paths where custom code is needed regardless of topology.
- Enables an upstreamable SDK instead of KAOS-only hardwiring.
- Preserves strong future Gateway posture without blocking SDK work.
- Avoids sidecar operational complexity in the initial design.
- Makes ModelAPI treatment explicit: LiteLLM is the auth-capable surface; Ollama is backend-only.

### Negative

- 1.0 SDK-only deployments do not prevent direct ClusterIP bypass for every service.
- Non-SDK/custom runtimes are not fully protected until Gateway or wrappers are introduced.
- Resource-level central audit is deferred to the Gateway extension.
- Some ModelAPI enforcement may depend on LiteLLM configuration or a wrapper.

### Risks

- If 1.0 is presented as complete platform security, users may overestimate protection. Documentation must call out that Gateway/NetworkPolicy is the bypass-prevention layer.
- Gateway implementation details may vary by GatewayClass, especially for JWT validation, ExtAuthz, ExtProc, and header mutation.
- NetworkPolicy enforcement depends on the cluster CNI.

---

## Follow-up

1. Define the SDK package and upstream contribution boundary.
2. Define AIB SDK APIs for grant checks, token exchange, user-grant-required responses, and third-party re-auth-required responses.
3. Define LiteLLM ModelAPI integration details.
4. Use [ADR-011](./ADR-011-gateway-api-resource-boundary-enforcement.md) for the GatewayAPI resource-boundary extension:
   - internal URL injection through Gateway,
   - JWT validation,
   - resource-level authz,
   - normalized identity headers,
   - NetworkPolicy-based ClusterIP bypass prevention.
5. Keep sidecar design deferred until a concrete requirement appears.
