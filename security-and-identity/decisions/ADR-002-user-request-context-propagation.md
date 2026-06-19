# ADR-002: User and request context propagation

## Status

Proposed. Requires host decisions before acceptance.

## Context

ADR-001 defines KAOS resource identity through `spec.security.id`, resolving to either:

- `kaos://{kind}/{namespace}/{name}` when `spec.security.id` is omitted, or
- `kaos://{kind}/{id}` when `spec.security.id` is provided.

The next decision is how a user-authenticated request becomes a security context that can be carried through:

- Agent runtime execution,
- MCP tool calls,
- A2A sub-agent delegation,
- async tasks,
- autonomous execution,
- AIB token exchange,
- future approval/consent flows.

## Source facts

### KAOS runtime request handling

Source files:

- `pydantic-ai-server/pais/server.py`
- `pydantic-ai-server/pais/serverutils.py`
- `pydantic-ai-server/pais/memory.py`

Current behavior:

- `/v1/chat/completions` accepts OpenAI-compatible chat requests.
- Session ID is read from `X-Session-ID` or request body `session_id`; otherwise a new memory session is created.
- Memory sessions currently use static actor values such as `app_name="agent"` and `user_id="user"`.
- OpenTelemetry context is extracted from request headers.
- No user principal, authorization token, identity claims, approval context, or run security context is extracted.
- `AgentDeps` currently contains only `session_id` and `memory`.

Implication:

- KAOS currently has correlation/session context, not security context.
- User/request context propagation requires new runtime data structures and request extraction.

### MCP client behavior

Source files:

- `pydantic-ai-server/pais/server.py`
- Pydantic AI `MCPServerStreamableHTTP` runtime signature.

Current KAOS behavior:

- `_parse_mcp_servers()` reads `MCP_SERVERS` and `MCP_SERVER_{name}_URL`.
- Each MCP server is instantiated as `MCPServerStreamableHTTP(mcp_url)`.
- No headers are currently passed.

Pydantic AI capability:

- `MCPServerStreamableHTTP` supports a `headers: dict[str, str] | None` constructor argument.
- It also supports `http_client` and `process_tool_call` hooks.

Implication:

- Static MCP headers are straightforward.
- Dynamic per-request headers are not wired in KAOS today.
- Dynamic user tokens probably require one of:
  - constructing MCP clients per request,
  - a custom `httpx.AsyncClient`/auth layer,
  - a Pydantic AI hook pattern if sufficient,
  - sidecar/Gateway token exchange instead of native runtime propagation.

### A2A delegation behavior

Source files:

- `pydantic-ai-server/pais/serverutils.py`
- `pydantic-ai-server/pais/tools.py`
- `pydantic-ai-server/pais/a2a.py`

Current behavior:

- `RemoteAgent` sends A2A JSON-RPC `SendMessage` to the peer root path `/`.
- Chat fallback posts to `/v1/chat/completions`.
- Only OpenTelemetry headers are injected.
- Delegation metadata only includes `{"delegation": true}`.
- Delegation forwards conversation context from memory, but not identity/security context.
- A2A `TaskState` includes `input-required`, but there is no complete approval/resume flow.

Implication:

- A2A context propagation needs explicit design.
- Sub-agents currently cannot distinguish original user identity, parent agent identity, or approved delegation scope.

### Autonomous execution behavior

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/controllers/agent_controller.go`
- `pydantic-ai-server/pais/server.py`
- `pydantic-ai-server/pais/a2a.py`

Current behavior:

- `spec.config.autonomous.goal` activates startup autonomous execution.
- Runtime starts an autonomous task during lifespan startup.
- Startup autonomous tasks have metadata `{"trigger":"startup"}`.
- There is no user/request context for startup autonomous execution.

Implication:

- Autonomous execution cannot rely on live user request tokens.
- Initial treatment should be agent-level identity plus correlation only, consistent with ADR-001.
- User-delegated grants for autonomous execution must be handled later in approval/consent decisions.

### AIB token exchange expectations

Source files:

- `agentic-identity-broker/internal/domain/tokenexchange/request.go`
- `agentic-identity-broker/internal/domain/tokenexchange/cel_evaluator.go`
- `agentic-identity-broker/internal/domain/tokenexchange/service.go`
- `agentic-identity-broker/internal/extproc/server/server.go`

Current behavior:

- AIB token exchange expects `subject_token`, `client_assertion`, and `resource`.
- CEL extracts principal and agent ID from subject token claims.
- AIB verifies user grant before checking token session existence.
- ExtProc can exchange an inbound Bearer token for a downstream resource token and replace the `Authorization` header.
- ExtProc passes through if no Bearer token is present.

Implication:

- KAOS must define what token/claims AIB sees.
- AIB can support a Gateway/sidecar-based exchange path, but KAOS does not yet produce or propagate the necessary user/agent context.

## Decision problem

KAOS needs a request security context model that is simple enough for initial implementation but extensible enough for:

- user-driven requests,
- MCP access,
- A2A delegation,
- future approval URLs,
- future autonomous grants,
- AIB token exchange.

## Proposed target concepts

### RequestSecurityContext

Introduce a runtime concept, not necessarily the final class name:

```text
RequestSecurityContext
  request_id
  session_id
  user_principal
  inbound_subject_token
  kaos_agent_identity
  parent_agent_identity
  delegation_chain
  approval_context
  auth_source
```

Initial implementation can start smaller:

```text
RequestSecurityContext
  request_id
  session_id
  user_principal
  inbound_subject_token
  kaos_agent_identity
```

This context should be attached to `AgentDeps` or an equivalent per-run dependency object.

### Request classes

The architecture should distinguish:

| Request class | Context source | Initial treatment |
|---|---|---|
| User chat request | Gateway/UI/API inbound request | Extract user principal and token if present |
| A2A delegated request | Parent Agent call | Propagate original user context plus delegation metadata |
| Async A2A task | A2A `SendMessage` autonomous mode | Same as A2A request, but persisted/correlated by task ID |
| Startup autonomous run | Agent CRD config | Agent identity only, no live user context |
| MCP tool call | Agent runtime to MCP | Use request context if available; otherwise agent-only |

## Options to decide

### Option A: Runtime-native propagation

KAOS runtime extracts inbound user/security context and passes it to MCP/A2A calls from the agent process.

Pros:

- Best semantic visibility.
- Runtime knows session, task, delegation, and tool context.
- Easier to include user principal and run metadata in audit/memory.
- Does not require all traffic to go through Gateway.

Cons:

- Requires runtime changes.
- MCP dynamic token propagation may be non-trivial with current client lifetime.
- Every relevant runtime/client path must be maintained.

Best fit:

- KAOS-specific user context and A2A delegation metadata.

### Option B: Gateway/ExtProc propagation

Inbound request carries a token to Gateway/Envoy/AIB ExtProc. Gateway/ExtProc exchanges or validates tokens and forwards to upstream services.

Pros:

- Centralized enforcement.
- Less application code for coarse-grained auth/token exchange.
- AIB ExtProc already exists for bearer-token exchange.

Cons:

- KAOS internal Agent-to-MCP calls currently use direct ClusterIP URLs, not Gateway.
- Gateway has less semantic context about tool calls and agent state.
- Does not automatically solve A2A delegation metadata or autonomous runs.

Best fit:

- Coarse-grained ingress/resource protection and token exchange.

### Option C: Sidecar/local proxy propagation

Agent talks to a local sidecar or MCPServer has a sidecar. The sidecar exchanges/validates tokens before forwarding.

Pros:

- Avoids changing every MCP server.
- Can protect internal traffic without forcing all calls through central Gateway.
- Could be MCP-aware later.

Cons:

- More deployment complexity.
- Sidecar injection/configuration required.
- Still needs runtime to send enough context to the sidecar unless the sidecar only uses static agent identity.

Best fit:

- Later enforcement topology if fine-grained MCP protection is needed without app changes.

### Option D: Minimal first step with context capture only

Initial KAOS captures user principal/token in runtime and stores it in per-run context, but does not yet enforce or propagate everywhere.

Pros:

- Smallest useful first step.
- Builds foundation for later MCP/A2A/AIB integration.
- Avoids premature Gateway-vs-sidecar decision.

Cons:

- Not sufficient security by itself.
- Could create false confidence if documented poorly.

Best fit:

- Research-to-implementation transition where exact enforcement topology is still open.

## Provisional recommendation

Use a layered decision:

1. **Define runtime `RequestSecurityContext` now.**
2. **Extract inbound principal/token at the Agent runtime boundary.**
3. **Propagate context to A2A delegation in metadata/headers.**
4. **Do not require dynamic MCP token propagation in the first identity/context decision.**
5. **Keep MCP propagation method open until enforcement topology decision.**
6. **Treat autonomous startup runs as agent-identity-only plus correlation for now.**

This avoids blocking on Gateway-vs-sidecar-vs-native enforcement while still establishing the context model every later decision needs.

## Host questions required to finalize ADR-002

### Q1. Where should inbound user authentication be assumed to happen initially?

Options:

| Option | Meaning | Tradeoff |
|---|---|---|
| External Gateway/UI only | Runtime trusts forwarded headers/token | Simple, but requires trusted boundary |
| Runtime validates JWT | Agent runtime validates issuer/audience | Stronger, but every runtime needs auth config |
| AIB validates before runtime | AIB/Gateway handles authn | Centralized, but needs routing/enforcement design |

Provisional recommendation:

- Assume trusted Gateway/UI forwarding for initial context capture, with later JWT validation at Gateway/AIB/runtime depending on enforcement decision.

### Q2. What should be the minimum context captured initially?

Candidate minimum:

```text
request_id
session_id
user_principal
inbound_subject_token
kaos_agent_identity
```

Host decision:

- Is storing/holding the inbound subject token in runtime acceptable initially, or should runtime only hold a reference/opaque context ID?

### Q3. Should A2A delegation propagate user context immediately?

Options:

| Option | Meaning | Tradeoff |
|---|---|---|
| No | Delegation remains agent-to-agent only | Simple, but sub-agent cannot enforce user grants |
| Metadata only | Propagate principal/session/delegation chain, no token | Safer, but sub-agent cannot exchange user token directly |
| Metadata + token | Propagate token to sub-agent | Most functional, highest token exposure |

Provisional recommendation:

- Propagate metadata immediately; defer token propagation until AIB/token-exchange and enforcement decisions.

### Q4. Should MCP calls receive user tokens natively from runtime?

Options:

| Option | Meaning | Tradeoff |
|---|---|---|
| Not initially | Keep MCP calls unchanged | Simple, but no MCP user auth yet |
| Static headers | Use `MCPServerStreamableHTTP(headers=...)` | Easy, but not per-user/request |
| Dynamic runtime headers | Inject token per request/tool call | Best native model, more runtime work |
| Gateway/sidecar exchange | Runtime sends to proxy, proxy handles token | Less app auth code, topology decision needed |

Provisional recommendation:

- Do not finalize MCP token propagation in ADR-002. Decide in enforcement topology. ADR-002 should only require the runtime to have the context available.

### Q5. How should startup autonomous runs be represented?

Options:

| Option | Meaning | Tradeoff |
|---|---|---|
| Agent identity only | No user context | Simple, matches current state |
| Pre-bound grant reference | Autonomous config references approved grant | Better control, needs approval/grant model |
| Run-scoped token/context | Runtime obtains run token | Stronger, future work |

Provisional recommendation:

- Agent identity only plus task/run correlation for now.

### Q6. Should RequestSecurityContext be persisted?

Options:

| Option | Meaning | Tradeoff |
|---|---|---|
| In-memory only | Per request/task only | Simple, weak for async/retry |
| Memory metadata | Store non-secret context in KAOS memory events | Useful audit, avoid token storage |
| Durable store | Store full run context | Needed for pause/resume, more design |

Provisional recommendation:

- Persist non-secret metadata only; never store raw bearer tokens in memory events.

## Proposed ADR-002 decision if host agrees

1. KAOS introduces a runtime request security context concept.
2. Agent runtime extracts principal/token/context from trusted inbound request sources.
3. `AgentDeps` or equivalent per-run deps carry non-secret security context.
4. A2A delegation propagates non-secret metadata and delegation chain.
5. Raw token propagation to sub-agents is deferred.
6. MCP token propagation is deferred to enforcement topology, but runtime must make context available.
7. Startup autonomous runs use Agent identity plus correlation only for now.
8. Persist non-secret context metadata; do not persist raw tokens.

## Decision status

Awaiting host answers.
