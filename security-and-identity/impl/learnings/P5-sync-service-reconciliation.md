# P5 — Sync service to MVP-robust (learnings)

**Phase**: P5 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-22
**Context**: hardening the P3 KAOS→broker sync projector into an MVP-robust reconciler — ModelAPI projection, pruning, per-resource isolation, retries and observability.

## Key findings

### Pruning is only safe when ownership is provable from the record itself

The reconcile loop must delete broker records and Secrets that no longer correspond to a live KAOS resource, but it shares the broker with whatever else registers there, so it can never delete a record it does not own. Ownership is therefore encoded into the record at creation and checked before any delete: services are owned iff their `client_id` is prefixed `kaos-mcpserver-`/`kaos-modelapi-`, permission sets iff the name is prefixed `kaos:`, agents iff the `display_name` parses as `kaos://agent/<ns>/<name>`, and credential Secrets iff they carry the label `app.kubernetes.io/managed-by=kaos-sync`. A broker record that is KAOS-prefixed but whose name cannot be parsed back into a namespace/name is left alone and recorded as a `STALE_EXTERNAL_ID` problem rather than deleted — refusing to guess is safer than mis-deleting. This keeps pruning total over KAOS-owned state while provably never touching foreign records.

### Deletion order is the mirror of creation order

Creation goes services → permission sets → agents (each layer references the one below). Pruning must run in the reverse, dependency-safe order: agents first (revoking their credentials), then the credential Secrets, then permission sets, then services. Deleting a service while a permission set still references it, or an agent while its Secret still exists, would either fail on the broker or leave a dangling mount. Encoding the order explicitly in `_prune` keeps each delete valid at the moment it runs.

### Per-resource isolation changes the failure model from "abort" to "degrade"

The P3 loop aborted on the first failure, so one unreachable edge or one malformed agent stopped the whole pass. P5 wraps every service, permission set, agent and prune operation individually: a failure becomes a categorized `Problem` (`AIB_UNREACHABLE`, `MISSING_CREDENTIALS`, `UNSUPPORTED_EDGE`, `STALE_EXTERNAL_ID`, `PRUNE_FAILED`) and the pass continues with the rest. The one place that stays fail-**closed** is an agent whose permission set is missing — it is skipped, not minted, because granting an identity without its intended grants would be a privilege error. Broker-wide failures (a `list` that cannot reach the broker at all) still mark the whole pass not-ok via `ReconcileSummary.ok`, which is what `/readyz` and the `last_pass_ok` gauge report on.

### Readiness must mean "a pass completed", not "a pass succeeded"

`/healthz` is pure liveness (the process is up) and always returns 200. `/readyz` returns 503 until the first reconcile pass *completes*, then 200 — deliberately decoupled from whether that pass had problems. If readiness required a clean pass, a transiently unreachable broker would flap the pod out of the endpoints and (with the chart's readiness probe) could mask the very metrics/logs an operator needs to diagnose the broker outage. Pass success is surfaced separately through the `kaos_sync_last_pass_ok` gauge and the per-category problem counters, so an unreachable broker degrades visibly without taking the sync pod down. This was confirmed on KIND: with no broker reachable the pod stayed Ready and kept serving metrics while recording `aib_unreachable` problems each pass.

### Idempotent retries belong at the request layer, below the reconcile logic

Transient broker failures (connection resets, 502/503/504) should not surface as reconcile problems if a retry would succeed, but the reconcile logic must stay pure and unit-testable. The retry therefore lives in the `aib_client._request` wrapper — bounded exponential backoff over transport errors and the 5xx set, with the attempt count, base delay and `sleep` all injectable so tests exercise retry-then-succeed and retry-exhausted without real waits. Only after retries are exhausted does the failure reach the reconcile loop as a `Problem`. Keeping retry below the protocol boundary means the reconcile fakes need no retry awareness.

### `list` as a method name shadows the `list` builtin in type annotations

Naming the admin-client method `list` (the natural REST verb) makes ty resolve `list[...]` return annotations in the same class scope to the *method*, not the builtin, even with `from __future__ import annotations`. The fix that kept the ergonomic method name was to import `typing.List` and annotate returns as `List[...]`. This recurred in `aib_client.py`, the `reconcile` protocols and `k8s.py` — worth doing pre-emptively whenever a method is named after a builtin container.

## Decisions carried forward

- Pruning is on by default (`prune_enabled`) but gated so it can be disabled operationally; ownership predicates are the single source of truth for what is deletable.
- The synthetic `kaos-<kind>-<ns>-<name>` / `kaos:<kind>:...` encoding is retained for ModelAPI as well as MCPServer; a native broker resource-grant model that replaces this encoding is deferred to the broker-productionisation phase.
- Sync stays a periodic full-reconcile loop; watch-based incremental reconcile, leader election and CRD `.status` integration are later-phase productionisation work.
- Active credential rotation (time/policy-driven) is explicitly out of scope; P5 only prunes/revokes credentials whose owning resource is gone.
