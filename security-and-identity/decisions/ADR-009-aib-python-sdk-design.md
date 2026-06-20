# ADR-009: AIB Python SDK design

**Status**: Proposed.
**Date**: 2026-06-20

---

## Decision

Proposed decision: design the SDK as a **small third-party Python SDK for AIB interoperability**.

The SDK should focus first on **automatic request context propagation**, using the same ergonomics as OpenTelemetry propagation:

1. Extract inbound AIB headers at server/framework boundaries.
2. Store the current request context in a request-local `ContextVar`.
3. Inject outbound AIB headers automatically into common Python HTTP clients.
4. Expose a simple dictionary-like `aib.ctx` for local inspection or overrides.
5. Keep manual `aib.ctx.to_headers()` as an escape hatch for non-instrumented transports.

The SDK must not depend on KAOS resource types, KAOS CRDs, KAOS identity formats, Kubernetes operators, Gateway resources, or LiteLLM configuration. KAOS can use the SDK through its own wrapper/adapters, but those wrappers are downstream integrations and are not part of the core SDK contract.

---

## Context

AIB is useful to agentic runtimes when agents need request context propagation, delegated authorization, third-party OAuth session access, token exchange, and consistent consent/re-authentication handling. Those needs are not unique to KAOS.

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
- FastAPI instrumentation,
- httpx instrumentation,
- requests instrumentation,
- FastMCP instrumentation,
- optional ASGI/FastA2A helper,
- optional LangChain middleware helper.

If `instrument.py` grows near roughly 800 lines or becomes hard to maintain, split it later. Do not start with many public modules such as `aib.context`, `aib.fastapi`, `aib.httpx`, `aib.mcp`, and `aib.propagation`.

Initial public API:

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

Future AIB server interaction can add:

```python
aib.Client(...)
```

but this ADR focuses on propagation first.

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

Use namespaced default propagation headers to avoid collisions:

```text
x-aib-request-id
x-aib-session-id
x-aib-principal
x-aib-actor
x-aib-parent-actor
x-aib-delegation-chain
x-aib-scopes
authorization
```

The SDK may allow custom header names later, but defaults should be stable.

Precedence:

1. User-provided outbound headers should not be overwritten by default.
2. Values in `aib.ctx` are the propagation source.
3. If no current context exists, instrumentors do nothing.
4. Override behavior can be a configuration option later, not the default.

---

## Automatic instrumentation

### FastAPI

`instrument_fastapi(app)` should add middleware that extracts inbound AIB headers into `aib.ctx`.

```python
import aib
from fastapi import FastAPI

app = FastAPI()
aib.instrument_fastapi(app)
```

Application code does not need to thread context through dependencies just for propagation.

Optional local override:

```python
@app.middleware("http")
async def set_actor(request, call_next):
    aib.ctx["actor"] = "agent://researcher"
    return await call_next(request)
```

If useful, `instrument_fastapi(app, actor="agent://researcher")` can provide the same behavior without custom middleware.

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

        aib.instrument_fastapi(self.app)
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

KAOS-specific identity mapping remains outside the SDK:

```python
@app.middleware("http")
async def kaos_actor(request, call_next):
    aib.ctx["actor"] = f"kaos://agent/{namespace}/{name}"
    return await call_next(request)
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
aib.instrument_asgi(app)
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

## AIB server interaction boundary

This ADR focuses on request propagation. AIB server interaction should be reviewed separately after the propagation model is accepted.

The later server-interaction section should cover:

- grant/resource checks,
- user-consent required responses,
- third-party re-authentication required responses,
- RFC 8693 token exchange,
- delegated token handling,
- structured result types.

Do not overload the propagation design with access-check semantics yet.

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
- require application code to manually pass headers in normal FastAPI/httpx/requests/Pydantic AI/FastMCP paths.

---

## Annex: Alternatives considered

### Option A: Many public framework modules

This would expose separate public modules such as `aib.context`, `aib.fastapi`, `aib.httpx`, `aib.mcp`, and `aib.propagation`.

Rejected for the initial SDK. It makes the API look larger than the problem. Start with `import aib`, `aib.ctx`, and a few package-level instrumentation functions.

### Option B: Manual header passing only

This would require application code to call `to_headers()` and pass headers into every outbound client.

Rejected. It is too error-prone and unlike successful propagation systems such as OpenTelemetry. Manual `to_headers()` remains only as an escape hatch.

### Option C: Orchestrator-specific SDK

This would make the SDK directly understand one orchestrator's identities, resource graph, and runtime configuration.

Rejected. It would make the SDK less reusable and would move orchestrator-specific concepts into AIB's core developer surface.

### Option D: Full agent runtime framework

This would turn the SDK into an agent runtime with tools, memory, task orchestration, and policy execution.

Rejected. The SDK should interoperate with existing frameworks rather than replacing them.

---

## Consequences

### Positive

- AIB gets a small reusable Python developer surface independent of any orchestrator.
- Request propagation is automatic across common FastAPI, httpx, requests, Pydantic AI MCP, and FastMCP paths.
- `aib.ctx` gives a simple override/inspection point without forcing explicit dependency passing.
- KAOS PAIS can integrate with minimal changes and without littering PAIS code with manual header plumbing.
- The package can grow to AIB server interactions later without overcomplicating propagation.

### Negative

- Global instrumentation must be enabled early and tested carefully.
- Instrumenting both `httpx` and `requests` requires maintaining two client hooks.
- Frameworks or providers that use other HTTP stacks may require manual `to_headers()` or later provider-specific support.
- A dict-like `aib.ctx` is ergonomic but must still be request-local through `ContextVar`, not a process-global mutable dictionary.

### Risks

- If instrumentation silently misses a transport, developers may think propagation happened when it did not.
- If instrumentation overwrites explicit user headers, it may break callers; defaults should avoid overwriting.
- If `aib.ctx` is implemented as a real global dict rather than a ContextVar-backed facade, concurrent requests will leak context.
- If the SDK grows server-interaction and policy APIs before propagation is stable, the API may become too broad.

---

## Decision summary

1. The SDK is a small third-party Python SDK for AIB interoperability.
2. The initial public API is `aib.ctx`, `instrument_fastapi`, `instrument_httpx`, `instrument_requests`, `instrument_fastmcp`, `instrument_asgi`, and `ctx.to_headers()`.
3. `aib.ctx` is a dictionary-like request-local mapping backed by `ContextVar`.
4. Automatic propagation is the default; manual header passing is an escape hatch.
5. The initial implementation can keep context, propagation, and instrumentors in `instrument.py` and split later only if size/maintainability requires it.
6. Pydantic AI MCP propagation is expected to work through global `httpx` instrumentation because its streamable HTTP transport uses `httpx.AsyncClient`.
7. LangChain propagation should rely first on `httpx`/`requests` instrumentation for tools and provider paths that use those clients; optional LangChain middleware can adjust `aib.ctx` around agent execution.
8. AIB server interactions are intentionally deferred to the next detailed section.
