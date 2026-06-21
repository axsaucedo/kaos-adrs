# P0 — Feasibility validation and hypothesis testing (progress)

**Phase**: P0 of [`../../security-and-identity/plan/proposed-split.md`](../../security-and-identity/plan/proposed-split.md)
**Status**: Complete — go.
**Date**: 2026-06-21
**Tracking issue**: axsaucedo/kaos#231

## Outcome

All P0 feasibility tasks pass against a live Agentic Identity Broker (AIB), both in local Docker Compose and deployed to a KIND cluster. The target architecture's load-bearing hypotheses are validated: the synthetic-service/PermissionSet encoding expresses an actor→resource edge, agents mint AIB-signed actor tokens, the access decision (allow/deny, keyed on the actor) is computable and gateway-callable with fail-closed semantics, two-identity propagation works across hops, and KAOS resources project into AIB to drive the decision end to end.

## Validation harness (KAOS repo `./tmp/security/`, gitignored)

| Script | Validates | Result |
|---|---|---|
| `00-up.sh` | AIB compose stack up + health (broker, agentgateway, mocks) | pass |
| `10-seed-decision.sh` | Encoding (H1), actor-token mint via client_credentials (H2), decision-from-data (H3) | 7/7 |
| `20-access-check.sh` | Access-check service: JSON contract + ext_authz 200/403, allow/deny/fail-closed | 8/8 |
| `30-propagation.py` | Two-identity propagation across A→B→C, request-id, per-hop actor override | 8/8 |
| `40-sync.sh` | KAOS→AIB sync from the live KIND cluster, then decision honours requested edges | 5/5 |
| in-cluster (T6) | AIB built + Helm-deployed to KIND (memory backend); seed+mint+decision in-cluster | 7/7 + checks |

Supporting artifacts: `accesscheck/app.py` (access-check probe), `sync/sync.py` + `sync/sample-kaos.yaml`, `envoy/envoy.yaml`, `aib-kind-values.yaml`, `CI-RECIPE.md`, `NOTES.md`.

## Commits

- KAOS repo (`feat/agent-identity-broker`): ignore the nested `agentic-identity-broker/` clone; add the markdown no-hard-wrap convention (earlier).
- AIB repo (`feat/p0-access-check-validation`, local — upstream is `zalando-infosec`, no PR access): default container images to public `alpine:3`; declare `awsKms.dynamodbTimeout` in the chart values schema.

The access-check was validated as an external probe rather than committed AIB Go code, deliberately deferring the in-AIB `/api/access/check` + Envoy/agentgateway `ext_authz` to the gateway-enforcement phase.

## Cleanup

Validation scripts remain under the gitignored `./tmp/security/`. The KIND AIB install (`aib-system`) and the local compose stack are torn down after the run; re-run `00-up.sh` and `CI-RECIPE.md` to reproduce.
