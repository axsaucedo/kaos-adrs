# Feasibility validation and hypothesis testing — implementation plan

**Branch (KAOS)**: `feat/agent-identity-broker` (validation harness under `./tmp/security/`, gitignored)
**Branch (AIB, local-only)**: `feat/p0-access-check-validation` (later renamed `feat/aib-deployability-foundation`); upstream is `zalando-infosec`, no PR access
**Tracking issue**: axsaucedo/kaos#231

## Execution rules (TOP PRIORITY — every task)

- Validation-first: prove each load-bearing hypothesis with a working, repeatable check before any production code is written elsewhere. Capture findings and plan-deltas in `impl/learnings/`.
- Artifacts live in the KAOS repo `./tmp/security/` (gitignored); noise -> `./tmp/null`. AIB work stays on local branches (no push to the private upstream).
- Output is a go/no-go decision plus concrete deltas to feed into `proposed-split.md` and the downstream phase plans.

## Problem statement

Before building production code, prove the whole identity/authorization approach is viable against a live Agentic Identity Broker (AIB): that the synthetic-service/PermissionSet encoding can express an actor→resource edge, that agents can mint AIB-signed actor tokens, that an allow/deny decision keyed on the actor is computable and gateway-callable with fail-closed semantics, that two-identity propagation works across hops, that KAOS resources can be projected into AIB, and that AIB can actually be built, Helm-installed, and run in a cluster.

## Current-state grounding (researched)

- AIB exposes an admin API (agents, services, permission-sets, agent client-credentials) and a `client_credentials` mint usable by LocalClients; `storage.type=memory` installs with no Postgres.
- The decision model is data-driven: edges are encoded as PermissionSets over synthetic services; the access decision can be derived from seeded records.
- AIB chart and container images need small fixes (public base image, values-schema) to build and deploy outside the upstream CI environment.

## Design plan (how it fits)

Stand up AIB locally (Docker Compose) and in KIND (memory backend); drive each hypothesis with a thin, scripted probe rather than committed product code. The access-check is exercised as an external probe (`accesscheck/app.py`) against a local Envoy `ext_authz`, deliberately deferring the in-AIB `/api/access/check` to the gateway-enforcement phase. Propagation is validated with a small Python script simulating the SDK's two-identity headers across hops. Sync is validated with a prototype that projects KAOS resources into AIB. Deployability findings become the foundation groundwork (ADR-AIB-000) and the plan-deltas this phase feeds back.

## Numbered TODOs

1. **AIB up + health.** Bring the AIB compose stack up (broker, agentgateway, mocks) and confirm health. **Validate**: `00-up.sh` healthy.
2. **Encoding + actor-token mint + decision-from-data.** Seed the synthetic-service/PermissionSet encoding (H1), mint an actor token via `client_credentials` (H2), and derive the decision from seeded data (H3). **Validate**: `10-seed-decision.sh` 7/7.
3. **Access-check service contract + ext_authz.** Exercise the access-check JSON contract and Envoy `ext_authz` 200/403 for allow/deny/fail-closed. **Validate**: `20-access-check.sh` 8/8.
4. **Two-identity propagation.** Simulate the SDK propagation slice (forward user subject, attach agent actor) across A→B→C with request-id and per-hop actor override. **Validate**: `30-propagation.py` 8/8.
5. **KAOS→AIB sync.** Project KAOS resources from a live KIND cluster into AIB, then confirm the decision honours the requested edges. **Validate**: `40-sync.sh` 5/5.
6. **In-cluster deployability.** Build AIB and Helm-deploy to KIND (memory backend); seed+mint+decision in-cluster. **Validate**: 7/7 + in-cluster checks. Capture deployability groundwork (public alpine base image, `awsKms.dynamodbTimeout` schema fix) on the AIB branch.
7. **Findings + plan-deltas.** Write `impl/progress` + `impl/learnings` (P0); fold the deltas (LocalClient design, deployability foundation) back into `proposed-split.md` and copy this plan to `plan/P0-feasibility-validation.md`.

## Validation per task

Each probe is a self-checking script returning a pass count; the full set is reproducible from `CI-RECIPE.md`. Go/no-go is granted only when every hypothesis passes both locally (Docker Compose) and deployed to KIND.

## Commit / PR strategy

- KAOS (`feat/agent-identity-broker`): ignore the nested `agentic-identity-broker/` clone; markdown no-hard-wrap convention. Validation harness stays gitignored under `./tmp/security/`.
- AIB (`feat/p0-access-check-validation`, local-only): default container images to public `alpine:3`; declare `awsKms.dynamodbTimeout` in the chart values schema. Not pushed (private upstream).
- Findings documented in `impl/learnings/P0-feasibility-validation.md`.

## Out of scope (later phases)

The committed in-AIB access-check Go service + gateway `ext_authz` (P2), the productionised propagation SDK (P1/P9), the in-cluster install + sync service (P3/P5), user auth (P6), `ext_proc` token exchange (P7), and CRD identity override (P8). P0 only de-risks; it ships no production code.
