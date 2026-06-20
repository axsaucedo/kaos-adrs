# ADR-011: Gateway API resource-boundary enforcement

**Status**: Proposed
**Date**: 2026-06-20

---

## Decision

Define a Gateway API resource-boundary mode for KAOS where internal Agent-to-Agent, Agent-to-MCPServer, and Agent-to-ModelAPI traffic can be routed through Gateway routes instead of direct ClusterIP service URLs.

In this mode, Gateway becomes the default resource access path for protected KAOS resources:

```text
Agent -> Gateway route -> MCPServer
Agent -> Gateway route -> ModelAPI
Agent -> Gateway route -> Agent
External client -> Gateway route -> Agent/MCPServer/ModelAPI
```

Direct ClusterIP Services remain necessary for Kubernetes mechanics such as service discovery, backend selection, and health checks, but they should not remain open as the normal application-level access path for protected resource calls. In strict Gateway mode, KAOS should pair Gateway routing with NetworkPolicy so:

- Gateway-to-backend application traffic is allowed,
- required platform traffic such as kubelet probes, DNS, operator access, Gateway, and AIB is allowed,
- direct workload-to-workload application traffic to protected ClusterIP Services is denied where the CNI supports it.

Health endpoints must not become a general bypass path. If the cluster/CNI can distinguish probe or platform traffic, health-check access should be narrowed to those actors; otherwise the policy must document the remaining limitation.

Gateway enforcement is a resource-boundary layer. It can host the equivalent of `require_access` for coarse resource-level checks such as:

```text
principal/subject + calling actor -> target KAOS resource
```

That means Gateway can reject requests before they reach the target workload when the caller is not allowed to access the Agent, MCPServer, or ModelAPI route. It should also enforce bearer-token presence, token exchange, normalized context headers, and bypass prevention. It should not replace SDK/runtime semantic checks for:

- MCP tool-level authorization,
- MCP argument-level authorization,
- agent run/session semantics,
- A2A delegation semantics,
- re-authentication retry handling in application flows.

AIB ExtProc can be used as one Gateway integration mode because the current AIB code implements Envoy's External Processing API and performs header-phase token exchange. However, the current AIB ExtProc is resource/header-oriented, not KAOS-resource-aware or MCP-tool-aware. KAOS must configure resource URIs, routing, and header conventions explicitly rather than assuming ExtProc understands KAOS CRDs.

Pure Gateway + AIB enforcement is possible only for coarse resource-level `require_access` semantics, and only if the Gateway integration has an auth-required policy plus an AIB decision/token-exchange path that fails closed for denied resource access. Current AIB ExtProc is close for token exchange but is not by itself a complete `require_access` implementation because no-Bearer requests pass through and current AIB does not yet expose first-class KAOS platform/resource grants.

---

## Context

[ADR-002](./ADR-002-enforcement-topology.md) accepts SDK-first security for 1.0 and defers Gateway API resource-boundary enforcement to a later extension.

[ADR-003](./ADR-003-user-request-context-propagation.md) defines propagated context headers such as:

```text
x-request-id
x-principal
x-actor
x-aib-context-id
x-aib-session-id
x-aib-delegation-chain
x-aib-scopes
authorization
```

[ADR-007](./ADR-007-transport-security-and-hardening-baseline.md) defers Gateway + NetworkPolicy boundary hardening from the minimal 1.0 transport baseline.

This ADR defines the scope of that Gateway extension and the integration modes KAOS must consider.

---

## Source facts

### Current KAOS Gateway API support

Source files:

- `operator/pkg/gateway/gateway.go`
- `operator/api/v1alpha1/gateway_types.go`
- `operator/chart/templates/gateway.yaml`
- `operator/controllers/agent_controller.go`
- `operator/controllers/mcpserver_controller.go`
- `operator/controllers/modelapi_controller.go`

Current KAOS Gateway facts:

- `GatewayRoute` only models request timeout.
- The chart can create a Gateway when `gatewayAPI.enabled` and `gatewayAPI.createGateway` are true.
- The chart's default Gateway listener is HTTP on port 80.
- `ReconcileHTTPRoute` creates `HTTPRoute` objects for Agents, MCPServers, and ModelAPIs when Gateway API is enabled.
- Route paths use:

  ```text
  /{namespace}/{resourceType}/{resourceName}
  ```

- Routes apply URL rewrite to strip the path prefix before forwarding to the backend.
- Routes configure backend service and request timeout.
- Gateway route generation does not currently configure JWT validation, external auth, ExtProc, header mutation, TLS, or NetworkPolicy.
- Agent status endpoints currently use direct ClusterIP URLs:

  ```text
  http://agent-{name}.{namespace}.svc.cluster.local:8000
  ```

- MCPServer status endpoints currently use direct ClusterIP URLs:

  ```text
  http://mcpserver-{name}.{namespace}.svc.cluster.local:8000
  ```

- ModelAPI status endpoints currently use direct ClusterIP URLs:

  ```text
  http://modelapi-{name}.{namespace}.svc.cluster.local:{port}
  ```

Implication:

KAOS already has the basic HTTPRoute substrate, but gateway-default resource access requires changes to URL injection/status endpoints and new policy objects or implementation-specific Gateway extensions.

### Current NetworkPolicy support

No current operator NetworkPolicy support was found for restricting direct Agent-to-MCPServer, Agent-to-ModelAPI, or Agent-to-Agent ClusterIP access.

Implication:

Gateway routing alone does not prevent direct ClusterIP bypass. NetworkPolicy generation is required for a strong resource-boundary mode, and its effectiveness depends on the cluster CNI.

### Current AIB ExtProc implementation

Source files:

- `agentic-identity-broker/internal/extproc/server/server.go`
- `agentic-identity-broker/internal/extproc/server/exchanger.go`
- `agentic-identity-broker/internal/extproc/config/config.go`
- `agentic-identity-broker/mocks/agentgateway/config.yaml`
- `agentic-identity-broker/config.extproc.docker.yaml`

Current AIB ExtProc facts:

- AIB ExtProc implements `envoy.service.ext_proc.v3.ExternalProcessorServer`.
- The `Process` stream handles `RequestHeaders`, `RequestBody`, `ResponseHeaders`, `ResponseBody`, request trailers, and response trailers.
- The primary enforcement is in the `RequestHeaders` phase.
- It extracts a bearer token from the `Authorization` header.
- If no Bearer token is present, it passes the request through unchanged.
- It reads `:scheme`, `:authority`, and `:path`.
- It builds a resource URI as:

  ```text
  {scheme}://{authority}{path}
  ```

  unless `:path` is already an absolute `http://` or `https://` URI.

- It validates the resource URI is an absolute HTTP(S) URI.
- It performs RFC 8693 token exchange by POSTing to AIB's token endpoint with:

  ```text
  grant_type=urn:ietf:params:oauth:grant-type:token-exchange
  subject_token=<inbound bearer token>
  subject_token_type=urn:ietf:params:oauth:token-type:access_token
  resource=<resource URI>
  client_assertion=<gateway/extproc client assertion>
  client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
  ```

- On successful exchange, it uses Envoy header mutation to replace:

  ```text
  authorization: Bearer <exchanged token>
  ```

- On broker errors with `error_uri`, it returns an immediate JSON-RPC URL elicitation response.
- On exchange infrastructure failures, it returns immediate 500/503 responses.
- Request and response bodies are passed through unchanged.
- Trace context can be extracted from incoming headers for telemetry, but ExtProc does not inject new trace headers.
- The Docker Compose `agentgateway` config demonstrates an `extProc` policy with:

  ```text
  extProc:
    host: "extproc-token-exchange:50051"
    failureMode: failClosed
  ```

Implication:

AIB ExtProc is valid for Envoy-compatible External Processing integrations. It can replace upstream `Authorization` with an exchanged token before the request reaches a protected backend. It does not currently inject KAOS/AIB context headers such as `x-principal`, `x-actor`, or `x-aib-delegation-chain`, and it does not evaluate MCP tool names or request bodies.

### AIB ExtProc constraints for KAOS Gateway mode

Current AIB ExtProc behavior has important constraints:

1. **No bearer means pass-through**
   - Gateway policy must separately require authentication when protected resources must not accept anonymous traffic.
   - ExtProc alone is not sufficient as an auth-required policy.
   - A gateway-level `require_access` mode must fail closed before or during ExtProc if the request has no usable authenticated subject.

2. **Resource URI is derived from Gateway request headers**
   - KAOS must decide whether AIB `resource` should be the external Gateway route URI or a canonical KAOS URI.
   - Current ExtProc does not map Gateway paths to `kaos://...` resource identifiers.
   - Gateway-level `require_access` only works if AIB policy records and ExtProc `resource` values use the same resource naming convention.

3. **Header mutation is limited**
   - Current ExtProc replaces `Authorization`.
   - It does not inject `x-principal`, `x-actor`, `x-aib-*`, or AIB decision headers.

4. **Body semantics are not inspected**
   - MCP tool-level and argument-level authorization still require SDK/runtime checks or a future MCP-aware proxy.

5. **Gateway API portability varies**
   - Standard `HTTPRoute` covers routing, filters such as URL rewrite and request header modification, backend refs, and timeouts.
   - JWT validation, external authorization, and Envoy ExtProc are implementation-specific extensions or policy resources, not portable core `HTTPRoute` behavior.

---

## Gateway integration modes

### Mode 0: SDK-only direct service mode

Current 1.0 baseline:

```text
Agent -> direct ClusterIP -> MCPServer/ModelAPI/Agent
SDK/native runtime performs context propagation and AIB calls
```

Properties:

- Simple.
- Works without Gateway or NetworkPolicy.
- Does not prevent direct ClusterIP bypass.
- Required for local/dev and initial SDK rollout.

### Mode 1: Gateway routing only

KAOS injects Gateway URLs instead of ClusterIP URLs:

```text
Agent -> Gateway HTTPRoute -> MCPServer/ModelAPI/Agent
```

Gateway handles:

- routing,
- path prefix,
- URL rewrite,
- timeouts,
- optional request-header mutation where portable.

Properties:

- Establishes the Gateway as the normal access path.
- Does not by itself authenticate, authorize, exchange tokens, or block direct ClusterIP bypass.
- Useful migration step before stricter enforcement.

### Mode 2: Gateway routing plus normalized headers

Gateway validates or trusts an upstream authentication boundary, then injects normalized context headers:

```text
x-request-id
x-principal
x-actor
authorization
```

Optionally, AIB/SDK-aware components propagate:

```text
x-aib-context-id
x-aib-session-id
x-aib-delegation-chain
x-aib-scopes
```

Properties:

- Gives SDK/native runtimes a consistent inbound context.
- Header trust must be boundary-scoped: workloads must not trust arbitrary client-supplied identity headers unless Gateway or another trusted boundary overwrote them.
- Portable Gateway API may support basic request header modification, but identity extraction/JWT validation remains implementation-specific.

### Mode 3: Gateway routing plus AIB ExtProc token exchange

Envoy-compatible Gateway/agentgateway calls AIB ExtProc before forwarding:

```text
Agent/client request with subject token
  -> Gateway ExtProc
  -> AIB token exchange
  -> Authorization header replaced with exchanged downstream token
  -> upstream MCPServer/ModelAPI/Agent
```

Properties:

- Validated against current AIB code: AIB ExtProc implements Envoy ExtProc and mutates `authorization`.
- Best fit for resource-level token exchange at the Gateway boundary.
- Requires a Gateway implementation that supports Envoy ExtProc or compatible policy.
- Requires an ExtProc Deployment, gRPC service, client credentials, and AIB token endpoint configuration.
- Requires a separate auth-required policy because current AIB ExtProc passes through requests without Bearer tokens.
- Still does not provide MCP tool/argument authorization.

### Mode 3b: Gateway routing plus AIB resource `require_access`

Gateway or an Envoy-compatible extension calls AIB before forwarding and fails closed unless AIB says the caller may access the target resource.

Conceptually:

```text
subject token + actor + target resource
  -> Gateway policy / ExtAuthz / ExtProc
  -> AIB resource authorization
  -> allow or deny before backend
```

Properties:

- This is feasible for coarse route/resource authorization.
- It can remove the need for every application to call `require_access` for simple Agent-to-MCPServer, Agent-to-ModelAPI, or Agent-to-Agent root access checks.
- It still requires application-level checks for tool names, tool arguments, agent run semantics, and user-facing re-authentication handling.
- It requires AIB to have first-class platform/resource grant semantics or a clearly documented bootstrap encoding.
- It may require extending current AIB ExtProc or using a separate Envoy `ext_authz`/Gateway authorization integration, because current ExtProc is token-exchange-oriented and no-Bearer pass-through is not fail-closed authorization.

### Mode 4: Gateway routing plus NetworkPolicy bypass prevention

KAOS generates NetworkPolicies that allow protected workloads to receive traffic from Gateway and required platform components, while denying direct application traffic from arbitrary Agents or other workloads.

Example target:

```text
allow Gateway -> MCPServer
allow Gateway -> ModelAPI
allow Gateway -> Agent
allow kubelet/probes as needed
deny Agent -> MCPServer direct ClusterIP
deny Agent -> ModelAPI direct ClusterIP
deny Agent -> Agent direct ClusterIP
```

Properties:

- This is the first mode that materially reduces direct ClusterIP bypass.
- Depends on CNI NetworkPolicy enforcement.
- Requires careful labels, namespace selectors, health/probe exceptions, and AIB/Gateway egress rules.
- Should be opt-in until tested across supported local and production clusters.

### Mode 5: Gateway resource-boundary required mode

The strict target combines:

```text
Gateway route URLs injected into runtimes
Gateway auth-required policy
Gateway/AIB ExtProc or equivalent resource authorization/token exchange
NetworkPolicy direct-bypass restriction
SDK/native semantic checks inside Agent/MCPServer
```

Properties:

- Strongest Gateway-based KAOS extension.
- Default application path is Gateway.
- Direct ClusterIP application calls are blocked where NetworkPolicy supports it.
- Gateway handles coarse resource boundary; SDK handles semantics.

---

## Required KAOS changes

### URL injection

Add a security/gateway mode where operator-injected runtime URLs prefer Gateway routes:

```text
MCP_SERVER_<name>_URL = http(s)://<gateway>/<namespace>/mcp/<name>
MODEL_API_URL         = http(s)://<gateway>/<namespace>/modelapi/<name>
AGENT_<name>_URL      = http(s)://<gateway>/<namespace>/agent/<name>
```

Status should distinguish:

```text
status.endpoint.clusterIP
status.endpoint.gateway
status.endpoint.active
```

or equivalent fields, so users can tell whether runtime traffic uses direct service or Gateway path.

### Gateway route policy model

Extend `GatewayRoute` beyond timeout to represent:

```text
enabled
gatewayRequired
authRequired
headerPropagation
aibExtProc
networkPolicy
```

This should likely be driven by global security profile defaults, with per-resource overrides only when needed.

### Header conventions

Gateway and SDK must agree on:

```text
x-request-id
x-principal
x-actor
x-aib-context-id
x-aib-session-id
x-aib-delegation-chain
x-aib-scopes
authorization
traceparent
baggage
```

Rules:

1. Gateway or trusted upstream auth boundary may set generic identity headers.
2. SDK may propagate headers downstream.
3. Workloads must only trust identity headers from configured trusted boundaries.
4. Client-supplied identity headers must be stripped or overwritten at Gateway.
5. Raw bearer tokens must not be logged or stored in durable task state.

### AIB ExtProc configuration

For AIB ExtProc mode, KAOS needs to define:

- ExtProc service endpoint.
- AIB token endpoint.
- ExtProc client credentials.
- expected subject token type.
- token-exchange audience and client assertion requirements.
- resource URI convention.
- failure behavior.

The resource URI convention is critical. Current AIB ExtProc sends the HTTP resource URI derived from `:scheme`, `:authority`, and `:path`; KAOS must ensure AIB records use the same URI or contribute/extend mapping to canonical KAOS resource IDs.

### NetworkPolicy generation

For strict Gateway mode, generate policies that:

- allow Gateway to call protected services,
- allow required kubelet probes, DNS, operator, Gateway, and AIB traffic as needed,
- allow workload egress to Gateway and AIB as needed,
- deny direct workload-to-protected-service application traffic.

This does not mean keeping all ClusterIP traffic open. The intended target is that ClusterIP Services still exist, but protected application traffic is only generally reachable through Gateway. This should be opt-in and clearly documented because it depends on CNI support and can break deployments if selectors are wrong.

---

## Annex: Alternatives considered

### Option A: Keep ClusterIP direct access as the only internal mode

Rejected for the Gateway extension.

This keeps the system simple, but it cannot provide a strong resource boundary or bypass prevention. It remains the 1.0 SDK-first baseline and local/dev mode.

### Option B: Gateway routing without NetworkPolicy

Accepted only as an intermediate mode.

It moves runtime traffic through Gateway but does not prevent direct ClusterIP bypass. It is useful for migration and observability, but it should not be described as strict enforcement.

### Option C: Gateway plus AIB ExtProc as the only enforcement

Rejected as complete enforcement.

AIB ExtProc can exchange tokens and mutate `Authorization`, but current code passes through requests without Bearer tokens and does not inspect MCP body/tool semantics. It must be combined with auth-required policy and SDK/runtime checks.

### Option C2: Gateway-level `require_access` for all authorization

Rejected as complete enforcement.

Gateway-level `require_access` is appropriate for coarse route/resource access, but Gateway does not understand every application semantic. It cannot decide MCP tool arguments, agent run/session state, or multi-step re-authentication retry behavior without pushing application semantics into the Gateway extension.

### Option D: Gateway plus NetworkPolicy plus SDK checks

Accepted as the target Gateway resource-boundary architecture.

Gateway handles coarse resource boundary, token exchange, and route-level `require_access` where AIB supports it. NetworkPolicy reduces direct bypass. SDK/runtime handles semantic checks and user-facing grant/re-auth flows.

### Option E: Sidecar instead of Gateway

Deferred.

Sidecars can help for local egress token injection or runtimes that cannot route through Gateway, but they add pod complexity and are not required for the Gateway resource-boundary target.

---

## Consequences

### Positive

- Gives KAOS a clear path from SDK-only enforcement to Gateway-enforced resource boundaries.
- Makes Gateway the default application access path for protected resources when enabled.
- Reduces direct ClusterIP bypass when paired with NetworkPolicy.
- Allows AIB ExtProc to be used where Envoy-compatible Gateway support exists.
- Keeps SDK/runtime semantic enforcement in place instead of overloading Gateway.
- Makes integration modes explicit and testable.

### Negative

- Requires operator changes to inject Gateway URLs instead of ClusterIP URLs.
- Requires Gateway implementation-specific policy resources for JWT validation, external auth, ExtProc, or advanced header mutation.
- Requires NetworkPolicy generation and CNI-dependent validation.
- Requires careful resource URI alignment between Gateway routes and AIB records.
- Adds another deployment component if AIB ExtProc is used.

### Risks

- If Gateway mode is enabled without NetworkPolicy, users may overestimate bypass protection.
- If ExtProc is used without auth-required policy, no-Bearer requests may pass through unchanged.
- If Gateway-injected identity headers are not stripped/overwritten, clients may spoof `x-principal` or `x-actor`.
- If URL rewrite changes the URI that ExtProc sees, AIB `resource` mapping may not match expected records.
- If NetworkPolicy selectors are wrong, workloads may lose access to required Gateway, AIB, DNS, or health probe traffic.
- If gateway-level `require_access` is presented as complete authorization, users may skip SDK/runtime checks that are still required for tool, argument, and workflow semantics.

---

## Decision summary

1. Add a Gateway API resource-boundary mode as the next hardening layer after SDK-first security.
2. In this mode, protected runtime URLs should use Gateway routes by default instead of direct ClusterIP service URLs.
3. Gateway routing alone is not strict enforcement; strict mode requires NetworkPolicy bypass prevention where supported.
4. Gateway should enforce coarse resource boundary, route-level `require_access` where AIB supports it, auth-required policy, token exchange, normalized headers, and audit at the request boundary.
5. SDK/native runtime code remains responsible for semantic Agent/MCP/ModelAPI behavior and user-facing grant/re-auth handling.
6. AIB ExtProc is a valid Envoy-compatible integration mode for token exchange and `Authorization` header replacement.
7. Current AIB ExtProc does not inject KAOS/AIB context headers and does not inspect MCP tool bodies; those remain SDK/runtime responsibilities unless ExtProc is extended.
8. KAOS must define a resource URI convention that matches what AIB ExtProc sends in token-exchange `resource`.
9. KAOS must not present Gateway mode as bypass-safe unless NetworkPolicy is enabled and validated.
10. ClusterIP Services should remain for Kubernetes mechanics, but strict Gateway mode should deny direct workload-to-workload application traffic to protected resources where supported.
11. Sidecars remain deferred unless a specific non-Gateway or egress-token-injection requirement appears.
