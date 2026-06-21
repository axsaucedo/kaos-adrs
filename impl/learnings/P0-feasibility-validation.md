# P0 — Feasibility validation and hypothesis testing (learnings)

**Phase**: P0 of [`../../security-and-identity/plan/proposed-split.md`](../../security-and-identity/plan/proposed-split.md)
**Date**: 2026-06-21

This is the most consequential P0 output: what was confirmed, what surprised us, the groundwork uncovered, and the concrete changes proposed for `proposed-split.md`. The proposed plan-deltas at the end are **for review, not yet applied**.

## Hypotheses

| # | Hypothesis | Result |
|---|---|---|
| H1 | The synthetic-service + PermissionSet + scope encoding can represent a KAOS actor→resource edge | Confirmed |
| H2 | A KAOS agent can mint an AIB-signed actor token | Confirmed — **only for agents registered as LocalClients** (see below) |
| H3 | The allow/deny decision (keyed on the actor) is computable from AIB data | Confirmed, including fail-closed |
| H4 | Two-identity (subject + actor) propagation works across hops with per-hop actor override | Confirmed |
| H5 | KAOS resources can be projected into AIB to drive the decision end to end | Confirmed (from the live KIND cluster) |
| H6 | AIB can be built and deployed to KIND and serve the data plane | Confirmed (with the groundwork below) |

## Key findings

The decision is data-first and reuses AIB's existing model cleanly: an agent's bound PermissionSets carry `service_scopes` of `{service_id, scopes}`; ALLOW iff some bound permission set covers the target service plus the requested action scope. The resource URI maps to a synthetic service by a stable `client_id` convention (`kaos://mcpserver/<ns>/<name>` ↔ `kaos-mcpserver-<ns>-<name>`). This is the bootstrap encoding the ADRs describe, and it works against the unmodified AIB data model.

The single most important runtime nuance: **agents must be registered in AIB as LocalClients** (no `client_id`, no `client_uris`) to mint AIB-issued actor tokens. `Agent.ClientType()` returns `ProxyClient` when a `client_id` is set, and in hybrid mode a ProxyClient's `client_credentials` request is forwarded to the upstream OAuth2 server (which fails). A LocalClient mints locally and yields a proper ES256 JWT with `sub`/`agent_id` = the agent UUID and `scope` = the granted action, validatable via the broker JWKS. The KAOS→AIB sync must therefore create agents without a `client_id`.

The access check reuses the broker JWKS for actor-token signature validation and returns allow/deny with a reason (`granted`, `grant_missing`, `resource_unknown`, `unauthenticated`, `invalid_actor_token`). Both the SDK JSON contract (`POST /api/access/check`) and an `ext_authz` HTTP surface (200 allow / 403 deny on `x-agent-authorization`) behave correctly and fail closed. Propagation is straightforward: extract trusted inbound headers (`x-request-id`, `x-principal`, `x-actor`, `authorization`, `x-agent-authorization`), generate a request id when absent, inject on outbound, and override only the actor per hop so each agent authenticates as itself while the user subject is carried unchanged — exactly the mechanism that makes multi-agent decisions key on the actor rather than the subject `azp`.

`client_credentials` is served on the main `/oauth2/token` endpoint (not only in the ExtProc exchanger), so the actor-token mint does not need a new endpoint — it needs correct client registration (LocalClient). The gateway in AIB's own compose is `agentgateway` (agentgateway.dev), not Envoy; it uses an `extProc` policy today. The standard Envoy `ext_authz` 200/403 contract is what the access check satisfies, and it is portable across Envoy and agentgateway.

## Groundwork uncovered (the [1.5]/[1.6] reality)

AIB is buildable and deployable, but several gaps had to be closed or worked around, and they should be treated as first-class prerequisites for the integration/install phase:

- **Container base image**: the production, extproc, and migrate Dockerfiles defaulted to a private `container-registry.zalando.net` base that is not publicly pullable. Fixed on the AIB branch to default to public `alpine:3` (override preserved via `BASE_IMAGE`).
- **Frontend build**: the broker image expects a built consent UI, and `just web-build` fails with `tsc: command not found` (web toolchain/deps incomplete). The API/data plane does not need the UI; a stub `web/dist/consent` is enough for data-plane validation, but a real image needs a working web build.
- **Helm chart schema**: the chart's own default values failed its `values.schema.json` (`awsKms.dynamodbTimeout` undeclared with `additionalProperties:false`). Fixed on the AIB branch.
- **Chart requires explicit secrets/auth**: it does not inject the JWE/encryption keys or an auth method by default. A working install must set `broker.thirdPartyOauth2.jweSigningKey`, `broker.encryption.memory.rawKey`, and `broker.server.{enduser,admin}.authentication.preauth.principalHeaderName`.
- **Storage**: `storage.type=memory` deploys cleanly with no Postgres and no migration job; the Postgres path depends on the Zalando postgres operator (`acid.zalan.do`). Memory backend is the right default for dev/CI/MVP installs.
- **Images are unpublished** (no image-publishing CI), so installs must build images and load them into the cluster (`kind load`). The full CI recipe is captured in `tmp/security/CI-RECIPE.md`.

## AIB-side constraints

The cloned AIB upstream remote is `git@github.com:zalando-infosec/agentic-identity-broker.git`. We have no push/PR access there, so P0's AIB changes live on a local branch (`feat/p0-access-check-validation`), validated locally (`just test` green), and this report goes to issue #231 rather than an AIB PR. This affects the upstreaming-oriented productionisation phases (SDK, AIB API): contributing upstream needs either access to `zalando-infosec` or a fork strategy — a decision to make before those phases.

A local-networking caveat for future local gateway tests: putting a real Envoy in front of a host-process access-check hit a Docker-Desktop-macOS quirk (`host.docker.internal` resolves IPv6-only; Envoy's container→host call would not connect). This is an environment artifact only — in-cluster, gateway and access-check are pods with normal DNS — but it means local Envoy↔host-process wiring should be avoided in favour of in-cluster pods.

## Proposed changes to `proposed-split.md` (for review — not applied)

1. **P3/P5 (sync)**: add an explicit constraint that the sync service registers KAOS agents as AIB **LocalClients** (no `client_id`) so actor tokens mint locally; capture the resource↔service `client_id` mapping convention.
2. **P3 ([1.5] groundwork)**: expand the AIB-deployability prerequisite to name the concrete items proven here — public base image, chart schema fix, JWE/encryption key + preauth values, **memory backend as the default** (defer Postgres/operator), build-and-`kind load` because images are unpublished, and a working web toolchain only when the consent UI is needed.
3. **P2 (gateway/access-check)**: note that `client_credentials` is already served on `/oauth2/token` (the gap is ProxyClient vs LocalClient handling, not a missing endpoint), and that the gateway target must cover both Envoy `ext_authz` and agentgateway (AIB's compose ships agentgateway, not Envoy).
4. **P9/P11 (upstreaming)**: flag the `zalando-infosec` upstream-access question as a precondition for upstreaming the SDK and AIB API extensions; decide fork-vs-contribute before those phases.
5. **Testing note**: prefer in-cluster pods for any gateway↔access-check validation; avoid local Envoy↔host-process wiring (Docker-Desktop networking quirk).
6. **Sequencing**: no phase reordering is required — P0 confirms the bottom-up order holds; the access-check decision logic, token mint, propagation, sync, and KIND deploy all work with the existing AIB, so P1–P6 can proceed as planned.
