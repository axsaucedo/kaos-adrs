# 001 - Target picture components and research domains

## Prompt

Another topic that I would see missing is the approval flow. That is something that we will want to consider also, the target picture about whether it's included in the initial implementations to be confirmed. OK, now we should proceed to the next stage, which is the target picture design. I want to start now. This will be a similar effort to identify the key domains to clarify, the key research areas to confirm, and to start building, using this to build a target picture. In this case, I want to make sure that we are now starting to look at the code bases and starting to have an understanding of the different components in place. For AIB, I want to focus specifically on what would be the current functionalities, but if there's something missing, we can already also include that in the target picture as well as we would be able to suggest/contribute upstream. From this prompt onwards, I now want us to have the content on ./tmp/target/. Actually, now that we are moving to a bit more of a structured development, I would like to start documenting the progress on this. We should create a new branch, although we are already in a new branch, and commit the prompt files and progress as this progresses under a folder that I currently have being ../kaos-ai-docs/ and createa a new folder security-and-identity/ where we want to add each of these files, and ensure use comprehensive commits style as each file is added, and you can also do it for the existing ones. Let's then start with the first exploration under ./target. Start with the key components high level that would be part of the target picture, and we'll take a similar research approach (as a Research -> Plan -> Implement). If required also fetch specific RPI resources to ensrue this is following best practice.

## Response

## Current stage

We are moving from exploratory AIB fit analysis into a **target-picture design** for KAOS security and identity. The goal is not implementation yet; it is to define the architectural domains, the key components, the missing flows, and the research needed before an initial implementation plan.

The target picture should account for:

- Existing KAOS components: Agent CRD/runtime, MCPServer CRD/runtimes, ModelAPI, Gateway API support, A2A tasks, autonomous execution, memory/task state, operator reconciliation.
- Existing AIB components: agent registry, service registry, permission sets, consent UI/API, OAuth2 session/token vault, OAuth2 server mode, client credentials, signing keys/JWKS, RFC 8693 token exchange, ExtProc token exchange, Postgres/memory storage, Helm deployment, telemetry, encryption.
- Potential external/security infrastructure: OIDC IdP, Gateway/Envoy, service mesh, SPIFFE/SPIRE, cert-manager, Kubernetes ServiceAccounts, admission webhooks, network policies, OPA/Kyverno/Gatekeeper.

## Target-picture component map

### 1. Identity sources

These define who or what is acting.

| Component | Role in target picture | Current status |
|---|---|---|
| **User IdP** | Authenticates human users and issues user tokens/claims. Could be existing enterprise IdP, Keycloak, Dex, or oauth2-proxy-backed flow. | External to KAOS/AIB; required for user-delegated flows. |
| **KAOS logical Agent identity** | Stable product/security identity for an `Agent` CRD, independent of pod replicas. | KAOS has Agent CRDs; no first-class security identity field yet. |
| **KAOS workload instance identity** | Proves a pod/replica may act as a logical agent or MCP server. | Kubernetes ServiceAccounts exist; AIB-specific workload binding missing. |
| **MCPServer identity** | Identifies the tool service executing an action. | KAOS has MCPServer CRDs; no AIB identity binding yet. |
| **AIB identity records** | Stores agent records, client credentials, permission set associations, and service records. | Implemented in AIB, but not synced from KAOS. |

Design question: should AIB trust Kubernetes ServiceAccount tokens, AIB-issued client credentials, SPIFFE IDs, or a combination?

### 2. Control-plane sync and metadata

This keeps AIB's registry aligned with KAOS resources.

| Component | Role | Target direction |
|---|---|---|
| **AIB Kubernetes watcher/controller** | Reads KAOS `Agent`, `MCPServer`, possibly `ModelAPI`, Services, HTTPRoutes, and ServiceAccounts. | Prefer this over KAOS pushing records imperatively. |
| **KAOS CRD identity fields** | Exposes stable identity intent and requested profiles. | Prototype via annotations; mature via `spec.identity`. |
| **Admission/mutating webhooks** | Validate identity config, default fields, optionally inject sidecars/env/projected tokens. | Optional but likely valuable. |
| **Runtime metadata store** | Maps logical agents, pod instances, routes, run IDs, grants, and service identities. | Needs design; may span Kubernetes status + AIB storage. |

Design question: what metadata is authoritative in KAOS vs AIB vs Kubernetes status?

### 3. Authentication and authorization enforcement points

These decide where requests are checked.

| Enforcement point | Role | Pros | Open questions |
|---|---|---|---|
| **Gateway/Envoy/ExtProc** | Central authn/authz and token exchange for user->agent, agent->MCP, possibly A2A. | Low app changes, centralized audit, leverages AIB ExtProc path. | Does all traffic route through Gateway? Can it parse MCP bodies for tool-level auth? |
| **Sidecar/local proxy** | Per-workload authn/authz/token exchange without changing app code. | Flexible, close to workload, can be MCP-aware. | Operational overhead, injection model, caching/failure behavior. |
| **Native FastMCP auth** | MCP server validates JWTs and can enforce tool-aware policy in-process. | Best tool context, simpler per-request decisions. | Requires runtime/server code/config integration. |
| **Agent runtime middleware** | Agent endpoints validate user/agent tokens and carry run context. | Required for user context propagation. | How much auth logic should live in Python runtime vs infra? |
| **Service mesh policy** | mTLS and service-to-service authz. | Best hard transport security if adopted. | Adds dependency and operational complexity. |

Design question: should the initial implementation use Gateway/ExtProc, sidecar, native runtime integration, or a layered combination?

### 4. Token and credential services

These issue, validate, exchange, and store credentials.

| Token/credential | Issuer/source | Holder | Purpose |
|---|---|---|---|
| **User token** | IdP/gateway | User request context, agent runtime | Identifies the human/request principal. |
| **Workload token** | Kubernetes SA, SPIFFE, mesh, or AIB | Agent/MCP pod | Proves pod instance identity. |
| **AIB agent token** | AIB OAuth2 server mode | Agent runtime | Internal KAOS/AIB bearer credential with audience/scope. |
| **MCP client assertion** | AIB or IdP | MCP/gateway/sidecar | Authenticates token exchange client. |
| **Downstream third-party token** | AIB token vault/exchange | MCP, sidecar, or gateway | Calls GitHub/Slack/Databricks/etc. |
| **Autonomous grant record** | AIB policy/consent flow | AIB storage | Time-bound authorization for autonomous runs. |

Design question: what exact token is sent on each hop, and when does exchange happen?

### 5. Consent, approval, and delegation lifecycle

Approval flow is a distinct domain and should be in the target picture.

| Flow | Meaning | Initial-design question |
|---|---|---|
| **User consent** | User allows agent X to use scopes Y on resource Z. | AIB has consent UI/API; KAOS must surface missing-consent/reauth states. |
| **Admin approval** | Platform/security owner approves agent X for permission profile Y. | Likely AIB-owned; may require upstream AIB additions. |
| **Runtime approval / HITL** | Human approves a specific risky action at runtime. | Not currently covered; decide whether initial scope includes this. |
| **Autonomous run authorization** | User/admin grants agent X permissions for run ID R until expiry. | Needed for KAOS autonomous execution. |
| **Revocation** | User/admin removes grant while tasks may be running. | Need fail-closed and task behavior. |

Approval should not be collapsed into OAuth consent only. The target picture needs at least three layers:

```text
1. Platform/admin approves what an agent is eligible to request.
2. User consents to user-delegated access.
3. Optional runtime approval gates high-risk actions.
```

Design question: which approval layers are required for the initial implementation, and which are future?

### 6. Traffic flows

The target design should explicitly model at least these flows:

1. **External user invokes KAOS agent**
   - User authenticates.
   - Agent receives verified identity.
   - Agent run/session stores user context.

2. **Agent calls MCP for user-delegated third-party access**
   - Agent/MCP request carries user + agent context.
   - Gateway/sidecar/native MCP asks AIB for exchange.
   - AIB checks user consent and permission sets.
   - MCP calls downstream API.

3. **Autonomous agent calls MCP**
   - No live user.
   - Agent uses workload/agent identity.
   - AIB checks service grant or user-delegated autonomous grant tied to run ID/expiry.

4. **Agent-to-agent delegation**
   - Caller agent identity verified.
   - Target agent validates bearer token or Gateway enforces A2A policy.
   - Signed payload identity is deferred.

5. **Agent calls ModelAPI**
   - Optional initial scope, but target picture should decide if model usage should carry user/agent identity for audit, quotas, and policy.

6. **Consent or approval missing**
   - AIB returns structured consent/approval requirement.
   - KAOS returns URL, elicits approval, or blocks/resumes task.

### 7. Hard security and transport

We should not design only bearer-token authorization. The target picture needs a baseline security posture:

| Concern | Research/design area |
|---|---|
| TLS for ingress | Gateway TLS, cert-manager, existing cluster ingress. |
| In-cluster TLS/mTLS | Service mesh, SPIFFE/SPIRE, cert-manager-issued service certs, or Gateway-only. |
| Certificate lifecycle | Avoid custom cert handling if possible. |
| Network policy | Namespace/service restrictions independent of app auth. |
| Secret management | Projected SA tokens, Kubernetes Secrets, CSI Secret Store, AIB-issued short-lived creds. |
| Logging/redaction | No bearer/downstream tokens in logs/traces. |
| Memory/task data | Retention, redaction, encryption, user/session access boundaries. |

Design question: which hard-security baseline is required for initial implementation vs recommended production deployment?

## Key research areas to confirm

### A. AIB codebase capabilities

Confirm exact current support for:

- Agent registry and client credential lifecycle.
- Permission sets and how they bind to agents/services.
- OAuth2 local/proxy/hybrid mode behavior and token claims.
- JWKS/signing-key lifecycle.
- RFC 8693 request shape and policy hooks.
- ExtProc capabilities and limitations.
- Consent/reauth URL behavior.
- Storage/encryption production readiness.
- Helm chart extension points.

### B. KAOS codebase integration points

Confirm exact surfaces for:

- Agent server request handling and context propagation.
- Pydantic AI MCP client creation and whether headers/auth can be injected.
- A2A `RemoteAgent` request headers and auth support.
- Autonomous task/run state and run IDs.
- Operator Agent/MCPServer/ModelAPI CRD fields and status.
- Gateway API HTTPRoute generation.
- Runtime env var injection and ServiceAccount support.

### C. External best-practice references

Likely references to review before design choices:

- OAuth 2.0 Token Exchange (RFC 8693).
- OAuth 2.0 Authorization Server Metadata (RFC 8414).
- OIDC/JWKS validation patterns.
- MCP auth specification and FastMCP auth provider docs.
- Kubernetes Gateway API auth extension/Envoy Gateway ExtAuth/ExtProc capabilities.
- SPIFFE/SPIRE workload identity.
- cert-manager certificate lifecycle.
- Istio/Linkerd service-to-service mTLS and authorization policy.
- Kubernetes projected ServiceAccount tokens and TokenRequest API.

## Initial target-picture hypothesis

The early target should avoid a custom KAOS auth framework and instead compose existing pieces:

```text
User IdP / Gateway auth
        ↓
KAOS Agent runtime with user/run context propagation
        ↓
Gateway/sidecar enforcement for Agent->MCP and optionally A2A/ModelAPI
        ↓
AIB for agent registry, permission policy, consent, token vault, token exchange
        ↓
MCP/third-party APIs with scoped downstream tokens
```

For first implementation, the most realistic slice is:

1. AIB watches or imports KAOS Agent/MCP metadata.
2. KAOS propagates user identity from ingress to agent run context.
3. Agent->MCP traffic goes through Gateway/ExtProc or sidecar.
4. AIB enforces user consent and token exchange for one protected MCP/third-party service.
5. Consent-required errors are surfaced as structured URLs, with retry rather than full pause/resume.

Future layers:

- First-class `spec.identity`.
- Autonomous run grants with expiry.
- MCP-aware sidecar or native FastMCP tool-level policy.
- ModelAPI policy/audit.
- Service mesh/SPIFFE integration.
- Runtime approval/HITL for high-risk tool actions.

## Research -> Plan -> Implement track

### Research

1. Validate AIB current API/runtime capabilities against the target component map.
2. Validate KAOS runtime/operator/gateway hooks for context propagation and enforcement.
3. Compare Gateway/ExtProc vs sidecar vs native FastMCP for MCP auth.
4. Compare OIDC/Keycloak/Dex/gateway options for user auth in KAOS.
5. Compare transport security options: Gateway TLS, service mesh mTLS, SPIFFE, cert-manager.
6. Define approval flow taxonomy: admin approval, user consent, runtime approval, autonomous grant.

### Plan

1. Choose initial target slice.
2. Define identity/token model and exact flows.
3. Define CRD metadata changes or annotations.
4. Define enforcement topology.
5. Define AIB upstream additions vs KAOS-specific integration.
6. Define tests/e2e validation.

### Implement

1. Minimal KAOS identity metadata and user context propagation.
2. Minimal AIB sync/import path.
3. One protected MCP flow with AIB token exchange.
4. Consent-required handling.
5. Documentation and example manifests.
