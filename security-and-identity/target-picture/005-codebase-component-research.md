# 005 - Codebase component research for security and identity target picture

## Prompt

Ok it seems that we are now mixing the research approach. So yes, let's first start by carrying out the research in the codebase. But then let's go back to a similar approach to 002 on definnign the "research sequencing" where we go through each major architectural decision one by one, amking  a decision and then finalising the work. So for now first start with 1) research on the codebase components to gather the actual context. 2) then define a architectural sections and questions that can be used to define the major components and tradeoffs. then 3) to go through each of these components one by one so we finalise the resarch and move to next phase. 4) then we sign off the target picture, and hten we can move to defining the plan for the initial components and break it down into a set of phases to deliver.

## Response

## Scope

This note captures source-level facts from the KAOS and AIB codebases before making target-architecture decisions. It is intentionally descriptive. The next note defines the research sequencing and architecture decision sections.

## KAOS source facts

### 1. Agent CRD and logical topology

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/controllers/agent_controller.go`

Current Agent CRD fields relevant to identity/security:

- `spec.modelAPI`: referenced ModelAPI name.
- `spec.model`: model identifier.
- `spec.mcpServers`: list of MCPServer names the agent may use.
- `spec.agentNetwork.expose`: whether the agent exposes an A2A endpoint; default true.
- `spec.agentNetwork.access`: allowlist of peer agent names this agent can call.
- `spec.config.autonomous`: startup autonomous goal, interval, and per-iteration runtime limit.
- `spec.config.taskConfig`: async A2A task budgets.
- `spec.gatewayRoute`: Gateway API route settings such as timeout.
- `spec.container.env`: direct environment variable override/injection.
- `spec.podSpec`: full pod spec strategic merge override.

Implications:

- KAOS already has an infra-level declaration of which MCPServers an Agent can use and which peer Agents it can call.
- This is not yet a security policy. It is deployment wiring and dependency resolution.
- There is no first-class `spec.identity`, `spec.security`, `spec.auth`, `spec.permissions`, or `spec.approvals` section.
- Agent logical identity currently defaults to `metadata.namespace` + `metadata.name`, and runtime identity receives only `AGENT_NAME` from the operator.
- Kubernetes UID is available in object metadata but is not currently propagated into the agent runtime.
- ServiceAccount is not a first-class Agent spec field, but could be set through `spec.podSpec.serviceAccountName` because Agent exposes a full pod spec override.

### 2. Agent deployment wiring

Source file:

- `operator/controllers/agent_controller.go`

The Agent controller resolves referenced ModelAPI and MCPServers before constructing the Deployment. It injects runtime configuration through environment variables:

- `AGENT_NAME`
- `AGENT_DESCRIPTION`
- `AGENT_INSTRUCTIONS`
- `MODEL_API_URL`
- `MODEL_NAME`
- `AGENTIC_LOOP_MAX_STEPS`
- `TOOL_CALL_MODE`
- memory configuration variables
- autonomous configuration variables
- A2A task budget variables
- `MCP_SERVERS` as a comma-separated list
- `MCP_SERVER_{name}_URL` for each resolved MCPServer endpoint
- `PEER_AGENTS` as a comma-separated list
- `PEER_AGENT_{NAME}_CARD_URL` for each resolved peer Agent endpoint
- OpenTelemetry environment variables

Implications:

- The simplest initial integration point for identity metadata is operator env injection.
- Existing env injection can carry logical identity, namespace, UID, AIB URLs, token endpoint URLs, or policy mode flags.
- This is also the current place where MCP target URLs are selected. If KAOS wants agent MCP calls to go through a Gateway or sidecar instead of direct ClusterIP service URLs, this controller is one of the main places to change.
- Peer-agent A2A URLs are also injected here, so A2A auth propagation and enforcement may need changes here and in the runtime `RemoteAgent` client.

### 3. MCPServer CRD and workload identity

Source files:

- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/controllers/mcpserver_controller.go`

Current MCPServer CRD fields relevant to identity/security:

- `spec.runtime`: runtime name such as `python-string`, `kubernetes`, `slack`, or `custom`.
- `spec.params`: runtime-specific configuration string passed through an env var from the runtime registry.
- `spec.serviceAccountName`: explicit ServiceAccount for RBAC, already first-class on MCPServer.
- `spec.telemetry`: OpenTelemetry configuration.
- `spec.gatewayRoute`: Gateway API route settings.
- `spec.container.env`: direct env injection.
- `spec.podSpec`: full pod spec strategic merge override.

Implications:

- MCPServer already has first-class ServiceAccount support, mainly for runtimes such as Kubernetes that need RBAC.
- MCPServer can also be modified through `podSpec`, so sidecars can be injected manually today, even without native KAOS support.
- The controller sets `status.endpoint` to the direct in-cluster service endpoint `http://mcpserver-{name}.{namespace}.svc.cluster.local:8000`.
- MCPServer does not currently declare identity, accepted token issuers, required auth, tool-level scopes, approval requirements, or protected resource identifiers.

### 4. Gateway API routing

Source files:

- `operator/pkg/gateway/gateway.go`
- `operator/controllers/agent_controller.go`
- `operator/controllers/mcpserver_controller.go`

Gateway behavior:

- Gateway API is controlled by operator environment variables: `GATEWAY_API_ENABLED`, `GATEWAY_NAME`, `GATEWAY_NAMESPACE`, and default timeout variables.
- Route path format is `/{namespace}/{resourceType}/{resourceName}`.
- Resource types are `agent`, `modelapi`, and `mcp`.
- HTTPRoute URL rewrite strips the prefix and forwards to the target Service on port 8000.
- Gateway endpoint helper currently uses `http://{gatewayHost}/{namespace}/{resourceType}/{resourceName}`.

Implications:

- KAOS already has a central ingress/routing abstraction for Agent, MCPServer, and ModelAPI.
- Current Gateway integration does not configure authn, authz, TLS, external authorization, ExtProc, header mutation, JWT validation, or per-route security policy.
- Gateway is a strong candidate for first coarse-grained enforcement because KAOS already models all three resource types uniformly there.
- Gateway alone does not currently solve internal direct service calls because Agent runtime is injected with direct MCP ClusterIP URLs, not Gateway paths.

### 5. Agent runtime request handling

Source files:

- `pydantic-ai-server/pais/server.py`
- `pydantic-ai-server/pais/serverutils.py`

Agent runtime behavior:

- Exposes `/health`, `/ready`, `/.well-known/agent.json`, memory endpoints, `/v1/chat/completions`, and A2A JSON-RPC at `/`.
- `/v1/chat/completions` accepts OpenAI-compatible requests.
- Session is selected from `X-Session-ID` or request body `session_id`; otherwise a new session is created.
- Memory sessions are created with static actor values like `"agent"` and `"user"`.
- OpenTelemetry context is extracted from request headers.
- There is no extraction of authenticated user principal, bearer token, claims, authorization header, approval context, or inbound identity metadata.
- Agent dependencies passed into Pydantic AI tools contain `session_id` and memory only.

Implications:

- User-token propagation is not currently implemented in the Agent runtime.
- There is no per-run security context object that tools, MCP clients, or sub-agent clients can consult.
- A future KAOS integration likely needs to extend `AgentDeps` or an equivalent run context with user principal, subject token, run ID, approval context, and/or delegation metadata.
- Current memory/session model may help correlate requests, but it is not a security/session authority.

### 6. MCP client wiring in agent runtime

Source file:

- `pydantic-ai-server/pais/server.py`

MCP behavior:

- `_parse_mcp_servers()` reads `MCP_SERVERS` and `MCP_SERVER_{name}_URL` environment variables.
- Each URL is normalized to end in `/mcp`.
- Each MCP server is instantiated as `MCPServerStreamableHTTP(mcp_url)`.
- No headers, token providers, auth objects, or per-request context are passed when constructing MCP clients.

Implications:

- Current agent-to-MCP calls are direct HTTP MCP calls with no auth propagation.
- If Pydantic AI's MCP client supports static or dynamic headers, KAOS could inject tokens natively. That exact API needs separate library-level research.
- If dynamic per-request headers are not supported or are hard to wire, Gateway/sidecar enforcement becomes more attractive.
- Existing runtime code does not expose MCP tool call details to an approval system before execution, except indirectly through Pydantic AI iteration internals.

### 7. A2A delegation wiring

Source files:

- `pydantic-ai-server/pais/serverutils.py`
- `pydantic-ai-server/pais/a2a.py`

A2A behavior:

- `RemoteAgent` fetches peer agent card unauthenticated from `/.well-known/agent.json`.
- A2A `SendMessage` posts to the peer agent root `/` with JSON-RPC.
- Chat fallback posts to peer `/v1/chat/completions`.
- The only propagated headers are OpenTelemetry headers injected through `opentelemetry.propagate.inject()`.
- The A2A message metadata includes `{"delegation": true}` but no user identity, parent run ID, token, approval grant, or signed delegation.

A2A task model:

- `TaskState` includes `submitted`, `working`, `completed`, `failed`, `canceled`, and `input-required`.
- Valid transitions include `working -> input-required` and `input-required -> working`.
- Local synchronous `send_message()` creates a task, executes it inline, and returns completed/failed.
- `submit_autonomous()` creates a background asyncio task and returns immediately.
- JSON-RPC supports `SendMessage`, `GetTask`, `ListTasks`, and `CancelTask`.
- There is no route/method for providing additional input to an `input-required` task.
- The current LocalTaskManager does not actively set `input-required`; it only defines it as a valid state.
- Tasks are in-memory only in `LocalTaskManager`.

Implications:

- KAOS has a conceptual hook for pause/resume (`input-required`) but not a complete durable approval pause/resume implementation.
- Approval as "fail with approval URL then retry" is easier to fit today than true pause/resume.
- UI-mediated approve-and-resubmit may be feasible if the UI can store/replay request context, but runtime support is not yet present in the source reviewed here.
- Signed A2A delegation is not implemented; currently delegation is trust-by-network/application convention.

### 8. Autonomous execution

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/controllers/agent_controller.go`
- `pydantic-ai-server/pais/server.py`
- `pydantic-ai-server/pais/a2a.py`

Autonomous behavior:

- Agent CRD `spec.config.autonomous.goal` activates autonomous execution on startup.
- Operator injects `AUTONOMOUS_GOAL`, interval, and max iteration runtime env vars.
- Runtime starts autonomous execution during FastAPI lifespan if `autonomous_goal` is configured.
- Autonomous execution uses `task_manager.submit_autonomous(..., metadata={"trigger":"startup"})`.
- Autonomous mode loops indefinitely unless canceled or the process stops; per-iteration errors are logged and the loop continues.
- Async non-autonomous A2A mode can also use budgets for iterations/runtime/tool calls.

Implications:

- Autonomous runs are real in KAOS and need security treatment distinct from immediate user requests.
- Startup autonomous runs currently do not have user identity, run-level approval grants, or expiry metadata.
- AIB-style user grants could apply if they are long-lived delegated grants, but there is no KAOS runtime binding today between an autonomous task and a specific approved grant.

### 9. Built-in MCP runtimes

Source files:

- `mcp-servers/python-string/server.py`
- `mcp-servers/fastmcp-codemode/server.py`

MCP runtime behavior:

- `python-string` uses FastMCP and exposes Python functions from `MCP_TOOLS_STRING` over streamable HTTP.
- `fastmcp-codemode` uses FastMCP, creates proxies to configured upstream MCP URLs from `MCP_SERVERS_CONFIG`, and applies FastMCP CodeMode transform.
- Neither runtime currently configures FastMCP auth, JWT validation, token exchange, or tool-level authorization.

Implications:

- Native MCP-server authorization would require runtime changes or reusable middleware/wrappers.
- Sidecar or Gateway enforcement can protect these runtimes without modifying their code, but tool-level authorization may require MCP-aware body parsing outside the server.

## AIB source facts

### 1. AIB application wiring

Source file:

- `agentic-identity-broker/internal/app/builder.go`

AIB wires these major services:

- agent registry/service
- third-party OAuth2 provider registry/service
- permission set service
- consent service
- OAuth2 session/token vault service
- OAuth2 authorization server routes and JWKS
- token exchange service
- session-token service
- optional JWT pre-authentication
- telemetry
- encryption/key management
- in-memory or Postgres storage adapters

Implications:

- AIB is currently much more concrete as an OAuth2 delegation/token/consent broker than as a Kubernetes workload identity controller.
- AIB has the right service boundaries for delegated OAuth and token exchange, but no native KAOS CRD watcher or operator integration was identified in the reviewed code.

### 2. AIB admin routes

Source file:

- `agentic-identity-broker/internal/adapters/http/routing/admin.go`

Admin APIs include:

- `/api/agents` CRUD.
- `/api/services` CRUD.
- `/api/permission-sets` CRUD.
- `/api/agents/{agent-id}/client-credentials` generate/get/revoke.
- `/api/oauth2-server/signing-keys` add/list/set-current/remove.

Implications:

- AIB can store agent records, third-party service records, permission sets, client credentials, and signing keys.
- The source reviewed shows admin APIs, not Kubernetes-native reconciliation.
- If KAOS/AIB integration is desired, the current options are either KAOS/operator pushes records to these APIs or AIB adds a Kubernetes watcher/reconciler. The latter remains architecturally cleaner for source-of-truth reasons but is not implemented.

### 3. AIB end-user routes and consent/session model

Source file:

- `agentic-identity-broker/internal/adapters/http/routing/enduser.go`

End-user APIs include:

- authenticated `/api/me`.
- authenticated consent routes under `/api/consent/agents`.
- authenticated grant create/get/revoke routes for an agent.
- authenticated third-party OAuth2 session routes.
- OAuth2 authorization server endpoints: `/oauth2/authorize`, `/oauth2/token`, `/.well-known/oauth-authorization-server`, `/oauth2/jwks.json`.
- optional consent SPA under `/consent/`.

Authentication behavior:

- Authenticated routes use `RequirePrincipalMiddleware`.
- Middleware can use plain-header pre-auth or JWT pre-auth depending on configuration.

Implications:

- AIB already has user-facing consent and token-session flows.
- This is user-consented OAuth delegation, not KAOS runtime approval/pause/resume.
- AIB can return user re-authentication hints/URLs through token exchange errors, which is relevant to fail-with-URL retry flows.

### 4. AIB Agent model

Source file:

- `agentic-identity-broker/internal/domain/storage/agent.go`

AIB Agent fields include:

- internal UUID `id`.
- optional OAuth `client_id`.
- optional `external_id`.
- display name and description.
- governance, documentation, and agent interface URLs.
- service requirements.
- permission set associations.
- redirect URIs.
- allowed scopes.
- client metadata document URIs.

Client classification:

- proxy client: has `client_id`.
- CIMD client: has `client_uris` but no `client_id`.
- local client: has neither.
- ambiguous client: has both and is invalid.

Implications:

- AIB's stable internal agent identity is a UUID, not KAOS `namespace/name` by default.
- `external_id` is the likely bridge for KAOS logical identity such as `kaos://agent/{namespace}/{name}` or a UID-qualified equivalent.
- AIB agent records support service requirements and permission set associations, which overlap with but are semantically stronger than KAOS's current `spec.mcpServers` wiring.

### 5. AIB PermissionSet and service requirement model

Source files:

- `agentic-identity-broker/internal/domain/storage/permission_set.go`
- `agentic-identity-broker/internal/domain/storage/service_requirement.go`

PermissionSet behavior:

- Permission sets are admin-defined bundles of OAuth2 scopes across one or more third-party services.
- Each service scope contains service ID, scopes, and requirement type.
- Duplicate service IDs in a permission set are invalid.

ServiceRequirement behavior:

- An agent service requirement points to a third-party OAuth2 service, requirement type, and required OAuth2 scopes.
- Required scopes must be non-empty.

Implications:

- AIB currently models OAuth2 service scopes, not MCP tool-level scopes or KAOS resource permissions.
- This model could be adapted for MCP protected resources if each MCP server or tool surface is represented as a service/resource with scopes.
- There is a key target-picture decision: whether MCP permissions should be mapped into AIB PermissionSets, handled by OPA/Keycloak, enforced in KAOS runtime, or kept initially coarse-grained.

### 6. AIB grants

Source file:

- `agentic-identity-broker/internal/domain/storage/user_grant.go`

UserGrant fields include:

- grant UUID.
- principal.
- agent UUID.
- optional `valid_until`.
- granted permission set entries.
- included service IDs per permission set.

Implications:

- AIB grants are user-to-agent delegated grants.
- Grants can expire and can include only selected services from permission sets.
- This aligns well with user-driven KAOS requests and with autonomous agents only if autonomous execution is backed by explicit durable delegated grants or run-scoped grants.

### 7. AIB token exchange service

Source files:

- `agentic-identity-broker/internal/domain/tokenexchange/request.go`
- `agentic-identity-broker/internal/domain/tokenexchange/cel_evaluator.go`
- `agentic-identity-broker/internal/domain/tokenexchange/service.go`

Token exchange behavior:

- Implements RFC 8693 token exchange request validation.
- Requires `grant_type`, `subject_token`, `client_assertion`, and `resource`.
- Validates subject token JWT and client assertion JWT.
- Uses CEL expressions to extract principal and agent ID from subject token claims.
- Uses CEL expression to authorize the privileged client.
- Resolves target service by protected resource URI.
- Verifies the user grant before checking token session existence to avoid information leakage.
- Retrieves a valid third-party access token, including refresh if needed.
- Validates permission-set effective scopes against session scopes.
- Returns an RFC 8693 response with token, token type, scope, expiry, and granted permission sets.
- Re-auth errors can include an `error_uri` pointing the user to service authorization.

Implications:

- Current AIB is directly useful for exchange from a user/agent subject token into a third-party service access token.
- KAOS does not currently produce or propagate the subject token/client assertion pair needed by this flow.
- AIB expects agent ID extraction to resolve to an AIB internal UUID unless configured to resolve by client ID.
- Mapping KAOS identity into AIB token exchange requires a deliberate token-claim strategy.

### 8. AIB ExtProc server

Source file:

- `agentic-identity-broker/internal/extproc/server/server.go`

ExtProc behavior:

- Implements Envoy External Processing gRPC service.
- On request headers, extracts bearer token and constructs resource URI from `:scheme`, `:authority`, and `:path`.
- Exchanges bearer token for downstream token scoped to the resource URI.
- Replaces the Authorization header with the exchanged token.
- If no bearer token is present, it passes the request through unchanged.
- If broker returns an error URI, it sends a JSON-RPC-like URL elicitation response with HTTP 200 and code `-32042`.
- Invalid resource can return 503; exchange failures can return 500/503.
- Request and response bodies are passed through unchanged.

Implications:

- AIB ExtProc is useful for Gateway/Envoy or sidecar token exchange without modifying the upstream MCP server.
- Current ExtProc is header/resource oriented, not MCP-tool aware.
- Because it passes bodies through unchanged, it cannot currently enforce per-tool authorization based on MCP JSON body unless extended.
- The no-token pass-through behavior is useful for optional exchange but would need strict upstream auth if protection is mandatory.

## Main integration facts from source

1. KAOS has deployment-time topology (`Agent -> MCPServer`, `Agent -> peer Agent`, `Agent -> ModelAPI`) but not runtime identity propagation.
2. KAOS has Gateway API routing for Agents, MCPServers, and ModelAPIs, but the agent runtime currently calls MCPServers directly through ClusterIP endpoints.
3. KAOS A2A propagates tracing headers only, not identity or delegation metadata.
4. KAOS has an `input-required` task state but no implemented approval pause/resume route or durable task store.
5. KAOS autonomous execution exists and currently starts without user/run security context.
6. AIB has concrete OAuth2 delegation, consent, token vault, permission set, token exchange, client credential, signing key, and ExtProc capabilities.
7. AIB does not currently integrate with KAOS CRDs or Kubernetes workload identity.
8. AIB's permission model is OAuth2 service/scope oriented, not natively KAOS MCP tool/action oriented.
9. AIB ExtProc can exchange tokens at a Gateway/sidecar boundary but is not currently enough for fine-grained MCP tool authorization.
10. The immediate target-picture research should therefore focus on bridging identity/context/enforcement gaps, not on whether AIB has a useful token broker core. It does.
