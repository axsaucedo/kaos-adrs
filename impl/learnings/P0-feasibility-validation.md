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

### The most important runtime finding: how an agent gets its own token depends on how it is registered

Background: in the target architecture every calling agent needs its **own** short-lived identity token (the "actor token") that the gateway validates and the access-check decides on. The agent obtains that token by calling AIB's OAuth2 token endpoint with the OAuth2 `client_credentials` grant (it presents its own client id + secret and gets back a signed JWT). P0 had to confirm AIB can actually issue such a token for a KAOS agent.

What we found: AIB does not treat every registered agent the same way. When AIB registers an agent it classifies it into one of three kinds based on which fields are set on the agent record (`Agent.ClientType()` in `internal/domain/storage/agent.go`):

- **LocalClient** — the agent record has *no* `client_id` and *no* `client_uris`. AIB is the agent's own identity provider: it mints the token itself, locally.
- **ProxyClient** — the agent record has a `client_id`. This means the agent's "real" identity lives in an *upstream* OAuth2 server (e.g. an existing corporate IdP), and AIB is configured to forward/proxy token requests to that upstream rather than mint them.
- **CIMDClient** — the agent record has `client_uris` (Client ID Metadata Document URLs); a discovery-based variant.

The broker in P0 runs in **hybrid** mode, which accepts all three kinds, so registration *succeeds* regardless. The problem only appears at token-mint time: for a **ProxyClient**, a `client_credentials` request is forwarded to the upstream OAuth2 server — but in our setup there is no real upstream IdP behind these synthetic KAOS agents, so the forwarded request fails (HTTP 500). Only a **LocalClient** mints a token directly from AIB.

So the rule is simply: **to get an AIB-issued actor token, a KAOS agent must be registered as a LocalClient — i.e. registered *without* a `client_id` (and without `client_uris`).** When registered that way, the mint succeeds and returns a proper ES256-signed JWT whose `sub`/`agent_id` claims equal the agent's AIB UUID and whose `scope` is the granted action; it validates against the broker's JWKS. The practical consequence for KAOS: the **KAOS→AIB sync service must create each agent record without a `client_id`**, because KAOS agents are identities that AIB itself issues — they are not proxies for some pre-existing upstream OAuth2 client. (A `client_id`/`client_uris` would only be appropriate later if a KAOS agent's identity were meant to be backed by an external IdP, which is not the current design.)

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

These are concrete edits I propose making to the work-split plan based on what P0 proved. Each says what the plan currently implies, what to change, and why. **None are applied yet — they are here for your decision.**

1. **Record the LocalClient registration rule in the sync phases (P3 and P5).** The plan currently describes the sync service as projecting agents, edges and credentials into AIB, but does not say *how* an agent must be registered for token minting to work. Change: state explicitly that the KAOS→AIB sync registers every KAOS agent as an AIB **LocalClient** — i.e. creates the agent record *without* a `client_id`/`client_uris` — because KAOS agents are identities AIB issues itself (not proxies for an upstream IdP); otherwise actor-token minting fails (see the runtime finding above). Also record the fixed naming convention the encoding relies on: a resource URI `kaos://mcpserver/<ns>/<name>` maps to an AIB synthetic service whose `client_id` is `kaos-mcpserver-<ns>-<name>`, and the requested edge becomes a PermissionSet scope `call` on that service. This makes the sync service's data contract unambiguous.

2. **Make the AIB-deployability groundwork in P3 concrete instead of a one-line "[1.5] prerequisite".** The plan currently lists "AIB deployability groundwork" abstractly. Change: enumerate the specific prerequisites P0 proved are needed to stand AIB up in a cluster, so the integration/install phase can plan them as real work: (a) the container images must use a publicly pullable base — the upstream Dockerfiles used a private Zalando registry (now fixed to `alpine:3` on our AIB branch); (b) the Helm chart's `values.schema.json` must accept the chart's own defaults — it didn't (now fixed); (c) the install must supply a JWE signing key, an encryption raw key, and a pre-auth principal header, or the broker crash-loops; (d) **default the install to the `memory` storage backend** so no PostgreSQL/operator is required for dev/CI/MVP (Postgres is a later, heavier option); (e) because AIB publishes no images, the installer must build images and load them into the cluster (`kind load`), so image-build/publish is itself a task; (f) a real broker image needs a working web (consent UI) build toolchain, which is only required when the UI is in scope — the API/data plane does not need it.

3. **Clarify the AIB-side gap for the gateway/access-check phase (P2).** The plan implies AIB needs new token + access-check capability. Change: note that the `client_credentials` grant is **already** served on AIB's main `/oauth2/token` endpoint, so minting actor tokens needs *correct agent registration* (LocalClient, per item 1), not a new endpoint — the only genuinely new AIB code for P2 is the access-check decision surface itself. Also record that AIB's own dev stack ships **agentgateway** (agentgateway.dev), not Envoy, and uses an `extProc` policy today; the access-check we validated satisfies the standard `ext_authz` 200-allow/403-deny contract, which is portable across both Envoy and agentgateway, so P2 should target that contract rather than a specific gateway implementation.

4. **Flag the AIB upstream-access question as a precondition for the upstreaming phases (P9 and P11).** The plan assumes the SDK and the AIB API extensions are eventually "upstreamed to AIB". Change: record that the cloned AIB's upstream is `github.com/zalando-infosec/agentic-identity-broker`, to which we currently have no push/PR access — so the upstreaming phases first need a decision: obtain access to that repo, or maintain a fork. This is a prerequisite to schedule those phases, not a code task.

5. **Add a testing guidance note.** Change: add a short note that any gateway↔access-check validation should run with both components as **in-cluster pods** (normal cluster DNS), and that wiring a containerised gateway to a host-process service locally should be avoided — on Docker-Desktop/macOS `host.docker.internal` resolved IPv6-only and the gateway could not reach a host-bound process. This is an environment artifact, not an architecture issue, but it will save time in later phases.

6. **Confirm no phase reordering is needed.** Change: add a sentence stating that P0 validated the decision logic, token mint, propagation, sync, and a KIND deploy all work against the *existing* AIB, so the bottom-up sequence holds and P1–P6 can proceed as planned. (Included for completeness — this item is a confirmation, not an edit to the phases.)
