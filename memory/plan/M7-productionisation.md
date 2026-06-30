# Productionisation, hardening, and documentation — implementation plan

**Branch (KAOS)**: `feat/memory-productionisation`, stacked off the later of `feat/memory-multitenancy` (M5) and `feat/memory-cli-install` (M6); PR targets that tip.
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `{M5, M6} → M7`. M7 is the final phase: it hardens the service for production, finalises the operational behaviour, promotes the M0 harnesses into committed e2e, and brings the docs up to the implementation. It stacks on whichever of M5/M6 lands last. **Before starting, re-read all prior `impl/learnings/` entries** (M0–M6) and fold every recorded delta and deferred decision into the tasks below.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run the touched suites locally; push the PR and confirm CI green including the new e2e. Alpha: breaking changes OK.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all phases) posted as a PR comment (not committed). Copy this plan to `plan/M7-productionisation.md` and write `impl/progress/M7-*.md` + `impl/learnings/M7-*.md`.

## Problem statement

Complete the operational correctness story and bring documentation up to the implementation. Harden `external` mode for high availability (stateless `replicas: 2+`, disruption budget, readiness/liveness, Mem0 change-history log disabled/ignored); finalise the `failureMode: soft | strict` behaviour end to end; add metrics/health endpoints and the memory-operation metrics; **evaluate and record a decision** on the deferred durable at-least-once extraction queue, building it only if write durability proves a hard requirement; promote the most valuable M0 harnesses into committed e2e tests runnable in CI (KIND); and write the user- and operator-facing documentation and update the repo instructions.

## Current-state grounding (researched)

- HA and degradation are fixed by [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md): `external` mode is stateless over shared Postgres (`replicas: 2+`); `local` mode pins to a single replica; Mem0's SQLite change-history log is disabled/ignored so it does not block scaling; `failureMode: soft|strict` selects fail-soft (working-only on recall failure, background retry on write failure) versus strict.
- The durable queue is explicitly deferred: in-process fire-and-forget is the v1 execution model; a durable at-least-once queue (Postgres SKIP-LOCKED job table) is a follow-up to adopt only when write durability becomes a hard requirement ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md)). M7 makes the explicit decision.
- Observability rides existing OpenTelemetry; the operation spans were added in M2/M3/M5. Metrics endpoints are new in M7 (mirror the sync-service productionisation precedent in the security work: `prometheus_client`, `/metrics`, readiness/liveness).
- e2e helpers and patterns: `operator/tests/e2e/conftest.py`, `test_modelapi_e2e.py`; the memory e2e files added in M4/M5 are the base to extend.
- Docs: VitePress under `docs/`; repo instructions in `.github/copilot-instructions.md` and `.github/instructions/*` (python/operator/e2e/docs). The memory model and surfaces must be documented and the instructions updated succinctly.

## Design plan (how it fits)

- **HA hardening (`external`).** Confirm/enforce statelessness, set `replicas: 2+` defaults for `external`, add a `PodDisruptionBudget` and readiness/liveness probes on the service Deployment (operator constructs them), and verify a replica restart loses no memory (durable state in Postgres). Confirm Mem0's change-history log is disabled.
- **`failureMode` end to end.** Verify soft (degrade + background retry) and strict (surface the error) across recall and write, from the Agent block through the runtime to the service, including the store-down → Agent-not-Ready-but-serving operator condition.
- **Metrics + health.** Add `prometheus_client` to the service: `/metrics` exposing memory-operation counters/histograms (recall/write/forget counts, extraction queue depth and failures, degraded-recall count, last-write-success gauge) and confirm `/readyz`/`/healthz`; operator exposes the metrics port and probes.
- **Durable-queue decision.** Measure in-process fire-and-forget under autonomous-loop event volume; record a decision in `impl/learnings/M7`: keep fire-and-forget (default) or build the Postgres SKIP-LOCKED durable queue. Build it only if the evidence shows unacceptable extraction loss; otherwise document the trigger condition for a future phase.
- **e2e promotion.** Promote the decisive M0 harnesses (scope-correct recall on both providers, model routing through a `ModelAPI`, working-tier summarization, deploy-and-restart durability) into committed `operator/tests/e2e/test_memory_*_e2e.py`, runnable in CI on KIND.
- **Docs.** Add a memory section to `docs/` (the memory model and tiers, the `MemoryStore` and Agent surfaces, install flow, scope/multi-tenancy, operations and degradation), and update `.github/copilot-instructions.md` + the path-specific instructions to describe the memory service, the `memory-service/` package, and the build/test commands. Keep docs succinct and functional; single-line paragraphs.

## Numbered TODOs

1. **HA hardening for `external` mode.** Operator: default `replicas: 2+` for `external`, add a `PodDisruptionBudget`, readiness/liveness probes; confirm statelessness and Mem0 change-history disabled. **Validate**: operator envtest — `external` store gets 2 replicas + PDB + probes, `local` stays single-replica; a local KIND restart test shows no memory loss; `cd operator && make test-unit`.

2. **`failureMode` end-to-end finalisation.** Verify soft/strict across recall and write through all three components and the store-down operator condition. **Validate**: cross-component tests — soft degrades + retries, strict surfaces errors, store-down → Agent not-Ready-but-serving; touched suites `pytest`/`make test-unit`.

3. **Metrics + health.** Add `prometheus_client` `/metrics` to the service with the memory-operation metrics; operator exposes the metrics port + probes. **Validate**: `memory-service` test asserts the metric registry updates on operations and readiness toggles on simulated store failure; `cd memory-service && pytest tests/test_metrics.py -v && make lint`.

4. **Durable-queue decision.** Measure extraction durability under load; record the decision (keep fire-and-forget vs build the durable queue) with the evidence and the trigger condition in `impl/learnings/M7-*.md`; build the durable queue only if justified. **Validate**: the measurement harness runs (in `./tmp/memory/`); the decision is documented; if built, durable-queue tests pass.

5. **Promote M0 harnesses to committed e2e.** Add `operator/tests/e2e/test_memory_*_e2e.py` covering scope-correct recall on both providers, model routing through a `ModelAPI`, working-tier summarization, and deploy-and-restart durability; reuse `conftest.py`. **Validate**: e2e green on local KIND and via `workflow_dispatch`; suppress to `./tmp/null`.

6. **Documentation + instructions.** Add the memory docs section to `docs/`; update `.github/copilot-instructions.md` and the path-specific instructions for the `memory-service/` package, the `MemoryStore`/Agent surfaces, and the build/test commands. **Validate**: `cd docs && npm run build` succeeds; instructions are succinct and accurate. Write `impl/progress/M7-*.md` + `impl/learnings/M7-*.md`, copy this plan, push `feat/memory-productionisation`, open the stacked PR, confirm CI green, write the gitignored `REPORT.md` (M0–M7, the whole memory effort) and post it as a PR comment.

## Validation per task

- Per-TODO: run the touched suites (`memory-service`/`pydantic-ai-server` `pytest` + `make lint`, `operator` `make test-unit`, `docs` `npm run build`). The promoted e2e runs in CI on KIND via `workflow_dispatch --ref feat/memory-productionisation`.
- Documentation changes are built (`npm run build`) but not unit-tested beyond that.

## Commit / PR strategy

- `feat/memory-productionisation` stacked on the later of M5/M6; one comprehensive commit per TODO; Copilot co-author trailer; CI green including the new e2e. The final `REPORT.md` (gitignored) summarises the entire memory effort and is posted as a PR comment.

## Out of scope (genuinely deferred)

The durable at-least-once queue if the M7 measurement does not justify it (documented trigger for a future phase); temporal/procedural memory tiers behind a future Graphiti-class engine; dynamic cross-cutting agent groups (`MemoryGroup`); per-tenant rate/fair-share quotas, logical export/import, application-level encryption, and proof-of-deletion ledgers ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md), [adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md)).
