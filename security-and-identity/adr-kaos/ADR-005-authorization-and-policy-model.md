# ADR-005: Authorization and policy model

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

Adopt **Option A: Simple AIB grant tables for the baseline profile**.

Keep the baseline implementation deliberately simple: explicit requested edges, explicit approved resource grants, and explicit user delegated grants. Do not add a generalized external-PDP envelope, policy plugin boundary, or policy abstraction layer to the baseline profile just to prepare for OPA/Rego or Keycloak Authorization Services.

Use the deployment-profile vocabulary consistently: the **baseline profile** uses SDK-native enforcement with external TLS and direct ClusterIP access; the **Gateway resource-boundary profile** adds Gateway routing, Envoy `ext_authz`, AIB ExtProc token exchange, and NetworkPolicy bypass prevention; the **advanced/hardened profile** adds optional mTLS/SPIFFE/service mesh/workload identity hardening.

Use:

| Authorization domain | Target model |
|---|---|
| Agent -> MCPServer | AIB resource grant |
| Agent -> ModelAPI root access | AIB resource grant |
| Agent -> Agent delegation | AIB resource grant |
| User -> Agent third-party delegation | AIB UserGrant + PermissionSet |
| MCP tool-level auth | Optional advanced policy; CRD/schema model required |
| MCP argument-level auth | Optional advanced policy; policy/approval model required |
| ModelAPI model allowlist/budget/rate limit | LiteLLM |
| Gateway route auth | Gateway resource-boundary profile + AIB resource grant |
| Human login/groups/roles | Keycloak/Dex/OIDC |
| Complex enterprise policy | Optional advanced OPA/Rego or Keycloak AuthZ integration |

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

Do not make OPA/Rego or Keycloak Authorization Services mandatory in the baseline profile. Treat them as optional advanced integrations to reconsider only when simple grants are no longer enough.

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) defines KAOS logical identities.

[ADR-003](./ADR-003-user-request-context-propagation.md) defines SDK-first request context propagation.

[ADR-002](./ADR-002-enforcement-topology.md) defines SDK-native baseline enforcement and the Gateway resource-boundary profile.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) defines AIB as the authorization and delegated-token broker for KAOS, with:

- AIB-owned KAOS logical resource grants,
- AIB-owned user-delegated third-party grants,
- KAOS CRD references as requested access edges,
- no-permission-by-default semantics,
- AIB PermissionSets primarily representing third-party service scopes,
- ModelAPI internals remaining LiteLLM-owned,
- OPA/Rego and Keycloak Authorization Services treated as optional advanced integrations under this decision.

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
- CEL can be part of AIB's implementation, but should not be treated as the user-facing policy language for the baseline profile unless explicitly designed.

### OPA/Rego is a general policy engine

External reference:

- Open Policy Agent policy language and HTTP API authorization documentation.

Relevant facts:

- OPA evaluates policies written in Rego over structured input data.
- It is suitable for fine-grained, context-aware decisions over API requests, infrastructure, and configuration data.
- OPA can be integrated by calling its REST API or embedding SDKs.
- Rego is more expressive than simple grant tables, but introduces an additional policy language, runtime, bundle/deployment model, and operational surface.

Implication:

- OPA/Rego is a credible optional advanced PDP for complex enterprise policies.
- It is likely overkill for the baseline KAOS policy model if that profile only needs requested edges plus approved grants.

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
- It remains better suited as human identity/SSO for the baseline profile unless the architecture intentionally adopts Keycloak as the central PDP.

---

## Decision scope

This ADR fixes the following scope:

1. What is the minimum baseline authorization data model?
2. Which permissions are declared in KAOS CRDs as requested access?
3. Which permissions are approved and stored in AIB?
4. Whether policy logic is simple grant lookup, CEL, OPA/Rego, Keycloak AuthZ, or a combination.
5. How admin/platform authorization combines with user-delegated grants.
6. How autonomous grants are represented.
7. What remains optional or advanced.

---

## Annex: Alternatives considered

### Option A: Simple AIB grant tables for the baseline profile

This option treats authorization as explicit data rather than as a general-purpose policy language. KAOS CRDs say what a resource is wired to use. AIB stores which of those requested edges are approved. Runtime enforcement then asks a simple question: "does an approved grant exist for this caller, target, and action?"

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

In practice, an Agent that references an MCPServer in its CRD would not automatically be allowed to call it. The CRD reference becomes a requested edge. AIB would need a matching approved resource grant before the SDK/Gateway/runtime lets the call proceed.

Example:

```text
CRD requested edge:
  kaos://agent/researcher -> kaos://mcpserver/github, action=call

AIB approved resource grant:
  kaos://agent/researcher -> kaos://mcpserver/github, action=call, status=approved

Runtime decision:
  allow if requested edge exists and approved grant exists
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

This option is intentionally "boring": it does not try to answer every advanced authorization question. It gives KAOS a clear baseline boundary between requested topology, approved resource access, and delegated user consent.

Pros:

- Simple to explain to operators and users.
- Fits ADR-001 through ADR-004.
- Keeps policy definitions config-as-code through KAOS CRDs and AIB records.
- Avoids new policy-language dependency.
- Easy to audit because the grant is a concrete row/record.
- Matches no-permission-by-default semantics.

Cons:

- Less expressive than OPA/Keycloak AuthZ.
- Complex context-aware policies need optional advanced extension.
- AIB needs first-class resource-grant and approval models.
- Does not solve MCP tool/argument policy until KAOS models tools and tool permissions explicitly.
- Requires a clear admin approval/bootstrap path, otherwise all requested edges remain denied.

Best fit:

- The baseline profile.
- The baseline "secure but understandable" model.
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

However, using CEL internally for claim extraction is different from exposing CEL as the primary user-facing policy model. Once CEL becomes policy, KAOS/AIB need policy storage, versioning, review, testing, migration, audit, debugging, error reporting, and a safe data model for what expressions are allowed to inspect. That is a much larger product surface than the current AIB implementation.

This option can also blur config-as-code boundaries. If access rules live inside dynamic CEL expressions, the operator can no longer understand authorization just by comparing KAOS requested edges and AIB approved grants.

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

- Internal claim extraction and simple checks, not the primary baseline user-facing policy language.
- Possible advanced implementation detail behind grant-table decisions.

### Option C: OPA/Rego as policy decision point

This option introduces OPA as the policy decision point. KAOS or AIB would assemble structured authorization input and call OPA for an allow/deny decision. AIB could still store grants and delegated tokens, but OPA would evaluate richer policy logic.

Example input:

```json
{
  "principal": "keycloak://kaos/alice",
  "agent": "kaos://agent/researcher",
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

The tradeoff is that OPA changes the architecture from "AIB owns concrete grants" to "AIB owns grants and OPA owns final policy logic" or "OPA owns final authorization and AIB is an input provider." That may be correct for advanced deployments, but it is more than is needed to decide basic Agent -> MCPServer, Agent -> ModelAPI, and Agent -> Agent access in the baseline profile.

Pros:

- Strong general-purpose policy model.
- Good for complex enterprise policies.
- Standard PDP pattern.
- Works across services and languages.
- Clear upgrade path if simple grants become insufficient.
- Can evaluate KAOS, AIB, IdP, and runtime context together.

Cons:

- Adds operational dependency.
- Requires policy bundle lifecycle.
- More complex than needed for baseline grant checks.
- Requires clear integration with AIB grants and KAOS CRDs.
- Requires deciding whether KAOS, AIB, Gateway, or each runtime calls OPA.
- Adds another failure mode to every protected call path.
- Makes debugging harder unless the input and decision trace are exposed well.

Best fit:

- Advanced/enterprise policy layer.
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

This option is therefore not "wrong"; it is a different product boundary. It would make Keycloak the enterprise PDP/PAP and make AIB more narrowly responsible for token brokerage. That may be useful as an optional integration, but it should not be the default baseline architecture unless KAOS intentionally chooses Keycloak as its central authorization platform.

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

- Optional enterprise integration, not the baseline default.
- Deployments that explicitly want Keycloak as the central PDP/PAP.

### Option E: Hybrid grant tables plus optional external PDP hooks

This option chooses Option A for the baseline profile but designs the data and request context so that OPA or Keycloak can be enabled as optional advanced integrations without rewriting the whole security model.

In this model, the baseline decision remains:

```text
allow if requested edge exists and approved AIB grant exists
```

But the authorization input is shaped in a profile-compatible way:

```text
principal
agent identity
target identity
action
requested edge metadata
approved grant metadata
user delegated grant metadata, if relevant
runtime/request context
```

In an advanced profile, an external PDP could evaluate that same input:

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

This is not a separate enforcement model for the baseline profile. It is a compatibility stance: keep the baseline simple, but avoid designing grants and request context in a way that blocks optional OPA/Keycloak integration.

Pros:

- Preserves the simplicity of Option A.
- Keeps a migration path to OPA/Rego or Keycloak AuthZ.
- Aligns SDK and Gateway input models with optional policy engines.
- Avoids premature commitment to a specific external PDP.

Cons:

- Requires discipline not to overbuild hooks before they are needed.
- The baseline implementation must define stable authorization input shapes.
- Some advanced PDP-specific features may still require schema changes.

Best fit:

- Advanced refinement after the Option A baseline is proven. This should not be selected as the baseline recommendation if it causes the SDK/API boundary to become broader than the current grant checks require.

---

## Decision summary

1. KAOS baseline authorization is data-first and grant-table-based.
2. KAOS CRD references define requested access edges only.
3. AIB owns approved KAOS resource grants.
4. AIB owns user-delegated third-party grants through UserGrants and PermissionSets.
5. Admin/platform grants and user-delegated grants are both required when both apply.
6. AIB CEL remains internal bounded expression support, not the primary policy authoring language.
7. OPA/Rego is an optional advanced policy integration.
8. Keycloak Authorization Services is an optional advanced integration; Keycloak/Dex/OIDC remains human identity/SSO in the baseline profile.
9. ModelAPI internal model/budget/rate authorization remains LiteLLM-owned.
10. MCP tool/argument-level policy remains optional until KAOS models tool permissions explicitly.
11. Autonomous run-scoped grants belong to the approval/consent execution model.
12. Optional external PDP compatibility must not broaden the baseline SDK/API surface beyond what direct grant checks require.
