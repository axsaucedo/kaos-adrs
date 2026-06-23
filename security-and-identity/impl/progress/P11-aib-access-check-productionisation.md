# P11 — AIB access-check API productionisation (progress)

**Phase**: P11 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P11-aib-access-check-productionisation.md`](../../plan/P11-aib-access-check-productionisation.md)
**Status**: Implementation complete. The P2 access-check slice (actor-keyed decision domain service, `POST /api/access/check`, and the Envoy `ext_authz` gRPC `Check`) is hardened to the ADR-AIB-002 production bar: optional subject-token handling with strict actor/subject separation, caller authorization on the HTTP surface, a structured decision contract (`decision_id`/`matched_grant`/`principal`/`message`), audit logging with token redaction, a per-decision latency budget with complete fail-closed coverage, safe gateway decision-metadata headers, OpenAPI documentation, a temporary-bootstrap label plus a target resource-grant model evaluation, and decision metrics. This is AIB-repo work on `feat/aib-access-check`; the actual upstreaming is a later phase.
**Date**: 2026-06-23
**Repo / branch**: `agentic-identity-broker` `feat/aib-access-check`, stacked on `feat/aib-deployability-foundation`, pushed to the `aib-tmp` review remote.

## Outcome

P2 delivered a working-but-not-production access-check keyed only on the actor token. P11 closes the concrete gaps to ADR-AIB-002 without changing the external shape of the contract beyond additive response fields — it makes the existing contract correct, safe, observable, and documented:

- **Subject (user) token handling and actor/subject separation**: the HTTP request gains an optional `subject_token`, and the gRPC path reads the user token from the standard `Authorization` header alongside the actor's `x-agent-authorization`. A supplied subject token is validated with the broker's existing user-token `JWTAuthenticator` (reused — *not* the actor validator, which has a different issuer/audience) and its principal is recorded on the decision and audit. The decision stays strictly `actor -> resource` from permission-set coverage: the subject principal never grants resource access. A malformed/invalid supplied subject token fails closed (deny).
- **Caller authorization on the HTTP surface**: `POST /api/access/check` can now be placed behind a caller-authorization boundary — an authenticated caller principal (the broker's pre-auth `RequirePrincipalMiddleware` / `X-Remote-User`) checked against a configured allowed-caller set, rejecting at the request layer (401 unauthenticated / 403 unauthorized) distinct from a 200 deny *decision*. It is config-gated so a dev/no-auth install still works open. The gRPC caller is the gateway at a trusted network boundary.
- **Structured decision contract**: `Decision` carries a `DecisionID` (generated per evaluation, or the caller-supplied correlation id echoed), a `MatchedGrant` (type + id on allow), and a human-readable `Message`. The HTTP body now returns `{allowed, principal, actor, resource, action, decision_id, matched_grant, reason, message}`; the gRPC path propagates the decision id/reason.
- **Audit logging + redaction**: one structured audit log line per decision (allow and deny) with decision_id/actor/subject/resource/action/reason/matched_grant/latency. A redaction helper guarantees raw actor/subject tokens and secrets never appear in logs, traces, or error messages; callers receive generic error text.
- **Latency budget, fail-closed completeness, gateway metadata**: a configurable per-decision `context.WithTimeout` fails closed on deadline; the fail-closed set is completed to include ambiguous resource resolution (a resource URI mapping to more than one service) and repository/evaluation errors, all of which deny rather than 500. On the gRPC allow path, safe set-not-append metadata headers (`x-kaos-actor`, `x-kaos-principal` when present, `x-kaos-decision-id`) are added to the backend request — never raw tokens.
- **OpenAPI + bootstrap labeling + target-model evaluation**: `POST /api/access/check` is fully documented in `api/enduser/openapi.yaml`; the synthetic-service/PermissionSet bootstrap encoding is labeled temporary in code and in a design note distinct from `UserGrant`; an evaluation note recommends the first-class `PlatformResource`/`ResourceGrant`/`RequestedAccessEdge`/`ResourceAccessDecision` model behind the unchanged contract.
- **Metrics**: a decision counter labelled by `allowed`/`reason`, an error counter, and a decision-latency histogram via the broker's existing telemetry provider.

## Deliverables

| Area | Deliverable |
|---|---|
| Subject token | `internal/adapters/http/handlers/accesscheck/handler.go` (optional `subject_token`, `WithSubjectValidator`), `internal/adapters/grpc/accesscheck/server.go` (`Authorization` header), `internal/app/builder.go` (wires the broker's `jwtauth.JWTAuthenticator` as the subject validator). |
| Actor/subject separation | `internal/domain/accesscheck/service.go` — `Decide(ctx, actorID, subjectPrincipal, resource, action, correlationID)`; subject recorded only, never used by `covers()`. |
| Caller authz | `internal/adapters/http/routing/enduser.go` — config-gated `RequirePrincipalMiddleware` + `requireAllowedAccessCheckCaller(allowed)`; `internal/ports/config.go` — `AccessCheck.HTTPCallerAuth{Enabled, AllowedCallers}`. |
| Decision contract | `internal/domain/accesscheck/service.go` — `Decision{Allowed, Reason, SubjectPrincipal, DecisionID, MatchedGrant, Message}`, `MatchedGrant{Type, ID}`, `NewDecisionID`, `messageForReason`, reason taxonomy incl. `resource_ambiguous`/`deadline_exceeded`/`internal_error`. |
| Audit + redaction | `internal/domain/accesscheck/redaction.go` — `RedactString`; handler/gRPC audit log lines with latency. |
| Latency + fail-closed | handler/gRPC `context.WithTimeout`; ambiguous-resource conflict -> deny; decider errors -> deny (200 allowed:false), not 500. |
| Gateway metadata | `internal/adapters/grpc/accesscheck/server.go` — set-not-append `x-kaos-actor`/`x-kaos-principal`/`x-kaos-decision-id` on allow. |
| OpenAPI + docs | `api/enduser/openapi.yaml` (+158 lines); `docs/architecture/access-check-resource-model.md` (bootstrap-temporary + target model evaluation). |
| Metrics | decision counter (allowed/reason), error counter, latency histogram via the existing meter provider. |
| Resource resolver | `internal/adapters/accesscheck/service_resolver.go` — surfaces a conflict (ambiguous) distinct from not-found. |

## Validation

- **Per-TODO + final**: `go build ./...` clean; `go test -race` on the access-check domain/HTTP/gRPC/adapter packages plus routing and app green; `go test -race ./internal/...` green; OpenAPI parses (`yaml.safe_load`).
- **In-cluster smoke** (Calico KIND `kaos-sec-e2e`, broker rebuilt from the branch — note the AIB Dockerfile packages a pre-built binary, so `just build-linux-arm64` must precede `docker build`): `POST /api/access/check` with an invalid actor token returns `200 {allowed:false, reason:invalid_actor_token, message, decision_id}`; a caller-supplied `decision_id` is echoed and a generated UUID is used when absent; a missing resource returns 400; the structured audit log line is emitted for each decision; the raw invalid token appears **zero** times in the broker logs (redaction confirmed).

## Out of scope / deferred

- The first-class `PlatformResource`/`ResourceGrant` model is **evaluated** (design note), not implemented — the bootstrap synthetic-service encoding remains, explicitly labeled temporary, behind the unchanged API contract.
- The positive end-to-end allow path (granted actor -> 200 through the gateway) requires sync-provisioned agents/permission-sets and the access-check ext_authz service wired into the gateway; it is validated by the unit/handler/gRPC tests and is part of the full-stack e2e follow-up rather than this brief in-cluster smoke.
