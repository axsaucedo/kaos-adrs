# ADR-012: AIB access-check API

**Status**: Proposed
**Date**: 2026-06-20

---

## Decision

Add a first-class AIB access-check API for resource-level authorization decisions.

The API must answer the question:

```text
Can principal X, acting through agent Y, access resource Z?
```

This is not supported by current AIB APIs. Current AIB only performs comparable grant checks inside OAuth2/token-exchange flows, and those flows continue into third-party session lookup, token refresh, and token response generation. That is the wrong shape for SDK `require_access` and Gateway API authorization.

The proposed API should support both:

1. **SDK usage**
   - `aib.check_access(...)`
   - `aib.require_access(...)`

2. **Gateway usage**
   - Envoy `ext_authz`, Envoy ExtProc authorization mode, Gateway implementation-specific authorization policy, or another fail-closed Gateway integration.

The API must return an authorization decision only. It must not perform third-party token exchange, must not require a live third-party OAuth2 session, and must not return third-party access tokens.

---

## Context

[ADR-009](./ADR-009-aib-python-sdk-design.md) describes SDK methods such as `check_access` and `require_access`, but current AIB does not expose a matching server API.

[ADR-011](./ADR-011-gateway-api-resource-boundary-enforcement.md) describes Gateway-level resource-boundary enforcement, but Gateway cannot call AIB for a clean resource decision without a standalone AIB access-check API.

This ADR defines the AIB-side capability required to make those SDK and Gateway designs real.

---

## Source facts

### Current AIB public APIs

Source files:

- `agentic-identity-broker/api/admin/openapi.yaml`
- `agentic-identity-broker/api/enduser/openapi.yaml`

Current admin operations are limited to:

- agents,
- third-party OAuth2 services,
- permission sets,
- agent client credentials,
- OAuth2 signing keys.

Current end-user/OAuth operations are limited to:

- current user,
- consent agents,
- user grants,
- third-party sessions,
- third-party OAuth2 authorize/callback,
- OAuth2 authorize,
- OAuth2 token,
- JWKS,
- OAuth2 metadata.

There is no endpoint named or shaped like:

```text
check_access
require_access
AccessDecision
/api/access/check
/oauth2/introspect-style resource check
```

### Current closest internal logic

Source files:

- `agentic-identity-broker/internal/domain/tokenexchange/service.go`
- `agentic-identity-broker/internal/domain/consent/service.go`
- `agentic-identity-broker/internal/domain/thirdparty/service.go`
- `agentic-identity-broker/internal/domain/storage/user_grant.go`
- `agentic-identity-broker/internal/domain/storage/permission_set.go`
- `agentic-identity-broker/internal/domain/storage/agent.go`

Current token exchange already performs some useful checks:

```text
validate subject_token
validate client_assertion
extract principal via CEL
extract agent_id via CEL
authorize privileged client via CEL
normalize resource URI
find service by protected_resources
verify user grant for principal + agent
validate permission-set/service coverage
retrieve third-party session
refresh third-party token if needed
return access token
```

For access-check purposes, only the first part is needed:

```text
validate subject_token
validate client_assertion or trusted caller
extract principal
extract agent/actor
resolve target resource
verify resource-level grant/policy
return allow/deny
```

The current `consent.Service.VerifyAgentAccess(principal, agentID)` verifies that a user has an active grant for an agent. It does not by itself verify a target KAOS resource. Token exchange adds target-service logic by looking up a third-party OAuth2 service through `FindByProtectedResource` and checking permission-set/service coverage before returning a token.

### Current model gap

Current AIB data model is centered on:

```text
Agent
ThirdpartyOAuth2Service
PermissionSet
UserGrant
UserSession
```

It does not have a first-class model for:

```text
PlatformResource
ResourceGrant
RequestedAccessEdge
ResourceAccessDecision
```

Therefore the access-check API can be implemented in two phases:

1. **Bootstrap phase**
   - Reuse existing ThirdpartyOAuth2Service `protected_resources`, PermissionSets, and UserGrants.
   - Suitable for early SDK/Gateway integration.
   - Explicitly temporary for KAOS platform/resource grants.

2. **Target phase**
   - Add first-class platform/resource grant objects.
   - Use the same API contract while replacing bootstrap lookup internals.

---

## User scenarios and testing

### User Story 1 - SDK performs resource access check (P1)

A Python Agent or MCPServer uses the AIB SDK to check whether the current principal and actor can access a target resource before executing a protected call.

**Independent test**:

Given a valid subject token, an active grant, and a target resource covered by the grant, `POST /api/access/check` returns `allowed: true`.

**Acceptance scenarios**:

1. Given a valid subject token and resource, when the SDK calls the access-check API, then AIB validates the token and extracts the principal and agent.
2. Given an active matching grant, when AIB checks access, then the response is `allowed: true`.
3. Given no matching grant, when AIB checks access, then the response is `allowed: false` with reason `grant_missing`.
4. Given an expired grant, when AIB checks access, then the response is `allowed: false` with reason `grant_expired`.

### User Story 2 - Gateway enforces route-level access before backend (P1)

An Envoy-compatible Gateway calls AIB before forwarding a request to a protected KAOS Agent, MCPServer, or ModelAPI route.

**Independent test**:

Given a request to a protected route without an allowed resource grant, the Gateway integration rejects the request before it reaches the backend.

**Acceptance scenarios**:

1. Given a Gateway request with a valid subject token, actor, and target resource, when the Gateway calls AIB, then AIB returns a deterministic allow/deny decision.
2. Given an allow decision, when the Gateway receives the response, then it forwards the request.
3. Given a deny decision, when the Gateway receives the response, then it rejects the request without calling the backend.
4. Given no Bearer token or unusable authentication context, when the Gateway calls AIB or its auth-required layer, then the request fails closed.

### User Story 3 - Decision API does not exchange tokens (P1)

Operators want route/resource authorization without retrieving third-party access tokens.

**Independent test**:

Given a valid grant but no live third-party OAuth2 session, the access-check API still returns the resource authorization decision and does not return `invalid_grant` for missing third-party session.

**Acceptance scenarios**:

1. Given the user has a resource grant but no third-party session, when access check runs, then AIB does not attempt session lookup.
2. Given the check is allowed, then the response contains no access token.
3. Given a third-party session is missing, then the response does not include a re-auth URL unless the checked resource explicitly requires session availability.

### User Story 4 - Bootstrap mode reuses existing grant model (P2)

AIB can support early SDK/Gateway access checks before first-class platform/resource grants exist.

**Independent test**:

Given a target resource URI mapped through `protected_resources` and a grant that covers the mapped service through PermissionSets, access check returns the expected decision.

**Acceptance scenarios**:

1. Given a resource URI matching one service's `protected_resources`, when AIB checks access, then it resolves that service.
2. Given a user grant with permission sets that include the service, then the decision is allowed.
3. Given a user grant that does not include the service, then the decision is denied.
4. Given multiple services match the same resource, then the decision fails closed with `ambiguous_resource`.

### User Story 5 - Target mode supports platform resources (P2)

AIB can later represent KAOS resources directly without encoding them as third-party OAuth2 services.

**Independent test**:

Given a platform resource grant for `kaos://agent/ns/researcher -> kaos://mcpserver/ns/github`, access check returns allowed without requiring third-party OAuth2 service records.

---

## API contract

### Endpoint

Proposed endpoint:

```http
POST /api/access/check
Content-Type: application/json
Authorization: Bearer <caller credential or gateway credential>
```

The endpoint should be available on the broker API surface used by trusted SDK/Gateway clients. It should not be a browser-only consent UI endpoint.

### Request

```json
{
  "subject_token": "eyJhbGciOi...",
  "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "resource": "kaos://mcpserver/default/github",
  "actor": "kaos://agent/default/researcher",
  "action": "access",
  "context": {
    "request_id": "req-123",
    "route": "/default/mcp/github"
  }
}
```

Fields:

| Field | Required | Description |
|---|---:|---|
| `subject_token` | yes | Token containing the user principal and, where configured, agent/actor claims |
| `subject_token_type` | yes | Token type; initially access token |
| `resource` | yes | Target resource URI, e.g. `kaos://...` or bootstrap HTTP protected resource |
| `actor` | no | Explicit actor/calling agent if not extracted from token |
| `action` | no | Requested action; default `access` |
| `context` | no | Non-secret correlation and route metadata |

### Response: allowed

```json
{
  "allowed": true,
  "principal": "user-x",
  "actor": "kaos://agent/default/researcher",
  "resource": "kaos://mcpserver/default/github",
  "action": "access",
  "decision_id": "dec-123",
  "matched_grant": {
    "type": "user_grant",
    "id": "..."
  }
}
```

### Response: denied

```json
{
  "allowed": false,
  "principal": "user-x",
  "actor": "kaos://agent/default/researcher",
  "resource": "kaos://mcpserver/default/github",
  "action": "access",
  "decision_id": "dec-124",
  "reason": "grant_missing",
  "message": "No active grant allows this actor to access the requested resource"
}
```

### HTTP status behavior

Use HTTP status for request/authentication/system validity, not for allow/deny decisions:

| Status | Meaning |
|---:|---|
| `200` | Decision returned, either `allowed: true` or `allowed: false` |
| `400` | Malformed request, invalid resource syntax, unsupported token type |
| `401` | Missing or invalid caller authentication |
| `403` | Caller is authenticated but not allowed to ask AIB for decisions |
| `500` | Internal server error |
| `503` | Dependency unavailable or policy engine unavailable |

Reason codes:

```text
allowed
grant_missing
grant_expired
resource_not_found
ambiguous_resource
actor_not_found
principal_invalid
policy_denied
unsupported_resource_type
configuration_error
```

---

## Functional requirements

- **FR-001**: AIB MUST expose a standalone access-check API that returns allow/deny decisions without issuing tokens.
- **FR-002**: The API MUST validate `subject_token` using the same JWT validation infrastructure used by token exchange where applicable.
- **FR-003**: The API MUST extract principal using configurable CEL expression, aligned with token exchange defaults.
- **FR-004**: The API MUST extract or accept actor identity using configurable CEL expression and/or explicit request field.
- **FR-005**: The API MUST validate the caller is authorized to request access decisions.
- **FR-006**: The API MUST fail closed on malformed tokens, missing resource, ambiguous resource, repository errors, and policy evaluation errors.
- **FR-007**: The API MUST return structured allow/deny decisions and machine-readable reason codes.
- **FR-008**: The API MUST not retrieve, refresh, return, or require third-party OAuth2 tokens.
- **FR-009**: Bootstrap mode MAY resolve `resource` through existing `ThirdpartyOAuth2Service.protected_resources`.
- **FR-010**: Bootstrap mode MAY verify service coverage through existing `UserGrant.granted_permission_sets` and PermissionSet `ServiceScope`.
- **FR-011**: Target mode SHOULD support first-class platform/resource grants without changing the API contract.
- **FR-012**: The API MUST emit structured audit logs for allow and deny decisions.
- **FR-013**: The API MUST redact tokens and secrets from logs, traces, and error messages.
- **FR-014**: The API SHOULD support an idempotent decision ID for audit/correlation.
- **FR-015**: The API SHOULD support Gateway-friendly latency budgets and timeouts.

---

## Gateway integration requirements

- **GW-001**: Gateway integration MUST fail closed when no authenticated subject is available.
- **GW-002**: Gateway integration MUST not rely on current token-exchange ExtProc no-Bearer pass-through behavior for authorization.
- **GW-003**: Gateway integration MAY use Envoy `ext_authz`, a new ExtProc authorization mode, or Gateway implementation-specific authorization policy.
- **GW-004**: Gateway integration MUST map route/backend target to the `resource` value sent to AIB deterministically.
- **GW-005**: Gateway integration MUST reject denied decisions before backend forwarding.
- **GW-006**: Gateway integration SHOULD propagate safe decision metadata to the backend only when useful and non-sensitive.

---

## SDK integration requirements

- **SDK-001**: SDK `check_access` returns the structured decision response.
- **SDK-002**: SDK `require_access` raises an authorization exception or returns an error when `allowed: false`.
- **SDK-003**: SDK methods MUST document that they require this AIB access-check API and are not backed by current token exchange alone.
- **SDK-004**: SDK methods MUST not call `/oauth2/token` for pure access decisions.

---

## Implementation notes

### Domain service

Introduce a domain service such as:

```text
AccessDecisionService.Check(ctx, request) -> AccessDecision
```

Initial implementation can reuse:

- JWT validation from token exchange,
- CEL principal/agent extraction from token exchange,
- `ThirdpartyOAuth2ProviderService.FindByProtectedResource` for bootstrap resource lookup,
- `consent.Service.VerifyAgentAccess` for user-agent grant existence,
- PermissionSet scope/service coverage logic from token exchange.

The extracted logic should stop before:

- `OAuth2SessionService.GetValidAccessToken`,
- third-party token refresh,
- token response construction.

### OpenAPI

The endpoint must be documented before implementation in the relevant AIB OpenAPI file, following AIB Constitution Principle IV.

### Tests

Tests should follow AIB TDD/E2E conventions:

- domain unit tests for allow/deny outcomes,
- handler tests for request/response contract,
- E2E tests for SDK-like and Gateway-like callers,
- explicit red tests before implementation.

---

## Annex: Alternatives considered

### Option A: Use `/oauth2/token` token exchange as access check

Rejected.

Token exchange performs grant checks but then requires third-party OAuth2 session state and returns tokens. It is the wrong contract for pure resource authorization.

### Option B: Use `GET /api/consent/agents/{agent-id}/grants`

Rejected.

This is a UI/read-model endpoint. It returns active grants for an authenticated user and agent, but does not take an arbitrary resource/action and does not produce a fail-closed authorization decision.

### Option C: Add only Gateway-specific ExtProc logic

Rejected as the only implementation.

Gateway integration is important, but SDKs also need the same decision semantics. A reusable AIB API avoids duplicating policy logic in Gateway and SDK-specific code.

### Option D: Add standalone access-check API

Accepted as the proposed direction.

It provides a single contract for SDK and Gateway integration, avoids token exchange misuse, and can evolve from bootstrap PermissionSet/service encoding to first-class platform/resource grants.

---

## Consequences

### Positive

- Makes SDK `check_access` and `require_access` real rather than speculative.
- Enables Gateway-level route/resource authorization without token exchange.
- Reuses existing AIB token validation, CEL extraction, grant, and PermissionSet logic.
- Avoids requiring third-party OAuth2 sessions for pure KAOS resource access.
- Creates a stable API that can survive the transition from bootstrap encoding to first-class resource grants.

### Negative

- Requires new AIB API, OpenAPI contract, handlers, domain service, tests, and docs.
- Bootstrap mode may still be conceptually awkward because it reuses third-party service/PermissionSet objects for platform resources.
- Gateway integration still needs a fail-closed authorization adapter separate from current token-exchange-only ExtProc behavior.

### Risks

- If bootstrap encoding is not clearly labeled temporary, AIB may accumulate platform-resource semantics in third-party OAuth2 data structures.
- If HTTP `403` is used for normal deny decisions, clients may lose structured decision details; prefer `200 allowed:false` for policy decisions.
- If Gateway and SDK use different resource naming conventions, decisions will diverge.
- If tokens are logged during checks, the new API becomes a token-leak vector.

---

## Decision summary

1. Current AIB does not support a standalone check/require-access API.
2. A new AIB access-check API is required for SDK `check_access`/`require_access` and Gateway resource authorization.
3. The API returns allow/deny decisions only; it does not exchange or return tokens.
4. Bootstrap implementation may reuse existing protected resources, UserGrants, and PermissionSets.
5. Target implementation should add first-class platform/resource grants behind the same API.
6. Gateway integration must fail closed and must not rely on current token-exchange ExtProc no-Bearer pass-through behavior.
7. SDK methods must explicitly depend on this API rather than pretending current `/oauth2/token` provides pure access checks.
