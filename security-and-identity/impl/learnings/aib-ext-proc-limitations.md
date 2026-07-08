# AIB ExtProc limitations — token exchange coupling, OPA enablement, and issuer configuration (learnings)

**Date**: 2026-07-08
**Context**: Live walkthrough of the `aib-keycloak` posture on a running KIND cluster (`kaos-walkthrough` namespace, AIB broker + ExtProc in `aib-system`, Keycloak realm `kaos`) while trying to demonstrate a request being allowed vs rejected end to end. These are the boundaries we hit, verified against the running deployment and the merged `#222` code in worktree `../aib-222-verify` (`internal/extproc/server/server.go`, `internal/extproc/authorization/`, `internal/ports/config.go`).

## What actually enforces today, and what does not

The gateway `jwt_authn` layer (the `SecurityPolicy` with a `user` Keycloak provider and an `agent` broker provider) is the live, demonstrable enforcement point. Requests are accepted or rejected there **on identity presence and validity only**:

- No token → `401 jwt_authn_access_denied{Jwt_is_missing}`.
- Malformed token → `401 ...{Jwt_is_not_in_the_form...}`.
- Untrusted issuer → `401 ...{Jwt_issuer_is_not_configured}`.
- Valid Keycloak user token → passes `jwt_authn`, then hits the ExtProc token-exchange filter.

What is **not** enforcing in this posture is fine-grained authorization (which agent may reach which resource). That is the ExtProc OPA decision, and it is not enabled in the deployment (see below). So the honest current outcomes are `401` (rejected identity) and, for a valid user token on an internal resource, `500` (identity passed, exchange could not complete) — never a permission-set-driven allow/deny.

## OPA authorization exists in `#222` but is off by default and unwired in the KAOS deployment

`#222` implements OPA-in-ExtProc authorization, but it is gated behind `authorization.enabled`, which **defaults to false** (`internal/extproc/config/loader.go:76`, `:323`). It is configured via `EXTPROC_AUTHORIZATION_ENABLED` plus `EXTPROC_AUTHORIZATION_POLICY_PATH` (AutomaticEnv, `EXTPROC_` prefix) or a mounted policy/config file. The live `aib-agentic-identity-broker-extproc` Deployment carries **none** of these — its env is only `EXTPROC_GRPC_*` and `EXTPROC_OAUTH2_*`, no `authorization.*` args, and no policy volume mount. So the sidecar runs the plain token-exchange path (`processRequestHeaders`), not the OPA path (`processRequestHeadersOPA`).

This is a **KAOS wiring gap, not an AIB limitation**: enabling the grant-graph decision requires KAOS to project `EXTPROC_AUTHORIZATION_ENABLED=true` and mount a `granted_permission_sets`/`data.kaos.grants` rego. Tracked as phase P17 / [F8](../plan/followups.md).

## Token exchange is coupled to the request path and cannot be skipped by Rego

The RFC 8693 token exchange is wired **unconditionally relative to the policy decision** — a custom Rego policy cannot express "allow but do not exchange". The decision document is allow/deny only: `Decision{Action, Reasons}` with `Action ∈ {allow, deny, approval_required, ciba_required}` (`internal/extproc/authorization/decision.go:5-6`), and the two non-terminal actions are treated as deny.

- **Body-bearing requests** (POST / MCP JSON-RPC): the exchange runs **eagerly in the headers phase, before OPA evaluates** (`processRequestHeadersOPA`, server.go:466-476). If the exchange fails the request is rejected there and OPA never runs; Rego cannot prevent an exchange that already happened.
- **Header-only requests** (GET / SSE): OPA runs first and *gates* the exchange, but only in the deny direction — on `allow` the code **unconditionally** calls `s.exchanger.Exchange(...)` (`processHeadersOnlyOPA`, server.go:576). There is no allow-branch that forwards without exchanging.
- The **only** path that skips the exchange is `passThrough()` when there is **no `Authorization` bearer** (`processRequestHeaders:344`, `processRequestHeadersOPA:408`). That same branch also skips OPA entirely — the G1 autonomous gap ([F3](../plan/followups.md)). So "authorized but not exchanged" is not expressible.

Making the exchange skippable would require an **AIB code change**, one of: (a) honor a new decision field/action (e.g. `allow_no_exchange` / `skip_exchange: true`) and branch to `replaceAuthorizationHeader`/`passThrough` instead of `Exchange(...)`; or (b) make the exchanger fail-open for internal resources with no third-party mapping (return the original token instead of erroring), which also removes the internal-resource 500 below. These fit the F0/upstream theme.

## Why a valid user token yields 500 on an internal resource

On an internal agent route the ExtProc always attempts to exchange the user bearer for the target resource URI. With no service whose `protected_resource` matches the internal URL, no consent grant, and no vaulted token, the exchange fails and the ExtProc returns a `500` ImmediateResponse (`processRequestHeaders` exchange-error path, FR-008/FR-010). This is expected current-state behaviour, not a KAOS wiring bug: the happy path needs the consent + third-party vault ([F9](../plan/followups.md)). It also means there is **no clean `200` for a user-delegated request on an internal resource** until either F9 lands or the exchanger fails open for unmapped internal resources.

## The agent-identity path needs the broker `public_url` set (issuer mismatch)

The by-design path that *would* forward to the workload is the agent-identity call: a valid broker-issued agent token in `x-agent-authorization` with **no** user `Authorization` bearer → `jwt_authn` passes on the `agent` provider, and ExtProc `passThrough()` (empty bearer) forwards it. Live, this returned `401 Jwt_issuer_is_not_configured`. Decoding a minted agent token showed `iss: http://localhost:8000` — the broker defaults `server.enduser.public_url` to `http://localhost:8000` (`internal/ports/config.go:185`) and stamps it as the token `iss` (`internal/domain/oauth2/service.go:28`), while the gateway `agent` provider expects the broker's in-cluster issuer. Fixed KAOS-side by setting `broker.server.enduser.publicUrl` to the in-cluster broker enduser URL at install time (see [F0](../plan/followups.md)). Note this path proves **authentication only** — it hits the G1 no-bearer branch, so even with OPA enabled the grant graph is not consulted.

## Net implication for demonstrating allow/deny

- **Authentication** (identity in/out) is fully demonstrable now: `401` with a specific reason for missing/malformed/untrusted tokens, and identity admitted for a valid Keycloak token.
- **A clean `200`** requires, depending on the path: the `public_url`/`iss` fix for the agent-identity (no-delegation) path; consent + vault (F9) for the user-delegated internal path; and `EXTPROC_AUTHORIZATION_*` + a mounted rego (F8/P17) for any fine-grained agent→resource decision.
- **Rego cannot be used to bypass the exchange** — that coupling is structural in `#222` and needs an upstream change, not a policy edit.
