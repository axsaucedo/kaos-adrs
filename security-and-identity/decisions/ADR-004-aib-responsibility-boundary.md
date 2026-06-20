# ADR-004: AIB responsibility boundary

**Status**: Accepted
**Date**: 2026-06-20

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) establishes that KAOS owns resource identity and topology, while AIB can mirror KAOS identities through `external_id`.

[ADR-003](./ADR-003-user-request-context-propagation.md) establishes an SDK-first request context propagation layer for Agents and MCPServers.

[ADR-002](./ADR-002-enforcement-topology.md) establishes an SDK-first 1.0 topology, LiteLLM as the preferred ModelAPI auth surface, GatewayAPI as a 1.1 resource-boundary extension, and sidecars as deferred.

This ADR defines what AIB owns within that architecture.


---

## Source facts

### AIB Agent registry

Source file:

- `agentic-identity-broker/internal/domain/storage/agent.go`

AIB `Agent` has:

- internal UUID `ID`,
- optional `ClientID`,
- optional `ExternalID`,
- display and documentation fields,
- `ServiceRequirements`,
- `PermissionSets`,
- redirect URIs,
- allowed scopes,
- client metadata document URIs.

Implication:

- AIB can represent KAOS Agents through `ExternalID`, using the identity format from ADR-001.
- AIB stores broker-side records used for authorization, consent, OAuth, and token exchange.
- AIB is not the source of truth for KAOS resource existence.

### AIB PermissionSets

Source file:

- `agentic-identity-broker/internal/domain/storage/permission_set.go`

AIB `PermissionSet` is an admin-defined bundle of OAuth2 scopes spanning one or more third-party services:

```text
PermissionSet
  service_scopes[]
    service_id
    scopes[]
    requirement_type
```

Implication:

- Current PermissionSets are naturally aligned with third-party OAuth/service scopes.
- They are not currently modeled around MCP tool names, MCP arguments, ModelAPI models, Gateway routes, or LiteLLM budgets.
- They can temporarily encode KAOS logical resource scopes through a synthetic internal service and custom scope naming convention, but this is a compatibility workaround rather than the target model.

Temporary workaround example:

```text
service: kaos-internal
scopes:
  - kaos:mcpserver:github:call
  - kaos:modelapi:gpt:invoke
  - kaos:agent:worker:delegate
```

This can bootstrap early resource checks through existing AIB data structures, but it should not be treated as the final resource-grant abstraction.

### AIB UserGrants

Source file:

- `agentic-identity-broker/internal/domain/storage/user_grant.go`

AIB `UserGrant` binds:

```text
principal + agent_id + granted_permission_sets + optional valid_until
```

Implication:

- AIB is well suited to be authoritative for user-delegated grants from a principal to an agent.
- Grant survival across KAOS Agent delete/recreate is possible if the KAOS-AIB sync service preserves the same AIB agent record for the same `external_id`.
- Current `UserGrant` is not a clean model for platform/resource grants, because it is centered on a principal delegating PermissionSets to an agent.
- A temporary bootstrap could use a synthetic platform principal, but the target model should distinguish platform/resource grants from user-delegated OAuth grants.

### KAOS CRD wiring

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/controllers/agent_controller.go`

KAOS Agent CRDs can reference:

- `spec.modelAPI`,
- `spec.mcpServers`,
- `spec.agentNetwork.access`.

Current behavior:

- The operator resolves these references and injects service URLs into the Agent runtime.
- These fields define topology and runtime wiring.
- They do not currently create grants, user consent, scoped authorization, or AIB PermissionSets.

Implication:

- In the security target picture, CRD wiring should become a **requested access edge**, not an automatic grant.
- Deploying an Agent connected to an MCPServer or ModelAPI must not automatically grant user-delegated access or platform resource access.
- When security is enabled, the default posture is **no permissions by default**.

Principle:

```text
wired == requested capability
wired != approved authorization
declared != granted
```

### AIB consent service

Source file:

- `agentic-identity-broker/internal/domain/consent/service.go`

AIB consent:

- resolves an Agent's service requirements and permission sets,
- checks active third-party OAuth sessions for the principal,
- creates or updates grants,
- validates mandatory permission sets and included service IDs,
- enforces active session requirements for grant submission.

Implication:

- AIB already owns a useful user-consent and delegated-grant workflow.
- This maps well to "agent needs user-granted access to third-party services."

### AIB token exchange

Source file:

- `agentic-identity-broker/internal/domain/tokenexchange/service.go`

AIB token exchange:

1. validates RFC 8693 request structure,
2. validates `subject_token`,
3. validates `client_assertion`,
4. extracts principal and agent ID via CEL,
5. authorizes privileged client via CEL,
6. resolves target service from `resource`,
7. verifies user grant before checking token session,
8. retrieves and refreshes stored third-party tokens,
9. validates permission-set scope coverage,
10. returns token exchange response or re-auth/approval hints.

Implication:

- AIB is already a strong fit for delegated third-party token exchange.
- AIB token exchange can be called directly by an SDK or indirectly by Gateway/ExtProc.
- Current AIB token exchange is service/resource oriented, not MCP-tool semantic.

### AIB ExtProc

Source file:

- `agentic-identity-broker/internal/extproc/server/server.go`

AIB ExtProc:

- extracts Bearer tokens at a proxy boundary,
- builds a resource URI,
- exchanges tokens,
- replaces the upstream `Authorization` header,
- returns error/reauth URI responses in some failure cases,
- passes request/response bodies through.

Implication:

- ExtProc fits Gateway or sidecar token exchange.
- Per ADR-002, this is a later Gateway/resource-boundary integration, not required for SDK-first 1.0.

---

## Decision

Use AIB as the **authorization and delegated-token broker** for KAOS 1.0, but not as the owner of all security concerns.

AIB owns two grant domains:

1. **Platform/resource grants**
   - Whether a KAOS logical caller may access a KAOS logical target.
   - Examples:

     ```text
     kaos://agent/researcher -> kaos://mcpserver/github
     kaos://agent/researcher -> kaos://modelapi/gpt
     kaos://agent/lead -> kaos://agent/worker
     ```

2. **User-delegated third-party grants**
   - Whether a principal has delegated a third-party OAuth/service permission set to an agent.
   - Example:

     ```text
     keycloak://kaos/alice -> kaos://agent/researcher -> github-issues-reader
     ```

KAOS CRD references define requested access edges. The KAOS-AIB sync service may mirror those requested edges into AIB records, but those requests are not automatically approved grants.

Security-enabled deployments are **no permission by default**:

```text
Agent references MCPServer      -> requested edge
Agent references ModelAPI       -> requested edge
Admin/platform grant exists     -> resource access allowed
User delegated grant exists     -> user third-party access allowed
```

Current AIB does not yet have a clean first-class model for platform/resource grants or a request/approval workflow for those grants. The accepted target therefore has two layers:

1. **Target model**: AIB gets a first-class platform/resource grant concept and an admin approval lifecycle for requested KAOS access edges.
2. **Bootstrap model**: early implementations may encode KAOS resource access with a synthetic internal AIB service plus custom PermissionSet scopes, or a synthetic platform principal, while keeping that representation explicitly temporary.

Bootstrap encoding must preserve the distinction between:

```text
platform/resource grant:
  kaos://agent/researcher -> kaos://mcpserver/github

user delegated grant:
  keycloak://kaos/alice -> kaos://agent/researcher -> github-issues-reader
```

The workaround must not make requested CRD wiring an approved grant automatically.

### Responsibility split

| Component | Owns |
|---|---|
| KAOS CRDs/operator | Resource existence, topology, service wiring, `spec.security.id`, requested access edges |
| KAOS-AIB sync service | Mirroring KAOS identities and requested access edges into AIB |
| KAOS/AIB SDK | Runtime context propagation, AIB client calls, SDK-native enforcement hooks |
| AIB | KAOS logical resource grants, user delegated grants, third-party services, PermissionSets, consent, token vault, token exchange |
| External IdP such as Keycloak/Dex/OIDC | Human authentication and user identity source |
| LiteLLM | ModelAPI internals: model access, provider keys, budgets, rate limits |
| GatewayAPI 1.1 | Resource-boundary enforcement, JWT validation, bypass prevention with NetworkPolicy |
| OPA/Keycloak AuthZ | Future optional PDP integration if requirements outgrow AIB's initial policy model |

### Keycloak boundary

Keycloak or another IdP answers:

```text
Who is this human user?
Can this user authenticate to KAOS?
What roles/groups/claims does this user have?
```

AIB answers:

```text
Has this principal delegated third-party access to this agent?
Is this agent allowed to call this KAOS logical resource?
Does the user have a live third-party OAuth session?
Can a scoped third-party token be returned now?
```

AIB does not replace Keycloak/Dex/OIDC for human authentication.

### Runtime and workload identity boundary

For 1.0, AIB validates logical identities and grants, not cryptographic workload bindings.

The 1.0 request context should carry:

```text
user principal X
calling KAOS logical identity Y
target KAOS logical identity Z
```

AIB can decide whether `Y -> Z` is authorized and whether `X -> Y -> third-party permission set` is granted.

ADR-001 already excludes Kubernetes ServiceAccounts and SPIFFE/SPIRE from the initial implementation. Therefore 1.0 does not prove that the physical pod making the request is cryptographically bound to the claimed KAOS identity.

That hardening is deferred to later Gateway+NetworkPolicy, Kubernetes ServiceAccount, or SPIFFE/SPIRE work.

### AIB token issuance boundary

AIB **does** issue or return delegated third-party access tokens through token exchange.

AIB **does not** become the general issuer of internal KAOS runtime identity/delegation tokens in 1.0.

This means:

- AIB can return GitHub/Slack/Google/etc. access tokens after grant/session validation.
- AIB should not be required to mint every internal Agent-to-Agent, Agent-to-MCPServer, or Agent-to-ModelAPI caller token in 1.0.
- Internal KAOS caller identity may initially come from trusted inbound user tokens, SDK-carried context, Gateway-normalized headers, or future workload identity.

### Autonomous agents

Autonomous runs split into two cases:

| Autonomous case | Initial treatment |
|---|---|
| Agent acts only as itself/service | AIB is not required; future options include robot users, service credentials, Kubernetes ServiceAccounts, or workload identity |
| Agent acts on behalf of a user's third-party account | AIB is in scope through durable user-delegated grants and token vault/session refresh |

Example:

```text
Daily email summarizer acts for Alice's Gmail
```

AIB should store Alice's delegated grant and Google OAuth session, then return a Google access token to the autonomous Agent when the grant and session are valid.

---

## Annex: Alternatives considered

### Option A: AIB only as delegated OAuth/token broker

AIB would own user delegated grants, third-party OAuth sessions, consent, token vault, and token exchange, but not KAOS resource grants.

Rejected as too narrow.

KAOS CRDs already define Agent-to-MCPServer, Agent-to-ModelAPI, and Agent-to-Agent requested access edges. These are natural KAOS logical resource grants. Keeping them outside AIB would either push definitions into dynamic SDK code or require a separate authorization store.

However, current AIB does not yet expose this as a first-class model, so implementation may need an interim PermissionSet/synthetic-service encoding before the proper resource-grant model exists.

### Option B: AIB as broad all-purpose policy platform

AIB would own all authorization, policy language, approval workflows, ModelAPI policies, MCP tool/argument rules, runtime token issuance, and token exchange.

Rejected for 1.0.

This overextends AIB beyond its current implementation and risks duplicating Keycloak, OPA, LiteLLM, and Gateway responsibilities. It also forces AIB to understand detailed MCP tool schemas, ModelAPI budgets, and Gateway route mechanics too early.

### Option C: Keycloak/OPA as the KAOS resource-grant source of truth

Keycloak Authorization Services or OPA could model KAOS resources, scopes, permissions, and policies.

Deferred.

This may be useful for enterprise deployments, but 1.0 benefits from keeping KAOS-native logical resource grants close to AIB, because AIB already understands agents, grants, token exchange, and delegated access. Keycloak remains the user identity source; OPA/Keycloak AuthZ can be revisited in the later authorization-policy ADR.

---

## Consequences

### Positive

- Keeps permission definitions config-as-code through KAOS CRDs and AIB-synced records, not hidden in SDK code.
- Makes CRD wiring meaningful as requested access without making it an automatic grant.
- Gives AIB a coherent authorization role for KAOS logical resource grants and user-delegated third-party grants.
- Keeps Keycloak focused on human identity/SSO.
- Keeps LiteLLM focused on ModelAPI model access, budgets, and rate limits.
- Keeps MCP tool/argument-level authorization deferred until KAOS models those concepts explicitly.

### Negative

- AIB needs a resource-grant concept beyond its current user grant and PermissionSet model.
- Until that exists, any PermissionSet-based resource-grant encoding is a temporary workaround and must be documented as such.
- AIB also needs a request/approval lifecycle for KAOS resource grants if requested CRD access edges are to be reviewed before approval.
- 1.0 logical identity validation does not cryptographically prove workload identity.
- Gateway/NetworkPolicy bypass prevention remains a 1.1 hardening layer.
- ModelAPI root access can be AIB-managed, but detailed model/budget enforcement remains in LiteLLM.

### Risks

- If requested edges are mistaken for approved grants, deployments could become over-permissive. Documentation and API naming must distinguish requested vs approved.
- If workload identity is not added later, malicious in-cluster workloads could spoof logical identity headers/context in weakly isolated clusters.
- AIB resource grants and AIB user-delegated grants must be modeled distinctly to avoid mixing platform access with user OAuth consent.

---

## Final decision

1. AIB is the authorization and delegated-token broker for KAOS 1.0.
2. AIB is authoritative for KAOS logical resource grants such as Agent-to-MCPServer, Agent-to-ModelAPI, and Agent-to-Agent.
3. AIB is authoritative for user delegated grants and third-party OAuth sessions.
4. KAOS remains authoritative for CRDs, topology, resource identity, runtime orchestration, and requested access edges.
5. KAOS CRD references are requested access edges; they do not automatically grant access.
6. Security-enabled deployments use no-permission-by-default semantics.
7. Target AIB needs a first-class platform/resource grant model distinct from user-delegated OAuth grants.
8. Target AIB needs a request/approval lifecycle for KAOS resource grants.
9. Until that exists, early implementations may bootstrap resource grants with a synthetic internal service and custom PermissionSet scopes, but this is temporary.
10. AIB PermissionSets remain primarily third-party service-scope bundles in the target model.
11. Do not force MCP tool names, MCP arguments, ModelAPI model allowlists, ModelAPI budgets, or Gateway route rules into AIB PermissionSets as the long-term model.
12. ModelAPI root resource access may be AIB-managed; ModelAPI internals remain LiteLLM-owned.
13. AIB returns delegated third-party access tokens through token exchange, but does not become the general issuer of internal KAOS runtime identity/delegation tokens in 1.0.
14. SDK-native AIB calls are the first integration path.
15. AIB ExtProc is deferred to the GatewayAPI 1.1 resource-boundary extension.
16. AIB does not replace Keycloak/Dex/OIDC for human authentication.
17. Kubernetes ServiceAccount/SPIFFE workload binding remains deferred from ADR-001.
18. OPA/Rego and Keycloak Authorization Services integration are deferred to the authorization-policy decision.
