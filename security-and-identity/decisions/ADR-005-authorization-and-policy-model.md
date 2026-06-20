# ADR-005: Authorization and policy model

**Status**: Proposed. Requires host decisions before acceptance.
**Date**: 2026-06-20

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) defines KAOS logical identities.

[ADR-002](./ADR-002-user-request-context-propagation.md) defines SDK-first request context propagation.

[ADR-003](./ADR-003-enforcement-topology.md) defines SDK-first enforcement for 1.0 and GatewayAPI as a 1.1 resource-boundary extension.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) defines AIB as the authorization and delegated-token broker for KAOS 1.0, with:

- AIB-owned KAOS logical resource grants,
- AIB-owned user-delegated third-party grants,
- KAOS CRD references as requested access edges,
- no-permission-by-default semantics,
- AIB PermissionSets primarily representing third-party service scopes,
- ModelAPI internals remaining LiteLLM-owned,
- OPA/Rego and Keycloak Authorization Services deferred to this decision.

This ADR decides how authorization definitions, policy rules, and approval semantics should be represented for the 1.0 target.

The core question is:

```text
What is the policy model for KAOS 1.0, and when should KAOS use simple grants, AIB CEL, OPA/Rego, or Keycloak Authorization Services?
```

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
- CEL can be part of AIB's implementation, but should not be treated as the user-facing policy language for 1.0 unless explicitly designed.

### OPA/Rego is a general policy engine

External reference:

- Open Policy Agent policy language and HTTP API authorization documentation.

Relevant facts:

- OPA evaluates policies written in Rego over structured input data.
- It is suitable for fine-grained, context-aware decisions over API requests, infrastructure, and configuration data.
- OPA can be integrated by calling its REST API or embedding SDKs.
- Rego is more expressive than simple grant tables, but introduces an additional policy language, runtime, bundle/deployment model, and operational surface.

Implication:

- OPA/Rego is a credible future PDP for complex enterprise policies.
- It is likely overkill for the first KAOS policy model if 1.0 only needs requested edges plus approved grants.

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
- It remains better suited as human identity/SSO for 1.0 unless the architecture intentionally adopts Keycloak as the central PDP.

---

## Decision problem

KAOS needs to decide:

1. What is the minimum 1.0 authorization data model?
2. Which permissions are declared in KAOS CRDs as requested access?
3. Which permissions are approved and stored in AIB?
4. Whether policy logic is simple grant lookup, CEL, OPA/Rego, Keycloak AuthZ, or a combination.
5. How admin/platform authorization combines with user-delegated grants.
6. How autonomous grants are represented.
7. What is explicitly deferred.

---

## Options

### Option A: Simple AIB grant tables for 1.0

Use explicit AIB records for:

- KAOS resource grants:

  ```text
  caller -> target -> action -> status
  ```

- user delegated grants:

  ```text
  principal -> agent -> permission_set -> valid_until
  ```

Policy is primarily grant lookup, expiry/status checks, and simple metadata checks.

Pros:

- Simple.
- Fits current decisions.
- Keeps policy definitions config-as-code through KAOS CRDs and AIB records.
- Avoids new policy-language dependency.
- Easy to audit and explain.

Cons:

- Less expressive than OPA/Keycloak AuthZ.
- Complex context-aware policies need later extension.
- AIB needs first-class resource-grant and approval models.

Best fit:

- KAOS 1.0.

### Option B: AIB CEL as the policy language

Use AIB CEL expressions to decide resource grants, delegated grants, and contextual authorization.

Pros:

- AIB already uses CEL in bounded flows.
- Deterministic and lightweight.
- No separate OPA runtime.

Cons:

- Current CEL usage is not a full policy management system.
- Complex policies become hard to govern and audit if stored as arbitrary expressions.
- Less familiar as an enterprise authorization language than Rego or Keycloak AuthZ.

Best fit:

- Internal claim extraction and simple checks, not primary 1.0 user-facing policy language.

### Option C: OPA/Rego as policy decision point

Represent KAOS authorization input as structured JSON and ask OPA for decisions.

Pros:

- Strong general-purpose policy model.
- Good for complex enterprise policies.
- Standard PDP pattern.
- Works across services and languages.

Cons:

- Adds operational dependency.
- Requires policy bundle lifecycle.
- More complex than needed for initial grant checks.
- Requires clear integration with AIB grants and KAOS CRDs.

Best fit:

- Future advanced/enterprise policy layer.

### Option D: Keycloak Authorization Services as PDP/PAP

Model KAOS resources/scopes/policies in Keycloak Authorization Services.

Pros:

- Centralized enterprise identity and authorization.
- Built-in resource/scope/permission/policy model.
- Integrates with user identity, groups, and roles.

Cons:

- Couples KAOS resource authorization to Keycloak.
- Duplicates AIB's selected role as KAOS resource-grant authority.
- Requires syncing dynamic KAOS CRD resources into Keycloak.
- Does not replace AIB token vault/delegated third-party session behavior.

Best fit:

- Optional enterprise integration, not default 1.0.

---

## Provisional recommendation

Adopt **Option A: Simple AIB grant tables for 1.0**.

Use:

| Authorization domain | 1.0 model |
|---|---|
| Agent -> MCPServer | AIB resource grant |
| Agent -> ModelAPI root access | AIB resource grant |
| Agent -> Agent delegation | AIB resource grant |
| User -> Agent third-party delegation | AIB UserGrant + PermissionSet |
| MCP tool-level auth | Deferred; future CRD/schema model required |
| MCP argument-level auth | Deferred; future policy/approval model required |
| ModelAPI model allowlist/budget/rate limit | LiteLLM |
| Gateway route auth | GatewayAPI 1.1 + AIB resource grant |
| Human login/groups/roles | Keycloak/Dex/OIDC |
| Complex enterprise policy | Future OPA/Rego or Keycloak AuthZ integration |

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

Do not make OPA/Rego or Keycloak Authorization Services mandatory in 1.0.

---

## Host questions required to finalize ADR-005

### Q1. Should the 1.0 authorization model be grant-table/data-first rather than policy-language-first?

Recommended answer:

- Yes. Use explicit requested edges, approved resource grants, and user delegated grants.

Tradeoff:

- Simple and auditable, but less expressive than OPA/Rego or Keycloak AuthZ.

### Q2. Should KAOS CRDs declare requested access only?

Recommended answer:

- Yes. `spec.modelAPI`, `spec.mcpServers`, and `spec.agentNetwork.access` are requested edges. They do not approve themselves.

Tradeoff:

- Avoids permissions-by-default, but requires admin approval flow or bootstrap grant creation.

### Q3. Should AIB CEL be the user-facing policy language?

Recommended answer:

- No. Keep CEL as internal bounded expression support for claim extraction/token checks. Do not expose it as the primary policy authoring language in 1.0.

Tradeoff:

- Avoids arbitrary expression governance in 1.0, but complex policies require later extension.

### Q4. Should OPA/Rego be mandatory in 1.0?

Recommended answer:

- No. Defer OPA/Rego until policy requirements exceed simple grants.

Tradeoff:

- Less enterprise-policy power initially, but avoids adding a second policy platform too early.

### Q5. Should Keycloak Authorization Services own KAOS resource authorization in 1.0?

Recommended answer:

- No. Keep Keycloak/Dex/OIDC as human identity/SSO. Keep KAOS resource grants in AIB.

Tradeoff:

- Avoids syncing dynamic KAOS resources into Keycloak now, but enterprise Keycloak AuthZ integration remains future work.

### Q6. How should admin/platform grants combine with user-delegated grants?

Recommended answer:

- Both must pass when both are relevant.

Example:

```text
Agent researcher calling MCP github for Alice requires:
  AIB resource grant: researcher -> github MCPServer
  AIB user grant: Alice -> researcher -> GitHub permission set
```

Tradeoff:

- Clear defense-in-depth, but more grant states to explain to users/admins.

### Q7. Should autonomous grants be first-class in this ADR?

Recommended answer:

- Partially. Treat autonomous runs as Agent identity plus correlation for platform grants, and use durable AIB user grants when acting for a user's third-party account. Defer run-scoped grants/expiry to approval/consent execution model.

Tradeoff:

- Keeps this ADR focused while acknowledging autonomous execution.

### Q8. Should MCP tool/argument-level policy be included now?

Recommended answer:

- No. KAOS currently models MCPServer-level references, not tool/argument permissions. Defer until KAOS can discover/model tools and declare permissions as config-as-code.

Tradeoff:

- 1.0 authorization is resource-level, not tool-level.

---

## Proposed ADR-005 decision if host agrees

1. KAOS 1.0 authorization is data-first and grant-table-based.
2. KAOS CRD references define requested access edges only.
3. AIB owns approved KAOS resource grants.
4. AIB owns user-delegated third-party grants through UserGrants and PermissionSets.
5. Admin/platform grants and user-delegated grants are both required when both apply.
6. AIB CEL remains internal bounded expression support, not the primary policy authoring language.
7. OPA/Rego is deferred to future advanced policy integration.
8. Keycloak Authorization Services is deferred; Keycloak/Dex/OIDC remains human identity/SSO in 1.0.
9. ModelAPI internal model/budget/rate authorization remains LiteLLM-owned.
10. MCP tool/argument-level policy is deferred until KAOS models tool permissions explicitly.
11. Autonomous run-scoped grants are deferred to the approval/consent execution model.

## Decision status

Awaiting host answers.
