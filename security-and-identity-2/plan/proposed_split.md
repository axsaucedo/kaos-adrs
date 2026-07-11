# Proposed work split and sequencing — security & identity phase 2

**Status**: Proposed (v1 — for review; becomes the living plan once approved)
**Date**: 2026-07-11
**Scope**: implementation phasing for [ADR 0001](../adrs/adr_0001_enforcement-topology-pdp-and-policy-delivery.md) (PDP + ext_authz + delivery), [ADR 0002](../adrs/adr_0002_agent-identity-issuers-and-aib-boundary.md) (issuers + AIB boundary), and [ADR 0003](../adrs/adr_0003_authorization-model-and-data-schema.md) (user + agent + resource model). [ADR 0004](../adrs/adr_0004_aib-token-exchange-and-consent.md) (token exchange) is adopted-but-gated and **out of scope here** — it gets its own plan (starting with its spike) after this stack ships.

---

## Purpose

This document proposes how the work is chunked and in what order. One phase = one plan-implement iteration = one PR, merged sequentially into `main`, each building on the previous. Detailed per-phase task breakdowns come after this split is approved.

Phase numbers continue the phase-1 sequence (P0–P17 shipped there); this stack is **two phases, P18–P19**. The work has exactly one load-bearing seam — P18 changes *where* the decision runs, P19 changes *what* it decides — so anything finer than two PRs would be splitting for its own sake.

## Guiding principles

- **Pre-alpha: redesign, don't migrate.** No backwards compatibility is kept anywhere. The phase-1 enforcement wiring (ext_proc-based authorization, the `authorization.provider` knob, AIB-as-enforcement config) is **deleted, not deprecated** — removed in the same PR that replaces it. No compatibility shims, no migration paths, no dual-mode support.
- **No historical documentation.** `docs/security/*` is rewritten to describe the new architecture as if it were the only one that ever existed. Nothing in the KAOS repo references the old design; all historical record lives in this kaos-ai-docs repo. Docs ship in lockstep inside each phase's PR, covering exactly what that phase made true.
- **Build on main.** Each phase starts from merged main (which already contains the phase-1 substrate this design keeps: gateway `jwt_authn` dual providers, `x-kaos-target-resource` stamping, the projection reconciler + policy ConfigMap, NetworkPolicy/strict-gateway, presets). What carries over is the substrate; what gets replaced is the decision point and the model.
- **Enforcement swap first, model on top.** P18 swaps the decision point and the identity issuers while keeping the *existing* actor-only rego, so the whole PR validates against the phase-1 allow/deny matrix; the model change (P19) then lands on a proven enforcement path. One variable per PR: where the decision runs, then what it decides.
- **Every phase is live-demoable in KIND** with a concrete allow/deny matrix, and CI-green before merge.

## Current-state baseline (what main has, relevant to this stack)

- Gateway `jwt_authn` with `user`/`agent` providers; per-route resource stamping; `SecurityPolicy` generation with an optional default-off ext_authz seam.
- `AuthzProjectionReconciler` producing the policy ConfigMap (`policy.rego` + `data.json`, actor-only `data.kaos.grants` + `data.kaos.jwks`), with automated/manual/operator-rego modes and never-prune.
- AIB projection adapter (registration, permission sets, credentials) and the pais propagation SDK (subject propagated unchanged, actor always local).
- `Agent.spec.autonomous` on the CRD; presets `kaos-internal`/`aib-only`/`aib-keycloak`; NetworkPolicy + `strictGatewayApi`.

## The proposed phases

### P18 — The agent plane on the new topology: PDP, ext_authz, and issuers (ADR 0001 + 0002)

**Goal**: the KAOS-run OPA is the enforcement point, the old enforcement path no longer exists, and `kaos-internal` is a zero-external-dependency agent-plane security posture.

**Scope** — enforcement swap and identity swap together, since both rewire the same chart/operator surface and the old path is deleted rather than migrated:

- *PDP + PEP*: chart deploys the stock-OPA PDP (separate Deployment, 2 replicas + PDB, `envoy_ext_authz_grpc`, ConfigMap volume-mounted); operator generates the ext_authz `SecurityPolicy` (gRPC, `failOpen: false`) on all internal routes, with `extAuthzUrl` defaulting to the chart's own PDP Service; `security.pdp.enabled` becomes the authorization switch.
- *Issuers*: the `agentAuth.identity.provider` abstraction (`serviceaccount | oidc | aib`); the ServiceAccount issuer end to end — per-agent SA projected tokens (single audience, kubelet-rotated), file-based token provider in the pais runtime, API-server JWKS injected into `data.kaos.jwks`, identity mapping (`data.kaos.agents[id].issuer_sub`); the AIB adapter reduced to credential provisioning only; the single-issuer-value F0 mechanism.
- *Deleted in the same PR*: the ext_proc enforcement path, the `authorization.provider` knob, permission-set projection from the default path, and all AIB-as-enforcement config/codepaths. Presets rewired: `kaos-internal` = SA issuer + PDP, fail-closed, no demo skips.

The existing actor-only rego and data schema are kept unchanged — this PR swaps *where* the decision runs and *who issues identity*, not *what* the policy decides, so the whole PR validates against the phase-1 allow/deny matrix.

**Demoable**: full enforcement in KIND with no AIB and no Keycloak installed — granted agent→resource allowed, ungranted denied, no-token denied (G1 closed by topology), PDP down → 403, ConfigMap edit propagates within the F4 bound; agent tokens rotate without operator involvement; the `aib`-issuer variation passes the same matrix.

### P19 — The model and the user plane: subject-required conjunction, AccessGrant, Keycloak (ADR 0003 + 0002's DCR)

**Goal**: the user + agent + resource model is live, no subject-less traffic exists, the Keycloak posture works end to end, and the repo tells only the new story.

**Scope** — the model change and its user-plane consumer together, closed out by the docs/deletion sweep:

- *Model*: the new rego — subject always required (user, or agent-identity with the CRD-projected `autonomous` flag), in-policy verification of both tokens, entry-edge vs internal-hop semantics (AccessGrant gates entry; agent grants gate movement); autonomous self-subjecting in the pais runtime (seed own token as subject at loop start); the `AccessGrant` CRD + compiler into `data.kaos.user_grants` + the `Enforced=False/NoUserIdentityProvider` status condition; entry vs internal route policy attachment. The old actor-only rego is deleted.
- *User plane*: the provider-generic `OIDCProjector` (RFC 7591/7592 DCR client-per-agent, Secret delivery, bootstrap token wiring); Keycloak preset provisioning gains the group-membership protocol mapper (documented as a hard requirement for bring-your-own-Keycloak).
- *Coherence sweep (closing tasks)*: remove every remaining reference to the old architecture (flags, dead code, stale comments, old doc pages); rewrite `docs/security/*` as the single coherent description of the shipped design (topology, issuers, AccessGrant guide, published `data.kaos.*` and request-conventions contracts, the "does not support" list from ADR 0003); the CI invariant that externally attached routes always carry the entry policy.

**Demoable**: user with a group AccessGrant reaches the agent, user without is denied at entry; autonomous agent operates end to end self-subjected; non-autonomous agent self-subjecting is denied; internal hops carry and verify the propagated subject; AccessGrant in `kaos-internal` shows `Enforced=False` and flips to enforced when `userAuth` is enabled; all three preset configurations (`kaos-internal`, Keycloak+DCR, Keycloak+AIB-issuer) green on one validation matrix; grep for old-architecture terms returns nothing.

## Execution conventions (apply to every phase plan in this stack)

Each phase's detailed plan and its implementation run follow these rules:

- **Plan before code.** Before starting a phase, put together a comprehensive task plan plus a design note on how the change fits the existing codebase (which files/controllers/charts are touched, what is deleted, how the new pieces slot into current seams). The phase's TODOs are enumerated by number.
- **Tasks are executed one by one, in order, none skipped.** A task is done only when its tests are validated and passing; each completed task is committed individually.
- **Commit style: "comprehensive commit"** — succinct, functional descriptions carrying the context of the work. Commit messages, branch names, and PR descriptions never reference task or phase numbers/identifiers — they describe only *what is being added or changed*.
- **All tests pass** before a task is committed and before the phase's PR is opened.
- **Temporary files live in `./tmp`** (gitignored), never `/tmp` — including any test scripts needing validation. Output suppression uses `./tmp/null` (e.g. `cat > ./tmp/null`) instead of `/dev/null`. This avoids host approval prompts for access outside the repo.
- **REPORT.md at the end of each phase**: when all tasks are finalised, create/overwrite a gitignored `REPORT.md` with a thorough overview of every task requested — the phase's own plus any carried-over prior ones — and each one's completion status. It is **never committed**; its contents are posted as a comment on the phase's GitHub PR as the documentation of record.

## Dependency structure

Strictly linear: P18 → P19. Each is independently mergeable and leaves main in a working, demoable state. If either PR grows unwieldy during detailed planning, the fallback seams are known (P18 could split enforcement vs issuers; P19 could split model vs Keycloak/DCR) — but the default is two.

## Out of scope (tracked, not planned here)

- **ADR 0004 exchange** — own plan after P19, opening with the KIND spike (mock third-party provider) whose go/no-go is recorded against the ADR.
- **KAOS UI workflows** (consent loop surfacing, AccessGrant management) — after the API-level behavior ships.
- The ADR 0003 deferred list (per-user downstream authorization, grant expiry, tool-level granularity) and the OPA bundle-polling evolution from ADR 0001 — revisited on their named triggers.
