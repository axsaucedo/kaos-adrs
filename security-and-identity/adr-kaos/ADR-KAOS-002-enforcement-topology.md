# ADR-KAOS-002: Enforcement topology

**Status**: Accepted
**Date**: 2026-06-19
---

## Decision

Adopt a **gateway-centric enforcement topology**.

The Envoy gateway is the enforcement plane:

- `jwt_authn` validates inbound user and agent tokens.
- `ext_authz` -> AIB makes allow/deny resource decisions.
- `ext_proc` -> AIB performs RFC 8693 token exchange.
- NetworkPolicy restricts direct ClusterIP workload-to-workload traffic.

Resource-to-resource authorization happens **only at the gateway**, not in Python or SDK code. The SDK is **not the enforcement boundary**: in the standard path it carries verified identity and request context across hops and keeps the agent actor token fresh, so the gateway can enforce end-to-end. SDK access-check and token-exchange client helpers exist but are optional, for custom servers deliberately run off-gateway; token exchange at the gateway through `ext_proc` is the standard path.

Security is binary. When KAOS security is enabled, the gateway is enabled and NetworkPolicy restricts intra-cluster ClusterIP access for workloads. Without the gateway, KAOS provides propagation only for local and development use; it does not enforce authentication, authorization, or token exchange. mTLS, SPIFFE, service mesh, sidecars, and pod-level workload identity are **out of scope** (not deferred): possession of the AIB credential under Kubernetes Secret isolation plus NetworkPolicy is the accepted trust model, and these layers are revisited only if a concrete requirement appears.

The gateway pipeline calls **both** `jwt_authn` and `ext_authz`, and this is intentional, not redundant: `jwt_authn` cryptographically validates each token (signature against JWKS, issuer, audience, expiry) and exposes verified claims, while `ext_authz` is purely an allow/deny decision call. `ext_authz` does **not** validate token signatures on its own. Validating in `jwt_authn` first means the decision backend (AIB, or an OPA drop-in) receives already-verified identity and stays a pure decision point rather than re-implementing JWKS validation — see [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md).

ModelAPI is covered uniformly by the gateway. Agents, MCPServers, and ModelAPIs use the same resource-boundary enforcement path, so ModelAPI does not need per-runtime authentication logic. LiteLLM remains responsible for model allowlists, budgets, rate limits, and model-internal policy. Ollama is treated as a backend model server behind LiteLLM or another protected KAOS surface.

Per-resource security configuration is `spec.security.id` only. Authentication, authorization, token exchange, and credential wiring are operator-wide integration concerns; CRD authors cannot override them per resource.

Sidecars are not selected, instead decision is to use gateway approach as per [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md). They may be reconsidered only for concrete future requirements such as local egress token injection or unsupported runtimes that cannot be placed behind the gateway.

---

## Context

KAOS needs a clear enforcement topology before request context propagation, AIB grant checks, token exchange, and delegated-token flows are implemented across:

- external user to Agent/MCPServer/ModelAPI,
- Agent to MCPServer,
- Agent to Agent,
- Agent to ModelAPI,
- MCPServer to third-party API,
- autonomous Agent loops.

Current KAOS source facts:

- KAOS can create `HTTPRoute` resources for Agents, MCPServers, and ModelAPIs using paths like `/{namespace}/{resourceType}/{resourceName}`.
- Gateway routing currently handles routing and timeout only. The target architecture extends that boundary with JWT validation, external authorization, ExtProc, and header mutation.
- Agent-to-MCP and Agent-to-Agent calls currently use direct ClusterIP service URLs. In the secured target, operator-injected URLs route through the gateway and NetworkPolicy blocks direct workload-to-workload bypass.
- Agent, MCPServer, and ModelAPI expose `spec.podSpec`, so sidecars are technically possible but not first-class.
- Agent and MCP runtimes do not need to become inbound authorization enforcement points in the target architecture.
- ModelAPI `Proxy` uses LiteLLM, which remains the model/budget/rate control surface. ModelAPI `Hosted` uses Ollama, which is backend-only for security purposes.

AIB source facts:

- AIB ExtProc extracts Bearer tokens at a proxy boundary, builds a resource URI, exchanges the token, and replaces the upstream `Authorization` header.
- AIB ExtProc is resource/header-oriented today, not MCP-tool-aware.
- AIB resource decisions and token exchange are directly useful at the gateway boundary.

---

## Rationale

### Why the gateway is the enforcement plane

The gateway is the only layer that can consistently enforce before requests reach KAOS workloads. It can reject unauthorized calls before runtime code executes, cover SDK and non-SDK runtimes uniformly, centralize user and agent token validation, perform token exchange on the standard request path, and produce boundary audit for allowed and denied attempts.

Gateway enforcement also pairs with NetworkPolicy. Without NetworkPolicy, direct ClusterIP calls can bypass a gateway route. With NetworkPolicy, protected workloads accept resource-to-resource traffic through the gateway path instead of direct workload-to-workload access.

### Why the SDK is not the enforcement boundary

The SDK preserves request context across Agent, MCPServer, ModelAPI, A2A, autonomous, and third-party flows, and keeps the agent's AIB actor token fresh. That is its job in the standard architecture; it does not authenticate users or enforce KAOS resource authorization.

The SDK *does* ship explicit authorization helpers — `check_access` / `require_access` (call the AIB access-check API) and `get_token` / `exchange_token` (RFC 8693 token exchange) — described in [ADR-AIB-001](../adr-aib/ADR-AIB-001-aib-python-sdk-design.md). Using them as the primary enforcement path inside application/agent code was considered and **deliberately rejected**: it would duplicate the gateway decision in every runtime and language, let custom Python become the de-facto security boundary, and make the posture depend on application correctness. Instead, the gateway's `ext_authz` enforces the resource boundary uniformly for SDK and non-SDK runtimes alike.

The helpers remain relevant at the **custom-MCP / off-gateway** level: a server intentionally run outside the gateway can call `require_access` itself to make a finer-grained decision. For example, a custom MCP server might gate an individual tool:

```python
# custom MCP server deliberately run off-gateway
client.require_access(subject=ctx.user, actor=ctx.agent,
                      resource="kaos://mcpserver/github", action="call")
```

This is an exception for custom deployments, not the standard path. KAOS does **not** currently plan tool-granular or argument-granular authorization at the gateway; coarse resource-boundary `access` is the modeled decision, and tool-level checks (if needed) are a runtime/SDK concern. Keeping enforcement at the gateway avoids duplicating decisions in application code and stops custom SDK behavior from becoming the security boundary.

### Why ModelAPI is covered by the gateway

ModelAPI contains multiple runtime shapes. LiteLLM has useful model allowlist, budget, and rate controls, while Ollama is not an identity-aware enforcement point. Placing ModelAPI behind the same gateway enforcement path avoids per-runtime auth logic and gives Agent-to-ModelAPI access the same AIB resource-grant decision as Agent-to-MCPServer and Agent-to-Agent access.

### Why mTLS, SPIFFE, sidecars, and mesh are out of scope

mTLS, SPIFFE, service mesh, workload identity, and sidecars can strengthen workload binding or local egress control, but they are not required to define KAOS resource authorization and add substantial complexity. They are therefore **out of scope** rather than a planned future phase: the gateway plus NetworkPolicy, with possession of the AIB credential under Kubernetes Secret isolation, is the accepted trust model. These layers are revisited only if a concrete requirement (e.g. cryptographic pod-to-identity proof in a hostile multi-tenant cluster) actually appears.

---

## Enforcement boundaries

| Traffic class | Without gateway (dev/local: propagation only, no enforcement) | Gateway-enforced (the secured target) |
|---|---|---|
| External user to Agent/MCPServer/ModelAPI | User token and context may be propagated, but KAOS does not enforce resource authentication or authorization. | Gateway `jwt_authn` validates the user token; `ext_authz` asks AIB for the resource decision; `ext_proc` performs token exchange when required. |
| Agent to Agent | SDK propagates context over direct service URLs; no KAOS resource authorization is enforced. | Caller presents its AIB-issued actor token; gateway `jwt_authn` validates it; `ext_authz` checks actor -> target/action; NetworkPolicy blocks direct ClusterIP bypass. |
| Agent to MCPServer | SDK propagates context over direct service URLs; no KAOS resource authorization is enforced. | Gateway validates the actor token, AIB authorizes actor -> MCPServer/action, and `ext_proc` performs token exchange for the upstream request when required. |
| Agent to ModelAPI | Calls may reach LiteLLM or a hosted backend directly; KAOS resource authorization is not enforced. | Gateway validates user/actor tokens and AIB authorizes actor -> ModelAPI/action. LiteLLM keeps model allowlist, budget, and rate internals. |
| MCPServer to third-party API | Optional SDK helper can request tokens for a custom off-gateway server; no gateway enforcement is present. | Standard path uses gateway `ext_proc` -> AIB token exchange after the gateway resource authorization decision; user-delegated grants control third-party token availability. |
| Autonomous Agent to resources | Actor context can be propagated if configured; no resource authorization is enforced. | Actor-only request is validated against the AIB agent issuer; `ext_authz` checks actor -> target/action; no user subject is required. |
| Non-SDK/custom runtime access | Runtime behavior is trusted by convention; KAOS does not enforce at the resource boundary. | Gateway applies the same `jwt_authn`, `ext_authz`, `ext_proc`, and NetworkPolicy path without requiring runtime-specific auth code. |

---

## Consequences

### Positive

- Establishes one enforcement plane for Agents, MCPServers, and ModelAPIs.
- Removes Python/SDK code from the resource-to-resource authorization boundary.
- Makes the secured posture binary and understandable: gateway plus NetworkPolicy.
- Covers non-SDK and custom runtimes through the same boundary.
- Keeps LiteLLM focused on model, budget, and rate internals instead of root KAOS resource authorization.
- Avoids sidecar operational complexity in the target architecture.

### Negative

- Local and development deployments without the gateway provide propagation only and no KAOS resource enforcement.
- The operator must inject gateway routes for protected internal calls instead of direct service URLs.
- The gateway implementation must support JWT validation, Envoy `ext_authz`, Envoy `ext_proc`, and header mutation.
- NetworkPolicy behavior depends on the cluster CNI.

### Risks

- GatewayClass capabilities may vary, especially around Envoy filters and extension points.
- If NetworkPolicy is absent or incomplete, direct ClusterIP bypass remains possible.
- AIB availability becomes part of the protected request path for authorization and token exchange.
- Documentation must clearly distinguish propagation-only local use from the secured target.

---

## Follow-up

1. Use [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md) to define the gateway enforcement pipeline in detail:
   - internal URL injection through the gateway,
   - `jwt_authn` for user and agent token validation,
   - `ext_authz` resource authorization,
   - `ext_proc` token exchange,
   - normalized identity headers,
   - NetworkPolicy-based ClusterIP bypass prevention.
2. Update operator URL injection so secured Agent-to-Agent, Agent-to-MCPServer, and Agent-to-ModelAPI calls use gateway routes.
3. Define the AIB `ext_authz` and `ext_proc` request context, including neutral resource/action fields.
4. Keep SDK work focused on context propagation, actor token lifecycle, and optional off-gateway helpers.
5. Treat sidecars, mTLS, SPIFFE, and mesh as out of scope; reconsider only if a concrete future requirement appears.
