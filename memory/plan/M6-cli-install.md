# CLI install integration, sample, and worked example — implementation plan

**Branch (KAOS)**: `feat/memory-cli-install`, stacked off `feat/memory-store-crd` (M4); PR targets `feat/memory-store-crd`.
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `M4 → M6 → M7`. M6 makes the memory feature turnkey through the existing `kaos system install` integration-flag pattern, ships a single sample, and provides the hands-on worked example that doubles as documentation. It depends on M4 (the chart already renders the `MemoryStore` CRD, controller RBAC, and the memory-service image). The end-to-end worked example that was previously scoped as a separate future milestone is **folded into M6** — there is no separate example milestone. **Before starting, re-read [`../impl/learnings/M4-memory-store-crd.md`](../impl/learnings/M4-memory-store-crd.md)** for the chart values/RBAC and the `MemoryStore` surface.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run `cd kaos-cli && pytest tests/ -v` locally (dry-run YAML validation) for CLI work; run the touched `pydantic-ai-server`/operator suites when removing the legacy path; KIND available for the real install + example check. Alpha: breaking changes are fine — no backward compatibility is kept.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M6-cli-install.md` and write `impl/progress/M6-*.md` + `impl/learnings/M6-*.md`.

## Problem statement

Provide a turnkey, human-readable on-ramp for the new memory feature that is consistent with the rest of KAOS: an explicit installer switch that provisions a development **pgvector** Postgres for `external`-mode stores, a single sample that stands the feature up with zero external dependencies, and one clear worked example that a human can read as documentation and run end to end to see memory recall work across sessions. At the same time, remove the superseded legacy Redis distributed-memory path entirely so there is a single, unambiguous memory story.

## Design decisions (resolved)

- **DQ1 — no `--memory-enabled` flag.** The `MemoryStore` controller and the memory-service image are always present in the operator/chart (`operator/main.go`, `chart/values.yaml defaultImages.memoryService`), so there is nothing to gate. Memory is available whenever a user applies a `MemoryStore`; a marker flag would be a confusing no-op. The flag is **not** added.
- **DQ2 — `--pgvector-memory-enabled` provisions a dev pgvector Postgres.** An explicit, opt-in flag (dev-only, never a production default) installs a single-node Postgres with the `pgvector` extension and writes a connection Secret that an `external`-mode `MemoryStore` references. Modelled on the existing `_install_redis` helper.
- **DQ3 — the legacy Redis distributed-memory path is removed completely.** We are in alpha with no backward-compatibility guarantee, so `--redis-enabled`, its install/uninstall helpers, the `agentDefaults.memory` Redis chart values, the runtime `RedisMemory` backend, and all documentation/examples/e2e references are deleted outright. The new `MemoryStore` is the only memory story; the old path is not referenced or deprecated, it is erased.
- **DQ4 — one sample, override-friendly.** A single sample ships a `local`-mode `MemoryStore` + a memory-enabled Agent + a self-contained embeddings `ModelAPI`. It is written so the same base can be pointed at the dev pgvector Postgres (`external` mode) for the worked example by overriding a couple of fields, avoiding a second near-duplicate sample.
- **DQ5 — the sample is self-contained.** It ships its own embeddings `ModelAPI` (mocked responses where a real model is not needed) so it validates on a fresh KIND cluster without external prerequisites, matching the KAOS sample norm.
- **Worked example folded in (was a separate future milestone).** The existing `docs/examples/redis-memory.md` (+ `examples/redis-memory.ipynb`) is **replaced** by a new memory worked example that demonstrates the `MemoryStore` + recall across sessions. The default/CI path uses mocked model responses (model-independent behaviour: verbatim short-term round-trip, isolation, recovery); a clearly-marked `external`/pgvector variant uses a real embedder and is verified manually. The example is documentation first — clear, simple, and easy to maintain.

## Current-state grounding (researched)

- **Flag pattern.** `kaos-cli/kaos_cli/system/__init__.py` defines install flags (`--gateway-enabled`, `--metallb-enabled`, `--monitoring-enabled`, `--redis-enabled`) and forwards them via `install_command(...)`. `--redis-enabled` is the flag being removed.
- **Helm plumbing.** `kaos-cli/kaos_cli/install.py` builds Helm `--set` args; `_install_redis`/`_uninstall_redis` (`:474-534`) install the bitnami Redis chart and wire `agentDefaults.memory.type=redis` + `agentDefaults.memory.redisUrl` (`:1342-1345`). This is the exact precedent for the new pgvector helper and the exact code being removed for Redis.
- **Chart targets (from M4).** M4 added `defaultImages.memoryService` + the `MemoryStore` CRD in `chart/crds/` and controller RBAC. The installer only writes values / installs the optional dev Postgres; it does not change the chart shape. `chart/values.yaml agentDefaults.memory` (`:186-191`, `type`/`redisUrl`) and the Redis lines in `chart/templates/operator-configmap.yaml` are removed.
- **Runtime.** `pydantic-ai-server/pais/memory.py` defines the legacy `RedisMemory` backend, wired in `server.py`/`a2a.py`/`serverutils.py` and covered by `tests/test_agent.py`; these Redis paths are removed. The new memory client (M3) is unaffected.
- **`MemoryStore` modes.** `local` mode is a single container with embedded Chroma + a SQLite short-term window on a PVC (zero external dependency — ideal for the sample and CI). `external` mode binds pgvector via a connection Secret and is what `--pgvector-memory-enabled` targets. A `MemoryStore` also references a `ModelAPI` + model for embeddings/summarisation.
- **Samples surface.** Samples are plain YAML in `operator/config/samples/*.yaml`, auto-discovered by glob and exposed via `kaos samples list|deploy|delete`; adding one numbered file is all that is needed.
- **Examples surface.** Worked examples are jupytext markdown in `docs/examples/*.md` (mirrored to `examples/*.ipynb`) that double as executable e2e tests in `operator/tests/e2e/test_examples_e2e.py`, each running in its own shard via a `pytest_filter` in `.github/workflows/reusable-tests.yaml`. Doc references to the Redis example live in `docs/python-framework/memory.md`, `docs/getting-started/concepts.md`, `docs/python-framework/overview.md`, `docs/python-framework/server.md`, and the instruction files.

## Numbered TODOs

1. **Remove the legacy Redis distributed-memory path entirely.** Delete `--redis-enabled` and its forwarding (`system/__init__.py`, `install.py` `_install_redis`/`_uninstall_redis` and the `agentDefaults.memory` wiring), the `agentDefaults.memory` Redis values and configmap lines in the chart, the `RedisMemory` backend and its wiring in `pydantic-ai-server/pais` (`memory.py`, `server.py`, `a2a.py`, `serverutils.py`), the Redis-specific tests, and the `docs/examples/redis-memory.*` files plus every Redis-memory reference in docs/instructions/e2e. **Validate**: `cd kaos-cli && pytest tests/ -v`; `cd pydantic-ai-server && pytest tests/ -v`; `cd operator && make test-unit`; no remaining `redis` references in first-party source (`grep`).

2. **`--pgvector-memory-enabled` dev Postgres provisioning.** Add the flag (`system/__init__.py`) and a `_install_pgvector`/`_uninstall_pgvector` helper (`install.py`, modelled on `_install_redis`) that stands up a single-node Postgres with the `pgvector` extension and writes a connection Secret (documented name/key) that an `external`-mode `MemoryStore` references. Dev-only; never a production default. **Validate**: dry-run/unit test asserts the flag triggers the helper and the secret contract; `cd kaos-cli && pytest tests/ -k pgvector -v`.

3. **Single memory sample.** Add one `operator/config/samples/*.yaml` containing a `local`-mode `MemoryStore`, a self-contained embeddings `ModelAPI` (mocked where a real model is not needed), and a memory-enabled Agent (`storeRef`, `scope`, `shortTermTokenBudget`, `rollingSummary`, `recall.presentation`, `failureMode`), written so switching the store to `external`/pgvector is a small override. Confirm it surfaces in `kaos samples list|deploy|delete`. **Validate**: dry-run YAML validation of the sample; `cd kaos-cli && pytest tests/ -k samples -v`.

4. **Worked example replacing the Redis example.** Add `docs/examples/memory.md` (jupytext, mirrored to `examples/memory.ipynb`) that reads as documentation: a short flow diagram, prerequisites, apply the sample, hold a short conversation, start a fresh session, and show the agent recalling earlier facts. Keep the default/CI path model-independent with mocked responses; include a clearly-marked `external`/pgvector section for real semantic recall. Wire it into `test_examples_e2e.py` and the reusable-tests shard, gating the real-embedder variant behind an explicit marker so it does not inflate default CI. **Validate**: the model-independent path runs green locally and in its shard; `cd operator && python -m pytest tests/e2e/test_examples_e2e.py -k memory` (mock path).

5. **Manual end-to-end verification + PR.** On local KIND: `kaos system install --pgvector-memory-enabled` (+ gateway/metallb as needed), apply the sample switched to `external`/pgvector, run the worked example hands-on, and **fetch the stored memory data** (recall endpoint / DB) to confirm facts persist and recall works across sessions. Suppress noise to `./tmp/null`. Capture what worked as the reusable base in `impl/learnings/M6-*.md`. **Validate**: install + example + data-fetch confirm recall end to end; `cd kaos-cli && pytest tests/ -v`. Write `impl/progress/M6-*.md`, copy this plan, push `feat/memory-cli-install`, open the stacked PR, confirm CI green, write the gitignored `REPORT.md` (M0–M6) and post it as a PR comment.

## Validation per task

- Per-TODO unit/dry-run suites as listed (CLI dry-run YAML assertions run in CI). The real-install + worked-example data-fetch check is local KIND and documented in `impl/learnings/M6-*.md` and `REPORT.md`. The real-embedder pgvector example path is marker-gated and not in default CI.

## Manual verification (explicit)

The worked example is only "done" once it has been run against a real cluster and the stored data has been inspected — not merely rendered. On KIND: provision pgvector via the new flag, bind an `external` `MemoryStore` to it, run the example conversation, then query the memory service/DB to prove the facts were written and are recalled in a new session. This validated example becomes the simple, human-readable base to iterate from.

## Commit / PR strategy

- `feat/memory-cli-install` stacked off `feat/memory-store-crd`; one comprehensive commit per TODO; Copilot co-author trailer; CI green. `REPORT.md` gitignored, posted as a PR comment.

## Out of scope (later phases — M7)

HA tuning for `external` mode, disruption budgets, metrics/health endpoints, the durable at-least-once extraction-queue decision, promoting additional harnesses into CI, and the full user/operator reference documentation. M6 delivers the installer switch, the single sample, and the one runnable worked example.
