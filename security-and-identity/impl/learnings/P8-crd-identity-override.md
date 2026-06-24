# P8 — CRD identity override (learnings)

**Phase**: P8 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-22
**Context**: introducing a first-class logical security identity for Agent/MCPServer/ModelAPI — namespace-scoped by default, pinnable via `spec.security.id` — resolved identically by the operator (Go) and the sync projection (Python), with oldest-wins collision/adoption.

> **Superseded — the `spec.security.id` override was subsequently removed.** Logical identity is now always `kaos://<kind>/<namespace>/<name>` (unique by construction), so the override, the oldest-wins collision/adoption logic, and the dual-side parity hazard described below no longer exist. This note is retained as a historical record of why the feature was built and what it cost to maintain. See [`ADR-KAOS-001`](../../adr-kaos/ADR-KAOS-001-identity-model-and-source-of-truth.md) for the removal amendment and the deferred shared-identity design note, and [`manual-e2e-identity-removal-validation.md`](manual-e2e-identity-removal-validation.md) for the end-to-end validation that the default-identity path stayed intact after removal.

## Key findings

### One identity rule, two implementations — keep them byte-identical and prove it

The identity model is implemented twice: `operator/pkg/identity/identity.go` (`Resolve`) and `sync-service/kaos_sync/projection.py` (`resolve_logical_id`). If they ever disagree, the operator would wire one identity into the agent actor (`AGENT_AUTH_IDENTITY`) while the sync service provisions grants under a different one — a silent authorization break. The rule is deliberately trivial (`kaos://<kind>/<id>` when set, else `kaos://<kind>/<ns>/<name>`) precisely so both sides stay in lock-step, and a scratch parity harness cross-checks the two for the same inputs. Treat any future change to the encoding as a paired change with a parity check, not a one-sided edit.

### Preserve the legacy default encoding exactly — the override is purely additive

The pre-P8 sync projection already encoded `<ns>/<name>` into the client id / permission set / external id. The safe way to add `security.id` was to make the explicit id substitute *only* the path segment (`_logical_path` returns `id` when set, else `<ns>/<name>`) and leave every downstream transform (`replace("/","-")`, `replace("/",":")`) untouched. This keeps default-id resources byte-identical to before (no migration, no churn in AIB), and confines the new behaviour to resources that opt in.

### Explicit-id external ids broke the prune guard — validate, don't parse

The prune-safety guard in `reconcile.py` used `parse_agent_external_id`, which expects the two-segment `kaos://agent/<ns>/<name>` form and returns `None` for the one-segment explicit-id form `kaos://agent/<id>`. Left unfixed, a *deleted* explicit-id agent would be classified as a malformed external id and treated as drift to skip — leaking its AIB record instead of pruning it. The fix is a dedicated `is_valid_agent_external_id` that accepts both forms; the lesson is that a stricter identity scheme needs its validators widened in the same change, or cleanup silently regresses.

### Oldest-wins by creationTimestamp is deterministic and adoption-friendly

A *shared* explicit id can be claimed by two resources of the same kind. Resolving by oldest `creationTimestamp` (ns/name as tiebreak) is deterministic across both the operator (`DetectConflict`) and the sync service (`_winners_and_conflicts`), needs no extra coordination state, and naturally supports adoption: when the holder is deleted, the remaining resource becomes oldest and takes over. RFC3339 timestamps sort lexicographically == chronologically, so a plain string sort suffices. Empty creationTimestamp sorts first (only relevant in unit fixtures; real CRs always have one).

### controller-runtime won't re-reconcile the loser when the holder is deleted — requeue it

When a duplicate-id loser is marked `Failed`, deleting the *holder* does not trigger a reconcile of the loser (they are distinct objects with no owner/watch relationship). Without a nudge the loser would stay `Failed` forever even though the id is now free. Returning `ctrl.Result{RequeueAfter: 30s}` on the losing path makes the loser re-evaluate and adopt the id on its own — a small but essential detail for the adoption story to actually work.

### The operator chart CRDs are hand-maintained — `make helm` is the wrong tool

Adding a CRD field tempts a `make helm` to "sync the chart", but that target regenerates the entire chart via helmify and clobbers hand-maintained `chart/values.yaml` (defaultImages/mcpRuntimes, image tags → `latest`), reorders RBAC, edits `deployment.yaml`, and injects unrelated newer-k8s-API churn into `chart/crds`. The correct, surgical process for a CRD field is: `make generate manifests` (regenerates `config/crd/bases` + deepcopy cleanly) then copy just the new `security:` block from `config/crd/bases/*.yaml` into the matching `chart/crds/*-crd.yaml` at the right alphabetical anchor. Recorded here because it directly contradicts the intuitive workflow and the earlier (wrong) plan note.

### CRDs are too large for client-side apply — use server-side

Applying the regenerated CRDs with a plain `kubectl apply` fails with `metadata.annotations: Too long` (the last-applied annotation exceeds the limit). `kubectl apply --server-side --force-conflicts` is required to install/update them and to validate the new field + pattern live. Worth knowing for any future CRD validation against a real cluster.

### Identity moves the logical id, not the kubernetes name

A subtle but important boundary: `spec.security.id` changes the *logical* identity used for AIB grants, but the resource's k8s `name` (and the sync credential secret keyed by it in `reconcile.py`) is untouched. Conflating the two would have rotated credentials or renamed objects on every id change. Keeping the credential secret keyed by name means an id change re-points AIB-side grants without disturbing the in-cluster credential material.
