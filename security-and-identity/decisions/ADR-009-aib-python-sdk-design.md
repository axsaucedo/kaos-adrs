# ADR-009: AIB Python SDK design

**Status**: Proposed.
**Date**: 2026-06-20

---

## Decision

Proposed decision: design the SDK as a **third-party Python SDK for AIB interoperability**, owned as part of the AIB ecosystem and independent of any specific orchestrator.

The SDK should make two domains easy for Python agentic applications:

1. **Request propagation**: capture, normalize, redact, serialize, and propagate request security context across HTTP, agent, tool, MCP, and delegation boundaries.
2. **AIB server interaction**: call AIB for resource-grant checks, user-consent state, RFC 8693 token exchange, re-authentication flows, and structured authorization outcomes.

The SDK must not depend on KAOS resource types, KAOS CRDs, KAOS identity formats, Kubernetes operators, Gateway resources, or LiteLLM configuration. KAOS can use the SDK through its own wrapper/adapters, but those wrappers are downstream integrations and are not part of the core SDK contract.

---

## Context

AIB is useful to agentic runtimes when agents need delegated authorization, third-party OAuth session access, token exchange, and consistent consent/re-authentication handling. Those needs are not unique to KAOS.

The SDK should therefore be written as a general-purpose Python package for agent frameworks and MCP servers. It should provide a small set of primitives that can be used by:

- FastAPI applications,
- Pydantic AI agent servers,
- FastMCP servers,
- custom Python agent runtimes,
- orchestrator-specific wrappers such as a KAOS integration layer.

The SDK is not a policy engine and is not an orchestrator. It does not define resource topology or approve access by itself. It gives Python applications a safe, consistent way to carry request context and ask AIB for decisions or delegated tokens.

---

## Package shape

Proposed package name:

```text
aib-sdk
```

Import namespace:

```python
import aib
```

Core modules:

| Module | Responsibility |
|---|---|
| `aib.context` | Request security context model, redaction, serialization, propagation headers. |
| `aib.fastapi` | FastAPI middleware/dependencies for inbound context extraction and outbound propagation. |
| `aib.client` | Async AIB API client for grant checks, consent URLs, token exchange, and re-auth flows. |
| `aib.mcp` | Helpers for MCP server/tool contexts and delegated-token retrieval. |
| `aib.pydantic_ai` | Optional helpers for attaching context to Pydantic AI dependencies and tool execution. |
| `aib.errors` | Structured result and denial types. |

Optional framework helpers must depend only on their framework package, not on KAOS. If framework dependencies are heavy, they can be extras:

```text
aib-sdk[fastapi]
aib-sdk[pydantic-ai]
aib-sdk[fastmcp]
```

---

## Domain 1: Request propagation

### Request context model

The SDK should expose a framework-neutral context object:

```python
from dataclasses import dataclass, field
from typing import Mapping

@dataclass(frozen=True)
class RequestContext:
    request_id: str
    session_id: str | None = None
    principal: str | None = None
    subject_token: str | None = None
    scopes: tuple[str, ...] = ()
    actor: str | None = None
    parent_actor: str | None = None
    delegation_chain: tuple[str, ...] = ()
    auth_source: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)
```

The model intentionally uses generic terms:

- `principal`: the human or service principal.
- `actor`: the current agent/service/tool actor.
- `parent_actor`: the delegating caller, if any.
- `delegation_chain`: ordered non-secret actor chain.
- `subject_token`: inbound token used for AIB token exchange when available.

No field uses KAOS-specific identity names. A KAOS wrapper may set `actor` to a KAOS logical identity, but the SDK treats it as an opaque string.

### Header propagation

The SDK should define canonical propagation headers:

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

Raw bearer tokens must never be included in safe logging or persistence helpers. The SDK should provide:

```python
safe = context.redacted()
headers = context.to_headers(include_subject_token=False)
headers_with_token = context.to_headers(include_subject_token=True)
```

The default should be safe:

- `include_subject_token=False`,
- redacted context for logs,
- explicit opt-in for forwarding tokens.

### FastAPI propagation example

```python
from fastapi import Depends, FastAPI
from aib.fastapi import AIBContextMiddleware, request_context

app = FastAPI()
app.add_middleware(
    AIBContextMiddleware,
    trusted_identity_headers=True,
)

@app.get("/work")
async def work(ctx = Depends(request_context)):
    return {
        "request_id": ctx.request_id,
        "principal": ctx.principal,
        "actor": ctx.actor,
    }
```

Outbound propagation:

```python
import httpx

async def call_child_service(ctx):
    async with httpx.AsyncClient() as client:
        return await client.post(
            "https://child-agent.example/run",
            headers=ctx.to_headers(include_subject_token=False),
            json={"task": "summarize"},
        )
```

### Pydantic AI server example

The SDK should make context available through dependencies without requiring the agent framework to know AIB internals:

```python
from dataclasses import dataclass
from pydantic_ai import Agent, RunContext
from aib.fastapi import request_context
from aib.context import RequestContext

@dataclass
class Deps:
    request_context: RequestContext

agent = Agent("openai:gpt-4o", deps_type=Deps)

@agent.tool
async def current_user(ctx: RunContext[Deps]) -> str:
    return ctx.deps.request_context.principal or "anonymous"

async def chat_endpoint(message: str, ctx = Depends(request_context)):
    result = await agent.run(message, deps=Deps(request_context=ctx))
    return result.output
```

### KAOS wrapper example for Pydantic AI server

KAOS can provide its own wrapper that maps KAOS runtime configuration into generic SDK fields. That wrapper is outside the core SDK:

```python
from aib.context import RequestContext

def kaos_actor_identity(kind: str, namespace: str, name: str) -> str:
    return f"kaos://{kind}/{namespace}/{name}"

def build_kaos_context(inbound, runtime_config) -> RequestContext:
    return RequestContext(
        request_id=inbound.request_id,
        session_id=inbound.session_id,
        principal=inbound.principal,
        subject_token=inbound.subject_token,
        scopes=tuple(inbound.scopes),
        actor=kaos_actor_identity(
            runtime_config.kind,
            runtime_config.namespace,
            runtime_config.name,
        ),
        auth_source=inbound.auth_source,
    )
```

The important boundary is that `kaos_actor_identity()` belongs to the KAOS wrapper. The AIB SDK only sees an opaque `actor` string.

### FastMCP vanilla example

For a plain FastMCP server, the SDK should expose helpers to read context and retrieve delegated tokens:

```python
from fastmcp import FastMCP
from aib.mcp import mcp_context

mcp = FastMCP("github-tools")

@mcp.tool
async def list_issues(repo: str, ctx = mcp_context()):
    # ctx is a generic AIB RequestContext
    return {
        "repo": repo,
        "principal": ctx.principal,
        "actor": ctx.actor,
    }
```

If FastMCP does not support dependency injection in a given version, the SDK can provide a small adapter around request/session metadata instead of requiring framework changes.

---

## Domain 2: AIB server interaction

### Client shape

The SDK should provide an async client:

```python
from aib.client import AIBClient

aib_client = AIBClient(
    base_url="https://aib.example.com",
    client_id="agent-runtime",
    client_secret="...",
)
```

The client should expose high-level methods rather than forcing application code to assemble raw AIB API calls:

```python
await aib_client.check_resource_access(
    actor=ctx.actor,
    resource="mcp://github-tools",
    action="call",
    context=ctx,
)

await aib_client.exchange_token(
    actor=ctx.actor,
    principal=ctx.principal,
    permission_set="github-issues",
    subject_token=ctx.subject_token,
    context=ctx,
)
```

### Result model

Expected authorization outcomes should be structured results, not broad exceptions:

```python
match result.kind:
    case "allowed":
        ...
    case "platform_approval_required":
        ...
    case "user_consent_required":
        return {"consent_url": result.consent_url}
    case "third_party_reauth_required":
        return {"reauth_url": result.reauth_url}
    case "denied":
        ...
```

Network failures, invalid SDK configuration, and malformed AIB responses can still raise typed exceptions.

### Resource access check example

```python
from aib.errors import AIBDenied

async def require_mcp_access(ctx, aib_client):
    result = await aib_client.check_resource_access(
        actor=ctx.actor,
        resource="mcp://github-tools",
        action="call",
        context=ctx,
    )

    if result.allowed:
        return

    raise AIBDenied(result)
```

### User delegated token exchange example

```python
async def github_token_for_user(ctx, aib_client) -> str:
    result = await aib_client.exchange_token(
        actor=ctx.actor,
        principal=ctx.principal,
        permission_set="github-issues",
        subject_token=ctx.subject_token,
        context=ctx,
    )

    if result.kind == "allowed":
        return result.access_token

    if result.kind == "user_consent_required":
        raise PermissionError(f"Consent required: {result.consent_url}")

    if result.kind == "third_party_reauth_required":
        raise PermissionError(f"Re-auth required: {result.reauth_url}")

    raise PermissionError(result.message)
```

### FastMCP delegated third-party API example

```python
from fastmcp import FastMCP
from aib.client import AIBClient
from aib.mcp import mcp_context

mcp = FastMCP("github-tools")
aib_client = AIBClient.from_env()

@mcp.tool
async def create_issue(repo: str, title: str, body: str, ctx = mcp_context()):
    token_result = await aib_client.exchange_token(
        actor=ctx.actor,
        principal=ctx.principal,
        permission_set="github-issues-write",
        subject_token=ctx.subject_token,
        context=ctx,
    )

    if not token_result.allowed:
        return token_result.to_problem_detail()

    # Tool code receives the token only in memory for the outbound API call.
    return await create_github_issue(
        repo=repo,
        title=title,
        body=body,
        access_token=token_result.access_token,
    )
```

### Pydantic AI tool example

```python
from pydantic_ai import RunContext

@agent.tool
async def file_issue(ctx: RunContext[Deps], repo: str, title: str) -> str:
    token = await github_token_for_user(
        ctx.deps.request_context,
        ctx.deps.aib_client,
    )
    await create_github_issue(repo, title, access_token=token)
    return "issue created"
```

### KAOS wrapper example for protected MCP calls

KAOS can use the generic SDK inside a wrapper around its generated MCP clients:

```python
class ProtectedMCPClient:
    def __init__(self, raw_client, aib_client, resource: str):
        self.raw_client = raw_client
        self.aib_client = aib_client
        self.resource = resource

    async def call_tool(self, name: str, args: dict, ctx):
        access = await self.aib_client.check_resource_access(
            actor=ctx.actor,
            resource=self.resource,
            action="call",
            context=ctx,
        )
        if not access.allowed:
            return access.to_problem_detail()

        return await self.raw_client.call_tool(
            name,
            args,
            headers=ctx.to_headers(include_subject_token=True),
        )
```

Again, the wrapper may use KAOS resource identities, but the SDK remains framework-neutral.

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
- implement durable human approval workflows.

---

## Annex: Alternatives considered

### Option A: Orchestrator-specific SDK

This would make the SDK directly understand one orchestrator's identities, resource graph, and runtime configuration.

Rejected. It would make the SDK less reusable and would move orchestrator-specific concepts into AIB's core developer surface.

### Option B: Raw AIB API client only

This would provide thin HTTP methods for AIB endpoints but leave context propagation, redaction, result normalization, and framework integration to every application.

Rejected. It would be too easy for each framework integration to propagate different headers, leak tokens, or handle consent/re-authentication inconsistently.

### Option C: Full agent runtime framework

This would turn the SDK into an agent runtime with tools, memory, task orchestration, and policy execution.

Rejected. The SDK should interoperate with existing frameworks such as FastAPI, Pydantic AI, and FastMCP rather than replacing them.

---

## Consequences

### Positive

- AIB gets a reusable Python developer surface independent of any orchestrator.
- Request propagation is consistent across FastAPI, Pydantic AI, FastMCP, and custom runtimes.
- AIB server interactions are normalized into safe, actionable results.
- Orchestrators can add thin wrappers without polluting the core SDK.
- Token redaction and safe persistence become default SDK behavior.

### Negative

- Orchestrator-specific integrations still need wrapper code.
- The SDK must maintain optional framework adapters and avoid hard dependencies where possible.
- The SDK needs stable AIB server API contracts for grant checks, token exchange, consent URLs, and re-authentication results.

### Risks

- If the SDK becomes too framework-specific, it will fail as a third-party interoperability layer.
- If it is only a thin HTTP client, framework integrations will duplicate propagation and error handling.
- If token forwarding is too convenient, applications may leak bearer tokens into logs, memory, or metadata.
- If result types are not precise, clients cannot distinguish admin approval, user consent, re-authentication, denial, and misconfiguration.

---

## Decision summary

1. The SDK is a third-party Python SDK for AIB interoperability.
2. The core SDK has no orchestrator-specific dependencies or resource identity assumptions.
3. The SDK covers request propagation and AIB server interaction as first-class domains.
4. FastAPI, Pydantic AI, and FastMCP helpers are framework adapters around the same generic context/client model.
5. Orchestrator integrations, including KAOS, should be wrappers that map local identities and runtime configuration into generic SDK fields.
6. The SDK uses structured results for expected authorization outcomes and typed exceptions for operational failures.
7. The SDK defaults to safe redaction and does not persist raw tokens.
