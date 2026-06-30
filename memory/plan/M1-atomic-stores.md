# Atomic memory stores — implementation plan

**Branch (KAOS)**: `feat/memory-atomic-stores`, stacked off `main` (after M0 learnings land).
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `M0 → M1 → M2`. M1 is the first production code in the memory stack and builds the two atomic stores that M2 composes into the service. It branches off `main` (M0 wrote no production code). **Before starting, re-read [`../impl/learnings/M0-feasibility-validation.md`](../impl/learnings/M0-feasibility-validation.md)** and fold its deltas (exact Mem0 version/config shapes, provider quirks, token-counting approach) into the tasks below.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message describing WHAT changed; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run unit tests locally and keep them green; push to the PR and confirm CI green. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M1-atomic-stores.md` and write `impl/progress/M1-*.md` + `impl/learnings/M1-*.md`.

## Problem statement

Build the two smallest independently-testable building blocks of the memory architecture, with full unit coverage and no service, network, or operator around them: (1) a **long-term adapter** wrapping Mem0 as a library, exposing scope-mapped `write`/`recall`/`delete` that translate the KAOS scope onto Mem0's `user_id`/`agent_id`/`run_id` identifiers, selectable across the Chroma (`local`) and pgvector (`external`) providers; and (2) a **working-tier store** — a plain relational table with token-budget eviction, a rolling-summary hook, and recency-ordered retrieval, on SQLite (`local`) or Postgres (`external`). Both bind their models to a resolved `ModelAPI` endpoint via configuration. These are libraries: deterministic, fast to test, and free of HTTP/policy/operator concerns, which land in later phases.

## Current-state grounding (researched)

- There is no long-term or vector code in KAOS today; `pais/memory.py` is working-only ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). The new code is greenfield but must match the [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md) contract so M2/M3 compose cleanly.
- Mem0 config shapes (vector store provider, llm, embedder) and scope-identifier semantics are fixed by [adr_0002](../adrs/adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) and confirmed in M0. The adapter is the only place that imports `mem0`.
- The working tier is relational, never on Redis, never on Mem0, co-located with the long-term store ([adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)). Token-budget + rolling summary replaces turn-count eviction.
- Model binding mirrors the Agent's `{modelAPI, model}` shape ([adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md)); the resolved endpoint is an OpenAI-compatible base URL (LiteLLM proxy, port 8000 — `operator/controllers/modelapi_controller.go:454-469`). M1 takes the resolved base URL + model as plain config; resolution from a CRD is M4.

## Design plan (how it fits)

Create a new top-level Python package **`memory-service/`** (sibling to `pydantic-ai-server/` and `mcp-servers/`), with an importable package `kaos_memory` and the standard repo toolchain (`pyproject.toml`, `Makefile` with `lint`/`test`, `uv`/venv, `black` + `ty`, `pytest`). M1 populates only the storage layer; M2 adds the HTTP service in the same package. Module layout:

- `kaos_memory/config.py` — typed config: `StorageConfig(type: local|external, local{provider,path}, external{provider,dsn})`, `ModelConfig(base_url, model, api_key)` for `summarization` and `embedding`, `WorkingTierConfig(token_budget, rolling_summary, hard_event_cap)`.
- `kaos_memory/scope.py` — the `Scope` value object (principal, agent_client_id, session_id, plus the `private|user|shared` selector from [adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md)) and the mapping to Mem0 filter keys (`private`→`agent_id`, `user`→`user_id`, `session`→`run_id`, `shared`→a reserved shared owner id — never an empty filter, since Mem0 2.x rejects owner-less searches). M1 ships the data shape and the mapping function; non-optional **enforcement** is M5 (here it is just a correct translation).
- `kaos_memory/longterm.py` — `LongTermStore`: constructs `mem0.Memory`/`AsyncMemory` from `StorageConfig`+`ModelConfig`; `write(scope, messages)`, `recall(scope, query, top_k)`, `delete(scope)`/`delete_all(scope)`. The only importer of `mem0`.
- `kaos_memory/working.py` — `WorkingStore`: a relational table via a thin DB abstraction that targets SQLite and Postgres with the same schema; `append(scope, role, content, metadata)`, `recent(scope, token_budget)`, `summarize_overflow(scope, model)` (rolling summary), `clear(scope)`. Idempotent `CREATE TABLE IF NOT EXISTS` on init.
- `kaos_memory/tokens.py` — token counting (per M0's chosen tokenizer).

Tests use a real embedded Chroma + a temp SQLite, and a pgvector/Postgres path gated behind a marker that runs against a local container in CI where available (fall back to SQLite-only assertions when Postgres is absent, but keep the pgvector tests runnable locally and in the e2e lane).

## Numbered TODOs

1. **Package scaffold.** Create `memory-service/` with `pyproject.toml` (deps: `mem0ai==2.0.10`, `chromadb`, `psycopg[pool]`, `pgvector`, `tiktoken`, `httpx`, `pydantic`), `Makefile` (`lint` = `black --check . && uvx ty check`; `test` = `pytest tests/ -v`), `kaos_memory/__init__.py`, and a `tests/` dir. Match the `pydantic-ai-server` toolchain conventions. **Validate**: `cd memory-service && make lint` and an empty `pytest` run succeed. **(M0 delta 4: pgvector needs `psycopg[pool]`, not `[binary]`. M0 delta 1: pin Mem0 2.x — its API differs from the 1.x sketch.)**

2. **Config + scope value objects.** Implement `config.py` and `scope.py` with the typed config and the `Scope`→Mem0-filter-keys mapping: `private`→`agent_id`, `user`→`user_id`, `session_id`→`run_id`, and `shared`→a **reserved shared owner id** (e.g. a fixed `agent_id`/group key naming the store-wide shared namespace) — **not** an empty/no-owner filter. Pure, no I/O. **Validate**: unit tests asserting each scope variant maps to the right Mem0 kwargs, that `shared` yields a concrete owner key, and that an unresolved/empty scope is representable (enforcement is M5). `pytest tests/test_scope.py -v`. **(M0 delta 2: Mem0 2.x `search` raises `ValueError` unless `filters` carries at least one of `user_id`/`agent_id`/`run_id`, so `shared` must map to a real owner key. Rich `AND/OR/NOT` operators are available for composite rules.)**

3. **Long-term adapter over Mem0.** Implement `longterm.py`: build the Mem0 client from `StorageConfig`+`ModelConfig` for both providers, and `write`/`recall`/`delete(_all)` mapping scope via TODO 2, targeting the **Mem0 2.x** signatures `add(messages, *, user_id=, agent_id=, run_id=, infer=)`, `search(query, *, top_k=, filters=, threshold=, rerank=)`, `delete(memory_id)`. Set `embedding_model_dims` on the pgvector config; do not pass it to Chroma (it infers dims). Disable Mem0's PostHog telemetry. Encapsulate the M0-confirmed config shapes; no scope key leaks to callers except through `Scope`. **Validate**: unit tests with embedded Chroma — scope-isolated write/recall (including the cross-owner pre-filtering assertion from M0), delete removes only the scoped items; a pgvector-marked test repeats the isolation assertions against a local Postgres. `pytest tests/test_longterm.py -v`. **(M0 deltas 1, 3, 5, 9.)**

4. **Working-tier store.** Implement `working.py` + `tokens.py`: the relational schema, `append`, recency-ordered `recent(token_budget)`, and `summarize_overflow` that folds older turns into a rolling summary using the `summarization` model (call the OpenAI-compatible endpoint via `httpx`), keeping recent turns verbatim and a hard event cap as a safety ceiling. Target SQLite and Postgres with one schema. **Validate**: unit tests — append/recent ordering, budget overflow triggers summarization not truncation, summary persisted and raw rows retained, hard cap enforced; run against SQLite, and the Postgres-marked variant against a local container. `pytest tests/test_working.py -v`.

5. **Model client + endpoint binding.** A small `models.py` wrapping the OpenAI-compatible calls (chat for summarization/extraction config, embeddings) used by the working store and passed into Mem0's config, taking `ModelConfig(base_url, model, api_key)`. Confirm the same config object drives both Mem0's llm/embedder and the working-tier summary. **Validate**: unit test against a stub OpenAI-compatible server (or recorded responses) asserting the base URL/model are honoured; `pytest tests/test_models.py -v && make lint`.

6. **Store composition smoke + docs.** A `tests/test_stores_smoke.py` that drives both stores together for one scope (append working turns, write long-term facts, recall both) to prove they compose without the service, and a `memory-service/README.md` documenting the package, config, and how to run tests in both storage modes. **Validate**: smoke test green in `local` mode; `make lint && make test`. Write `impl/progress/M1-*.md` + `impl/learnings/M1-*.md` (note any Mem0/pgvector deltas for M2), copy this plan, push `feat/memory-atomic-stores`, open the stacked PR into `main`, confirm CI green, write the gitignored `REPORT.md` (M0–M1) and post it as a PR comment.

## Validation per task

- Per-TODO: `cd memory-service && python -m pytest tests/ -v && make lint`. The pgvector/Postgres tests use a local container (document the `docker run pgvector/pgvector` invocation in the README); they must pass locally and in the lane that has Postgres, and are skipped with a clear marker where Postgres is unavailable.
- Add a CI job (or extend the python-tests workflow) to run the `memory-service` suite; wire it in this phase so later phases inherit it.

## Commit / PR strategy

- `feat/memory-atomic-stores` off `main`; one comprehensive, functional commit per TODO; PR into `main`; Copilot co-author trailer on KAOS commits. Keep CI green. `REPORT.md` gitignored, posted as a PR comment.

## Out of scope (later phases)

The HTTP service and background execution (M2); the runtime client and message-history bridge (M3); the CRD/operator wiring that resolves `StorageConfig`/`ModelConfig` from a `MemoryStore` (M4); non-optional fail-closed scope enforcement, A2A prefix inheritance, and erasure fan-out semantics (M5 — M1 ships only the correct scope mapping, not the enforcement policy); HA, metrics, durable queue, e2e, docs (M7).
