# P0 — Feasibility validation and hypothesis testing (learnings)

**Phase**: P0 of [`../../security-and-identity/plan/proposed-split.md`](../../security-and-identity/plan/proposed-split.md)
**Date**: 2026-06-21

This is the most consequential P0 output: what was confirmed, what surprised us, the groundwork uncovered, and the concrete changes proposed for `proposed-split.md`. The proposed plan-deltas at the end are **for review, not yet applied**.

## Hypotheses

| # | Hypothesis | Result |
|---|---|---|
| H1 | The synthetic-service + PermissionSet + scope encoding can represent a KAOS actor→resource edge | Confirmed |
| H2 | A KAOS agent can obtain an AIB-signed actor token | Confirmed — **when the agent is registered as a LocalClient** (see below) |
| H3 | The allow/deny decision (keyed on the actor) is computable from AIB data | Confirmed, including fail-closed |
| H4 | Two-identity (subject + actor) propagation works across hops with per-hop actor override | Confirmed |
| H5 | KAOS resources can be projected into AIB to drive the decision end to end | Confirmed (from the live KIND cluster) |
| H6 | AIB can be built and deployed to KIND and serve the data plane | Confirmed (with the groundwork below) |

## Key findings

### The decision is data-first and reuses AIB's existing model

An agent's bound PermissionSets carry `service_scopes` of `{service_id, scopes}`; the decision is ALLOW iff some bound permission set covers the target service plus the requested action scope. The resource URI maps to a synthetic AIB service by a stable `client_id` convention (`kaos://mcpserver/<ns>/<name>` ↔ service `client_id` `kaos-mcpserver-<ns>-<name>`), and the requested edge becomes a `call` scope on that service. This is the bootstrap encoding the ADRs describe, and it works against the unmodified AIB data model.

### How an agent gets its actor token — and why "LocalClient" is the design choice

**Terminology first, because the names are misleading.** In the target architecture every calling agent needs its **own** short-lived identity token (the "actor token") that the gateway validates and the access-check decides on. The agent obtains that token by making a **plain HTTP `POST /oauth2/token`** call to AIB with the OAuth2 `client_credentials` grant — it presents its own client id + secret and gets back a signed JWT:

```
POST http://<aib>/oauth2/token
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials&client_id=<id>&client_secret=<secret>&scope=call
→ { "access_token": "<ES256 JWT>", "token_type": "Bearer", ... }
```

Two clarifications that matter for the Python SDK:

- **This is just an HTTP call.** In P0 the "agent" was literally `curl`; the Python SDK does the same with `httpx`. There is **no Go client library** to package — "LocalClient/ProxyClient/CIMDClient" is **not** an SDK, it is a **server-side classification AIB applies to the stored agent record** (`Agent.ClientType()` in `internal/domain/storage/agent.go`). The word "client" there means "OAuth2 client registration" (the agent as a registered OAuth2 client), not a library.
- **The agent never mints its own token.** "Local" describes where **AIB** produces the token, not the agent. The agent always calls AIB over HTTP for every token. The realistic lifecycle: the pod holds a **long-lived credential** (client id + secret in a Secret); the SDK exchanges it at AIB's `/oauth2/token` for a **short-lived actor token** (~1h TTL) and refreshes ahead of expiry. So AIB is contacted for every token issuance (cached + refresh-ahead, not on every request).

**The three agent kinds** AIB assigns from the fields set on the agent record:

- **LocalClient** — the agent record has *no* `client_id` and *no* `client_uris`. **AIB itself mints** the JWT, signing it with AIB's own keys. AIB *is* the agent's identity authority.
- **ProxyClient** — the agent record has a `client_id`. This declares that the agent's credential is issued by a **separate upstream OAuth2 server**, and AIB does **not** mint — it **forwards** the token request to that upstream (`oauth2_authorization_server.proxy.upstream_token_endpoint`) and relays the result. This upstream is an *agent-credential* authority, **not** the human/user IdP (see below).
- **CIMDClient** — the agent record has `client_uris`, i.e. the `client_id` is an **HTTPS URL serving a Client ID Metadata Document** (JSON) that AIB fetches and validates (SSRF-hardened, cached; AIB ADR-015). It is designed for public/native agents that self-describe via a URL instead of pre-registering a secret.

The broker runs in **hybrid** mode, which accepts all three kinds, so *registration* succeeds regardless. The difference only appears at **mint time**: for a **ProxyClient** the `client_credentials` request is forwarded to the upstream OAuth2 server — and in our setup there is no such upstream behind these synthetic KAOS agents, so the forwarded request fails (HTTP 500). Only a **LocalClient** mints directly from AIB.

**Design decision (confirmed): KAOS agents are registered as LocalClients.** AIB is the agent identity authority in the KAOS design (ADR-KAOS-001: "Keycloak issues human tokens only; AIB issues agent identities"), so a KAOS agent is a LocalClient — registered **without** `client_id`/`client_uris`. Minting then returns a proper ES256-signed JWT whose `sub`/`agent_id` equal the agent's AIB UUID and whose `scope` is the granted action, validatable against AIB's JWKS. The KAOS→AIB sync service must therefore create each agent record without a `client_id`.

**Why not ProxyClient, given a user IdP is on the roadmap.** These are two **independent identity planes** and must not be conflated:

- **User (human) identity** → Keycloak/OIDC. This is the IdP on the roadmap; it authenticates **people** and produces the *subject* token.
- **Agent (actor) identity** → **AIB issues it**; AIB is the agent authority and produces the *actor* token.

ProxyClient is about the *agent's own credential* being backed by a **separate upstream agent-credential OAuth2 server** — not by the user Keycloak. Adding Keycloak for users therefore does **not** make agents ProxyClients. ProxyClient would only be relevant if we deliberately introduced an external authority that issues *agent* credentials and wanted AIB to front it — which is not the current design.

**CIMDClient is out of scope for KAOS.** We control agent registration through the sync service and provision a real secret into the pod, so URL-based self-description adds no value for cluster-internal agents. It is noted only for completeness.

### Access check and propagation

The access check reuses AIB's JWKS for actor-token signature validation and returns allow/deny with a reason (`granted`, `grant_missing`, `resource_unknown`, `unauthenticated`, `invalid_actor_token`). Both the SDK JSON contract (`POST /api/access/check`) and an `ext_authz` HTTP surface (200 allow / 403 deny keyed on `x-agent-authorization`) behave correctly and fail closed.

Propagation is straightforward: extract trusted inbound headers (`x-request-id`, `x-principal`, `x-actor`, `authorization`, `x-agent-authorization`), generate a request id when absent, inject on outbound, and override only the **actor** per hop so each agent authenticates as itself while the user **subject** is carried unchanged — exactly the mechanism that makes multi-agent decisions key on the actor rather than the subject `azp`.

### What is genuinely new on the AIB side

`client_credentials` is **already** served on AIB's main `/oauth2/token` endpoint, so actor-token minting needs only correct registration (LocalClient), **not** a new endpoint. The genuinely new AIB-side work is the **access-check decision surface** (`check_access` / `POST /api/access/check` for SDKs, plus an Envoy `ext_authz` Check service for the gateway). KAOS targets the **Envoy gateway** (the existing KAOS Gateway choice). AIB's own dev stack happens to ship `agentgateway` (agentgateway.dev) with an `extProc` policy, but we do not adopt it; the access-check satisfies the standard Envoy `ext_authz` 200-allow/403-deny contract.

## Groundwork uncovered (the deployability reality)

AIB is buildable and deployable, but it is **a private, not-yet-released project**: it publishes no images or charts, and several gaps had to be closed to stand it up. These are not incidental fix-ups — they are **foundational work** that KAOS depends on and that should be structured for eventual upstream contribution (see proposed change 2).

- **Container base image**: the production, extproc, and migrate Dockerfiles defaulted to a private `container-registry.zalando.net` base that is not publicly pullable. Fixed on the AIB branch to default to public `alpine:3` (override preserved via `BASE_IMAGE`).
- **Helm chart schema**: the chart's own default values failed its `values.schema.json` (`awsKms.dynamodbTimeout` undeclared with `additionalProperties:false`). Fixed on the AIB branch.
- **Chart requires explicit secrets/auth**: it does not inject the JWE/encryption keys or an auth method by default. A working install must set `broker.thirdPartyOauth2.jweSigningKey`, `broker.encryption.memory.rawKey`, and `broker.server.{enduser,admin}.authentication.preauth.principalHeaderName`.
- **Storage**: `storage.type=memory` deploys cleanly with no Postgres and no migration job; the Postgres path depends on the Zalando postgres operator (`acid.zalan.do`). Memory backend is the right default for dev/CI/MVP installs.
- **Frontend build**: the broker image expects a built consent UI, and `just web-build` fails with `tsc: command not found` (web toolchain/deps incomplete). The API/data plane does not need the UI; a stub `web/dist/consent` is enough for data-plane validation, but a real image needs a working web build.
- **Images/charts are unpublished**: because AIB is unreleased, installs must build images and load them into the cluster (`kind load`). The full recipe is captured in `tmp/security/CI-RECIPE.md`.

## AIB-side contribution model

The cloned AIB upstream is `github.com/zalando-infosec/agentic-identity-broker`. We **do** have access, but we will **not** push to it directly — upstream contributions go through a **fork** with the appropriate credentials, handled once the work is ready. For now the AIB-side fixes live on a local branch (`feat/p0-access-check-validation`), validated locally (`just test` green), and this report goes to issue #231. The focus during the build phases is to produce clean, **stacked branches/commits** that a later phase can contribute upstream from a fork.

A local-networking caveat for future local gateway tests: putting a real Envoy in front of a host-process access-check hit a Docker-Desktop-macOS quirk (`host.docker.internal` resolved IPv6-only; Envoy's container→host call would not connect). This is an environment artifact only — in-cluster, gateway and access-check are pods with normal DNS — but it means local Envoy↔host-process wiring should be avoided in favour of in-cluster pods.

## Proposed changes to `proposed-split.md` (for review — not applied)

These are concrete edits I propose making to the work-split plan based on what P0 proved. Each says what the plan currently implies, what to change, and why. **None are applied yet — they are here for your decision.**

1. **Record the LocalClient registration rule in the sync phases (P3 and P5).** The plan describes the sync service projecting agents, edges and credentials into AIB, but does not say *how* an agent must be registered for token minting to work. Change: state explicitly that the KAOS→AIB sync registers every KAOS agent as an AIB **LocalClient** — creating the agent record *without* a `client_id`/`client_uris` — because AIB is the agent identity authority (it mints the actor token itself); a `client_id` would make the agent a ProxyClient whose token request AIB forwards to a (nonexistent) upstream and fails. Also record the encoding's fixed naming convention: resource URI `kaos://mcpserver/<ns>/<name>` ↔ synthetic service `client_id` `kaos-mcpserver-<ns>-<name>`, requested edge → PermissionSet `call` scope on that service. This makes the sync service's data contract unambiguous.

2. **Restructure the AIB-side work as a stack of branches founded on a new ADR-AIB-000, because AIB is private/unreleased.** The plan currently treats AIB deployability as a one-line "[1.5] prerequisite" and assumes published charts/images will exist. They do not — AIB ships no images or charts yet, so the deployability groundwork is **foundational AIB work**, not setup. Change: model the AIB-repo work as **stacked PRs/branches**, bottom to top:
   1. **Foundation (base branch)** — the deployability groundwork as a coherent foundation: public base image, a Helm chart that validates its own defaults and runs on the **`memory` backend by default** (no Postgres/operator), explicit JWE/encryption-key + pre-auth wiring, and an image-build/`kind load` path (a working web/consent-UI toolchain only when the UI is in scope). Document this foundation in a **new `ADR-AIB-000`** (the foundations the rest of the AIB work and the KAOS integration depend on, including the chart/image story). The two P0 fixes (alpine base, chart schema) are the first commits on this branch.
   2. **Access-check API branch** — `check_access` / `POST /api/access/check` + the Envoy `ext_authz` Check service, stacked on the foundation branch.
   3. **SDK branch** — the AIB Python SDK, stacked on the access-check branch.
   This keeps each layer reviewable on its own and ready for upstreaming in order.

3. **State that the only new AIB capability for the gateway phase (P2) is the access-check, and target Envoy.** The plan implies AIB needs new token *and* access-check capability. Change: note that `client_credentials` is **already** served on `/oauth2/token`, so actor-token minting needs only correct registration (LocalClient, per item 1) — the genuinely new AIB code is the **access-check** (`check_access` / `/api/access/check` + Envoy `ext_authz` Check). KAOS targets the **Envoy gateway** (the existing choice); note `agentgateway` exists in AIB's dev stack but is not adopted now.

4. **Add a dedicated upstream-contribution phase (new `P<n>`), via fork.** The plan assumes the SDK and AIB API extensions are "upstreamed to AIB" inside the productionisation phases. Change: pull the upstreaming out into its **own phase** whose job is to contribute the stacked AIB branches (foundation → access-check → SDK) upstream **from a fork**, using the appropriate credentials, once the work is ready. Record that we have access to `zalando-infosec/agentic-identity-broker` but deliberately do **not** push to it directly; near-term build phases just produce clean stacked branches/commits that this phase later contributes.

5. **Add a testing guidance note.** Change: any gateway↔access-check validation should run with both components as **in-cluster pods** (normal cluster DNS); avoid wiring a containerised gateway to a host-process service locally (on Docker-Desktop/macOS `host.docker.internal` resolved IPv6-only and the gateway could not reach a host-bound process). Environment artifact, not architecture — but it saves time later.

6. **Confirm no phase reordering is needed.** P0 validated the decision logic, token mint, propagation, sync, and a KIND deploy against the *existing* AIB, so the bottom-up sequence holds and P1–P6 can proceed as planned. (A confirmation, plus the additions in items 2 and 4: a new `ADR-AIB-000` and a new upstream-contribution phase.)
