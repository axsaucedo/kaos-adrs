# ADR-AIB-001: AIB Python SDK design

**Status**: Proposed
**Date**: 2026-06-20

---

## Decision

Proposed decision: design the SDK as a **small third-party Python SDK for AIB interoperability**.

The SDK should focus first on **automatic request context propagation**, using the same ergonomics as OpenTelemetry propagation:

1. Extract trusted inbound propagation headers at server/framework boundaries.
2. Store the current request context in a request-local `ContextVar`.
3. Inject outbound AIB headers automatically into common Python HTTP clients.
4. Expose a simple dictionary-like `aib.ctx` for local inspection or overrides.
5. Enrich context from instrumentation arguments, resolver callbacks, and environment-variable defaults.
6. Keep manual `aib.ctx.to_headers()` as an escape hatch for non-instrumented transports.

The SDK must not depend on KAOS resource types, KAOS CRDs, KAOS identity formats, Kubernetes operators, Gateway resources, or LiteLLM configuration. KAOS can use the SDK through its own wrapper/adapters, but those wrappers are downstream integrations and are not part of the core SDK contract.

---

## Context

AIB is useful to agentic runtimes when agents need request context propagation, delegated authorization, third-party OAuth session access, token exchange, and consistent grant/re-authentication handling. Those needs are not unique to KAOS.

The SDK should therefore be a general-purpose Python package for agent frameworks, HTTP services, and MCP servers. It should provide primitives usable by:

- FastAPI applications,
- Pydantic AI agent servers,
- FastMCP servers,
- FastA2A/ASGI-style agent servers,
- LangChain agents and tools,
- custom Python agent runtimes,
- orchestrator-specific wrappers such as a KAOS integration layer.

Validated framework facts:

- Pydantic AI `MCPServerStreamableHTTP` creates or accepts an `httpx.AsyncClient` and passes it into MCP's streamable HTTP transport. Global `httpx` instrumentation can therefore cover Pydantic AI MCP traffic when enabled before use.
- KAOS PAIS `RemoteAgent` already uses `httpx.AsyncClient`; global `httpx` instrumentation can cover A2A and chat-completion delegation calls.
- FastMCP exposes middleware and `Context` objects, so a single `instrument_fastmcp(mcp)` helper can extract context for tool execution.
- LangChain is not installed in the current KAOS PAIS environment. Current LangChain docs show `create_agent(..., middleware=[...])`, `@tool` functions, and `ToolRuntime` for tool runtime context. For AIB propagation, HTTP client instrumentation is the reliable generic path; LangChain middleware can be optional for setting/updating `aib.ctx` around agent execution.

The SDK is not a policy engine and is not an orchestrator. It does not define resource topology or approve access by itself. It gives Python applications a safe, consistent way to carry request context and, in a later interaction section, ask AIB for decisions or delegated tokens.

---

## Package and file shape

Keep the public API and maintenance model small.

Package:

```python
import aib
```

Initial file layout:

```text
aib/
  __init__.py
  instrument.py
  py.typed
```

`instrument.py` can hold:

- the request-local context mapping,
- header extraction/injection helpers,
- environment-derived context defaults,
- FastAPI instrumentation,
- httpx instrumentation,
- requests instrumentation,
- FastMCP instrumentation,
- optional ASGI/FastA2A helper,
- optional LangChain middleware helper.

If `instrument.py` grows near roughly 800 lines or becomes hard to maintain, split it later. Do not start with many public modules such as `aib.context`, `aib.fastapi`, `aib.httpx`, `aib.mcp`, and `aib.propagation`.

Initial propagation API:

```python
import aib

aib.ctx

aib.instrument_fastapi(app)
aib.instrument_httpx()
aib.instrument_requests()
aib.instrument_fastmcp(mcp)
aib.instrument_asgi(app)

aib.ctx.to_headers()
```

AIB server interaction API:

```python
client = aib.Client(...)
```

The SDK should expose a small framework-agnostic client surface for access checks, re-authentication handling, and delegated token retrieval. Framework integrations can wrap these calls later, but the core interface should work in plain Python code.

---

## Request-local context API

Expose `aib.ctx` as a dictionary-like request-local mapping backed by `ContextVar`.

Example:

```python
import aib

aib.ctx["request_id"] = "req-123"
aib.ctx["session_id"] = "session-456"
aib.ctx["principal"] = "user://alice"
aib.ctx["actor"] = "agent://researcher"
```

In normal server operation, application code should not need to create the initial context manually. Instrumentation should initialize it per request by:

1. reading trusted inbound headers,
2. generating a request ID when the inbound request does not provide one,
3. reading local runtime defaults from environment variables,
4. applying explicit instrumentation arguments,
5. applying framework-specific resolver callbacks.

For example, an instrumented first agent server can receive a request with no propagation headers and still produce a context containing a generated `request_id` and a configured local `actor`.

If simple to implement, support normal mapping methods:

```python
aib.ctx.update({"actor": "agent://worker"})
principal = aib.ctx.get("principal")
aib.ctx.pop("subject_token", None)
```

If those methods complicate the implementation, keep only the core mapping operations and `to_headers()` initially.

Do not add redacted/safe dictionary APIs in the initial proposal. Keep the API small. The SDK should still avoid injecting raw sensitive values unless explicitly present in `aib.ctx`.

Manual header escape hatch:

```python
headers = aib.ctx.to_headers()
```

This supports non-instrumented transports, custom clients, tests, or framework gaps.

---

## Header model

Do not namespace every propagated field as `x-aib-*`. Use generic headers for concepts whose meaning is not owned by AIB, and reserve `x-aib-*` for AIB-owned context.

Default propagation headers:

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

`x-request-id` is the request/correlation ID for the call chain. If an inbound request does not provide it, the first instrumented server should generate it. AIB should not create a second AIB-specific request ID by default.

`x-principal` and `x-actor` can be generic because they describe common request context. They must still be treated as trusted only when extracted from configured trusted boundaries, verified authentication, or application resolvers. The SDK should not blindly trust arbitrary client-supplied identity headers in internet-facing deployments.

`x-aib-context-id`, `x-aib-session-id`, `x-aib-delegation-chain`, and `x-aib-scopes` are AIB-specific because their semantics are owned by AIB and may be tied to consent, token exchange, delegation, or AIB server-side state.

The SDK may allow custom header names later, but defaults should be stable and should avoid duplicating generic context as AIB-specific headers.

Precedence:

1. User-provided outbound headers should not be overwritten by default.
2. Values in `aib.ctx` are the propagation source.
3. Inbound trusted headers initialize `aib.ctx`.
4. If no request ID exists, inbound instrumentation generates one.
5. Environment defaults initialize local runtime identity when explicit values are not provided.
6. Explicit instrumentation arguments override environment defaults.
7. Resolver callbacks can derive request-specific values from verified framework state.
8. Override behavior for outbound headers can be a configuration option later, not the default.

---

## Context enrichment defaults

The SDK should support context enrichment at instrumentation time because most clients will not know the first agent server's local runtime identity. A typical incoming request may include no request ID, no actor, and no AIB-specific context. The first trusted server should fill the safe defaults.

Default environment variables:

```text
AIB_ACTOR
AIB_PRINCIPAL
AIB_SERVICE
AIB_CONTEXT_ID
AIB_SESSION_ID
```

`AIB_ACTOR` is the most important default for agent servers and MCP servers. It identifies the local runtime actor, for example `agent://researcher` or another deployment-defined opaque string. `AIB_PRINCIPAL` should be optional and is only appropriate when the process has a fixed trusted principal; user-specific principal values should normally come from verified request authentication or a resolver.

Instrumentation should also accept explicit values and resolver callbacks:

```python
import aib

aib.instrument_fastapi(
    app,
    actor="agent://researcher",
    principal_resolver=get_principal_from_verified_auth,
)
```

Equivalent environment-driven setup should work without code-level identity arguments:

```bash
export AIB_ACTOR="agent://researcher"
```

```python
import aib

aib.instrument_fastapi(app)
aib.instrument_httpx()
```

Request-time enrichment order should be:

1. extract trusted inbound propagation headers,
2. generate `request_id` if absent,
3. apply environment defaults for missing local fields,
4. apply explicit instrumentation values for missing or configured fields,
5. apply resolver callbacks for request-specific values.

This keeps simple deployments ergonomic while allowing orchestrators to inject identity through environment variables or explicit wrappers.

---

## Automatic instrumentation

### FastAPI

`instrument_fastapi(app)` should add middleware that extracts trusted inbound propagation headers into `aib.ctx`, generates a request ID when missing, and enriches local context from environment defaults, explicit arguments, and resolver callbacks.

```python
import aib
from fastapi import FastAPI

app = FastAPI()
aib.instrument_fastapi(app)
```

Application code does not need to thread context through dependencies just for propagation.

Optional local configuration:

```python
aib.instrument_fastapi(
    app,
    actor="agent://researcher",
    principal_resolver=get_principal_from_verified_auth,
)
```

Environment defaults should provide the same simple path without code-level identity arguments when deployment configuration is preferred.

### httpx

`instrument_httpx()` should patch or hook `httpx.Client` and `httpx.AsyncClient` so outbound requests read `aib.ctx` at request time and inject AIB headers.

```python
import aib
import httpx

aib.instrument_httpx()

async with httpx.AsyncClient() as client:
    await client.post("https://child-agent.example/run")
```

Because injection happens at request time, clients can be constructed once and still propagate per-request context.

### requests

`instrument_requests()` should patch `requests.Session.request` or an equivalent central requests call path.

```python
import aib
import requests

aib.instrument_requests()

requests.get("https://api.example.com/data")
```

This is separate from `httpx` instrumentation. The current KAOS PAIS environment has `requests` installed, but does not have OpenTelemetry's requests instrumentation installed; the AIB SDK can provide its own lightweight requests instrumentor.

### Manual instrumentation

For unsupported transports:

```python
headers = aib.ctx.to_headers()
await custom_client.send(headers=headers)
```

This should be an escape hatch, not the normal framework integration path.

---

## Framework examples

### KAOS PAIS

KAOS PAIS should instrument once during server setup.

```python
import aib

class AgentServer:
    def _setup_aib(self):
        if not self.settings.aib_enabled:
            return

        aib.instrument_fastapi(
            self.app,
            actor=self.settings.aib_actor,
            principal_resolver=self._resolve_aib_principal,
        )
        aib.instrument_httpx()
```

Existing `RemoteAgent` can continue to use ordinary `httpx.AsyncClient`:

```python
self._client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)
```

A2A and chat-completion delegation calls then propagate AIB headers automatically because `httpx` is globally instrumented.

Existing Pydantic AI MCP setup can remain simple:

```python
MCPServerStreamableHTTP(mcp_url)
```

This is covered because Pydantic AI's streamable MCP transport uses `httpx.AsyncClient`. If global instrumentation is disabled or a future transport bypasses `httpx`, PAIS can still pass an instrumented client explicitly, but that should be a fallback rather than the default path.

KAOS-specific identity mapping remains outside the SDK. KAOS can provide the actor explicitly as above or through environment variables injected into the workload:

```yaml
env:
  - name: AIB_ACTOR
    value: kaos://agent/default/researcher
```

The SDK only sees an opaque `actor` string.

### Pydantic AI

For plain Pydantic AI with MCP tools:

```python
import aib
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP

aib.instrument_httpx()

agent = Agent(
    "openai:gpt-4o",
    toolsets=[
        MCPServerStreamableHTTP("http://github-tools/mcp"),
    ],
)
```

No tool code is required for propagation. If a tool needs to inspect context:

```python
@agent.tool
async def current_actor() -> str:
    return aib.ctx.get("actor", "unknown")
```

### FastMCP

For FastMCP servers, expose one simple helper:

```python
import aib
from fastmcp import FastMCP

mcp = FastMCP("github-tools")
aib.instrument_fastmcp(mcp)
```

Tool code can inspect context only when needed:

```python
@mcp.tool
async def list_issues(repo: str):
    return {
        "repo": repo,
        "principal": aib.ctx.get("principal"),
        "actor": aib.ctx.get("actor"),
    }
```

The helper should be implemented through FastMCP middleware so extraction happens before tool execution.

### FastA2A / ASGI-style agent servers

If FastA2A is ASGI-compatible, the SDK should use a generic ASGI helper:

```python
import aib
from fasta2a import FastA2A

app = FastA2A()
aib.instrument_asgi(app, actor="agent://worker")
aib.instrument_httpx()
```

Handler code can read `aib.ctx` if needed:

```python
@app.task
async def handle_task(message):
    return {
        "principal": aib.ctx.get("principal"),
        "actor": aib.ctx.get("actor"),
    }
```

If a FastA2A implementation is not ASGI-compatible, the SDK should rely on manual `aib.ctx.to_headers()` or a small framework-specific helper after the framework surface is verified.

### LangChain

Current LangChain docs show:

- `create_agent(model=..., tools=..., middleware=[...])`,
- tools as Python callables or `@tool` functions,
- `ToolRuntime` for accessing LangChain runtime state/context inside tools.

For AIB propagation, the most reliable generic integration is HTTP client instrumentation, because LangChain tools commonly call external APIs through ordinary Python clients:

```python
import aib
import requests
from langchain.agents import create_agent
from langchain.tools import tool

aib.instrument_requests()
aib.instrument_httpx()

@tool
def search_api(query: str):
    response = requests.get(
        "https://api.example.com/search",
        params={"q": query},
    )
    return response.json()

agent = create_agent(
    model="openai:gpt-4o",
    tools=[search_api],
)
```

If a LangChain tool needs the current AIB context:

```python
@tool
def current_actor() -> str:
    return aib.ctx.get("actor", "unknown")
```

Optional LangChain middleware can be added later if it is useful to set or adjust `aib.ctx` around agent execution:

```python
agent = create_agent(
    model="openai:gpt-4o",
    tools=[search_api],
    middleware=[
        aib.langchain_middleware(actor="agent://researcher"),
    ],
)
```

The ADR does not assume that every LangChain provider uses `httpx` or `requests`. HTTP instrumentation covers tools and providers that use those clients. Other provider SDKs may require provider-specific support or manual propagation later.

---

## AIB server interaction API

The SDK should expose AIB server interactions as a small typed client. The client should use `aib.ctx` by default, so callers do not repeatedly pass principal, actor, request ID, or delegation context.

Initial client construction:

```python
import aib

client = aib.Client(
    base_url="https://aib.example.com",
    api_key_env="AIB_API_KEY",
)
```

Default environment variables:

```text
AIB_BASE_URL
AIB_API_KEY
```

If `base_url` is not passed, the client should read `AIB_BASE_URL`. If an API key or workload credential is not passed, the client should read the configured env var. The SDK should not prescribe the final AIB server authentication mechanism; it should support the current AIB deployment while leaving room for workload identity later.

### Machine identity and actor-token lifecycle

In the gateway-centric KAOS deployment the agent does not call AIB for access decisions — the gateway does. The SDK's primary server-side job is therefore to give the agent its **own machine identity** (the actor) and attach it to outbound calls, so the gateway can validate actor + subject.

The SDK manages the agent's AIB-issued **actor token** transparently:

```python
import aib

# Credentials come from the mounted Secret (provisioned by the sync service, mounted by the operator).
aib.instrument_agent_identity(
    issuer_env="AIB_ISSUER",                 # AIB OIDC issuer (mints agent tokens; exposes JWKS)
    client_id_env="AIB_CLIENT_ID",
    client_secret_file="/var/run/aib/client_secret",   # projected file; watched for rotation
)

token = aib.actor_token()                    # cached, always-fresh AIB actor token (sub/azp = this agent)
```

Lifecycle requirements:

- **Acquire** the actor token via the `client_credentials` grant against AIB's `/oauth2/token` (default client auth `client_secret`; `private_key_jwt` supported for stronger deployments).
- **Refresh-ahead caching**: refresh at a TTL fraction (e.g. ~75–80%) so the request path never blocks on a refresh.
- **Credential reload**: watch the mounted secret file and reload on rotation without a restart, honoring AIB's previous-secret grace window.
- **Reactive retry**: on a `401` from the gateway, refresh once and retry the call a single time.
- **Backoff** on AIB unavailability; fail closed (surface an auth error) rather than proceeding unauthenticated.

The httpx/requests/MCP instrumentation injects this actor token as `x-agent-authorization` and forwards the inbound user subject `Authorization` automatically. The instrumented call is thus the seamless "ensure-fresh + inject + retry" path — no manual check-then-refresh.

The `check_access`/`require_access`/`get_token`/`exchange_token` methods below remain available but are **optional**, for custom servers run off-gateway; the standard gateway path performs authorization and token exchange itself.

### Core request types

The client should accept simple strings and small typed request objects. Plain strings keep the first API ergonomic; request objects allow advanced callers to be explicit.

```python
decision = client.check_access(
    resource="agent://default/researcher",
    action="invoke",
)
```

Equivalent explicit form:

```python
decision = client.check_access(
    aib.AccessRequest(
        principal=aib.ctx.get("principal"),
        actor=aib.ctx.get("actor"),
        resource="agent://default/researcher",
        action="invoke",
        request_id=aib.ctx.get("request_id"),
        scopes=[],
        metadata={},
    )
)
```

The minimum request fields are:

| Field | Meaning |
|---|---|
| `principal` | User or subject on whose behalf the action is requested. Defaults from `aib.ctx`. |
| `actor` | Local agent/runtime actor performing the action. Defaults from `aib.ctx`. |
| `resource` | Target logical resource, opaque to the SDK. |
| `action` | Requested operation such as `invoke`, `call`, `read`, `use`, or `exchange_token`. |
| `scopes` | Optional third-party or resource scopes. |
| `request_id` | Request/correlation ID. Defaults from `aib.ctx`. |
| `metadata` | Optional non-sensitive structured context. |

### Access checks

Use `check_access` when the application wants to inspect the result:

```python
decision = client.check_access(
    resource="mcp://default/github",
    action="call",
)

if decision.allowed:
    ...
else:
    ...
```

Use `require_access` when the application wants exceptions for non-allowed outcomes:

```python
client.require_access(
    resource="modelapi://default/openai",
    action="use",
)
```

Expected result shape:

```python
class AccessDecision:
    allowed: bool
    reason: str | None
    grant_id: str | None
    reauth_url: str | None
    expires_at: datetime | None
    metadata: dict[str, object]
```

Expected exceptions:

```python
aib.AccessDenied
aib.ReauthenticationRequired
aib.AIBUnavailable
```

`ReauthenticationRequired` should expose the relevant URL and structured decision details so callers can return a retryable response to the user. Missing or expired user grants should be represented as an access-denied or user-grant-required outcome, because current AIB token exchange does not expose a dedicated grant-renewal URL field.

### Delegated token retrieval

For third-party APIs, callers should ask AIB for a delegated token rather than storing or refreshing third-party tokens locally:

```python
token = client.get_token(
    resource="github://repos/acme/payments",
    scopes=["issues:read"],
)

headers = {"authorization": f"Bearer {token.access_token}"}
```

Expected result shape:

```python
class TokenResult:
    access_token: str
    token_type: str
    expires_at: datetime | None
    scopes: list[str]
    metadata: dict[str, object]
```

`get_token` should return a token only when AIB has a valid grant/session and the current principal/actor context is authorized. If the user grant is missing or expired, it should return/raise an access-denied or user-grant-required outcome. If third-party re-authentication is required, it should raise `ReauthenticationRequired` with a URL.

### Token exchange

If the AIB server exposes RFC 8693 token exchange directly, the SDK should provide a small explicit method:

```python
token = client.exchange_token(
    subject_token=upstream_token,
    audience="github",
    scopes=["issues:read"],
)
```

This is lower-level than `get_token`. KAOS components should usually use `get_token` for third-party calls and reserve `exchange_token` for cases where they already hold an upstream subject token and need direct exchange semantics.

### Minimal client surface

The initial framework-agnostic API should be:

```python
client = aib.Client(...)

decision = client.check_access(...)
client.require_access(...)

token = client.get_token(...)
token = client.exchange_token(...)
```

Async equivalents should exist without changing semantics:

```python
client = aib.AsyncClient(...)

decision = await client.check_access(...)
await client.require_access(...)

token = await client.get_token(...)
token = await client.exchange_token(...)
```

The SDK should not expose a policy language, grant mutation API, resource reconciler, or approval workflow API in this interface. Those are AIB server/admin concerns or orchestrator sync concerns, not runtime SDK primitives.

---

## Framework-agnostic KAOS flows

The following flows define what KAOS needs from the SDK across Agent, MCPServer, and ModelAPI interactions. Framework-specific examples should be added later after this interface is accepted.

### Flow 1: user invokes an agent

An incoming request reaches the first agent server. The SDK instrumentation extracts trusted headers, generates `request_id` if absent, enriches `actor` from `AIB_ACTOR` or explicit configuration, and resolves `principal` from verified user authentication.

The agent server checks root access:

```python
client.require_access(
    resource="agent://default/researcher",
    action="invoke",
)
```

If allowed, the request proceeds. If re-authentication is required, the server returns a structured retryable response containing the URL from the SDK exception. If denied, the server returns an authorization failure.

### Flow 2: agent delegates to another agent

The parent agent calls a child agent through an instrumented HTTP client. Propagation adds `x-request-id`, `x-principal`, `x-actor`, and any AIB-owned context.

The child agent enriches its local `actor`, preserving the principal and request ID, then checks whether the principal/actor context can invoke the child:

```python
client.require_access(
    resource="agent://default/planner",
    action="invoke",
)
```

The SDK does not need to understand the KAOS resource graph. It sends opaque resource IDs and current propagated context to AIB.

### Flow 3: agent calls an MCP server

Before making the call, the agent runtime can check access to the MCPServer root resource:

```python
client.require_access(
    resource="mcp://default/github",
    action="call",
)
```

The outbound MCP request then propagates context automatically. The MCP server can also perform the same root check on receipt. KAOS can choose whether the caller side, callee side, or both perform the check; the SDK supports either placement.

Tool-level and argument-level authorization remain outside the initial SDK contract.

### Flow 4: MCP tool calls a third-party API

The MCP tool asks AIB for a delegated token:

```python
token = client.get_token(
    resource="github://repos/acme/payments",
    scopes=["issues:read"],
)
```

If the user grant is missing/expired, the SDK returns an access-denied or user-grant-required outcome. If the third-party session is missing or unusable, the SDK raises `ReauthenticationRequired` with a URL. The MCP server returns that structured condition to the agent/user rather than silently failing or trying to refresh credentials itself.

If allowed, the tool uses the returned token for the third-party API call and does not persist it.

### Flow 5: agent uses a ModelAPI

The agent runtime checks root access to the ModelAPI resource:

```python
client.require_access(
    resource="modelapi://default/openai",
    action="use",
)
```

If allowed, the ModelAPI's internal controls still apply. Model allowlists, budgets, provider credentials, and rate limits remain LiteLLM or ModelAPI responsibilities rather than AIB SDK responsibilities.

### Flow 6: re-authentication retry

When `require_access` or `get_token` raises `ReauthenticationRequired`, the runtime returns the URL to the user through its normal response channel. After the user completes re-authentication, the same request can be retried with the same logical context and should succeed if AIB now has the required session.

The SDK should make these outcomes explicit and typed. It should not return success-shaped empty tokens or boolean-only denials for flows that require user action.

---

## Non-goals

The SDK should not:

- define orchestrator resource identity formats,
- parse Kubernetes CRDs,
- reconcile resources into AIB,
- generate Gateway or NetworkPolicy resources,
- own policy definitions,
- replace IdP/OIDC authentication,
- replace LiteLLM model-level authorization,
- persist raw third-party tokens,
- implement durable human approval workflows,
- mutate AIB grants or resource definitions from runtime request handlers,
- require application code to manually pass headers in normal FastAPI/httpx/requests/Pydantic AI/FastMCP paths.

---

## Consequences

### Positive

- AIB gets a small reusable Python developer surface independent of any orchestrator.
- Request propagation is automatic across common FastAPI, httpx, requests, Pydantic AI MCP, and FastMCP paths.
- `aib.ctx` gives a simple override/inspection point without forcing explicit dependency passing.
- First trusted servers can generate missing request IDs and enrich context from environment defaults or resolver callbacks.
- A small `Client`/`AsyncClient` surface covers root access checks, re-authentication outcomes, delegated token retrieval, and token exchange without making the SDK a policy engine.
- KAOS PAIS can integrate with minimal changes and without littering PAIS code with manual header plumbing.
- KAOS Agent, MCPServer, and ModelAPI flows can share one runtime SDK contract while keeping KAOS-specific resource IDs opaque.

### Negative

- Global instrumentation must be enabled early and tested carefully.
- Instrumenting both `httpx` and `requests` requires maintaining two client hooks.
- Frameworks or providers that use other HTTP stacks may require manual `to_headers()` or later provider-specific support.
- A dict-like `aib.ctx` is ergonomic but must still be request-local through `ContextVar`, not a process-global mutable dictionary.
- Runtime code must handle typed re-authentication outcomes instead of treating authorization as a boolean-only check.

### Risks

- If instrumentation silently misses a transport, developers may think propagation happened when it did not.
- If instrumentation overwrites explicit user headers, it may break callers; defaults should avoid overwriting.
- If identity headers are trusted from untrusted clients, callers can spoof principals or actors; inbound extraction must distinguish trusted boundaries from untrusted client input.
- If `aib.ctx` is implemented as a real global dict rather than a ContextVar-backed facade, concurrent requests will leak context.
- If `Client` grows grant mutation, reconciliation, policy authoring, or approval workflow APIs, the SDK may become too broad.

---

## Decision summary

1. The SDK is a small third-party Python SDK for AIB interoperability.
2. The initial propagation API is `aib.ctx`, `instrument_fastapi`, `instrument_httpx`, `instrument_requests`, `instrument_fastmcp`, `instrument_asgi`, and `ctx.to_headers()`.
3. `aib.ctx` is a dictionary-like request-local mapping backed by `ContextVar`.
4. Automatic propagation is the default; manual header passing is an escape hatch.
5. Generic context should use generic headers by default: `x-request-id`, `x-principal`, and `x-actor`; AIB-specific headers are reserved for AIB-owned context such as session, delegation chain, scopes, and context IDs.
6. Instrumented servers should generate a request ID when missing and enrich local context from environment defaults, explicit arguments, and resolver callbacks.
7. The framework-agnostic server API should expose `Client`/`AsyncClient` with `check_access`, `require_access`, `get_token`, and `exchange_token`.
8. SDK server interactions should use current `aib.ctx` by default and return typed decisions, tokens, and user-action exceptions.
9. The initial implementation can keep context, propagation, and instrumentors in `instrument.py` and split later only if size/maintainability requires it.
10. Pydantic AI MCP propagation is expected to work through global `httpx` instrumentation because its streamable HTTP transport uses `httpx.AsyncClient`.
11. LangChain propagation should rely first on `httpx`/`requests` instrumentation for tools and provider paths that use those clients; optional LangChain middleware can adjust `aib.ctx` around agent execution.
