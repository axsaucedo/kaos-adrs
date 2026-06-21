# Gateway ext_authz enforcement — implementation plan

**Branch (KAOS)**: `feat/gateway-ext-authz`, stacked off `feat/p1-sdk-propagation`; PR targets `feat/p1-sdk-propagation`
**Branch (AIB, local-only)**: rename `feat/p0-access-check-validation` -> `feat/aib-deployability-foundation`; create `feat/aib-access-check` on top
**Tracking issue**: axsaucedo/kaos#231

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with Copilot co-author.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1-3 checks locally before relying on CI; prefer full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- AIB repo is private upstream (`zalando-infosec`); we do NOT push there — AIB work stays on local stacked branches (validated with `just test` + KIND), upstreamed from a fork later.
- Scratch under `./tmp/` (gitignored), noise -> `./tmp/null`. End: gitignored REPORT.md (all prior + current tasks), posted as a PR comment (not committed).

## Problem statement

Deliver a working (not production) gateway authorization check: the KAOS operator generates an Envoy Gateway authorization policy per protected route that calls an AIB access-check, which decides allow/deny keyed on the calling agent (actor) and fails closed. Builds the genuinely-new AIB capability (the access-check) and the operator-side policy generation. ext_proc/token-exchange and ClusterIP restriction are out of scope; user auth is simulated (actor-only).

## Current-state grounding (researched)

- **AIB decision data model**: an agent's bound PermissionSets carry `service_scopes` `{service_id, scopes}`; ALLOW iff a bound PS covers the target service + requested action scope. Resource URI maps to a synthetic service by `client_id` convention `kaos://mcpserver/<ns>/<name>` <-> `kaos-mcpserver-<ns>-<name>`. Coverage logic today is inline in `internal/domain/tokenexchange/service.go` (`resolveEffectiveScopes`), not reusable — the access-check needs its own small domain service reusing repos. `consent.VerifyAgentAccess(principal, agentID)` covers user-delegated grants only.
- **AIB token validation**: broker issues local actor tokens (client_credentials ES256 JWT) signed by its keys; JWKS at `/oauth2/jwks.json`. `internal/adapters/jwtauth/jwx_authenticator.go` (`NewJWXAuthenticator`/`Authenticate`) validates a token against JWKS and returns claims (sub/agent_id) — reuse it.
- **AIB repos/lookups**: `AgentRepository.Get`/`GetByClientID` (`internal/ports/storage.go`), `PermissionSetService.GetByIDs`; service lookup by client_id needed (thirdparty provider repo: `FindByProtectedResource`; may add a GetByClientID or list+filter). HTTP routes registered in `internal/adapters/http/routing/{admin,enduser}.go`; handlers wired in `internal/app/{handlers.go,builder.go}`. enduser surface uses `RequirePrincipalMiddleware`. Tests: same-package domain mocks; handler tests via httptest; `just test`.
- **AIB gRPC**: `go.mod` has `envoyproxy/go-control-plane/envoy v1.37.0` (includes `service/auth/v3`). The existing ext_proc gRPC server (`cmd/extproc-token-exchange`, `internal/extproc/server`) is the template IF a gRPC Check is needed — but P2 uses HTTP ext_authz instead (below).
- **Operator gateway**: `pkg/gateway/gateway.go` `ReconcileHTTPRoute` builds HTTPRoutes (parentRefs, `/{ns}/{type}/{name}` prefix match, URLRewrite, backendRef) from env config (`GATEWAY_API_ENABLED`, `GATEWAY_NAME/NAMESPACE`). Controllers call it (agent/mcpserver/modelapi) and `Owns(&gatewayv1.HTTPRoute{})`. Config flows Helm values -> `chart/templates/operator-configmap.yaml` env -> `pkg/gateway.GetConfig()`. Reconcile pattern: Get -> build -> SetControllerReference -> Create/Update. RBAC markers in `main.go` + per-controller. `make generate manifests`; unit via envtest (`controllers/integration/suite_test.go`); e2e pytest in `operator/tests/e2e` (conftest installs operator with gatewayAPI enabled, port-forwards Envoy).
- **Envoy Gateway** v1.4.6 (installed via `kaos-cli/install.py` + `operator/hack/install-gateway.sh`). Operator imports only `gateway-api/apis/v1`, no `gateway.envoyproxy.io` types -> generate `SecurityPolicy` as `unstructured.Unstructured` (no heavy dep). EG `SecurityPolicy.spec.extAuth` supports `http` and `grpc` backends + `targetRefs`.

## Design plan (how it fits)

- **Gateway integration = `SecurityPolicy` + `extAuth.grpc`** -> a net-new AIB gRPC `envoy.service.auth.v3.Authorization/Check` service (mirrors the existing `ext_proc` gRPC binary; the `service/auth/v3` proto is already a dependency via go-control-plane). gRPC is the standard/ADR-specified shape and avoids header hacks.
- **Resource/action via `contextExtensions`** (required). The operator sets `kaos.resource` = the **resolved** resource identity (`kaos://{kind}/{ns}/{name}`, or `kaos://{kind}/{id}` when a custom id is used) and `kaos.action` per route; the Check service reads them from `CheckRequest.attributes.context_extensions`. Path-derivation is rejected because a custom `spec.security.id` decouples the identity from the route path. RISK: confirm EG v1.4.6 `SecurityPolicy.extAuth.grpc` surfaces `contextExtensions`; if not, fall back to operator-**set** request headers carrying the resolved identity (set-not-append, stripped from client input) — NOT path-derivation.
- **AIB access-check** = one decision domain service + two surfaces over it: HTTP `POST /api/access/check` (JSON, always 200 `{allowed, reason}`) for SDK/off-gateway callers, and the gRPC `Check` (OK=allow / Denied 403) for the gateway. Both validate the actor token (`x-agent-authorization`) via JWKS -> actor id, map the resource URI to the synthetic service by client_id convention (`kaos://{kind}/{ns}/{name}` -> `kaos-{kind}-{ns}-{name}`; the same transform handles custom ids), and decide from permission-set coverage. Fail closed (missing/invalid actor -> deny).
- **Operator** gains operator-wide security config (Helm -> configmap env -> config struct). When enabled, per protected route it generates a `SecurityPolicy` (unstructured `gateway.envoyproxy.io/v1alpha1`) targeting that route with `extAuth.grpc` -> the configured AIB ext_authz service and `contextExtensions` (resolved `kaos.resource` + `kaos.action`), fail-closed. Gated/default-off so existing routes/e2e are unaffected.
- AIB work on local stacked branches; operator work on the KAOS PR.

## Numbered TODOs

T1 (AIB, local) — Access-check decision domain service. New `internal/domain/accesscheck/` with `Decide(ctx, actorID, resource, action) (Decision, error)` returning allow/deny + reason (`granted`, `grant_missing`, `resource_unknown`). Resolve agent -> permission_sets -> service_scopes; map the resource URI to the synthetic service by client_id convention (`kaos://{kind}/{ns}/{name}` or `kaos://{kind}/{id}` -> `kaos-...`); ALLOW iff a bound PS covers that service + action scope. Reuse AgentRepository, PermissionSetService, and a service-by-client_id lookup. Validate: same-package unit tests with mocks; `just test`.

T2 (AIB, local) — HTTP `POST /api/access/check` (SDK surface). Validate the actor token (`actor_token`/`x-agent-authorization`) via JWKS -> actor id; resource/action from the JSON body; call the decision service; return 200 JSON `{allowed, reason, ...}` (HTTP status reflects request/auth validity, not the decision). Builder + routing wiring (enduser surface). Validate: handler tests (httptest) for allow/deny/fail-closed/invalid-token/unknown-resource; `just test`.

T3 (AIB, local) — gRPC `Authorization/Check` ext_authz service (gateway surface). New gRPC binary/service mirroring the existing `ext_proc` server, implementing `envoy.service.auth.v3.Authorization/Check`: extract the actor token from the `x-agent-authorization` header, resource/action from `attributes.context_extensions` (`kaos.resource`/`kaos.action`), validate the actor token via JWKS, call the decision service, return OK (allow) or Denied 403 (deny/fail-closed). Config + bootstrap like the ext_proc binary. Validate: in-process gRPC server tests (allow/deny/fail-closed); `just test`.

T4 (AIB, local) — Build + KIND validation of both surfaces. Build the broker (+ ext_authz) images with the new code, deploy to KIND (reuse tmp/security values), seed the encoding (reuse tmp/security harness), and exercise `POST /api/access/check` (JSON) and the gRPC `Check` (via Envoy or grpcurl with context_extensions) with crafted inputs: granted->allow, ungranted->deny, no-actor->fail-closed. Validate: scripted checks pass; document in tmp/security notes.

T5 (Operator, PR) — Operator-wide security config plumbing. Add Helm values for agent-auth (the ext_authz service ref + enablement) -> `operator-configmap.yaml` env -> a config struct the gateway/controllers read (extend `pkg/gateway` config or a new `pkg/security`). Default off: absent config -> no behavior change. Validate: Go unit test for config parsing; `make test-unit`.

T6 (Operator, PR) — SecurityPolicy (extAuth.grpc + contextExtensions) generation. When security is enabled, per protected route generate a `SecurityPolicy` (unstructured, `gateway.envoyproxy.io/v1alpha1`) with `targetRefs` -> the HTTPRoute, `extAuth.grpc` -> the configured AIB ext_authz service, and `contextExtensions` `kaos.resource` = the resolved resource identity (incl. custom id) + `kaos.action`, fail-closed (`failOpen: false`). First verify EG v1.4.6 surfaces `contextExtensions` on `SecurityPolicy.extAuth`; if not, fall back to an operator-**set** request header carrying the resolved identity. Owned by the resource (SetControllerReference). Add RBAC for securitypolicies; `make generate manifests`. Validate: Go unit tests asserting the generated SecurityPolicy shape (pure function, no cluster); `make test-unit`.

T7 (Operator, PR) — Local KIND validation + CI + REPORT. Deploy AIB (new endpoints) + the operator with security enabled in KIND; create an Agent+MCPServer, seed a grant, confirm the generated SecurityPolicy enforces allow/deny through the gateway (1-3 local checks). Run operator unit tests + a representative existing e2e locally. Push the operator PR, validate go-tests + existing e2e CI green (full auth e2e in CI is a later wiring phase). Write gitignored REPORT.md (all prior + current tasks); post as a PR comment.

## Validation per task

- T1-T3: `just test` (AIB Go unit + handler + gRPC server tests). T4: KIND deploy + scripted allow/deny/fail-closed.
- T5/T6: `make test-unit` (Go unit/envtest; generation tests are pure functions). T7: local KIND end-to-end (1-3 checks) + operator PR CI (go-tests + existing e2e). Reproduce 1-3 CI failures locally if red.
- Risk: whether EG v1.4.6 `SecurityPolicy.extAuth.grpc` surfaces `contextExtensions` — verify against the EG schema during T6; fall back to an operator-set resolved-identity header if absent (path-derivation is rejected because custom ids break it).

## Commit / PR strategy

- AIB: local stacked branches `feat/aib-deployability-foundation` -> `feat/aib-access-check`; per-task commits (T1-T4); not pushed (validated locally + KIND).
- KAOS: `feat/gateway-ext-authz` off `feat/p1-sdk-propagation`; one comprehensive commit per operator TODO; PR into `feat/p1-sdk-propagation`; keep CI green.
- REPORT.md gitignored; contents as a PR comment.

## Out of scope (later phases)

`ext_proc` token exchange, NetworkPolicy/ClusterIP restriction + TLS, user auth (Keycloak jwt_authn), the `--auth-enabled` install + sync service (full in-cluster e2e wiring), native resource-grant model.
