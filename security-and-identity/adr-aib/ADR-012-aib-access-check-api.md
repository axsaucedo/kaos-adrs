# ADR-012: AIB access-check API

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

Add a first-class AIB access-check API for resource-level authorization decisions.

The API must answer the question:

```text
Can principal X, acting through agent Y, access resource Z?
```

This is not supported by current AIB APIs. Current AIB only performs comparable grant checks inside OAuth2/token-exchange flows, and those flows continue into third-party session lookup, token refresh, and token response generation. That is the wrong shape for SDK `require_access` and Gateway API authorization.

The API should support both:

1. **SDK usage**
   - `aib.check_access(...)`
   - `aib.require_access(...)`

2. **Gateway usage**
   - Envoy `ext_authz` / External Authorization gRPC for fail-closed route authorization.

The API must return an authorization decision only. It must not perform third-party token exchange, must not require a live third-party OAuth2 session, and must not return third-party access tokens.

Gateway integration and SDK integration should share one internal AIB domain service, but they should not expose the same wire protocol:

| Caller | Wire protocol | Purpose |
|---|---|---|
| SDK/application code | HTTP `POST /api/access/check` | Direct programmatic `check_access` / `require_access` calls |
| Envoy-compatible Gateway | Envoy `envoy.service.auth.v3.Authorization/Check` (`ext_authz`) | Native fail-closed Gateway allow/deny before backend forwarding |
| Existing AIB ExtProc | Envoy `envoy.service.ext_proc.v3.ExternalProcessor/Process` (`ext_proc`) | Existing token exchange/header mutation, not the primary authorization contract |

The access-check implementation MUST verify the user subject token as part of the decision. AIB must not treat user identity headers or unauthenticated request metadata as proof of the user unless a separately configured trusted boundary has already authenticated and signed/validated that identity.

### Two identities: subject (user) and actor (calling agent)

The decision uses two distinct identities, and is keyed on the **actor**:

- **Subject** = the user principal, from a Keycloak/OIDC-issued user token. Used for user-delegated third-party grants.
- **Actor** = the **calling agent**, from the agent's own **AIB-issued identity** (its actor token or client assertion), which AIB issues via `client_credentials`. AIB derives the actor from the caller's authenticated agent identity, **not from `subject_token.azp`**.

The decision is therefore `actor (calling agent) -> resource`. This is what makes multi-agent delegation correct: when Agent B calls a resource, the actor is B's own AIB identity, so the decision is `B -> resource`, never the original user-token `azp`. The Gateway is the primary caller (via `ext_authz`); the HTTP `POST /api/access/check` path is for custom servers run off-gateway. Context is passed using neutral `kaos.resource`/`kaos.action` values so the same contract serves AIB or an alternate backend (e.g. OPA).

---

## Context

[ADR-009](./ADR-009-aib-python-sdk-design.md) describes SDK methods such as `check_access` and `require_access`, but current AIB does not expose a matching server API.

[ADR-011](../adr-kaos/ADR-011-gateway-api-resource-boundary-enforcement.md) describes Gateway-level resource-boundary enforcement, but Gateway cannot call AIB for a clean resource decision without a standalone AIB access-check API.

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

### Current AIB user-token verification building blocks

Source files:

- `agentic-identity-broker/internal/domain/tokenexchange/jwt_validator.go`
- `agentic-identity-broker/internal/domain/tokenexchange/subject_token.go`
- `agentic-identity-broker/internal/domain/tokenexchange/service.go`
- `agentic-identity-broker/examples/config/token-exchange.yaml`
- `agentic-identity-broker/examples/config/jwt-preauth.yaml`

AIB already has relevant authentication-provider integration points:

- Token exchange validates `subject_token` JWTs through a `JWKSProvider`.
- Validation checks signature, configured issuer, configured audience, expiration, and not-before where applicable.
- The expected issuer and JWKS URI are supplied from the upstream OAuth2/OIDC provider configuration.
- Principal extraction is configurable through CEL, for example `subject_token.sub`, `subject_token.email`, or `subject_token.preferred_username`.
- Actor/agent extraction is configurable through CEL, for example resolving an upstream client ID from `subject_token.azp` or reading a dedicated agent ID claim.
- AIB also supports JWT pre-auth for end-user UI/API surfaces, where a trusted reverse proxy, API gateway, or service mesh can provide a JWT header verified with JWKS and expected issuer/audience.

Implication:

The access-check API does not need to invent a new user-authentication mechanism. It should reuse the same JWT validation and CEL extraction infrastructure that token exchange already uses, with configuration pointing at Keycloak, Dex, or another OIDC/OAuth2 provider's issuer and JWKS endpoint. Keycloak/Dex remain the authentication/token issuers; AIB verifies their tokens and uses the resulting principal/actor claims for authorization decisions.

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

A Python Agent or MCPServer uses the AIB SDK to check whether the calling agent (actor) can access a target resource before executing a protected call.

**Independent test**:

Given a valid actor token, an approved resource grant for that actor, and a target resource, `POST /api/access/check` returns `allowed: true`.

**Acceptance scenarios**:

1. Given a valid actor token and resource, when the SDK calls the access-check API, then AIB validates the actor token and derives the actor from it (not from any subject `azp`).
2. Given an approved resource grant for the actor, when AIB checks access, then the response is `allowed: true`.
3. Given no matching grant for the actor, when AIB checks access, then the response is `allowed: false` with reason `grant_missing`.
4. Given an expired grant, when AIB checks access, then the response is `allowed: false` with reason `grant_expired`.

### User Story 2 - Gateway enforces route-level access before backend (P1)

An Envoy-compatible Gateway calls AIB before forwarding a request to a protected KAOS Agent, MCPServer, or ModelAPI route.

**Independent test**:

Given a request to a protected route whose actor has no approved resource grant, the Gateway integration rejects the request before it reaches the backend.

**Acceptance scenarios**:

1. Given a Gateway request with a valid actor token, an optional subject token, and a target resource, when the Gateway calls AIB, then AIB returns a deterministic allow/deny decision keyed on the actor.
2. Given an allow decision, when the Gateway receives the response, then it forwards the request.
3. Given a deny decision, when the Gateway receives the response, then it rejects the request without calling the backend.
4. Given no authenticated actor, when the Gateway calls AIB or its auth-required layer, then the request fails closed.

### User Story 3 - Decision API does not exchange tokens (P1)

Operators want route/resource authorization without retrieving third-party access tokens.

**Independent test**:

Given an approved resource grant but no live third-party OAuth2 session, the access-check API still returns the resource authorization decision and does not return `invalid_grant` for a missing third-party session.

**Acceptance scenarios**:

1. Given the actor has a resource grant but no third-party session, when access check runs, then AIB does not attempt session lookup.
2. Given the check is allowed, then the response contains no access token.
3. Given a third-party session is missing, then the response does not include a re-auth URL unless the checked resource explicitly requires session availability.

### User Story 4 - Bootstrap mode for actor-to-resource grants (P2)

AIB can support early SDK/Gateway access checks before first-class platform/resource grants exist, using a synthetic internal service plus PermissionSet scopes — kept distinct from user-delegated `UserGrant`s.

**Independent test**:

Given a target resource URI mapped to the synthetic platform service, and a bootstrap grant for the **actor** covering it, access check returns the expected `actor -> resource` decision.

**Acceptance scenarios**:

1. Given a resource URI matching the synthetic platform service mapping, when AIB checks access, then it resolves that resource.
2. Given a bootstrap grant for the actor that covers the resource, then the decision is allowed.
3. Given no bootstrap grant for the actor covering the resource, then the decision is denied.
4. Given an ambiguous resource mapping, then the decision fails closed with `ambiguous_resource`.

Note: a user-delegated `UserGrant` alone never grants KAOS resource access; the two grant families stay distinct (ADR-004).

### User Story 5 - Target mode supports platform resources (P2)

AIB can later represent KAOS resources directly without encoding them as third-party OAuth2 services.

**Independent test**:

Given a platform resource grant for `kaos://agent/ns/researcher -> kaos://mcpserver/ns/github`, access check returns allowed without requiring third-party OAuth2 service records.

---

## API contract

### HTTP endpoint for SDK/application callers

Endpoint:

```http
POST /api/access/check
Content-Type: application/json
Authorization: Bearer <caller credential or gateway credential>
```

The endpoint should be available on the broker API surface used by trusted SDK/Gateway clients. It should not be a browser-only consent UI endpoint.

### Request

```json
{
  "actor_token": "eyJhbGciOi...",
  "subject_token": "eyJhbGciOi...",
  "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "resource": "kaos://mcpserver/default/github",
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
| `actor_token` | yes | The calling agent's AIB-issued identity token; the decision keys on this (the actor). At the gateway this is the `x-agent-authorization` token. |
| `subject_token` | no | The user principal token (Keycloak/OIDC), used only for user-delegated third-party grants. Absent for autonomous (actor-only) calls. |
| `subject_token_type` | no | Subject token type when a subject is present. |
| `resource` | yes | Target resource URI, e.g. `kaos://...` |
| `action` | no | Requested action; default `access` |
| `context` | no | Non-secret correlation and route metadata |

The actor MUST be derived from the authenticated `actor_token` (the calling agent's own AIB identity), **never** from `subject_token.azp`.

### Envoy `ext_authz` endpoint for Gateway callers

Gateway integrations should use Envoy External Authorization rather than trying to make Envoy synthesize the SDK JSON request directly.

The Gateway-facing AIB service should implement:

```protobuf
// envoy.service.auth.v3
service Authorization {
  rpc Check(CheckRequest) returns (CheckResponse);
}
```

Actual Envoy Gateway configuration should attach a `SecurityPolicy` with `extAuth.grpc` to the generated `HTTPRoute` and pass:

```yaml
extAuth:
  grpc:
    backendRefs:
      - group: ""
        kind: Service
        name: aib-ext-authz
        port: 9002
  headersToExtAuth:
    - authorization
    - x-request-id
  contextExtensions:
    - name: kaos.resource
      value: kaos://mcpserver/default/github
    - name: kaos.action
      value: access
  failOpen: false
  timeout: 500ms
  statusOnError: 503
```

The Gateway adapter maps Envoy `CheckRequest` to the same internal access decision request:

| Access decision field | Envoy `CheckRequest` source |
|---|---|
| `subject_token` | `attributes.request.http.headers["authorization"]`, after removing `Bearer ` |
| `resource` | `context_extensions["kaos.resource"]`, derived by KAOS from the target route/backend |
| `action` | `context_extensions["kaos.action"]`, default `access` |
| `actor` | verified token claim via CEL, or trusted Gateway-provided context/header only if configured |
| `request_id` | `attributes.request.http.headers["x-request-id"]` |
| HTTP metadata | `attributes.request.http.method`, `path`, `host`, and selected route metadata |

`allowed: true` maps to an Envoy OK response. `allowed: false` maps to a denied response, normally HTTP 403. Authentication/configuration/system errors map to denied or error responses according to the fail-closed Gateway policy.

### Relationship to existing AIB ExtProc

The existing AIB ExtProc service is also gRPC, but it implements a different Envoy API:

```protobuf
// envoy.service.ext_proc.v3
service ExternalProcessor {
  rpc Process(stream ProcessingRequest) returns (stream ProcessingResponse);
}
```

That service is appropriate for token exchange and header mutation. It currently reads `Authorization`, builds an HTTP resource URI from `:scheme`, `:authority`, and `:path`, calls RFC 8693 token exchange, and replaces the `Authorization` header with an exchanged token.

It is not the primary Gateway authorization API because current behavior passes no-Bearer requests through and is token-exchange-oriented. AIB may keep ExtProc for token exchange while adding `ext_authz` for authorization decisions.

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
- **FR-002**: The API MUST validate the `actor_token` (the calling agent's AIB-issued identity) and, when present, the `subject_token`, using the JWT validation infrastructure (signature, issuer, audience, expiration, not-before).
- **FR-003**: The API MUST derive the actor (calling agent) from the authenticated `actor_token`, never from `subject_token.azp`.
- **FR-004**: The API MUST decide `actor -> resource`; the subject principal, when present, is used only to evaluate user-delegated third-party grants. Autonomous (actor-only) calls have no subject.
- **FR-005**: The API MUST validate the caller is authorized to request access decisions.
- **FR-006**: The API MUST fail closed on a missing/invalid actor token, malformed tokens, missing resource, ambiguous resource, repository errors, and policy evaluation errors.
- **FR-007**: The API MUST return structured allow/deny decisions and machine-readable reason codes.
- **FR-008**: The API MUST not retrieve, refresh, return, or require third-party OAuth2 tokens.
- **FR-009**: Bootstrap mode MAY encode KAOS platform/resource grants through a synthetic internal service plus PermissionSet scopes — kept distinct from user-delegated `UserGrant`s and marked explicitly temporary — to resolve `actor -> resource` decisions until first-class resource grants exist.
- **FR-010**: Resource-access decisions MUST remain `actor -> resource`; a user-delegated `UserGrant` MUST NOT by itself be treated as KAOS resource access.
- **FR-011**: Target mode SHOULD support first-class platform/resource grants without changing the API contract.
- **FR-012**: The API MUST emit structured audit logs for allow and deny decisions.
- **FR-013**: The API MUST redact tokens and secrets from logs, traces, and error messages.
- **FR-014**: The API SHOULD support an idempotent decision ID for audit/correlation.
- **FR-015**: The API SHOULD support Gateway-friendly latency budgets and timeouts.

---

## Gateway integration requirements

- **GW-001**: Gateway integration MUST fail closed when no authenticated **actor** is available.
- **GW-002**: Gateway integration MUST not rely on current token-exchange ExtProc no-Bearer pass-through behavior for authorization.
- **GW-003**: Gateway integration SHOULD use Envoy `ext_authz` gRPC as the primary fail-closed Gateway authorization contract.
- **GW-004**: Gateway integration MUST map route/backend target to the `resource` value sent to AIB deterministically.
- **GW-005**: Gateway integration MUST reject denied decisions before backend forwarding.
- **GW-006**: Gateway integration SHOULD propagate safe decision metadata to the backend only when useful and non-sensitive.
- **GW-007**: Existing AIB ExtProc MAY continue to be used for token exchange/header mutation, but MUST NOT be treated as complete Gateway authorization unless it gains fail-closed authorization semantics.

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

Accepted.

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
