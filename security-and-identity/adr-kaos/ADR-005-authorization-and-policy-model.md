# ADR-005: Authorization and policy model

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

Adopt **Option A: Simple AIB grant tables for the target model**.

Keep authorization data-first: explicit requested edges, explicit approved resource grants, and explicit user delegated grants. Do not add a generalized external-PDP envelope, policy plugin boundary, or policy abstraction layer by default just to prepare for OPA/Rego or Keycloak Authorization Services.

The enforcement point for KAOS resource authorization is the gateway `ext_authz` call. AIB evaluates the runtime decision through that call: "does an approved grant exist for this caller, target, and action?" The decision is keyed on the **ACTOR**: the calling agent's own AIB-issued identity carried in `x-agent-authorization: Bearer`. The user principal carried in `Authorization: Bearer` is the **SUBJECT** and is used for user-delegated third-party grants, not for attributing resource-to-resource access. Autonomous runs are actor-only.

The SDK propagates verified identity and context so the gateway can enforce end-to-end. It does not enforce KAOS resource authorization.

Use:

| Authorization domain | Target model |
|---|---|
| Agent -> MCPServer | AIB resource grant enforced by gateway `ext_authz` |
| Agent -> ModelAPI root access | AIB resource grant enforced by gateway `ext_authz` |
| Agent -> Agent delegation | AIB resource grant enforced by gateway `ext_authz` |
| User -> Agent third-party delegation | AIB UserGrant + PermissionSet, evaluated for delegated token availability |
| MCP tool-level auth | Optional future policy; CRD/schema model required |
| MCP argument-level auth | Optional future policy; policy/approval model required |
| ModelAPI model allowlist/budget/rate limit | LiteLLM |
| Gateway route auth | Gateway `ext_authz` enforces it using an AIB resource grant |
| Human login/groups/roles | Keycloak/Dex/OIDC |
| Complex enterprise policy | Optional future OPA/Rego or Keycloak AuthZ integration; OPA can be a drop-in `ext_authz` backend via opa-envoy |

Policy should be represented as data first:

```text
requested edge:
  source: kaos://agent/researcher
  target: kaos://mcpserver/github
  action: call

approved resource grant:
  source: kaos://agent/researcher
  target: kaos://mcpserver/github
  action: call
  status: approved

delegated user grant:
  principal: keycloak://kaos/alice
  agent: kaos://agent/researcher
  permission_set: github-issues-reader
  valid_until: ...
```

Use CEL only for:

- claim extraction,
- token claim shaping,
- simple built-in checks,
- implementation internals where AIB already uses it.

Do not make OPA/Rego or Keycloak Authorization Services mandatory. Treat them as optional future enterprise PDP integrations to reconsider only when simple grants are no longer enough. OPA is specifically a drop-in Envoy `ext_authz` backend through opa-envoy when it is fed equivalent policy and data.

Per-resource security configuration is `spec.security.id` only. Authentication, authorization, and backend selection are operator-wide integration concerns.

### Backend-neutral authorization integration

The authorization integration is backend-neutral: it uses the standard Envoy `ext_authz` gRPC contract (`envoy.service.auth.v3.Authorization/Check`) and neutral `kaos.resource` / `kaos.action` `context_extensions`. AIB is the default backend. OPA is swappable as a drop-in backend via opa-envoy with no Envoy or KAOS configuration change, provided it has equivalent policy and data. Keycloak-as-authz would need an adapter because it is the IdP, not an `ext_authz` backend.

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) defines KAOS logical identities.

[ADR-003](./ADR-003-user-request-context-propagation.md) defines request context propagation.

[ADR-002](./ADR-002-enforcement-topology.md) defines gateway-centric enforcement: `jwt_authn`, `ext_authz` -> AIB, `ext_proc` -> AIB token exchange, and NetworkPolicy bypass prevention.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) defines AIB as the authorization and delegated-token broker for KAOS, with:

- AIB-owned KAOS logical resource grants,
- AIB-owned user-delegated third-party grants,
- KAOS CRD references as requested access edges,
- no-permission-by-default semantics,
- AIB PermissionSets primarily representing third-party service scopes,
- ModelAPI internals remaining LiteLLM-owned,
- OPA/Rego and Keycloak Authorization Services treated as optional future enterprise integrations under this decision.

[ADR-011](./ADR-011-gateway-api-resource-boundary-enforcement.md) defines the gateway enforcement pipeline that calls AIB for resource authorization and token exchange.

This ADR decides how authorization definitions, policy rules, and approval semantics should be represented for the target architecture.

---

## Source facts

### KAOS CRDs define topology, not explicit security policy

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

Current relevant fields:

- Agent `spec.modelAPI`
- Agent `spec.mcpServers`
- Agent `spec.agentNetwork.access`
- Agent `spec.config.autonomous`
- Agent `spec.config.taskConfig`
- MCPServer `spec.runtime`
- MCPServer `spec.serviceAccountName`
- ModelAPI `spec.proxyConfig.models`
- ModelAPI `spec.hostedConfig.model`
- all three resource types expose `spec.gatewayRoute`, `spec.container`, and `spec.podSpec`

Implication:

- KAOS currently models root resource relationships, not fine-grained authorization rules.
- Agent-to-MCPServer, Agent-to-ModelAPI, and Agent-to-Agent references can be treated as requested access edges.
- KAOS does not currently model MCP tool names, MCP arguments, approval conditions, resource grant status, or policy expressions.

### AIB PermissionSets are service-scope bundles

Source file:

- `agentic-identity-broker/internal/domain/storage/permission_set.go`

AIB PermissionSets bind third-party service IDs to OAuth2 scopes and requirement types.

Implication:

- They are a good fit for third-party delegated OAuth scopes.
- They are not a good long-term model for all KAOS resource grants, MCP tool arguments, ModelAPI budgets, or Gateway routes.
- ADR-004 permits a temporary synthetic-service/custom-scope workaround for resource grants, but the target is a first-class resource-grant model.

### AIB UserGrants are principal-to-agent delegated grants

Source file:

- `agentic-identity-broker/internal/domain/storage/user_grant.go`

AIB UserGrant binds:

```text
principal + agent_id + granted_permission_sets + optional valid_until
```

Implication:

- This is the right model for user-delegated third-party grants.
- It should not be overloaded as the long-term model for platform/resource grants.

### AIB CEL is used for bounded claim extraction and request checks

Source files:

- `agentic-identity-broker/internal/domain/tokenexchange/cel_evaluator.go`
- `agentic-identity-broker/internal/domain/jwtauth/cel_evaluator.go`
- `agentic-identity-broker/internal/domain/oauth2server/token_claims_cel.go`

Current CEL usage:

- Extract principal from JWT claims.
- Extract agent ID from subject token claims.
- Authorize privileged token-exchange client.
- Extract optional identity/profile attributes.
- Add custom OAuth2 token claims.

Implementation traits:

- CEL expressions are compiled at startup.
- Evaluation has a timeout.
- Expressions operate on bounded request/claims maps.

Implication:

- CEL is a good fit for small, local, deterministic transformations and simple checks.
- CEL is not currently a full policy administration model for KAOS resources.
- CEL can be part of AIB's implementation, but should not be treated as the user-facing policy language unless explicitly designed.

### OPA/Rego is a general policy engine

External reference:

- Open Policy Agent policy language and HTTP API authorization documentation.

Relevant facts:

- OPA evaluates policies written in Rego over structured input data.
- It is suitable for fine-grained, context-aware decisions over API requests, infrastructure, and configuration data.
- OPA can be integrated with Envoy through opa-envoy as an `ext_authz` backend.
- Rego is more expressive than simple grant tables, but introduces an additional policy language, runtime, bundle/deployment model, and operational surface.

Implication:

- OPA/Rego is a credible optional future enterprise PDP for complex policies.
- It can replace AIB as the `ext_authz` decision backend without changing Envoy or KAOS configuration if it receives equivalent `kaos.resource` / `kaos.action` context and grant data.
- It is overkill for the target KAOS grant model when the needed decision is requested edge plus approved grant.

### Keycloak Authorization Services can be a PDP/PAP

External reference:

- Keycloak Authorization Services documentation.

Relevant facts:

- Keycloak supports resource, scope, permission, and policy management.
- It can act as a centralized Policy Administration Point and Policy Decision Point.
- It supports RBAC, ABAC, user-based, context-based, rule-based, and time-based policies.
- It is well aligned with human identity and enterprise SSO.

Implication:

- Keycloak Authorization Services could model KAOS resources and policies in enterprise deployments.
- It would duplicate or displace part of AIB's KAOS-native resource-grant role.
- It remains better suited as human identity/SSO by default unless the architecture intentionally adopts Keycloak as the central PDP through an adapter.

---

## Decision scope

This ADR fixes the following scope:

1. What is the minimum target authorization data model?
2. Which permissions are declared in KAOS CRDs as requested access?
3. Which permissions are approved and stored in AIB?
4. Whether policy logic is simple grant lookup, CEL, OPA/Rego, Keycloak AuthZ, or a combination.
5. How admin/platform authorization combines with user-delegated grants.
6. How autonomous grants are represented.
7. What remains optional or future.

---

## Annex: Alternatives considered

### Option A: Simple AIB grant tables for the target model

This option treats authorization as explicit data rather than as a general-purpose policy language. KAOS CRDs say what a resource is wired to use. AIB stores which of those requested edges are approved. Runtime enforcement then asks a simple question through gateway `ext_authz`: "does an approved grant exist for this caller, target, and action?"

The model has two distinct grant families:

- KAOS resource grants:

  ```text
  caller -> target -> action -> status
  ```

- user delegated grants:

  ```text
  principal -> agent -> permission_set -> valid_until
  ```

Policy is primarily grant lookup, expiry/status checks, and simple metadata checks.

In practice, an Agent that references an MCPServer in its CRD would not automatically be allowed to call it. The CRD reference becomes a requested edge. AIB needs a matching approved resource grant before the gateway allows the call.

Example:

```text
CRD requested edge:
  kaos://agent/researcher -> kaos://mcpserver/github, action=call

AIB approved resource grant:
  kaos://agent/researcher -> kaos://mcpserver/github, action=call, status=approved

Runtime decision at gateway ext_authz:
  allow if requested edge exists and approved grant exists for actor -> target/action
```

For delegated third-party access, the resource grant is not enough. If the GitHub MCP needs to call GitHub as Alice, AIB must also have a user-delegated grant:

```text
resource grant:
  kaos://agent/researcher -> kaos://mcpserver/github, action=call

user delegated grant:
  keycloak://kaos/alice -> kaos://agent/researcher -> github-issues-reader

decision:
  allow MCP call only if the resource grant exists;
  provide GitHub token only if the user delegated grant also exists
```

This option is intentionally simple: it gives KAOS a clear boundary between requested topology, approved resource access, and delegated user consent.

Pros:

- Simple to explain to operators and users.
- Fits ADR-001 through ADR-004.
- Keeps policy definitions config-as-code through KAOS CRDs and AIB records.
- Avoids new policy-language dependency.
- Easy to audit because the grant is a concrete row/record.
- Matches no-permission-by-default semantics.
- Aligns directly with gateway `ext_authz` decisions.

Cons:

- Less expressive than OPA/Keycloak AuthZ.
- Complex context-aware policies need optional future extension.
- AIB needs first-class resource-grant and approval models.
- Does not solve MCP tool/argument policy until KAOS models tools and tool permissions explicitly.
- Requires a clear admin approval/bootstrap path, otherwise all requested edges remain denied.

Best fit:

- The target model.
- Environments where explicit allowlists are preferable to writing policy code.

### Option B: AIB CEL as the policy language

This option would make AIB's existing CEL expression support the main policy authoring mechanism. Instead of asking only whether a grant record exists, AIB would evaluate expressions over request context, token claims, resource metadata, time, labels, or other attributes.

Example policy shape:

```text
allow if:
  request.principal.groups contains "engineering"
  and request.agent.namespace == "prod"
  and request.target.kind == "mcpserver"
  and request.action == "call"
```

This is attractive because AIB already uses CEL in several bounded places: extracting principals from JWTs, extracting agent IDs from tokens, authorizing privileged token-exchange clients, and shaping token claims. CEL is deterministic and lighter than introducing OPA.

However, using CEL internally for claim extraction is different from exposing CEL as the primary user-facing policy model. Once CEL becomes policy, KAOS/AIB need policy storage, versioning, review, testing, migration, audit, debugging, error reporting, and a safe data model for what expressions are allowed to inspect.

Pros:

- AIB already uses CEL in bounded flows.
- Deterministic and lightweight.
- No separate OPA runtime.
- Can express simple contextual rules without adopting Rego.
- Could be useful inside AIB for implementation-level checks.

Cons:

- Current CEL usage is not a full policy management system.
- Complex policies become hard to govern and audit if stored as arbitrary expressions.
- Less familiar as an enterprise authorization language than Rego or Keycloak AuthZ.
- Requires a policy lifecycle and administrator UX that AIB does not currently provide.
- Risks mixing low-level token/claim transformation with high-level KAOS authorization.

Best fit:

- Internal claim extraction and simple checks, not the primary user-facing policy language.
- Possible future implementation detail behind grant-table decisions.

### Option C: OPA/Rego as policy decision point

This option introduces OPA as the policy decision point. In the gateway-centric architecture, OPA can be a drop-in `ext_authz` backend via opa-envoy. AIB could still store grants and delegated tokens, but OPA would evaluate richer policy logic over equivalent input.

Example input:

```json
{
  "principal": "keycloak://kaos/alice",
  "actor": "kaos://agent/researcher",
  "target": "kaos://mcpserver/github",
  "action": "call",
  "requested_edge_exists": true,
  "resource_grant_status": "approved",
  "namespace": "prod",
  "time": "2026-06-20T04:24:50Z"
}
```

Example decision:

```text
allow if:
  resource_grant_status == "approved"
  and namespace == "prod"
  and principal is in an approved group
  and current time is within an allowed window
```

OPA is the strongest option if KAOS needs enterprise-style policy: group/role rules, label-based rules, environment-based constraints, time windows, organization-specific exceptions, separation of duties, or policy bundles managed by a central platform team.

The tradeoff is that OPA changes the architecture from "AIB owns concrete grants" to "AIB owns grants and OPA owns final policy logic" or "OPA owns final authorization and AIB is an input provider." That may be correct for enterprise deployments, but it is more than is needed to decide basic Agent -> MCPServer, Agent -> ModelAPI, and Agent -> Agent access in the target model.

Pros:

- Strong general-purpose policy model.
- Good for complex enterprise policies.
- Standard PDP pattern.
- Works across services and languages.
- Clear upgrade path if simple grants become insufficient.
- Can evaluate KAOS, AIB, IdP, and runtime context together.
- Can use the same Envoy `ext_authz` contract as AIB.

Cons:

- Adds operational dependency.
- Requires policy bundle lifecycle.
- More complex than needed for simple grant checks.
- Requires clear integration with AIB grants and KAOS CRDs.
- Adds another failure mode to every protected call path.
- Makes debugging harder unless the input and decision trace are exposed well.

Best fit:

- Optional future enterprise policy.
- Deployments that already standardize on OPA for platform authorization.

### Option D: Keycloak Authorization Services as PDP/PAP

This option uses Keycloak not only for human login/SSO, but also as the central authorization system. KAOS resources would be represented as Keycloak resources/scopes. Keycloak policies and permissions would decide whether a user, agent, or client can access a target.

Example mapping:

```text
KAOS resource:
  kaos://mcpserver/github

Keycloak resource:
  mcpserver:github

Keycloak scope:
  call

Keycloak permission:
  allow agent researcher, or users in group platform-admins, to call mcpserver:github
```

This is appealing in enterprises where Keycloak is already the policy administration point. It keeps user identity, groups, roles, and authorization in one system.

The problem is that KAOS resources are dynamic Kubernetes resources. If Keycloak owns KAOS resource authorization, KAOS must sync Agents, MCPServers, ModelAPIs, scopes, permissions, and deletions into Keycloak. This overlaps with ADR-004, which already chose AIB as the KAOS resource-grant authority and delegated-token broker. It also does not replace AIB's token vault and third-party delegated session model.

This option is therefore a different product boundary. It may be useful as an optional future enterprise integration, but it should not be the default architecture unless KAOS intentionally chooses Keycloak as its central authorization platform through an adapter.

Pros:

- Centralized enterprise identity and authorization.
- Built-in resource/scope/permission/policy model.
- Integrates with user identity, groups, and roles.
- Familiar to organizations already running Keycloak.
- Can support rich admin-managed authorization policies.

Cons:

- Couples KAOS resource authorization to Keycloak.
- Duplicates AIB's selected role as KAOS resource-grant authority.
- Requires syncing dynamic KAOS CRD resources into Keycloak.
- Does not replace AIB token vault/delegated third-party session behavior.
- Makes non-Keycloak deployments harder if treated as mandatory.
- Risks making KAOS security architecture depend on Keycloak-specific concepts instead of portable KAOS logical identities.

Best fit:

- Optional future enterprise integration.
- Deployments that explicitly want Keycloak as the central PDP/PAP.

### Option E: Grant tables plus optional external PDP compatibility

This option chooses Option A but shapes the data and request context so that OPA or Keycloak can be integrated later without rewriting the grant model.

In this model, the default decision remains:

```text
allow if requested edge exists and approved AIB grant exists
```

The authorization input is shaped in a backend-neutral way:

```text
principal
actor identity
target identity
action
requested edge metadata
approved grant metadata
user delegated grant metadata, if relevant
runtime/request context
```

A future external PDP could evaluate that same input:

```text
allow if:
  AIB grant exists
  and OPA policy allows the request
```

or:

```text
allow if:
  AIB grant exists
  and Keycloak AuthZ allows the request
```

This is not a separate enforcement model. It is a compatibility stance: keep the default simple, but avoid designing grants and request context in a way that blocks optional OPA/Keycloak integration.

Pros:

- Preserves the simplicity of Option A.
- Keeps a migration path to OPA/Rego or Keycloak AuthZ.
- Aligns gateway input with optional policy engines.
- Avoids premature commitment to a specific external PDP.

Cons:

- Requires discipline not to overbuild hooks before they are needed.
- The implementation must define stable authorization input shapes.
- Some PDP-specific features may still require schema changes.

Best fit:

- Future refinement after Option A is proven.
- Backend-neutral `ext_authz` inputs using `kaos.resource` and `kaos.action`.

---

## Decision summary

1. KAOS authorization is data-first and grant-table-based by default.
2. KAOS CRD references define requested access edges only.
3. AIB owns approved KAOS resource grants.
4. AIB owns user-delegated third-party grants through UserGrants and PermissionSets.
5. Runtime KAOS resource authorization is enforced at the gateway through `ext_authz`, not in the SDK.
6. AIB evaluates whether an approved grant exists for actor -> target/action; the actor is the calling agent's own AIB-issued identity.
7. The user principal is used for user-delegated third-party grants and autonomous runs are actor-only.
8. Gateway authorization input uses neutral `kaos.resource` and `kaos.action` context extensions.
9. AIB CEL remains internal bounded expression support, not the primary policy authoring language.
10. OPA/Rego is an optional future enterprise PDP; OPA can be a drop-in `ext_authz` backend via opa-envoy.
11. Keycloak Authorization Services is an optional future enterprise integration; Keycloak/Dex/OIDC remains human identity/SSO by default.
12. ModelAPI internal model/budget/rate authorization remains LiteLLM-owned.
13. MCP tool/argument-level policy remains optional until KAOS models tool permissions explicitly.
14. Optional external PDP compatibility must not broaden the per-resource configuration surface beyond `spec.security.id`.
