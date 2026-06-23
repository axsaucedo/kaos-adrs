# P10 — sync service productionisation (progress)

**Phase**: P10 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P10-sync-service-productionisation.md`](../../plan/P10-sync-service-productionisation.md)
**Status**: Implementation complete (extraction deferred). The in-repo sync service moves from a single-replica fixed-interval poll loop to a productionised reconciler: it reacts to KAOS resource changes via a debounced watch, elects a single active leader so it can run as an HA Deployment without double-minting/pruning, proactively rotates aging agent client secrets within the broker's grace window, writes per-resource sync state back onto the KAOS objects as annotations, and ships as a versioned, published `axsauze/kaos-sync` image whose chart tracks the release. Repo extraction (TODO 6) is deliberately deferred to a manual post-P12 step.
**Date**: 2026-06-23
**PR**: stacked onto `feat/sdk-token-lifecycle` (the P9 branch)

## Outcome

P5 made the sync service correct and observable but it was still a single process that only polled and only minted. P10 closes the productionisation gap without re-doing any P5 work — every new path is additive and flag-gated where it changes a default:

- **Watch-based incremental reconcile**: a background watch over the three CRD list endpoints sets a dirty flag on any change; a debounced worker runs a full idempotent `run_once` on dirty (coalescing bursts) and on a periodic safety-net resync. Watch disconnects never crash the loop — they fall back to a full resync and re-watch. `run_once`'s contract is unchanged.
- **Leader election**: a `coordination.k8s.io` Lease elects one active reconciler (holder = `POD_NAME`/hostname). Only the leader runs the watch + reconcile worker; a relinquished leader stops minting/pruning immediately and re-contends. Renewal failure or a backend error relinquishes leadership rather than crashing. Election is on by default and can be disabled for a simple single-pod install. A standby replica still passes its readiness probe.
- **Active credential rotation**: each minted Secret is stamped with `kaos.dev/aib-credential-rotated-at`; when rotation is enabled and a Secret is older than the configured interval, the reconciler re-mints the agent's credential and writes the new client secret into the same Secret in place. The broker keeps a grace window on the previous secret and the Secret is never emptied first, so running pods (and the P9 SDK file-reload) pick up the new value before the old one is retired. Off by default.
- **CRD status / annotation write-back**: after each pass the service patches additive `kaos.dev/aib-*` annotations onto each source Agent/MCPServer/ModelAPI (`aib-synced-at`, `aib-external-id`, `aib-sync-status` ok/drift/error, `aib-sync-message`). The patch touches only `metadata.annotations`, so it never clobbers spec or fights the operator; a patch against a deleted object is ignored and write-back is best-effort (never fails a pass). On by default.
- **Versioned image + chart packaging**: the release image pipeline builds and publishes the multi-arch `axsauze/kaos-sync` image, and the sync chart version/appVersion (and package version) advance in lockstep with the rest of the project; the chart image tag defaults to the chart appVersion so it tracks the release.

## Deliverables

| Area | Deliverable |
|---|---|
| Watch | `sync-service/kaos_sync/k8s.py` — `WatchEvent` + `KubeWatchSource` (background watch threads over the three plurals, 410/expired-RV fallback to full resync). `main.py` — `DirtyTracker` + debounced `reconcile_loop`. `config.py` — `watch_enabled` / `watch_debounce_seconds`. |
| Leader election | `k8s.py` — `KubeLeaseBackend` (acquire/renew/takeover over `coordination.k8s.io/v1` Lease, lost-update race → not-acquired). `main.py` — `LeaderElector` (transition callbacks, never raises) + `_WorkerHandle` (guarded worker that cannot mint/prune after losing leadership). `config.py` — `KAOS_SYNC_LEADER_*`. Chart Role gains `leases` get/create/update. |
| Credential rotation | `reconcile.py` — `CREDENTIAL_ROTATED_AT_ANNOTATION`, `_rotation_due`, in-place re-mint, `AgentSync.credentials_rotated`. `k8s.py` `KubeSecretStore` — annotation read/write (`get_annotation`, `upsert(..., annotations=)`). `config.py` — `KAOS_SYNC_CREDENTIAL_ROTATION_SECONDS` (0 = disabled). `observability.py` — `credentials.rotated` metric. |
| Status write-back | `reconcile.py` — `ResourceSync`, `ReconcileSummary.resources`, `status_annotations(...)`, `AIB_*` annotation keys; per-service/per-agent results + identity-conflict drift entries. `k8s.py` — `KubeStatusWriter.patch_annotations` (merge patch on `metadata.annotations` only, 404-tolerant). `main.py` `run_once` — best-effort write-back. `config.py` — `KAOS_SYNC_STATUS_ANNOTATIONS_ENABLED` (default on). Chart Role gains `patch` on the three CRDs. |
| Packaging | `.github/workflows/reusable-build-images.yaml` — `build-sync` + `merge-sync` jobs for `axsauze/kaos-sync` (context `sync-service`, multi-arch). `release.yaml` — sync chart version/appVersion sed in `build-helm` and `bump-version`; sync package version in `bump-version`. `sync-service/chart/Chart.yaml` — realigned to the current version line. |

## Validation

- **Unit tests**: `cd sync-service && python -m pytest tests/ -q` → 75 passed; `black --check kaos_sync tests` clean. Coverage added for: watch-driven reconcile + burst coalescing + disconnect resync; leader acquire/relinquish/standby/backend-error; rotation due/not-due/disabled + annotation stamping; status write-back ok/drift/error + disabled + annotations-only patch body; config knobs.
- **Chart**: `helm template sync-service/chart` renders the `leases` and CRD-`patch` RBAC and resolves the image to `axsauze/kaos-sync:<appVersion>`; `--set image.tag=test` override verified.
- **Image**: `docker build sync-service` succeeds.
- **Workflows**: `release.yaml` and `reusable-build-images.yaml` parse as YAML.
- **Full productionisation in-cluster e2e** (watch latency, leader failover, live rotation across the grace window, annotation write-back on real objects): folded into the dedicated genuine end-to-end validation block that runs after P4, because a real end-to-end check needs the P4 NetworkPolicy to force internal agent→MCP traffic through the gateway (KAOS otherwise injects direct `svc.cluster.local` URLs that bypass the gateway). The branch's CI runs the unit suites; the in-cluster behaviours are validated in that block on the auth-enabled cluster.
