# AIB ExtProc limitations — token exchange coupling, OPA enablement, and issuer configuration (learnings)

**Date**: 2026-07-08
**Context**: Live walkthrough of the `aib-keycloak` posture on a running KIND cluster (`kaos-walkthrough` namespace, AIB broker + ExtProc in `aib-system`, Keycloak realm `kaos`) while trying to demonstrate a request being allowed vs rejected end to end. These are the boundaries we hit, verified against the running deployment and the merged `#222` code in worktree `../aib-222-verify` (`internal/extproc/server/server.go`, `internal/extproc/authorization/`, `internal/ports/config.go`).

## Background and work to date — context for a fresh session

This section orients a session picking this up from scratch. The rest of the document is the detailed evidence.

**The question we were answering.** Can the KAOS `aib-keycloak` security posture actually *enforce authorization* for internal traffic (agent→MCP, agent→agent, agent→ModelAPI) using AIB's ExtProc, or only authenticate identity? The investigation was diagnostic/Q&A driven by manually walking `docs/security/walkthrough-aib.md` on a live KIND cluster and repeatedly hitting "nothing works" moments. **Answer reached: authentication only today; internal authorization needs a different mechanism (KAOS-run OPA behind the ext_authz seam). See the Verdict section.**

**The stack under investigation.** A running KIND cluster (do NOT destroy it) with: the AIB broker + ExtProc in `aib-system`, Keycloak realm `kaos`, and a walkthrough workload in `kaos-walkthrough`. Enforcement is at the Envoy Gateway `jwt_authn` layer plus the AIB ExtProc token-exchange filter. The `aib-keycloak` posture runs the broker in `mode=hybrid` with Keycloak as the upstream IdP. AIB source under test is worktree `../aib-222-verify` (merged `#222`, OPA-in-ExtProc).

**KAOS security postures (CLI presets).** The CLI was simplified to a small set of auth presets; `aib-keycloak` is the full posture (gateway JWT + AIB ExtProc + Keycloak). This work lives on branch `feat/gatewayapi-strict-and-cli-simplification`, PR `#267` (`axsaucedo/agentic-kubernetes-operator`).

**What is fully working / demonstrated.** Gateway identity authentication: a request is admitted or rejected purely on token presence/validity (401 with specific reasons; valid Keycloak user token admitted). The live allow/deny demonstration is captured as "Step 6" in the walkthrough. Agent identity verification (actor token `sub` = logical identity) is covered in the sibling learning `actor-token-sub-logical-identity-verification.md`.

**What is NOT working / the ceiling.** Fine-grained authorization for internal resources. Root causes, all evidenced below: AIB OPA is off by default *and* not exposed by the broker chart; the RFC 8693 token exchange is mandatory and coupled to the request path (Rego cannot skip it); the exchange `500`s on internal resources (no service/consent/vault) and has no echo/same-token mode; a vaulted token cannot be seeded out of band; and storing a token "for the MCP server" would replace the identity header and ruin the flow.

**Where the follow-ups live** (`../plan/followups.md`): **F0** = AIB chart gaps (client-credentials endpoint + arbitrary env passthrough; extended here with the `public_url`/`iss` note and the OPA-env/policy-volume gap). **F3** = autonomous-mode / G1 gap (no subject bearer → OPA bypassed). **F8/P17** = live enforcement validation + broker OPA-authz enablement. **F9** = consent-based delegated access (AIB's defining capability; the only path to a user-delegated 200, external targets). **F2** = fold the vendored AIB token client into the KAOS Python SDK. The upstream-contribution track (was P14) is cancelled.

**Where the architecture decision lives** (`../adrs/adr_0001_enforcement-topology-and-policy-engine.md`): ADR 0001 originally chose AIB ext_proc-OPA as the single enforcement point and reserved ext_authz as an "optional, default-off generic seam". **This investigation invalidates the assumption that ext_proc-OPA can serve internal (Model 1) authorization** — the exchange coupling 500s internal calls before OPA. The reserved KAOS-run OPA seam should therefore become PRIMARY for internal authz (AIB = identity, KAOS-OPA = authorization; complementary). ADR 0001 is a candidate for amendment but has NOT yet been edited — this is the main open design task for the next session.

**Sibling learnings worth reading first** (same directory): `opa-extproc-authz-model-parity-and-oauth-path.md` (the #222 OPA capability + Model 1/Model 2 grant sources), `actor-token-sub-logical-identity-verification.md`, and the `manual-e2e-*.md` validation notes.

**Immediate next steps for a fresh session.**
1. Decide and (if agreed) amend ADR 0001: internal authorization via a KAOS-run OPA ext_authz seam; scope AIB ext_proc-OPA to external delegated access. Reflect in `followups.md` and this learning.
2. Optionally run the empirical *deny* demonstration (patch `EXTPROC_AUTHORIZATION_ENABLED=true` + a mounted rego on the live ExtProc, GET path) — but note it cannot prove an internal *allow* (see the OPA section).
3. Push the kaos-ai-docs commits if that repo is meant to be pushed (they are currently local only). Refresh `REPORT.md` and re-post to PR #267 (`gh pr comment 267 --body-file REPORT.md`, `axsaucedo` account).

**Environment quirks to save time.** In-cluster curl pod (`kubectl run --rm -i --image=curlimages/curl`) reaches the gateway LB IP `172.18.0.200`; the macOS host cannot (NetworkPolicy blocks direct-to-pod, so direct curl hangs). Base64url-decode a JWT payload with `cut -d. -f2 | base64 -d`. `gh` account switch is needed per repo: `axsaucedo` for the KAOS repo/PR; `alejandro-saucedo_zse` to resolve AIB `zalando-infosec/agentic-identity-broker` PRs. Cannot use `pkill`/`killall` (only `kill <PID>`); cannot `kubectl exec` into the distroless operator. Commit with `git -c commit.gpgsign=false` and the local identity — never override the git author email.

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

## What the exchange is for, and why it cannot "return the same token"

The exchange is purpose-built for **delegated external access**: it swaps the user subject token for a *different, previously-vaulted third-party access token* that the agent then presents to that external API. `TokenExchangeService.Exchange` (`internal/domain/tokenexchange/service.go:168`) requires three things to succeed:

- **Registered service** — the resource URI must resolve to a service with a `protected_resource` (`FindByProtectedResource`, step 8); otherwise `invalid_target`.
- **User consent grant** — a `UserGrant` for (principal, agent) must exist and be active (`consentService.VerifyAgentAccess`, step 9); otherwise `access_denied`.
- **Vaulted OAuth2 session** — a stored third-party session holding a real access/refresh token (`oauth2SessionService.GetValidAccessToken`, step 10); otherwise `invalid_grant` with a re-auth URL.

The response *is* that vaulted third-party token. There is **no echo/identity/pass-the-subject-token mode** — the service always looks up a target service and returns a third-party token, so for an internal KAOS resource (no service, no session) it can only fail. Consequently:

- **Default/auto grants do not get you to `200`.** Pre-seeding a `UserGrant` (a "trusted/pre-authorized client" pattern) removes the interactive consent screen, but the exchange still requires a vaulted session (step 10) — an actual third-party token obtained via a real OAuth authorization-code flow. Default consent cannot manufacture that token.
- **For internal resources the exchange is the wrong tool.** Making internal agent→MCP/agent→agent calls succeed is not a grant-seeding problem; it is the "do not exchange" AIB change (skip-exchange decision action, or a fail-open exchanger for unmapped internal resources) already noted above.
- **Default consent is a legitimate F9 sub-option** for external targets (drop the human click via admin pre-grant), but it cannot replace the third-party token vault.

## The agent-identity path needs the broker `public_url` set (issuer mismatch)

The by-design path that *would* forward to the workload is the agent-identity call: a valid broker-issued agent token in `x-agent-authorization` with **no** user `Authorization` bearer → `jwt_authn` passes on the `agent` provider, and ExtProc `passThrough()` (empty bearer) forwards it. Live, this returned `401 Jwt_issuer_is_not_configured`. Decoding a minted agent token showed `iss: http://localhost:8000` — the broker defaults `server.enduser.public_url` to `http://localhost:8000` (`internal/ports/config.go:185`) and stamps it as the token `iss` (`internal/domain/oauth2/service.go:28`), while the gateway `agent` provider expects the broker's in-cluster issuer. Fixed KAOS-side by setting `broker.server.enduser.publicUrl` to the in-cluster broker enduser URL at install time (see [F0](../plan/followups.md)). Note this path proves **authentication only** — it hits the G1 no-bearer branch, so even with OPA enabled the grant graph is not consulted.

## Net implication for demonstrating allow/deny

- **Authentication** (identity in/out) is fully demonstrable now: `401` with a specific reason for missing/malformed/untrusted tokens, and identity admitted for a valid Keycloak token.
- **A clean `200`** requires, depending on the path: the `public_url`/`iss` fix for the agent-identity (no-delegation) path; consent + vault (F9) for the user-delegated internal path; and `EXTPROC_AUTHORIZATION_*` + a mounted rego (F8/P17) for any fine-grained agent→resource decision.
- **Rego cannot be used to bypass the exchange** — that coupling is structural in `#222` and needs an upstream change, not a policy edit.

## Live test matrix (every combination we actually sent)

All requests were sent from an in-cluster curl pod (`kubectl run --rm -i --image=curlimages/curl`) to the gateway LB IP `172.18.0.200` on the `PathPrefix /kaos-walkthrough/agent/coordinator` route (the LB IP is not reachable from the macOS host; a `NetworkPolicy` blocks direct-to-pod, so direct curl hangs). Each resource `SecurityPolicy` has two `jwt_authn` providers: `agent` (broker JWKS, header `x-agent-authorization`) and `user` (Keycloak JWKS, header `Authorization`).

| # | What was sent | Live result | Where it stopped |
|---|---------------|-------------|------------------|
| 1 | No token at all | `401 jwt_authn_access_denied{Jwt_is_missing}` | gateway `jwt_authn` |
| 2 | Malformed bearer (`Authorization: Bearer abc`) | `401 ...{Jwt_is_not_in_the_form...}` | gateway `jwt_authn` |
| 3 | Well-formed JWT, wrong/unknown issuer | `401 ...{Jwt_issuer_is_not_configured}` | gateway `jwt_authn` |
| 4 | Valid Keycloak **user** token in `Authorization` | passes `jwt_authn` → `500` `direct_response` | ExtProc token exchange fails (no service/consent/vault for internal URI) |
| 5 | Minted broker **agent** token in `x-agent-authorization`, no user bearer | `401 ...{Jwt_issuer_is_not_configured}` | gateway `jwt_authn` — decoded token `iss: http://localhost:8000` ≠ the `agent` provider issuer (the `public_url`/`iss` bug) |

We never observed a `200` through the route in any combination. Outcomes 1–3 = identity rejected; 4 = identity accepted but exchange cannot complete; 5 = the by-design passthrough path blocked only by the issuer misconfiguration (which the CLI fix addresses, but even fixed it proves authentication only — it lands on the no-bearer `passThrough()` branch and never consults OPA).

## Vault/session seeding is not injectable — you cannot "store a token" out of band

The only code path that writes a token into the vault is the interactive OAuth2 authorization-code flow: `InitiateFlow` (`GET /api/third-party/{serviceId}/oauth2/authorize`, handler.go:609) → user authenticates at the third-party IdP → `HandleCallback` (`GET /api/third-party/{serviceId}/oauth2/callback`, handler.go:224, router.go:610) → `OAuth2SessionService.HandleCallback` (service.go:511) → `createSession` (service.go:418) → `storeSession` (encrypt + `repository.Create`). The third-party HTTP surface exposes **only** `GET /third-party/sessions` (list), `GET /third-party/{serviceId}/session` (details), and `DELETE /third-party/{serviceId}/session` (terminate) — there is **no `POST`/`PUT` to inject or seed a token** (handler.go:608–612). So a session/token can be *created* only by a real user completing a real OAuth flow against a real (or mock) IdP for a *registered service*; it cannot be pre-loaded administratively.

## Storing a token "for the MCP server" would ruin the execution flow

To make the exchange succeed for an internal MCP server you would have to (a) register the MCP server as an *external third-party OAuth2 service* whose `protected_resource` matches its URL, (b) stand up an IdP and have a user complete the auth-code flow so a session exists, and (c) seed a consent grant. Even after all that, on success the ExtProc **replaces the outgoing `Authorization` header with the vaulted third-party token** (`replaceAuthorizationHeader`, server.go:955; called from the body path at :388 and the header-only path at :584) before forwarding. The MCP server would then receive a fabricated third-party token *instead of* the agent/user identity it expects. This inverts the design (treats an internal KAOS component as an external resource server), is operationally meaningless, and yields **zero** authorization value — the authz decision (permission sets / grants) is entirely separate from the token that gets swapped in. Conclusion: storing a token for an internal MCP server is **not viable and actively harmful** to the flow. The RFC 8693 exchange is structurally the wrong mechanism for internal (agent→MCP, agent→agent, agent→ModelAPI) traffic.

## The chart does not expose the ExtProc OPA authorizer at all

Beyond "disabled by default", the broker Helm chart provides **no way to turn it on**. `charts/agentic-identity-broker/templates/extproc.yaml` sets a fixed env list that stops at `EXTPROC_LOG_LEVEL` (lines 51–75: `EXTPROC_GRPC_*`, `EXTPROC_OAUTH2_*`, `EXTPROC_LOG_LEVEL` only) with **no** `EXTPROC_AUTHORIZATION_ENABLED`, no `EXTPROC_AUTHORIZATION_POLICY_PATH`, and no `volumes`/`volumeMounts` for a rego bundle. (`templates/configmap-grants.yaml` is a red herring — it is Postgres `GRANT` SQL for the DB-migration Job, gated on `storage.type == postgres`, unrelated to OPA.) Enabling OPA on the running deployment therefore requires **manual deployment surgery**: patch the env in and mount a ConfigMap-backed rego as a volume. This is a chart-support gap on top of the KAOS-projection gap (F8/P17), not just an unset value.

## We did NOT try `authorization.enabled=true` live — and why it would not change the verdict

We have **not** enabled OPA on the live ExtProc in this investigation (it would need the manual patch above). Reasoning it through against the code, enabling it cannot produce a working internal `allow → 200`:

- **Body path (POST / MCP JSON-RPC)**: the exchange runs in the headers phase *before* OPA (`processRequestHeadersOPA`, server.go:466–476), so an internal request `500`s on the failed exchange before OPA is ever consulted.
- **Header-only path (GET / SSE)**: OPA runs first, so a rego **deny → clean `403`** *is* demonstrable — but on `allow` the code unconditionally calls `Exchange(...)` (server.go:576/584), which then `500`s for the same unmapped-internal-resource reason.

So a live OPA experiment could prove **deny (403)** but never a working **allow (200)** for internal resources. That is why we did not spend the deployment surgery: it cannot lift the ceiling. (If a future session wants the empirical deny demonstration, patch `EXTPROC_AUTHORIZATION_ENABLED=true` + `EXTPROC_AUTHORIZATION_POLICY_PATH=/policy/authz.rego`, mount a rego ConfigMap, and send a GET that the rego denies.)

## AIB `#231` does not close this gap

AIB PR `#231` (`zalando-infosec/agentic-identity-broker`, "Permission Sets & Tool Authorization + CIBA") is a **draft design document only** (`specs/design-permission-sets-tool-authorization.md`, ~1519 lines, no code), referencing `#200`. It doubles down on the third-party model ("the broker does not mint tokens; the access token comes from the third-party provider") and adds tiered runtime approval + CIBA. It does **not** add a skip-exchange action, a fail-open exchanger, or any internal-resource path — i.e. it does not solve internal KAOS authorization. Its useful principle is *"separate authorization from token acquisition"*, which is the AIB-side direction for our F9, but it is unmerged and third-party-scoped.

## Verdict (2026-07-08, end of investigation)

The ceiling reachable from AIB today for KAOS is **agent identity verification (authentication)**. Internal **authorization** (which agent may reach which internal resource) cannot be delivered by AIB's ExtProc as shipped, because: OPA is off, chart-unexposed, and — even if enabled — is short-circuited by the mandatory RFC 8693 exchange, which `500`s on internal resources and cannot be made to "return the same token" or be seeded with one. Internal authorization should therefore be pursued through a **different mechanism**: a KAOS-run OPA behind the ext_authz seam (ADR 0001's reserved, default-off seam), with AIB kept as the identity provider (complementary, not either/or).

## Appendix — PRs, commits, and code references

**AIB source under test**: worktree `../aib-222-verify`, remote `alejandro-saucedo_zse/agentic-identity-broker` (fork of `zalando-infosec/agentic-identity-broker`), containing merged `#222` (OPA-in-ExtProc). Draft `#231` reviewed separately via `gh pr view 231 --repo zalando-infosec/agentic-identity-broker` (resolvable only with the `alejandro-saucedo_zse` gh account, not `axsaucedo`).

**Key AIB code references**:
- `internal/extproc/server/server.go` — `processRequestHeaders` (non-OPA, exchange + 500), `processRequestHeadersOPA:466–476` (body: exchange before OPA), `processHeadersOnlyOPA:576–584` (OPA first, unconditional exchange on allow), `replaceAuthorizationHeader:955` (header swap, callers :388/:584), `passThrough` (no-bearer skip).
- `internal/extproc/authorization/decision.go:5–6` — `Decision{Action, Reasons}`, `Action ∈ {allow, deny, approval_required, ciba_required}` (no skip-exchange).
- `internal/extproc/config/loader.go:76,323` — `authorization.enabled` default false; env `EXTPROC_AUTHORIZATION_*`.
- `internal/domain/tokenexchange/service.go:168` — `Exchange()` steps 8 (service by `protected_resource`), 9 (consent `VerifyAgentAccess`), 10 (vaulted `GetValidAccessToken`); no echo mode.
- `internal/domain/oauth2session/service.go:418,511` + `internal/adapters/http/oauth2_sessions/handler.go:224,608–612` — session creation only via OAuth callback; no seed API.
- `internal/ports/config.go:185` — `PublicURL` default `http://localhost:8000`; `internal/domain/oauth2/service.go:28` — stamped as token `iss`.

**Broker chart references**: `charts/agentic-identity-broker/templates/extproc.yaml:51–75` (env, no authorization/volume); `templates/configmap.yaml:27–28` (`broker.server.enduser.publicUrl` → `public_url`); `templates/configmap-grants.yaml` (Postgres GRANT SQL, unrelated).

**KAOS changes made during this investigation** (branch `feat/gatewayapi-strict-and-cli-simplification`, PR `#267`, remote `axsaucedo/agentic-kubernetes-operator`):
- `6d76fc14` `docs(security): demonstrate live gateway allow/deny in aib-keycloak walkthrough` — added walkthrough "Step 6" with the in-cluster curl allow/deny demonstration.
- `68da2ea2` `fix(cli): set broker enduser public URL so agent token iss matches gateway` — the `public_url`/`iss` fix (`_build_aib_broker_public_url_args()` in `kaos-cli/kaos_cli/install.py`, seeded for all AIB postures; test in `tests/test_cli_integration.py`; 110 CLI tests pass).

**kaos-ai-docs commits** (remote `axsaucedo/kaos-telemetry-blogpost`): `867abcc` (this learning doc + F0 extension in `../plan/followups.md`), `72601a1` (token-exchange purpose/no-echo), plus this update.

**What was NOT changed in AIB**: no AIB code was modified — a skip-exchange decision action and/or a fail-open exchanger for unmapped internal resources remain the required upstream changes (F0 theme). The `public_url` default fix was applied KAOS-side (chart value), not upstream.
