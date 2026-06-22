# P8 — CRD identity override (progress)

**Phase**: P8 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P8-crd-identity-override.md`](../../plan/P8-crd-identity-override.md)
**Status**: Complete — every Agent, MCPServer and ModelAPI now has a first-class logical security identity that defaults to namespace-scoped (`kaos://<kind>/<ns>/<name>`) and can be pinned to a stable, namespace-independent value via `spec.security.id` (`kaos://<kind>/<id>`). The operator resolves the identity, wires it into the agent actor environment, and enforces oldest-wins collision/adoption with a `Failed` status on the loser; the sync projection mirrors the identical resolution and surfaces duplicate-identity conflicts in logs and metrics.
**Date**: 2026-06-22
**PR**: stacked onto `feat/extproc-token-exchange` (the P7 branch)

## Outcome

Before P8 a resource's identity was implicitly its `<namespace>/<name>`, computed ad hoc inside the sync projection; there was no way to give a resource a stable identity that survives a namespace move or rename, and no operator-side notion of identity at all. P8 introduces a single shared identity model used by both the operator (Go) and the sync service (Python):

- **Default**: `kaos://<kind>/<namespace>/<name>` — unique with zero user input, byte-identical to the legacy encoding so existing installs are unchanged.
- **Override**: `spec.security.id: <id>` → `kaos://<kind>/<id>` — namespace-independent, so the resource keeps the same identity (and therefore the same delegated grants and credentials) across a move or rename.

The operator now wires the resolved identity into the agent actor (`AGENT_AUTH_IDENTITY`), and both control-plane components detect duplicate explicit ids and resolve them deterministically (oldest creationTimestamp wins; the loser is marked `Failed` and not provisioned; the survivor adopts the id once the holder is gone).

## Deliverables

| Area | Deliverable |
|---|---|
| CRD surface | `api/v1alpha1/security_types.go` — `SecuritySpec{ID}` (`Optional`, `Pattern ^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$`) + nil-safe `GetID()`; `Security *SecuritySpec` added to `AgentSpec`, `MCPServerSpec`, `ModelAPISpec`. Regenerated deepcopy + `config/crd/bases/*.yaml`; chart CRDs surgically patched (the chart is hand-maintained — `make helm` is destructive). Pattern enforcement verified live via server-side dry-run (`bad/id` rejected). |
| Operator resolver | `pkg/identity/identity.go` — `Kind` consts + `Resolve(kind, ns, name, securityID)`. Agent `buildAgentAuthEnvVars` now sets `AGENT_AUTH_IDENTITY` from `identity.Resolve(... GetID())`. |
| Operator collision/adoption | `pkg/identity/conflict.go` — `Holder`, `LegitimateHolder`, `DetectConflict` (oldest creationTimestamp wins, ns/name tiebreak). Wired into all three controllers: list same-kind, build candidates, detect; loser → `Phase=Failed`, `Ready=false`, message, `RequeueAfter 30s` so it adopts the id once the holder is deleted. |
| Sync projection | `kaos_sync/projection.py` — `resolve_logical_id`/`_logical_path` mirroring the operator; `edge_service_client_id`/`edge_permission_set_name`/`edge_resource_uri`/`agent_external_id` extended with an optional `security_id`; `security_id` on `DesiredService`/`DesiredPermissionSet`/`DesiredAgent`; `IdentityConflict` + `DesiredState.conflicts`; `_resource_identity` + `_winners_and_conflicts`; two-pass `project()` (edge-target security map + dedup). `is_valid_agent_external_id` handles both default (`kaos://agent/<ns>/<name>`) and explicit-id (`kaos://agent/<id>`) external-id forms; `reconcile.py` prune guard updated to use it. |
| Sync conflict surfacing | `ReconcileSummary.conflicts` populated in `reconcile()`; `kaos.sync.identity.conflicts` counter (per `{kind}`) in `observability.py`; conflict count + per-conflict warnings logged in `main.run_once`. |
| Samples + docs | `operator/config/samples/7-stable-identity.yaml` (MCPServer + Agent pinning a stable id, agent edge authorized against the resolved shared identity) + kustomization entry + CLI sample-count test; `security.id` reference sections (default identity, override, resolution table, oldest-wins collision/adoption rule) added to the Agent, MCPServer and ModelAPI CRD docs. |

## Validation

- **Operator unit + fake-client tests**: `go test ./pkg/identity/... ./controllers/...` green — `Resolve` default/override across kinds (88.5% pkg coverage), `DetectConflict` oldest-wins + tiebreak + adoption-after-delete + distinct-ids-no-conflict, and controller conflict tests (older Ready, newer Failed, adoption after delete) via the controller-runtime fake client. `go build ./...` clean. (`make test-unit` coverage recompile hits a local go1.26-vs-go1.25 toolchain mismatch on stdlib — environmental, not code; the actual test packages all report `ok`.)
- **Sync unit tests**: 53 tests green incl. resolution, explicit-id encoding parity, dedup of shared ids, `_winners_and_conflicts`, prune of deleted explicit-id agents, reconcile + observability conflict surfacing. `black --check` + `ty check` clean (only pre-existing `k8s.py` diagnostics).
- **CRD server-side acceptance**: updated CRDs applied server-side; all three sample resources (`spec.security.id` set) accepted; the `^[a-z0-9]...` pattern rejects a slash live.
- **Resolver↔projection parity**: a scratch harness ran identical `(kind, ns, name, id)` cases through the Go `identity.Resolve` and the Python `resolve_logical_id`; output is byte-identical across default and override forms — the cross-component identity contract holds.
- **CLI sample tests**: 16 sample tests green after registering `7-stable-identity` and updating the count assertion.
- **Full auth-enabled e2e** (conflict→Failed, grant survives delete/recreate in another namespace, MCPServer explicit id authorizes an agent edge via ext_authz, no-id regression): exercised in CI on the stacked PR; locally gated on building+loading new operator/agent/sync images, so deferred to CI per the efficiency policy.

## Notes

- **`make helm` is destructive and must not be used for CRD chart sync** — it regenerates the whole chart via helmify, clobbering hand-maintained `chart/values.yaml`/RBAC/`deployment.yaml` and injecting unrelated newer-k8s-API churn into `chart/crds`. Correct process: `make generate manifests` (regenerates `config/crd/bases` + deepcopy) then surgically mirror only the new field into `chart/crds/*-crd.yaml`.
- The agent's k8s `name` is unchanged by an identity override — only the *logical* identity moves. The sync credential secret stays keyed by the resource name in `reconcile.py`; the explicit id changes only the AIB-side service client id / permission set / external id.
- Default-path encoding is preserved byte-for-byte (`client_id = kaos-<slug>-<ns>-<name>`, permission set `kaos:<slug>:<ns>:<name>:call`), so no migration is required for resources without `security.id`.
- Out of scope (later phases): refresh-ahead/reactive actor-token lifecycle in the SDK (P9); sync productionisation — watch/leader-election/rotation/status write-back (P10); AIB-side subject/actor separation + access-check hardening (P11).
