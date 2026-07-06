# pgvector semantic-recall example — implementation plan (future milestone)

**Branch (KAOS)**: `feat/memory-pgvector-example`, stacked off `feat/memory-productionisation` (M7); PR targets that tip.
**Status**: Future / opt-in. Not on the critical path — schedule after M7 lands.

> **Why a separate phase.** The default e2e suite proves the memory control and data planes with a mock `ModelAPI`, so it can only assert model-independent behaviour: verbatim short-term round-trip, per-scope isolation, and agent memory-binding recovery ([M4](./M4-memory-store-crd.md)). Real semantic long-term recall — writing turns, extracting facts through an embedder, and retrieving them by similarity — needs a real embedding model and a real vector store, which the mock cannot provide. This phase adds a fully-fledged, documented example that exercises `storage.type: external` (pgvector) with a real embedder end to end, plus a marker-gated e2e that runs it only when credentials are supplied. It is the hands-on counterpart to the library-level pgvector coverage, which stays gated behind `KAOS_TEST_PGVECTOR_DSN` and is not in CI.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run the touched suites locally; push the PR and confirm CI green. The marker-gated e2e does not run in default CI — it is opt-in via an explicit secret/marker.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` posted as a PR comment (not committed). Copy this plan alongside the other phase plans and write `impl/progress/*` + `impl/learnings/*` entries.

## Problem statement

Semantic long-term recall is the headline capability of the memory work, yet nothing in the committed, always-on test surface demonstrates it against a real vector backend — the mock `ModelAPI` returns canned completions and cannot embed. Operators therefore have no runnable, documented reference for standing up an `external`-mode `MemoryStore` on pgvector with a real embedder and watching an agent recall facts across sessions. This phase closes that gap with a self-contained example under `docs/examples/` and an e2e that runs it behind an explicit opt-in, so the semantic path is exercised without inflating default CI time or requiring provider credentials in every run.

## Current-state grounding (researched)

- `storage.type: external` binds Mem0 to pgvector plus a plain short-term table on a shared Postgres, stateless at `replicas: 2+` ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md)); `local` mode uses embedded Chroma + SQLite on a PVC. The `MemoryStore` CRD already carries the `external` storage block and the `summarization`/`embedding` model roles ([M4](./M4-memory-store-crd.md)).
- The library-level pgvector tests exist but are skipped unless `KAOS_TEST_PGVECTOR_DSN` is set; they are deliberately excluded from CI to avoid standing up Postgres and a real embedder on every run.
- The memory e2e added in [M4](./M4-memory-store-crd.md) asserts only model-independent behaviour on `local` Chroma with a mock `ModelAPI`, in its own `memory` shard. Real semantic recall is explicitly out of that scope.
- The example layout precedent is `docs/examples/*` with per-example resources and an e2e entry in `operator/tests/e2e/test_examples_e2e.py`, each example running in its own matrix shard with a `pytest_filter` in `.github/workflows/reusable-tests.yaml`.
- A real embedder can be supplied either by a hosted `ModelAPI` (e.g. an in-cluster Ollama embedding model) or by a proxy `ModelAPI` fronting a provider embeddings endpoint with a supplied key; the marker/secret decides which.

## Design plan (how it fits)

- **Example manifests.** Add `docs/examples/memory-pgvector-semantic-recall/` with: a Postgres (pgvector) deployment or a documented external DSN, a `ModelAPI` providing a real embedding model (and a summarisation model), an `external`-mode `MemoryStore` referencing them, and an `Agent` bound to the store with memory tools enabled. Include a `README.md` walking through deploy → converse → observe recall across two sessions.
- **Documented walkthrough.** The README demonstrates the semantic property: in session A the agent is told durable facts; in session B (new session id, same scope) the agent recalls them via long-term search, not verbatim short-term replay. Show the recall block and the extracted facts. Keep prose single-line per paragraph.
- **Marker-gated e2e.** Add `test_memory_pgvector_semantic_recall_example` in the examples e2e, guarded by a `pytest.mark.skipif` on an explicit opt-in (a secret/env such as `KAOS_E2E_PGVECTOR_EMBEDDER`), so it runs only when a real embedder is available. It deploys the example, drives a write with `infer=True`, waits for extraction, and asserts a semantically-related query returns the extracted fact with the short-term window excluded. Bound every wait; no infinite loops.
- **CI wiring, opt-in only.** Add a dedicated matrix shard for the example with its `pytest_filter`, but keep it gated so the default `pull_request` run skips it (no embedder secret present). Provide a `workflow_dispatch` path and/or a scheduled run that supplies the secret to exercise it out-of-band. This keeps default e2e wall-clock bounded.
- **No product code change expected.** This phase is example + test + docs; if it surfaces a real gap in `external` wiring it is fixed here, but the intent is to document and validate the existing capability, not extend it.

## Numbered TODOs

1. **Example manifests + README.** Add `docs/examples/memory-pgvector-semantic-recall/` (pgvector Postgres, embedding+summarisation `ModelAPI`, `external` `MemoryStore`, bound `Agent`) and a README walkthrough demonstrating cross-session semantic recall. **Validate**: `kubectl apply --dry-run=server` (or kaos CLI dry-run) accepts every manifest; the README steps are internally consistent.
2. **Marker-gated semantic-recall e2e.** Add `test_memory_pgvector_semantic_recall_example`, skipped unless the embedder opt-in is set; deploy the example, write with `infer=True`, wait bounded for extraction, assert a related query recalls the extracted fact with short-term excluded. **Validate**: locally with a real embedder (Ollama or a keyed proxy) the test passes; without the opt-in it skips cleanly. Suppress to `./tmp/null`.
3. **CI shard + opt-in trigger.** Add the example's matrix shard and `pytest_filter` in `.github/workflows/reusable-tests.yaml`, gated so default PR runs skip it; add a `workflow_dispatch`/scheduled path that supplies the embedder secret. **Validate**: default e2e wall-clock is unchanged (shard skips); the dispatch path runs the test green.
4. **Docs + instructions.** Link the example from the memory docs section and note the opt-in e2e in the e2e instructions. **Validate**: `cd docs && npm run build` succeeds. Write `impl/progress/*` + `impl/learnings/*`, copy this plan, push the branch, open the stacked PR, confirm default CI green, and post the gitignored `REPORT.md` as a PR comment.

## Validation per task

- Per-TODO: run the touched suites (`operator` e2e locally with the embedder opt-in for the new test; `docs` `npm run build`). The default `pull_request` e2e must remain green and bounded with the new shard skipped.
- The semantic assertion is the acceptance signal: a query unrelated in surface form but related in meaning recalls the extracted fact, proving embedding-backed retrieval rather than string match.

## Commit / PR strategy

One stacked PR off M7. Example manifests, e2e, CI wiring, and docs each commit separately with comprehensive functional messages and the KAOS co-author trailer. The plan and `impl/` entries are committed to `kaos-ai-docs` separately (no trailer).
