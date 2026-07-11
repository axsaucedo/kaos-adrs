# Research 001 — Why AIB cannot authorize internal KAOS traffic (Option 1 evidence)

**Date**: 2026-07-11
**Sources**: live investigation recorded in [aib-ext-proc-limitations](../../security-and-identity/impl/learnings/aib-ext-proc-limitations.md) (verified against merged AIB `#222` in worktree `../aib-222-verify`), [model-parity learnings](../../security-and-identity/impl/learnings/opa-extproc-authz-model-parity-and-oauth-path.md), and a fresh 2026-07-11 inspection of the local `agentic-identity-broker` clone (fork branch `feature/python-sdk` vs `upstream/main`).

This document consolidates the evidence for evaluating **Option 1** (find a workaround so AIB itself delivers authorization). Every avenue explored is listed with why it fails or what it would cost. The verdict: no configuration- or policy-level workaround exists; every viable path requires either an upstream AIB code change or maintaining a diverged fork.

## The structural coupling

AIB `#222` (merged to upstream `main`) embeds OPA inside the ext_proc token-exchange filter. The authorization decision and the RFC 8693 token exchange are wired together such that **authorization only happens on request paths where an exchange happens or is about to happen**:

- **Body-bearing requests** (POST / MCP JSON-RPC): the exchange runs eagerly in the headers phase **before** OPA evaluates (`internal/extproc/server/server.go`, `processRequestHeadersOPA:466-476`). An internal resource fails the exchange with a `500` before OPA is ever consulted.
- **Header-only requests** (GET / SSE): OPA evaluates first and can produce a clean deny (`403`), but on `allow` the code **unconditionally** calls `Exchange(...)` (`processHeadersOnlyOPA:576-584`) — there is no allow-without-exchange branch, so an internal resource still `500`s.
- **No-bearer requests**: the only path that skips the exchange is `passThrough()` when there is no `Authorization` bearer (`processRequestHeadersOPA:407-409`), and that same branch also skips OPA entirely — the G1 autonomous gap.

The decision document cannot express "allow but do not exchange": `Decision.Action ∈ {allow, deny, approval_required, ciba_required}` (`internal/extproc/authorization/decision.go:5-6`), and the non-terminal actions are treated as deny. So "authorized but not exchanged" is not expressible in rego, in config, or in data.

## Why the exchange always fails for internal resources

`TokenExchangeService.Exchange` (`internal/domain/tokenexchange/service.go:168`) requires three things: a registered service whose `protected_resource` matches the target URI (step 8), an active `UserGrant` consent for the (principal, agent) pair (step 9), and a **vaulted third-party OAuth2 session** holding a real access token (step 10). The response *is* that vaulted third-party token — there is no echo/identity mode that returns the original subject token.

Internal KAOS resources (agent→MCP, agent→agent, agent→ModelAPI) have no third-party IdP, so step 10 can never be satisfied legitimately. The failure modes of every seeding workaround were checked:

- **Pre-seeding a `UserGrant`** (trusted-client pattern) removes the consent screen but not the step-10 vault requirement.
- **Injecting a token into the vault out of band** is impossible: the only write path is the interactive OAuth2 authorization-code callback (`internal/domain/oauth2session/service.go:418,511`); the third-party HTTP surface has list/get/delete but **no POST/PUT to seed a session** (`handler.go:608-612`).
- **Registering the internal MCP server as a fake third-party service** and completing a real OAuth flow against a stub IdP would technically satisfy the exchange — but on success ext_proc **replaces the outgoing `Authorization` header with the vaulted token** (`replaceAuthorizationHeader:955`), so the workload receives a fabricated third-party token instead of the user/agent identity it expects. This inverts the design, adds an IdP per internal resource, and provides zero authorization value (the grant evaluation is separate from the swapped token). Actively harmful; rejected.

## Deployment-level blockers (even before the structural ones)

- OPA authorization is **off by default** (`internal/extproc/config/loader.go:76,323`) and the AIB Helm chart provides **no way to turn it on**: `charts/agentic-identity-broker/templates/extproc.yaml:51-75` templates no `EXTPROC_AUTHORIZATION_*` env and no policy volume. Enabling it requires manual deployment surgery.
- Even with surgery, the live experiment ceiling is: **deny (403) demonstrable on GET paths only; allow (200) never** — because allow always triggers the failing exchange. The phase-1 live test matrix never observed a `200` through the route in any of the five identity combinations sent.

## Upstream disposition

- The AIB maintainers confirmed an upstream **ext_authz authorization endpoint will not be added**; `#222` (authz inside the exchange filter) is their answer.
- AIB `#231` ("Permission Sets & Tool Authorization + CIBA") is a **design document only** (no code), scoped to the third-party model; it adds no skip-exchange action and no internal-resource path. Its one useful principle — *"separate authorization from token acquisition"* — supports the Option 2 direction rather than Option 1.
- The upstream changes that *would* unlock Option 1 are known and small in concept: (a) a `skip_exchange`-style decision action that branches to pass-through instead of `Exchange(...)`, or (b) a fail-open exchanger for unmapped internal resources. Both were assessed in phase 1 as upstream contributions AIB has not planned, and the upstream-contribution track was cancelled.

## The fork-only access-check service (the third path, previously abandoned)

A fresh inspection of the local AIB clone shows the KAOS-authored **access-check decision service** still exists on the fork branch `alejandro-saucedo_zse/agentic-identity-broker@feature/python-sdk` (the `#398`/`#399` lineage): an HTTP `POST /api/access/check` decision API, a gRPC `envoy.service.auth.v3.Authorization` (ext_authz) server as a separate binary (`cmd/access-check-grpc/`), a fail-closed decision core over PermissionSets and UserGrants (`internal/domain/accesscheck/service.go:119-163`), and its own ADR (`adrs/029-access-check-decision-service.md`). Notably its data model **does** consult the user dimension: `userGrantRequired(...)` verifies an active `UserGrant` for the (subject principal, agent) pair, so it evaluates user + agent + resource.

Verified branch facts (2026-07-11): the fork branch diverged from upstream at `#396` (`8430bb3c`), is 43 commits ahead (access-check + Python SDK) and 5 behind — and those 5 include `#222` itself, so the fork **lacks** the OPA-in-ext_proc feature and upstream **lacks** access-check (`git ls-tree upstream/main` has no accesscheck files). The two authorization surfaces exist on disjoint branches, and upstream declined this one.

Reviving it would mean maintaining a permanently diverged AIB fork as a KAOS runtime dependency: rebasing 43 commits over upstream's movement, owning images/charts/CVEs for a security-critical component, with no upstream convergence path. Phase 1 already cancelled this track once for exactly these reasons.

## Verdict for Option 1

There is **no workaround within AIB as shipped**. The three theoretical paths are: (a) upstream skip-exchange/fail-open change — not planned, outside KAOS control; (b) fake-third-party vault seeding — structurally impossible to do cleanly and actively harmful when forced; (c) revive the fork's access-check ext_authz — functionally sound (and the only AIB surface that already models user + agent + resource) but a permanent fork-maintenance burden that was already cancelled. Option 1 is therefore not viable as the primary direction; the access-check decision *model* (not its fork) remains a useful reference for [research/003](./003-user-agent-resource-authz-gap.md) and the KAOS-run OPA design in [research/004](./004-keycloak-and-kaos-run-opa-authz-path.md).
