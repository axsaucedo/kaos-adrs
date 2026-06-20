# 003 - Current and aspirational AIB features

## Prompt

Ok and when you say ``` user-consented delegated OAuth tokens and RFC 8693 token exchange```, does this mean that these are the extent of the entire features implemented atm in AIB? Or these are the features that would be relevant? Are there further features that are not yet implemented?

## Response

No - **user-consented OAuth tokens + RFC 8693 token exchange are not the entire AIB project**, they are the **most KAOS-relevant implemented slice today**.

From the current codebase, AIB also implements or has substantial plumbing for:

| Area | Current state |
|---|---|
| Agent registry | Admin CRUD for agents, metadata, client IDs, permission-set requirements |
| Third-party OAuth2 service registry | Admin CRUD for external OAuth providers/resources |
| Permission sets | Grouping/scoping permissions an agent can request |
| Consent UI/API | End-user grant/revoke flows for agent access |
| OAuth2 session/token vault | Stores user third-party OAuth sessions/tokens, encrypted at rest |
| OAuth2 authorization server mode | Local/proxy/hybrid modes, auth code + client credentials |
| Broker-issued client credentials | Per-agent credentials, hashed secrets |
| Signing keys + JWKS | Managed signing keys and public JWKS endpoint |
| RFC 8693 token exchange | Exchange subject token for stored third-party token after consent checks |
| ExtProc sidecar/service | Envoy external processor to transparently swap bearer tokens |
| Persistence/deployment | Memory/Postgres storage, migrations, Helm chart, telemetry, config |

The reason I emphasized **consent + token exchange** is that those are the features that most directly map to KAOS MCP servers: an agent or gateway can present a user/subject token, and AIB can return a scoped third-party token only if the user granted that agent access.

There are also broader features described in docs that are **not clearly implemented as production-ready capabilities yet**, especially:

| Aspirational / not yet KAOS-ready | What seems missing |
|---|---|
| Cryptographic agent-to-agent identity | No obvious full flow where agents sign payloads and peers verify via broker-managed public keys |
| Federated broker-to-broker trust | Described in docs, but not visible as an implemented core API surface |
| Kubernetes-native agent identity | No direct KAOS/CRD reconciliation, pod identity issuance, or workload binding |
| A2A authorization | No built-in KAOS A2A middleware enforcing AIB grants/identity |
| MCP-native authorization | Would need MCP gateway/server integration and token propagation |
| Automatic KAOS integration | No operator/controller wiring to register Agents/MCPServers into AIB |

So the clean answer is: **AIB already has more than just consent/token exchange, but those are the mature-looking pieces most relevant to KAOS now. The broader "agent identity broker" vision still needs features before it fully matches KAOS's core multi-agent security needs.**
