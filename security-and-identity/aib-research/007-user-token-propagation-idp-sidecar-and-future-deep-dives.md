# 007 - User token propagation, IdP integration, sidecar enforcement, and future deep dives

## Prompt

1. ok. 2. ok. 3. What does that mean that it doesn't support KAOS user token propagation to MCP? How is that an AIB feature? How is that not a KAOS-specific feature to receive the token from the user and then pass it through? Also, for support on KAOS, I would like to understand: what do I need to implement? Is that something that I would have to integrate with an OAuth provider in the cluster, like Keycloak? or Dex? 4. Ok, but this is still so possible with a side cursor, right? That way it doesn't need to modify the server. 5. Okay, let's dive deeper into this one when we move to the design, as I want to understand the key trade-off with pros, cons, and architectural considerations. 6. Ok, I'd say let's leave this one out for now. 8. Okay, for this we will need also a deeper dive with architectural considerations, etc. 9. ok.

## Response

## 3. User token propagation is primarily a KAOS feature, not an AIB feature

Correct: **KAOS user-token propagation to MCP is not something AIB itself should magically implement.** It is a KAOS runtime/gateway concern.

What I meant by "AIB doesn't support KAOS user token propagation to MCP" was: current AIB has no KAOS integration that causes KAOS requests to carry user identity through the agent runtime and into MCP calls. AIB can validate/exchange tokens once they are presented, but KAOS must decide how the user/request identity enters and flows through the system.

The responsibilities split cleanly:

| Responsibility | Owner |
|---|---|
| Authenticate external user | IdP / Gateway / auth proxy |
| Receive user identity at KAOS agent endpoint | KAOS Gateway / Agent runtime |
| Preserve identity during agent execution | KAOS runtime/session context |
| Forward identity/context on MCP calls | KAOS runtime, MCP client wrapper, gateway, or sidecar |
| Validate/exchange token and enforce consent/policy | AIB |
| Store third-party user tokens | AIB |

So yes: this is mostly **KAOS-specific plumbing**, not an AIB core feature.

### What would KAOS need to implement?

Minimum useful path:

1. **Ingress authentication**
   - Put user-facing KAOS agent endpoints behind an OAuth/OIDC-aware gateway or auth proxy.
   - The gateway authenticates users and forwards a verified identity/token.

2. **Agent runtime user context**
   - Agent request handler extracts the user principal or bearer token.
   - Stores it in the run/session context, not in global process state.

3. **MCP call propagation**
   - When the agent calls MCP, the MCP request includes user/request context plus agent/workload identity.
   - This can be done in the Pydantic AI MCP client wrapper, a proxy/sidecar, or through Gateway routing.

4. **AIB exchange/enforcement**
   - MCP server, sidecar, or gateway presents the subject token/context to AIB.
   - AIB checks consent and returns the correct downstream token or a consent-required error.

5. **Consent-required behavior**
   - KAOS must surface consent/reauth URLs back to the user or mark the task blocked.

### Does KAOS need Keycloak/Dex?

For user-driven flows: **yes, KAOS needs some trusted user identity source.** It does not have to be Keycloak or Dex specifically.

Options:

| Option | Notes |
|---|---|
| Existing enterprise IdP | Best for real deployments; AIB validates issuer/JWKS or relies on gateway-verified identity. |
| Keycloak | Good local/enterprise OIDC provider; useful for demos and full in-cluster auth. |
| Dex | Good lightweight OIDC broker for Kubernetes-native setups. |
| oauth2-proxy / auth gateway | Can authenticate with upstream IdP and pass identity headers/JWTs to KAOS. |
| AIB local OAuth2 mode | Could issue internal KAOS tokens, but it does not replace the need to authenticate humans unless AIB also owns that user login flow. |

Practical recommendation:

- For production: integrate with existing OIDC provider.
- For local/e2e: use Dex or Keycloak.
- Use AIB as the **delegation/token-exchange/consent authority**, not necessarily as the primary human IdP.

## 4. Sidecar can enforce fine-grained authorization without modifying MCP server code

Yes. A sidecar/local proxy can sit in front of the MCP server and enforce authorization without changing the MCP app.

```text
Agent -> MCP auth sidecar -> MCP server
             |
            AIB
```

The sidecar can:

- Validate JWTs.
- Call AIB for token exchange.
- Parse MCP JSON-RPC/streamable HTTP payloads.
- Extract tool name and arguments.
- Enforce policy before forwarding.
- Replace or inject downstream authorization headers.

This avoids modifying each MCP server, but the sidecar itself must be MCP-aware if it wants tool-level decisions. If it only looks at headers/routes, it can enforce resource-level policy but not tool-level policy.

So the real options are:

| Enforcement point | App changes? | Can enforce tool-level auth? | Complexity |
|---|---:|---:|---:|
| MCP server native | Yes | Yes | Medium per runtime |
| Sidecar MCP-aware proxy | No MCP app changes | Yes | Medium/high shared infra |
| Central Gateway/ExtProc | No app changes | Yes only if MCP-aware/body parsing | Medium/high central infra |
| Header-only Gateway/sidecar | No app changes | No, mostly route/resource-level | Lower |

Sidecar is a strong option if KAOS wants no MCP app changes but still wants per-tool policy.

## 5. Gateway vs sidecar design deep dive

Parked for design phase. This needs a dedicated comparison covering traffic topology, failure modes, caching, policy location, operational overhead, HTTPRoute/Gateway API implications, sidecar injection, observability, and security boundaries.

## 6. Signed payload identity

Deferred/out of scope for now. JWT bearer auth is likely sufficient for initial KAOS+AIB integration.

## 8. Consent/reauth design deep dive

Also parked for design phase. This needs a dedicated treatment of fail-with-URL, MCP elicitation, blocking task state, callback/resume, retries, autonomous workflows, and how this maps to KAOS's current A2A task/autonomous execution model.
