# ADR-003: Enforcement topology

## Status

Proposed. Requires host decisions before acceptance.

## Context

ADR-002 showed that user/request context propagation depends on where KAOS enforces authentication, token exchange, and authorization. Gateway, sidecar, native runtime, and no-enforcement approaches all imply different token and context propagation requirements.

This ADR is intentionally moved before finalizing ADR-002.

The core question is:

```text
Where should KAOS enforce authentication, token exchange, and authorization for Agent, MCPServer, ModelAPI, A2A, and third-party API traffic?
```

## Source facts from KAOS

### Gateway API is supported but not used for all internal traffic

Source files:

- `operator/pkg/gateway/gateway.go`
- `operator/controllers/agent_controller.go`
- `operator/controllers/mcpserver_controller.go`

Current behavior:

- KAOS can create `HTTPRoute` resources for Agents, MCPServers, and ModelAPIs.
- Route path format is:

  ```text
  /{namespace}/{resourceType}/{resourceName}
  ```

- Gateway routing strips the prefix and forwards to the backing Kubernetes Service.
- Gateway integration currently handles routing and timeout only.
- It does not configure authn, authz, TLS, JWT validation, external authorization, ExtProc, or header mutation.
- Agent runtime currently receives direct MCP URLs from the operator:

  ```text
  http://mcpserver-{name}.{namespace}.svc.cluster.local:8000
  ```

Implication:

- KAOS already has a central external routing layer.
- But Agent-to-MCP internal calls do not automatically pass through Gateway today.
- If Gateway is chosen for internal enforcement, operator URL injection must change.

### Sidecars are possible through podSpec but not first-class

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

Current behavior:

- Agent, MCPServer, and ModelAPI expose `spec.podSpec`.
- MCPServer has first-class `spec.serviceAccountName`.
- KAOS does not currently have a first-class sidecar/security proxy configuration.

Implication:

- Users can technically inject sidecars manually today.
- A target picture can introduce sidecar support later without proving it in the current implementation.
- First-class sidecar support would require CRD/operator work.

### Native runtime/MCP auth is not implemented

Source files:

- `pydantic-ai-server/pais/server.py`
- `pydantic-ai-server/pais/serverutils.py`
- `mcp-servers/python-string/server.py`
- `mcp-servers/fastmcp-codemode/server.py`

Current behavior:

- Agent runtime does not validate inbound user auth.
- A2A delegates with tracing headers only.
- MCP runtimes do not configure FastMCP auth/JWT validation.
- Pydantic AI MCP client supports static headers, but KAOS does not pass any.

Implication:

- Native runtime enforcement is possible but requires application/runtime changes.
- Native enforcement gives best semantic context but highest code-surface responsibility.

## Source facts from AIB

### AIB ExtProc supports token exchange at proxy boundary

Source file:

- `agentic-identity-broker/internal/extproc/server/server.go`

Current behavior:

- AIB ExtProc implements Envoy External Processing gRPC.
- It extracts a Bearer token from request headers.
- It constructs a resource URI from request pseudo-headers.
- It exchanges the token and replaces the upstream `Authorization` header.
- If no Bearer token exists, it passes through.
- It passes request/response bodies through unchanged.
- It can return an approval/reauth URL-style response when broker errors contain `error_uri`.

Implication:

- AIB already fits Gateway/Envoy or sidecar token exchange.
- It is currently resource/header-oriented, not MCP-tool-aware.
- It does not by itself enforce fine-grained MCP tool authorization from request body.

## External facts

### Envoy ext_authz

External reference:

- Envoy External Authorization filter docs.

Relevant facts:

- Envoy `ext_authz` calls an external HTTP/gRPC service to decide whether a request is authorized.
- Unauthorized requests can be rejected with `403`.
- The authz service can receive request metadata and optionally request body content.
- Returned metadata can be propagated to upstream/downstream.

Implication:

- `ext_authz` fits allow/deny authorization.
- It is not primarily a token rewriting mechanism.
- It can inspect limited body data, but body-based MCP authorization adds buffering and parsing complexity.

### Envoy ext_proc

External reference:

- Envoy External Processing filter docs.

Relevant facts:

- Envoy `ext_proc` connects an external processor into the request/response lifecycle.
- The processor can examine and modify headers, bodies, and trailers.
- It can return a brand-new response.

Implication:

- `ext_proc` fits token exchange/header mutation.
- It can be extended for body-aware MCP decisions, but that is more complex than header-only exchange.

### Gateway API HTTPRoute

External reference:

- Gateway API HTTP routing guide.

Relevant facts:

- `HTTPRoute` matches HTTP traffic by host, path, and headers and forwards it to Kubernetes Services.
- Multiple routes can attach to a Gateway.

Implication:

- Gateway API is appropriate for coarse HTTP routing.
- Fine-grained auth filters are implementation-specific and generally require GatewayClass-specific policy resources or Envoy/agentgateway configuration.

## Enforcement surfaces

The target picture has several distinct traffic classes:

| Traffic class | Example | Security need |
|---|---|---|
| External user to Agent | UI/user calls `/v1/chat/completions` | User authentication, request context creation |
| External user to MCPServer | User or tool client calls MCP directly | User auth, service/tool authorization |
| Agent to MCPServer | Agent tool call | User/agent delegated auth, token exchange |
| Agent to Agent | A2A delegation | Delegation context, user/agent lineage |
| Agent to ModelAPI | LLM call | Agent/service auth, cost/rate control |
| MCPServer to third-party API | Tool calls external API | User delegated OAuth token |
| Agent autonomous loop | Startup/self-looping | Agent grants, run correlation |

No single enforcement point solves all of these cleanly.

## Options

### Option A: Gateway-first enforcement

All protected HTTP traffic should go through Gateway where possible. Gateway/Envoy policies, `ext_authz`, and/or AIB `ext_proc` enforce authentication, authorization, and token exchange.

Pros:

- Centralized control point.
- Leverages existing KAOS Gateway integration.
- Good for external user-to-Agent/MCP/ModelAPI ingress.
- Can use AIB ExtProc for token exchange without modifying upstream services.
- Operationally simpler than per-pod sidecars.

Cons:

- Agent-to-MCP calls currently bypass Gateway.
- Forcing internal traffic through Gateway requires operator URL injection changes.
- Gateway has less semantic visibility into agent run state and tool intent.
- MCP tool-level authorization through Gateway requires request body parsing/buffering.
- Gateway policy/filter support may depend on the selected Gateway implementation.

Best fit:

- Ingress auth.
- Coarse-grained resource-level enforcement.
- Token exchange by protected resource URI.

### Option B: Sidecar/local proxy enforcement

Agents and/or MCPServers use a local sidecar proxy for token exchange/authz. Agent calls `localhost` or sidecar-controlled upstreams; sidecar forwards to MCP/API after checks.

Pros:

- Protects internal service-to-service traffic without routing everything through central Gateway.
- Avoids modifying MCP server application code.
- Can be closer to runtime context.
- Can become MCP-aware later.
- Works well for Agent-to-MCP and MCP-to-third-party paths.

Cons:

- More pods/containers and operational complexity.
- Requires sidecar injection/configuration support.
- Needs a way for the Agent to pass user/request context to sidecar.
- Failure modes become distributed.
- More complex debugging.

Best fit:

- Internal Agent-to-MCP enforcement.
- Environments where internal traffic should not hairpin through Gateway.
- Later fine-grained MCP-aware enforcement.

### Option C: Native runtime/MCP enforcement

Agent runtime, A2A client/server, and MCP servers validate tokens/context directly.

Pros:

- Best semantic visibility.
- Runtime knows user request, session, task, delegation chain, and tool call.
- Most precise for MCP tool-level authorization and approval.
- Avoids extra proxy infrastructure.

Cons:

- Requires application code changes across runtime and MCP servers.
- Harder to enforce uniformly for custom MCP servers.
- More security-sensitive code in KAOS/Python runtimes.
- Each language/runtime needs support.

Best fit:

- Request context capture.
- A2A delegation metadata.
- Tool-level decisions when proxy/body parsing is insufficient.

### Option D: No enforcement initially; context only

Initial implementation captures context and syncs AIB identities/grants, but does not enforce authz/token exchange in request paths.

Pros:

- Very simple.
- Good for demos/research.
- Lets ADR-002 proceed without choosing topology.

Cons:

- Not a security implementation.
- Does not meet the target picture for protected MCP/third-party access.
- Risks building context plumbing that later conflicts with enforcement topology.

Best fit:

- Explicit prototype only.

### Option E: Hybrid staged topology

Use different enforcement points for different traffic classes:

1. Gateway for external ingress.
2. Runtime context for per-run/request identity.
3. Native A2A metadata propagation for delegation.
4. Defer Agent-to-MCP enforcement choice to either sidecar or Gateway path after minimal context exists.
5. Use AIB ExtProc where token exchange is needed at a proxy boundary.
6. Keep ServiceAccounts/SPIFFE out of the initial implementation.

Pros:

- Matches the fact that no single point solves all flows.
- Keeps initial scope simple.
- Avoids premature sidecar mandate.
- Preserves path to Gateway, sidecar, or native enforcement.
- Lets ADR-002 finalize the context model without deciding all token mechanics.

Cons:

- Less clean than a single topology.
- Requires explicit phase boundaries to avoid ambiguity.
- Some enforcement remains deferred.

Best fit:

- KAOS target picture with staged implementation.

## Provisional recommendation

Adopt **Option E: Hybrid staged topology**.

Initial target posture:

| Traffic class | Initial enforcement direction |
|---|---|
| External user to Agent/MCP/ModelAPI | Gateway-authenticated ingress, or trusted upstream auth headers |
| Agent runtime execution | Native `RequestSecurityContext` capture |
| A2A delegation | Native non-secret context/delegation metadata propagation |
| Agent-to-MCP | Keep direct initially; choose Gateway URL or sidecar in a later implementation phase |
| MCPServer-to-third-party API | AIB token exchange is target; exact proxy/native path to be decided |
| ModelAPI | Keep in identity model; enforcement can start at Gateway/route level |
| Autonomous runs | Agent identity plus correlation only |

This means ADR-003 should not mandate sidecars or all-through-Gateway initially. Instead, it should decide:

- Gateway is the preferred ingress enforcement point.
- Runtime context is required regardless of Gateway/sidecar.
- Sidecars are a later production/internal enforcement option, not initial baseline.
- Native runtime changes are required for context and A2A metadata, not necessarily all authz.
- AIB ExtProc is useful where an Envoy/Gateway/sidecar boundary exists.

## Why runtime context is still required

Gateway or sidecar enforcement only sees the request at that hop.

If the flow is:

```text
User -> Gateway -> Agent -> MCP
```

then Gateway sees `User -> Agent`, but not `Agent -> MCP` unless the Agent's MCP call also goes through Gateway.

If the flow is:

```text
User -> Gateway -> Agent -> local sidecar -> MCP
```

then the sidecar sees `Agent -> MCP`, but it still needs the Agent to pass some user/run/delegation context or token.

Therefore, ADR-002 remains necessary regardless of topology:

- Gateway/sidecar enforce.
- Runtime context carries who/what the Agent is acting for across multi-step reasoning and delegation.

## Host questions required to finalize ADR-003

### Q1. Is Gateway the preferred ingress enforcement point?

Provisional answer:

- Yes. Use Gateway/trusted upstream auth as the first external boundary.

Host decision:

- Should Agent/MCP/ModelAPI external access always be routed through Gateway for target architecture?

### Q2. Should Agent-to-MCP internal calls go through Gateway in the initial target?

Options:

| Option | Meaning | Tradeoff |
|---|---|---|
| Keep direct ClusterIP initially | Current behavior | Simple, but no proxy enforcement |
| Use Gateway URLs internally | Central enforcement | Hairpin/route complexity, needs token forwarding |
| Use sidecar URLs | Local enforcement | More pod complexity |

Provisional answer:

- Keep direct initially, but design runtime context so Gateway/sidecar can be introduced later.

### Q3. Should sidecars be part of the first implementation?

Provisional answer:

- No. Treat sidecars as production/internal enforcement extension, not initial baseline.

Host decision:

- Is sidecar support explicitly deferred, or should it be included as a first-class target requirement now?

### Q4. Should AIB ExtProc be part of the initial topology?

Provisional answer:

- Not mandatory initially. Use AIB ExtProc when Gateway/Envoy/sidecar token exchange is introduced.

Host decision:

- Should the target picture assume Envoy/ExtProc is installed from the start, or only as an optional integration?

### Q5. What authorization granularity is required initially?

Options:

| Granularity | Enforcement point |
|---|---|
| Resource-level | Gateway/sidecar header/path auth |
| MCP server-level | Gateway/sidecar/native |
| MCP tool-level | Native runtime/MCP or MCP-aware proxy |
| Argument-level | Native runtime/MCP, approval system |

Provisional answer:

- Resource/MCP server-level initially; tool/argument-level later.

### Q6. Should ModelAPI be enforced in the initial topology?

Provisional answer:

- Keep ModelAPI identity in the target picture, but only require Gateway/resource-level protection initially.

### Q7. Should failures be fail-closed?

Provisional answer:

- For protected routes, yes: auth/token-exchange failures should fail closed.
- For routes explicitly configured as unauthenticated/dev, fail-open/pass-through is acceptable.

## Proposed ADR-003 decision if host agrees

1. Use Gateway/trusted upstream auth as the initial external ingress boundary.
2. Do not require all internal Agent-to-MCP traffic to go through Gateway initially.
3. Do not require sidecars in the first implementation.
4. Require runtime request context because Gateway/sidecar cannot preserve multi-step user intent alone.
5. Keep AIB ExtProc as an optional/progressive integration for proxy-based token exchange.
6. Start with resource/MCP server-level enforcement; defer MCP tool/argument-level enforcement.
7. Keep ModelAPI identity in scope but enforce it initially only at resource/Gateway level.
8. Protected routes fail closed; explicitly dev/unauthenticated routes may pass through.

## Decision status

Awaiting host answers.
