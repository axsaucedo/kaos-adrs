# ADR-KAOS-004: AIB responsibility boundary

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

Use AIB as the **authorization, agent-identity, and delegated-token broker** for KAOS, but not as the owner of all security concerns.

Enforcement is gateway-centric: the Envoy gateway validates identities, calls AIB `ext_authz` for allow/deny resource decisions, and uses AIB `ext_proc` for token exchange. AIB is the decision and token authority behind that gateway; it is not invoked per-runtime from application code (except in custom servers run off-gateway). See ADR-KAOS-009.

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

Current AIB does not yet have a clean first-class model for platform/resource grants or a request/approval workflow for those grants. The accepted target therefore has two AIB resource-grant modeling tracks:

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
| KAOS CRDs/operator | Resource existence, topology, service wiring, `spec.security.id`, requested access edges, mounting AIB agent credentials into pods |
| KAOS-AIB sync service | Mirroring KAOS identities and requested access edges into AIB; provisioning per-agent AIB credentials into Secrets |
| KAOS/AIB SDK | Runtime context propagation (subject + actor) and agent machine-token lifecycle; optional AIB client calls for custom off-gateway servers |
| AIB | Agent identities (per-agent client credentials + issued actor tokens), KAOS logical resource grants, user delegated grants, third-party services, PermissionSets, consent, token vault, token exchange, `ext_authz` access decisions |
| External IdP such as Keycloak/Dex/OIDC | Human authentication and user identity source only |
| LiteLLM | ModelAPI internals: model access, provider keys, budgets, rate limits |
| Gateway (Envoy) | Enforcement plane: `jwt_authn`, `ext_authz` to AIB, `ext_proc` token exchange, NetworkPolicy bypass prevention |
| OPA/Keycloak AuthZ | Optional advanced PDP integration (OPA is a drop-in `ext_authz` backend) if requirements outgrow AIB's grant model |

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

AIB validates logical identities and grants, not cryptographic workload bindings.

The propagated request context carries two distinct identities:

```text
user principal X        (subject; Keycloak/OIDC-issued user token)
calling agent Y         (actor; AIB-issued agent token, sub/azp = agent Y)
target KAOS identity Z  (resolved from the gateway route)
```

AIB decides whether actor `Y -> Z` is authorized (resource access) and whether `X -> Y -> third-party
permission set` is granted (user-delegated third-party access).

ADR-KAOS-001 excludes Kubernetes ServiceAccounts and SPIFFE/SPIRE, so the model does not cryptographically
prove that the physical pod is bound to agent Y; it proves possession of Y's AIB credential. Pod-level
cryptographic binding (mTLS/SPIFFE) is deferred future hardening.

### Multi-agent delegation: actor identity must be the calling agent

Consider `user -> Agent A -> Agent B -> MCPServer Y`, where A may access MCP X and B may access MCP Y.

If B simply forwarded the user's token (whose `azp` = A) and the decision read the agent from
`subject_token.azp`, B's call to Y would be wrongly attributed to **A** — a real authorization bug.

The target avoids this **without nested-actor chains**: each agent authenticates as **itself** using its
own AIB-issued identity. When B calls Y, the **actor** is B (from B's own AIB token), and the user rides
as the **subject**. The decision is `actor B -> resource Y`, so:

```text
B -> Y   allowed only if B is granted Y
A -> Y   denied (A is not granted Y), even if A delegated a task to B
```

This is correct least privilege: delegating a task to B never widens B's access, and A cannot reach Y
through B unless B itself is allowed. The user principal is used only for user-delegated third-party
grants. Resource-access decisions therefore key on the **calling agent's own identity, never on
`subject_token.azp`**. Deep multi-hop delegation-chain *policy* (e.g. "B may be delegated to only by A")
is out of scope.

### AIB issues agent identities

AIB **is** the agent identity issuer. AIB is a full OAuth2 authorization server: in local/hybrid mode it
mints AIB-signed JWTs, exposes JWKS and RFC 8414 metadata, and supports the `client_credentials` grant.

- Each KAOS agent is registered with AIB and issued per-agent client credentials through the admin API.
- The agent obtains its short-lived **actor token** by running `client_credentials` against AIB's
  existing `/oauth2/token` endpoint; the token's `sub`/`azp` resolves to its KAOS logical identity.
- Client authentication defaults to the `client_secret` (Argon2id-hashed by AIB); `private_key_jwt`
  (client assertion) is a stronger option; mTLS is future hardening.
- AIB also issues or returns delegated **third-party** access tokens through token exchange.

This is a deliberate change from an earlier scoping deferral that said AIB would not issue internal
identity tokens: AIB already implements this, and gateway-centric multi-agent delegation requires it.
**Keycloak/Dex/OIDC remain human authentication only**; they do not issue agent identities.

### Autonomous agents

Autonomous runs split into two cases:

| Autonomous case | Treatment |
|---|---|
| Agent acts only as itself/service | Actor-only: the agent uses its AIB-issued identity; there is no user subject |
| Agent acts on behalf of a user's third-party account | AIB is in scope through durable user-delegated grants and token vault/session refresh |

Example:

```text
Daily email summarizer acts for Alice's Gmail
```

AIB should store Alice's delegated grant and Google OAuth session, then return a Google access token to the autonomous Agent when the grant and session are valid.

---

## Context

[ADR-KAOS-001](./ADR-KAOS-001-identity-model-and-source-of-truth.md) establishes that KAOS owns resource identity and topology, while AIB can mirror KAOS identities through `external_id`.

[ADR-KAOS-003](./ADR-KAOS-003-user-request-context-propagation.md) establishes a propagation-only SDK that carries the user subject and the agent actor across hops.

[ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md) establishes gateway-centric enforcement, LiteLLM as the ModelAPI internals surface, and sidecars as deferred.

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

- AIB can represent KAOS Agents through `ExternalID`, using the identity format from ADR-KAOS-001.
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
- Per ADR-KAOS-002, AIB ExtProc token exchange runs at the gateway.

---

## Annex: Alternatives considered

### Option A: AIB only as delegated OAuth/token broker

AIB would own user delegated grants, third-party OAuth sessions, consent, token vault, and token exchange, but not KAOS resource grants.

Rejected as too narrow.

KAOS CRDs already define Agent-to-MCPServer, Agent-to-ModelAPI, and Agent-to-Agent requested access edges. These are natural KAOS logical resource grants. Keeping them outside AIB would either push definitions into dynamic SDK code or require a separate authorization store.

However, current AIB does not yet expose this as a first-class model, so implementation may need an interim PermissionSet/synthetic-service encoding before the proper resource-grant model exists.

### Option B: AIB as broad all-purpose policy platform

AIB would own all authorization, policy language, approval workflows, ModelAPI policies, MCP tool/argument rules, runtime token issuance, and token exchange.

Rejected as the baseline target.

This overextends AIB beyond its current implementation and risks duplicating Keycloak, OPA, LiteLLM, and Gateway responsibilities. It also forces AIB to understand detailed MCP tool schemas, ModelAPI budgets, and Gateway route mechanics too early.

### Option C: Keycloak/OPA as the KAOS resource-grant source of truth

Keycloak Authorization Services or OPA could model KAOS resources, scopes, permissions, and policies.

Not selected as the default.

This may be useful for enterprise deployments, but the target benefits from keeping KAOS-native logical resource grants close to AIB, because AIB already understands agents, grants, token exchange, and delegated access. Keycloak remains the user identity source; OPA/Keycloak AuthZ can be handled as optional advanced integration under ADR-KAOS-005.

---

## Consequences

### Positive

- Keeps permission definitions config-as-code through KAOS CRDs and AIB-synced records, not hidden in SDK code.
- Makes CRD wiring meaningful as requested access without making it an automatic grant.
- Gives AIB a coherent authorization role for KAOS logical resource grants and user-delegated third-party grants.
- Keeps Keycloak focused on human identity/SSO.
- Keeps LiteLLM focused on ModelAPI model access, budgets, and rate limits.
- Keeps MCP tool/argument-level authorization optional until KAOS models those concepts explicitly.

### Negative

- AIB needs a resource-grant concept beyond its current user grant and PermissionSet model.
- Until that exists, any PermissionSet-based resource-grant encoding is a temporary workaround and must be documented as such.
- AIB also needs a request/approval lifecycle for KAOS resource grants if requested CRD access edges are to be reviewed before approval.
- Logical identity validation does not cryptographically prove workload identity.
- Gateway/NetworkPolicy bypass prevention is part of the required secured target.
- ModelAPI root access can be AIB-managed, but detailed model/budget enforcement remains in LiteLLM.

### Risks

- If requested edges are mistaken for approved grants, deployments could become over-permissive. Documentation and API naming must distinguish requested vs approved.
- Until future workload-identity hardening (mTLS/SPIFFE) is added, malicious in-cluster workloads could spoof logical identity headers/context in weakly isolated clusters.
- AIB resource grants and AIB user-delegated grants must be modeled distinctly to avoid mixing platform access with user OAuth consent.

---

## Final decision

1. AIB is the authorization, agent-identity, and delegated-token broker for KAOS.
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
12. ModelAPI root resource access is enforced at the gateway via AIB; ModelAPI internals remain LiteLLM-owned.
13. AIB issues per-agent identity tokens via `client_credentials` (local/hybrid mode) and returns delegated third-party tokens via token exchange. Keycloak/Dex/OIDC remain human authentication only.
14. Resource-access decisions key on the calling agent's own AIB-issued identity (the actor), never on `subject_token.azp`; the user principal is used for user-delegated grants.
15. Enforcement is gateway-centric: AIB is invoked through the gateway's `ext_authz` and `ext_proc`; per-runtime SDK calls are only for custom off-gateway servers.
16. AIB does not replace Keycloak/Dex/OIDC for human authentication.
17. Kubernetes ServiceAccount/SPIFFE pod-level workload binding remains deferred future hardening (ADR-KAOS-001).
18. OPA/Rego and Keycloak Authorization Services remain optional advanced integrations (ADR-KAOS-005); OPA is a drop-in `ext_authz` backend.
