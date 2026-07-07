# M7 — Productionisation, hardening, and documentation — progress

Status: complete.

The memory feature is brought to a shippable state by adding only the genuinely missing production essentials and recording explicit defer decisions for the rest. The scope was calibrated against what earlier phases already shipped — health/readiness probes, replica control, the layered failure-mode contract, and a committed memory e2e — so this phase avoided synthetic work. It adds high-availability defaults for external stores, closes the one untested seam in the failure-mode contract, proves short-term durability across a pod restart, and documents the operational surface end to end.

## Tasks

1. **High-availability defaults for external stores.** The operator now defaults an external-mode `MemoryStore` to two replicas when the replica count is unset (local single-writer stores stay at one; an explicit count always wins) and attaches a `PodDisruptionBudget` with `minAvailable=1` for any store running two or more replicas, reconciling it away when a store drops back to one. Implementing this required removing the static `+kubebuilder:default=1` marker from the `replicas` field — the API server materialises a defaulted field on every object, which defeated the controller's mode-aware defaulting — while keeping the `Minimum=1` validation and the CEL rule pinning local stores to a single replica. envtest integration assertions cover both paths (external → two replicas + PDB; local → one replica + no PDB).

2. **Cross-component failure-mode verification.** Soft/strict was already implemented and unit-covered at every layer independently (service, client, operator), but the client-service boundary itself was never exercised together. A new test wires a real `MemoryServiceClient` to a real service app over an in-process ASGI transport and asserts the degrade-on-soft / raise-on-strict behaviour survives the HTTP round trip for recall (always soft), write, and forget.

3. **Durable extraction queue — decision only.** Assessed the in-process fire-and-forget extraction model (`BackgroundRunner`) against a durable `SKIP LOCKED` job queue and decided to keep fire-and-forget for this phase, with the reasoning, the narrow bounded loss window, and explicit revisit triggers recorded in the learnings. Extraction is funnelled through a single scheduler seam, so the swap is a localised change if a trigger fires.

4. **End-to-end durability gap-check.** Reviewed the committed memory e2e for productionisation coverage and added a test asserting the short-term window survives a memory-service pod restart: it writes turns, deletes the pod (freeing the RWO PVC rather than a rollout restart, which would deadlock on the volume), waits for the replacement to become ready, recalls, and asserts the turns persisted. It runs automatically in the existing `memory` e2e shard.

5. **Documentation and repository instructions.** Added a high-availability and operations section to the MemoryStore CRD docs (replica defaulting and PDB, health/readiness probes, soft/strict degradation, the `--pgvector-memory-enabled` dev Postgres install flow); corrected the runtime and Agent CRD memory examples to the shipped `config.memory` surface (dropped the removed `contextLimit`/`maxSessions`/`maxSessionEvents` knobs, added `clientParams`) and documented the short/medium/long-term tiers and the `private`/`user`/`shared`/`session` scope semantics; and registered the `kaos-memory` package in the repository instructions with its build/test commands, structure, key files, and the MemoryStore CRD overview.

## Validation

- `operator` envtest (MemoryStore controller): external store defaults to two replicas with a `PodDisruptionBudget`; local store stays at one replica with no PDB.
- `kaos-memory` suite: full run green (79 passed, 4 skipped) including the new cross-component failure-mode test; `make lint` clean (black + ty).
- `operator` e2e: the pod-restart survival test compiles and is black-clean; it executes in the `memory` shard in PR CI.
- `docs`: `npm run build` completes with no errors.

## Deferred (explicit, with triggers in learnings)

- Prometheus `/metrics` endpoint on the memory service — deferred; health/readiness probes and the failure counter cover operability for alpha.
- Durable at-least-once extraction queue (`SKIP LOCKED` job table + polling worker) — deferred; keep in-process fire-and-forget with bounded retry and graceful drain until a documented trigger holds.

Findings and the deltas to carry forward are recorded in [`../learnings/M7-productionisation.md`](../learnings/M7-productionisation.md).
