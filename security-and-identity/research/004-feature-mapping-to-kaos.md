# 004 - Feature mapping to KAOS

## Prompt

Ok I would need more details to understand each of these above. So give me for each of the currently implemented features in AIB, how KAOS would use them in the scenario where they were finished / maure or kaos was extended accordingly. Also cover the aspirational ones.

## Response

Below is the cleaner framing: **AIB would be a security/identity companion plane for KAOS**, not a replacement for KAOS agents, MCP servers, or the operator. KAOS would keep orchestrating agents/tools; AIB would decide **who the agent is, what it is allowed to access, whether a user consented, and which token should be used downstream**.

## Currently implemented / substantially implemented AIB features

| AIB feature | What it does | How KAOS would use it if integrated/mature |
|---|---|---|
| **Agent registry** | Stores agent records: agent ID, client ID, display name, docs/governance URLs, permission requirements. | KAOS operator could auto-register each `Agent` CRD into AIB. A KAOS agent named `researcher` would get an AIB identity/record. AIB becomes the source for security metadata: "this is the `researcher` agent, these are its declared permissions, these are its docs/governance links." |
| **Third-party OAuth2 service registry** | Stores external OAuth2 providers/resources such as GitHub, Google, Slack, Databricks, etc. Includes client credentials, scopes, protected resources. | KAOS MCP runtimes that call third-party APIs could point to AIB instead of embedding raw API tokens. Example: a `github-mcp` server declares GitHub as a protected resource; AIB knows GitHub's OAuth config and scopes. |
| **Permission sets** | Groups scopes/permissions into named sets that agents can request. | KAOS could map `Agent.spec.mcpServers` or future `Agent.spec.permissions` to AIB permission sets. Example: `code-review-agent` needs `github:repo:read` and `github:pull_request:write`; AIB presents that bundle to users/admins. |
| **Consent UI/API** | Lets a user grant/revoke an agent's access to third-party services/scopes. | Before a KAOS agent can use a user's GitHub/Slack/Google token through an MCP server, the user approves that delegation in AIB. This is the key "agent acts on behalf of user" flow. |
| **OAuth2 session / token vault** | Stores user OAuth2 sessions and third-party access/refresh tokens, encrypted at rest. | KAOS would stop putting long-lived third-party tokens in MCP env vars/secrets for user-scoped tools. Instead, MCP servers request scoped tokens from AIB at call time. |
| **OAuth2 authorization server mode** | AIB can act as a local/proxy/hybrid OAuth2 server. Supports auth code, client credentials, signing keys, JWKS. | KAOS could use AIB-issued tokens as runtime credentials between agents, MCP servers, gateway, and protected resources. This could become the auth layer for internal KAOS HTTP traffic. |
| **Broker-issued client credentials** | AIB can generate/revoke credentials for agents. | KAOS operator could inject short-lived or broker-managed credentials into agent pods. An agent would authenticate to AIB as itself, not via a shared cluster secret. |
| **Signing keys + JWKS** | AIB manages signing keys and exposes public key material through JWKS. | KAOS services, MCP servers, and gateways could validate AIB-issued JWTs locally. Example: MCP server receives `Authorization: Bearer <AIB JWT>` and verifies it against AIB JWKS. |
| **RFC 8693 token exchange** | Exchanges a subject token for another token, after validating user, agent, resource, consent, and policy. | Most important KAOS use case: agent/MCP presents a token saying "user X via agent Y wants resource Z"; AIB returns the correct third-party access token only if consent and policy allow it. |
| **ExtProc token exchange service** | Envoy External Processor that intercepts requests, exchanges bearer tokens via AIB, and replaces `Authorization` before forwarding. | KAOS Gateway/Envoy could transparently protect MCP servers or external API egress. Agents call MCP normally; gateway swaps the token before the MCP/backend sees it. This reduces changes needed in every MCP server. |
| **Memory/Postgres storage + migrations** | Supports ephemeral memory storage and persistent Postgres storage. | For KAOS production, AIB would use Postgres. For local demos/e2e, memory mode could be enough. |
| **Helm chart / Kubernetes deployment** | Deploys AIB into Kubernetes with end-user/admin ports, storage, ingress, security context. | KAOS install could optionally deploy AIB as an add-on: `kaos system install --identity-broker-enabled`. |
| **Telemetry / audit logging** | Structured logs and OpenTelemetry support. | KAOS traces could include agent identity, token exchange, MCP call, and third-party API access. This is valuable for debugging and compliance. |
| **Encryption-at-rest** | Encrypts sensitive stored values such as OAuth client secrets/tokens/signing material. | KAOS would rely on AIB as the secure vault for delegated user tokens instead of distributing secrets into agent/MCP pods. |

## How these would fit into KAOS workflows

### 1. Agent registration

Today KAOS has:

```yaml
kind: Agent
metadata:
  name: researcher
spec:
  mcpServers:
    - github-tools
```

With AIB integration, the KAOS operator could create/update an AIB agent record:

```text
KAOS Agent researcher
-> AIB Agent record
-> client_id / agent_id
-> required permission sets
-> allowed services/resources
```

That gives the runtime a stable security identity separate from Kubernetes service names.

### 2. MCP server as protected resource

Today a KAOS MCP server might hold credentials directly:

```text
Agent -> MCPServer -> GitHub API
```

With AIB:

```text
Agent -> MCPServer -> AIB token exchange -> GitHub API
```

The MCP server does not need a static GitHub token. It asks AIB for a user/agent-scoped token.

### 3. User-consented third-party tool access

Example: user asks a KAOS agent:

> "Create a GitHub issue for this incident."

Flow with AIB:

1. User authenticates through gateway/IdP.
2. User invokes KAOS agent.
3. Agent calls `github-mcp`.
4. `github-mcp` needs GitHub token for this user.
5. MCP/gateway asks AIB: "Can agent `incident-agent` access GitHub issues for user `alice`?"
6. AIB checks consent, permission set, active OAuth session, scopes.
7. If allowed, AIB returns scoped GitHub token.
8. MCP calls GitHub.

That is the strongest current AIB-to-KAOS fit.

### 4. Transparent Gateway/ExtProc mode

Instead of changing every MCP server, KAOS could put Envoy/agentgateway in front of MCP traffic:

```text
Agent
  -> Gateway / Envoy ExtProc
  -> AIB RFC 8693 token exchange
  -> MCP server receives exchanged bearer token
```

This is appealing because the token exchange happens at the infrastructure layer.

## Aspirational / not-yet-complete features and how KAOS would use them

| Aspirational feature | What it would mean | KAOS value |
|---|---|---|
| **Cryptographic agent-to-agent identity** | Each agent has key material or signed tokens proving its identity. Peers can verify that "this request really came from agent X." | KAOS A2A delegation becomes zero-trust. `coordinator` cannot spoof `analyst`; every A2A request is signed or carries a verifiable token. |
| **Federated broker-to-broker trust** | Multiple AIB instances trust each other across orgs/clusters. | KAOS agents in different clusters/orgs could collaborate. Example: company A's KAOS agent delegates to company B's KAOS agent without sharing one central IdP. |
| **Kubernetes-native workload identity** | AIB binds identities to pods/service accounts/namespaces and validates workload origin. | Prevents a random pod from claiming to be `researcher`. KAOS operator could bind `Agent` CRDs to AIB identities and Kubernetes service accounts. |
| **A2A authorization** | AIB policies decide which agent may call which other agent, with which task/action context. | Replaces or strengthens KAOS's current `agentNetwork.access` allowlist. Instead of just "coordinator can call analyst," policy could say "coordinator can ask analyst for read-only analysis but cannot delegate deployment actions." |
| **MCP-native authorization** | MCP protocol/tool calls carry identity and scopes; MCP server enforces per-tool authorization. | Fine-grained tool security. Example: same `kubernetes-mcp` exposes `get_pods` and `delete_deployment`; AIB allows read tools for one agent but blocks destructive tools. |
| **Automatic KAOS reconciliation** | KAOS operator manages AIB records as part of CRD reconciliation. | Users do not manually configure AIB. Creating an Agent/MCPServer automatically registers identity, permissions, services, and routes. |
| **Policy model for agent capabilities** | Formal model for what an agent is allowed to do, not just OAuth scopes. | Enables governance: "this agent may read Slack and GitHub, but may not write production Kubernetes resources unless approved." |
| **Human approval / re-auth flows inside agent UX** | If token/consent is missing, AIB returns a URL or elicitation flow. | KAOS agent can tell user: "I need GitHub issue write access; approve here," then continue after approval. AIB's ExtProc already hints at this with URL elicitation behavior, but KAOS would need runtime UX support. |
| **Audit/event correlation across agent actions** | Identity, consent, token exchange, MCP call, and final action linked in traces/logs. | You can answer: "Which user authorized which agent to perform which API call, through which MCP server, at what time?" |

## So is AIB useful now or not?

**Both, depending on scope:**

| Scope | Answer |
|---|---|
| "Can I deploy current AIB and KAOS is automatically secure?" | **No.** |
| "Can current AIB solve a real KAOS-adjacent problem with integration?" | **Yes: delegated OAuth/token-vault/token-exchange for MCP tools.** |
| "Does current AIB implement the whole agent identity/federation vision?" | **No, not fully.** |
| "Is it a good foundation for KAOS identity features?" | **Yes, especially around consent, token exchange, OAuth2 server mode, and ExtProc.** |

The key distinction is: **current AIB is already useful for delegated third-party API access, but not yet sufficient as KAOS's complete agent identity/security layer.**
