# ADR-006: Consent and re-authentication execution model

**Status**: Accepted.
**Date**: 2026-06-20

---

## Decision

Adopt a **fail-with-actionable-user-URL-and-retry** model for AIB-backed user consent and third-party re-authentication.

Do **not** describe current AIB behavior as a generic "approval flow". Current AIB implements:

1. admin/operator configuration of agents, third-party services, permission sets, credentials, and signing keys,
2. end-user consent grants for agent access to third-party permission sets,
3. third-party OAuth2 session connection and re-authentication,
4. token exchange that verifies principal, agent, grant, session, scopes, and target resource before returning a third-party access token.

Current AIB does **not** implement a runtime-created admin approval request queue such as:

```text
requested -> pending_admin_approval -> approved | denied | expired
```

Therefore KAOS 1.0 must separate these cases explicitly:

| Case | 1.0 behavior |
|---|---|
| Missing KAOS resource grant | Fail closed with `platform_grant_missing`; no user consent URL; admin/platform grant must already exist or be bootstrapped explicitly. |
| Missing or expired user delegated grant | Fail with `user_consent_required` and AIB agent consent URL; user re-grants and retries. |
| Missing/unusable third-party OAuth2 session | Fail with `third_party_reauth_required` and AIB third-party authorization URL; user reconnects the service and retries. |
| Runtime-created admin approval request | Not implemented in current AIB; deferred. |
| MCP tool/argument approval | Deferred; not modeled in 1.0. |
| A2A task pause/resume via `input-required` | Deferred; KAOS has the state but not the durable resume workflow. |
| Autonomous run needs consent/re-auth | Stop/skip the protected action and record a structured event; do not block indefinitely or auto-grant. |

In short:

```text
Admin/platform resource grants:
  pre-existing grant data only; no runtime admin approval queue in 1.0.

User delegated consent:
  AIB consent UI/API creates or refreshes user_grants.

Third-party re-authentication:
  AIB OAuth2 session flow creates or refreshes encrypted user_sessions.

Runtime pause/resume:
  deferred until KAOS has durable tasks, resume APIs, and UI support.
```

This keeps KAOS 1.0 aligned with the "keep it simple" principle:

- no blocking waits,
- no durable pause/resume stack,
- no hidden approval state in memory,
- no accidental auto-granting in production,
- no conflation of admin approval, user delegated consent, and third-party OAuth2 re-authentication.

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) defines KAOS logical identities.

[ADR-003](./ADR-003-user-request-context-propagation.md) defines SDK-first request context propagation.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) defines AIB as the owner of:

- approved KAOS logical resource grants,
- user-delegated third-party grants,
- delegated third-party token exchange.

[ADR-005](./ADR-005-authorization-and-policy-model.md) accepts a simple grant-table model for 1.0:

- KAOS CRD references are requested access edges only.
- AIB owns approved KAOS resource grants.
- AIB owns user-delegated third-party grants.
- no-permission-by-default applies when security is enabled.
- OPA/Rego, Keycloak Authorization Services, MCP tool/argument policy, and autonomous run-scoped grants are deferred.

This ADR decides what happens operationally when an agent action cannot proceed because a platform grant, user delegated grant, or third-party OAuth2 session is missing or expired.

The key clarification is that **current AIB user consent and third-party re-authentication are not an admin approval workflow**. They are user-facing flows that update existing AIB grant/session state.

---

## Terminology

This ADR separates five concepts that are easy to conflate:

| Concept | Meaning | Example | Current implementation status |
|---|---|---|---|
| Admin/platform configuration | Admin defines agents, services, permission sets, credentials, and signing keys | Admin creates `github-issues-reader` permission set | Implemented by AIB admin APIs |
| Platform resource grant | Permission for one KAOS logical resource to use another KAOS logical resource | `agent://researcher` may call `mcp://github` | Target 1.0 AIB/KAOS grant model; runtime approval queue not implemented |
| User delegated consent grant | User allows an agent to use third-party permission sets on their behalf | Alice allows researcher to use GitHub issues permission set | Implemented by AIB consent APIs/UI and `user_grants` |
| Third-party OAuth2 session | User has connected a third-party account and AIB stores encrypted access/refresh tokens | Alice connected GitHub through OAuth2 | Implemented by AIB OAuth2 session APIs and `user_sessions` |
| Runtime human approval | Human approves a specific action or continuation during a run | "Approve sending this email" | Deferred |

The 1.0 goal is not to solve all five with one mechanism. The goal is to define a safe and simple behavior for each.

---

## Implemented AIB behavior

### Admin configuration exists, but runtime admin approval requests do not

Relevant files:

- `agentic-identity-broker/internal/adapters/http/routing/admin.go`
- `agentic-identity-broker/internal/adapters/http/handlers/admin/permission_sets_handler.go`
- `agentic-identity-broker/api/admin/openapi.yaml`

AIB admin APIs support CRUD-style configuration for:

- agents,
- third-party OAuth2 services,
- permission sets,
- per-agent client credentials,
- signing keys.

This is admin/operator configuration, not a runtime approval queue. There is no observed current endpoint/table for `access_requests`, `pending_approvals`, `approve_request`, or `deny_request`.

Implication:

- KAOS must not rely on current AIB to create a pending admin approval request when a runtime access edge is missing.
- Missing platform resource grants should fail closed.
- Any future admin approval queue would require new durable server-side state, admin APIs, UI, expiry, auditing, and retry/resume semantics.

### User delegated consent grants are implemented

Relevant files:

- `agentic-identity-broker/internal/adapters/http/routing/enduser.go`
- `agentic-identity-broker/internal/adapters/http/handlers/consent/grants_handler.go`
- `agentic-identity-broker/internal/domain/consent/service.go`
- `agentic-identity-broker/internal/domain/storage/user_grant.go`
- `agentic-identity-broker/web/src/pages/AgentGrantDetailPage.tsx`
- `agentic-identity-broker/migrations/003_create_user_grants.up.sql`
- `agentic-identity-broker/migrations/019_migrate_user_grants_to_permission_sets.up.sql`

AIB consent APIs and SPA allow an authenticated end user to:

- view an agent's requested services and permission sets,
- select grantable permission sets/services,
- create or update a user grant,
- set optional `valid_until`,
- revoke a grant,
- return to an authorization-session redirect URL when applicable.

The durable state is `user_grants`, keyed by principal and agent. In the permission-set model, the grant stores `granted_permission_sets`, which maps permission set IDs to included service IDs.

Implication:

- Missing user delegated grant should become `user_consent_required`.
- Expired `user_grants.valid_until` should become `user_consent_required` or equivalent "re-consent required".
- This should point the user to the AIB consent UI for the relevant agent.
- It is not a third-party re-authentication problem and not an admin approval problem.

### Third-party OAuth2 sessions are implemented

Relevant files:

- `agentic-identity-broker/internal/adapters/http/oauth2_sessions/handler.go`
- `agentic-identity-broker/internal/domain/oauth2session/service.go`
- `agentic-identity-broker/migrations/004_create_user_sessions.up.sql`

AIB OAuth2 session APIs allow a user to connect or reconnect a third-party service:

```text
user -> AIB third-party authorize endpoint
     -> GitHub/Google/etc OAuth2 authorize page
     -> AIB callback
     -> AIB exchanges code for access/refresh tokens
     -> AIB stores encrypted session in user_sessions
```

`user_sessions` stores encrypted access/refresh tokens, token type, token expiry, granted scopes, encryption context, and timestamps for a `(principal, service)` pair.

A third-party session is missing or unusable when:

- no session exists for `(principal, service)`,
- the access token is expired and cannot be refreshed,
- the refresh token is expired, revoked, absent, or unusable,
- token refresh fails,
- the session scopes do not cover the required effective scopes.

Implication:

- Missing/unusable session should become `third_party_reauth_required`.
- The response should include a third-party re-auth URL such as AIB's `/api/third-party/{serviceId}/oauth2/authorize`.
- This is not a user grant approval problem; it is a third-party account connection/refresh problem.

### Token exchange distinguishes grants from sessions

Relevant files:

- `agentic-identity-broker/internal/domain/tokenexchange/request.go`
- `agentic-identity-broker/internal/domain/tokenexchange/service.go`
- `agentic-identity-broker/internal/domain/tokenexchange/response.go`
- `agentic-identity-broker/specs/013-token-exchange/contracts/token-exchange-endpoint.yaml`

AIB token exchange:

1. validates token exchange request shape,
2. validates `subject_token`,
3. validates `client_assertion`,
4. extracts principal from the subject token,
5. extracts agent ID from the subject token,
6. authorizes the privileged client through CEL,
7. resolves the requested `resource` to a third-party OAuth2 service,
8. checks user grant before session lookup,
9. retrieves/refreshes third-party session token,
10. validates permission-set/effective-scope coverage,
11. returns an RFC 8693 token exchange response.

The ordering matters:

```text
grant check first
session check second
```

This prevents leaking whether a user has a third-party session when the agent has not been granted access.

Implication:

- Missing/expired user grant and missing/unusable third-party session must remain separate structured outcomes.
- KAOS should not collapse both into a generic "approval required" response.

---

## Execution model

### Missing platform resource grant

When an Agent tries to call an MCPServer, ModelAPI, or another Agent without an approved platform resource grant:

```text
deny:
  code: platform_grant_missing
  principal: keycloak://kaos/alice
  actor: agent://default/researcher
  target: mcp://default/github
  action: call
```

The runtime should not return an AIB user consent URL or third-party re-auth URL. This is not a user-facing third-party consent/session problem.

Current AIB does not implement a pending admin approval request queue for this case. KAOS 1.0 should therefore fail closed and rely on pre-existing approved grants or explicit bootstrap/dev auto-grant behavior.

### Missing or expired user delegated grant

When the platform resource grant exists but AIB reports that the user has not granted, or no longer grants, the agent the required third-party permission set:

```text
deny:
  code: user_consent_required
  principal: keycloak://kaos/alice
  agent: agent://default/researcher
  permission_set: github-issues-reader
  consent_url: https://aib.example.com/consent/agent/{agent-id}
```

The user opens the AIB consent UI, grants the agent permission, and retries the operation.

If `user_grants.valid_until` has expired, this is the same category: the user must re-consent/re-grant. It should not be treated as a third-party token refresh.

### Missing or unusable third-party OAuth2 session

When AIB token exchange finds that the user grant exists but the user's third-party OAuth2 session is missing, expired beyond refresh, revoked, or missing required scopes:

```text
deny:
  code: third_party_reauth_required
  service: github
  reauth_url: https://aib.example.com/api/third-party/{serviceId}/oauth2/authorize
```

The user reconnects or re-authorizes the third-party service and retries the operation.

If only the third-party access token is expired and the refresh token is valid, AIB should refresh internally and return a usable access token. The runtime should not involve the user in that case.

### Runtime human approval

Runtime human approval for action-specific decisions is deferred.

Examples:

```text
Approve sending this email.
Approve deleting this file.
Approve paying this invoice.
```

These are not equivalent to AIB user delegated consent or third-party re-authentication. They require a separate task/UI approval model and policy vocabulary.

### Autonomous runs

Autonomous runs must not create new user consent, reconnect third-party accounts, or wait indefinitely for a human.

If an autonomous run encounters missing consent or re-authentication:

```text
record event:
  consent_or_reauth_required

stop/skip protected action:
  depending on agent task semantics
```

The detailed policy for pausing/resuming autonomous runs is deferred until KAOS has durable task approval support.

---

## A2A `input-required` is not the 1.0 mechanism

Source file:

- `pydantic-ai-server/pais/a2a.py`

Relevant facts:

- `TaskState.INPUT_REQUIRED = "input-required"` exists.
- Valid transitions include `WORKING -> INPUT_REQUIRED` and `INPUT_REQUIRED -> WORKING`.
- The JSON-RPC route supports `tasks/send`, `tasks/get`, `tasks/list`, and `tasks/cancel`.
- There is no explicit resume/continue method that attaches user approval input to an existing `input-required` task.
- `LocalTaskManager` stores tasks in process memory.
- Current execution paths transition tasks directly to `COMPLETED` or `FAILED`; they do not surface structured approval requests.

Implication:

- KAOS has a useful lifecycle state for future pause/resume.
- Treating `input-required` as the 1.0 approval mechanism would require task persistence, resume APIs, approval payloads, UI support, and security context preservation.

---

## Memory is not approval state

Source file:

- `pydantic-ai-server/pais/memory.py`

Relevant facts:

- Memory stores events such as user messages, agent responses, tool calls, tool results, delegation requests, and delegation responses.
- Memory backends include local, Redis, and null behavior.
- Memory is suitable for replaying conversation context and tool history.
- It is not currently an approval ledger or secure token/security-context store.

Implication:

- Consent and re-authentication state must live in AIB grant/session state, not hidden KAOS memory events.
- Future admin/runtime approval state would need a dedicated durable model.

---

## Annex: Alternatives considered

### Option A: Treat all human action as one generic approval flow

This option returns a generic `approval_required` response for missing platform grants, missing user consent, expired user grants, missing third-party sessions, and runtime action approvals.

Rejected. It hides the implemented AIB distinction between `user_grants` and `user_sessions`, and it incorrectly implies that current AIB has a generic approval engine.

### Option B: Fail with consent/re-auth URL and require retry

This option lets execution begin when platform/resource access is allowed, but if user delegated consent or third-party re-authentication is required, the protected call fails with a structured action URL. After the user completes the flow, the user retries the request or tool call.

Accepted for KAOS 1.0 because it matches current AIB capabilities and avoids building durable pause/resume now.

### Option C: Pause the A2A task with `input-required`

This option uses the A2A `input-required` state as a true human-in-the-loop pause. When consent, re-authentication, or runtime approval is required, the task transitions to `input-required`; after the human acts, a resume call continues the same task.

Deferred. It is the better long-term UX for complex multi-step tasks, but current KAOS does not yet have durable task persistence, resume APIs, structured approval payloads, secure context preservation, or UI support.

### Option D: Automatically create grants from CRD references

This option treats CRD wiring as both requested access and approved access. If an Agent references an MCPServer or ModelAPI, KAOS or AIB automatically creates the approved resource grant.

Rejected as the production/default security behavior. It conflicts with no-permission-by-default and makes CRD authors implicit security approvers. Explicit bootstrap/dev auto-grant behavior may still be useful, but it must be clearly marked and auditable.

---

## Consequences

### Positive

- ADR language matches current AIB implementation instead of implying a nonexistent generic approval workflow.
- KAOS can handle current AIB outcomes cleanly: consent URL, re-auth URL, or platform grant missing.
- AIB token exchange remains secure by checking grants before sessions.
- Runtime implementation stays simple: fail with structured action and retry.

### Negative

- Missing platform resource grants do not get an automatic admin approval request in 1.0.
- Users may need to retry after consent or re-authentication.
- Long-running tasks cannot yet pause and resume seamlessly around consent/re-authentication.

### Risks

- If clients label every outcome as "approval required", users and operators may misunderstand who must act.
- If missing grants and missing sessions are collapsed, KAOS may leak third-party session state or show the wrong URL.
- If future admin approval state is added without durable storage and audit, it may become unreliable or insecure.

---

## Decision summary

1. KAOS 1.0 separates platform resource grants, user delegated consent grants, third-party OAuth2 sessions, and runtime human approvals.
2. Current AIB supports admin configuration, user consent grants, OAuth2 sessions, and token exchange; it does not currently support runtime-created admin approval requests.
3. Missing platform resource grants fail closed with `platform_grant_missing`; no user consent or third-party re-auth URL should be returned for that case.
4. Missing or expired user delegated grants use AIB consent UI/API and fail with `user_consent_required` plus `consent_url`.
5. Missing/unusable third-party OAuth2 sessions use AIB OAuth2 session flow and fail with `third_party_reauth_required` plus `reauth_url`.
6. Expired third-party access tokens should be refreshed by AIB when a valid refresh token/session exists.
7. Synchronous requests must not block while waiting for consent, re-authentication, or future approval.
8. A2A `input-required` pause/resume is deferred until KAOS has durable tasks, resume APIs, approval payloads, and UI support.
9. Runtime human approval for specific tool actions is deferred until KAOS models tool/argument permissions or approval policies explicitly.
10. Autonomous runs must not auto-create consent or wait indefinitely; they should record structured consent/re-auth-required events and stop/skip protected actions.
11. CRD references must not auto-create approved resource grants in production/default security mode.
