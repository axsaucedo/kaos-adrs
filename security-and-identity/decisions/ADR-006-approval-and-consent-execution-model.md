# ADR-006: Approval and consent execution model

**Status**: Accepted.
**Date**: 2026-06-20

---

## Context

[ADR-001](./ADR-001-identity-model-and-source-of-truth.md) defines KAOS logical identities.

[ADR-003](./ADR-003-user-request-context-propagation.md) defines SDK-first request context propagation.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) defines AIB as the owner of:

- KAOS logical resource grants,
- user-delegated third-party grants,
- delegated token exchange.

[ADR-005](./ADR-005-authorization-and-policy-model.md) accepts a simple grant-table model for 1.0:

- KAOS CRD references are requested access edges only.
- AIB owns approved KAOS resource grants.
- AIB owns user-delegated third-party grants.
- no-permission-by-default applies when security is enabled.
- OPA/Rego, Keycloak Authorization Services, MCP tool/argument policy, and autonomous run-scoped grants are deferred.

This ADR decides what happens operationally when an agent action cannot proceed because approval, user consent, or re-authentication is missing.


---

## Terminology

This ADR separates four concepts that are easy to conflate:

| Concept | Meaning | Example | Primary owner |
|---|---|---|---|
| Admin/platform approval | Approval that one KAOS resource may use another KAOS resource | `kaos://agent/researcher` may call `kaos://mcpserver/github` | AIB resource grants, created by admin/bootstrap flow |
| User delegated consent | User allows an agent to use a third-party permission set on their behalf | Alice allows researcher to use `github-issues-reader` | AIB UserGrant + PermissionSet |
| Third-party re-authentication | User has consented, but their third-party OAuth session is absent, expired, or missing required scopes | Alice must reconnect GitHub | AIB OAuth/session flow |
| Runtime human approval | Human must approve a specific action or continuation during an agent run | "Approve sending this email" | Future KAOS task/UI approval model |

The 1.0 goal is not to solve all four with one mechanism. The goal is to define a safe and simple behavior for each.

---

## Source facts

### KAOS A2A has an `input-required` state but no complete pause/resume workflow

Source file:

- `pydantic-ai-server/pais/a2a.py`

Relevant facts:

- `TaskState.INPUT_REQUIRED = "input-required"` exists.
- Valid transitions include `WORKING -> INPUT_REQUIRED` and `INPUT_REQUIRED -> WORKING`.
- The JSON-RPC route supports:
  - `SendMessage` / `tasks/send`,
  - `GetTask` / `tasks/get`,
  - `ListTasks` / `tasks/list`,
  - `CancelTask` / `tasks/cancel`.
- There is no explicit resume/continue method that attaches user approval input to an existing `input-required` task.
- `LocalTaskManager` stores tasks in process memory.
- Current execution paths transition tasks directly to `COMPLETED` or `FAILED`; they do not surface structured approval requests.

Implication:

- KAOS has a useful lifecycle state for future pause/resume, but it does not yet have a complete durable human-in-the-loop approval mechanism.
- Treating `input-required` as the 1.0 approval mechanism would require task persistence, resume APIs, approval payloads, UI support, and security context preservation.

### KAOS memory stores conversation/session events, not approval state

Source file:

- `pydantic-ai-server/pais/memory.py`

Relevant facts:

- Memory stores events such as user messages, agent responses, tool calls, tool results, delegation requests, and delegation responses.
- Memory backends include local, Redis, and null behavior.
- Memory is suitable for replaying conversation context and tool history.
- It is not currently an approval ledger or a secure store for raw tokens/security context.

Implication:

- Approval and consent state should not be hidden in memory events.
- Missing approval/consent should be represented by explicit task/API errors and AIB grant/session state.

### AIB consent APIs support user grants

Source files:

- `agentic-identity-broker/docs/api/consent-endpoints.md`
- `agentic-identity-broker/docs/api/consent-apis.md`
- `agentic-identity-broker/internal/adapters/http/handlers/consent/grants_handler.go`

Relevant facts:

- AIB exposes consent APIs for end users to view agent information and manage grants.
- Consent endpoints require an authenticated principal, currently supplied through trusted reverse-proxy context such as `X-Principal`.
- Grant creation/update is an upsert on a user+agent grant.
- Grants include permission-set selections and optional `valid_until`.
- Grant revocation is supported.
- Mutating consent requests use CSRF protection.
- AIB can validate authorization session tokens and return a redirect URL after grant creation when the consent flow is tied to an authorization session.

Implication:

- AIB already has the right product surface for user delegated consent.
- KAOS should use AIB consent URLs/errors for missing user consent rather than inventing its own user-consent store.
- AIB does not currently provide the complete KAOS admin approval workflow for resource grants.

### AIB token exchange can distinguish missing consent from missing/expired third-party sessions

Source file:

- `agentic-identity-broker/internal/domain/tokenexchange/service.go`

Relevant facts:

- Token exchange validates subject tokens and client assertions.
- It extracts principal and agent identity.
- It checks the user grant before retrieving third-party sessions.
- Missing, revoked, or expired user grants map to access-denied style errors.
- Missing or expired third-party sessions map to `invalid_grant` with re-auth hints and `error_uri` values.
- If a session lacks required scopes, AIB returns `invalid_grant` with a re-auth URL.
- AIB intentionally checks grants before sessions to avoid leaking whether a user has a third-party session when the agent is not granted.

Implication:

- KAOS should preserve this distinction:
  - no grant means consent/authorization is missing,
  - no session means re-authentication is required,
  - no resource grant means platform/admin approval is missing.
- Runtime errors should not expose tokens or sensitive third-party session details.

---

## Decision scope

This ADR fixes the following scope:

1. Which checks happen before a run starts.
2. Which failures return an approval/consent/re-auth URL and require retry.
3. Whether synchronous chat requests may block while waiting for approval.
4. Whether A2A `input-required` should be used in 1.0.
5. How autonomous runs behave when consent or re-authentication is required.
6. What AIB must support now versus later.
7. What KAOS UI/admin UI must support now versus later.

---

## Annex: Alternatives considered

### Option A: Preflight all approval and consent before execution

This option requires every needed platform approval, user delegated consent, and third-party session to exist before the agent begins execution. The runtime performs a full preflight check and refuses to start if anything is missing.

Example:

```text
Before running researcher for Alice:
  1. Check researcher -> github MCP resource grant.
  2. Check researcher -> gpt ModelAPI resource grant.
  3. Check Alice -> researcher -> GitHub permission set.
  4. Check Alice has active GitHub OAuth session.
  5. Start the run only if all checks pass.
```

This is simple for deterministic workflows where the needed resources are known from CRDs. It fits admin/platform grants especially well because resource edges are known at deploy time.

It is weaker for dynamic third-party usage. An agent may not know it needs GitHub until the conversation evolves or a tool is selected. Preflighting every possible user consent can lead to over-consent: users are asked to grant access that may not actually be needed.

Pros:

- Very predictable.
- Avoids mid-run failures for known dependencies.
- Good fit for admin/platform resource grants.
- Easier to reason about in CI/admin workflows.

Cons:

- Can require broad consent before it is needed.
- Hard to know all third-party scopes needed before agent execution.
- Does not match dynamic agent/tool behavior well.
- Requires more UI orchestration before a chat can start.

Best fit:

- Admin/platform resource grants.
- Static CRD requested edges.
- Optional preflight diagnostics, not the only user-consent behavior.

### Option B: Fail fast with consent/re-auth URL and require retry

This option lets execution begin when platform/resource access is allowed, but if a user delegated grant or third-party session is missing, the protected call fails with a structured error. The error includes enough information for the UI/client to send the user to AIB consent or re-authentication. After the user completes the flow, the user retries the request or tool call.

Example:

```text
Alice asks researcher to file a GitHub issue.

Runtime checks:
  researcher -> github MCP resource grant: approved
  Alice -> researcher -> GitHub permission set: missing

Runtime response:
  action blocked: user consent required
  approval_url: https://aib.example.com/consent/agent/...

After Alice approves:
  Alice retries the action.
```

For expired third-party sessions:

```text
AIB token exchange response:
  invalid_grant
  error_uri: https://aib.example.com/oauth/github/authorize?...

KAOS response:
  re-authentication required for GitHub
  reauth_url: ...
```

This keeps 1.0 simple because the runtime does not need to suspend and resume an execution stack. The client or user retries after consent. It also avoids asking for consent until a capability is actually needed.

Pros:

- Simple runtime behavior.
- Uses AIB's existing consent and re-auth flows.
- Avoids blocking requests while waiting for a human.
- Avoids building durable pause/resume in 1.0.
- Consent is demand-driven rather than broad upfront.

Cons:

- User may need to retry the request.
- Agent may lose some intermediate reasoning unless the client/session preserves enough context.
- Requires clear structured errors so UI/CLI clients can present the right action.
- Less seamless than true pause/resume.

Best fit:

- KAOS 1.0 user delegated consent and third-party re-authentication.

### Option C: Pause the A2A task with `input-required` and resume after approval

This option uses the A2A `input-required` state as a true human-in-the-loop pause. When approval, consent, or re-authentication is required, the task transitions to `input-required`. The UI shows an approval URL or approval prompt. After the user/admin acts, a resume call continues the same task.

Example:

```text
Task state:
  working -> input-required

Task status message:
  GitHub consent required for Alice.
  approval_url: https://aib.example.com/consent/agent/...

After approval:
  tasks/resume(task_id, approval_result)
  input-required -> working
```

This is the best long-term UX for complex multi-step and autonomous tasks. It preserves task identity and can avoid asking the user to restate the request.

However, current KAOS only has the state constant and transition rules. It does not yet have a complete durable resume mechanism, structured approval payloads, secure context preservation, or UI workflows for this. Implementing it now would expand the 1.0 scope significantly.

Pros:

- Best UX for long-running tasks.
- Natural fit for A2A async and future runtime human approvals.
- Preserves task identity.
- Can support multi-agent approval flows later.

Cons:

- Requires new resume APIs and task persistence.
- Requires structured approval records and UI support.
- Requires preserving request security context across pauses.
- More complex than required for initial grant-table authorization.

Best fit:

- Future approval/consent execution model after basic 1.0 grant checks work.

### Option D: Block synchronous requests while waiting for approval

This option keeps the HTTP/chat request open while the user completes consent or approval in another browser window.

Example:

```text
User asks for GitHub action.
Runtime detects missing consent.
Runtime returns approval URL but keeps request open.
User approves in browser.
Runtime resumes and returns final answer in same HTTP response.
```

This may feel seamless in a demo, but it is brittle operationally. Human consent can take minutes or never complete. HTTP clients, gateways, and load balancers have timeouts. It also complicates cancellation and cleanup.

Pros:

- Smooth if approval is immediate.
- No explicit retry needed.

Cons:

- Fragile with gateway/client timeouts.
- Consumes runtime resources while waiting for humans.
- Hard to cancel and audit cleanly.
- Poor fit for autonomous or multi-agent flows.

Best fit:

- Not recommended for KAOS 1.0.

### Option E: Automatically create grants from CRD references

This option treats CRD wiring as both requested access and approved access. If an Agent references an MCPServer or ModelAPI, KAOS or AIB automatically creates the approved resource grant.

Example:

```text
Agent spec references github MCP.
KAOS sync service creates:
  researcher -> github MCP, action=call, status=approved
```

This is operationally convenient, especially for development clusters, but it conflicts with no-permission-by-default. It also weakens the separation established in ADR-004 and ADR-005: CRDs define requested edges, not authorization approval.

There may still be a bootstrap mode for local development or trusted namespaces, but it should be explicit and distinguishable from production approval semantics.

Pros:

- Very easy developer experience.
- No separate admin approval UI needed initially.
- Useful for local demos or trusted bootstrap installs.

Cons:

- Violates no-permission-by-default if enabled by default.
- Makes CRD authors implicit security approvers.
- Harder to audit who approved resource access.
- Can hide missing approval flows that production needs.

Best fit:

- Explicit development/bootstrap mode only, not the 1.0 security default.

---

## Decision

Adopt a simple split model:

| Case | 1.0 behavior |
|---|---|
| Missing KAOS resource grant | Fail closed with `platform_approval_required`; do not auto-create in production |
| Missing user delegated grant | Fail fast with AIB consent URL; user retries after consent |
| Missing/expired third-party session | Fail fast with AIB re-auth URL; user retries after re-auth |
| Missing MCP tool/argument approval | Deferred; not modeled in 1.0 |
| Runtime human approval during a task | Deferred; future A2A `input-required` pause/resume |
| Autonomous run needs new consent/re-auth | Stop or fail the action with structured approval-required event; do not prompt/block indefinitely |

In short:

```text
Admin/platform approval:
  pre-approved resource grants only.

User delegated consent and third-party re-auth:
  fail with actionable URL and retry.

Runtime pause/resume:
  defer until A2A task persistence, resume APIs, and UI support exist.
```

This keeps 1.0 aligned with the "keep it simple" principle:

- no blocking waits,
- no durable pause/resume stack,
- no auto-granting by default,
- no hidden approval state in memory,
- no conflation of admin approval and user consent.

---

## Required 1.0 behavior

### Resource grant missing

When an Agent tries to call an MCPServer, ModelAPI, or another Agent without an approved AIB resource grant:

```text
deny:
  code: platform_approval_required
  source: kaos://agent/researcher
  target: kaos://mcpserver/github
  action: call
```

The runtime should not return a user OAuth consent URL because this is not a user-consent problem. It is an admin/platform approval problem.

### User delegated grant missing

When the platform resource grant exists but AIB reports that the user has not granted the agent the required third-party permission set:

```text
deny:
  code: user_consent_required
  principal: keycloak://kaos/alice
  agent: kaos://agent/researcher
  permission_set: github-issues-reader
  consent_url: ...
```

The client should direct the user to AIB consent and then retry.

### Third-party session missing or expired

When AIB token exchange returns `invalid_grant` with `error_uri` for a missing, expired, or insufficient-scope third-party session:

```text
deny:
  code: third_party_reauth_required
  service: github
  reauth_url: ...
```

The client should direct the user to re-authenticate and then retry.

### Autonomous runs

Autonomous runs must not create new user consent or wait indefinitely for re-authentication.

If an autonomous run encounters missing consent or re-authentication:

```text
record event:
  consent_or_reauth_required

stop/skip protected action:
  depending on agent task semantics
```

The detailed policy for pausing/resuming autonomous runs is deferred until KAOS has durable task approval support.

---

## Decision summary

1. KAOS 1.0 separates admin/platform approval, user delegated consent, third-party re-authentication, and runtime human approval.
2. Admin/platform resource access requires pre-existing AIB resource grants.
3. Missing resource grants fail closed with a `platform_approval_required` style error.
4. User delegated consent uses AIB consent flows and fail-with-consent-URL-and-retry.
5. Third-party session expiry or missing scopes use AIB re-auth URLs and fail-with-reauth-URL-and-retry.
6. Synchronous requests must not block while waiting for consent, re-authentication, or approval.
7. A2A `input-required` pause/resume is deferred until KAOS has durable tasks, resume APIs, approval payloads, and UI support.
8. Runtime human approval for specific tool actions is deferred until KAOS models tool/argument permissions or approval policies explicitly.
9. Autonomous runs must not auto-create consent or wait indefinitely; they should record structured approval-required events and stop/skip protected actions.
10. CRD references must not auto-create approved resource grants in the production/default security mode.
11. Optional bootstrap/dev auto-grant behavior may be considered later, but must be explicit and auditable.

