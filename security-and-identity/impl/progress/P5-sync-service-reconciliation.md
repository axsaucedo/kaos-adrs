# P5 — Sync service to MVP-robust (progress)

**Phase**: P5 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P5-sync-service-reconciliation.md`](../../plan/P5-sync-service-reconciliation.md)
**Status**: Complete — the sync service is now an MVP-robust reconciler with ModelAPI projection, pruning, drift reporting and observability, validated on local KIND.
**Date**: 2026-06-22
**PR**: axsaucedo/kaos#235 (stacked onto `feat/aib-install-and-sync`, the P3 branch)

## Outcome

The P3 sync service was a minimal projector — MCPServer edges only, create/update, no pruning, no observability, and a pass that aborted on the first failure. P5 hardens it into a reconciler suitable for an MVP deployment: it projects ModelAPI edges alongside MCPServer edges, prunes broker records and credential Secrets that no longer correspond to a live KAOS resource, isolates per-resource failures into categorized problems without aborting the pass, retries transient broker errors with bounded backoff, and exposes Prometheus metrics plus liveness/readiness endpoints. The chart grants the secret-delete permission pruning needs and wires the metrics/health ports, probes and tuning knobs.

## Deliverables

| Area | Deliverable |
|---|---|
| Broker admin client | `aib_client.py` — `list`/`get`/`delete`/`revoke_credentials` plus a `_request` wrapper with bounded exponential-backoff retry over transport errors and 5xx; 404 on delete/revoke is treated as already-gone. |
| ModelAPI projection | `projection.py` refactored onto a shared kind-keyed edge shape; `Agent → ModelAPI` edges become `kaos-modelapi-<ns>-<name>` services and `kaos:modelapi:<ns>:<name>:call` permission sets; agents are projected when they declare any edge. |
| Pruning | Ownership predicates + `parse_agent_external_id` in `projection.py`; `reconcile._prune` deletes orphaned KAOS-owned agents (revoking credentials), Secrets, permission sets and services in dependency-safe order; `KubeSecretStore.list`/`delete` (label-scoped, 404-tolerant). |
| Drift/status | `ProblemCategory` enum + `Problem` dataclass; `ReconcileSummary.problems`/`ok`; `AgentSync.ok`/`error`; every operation wrapped so a single failure is recorded and the pass continues (agents missing a permission set fail closed). |
| Observability | `observability.py` — Prometheus counters/gauges, `record_summary`, `HealthState`, pure `handle_path` routing, threaded `start_http_servers` for `/metrics`, `/healthz`, `/readyz`. |
| Chart/RBAC | secrets RBAC gains `delete`; deployment exposes metrics/health container ports, liveness (`/healthz`) and readiness (`/readyz`) probes, and the new env; `values.yaml` surfaces pruning, retry and observability settings. |

## Validation

- **Unit tests**: 45 tests green across projection, reconcile (prune + isolation), aib_client (list/delete/404/retry), observability and config; `black --check` and `uvx ty check` clean.
- **Helm**: `helm lint` + `helm template` render the new RBAC verb, ports, probes and env.
- **Local KIND (`kind-kaos-e2e`)**: built and loaded the sync image, installed the chart pointed at an unreachable broker. The pod reached `1/1` Ready (readiness flips after the first pass), `/readyz` returned `200 ready`, and `/metrics` exposed `kaos_sync_reconcile_passes_total`, `kaos_sync_reconcile_problems_total{category="aib_unreachable"}` and the projected-count gauges. Logs confirmed the fail-open loop: broker `Connection refused` recorded as `aib_unreachable` problems without crashing the process.
- **CI (PR #235)**: Python Tests `sync-tests` job green; E2E suite dispatched on the branch (stacked PRs into non-main bases require manual dispatch).

## Notes

- The full broker-backed reconcile/prune lifecycle e2e (create → update → delete-prune against a live broker) remains local-KIND only while the broker is unpublished; the local validation above exercised the runtime, chart, RBAC, fail-open loop and observability in a real cluster against an unreachable broker.
- Sync-service CI runs `black --check` + pytest (not `ty`); `ty` is kept clean locally via `make lint`.
- Out of scope (later phases): active credential rotation, watch-based incremental reconcile, leader election, CRD `.status` integration, A2A edge projection, and the native broker resource-grant model.
