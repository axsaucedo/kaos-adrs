# ADR-KAOS-006: Re-authentication execution model

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

Adopt a **gateway-surfaced fail-with-re-auth-URL-and-retry** model for third-party OAuth2 sessions managed by AIB.

Current AIB does not provide a runtime-created admin approval queue; it provides admin configuration, end-user grant management, third-party OAuth2 sessions, and token exchange.

By default, the gateway-centric target model must treat these outcomes separately:

| Case | Behavior | Where it is surfaced |
|---|---|---|
| Missing KAOS resource grant | Fail closed with `platform_grant_missing`; no user action URL is returned. | Gateway `ext_authz` denied response from AIB. |
| Missing or expired user delegated grant | Fail closed with `user_grant_required`; the user must re-grant through the existing AIB grant UI/API and retry. | Gateway `ext_authz` denied response from AIB for the grant decision. |
| Missing/unusable third-party OAuth2 session | Fail with `third_party_reauth_required` and a third-party authorization URL; the user reconnects the service and retries. | Gateway `ext_proc` immediate response from AIB token exchange with `error_uri`/re-auth URL. |
| Runtime-created admin approval request | Deferred; not implemented in current AIB. | Not surfaced by KAOS today. |
| MCP tool/argument approval | Deferred; not modeled in the target model. | Not surfaced by KAOS today. |
| A2A task pause/resume via `input-required` | Deferred; KAOS has the state but not the durable resume workflow. | Future durable task workflow. |
| Autonomous run needs a user action | Stop/skip the protected action and record a structured `user_action_required` event; do not block indefinitely or auto-grant. | Agent/task event handling after the gateway response. |

The standard path is gateway enforcement:

- `jwt_authn` validates inbound user and agent tokens,
- `ext_authz` asks AIB for allow/deny resource decisions,
- `ext_proc` performs RFC 8693 token exchange and can return immediate re-auth responses,
- NetworkPolicy restricts direct ClusterIP workload-to-workload traffic so calls cannot bypass the gateway.

The SDK carries verified identity/context across hops so the gateway can enforce end-to-end. It does not authenticate users and does not enforce authorization. SDK access-check and token-exchange client helpers are optional helpers for custom servers deliberately run off-gateway.

This keeps the model simple:

- no blocking waits,
- no durable pause/resume stack,
- no hidden approval state in memory,
- no accidental auto-granting in production,
- no URL fields for outcomes that current AIB does not return.

---

## Context

[ADR-KAOS-001](./ADR-KAOS-001-identity-model-and-source-of-truth.md) defines KAOS logical identities.

[ADR-KAOS-003](./ADR-KAOS-003-user-request-context-propagation.md) defines request context propagation.

[ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md) defines AIB as the owner of:

- approved KAOS logical resource grants,
- user-delegated third-party grants,
- delegated third-party token exchange.

[ADR-KAOS-005](./ADR-KAOS-005-authorization-and-policy-model.md) accepts a simple grant-table model:

- KAOS CRD references are requested access edges only.
- AIB owns approved KAOS resource grants.
- AIB owns user-delegated third-party grants.
- no-permission-by-default applies when security is enabled.
- OPA/Rego, Keycloak Authorization Services, MCP tool/argument policy, and autonomous run-scoped grants are deferred.

[ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md) defines the gateway as the enforcement plane. Resource-to-resource authorization happens at the gateway, not in Python/SDK code. Per-resource configuration is `spec.security.id` only.

This ADR decides what happens operationally when an agent action cannot proceed because a platform grant, user delegated grant, or third-party OAuth2 session is missing or expired.

---

## Terminology

| Concept | Meaning | Example | Current implementation status |
|---|---|---|---|
| Admin/platform configuration | Admin defines agents, services, permission sets, credentials, and signing keys | Admin creates `github-issues-reader` permission set | Implemented by AIB admin APIs |
| Platform resource grant | Permission for one KAOS logical resource to use another KAOS logical resource | `agent://researcher` may call `mcp://github` | Target AIB/KAOS grant model; runtime approval queue not implemented |
| User delegated grant | User allows an agent to use third-party permission sets on their behalf | Alice allows researcher to use a GitHub issues permission set | Implemented by AIB end-user grant APIs/UI and `user_grants` |
| Third-party OAuth2 session | User has connected a third-party account and AIB stores encrypted access/refresh tokens | Alice connected GitHub through OAuth2 | Implemented by AIB OAuth2 session APIs and `user_sessions` |
| Runtime human approval | Human approves a specific action or continuation during a run | "Approve sending this email" | Deferred |

---

## Implemented AIB behavior

### Admin configuration exists, but runtime admin approval requests do not

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
- Any admin approval queue would require new durable server-side state, admin APIs, UI, expiry, auditing, and retry/resume semantics.

### User delegated grants are implemented

AIB end-user grant APIs and UI allow an authenticated end user to:

- view an agent's requested services and permission sets,
- select grantable permission sets/services,
- create or update a user grant,
- set optional `valid_until`,
- revoke a grant,
- return to an authorization-session redirect URL when applicable.

The durable state is `user_grants`, keyed by principal and agent. In the permission-set model, the grant stores `granted_permission_sets`, which maps permission set IDs to included service IDs.

Implication:

- Missing user delegated grant should become `user_grant_required`.
- Expired `user_grants.valid_until` should also become `user_grant_required`.
- Current AIB token exchange does not expose a dedicated grant-renewal URL field for this outcome.
- This is not a third-party re-authentication problem and not an admin approval problem.

### Third-party OAuth2 sessions are implemented

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
- This is a third-party account connection/refresh problem.

### Token exchange distinguishes grants from sessions

AIB token exchange:

1. validates token exchange request shape,
2. validates `subject_token`,
3. validates `client_assertion`,
4. extracts principal from the subject token,
5. identifies the calling agent actor,
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

The gateway `ext_authz` path surfaces the denied response from AIB. The runtime should not return a user action URL. Current AIB does not implement a pending admin approval request queue for this case. The target model should therefore fail closed and rely on pre-existing approved grants or explicit bootstrap/dev auto-grant behavior.

### Missing or expired user delegated grant

When the platform resource grant exists but AIB reports that the user has not granted, or no longer grants, the agent the required third-party permission set:

```text
deny:
  code: user_grant_required
  principal: keycloak://kaos/alice
  agent: agent://default/researcher
  permission_set: github-issues-reader
```

The gateway `ext_authz` path surfaces the denied response from AIB for the grant decision. The user must re-grant and retry the operation.

If `user_grants.valid_until` has expired, this is the same category: the user must re-grant. It should not be treated as a third-party token refresh.

### Missing or unusable third-party OAuth2 session

When AIB token exchange finds that the user grant exists but the user's third-party OAuth2 session is missing, expired beyond refresh, revoked, or missing required scopes:

```text
deny:
  code: third_party_reauth_required
  service: github
  reauth_url: https://aib.example.com/api/third-party/{serviceId}/oauth2/authorize
```

The gateway `ext_proc` path surfaces an immediate response from AIB token exchange with the re-auth URL, using the RFC 8693 error response shape including `error_uri` where applicable. The user reconnects or re-authorizes the third-party service and retries the operation.

If only the third-party access token is expired and the refresh token is valid, AIB should refresh internally and return a usable access token. The runtime should not involve the user in that case.

### Runtime human approval

Runtime human approval for action-specific decisions is deferred.

Examples:

```text
Approve sending this email.
Approve deleting this file.
Approve paying this invoice.
```

These require a separate task/UI approval model and policy vocabulary.

### Autonomous runs

Autonomous runs must not reconnect third-party accounts or wait indefinitely for a human.

If an autonomous run encounters a missing user grant or third-party re-authentication requirement:

```text
record event:
  user_action_required

stop/skip protected action:
  depending on agent task semantics
```

The detailed policy for pausing/resuming autonomous runs is deferred until KAOS has durable task approval support.

---

## A2A `input-required` is not the default mechanism

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

- KAOS has a useful lifecycle state for durable pause/resume.
- Treating `input-required` as the default approval mechanism would require task persistence, resume APIs, approval payloads, UI support, and security context preservation.

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

- Third-party session state must live in AIB grant/session state, not hidden KAOS memory events.
- Admin/runtime approval state would need a dedicated durable model.

---

## Annex: Alternatives considered

### Option A: Treat all human action as one generic approval flow

This option returns a generic `approval_required` response for missing platform grants, missing user grants, expired user grants, missing third-party sessions, and runtime action approvals.

Rejected. It hides the implemented AIB distinction between `user_grants` and `user_sessions`, and it incorrectly implies that current AIB has a generic approval engine.

### Option B: Fail with re-auth URL and require retry

This option lets execution begin when platform/resource access is allowed, but if third-party re-authentication is required, the protected call fails with a structured action URL. After the user completes the flow, the user retries the request or tool call.

Accepted because it matches current AIB capabilities, fits gateway `ext_proc` immediate responses for token exchange failures, and avoids building durable pause/resume now.

### Option C: Pause the A2A task with `input-required`

This option uses the A2A `input-required` state as a true human-in-the-loop pause. When re-authentication or runtime approval is required, the task transitions to `input-required`; after the human acts, a resume call continues the same task.

Deferred. It is the better long-term UX for complex multi-step tasks, but current KAOS does not yet have durable task persistence, resume APIs, structured approval payloads, secure context preservation, or UI support.

### Option D: Automatically create grants from CRD references

This option treats CRD wiring as both requested access and approved access. If an Agent references an MCPServer or ModelAPI, KAOS or AIB automatically creates the approved resource grant.

Rejected as the production/default security behavior. It conflicts with no-permission-by-default and makes CRD authors implicit security approvers. Explicit bootstrap/dev auto-grant behavior may still be useful, but it must be clearly marked and auditable.

---

## Consequences

### Positive

- ADR language matches current AIB implementation instead of implying a nonexistent generic approval workflow.
- KAOS can handle current AIB outcomes cleanly: re-auth URL, user grant required, or platform grant missing.
- AIB token exchange remains secure by checking grants before sessions.
- Runtime implementation stays simple: fail with structured action and retry.
- Enforcement remains gateway-centric; Python application code is not the standard place that produces authorization outcomes.

### Negative

- Missing platform resource grants do not get an automatic admin approval request by default.
- Missing/expired user grants do not get a dedicated URL field from the runtime SDK.
- Users may need to retry after re-authentication.
- Long-running tasks cannot yet pause and resume seamlessly around re-authentication.

### Risks

- If clients label every outcome as "approval required", users and operators may misunderstand who must act.
- If missing grants and missing sessions are collapsed, KAOS may leak third-party session state or show the wrong URL.
- If admin approval state is added without durable storage and audit, it may become unreliable or insecure.
- If workloads can bypass the gateway, these structured outcomes may not be produced consistently.

---

## Decision summary

1. The target model separates platform resource grants, user delegated grants, third-party OAuth2 sessions, and runtime human approvals.
2. These structured outcomes are surfaced through the gateway path: `ext_authz` denied responses for grant decisions and `ext_proc` immediate responses for token-exchange or third-party re-authentication `error_uri` handling.
3. Current AIB supports admin configuration, user grants, OAuth2 sessions, and token exchange; it does not currently support runtime-created admin approval requests.
4. Missing platform resource grants fail closed with `platform_grant_missing`; no user action URL should be returned for that case.
5. Missing or expired user delegated grants fail with `user_grant_required`; current AIB token exchange does not expose a dedicated grant-renewal URL field.
6. Missing/unusable third-party OAuth2 sessions use AIB OAuth2 session flow and fail with `third_party_reauth_required` plus `reauth_url`.
7. Expired third-party access tokens should be refreshed by AIB when a valid refresh token/session exists.
8. Synchronous requests must not block while waiting for re-authentication or additional approval.
9. A2A `input-required` pause/resume is deferred until KAOS has durable tasks, resume APIs, approval payloads, and UI support.
10. Runtime human approval for specific tool actions is deferred until KAOS models tool/argument permissions or approval policies explicitly.
11. Autonomous runs must not wait indefinitely; they should record structured user-action-required events and stop/skip protected actions.
12. CRD references must not auto-create approved resource grants in production/default security behavior.
13. SDK access-check and token-exchange helpers are only for custom off-gateway servers; the standard enforcement and token-exchange path is the gateway.
