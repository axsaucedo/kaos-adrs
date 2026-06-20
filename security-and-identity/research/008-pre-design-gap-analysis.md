# 008 - Pre-design gap analysis

## Prompt

3. Okay, we'll flesh this out further to define exactly what we needed to support this within KAOS. 4. Okay, same as before. 6. ok. --- aIt seems now all of the other questions and topics have been addressed. We now want to start moving towards putting together an architectural assessment and design of what could be the target picture that then can be used for the initial implementations. Before that, perform an analysis of all of these progress points and discussion, and outline if there are any flow considerations or integrations missing from the top of my mind.

I think the only consideration is more on the implementation side, including not just the authorisation and authentication but general security within chaos. For example, we haven't really introduced hard security such as certificate support as well as SSL. There is a question of whether we want to implement this authentication and authorisation ourselves, or whether we want to also explore other alternatives such as service mesh-based service-to-service frameworks within Kubernetes, or actually implementing the authorisation sidecars ourselves. Potentially even assessing what components should be part of AIP instead of being developed within and for chaos, as well as potentially even third-party components like an SDK for Python, although right now I don't see custom Python integrations that need to be built.

## Response

Before the target design, the main missing piece is not another AIB feature list; it is a complete **security flow model** for KAOS traffic. The architecture needs to define identities, token propagation, enforcement points, trust boundaries, certificate/TLS posture, and which components are owned by KAOS, AIB, or third-party infrastructure.

## What is already covered

The prior discussion has mostly settled these:

| Area | Current conclusion |
|---|---|
| AIB fit | Useful as identity/consent/token-exchange plane, not a drop-in KAOS core feature. |
| Agent registry | Prefer AIB CRD watcher/controller over KAOS imperative push. |
| KAOS identity metadata | Prototype via annotations, mature via `spec.identity`; AIB remains policy authority. |
| Permission sets | Centralized in AIB, not blindly granted from Agent CRD. |
| Identity model | Separate logical agent, workload instance, user/request, and MCP/server identities. |
| User token propagation | KAOS runtime/gateway concern, not AIB core. |
| MCP enforcement | Possible via native FastMCP auth, MCP-aware sidecar, or MCP-aware Gateway/ExtProc. |
| Gateway vs sidecar | Needs dedicated design comparison. |
| Autonomous agents | Need agent-owned/service grants or user-delegated grants bound to run ID/expiry. |
| Signed A2A payloads | Optional/advanced; leave out of initial design. |
| Consent/reauth UX | Needs separate design for fail-with-URL, elicitation, pause/resume. |

## Missing or underdeveloped flow considerations

### 1. End-to-end request identity flow

The design still needs exact flows for:

```text
external user -> gateway -> KAOS agent -> MCP -> third-party API
```

and:

```text
autonomous agent -> MCP -> third-party/internal API
```

For each hop, define:

- What token/certificate is presented?
- Who verifies it?
- What identity claims are preserved?
- What gets exchanged?
- What is logged/audited?
- What happens on missing consent, expired token, or denied policy?

### 2. In-cluster service-to-service trust

We discussed bearer tokens but not fully the transport trust layer:

- TLS for all HTTP traffic?
- mTLS between workloads?
- Gateway-terminated TLS only, or end-to-end TLS?
- Certificates managed by cert-manager, service mesh, SPIRE/SPIFFE, Gateway API, or custom KAOS/AIB logic?

This matters because bearer tokens over plaintext pod network traffic are not enough for a robust security story.

### 3. Service mesh / SPIFFE / existing Kubernetes security alternatives

Before building custom sidecars, assess alternatives:

| Alternative | What it could provide |
|---|---|
| Istio/Linkerd/Consul mesh | mTLS, workload identity, traffic policy, telemetry, authz policy. |
| SPIRE/SPIFFE | Strong workload identity independent of service mesh. |
| cert-manager | Certificate issuance/rotation for Gateway and services. |
| Envoy Gateway policies | Centralized Gateway API-compatible authn/authz extension points. |
| OPA/Gatekeeper/Kyverno | Admission and policy validation for CRDs. |

AIB may not need to own transport identity if mesh/SPIFFE owns workload identity and AIB owns consent/token exchange.

### 4. Policy model boundaries

Need to decide what policy lives where:

| Policy type | Candidate owner |
|---|---|
| Agent may use permission set X | AIB |
| User granted agent X scopes Y | AIB |
| Agent pod may claim logical identity X | KAOS + Kubernetes + AIB |
| Agent may call MCP server Y | KAOS `agentNetwork` today, maybe AIB later |
| MCP tool invocation allowed | MCP runtime, sidecar, or Gateway policy |
| Network-level service-to-service allow | Mesh/network policy/Gateway |
| CRD validity/security posture | KAOS webhook/admission policy |

Without this separation, the design risks duplicating authorization across KAOS, AIB, Gateway, and sidecars.

### 5. Token types and lifetimes

Need a token taxonomy:

- User ID token/access token from IdP.
- AIB-issued internal agent token.
- Workload/service account token.
- MCP server token/client assertion.
- RFC 8693 exchanged downstream token.
- Long-lived refresh token stored in AIB vault.
- Autonomous run grant token/record.

For each: issuer, audience, holder, storage location, lifetime, renewal path, revocation behavior.

### 6. Runtime metadata store

AIB can sync CRDs, but runtime state may need a store:

- Agent logical ID -> CRD UID -> active pods/service accounts.
- MCP resource -> service endpoint/protected resources.
- Autonomous run ID -> owner/grant/expiry.
- Gateway route -> AIB resource/audience.

Some of this is in Kubernetes status; some may belong in AIB; some may need explicit KAOS status fields.

### 7. Multi-replica and instantiation semantics

Need to define:

- One logical agent can have N pod replicas.
- Is identity per logical agent, per pod instance, or both?
- Are grants attached to logical agent or instance?
- What happens during rollout?
- How are old pod credentials revoked?

Likely answer: grants attach to logical agent; runtime credentials attach to workload instance.

### 8. ModelAPI access control

We focused on MCP, but ModelAPI may also need policy:

- Which agents may call which model?
- Should model calls carry agent/user identity?
- Should model usage be auditable per user/request/agent?
- Should autonomous agents have model budget/permission controls?

This could be phase two, but it belongs in the target picture.

### 9. Memory and task data security

KAOS memory/task stores may contain sensitive user data, tool outputs, tokens accidentally included by tools, or consent URLs.

Need to consider:

- Encryption at rest for Redis/local alternatives.
- Redaction of tokens from traces/logs.
- Per-user/session access boundaries.
- Retention and deletion.

### 10. Secrets and configuration security

Need to decide:

- Where AIB client secrets live.
- How agent/MCP runtime credentials are mounted.
- Whether KAOS should use projected service account tokens, Kubernetes Secrets, CSI Secret Store, or AIB-issued short-lived credentials.
- Rotation/revocation process.

### 11. Consent and autonomous safety

Need precise behavior for:

- User-triggered missing consent.
- Autonomous missing consent.
- Expired autonomous grant.
- User revokes grant while autonomous task is running.
- Task pause/resume vs fail closed.

### 12. SDK requirement

At the moment, a custom Python SDK does not look necessary if enforcement is done by Gateway/sidecar and FastMCP can validate JWTs natively.

An SDK may become useful only if KAOS chooses app-level integration:

- Agent runtime needs to request AIB tokens directly.
- MCP tools need helper APIs for token exchange.
- Consent-required errors need common structured handling.

Initial design can avoid SDK work by prioritizing infrastructure-level enforcement.

## Initial design axes to evaluate

The architecture assessment should explicitly compare these:

1. **Authn source**: existing enterprise IdP vs Dex/Keycloak vs AIB local mode.
2. **Workload identity**: Kubernetes SA tokens vs AIB credentials vs SPIFFE/SPIRE vs mesh identity.
3. **Enforcement point**: Gateway/ExtProc vs sidecar vs app-native FastMCP/agent runtime.
4. **Policy owner**: AIB vs KAOS CRD fields vs mesh/Gateway policies.
5. **Traffic coverage**: user->agent only, agent->MCP, A2A, ModelAPI, egress.
6. **Consent UX**: fail URL vs MCP elicitation vs pause/resume.
7. **Autonomous authorization**: service grant vs user-delegated run grant.

## Main recommendation before design

Do not design this as "KAOS implements auth itself" vs "AIB implements auth itself." The cleaner split is:

```text
IdP / mesh / Kubernetes = baseline identity and transport security
AIB = agent/user consent, policy, token vault, token exchange
KAOS = orchestration, runtime context propagation, CRD metadata, task UX
Gateway/sidecar = enforcement point
```

The target architecture should prefer using existing primitives for hard security: OIDC, JWKS, TLS/mTLS, cert-manager, service mesh/SPIFFE where appropriate. KAOS should avoid building custom crypto, custom certificate lifecycle, or a bespoke auth framework unless there is no existing component that fits.
