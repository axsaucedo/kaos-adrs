# ADR-KAOS-009: Gateway API resource-boundary enforcement

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

The Envoy-compatible **Gateway is the enforcement plane** for KAOS security. When security is enabled, all Agent-to-Agent, Agent-to-MCPServer, Agent-to-ModelAPI, and external traffic to protected resources is routed through Gateway routes instead of direct ClusterIP URLs, and the Gateway enforces authentication, authorization, and token exchange:

```text
Agent / external client
  -> Gateway route
     -> jwt_authn   (validate identities)
     -> ext_authz   (AIB allow/deny resource decision)
     -> ext_proc    (AIB token exchange, when a third-party token is required)
  -> protected MCPServer / ModelAPI / Agent
```

Resource-to-resource authorization happens **only at the Gateway**, not in Python/SDK code. The SDK is propagation-only: it carries the verified identities across hops so the Gateway can enforce end-to-end. There is no partial SDK-enforced mode; security enabled is binary and **requires both the Gateway and NetworkPolicy** (below). mTLS/SPIFFE/service-mesh workload binding is future hardening.

### Two-identity authentication

Each protected request carries two identities, validated by Envoy `jwt_authn` with two providers:

| Identity | Header | Issuer | Validated against |
|---|---|---|---|
| User principal (subject) | `Authorization: Bearer` | Keycloak/OIDC | `userAuth.issuer` |
| Calling agent (actor) | `x-agent-authorization: Bearer` | AIB | `agentAuth.issuer` |

`ext_authz` then decides **actor (calling agent) -> resource**, using the user principal for user-delegated third-party grants. The decision keys on the calling agent's own AIB-issued identity, **never on `subject_token.azp`**, which is what makes multi-agent delegation correct (see ADR-KAOS-004). Autonomous runs have no user subject (actor-only). The SDK sets `x-agent-authorization` from the agent's AIB machine token and forwards the inbound user `Authorization`.

### NetworkPolicy is required, not optional

Direct ClusterIP Services remain for Kubernetes mechanics (service discovery, backend selection, health checks), but they must not be the application-level access path. Because enforcement lives only at the Gateway, security-enabled deployments **must** pair Gateway routing with NetworkPolicy so:

- Gateway-to-backend application traffic is allowed,
- required platform traffic (kubelet probes, DNS, operator, Gateway, AIB) is allowed,
- direct workload-to-workload application traffic to protected ClusterIP Services is denied where the CNI supports it.

Without NetworkPolicy the Gateway can be bypassed via ClusterIP, so it is part of the required secured target, not an add-on. Health endpoints must not become a general bypass path; narrow probe/platform access where the CNI allows it, otherwise document the limitation.

### Authorization scope

The Gateway enforces coarse resource-boundary `require_access` (can this user, through this agent, reach this Agent/MCPServer/ModelAPI), via the AIB access-check API ([ADR-AIB-002](../adr-aib/ADR-AIB-002-aib-access-check-api.md)). It does not replace runtime/SDK semantics for MCP tool-level and argument-level authorization, agent run/session state, or multi-step re-authentication retry — those remain deferred or runtime concerns.

### Backend-neutral authorization (AIB default, OPA drop-in)

The authorization integration is deliberately backend-neutral. It uses the **standard Envoy `ext_authz` gRPC contract** (`envoy.service.auth.v3.Authorization/Check`) and **neutral `kaos.resource` / `kaos.action` context_extensions**, so the decision backend is swappable with **no KAOS or Envoy configuration change**: AIB is the default, and OPA is a drop-in via the opa-envoy plugin (the backend must be fed equivalent policy/data). Keycloak remains swappable as the **IdP** (authn), not as the authz backend — Keycloak Authorization Services would need an adapter since it is not an `ext_authz` server.

### ExtProc vs ExtAuthz

ExtProc and external authorization are different Envoy extension points; AIB serves both:

| Envoy integration | Formal API | KAOS/AIB role |
|---|---|---|
| `ext_authz` / External Authorization | `envoy.service.auth.v3.Authorization/Check` | AIB allow/deny resource decision (primary authorization) |
| `ext_proc` / External Processing | `envoy.service.ext_proc.v3.ExternalProcessor/Process` | AIB token exchange / `Authorization` replacement for third-party calls |

`ext_authz` is the authorization contract; `ext_proc` token exchange is applied when a protected call needs a delegated third-party token.

---

## Context

[ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md) establishes gateway-centric enforcement, with the SDK as a propagation-only layer.

[ADR-KAOS-003](./ADR-KAOS-003-user-request-context-propagation.md) defines propagated context headers such as:

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

[ADR-KAOS-007](./ADR-KAOS-007-transport-security-and-hardening-baseline.md) makes Gateway + NetworkPolicy boundary hardening a required part of security-enabled deployments, on top of the external TLS baseline.

This ADR defines the gateway enforcement model and the operator changes it requires.

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

KAOS already has the basic HTTPRoute substrate, but gateway-default resource access requires changes to URL injection/status endpoints and new policy objects or implementation-specific Gateway policy resources.

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
   - MCP tool-level and argument-level authorization still require SDK/runtime checks or an optional MCP-aware proxy.

5. **Gateway API portability varies**
   - Standard `HTTPRoute` covers routing, filters such as URL rewrite and request header modification, backend refs, and timeouts.
   - JWT validation, external authorization, and Envoy ExtProc are implementation-specific extensions or policy resources, not portable core `HTTPRoute` behavior.

### Envoy Gateway `ext_authz` shape for AIB access checks

Envoy Gateway exposes external authorization through `gateway.envoyproxy.io/v1alpha1` `SecurityPolicy` with `spec.extAuth`. The concrete shape for a KAOS route is:

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: aib-authz-mcp-github
  namespace: default
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: mcpserver-github
  extAuth:
    grpc:
      backendRefs:
        - group: ""
          kind: Service
          name: aib-ext-authz
          port: 9002
    headersToExtAuth:
      - authorization
      - x-agent-authorization
      - x-request-id
    contextExtensions:
      - name: kaos.resource
        value: kaos://mcpserver/default/github
      - name: kaos.action
        value: access
    failOpen: false
    timeout: 500ms
    statusOnError: 503
```

Mapping to AIB:

| AIB access-check input | Gateway source |
|---|---|
| calling agent (actor) | `x-agent-authorization` agent token (AIB-issued); the decision keys on this |
| user principal (subject) | `authorization` header; used for user-delegated third-party grants |
| resource | `contextExtensions["kaos.resource"]`, generated by KAOS from the target route/backend |
| action | `contextExtensions["kaos.action"]`, usually `access` |
| request ID | `x-request-id` |

Envoy `jwt_authn` validates **both** tokens before `ext_authz`: the user subject token against `userAuth.issuer` (Keycloak) and the agent actor token against `agentAuth.issuer` (AIB). `ext_authz` then decides **actor -> resource**, using the subject only for user-delegated grants. The actor is the calling agent's own AIB identity, never `subject_token.azp`. Autonomous calls have no subject (actor-only).

---

## Enforcement flow

There is one enforcement model, not a ladder of profiles. Two deployment states exist:

**Development (no gateway):** the SDK propagates context but nothing is enforced. Suitable for local
development only; direct ClusterIP access is open and there is no authorization.

**Secured (gateway enabled):** the required target. Operator-injected runtime URLs use Gateway routes,
NetworkPolicy restricts direct ClusterIP bypass, and every protected request flows through the inline
gateway pipeline:

```text
caller request
  ( Authorization: Bearer <user subject, Keycloak>  +  x-agent-authorization: Bearer <agent actor, AIB> )
    -> jwt_authn   validate subject (userAuth.issuer) and actor (agentAuth.issuer)
    -> ext_authz   AIB decides actor (calling agent) -> target resource; user principal for delegated grants
    -> ext_proc    AIB token exchange when a delegated third-party token is required
  -> protected MCPServer / ModelAPI / Agent
```

Properties:

- Gateway is the only enforcement point; the SDK only propagates the two identities so the gateway can
  decide end-to-end.
- Resource access keys on the calling agent's own AIB-issued identity (the actor), never on
  `subject_token.azp` — this is what makes multi-agent delegation correct (ADR-KAOS-004).
- NetworkPolicy is required so the gateway cannot be bypassed via ClusterIP.
- The gateway handles the coarse resource boundary and token exchange; MCP tool/argument semantics and
  user-facing grant/re-auth flows remain runtime/SDK or deferred concerns.
- The `ext_authz` backend is swappable (AIB default; OPA drop-in) via the standard contract and neutral
  `kaos.resource`/`kaos.action` context_extensions.

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

This should be driven by global security configuration (ADR-KAOS-001 keeps per-resource config to `spec.security.id` only).

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

### Operator-wide security configuration (Helm)

Security is configured operator-wide (Helm values rendered into operator config), the same way KAOS wires other platform integrations. Presence of the `security` block implies enabled:

```yaml
security:
  userAuth:                    # human users — standard OIDC; validated at the gateway (Keycloak default, swappable)
    issuer:  https://keycloak.<domain>/realms/kaos
    audience: kaos
    jwksUri: ""                # optional; discovered from issuer .well-known
  agentAuth:                   # agent identity + authorization via AIB
    issuer:  http://aib-enduser.aib-system.svc.cluster.local:8000   # AIB OIDC issuer: mints agent tokens + JWKS
    extAuthzUrl: aib-ext-authz.aib-system.svc.cluster.local:9002    # envoy ext_authz — access checks (AIB default; OPA drop-in)
    extProcUrl:  aib-extproc.aib-system.svc.cluster.local:50051     # envoy ext_proc — token exchange
    credentialSecretPrefix: kaos-aib                                # per-agent credential Secret (operator mounts; sync creates)
```

`userAuth` and `agentAuth` become two Envoy `jwt_authn` providers. The AIB admin URL/credentials are not here — they live in the sync-service config ([ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md)). Per-resource configuration is `spec.security.id` only (ADR-KAOS-001).

The operator generates, per protected route, an Envoy `SecurityPolicy` `extAuth.grpc` pointing at `agentAuth.extAuthzUrl`, with `headersToExtAuth` including `authorization` and `x-agent-authorization`, `contextExtensions` `kaos.resource`/`kaos.action` derived from the target identity, and fail-closed behavior (`failOpen: false`, `statusOnError: 503`). Token exchange uses `agentAuth.extProcUrl` when a protected call needs a delegated third-party token.

### Agent credential mounting (operator)

When security is enabled, the operator mounts each agent's AIB credential Secret (named by `credentialSecretPrefix`, provisioned by the sync service) into the Agent/MCPServer pod. A projected-volume mount is preferred so credential rotation reloads without a restart; Kubernetes keeps the pod `Pending` until the Secret exists, which orders provisioning naturally.

### Token lifecycle and failure modes

- Pods hold long-lived **credentials**, not long-lived tokens. Actor tokens (AIB-issued) are short-lived.
- The SDK manages the actor token: **refresh-ahead caching** (refresh at a TTL fraction so the request path never refreshes), file-watched credential reload on rotation (AIB rotation has a grace window), a **single reactive retry on 401**, and backoff on AIB unavailability. The instrumented call is the seamless "ensure-fresh + inject + retry" path; no manual check-then-refresh.
- The gateway pipeline runs inline in one request pass: `jwt_authn -> ext_authz -> ext_proc -> upstream`.
- **Fail closed** always (auth is critical; there is no fail-open knob): an expired/unrefreshable actor token yields `401`/`403`; an unreachable `ext_authz`/AIB yields `503`. No silent allow.

### NetworkPolicy generation

NetworkPolicy is part of the required secured target. The operator generates policies that:

- allow Gateway to call protected services,
- allow required kubelet probes, DNS, operator, Gateway, and AIB traffic,
- allow workload egress to Gateway and AIB,
- deny direct workload-to-protected-service application traffic.

ClusterIP Services still exist for Kubernetes mechanics, but protected application traffic is only reachable through the Gateway. Effectiveness depends on CNI NetworkPolicy support, which must be validated per cluster.

---

## Annex: Alternatives considered

### Option A: Keep ClusterIP direct access as the only internal mode

Rejected as the secured target.

This keeps the system simple, but it cannot provide a strong resource boundary or bypass prevention. It remains the development state (no gateway) only.

### Option B: Gateway routing without NetworkPolicy

Not a security mode.

It moves runtime traffic through Gateway but does not prevent direct ClusterIP bypass, so it does not satisfy security-enabled. It is only a non-secured migration/observability step; the secured target requires NetworkPolicy.

### Option C: Gateway plus AIB ExtProc as the only enforcement

Rejected as complete enforcement.

AIB ExtProc exchanges tokens and mutates `Authorization`, but it is not an authorization decision point. Authorization is the `ext_authz` path; ExtProc complements it for token exchange.

### Option C1: Gateway plus AIB ext_authz for coarse resource authorization

Accepted as the target Gateway authorization integration.

Envoy `ext_authz` is the right native contract for route-level allow/deny. AIB exposes an `envoy.service.auth.v3.Authorization/Check` implementation (ADR-AIB-002). Existing AIB ExtProc remains useful for token exchange, but it is not the authorization contract.

### Option C2: Gateway-level `require_access` for all authorization

Accepted for resource-boundary authorization; tool/argument/workflow semantics are out of scope.

Gateway `ext_authz` decides route/resource access. It cannot decide MCP tool arguments, agent run/session state, or multi-step re-authentication retry — those are not part of the resource-boundary enforcement model and remain future or runtime-specific concerns, not application enforcement that KAOS mandates.

### Option D: Gateway plus NetworkPolicy (the secured target)

Accepted.

The gateway handles authentication, resource-boundary authorization, and token exchange; NetworkPolicy prevents direct ClusterIP bypass. The SDK only propagates identities. Tool/argument semantics, if ever needed, are future controls, not part of this enforcement model.

### Option E: Sidecar instead of Gateway

Deferred.

Sidecars can help for local egress token injection or runtimes that cannot route through Gateway, but they add pod complexity and are not required for the gateway enforcement target.

---

## Consequences

### Positive

- Makes the gateway the single enforcement plane for protected resources.
- Makes the Gateway the application access path for protected resources when security is enabled.
- Prevents direct ClusterIP bypass through required NetworkPolicy.
- Covers all runtimes (including ModelAPI and non-Python servers) uniformly, with no per-runtime security code.
- Keeps the SDK to propagation only, avoiding per-language enforcement duplication.

### Negative

- Requires operator changes to inject Gateway URLs instead of ClusterIP URLs and to mount agent credentials.
- Requires Gateway implementation-specific policy resources for `jwt_authn`, `ext_authz`, and `ext_proc`.
- Requires NetworkPolicy generation and CNI-dependent validation.
- Requires a resource-naming convention shared between Gateway routes and AIB records.
- Adds the AIB `ext_authz`/`ext_proc` deployment as a dependency of the secured target.

### Risks

- If NetworkPolicy is absent or the CNI does not enforce it, the Gateway can be bypassed via ClusterIP; security-enabled therefore requires it.
- If Gateway-injected identity headers are not stripped/overwritten, clients may spoof identity headers; the gateway must own `Authorization`/`x-agent-authorization`.
- If URL rewrite changes the URI the gateway derives, the `kaos.resource` value may not match AIB records.
- If NetworkPolicy selectors are wrong, workloads may lose access to required Gateway, AIB, DNS, or health probe traffic.

---

## Decision summary

1. The Envoy gateway is the enforcement plane for KAOS security; resource-to-resource authorization happens only at the gateway.
2. When security is enabled, protected runtime URLs use Gateway routes instead of direct ClusterIP URLs.
3. Security is binary: it requires both the Gateway and NetworkPolicy (gateway routing without NetworkPolicy is not a security mode).
4. The gateway enforces resource-boundary `require_access` via AIB `ext_authz`, plus `jwt_authn` (two providers) and `ext_proc` token exchange.
5. Decisions key on the calling agent's AIB-issued identity (the actor), never `subject_token.azp`; the user subject is used for user-delegated grants.
6. The SDK is propagation-only; tool/argument/workflow semantics are future or runtime-specific controls, not part of this enforcement model.
7. The `ext_authz` backend is swappable (AIB default, OPA drop-in) over the standard contract with neutral `kaos.resource`/`kaos.action`.
8. KAOS defines a resource-naming convention shared between Gateway routes and AIB records.
9. mTLS/SPIFFE/service-mesh workload binding and sidecars are deferred future hardening.
