# Memory feasibility validation — implementation plan

**Branch (KAOS)**: `feat/memory-feasibility-validation` (base of the memory stack; branches off `main`).
**Tracking issue**: TBD (create on kickoff; do not reference it in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md) the memory implementation is a bottom-up stack `M0 → M1 → M2 → {M3, M4} → M5 → M7`, `M4 → M6 → M7`. M0 is the **base of the stack** and the **gate**: it builds no production code, only runnable validation harnesses in the gitignored `./tmp/memory/`, and its findings can reshape every later plan. Nothing depends on M0 code (there is none); everything depends on M0's go/no-go and its recorded plan deltas. M1 branches off `main` after M0's learnings are written (M0 itself may merge as a docs/learnings-only PR, or its harnesses may be kept local — decide at kickoff; the security precedent kept P0 harnesses local and committed only the learnings).

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: build the harness slice → run it green → record the finding. M0 commits are limited to the `impl/learnings/` writeup and any harness promoted deliberately; production code is **not** written in M0.
- This phase is **validation only**. The goal is a go/no-go plus concrete plan deltas, not shippable code. Do not start M1 production code here.
- Scratch lives under `./tmp/memory/` (gitignored); suppress noise to `./tmp/null` (create it if missing: `mkdir -p ./tmp && : > ./tmp/null`). **Do NOT use `/tmp`** — writing outside the repo triggers host permission prompts.
- Use a throwaway Python venv under `./tmp/memory/.venv` for harness dependencies (Mem0, chromadb, psycopg, pydantic-ai) so nothing pollutes the real project envs.
- KIND is available; run the deployability checks locally. Be efficient — a handful of decisive checks, not an exhaustive matrix.
- Autonomous: make reasonable assumptions and record them; do not block on host input.
- End: write `impl/learnings/M0-feasibility-validation.md` with results, surprises, and the plan deltas to fold into M1–M7. Copy this plan to `plan/M0-feasibility-validation.md` (already here). No `REPORT.md` for M0 unless a PR is opened.

## Problem statement

Before committing to the memory architecture decided in [adr_0001](../adrs/adr_0001_memory-model-and-lifecycle-operations.md)–[adr_0005](../adrs/adr_0005_multi-tenancy-agent-grouping-and-governance.md), prove the load-bearing hypotheses with working code. The design rests on five claims that must hold or the plan changes: (1) Mem0 runs as a **library** (not the stock server) against both Chroma and pgvector and applies scope filters **inside** the vector query so multi-tenant recall is correct; (2) Mem0's extraction and embedding models can be routed through a KAOS `ModelAPI` (LiteLLM, OpenAI-compatible base URL) rather than direct provider keys; (3) a token-budget working tier with a rolling summary is cheap on a plain relational table (SQLite local, Postgres external); (4) recalled facts can be surfaced to a Pydantic AI run as a structured system block; (5) the `local` single-container shape (Chroma + SQLite on one PVC) and the `external` shape (pgvector + Postgres) both stand up in KIND. M0 confirms each and feeds deltas back into the plans.

## Current-state grounding (researched)

- The runtime memory contract today is working-only: `pais/memory.py` (695 lines) with `LocalMemory` (in-process `deque`), `RedisMemory`, `NullMemory`; chosen by `_create_memory` in `pais/server.py:646-665` from `MEMORY_*` env. No long-term tier exists ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)).
- Mem0 internals were already verified during the ADR phase ([KAOS-R10](../research/KAOS-R10-engine-assessment-and-integration.md), [KAOS-R5-1](../research/KAOS-R5-1-mem0.md)): `add(infer=True)` extracts synchronously in-process via one or more LLM calls; `AsyncMemory` is asyncio over the same path; Mem0's only node-local state is a non-critical SQLite change-history audit log; the FAISS path post-filters metadata (lossy under multi-tenant sharing) while Chroma and pgvector pre-filter (correct). M0 confirms these against running code, not just source reading.
- `ModelAPI` proxy mode exposes an OpenAI-compatible LiteLLM endpoint on port `8000` (`operator/controllers/modelapi_controller.go:454-469`); embeddings and chat both flow through it. Mem0 accepts an OpenAI-compatible `openai_base_url`/`api_base` for its LLM and embedder configs — this is the binding to validate.
- Storage modes are fixed by [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md): `local` = embedded Chroma + SQLite working table on one PVC, single replica; `external` = pgvector + plain working table on shared Postgres, stateless `replicas: 2+`.

## Design plan (how it fits)

Each harness is a small standalone script under `./tmp/memory/` that exercises exactly one hypothesis with assertions, runnable with `python <script>.py` against the throwaway venv. They use real Mem0, real Chroma, real psycopg/pgvector (via a local container), and real pydantic-ai, so the findings are trustworthy. Where an LLM is needed, prefer a cheap real model through a locally-run LiteLLM (or a recorded/mock OpenAI-compatible endpoint) so the `ModelAPI` routing path is what is actually exercised. The KIND checks reuse the cluster the repo already uses for e2e. Nothing here is wired into the operator or the runtime; M0 only proves the pieces compose.

## Numbered TODOs

1. **Harness scaffold + throwaway env.** Create `./tmp/memory/` with a `.venv`, a `requirements.txt` (`mem0ai`, `chromadb`, `psycopg[binary]`/`pgvector`, `litellm`, `pydantic-ai`, `pytest`), and a `README.md` describing how to run each check. Create `./tmp/null`. **Validate**: `./tmp/memory/.venv/bin/python -c "import mem0, chromadb, pydantic_ai"` succeeds; record exact resolved versions of Mem0 and its deps (the ADRs assume a specific Mem0 contract — pin what is actually installed).

2. **Mem0 + Chroma scope-filtered recall (local mode).** Script that constructs `Memory`/`AsyncMemory` with an embedded Chroma `PersistentClient` on a temp dir, writes facts for several distinct `user_id`/`agent_id`/`run_id` combinations, then searches and **asserts** that a query scoped to one owner never returns another owner's facts, including when the other owner's facts are nearer neighbours (craft semantically-close cross-owner facts to prove pre-filtering, not post-filtering). **Validate**: assertions pass; capture the exact Mem0 config dict shape (provider keys, collection naming) for M1.

3. **Mem0 + pgvector scope-filtered recall (external mode).** Same assertions against pgvector. Stand up a local Postgres with the `pgvector` extension (a container under `./tmp/memory/`, e.g. `pgvector/pgvector`), point Mem0's vector store at it, repeat the cross-owner pre-filtering assertions, and confirm two Mem0 client instances pointed at the same Postgres see each other's writes (the shared-state premise of `external` mode HA). **Validate**: assertions pass; record the DSN/secret shape and how Mem0 self-creates its schema on first connect.

4. **Model routing through a ModelAPI-style endpoint.** Run a local LiteLLM proxy (OpenAI-compatible, port 8000) fronting a cheap real model (or a deterministic mock), configure Mem0's LLM (extraction) and embedder to use that base URL via the `{modelAPI→base_url, model}` mapping, and confirm `add(infer=True)` extracts facts and `search` embeds the query through the proxy. **Validate**: extraction produces stored facts and recall returns them, with all model traffic observably hitting the proxy; record the precise Mem0 llm/embedder config blocks for the `models.summarization`/`models.embedding` design.

5. **Token-budget working tier + rolling summary.** A relational working-store sketch (SQLite file for local, the same Postgres for external) with `(session, role, content, created_at, metadata)` rows, a token-budget bound (count tokens with a real tokenizer), recency-ordered retrieval, and a rolling-summary step that folds overflow into a summary via the proxy model. **Validate**: inserting past the budget triggers summarization (not truncation), recent turns stay verbatim, the summary is persisted and re-derivable from raw rows; record token-counting approach and summary prompt shape for M1.

6. **Pydantic AI recall-as-block slice.** A minimal pydantic-ai agent run that injects recalled facts (from TODO 2/3) as a structured system block and confirms the model can use them, plus a sketch of the full-fidelity message-history replay (a `ModelRequest`/`ModelResponse` list including `ToolCallPart`/`ToolReturnPart`) to confirm the bridge shape. **Validate**: the run consumes the recalled block; the replay list round-trips; record the presentation format for M3.

7. **Deployability check in KIND.** Stand up the `local` shape (a single container running Chroma + SQLite on a PVC) and the `external` shape (pgvector + Postgres) in KIND with throwaway manifests under `./tmp/memory/`, confirming both start, accept writes, and survive a pod restart for the external case (durable state in Postgres) versus single-replica pinning for local. **Validate**: both shapes reach Ready and serve a write/recall; record the container/PVC/secret shapes for M2/M4. Suppress kubectl noise to `./tmp/null`.

8. **Findings + plan deltas.** Write `impl/learnings/M0-feasibility-validation.md`: a go/no-go, the confirmed/refuted hypotheses, the exact Mem0 version and config shapes, the model-routing config, the working-tier approach, the deployability shapes, and a numbered list of concrete deltas to fold into M1–M7 (e.g. Mem0 API signatures that differ from the ADR sketch, schema names, any provider quirk). **Validate**: the document is complete and each later plan that an item touches is named. Commit only this learnings file (and optionally a promoted harness if clearly reusable).

## Validation per task

- Each TODO is a runnable script with assertions; "green" means the script exits 0 with its assertions satisfied. Capture command output to `./tmp/memory/<n>.log` (or `./tmp/null` when noise-only).
- No KAOS unit suites run in M0 (no production code changes). The only committed artifact is the learnings writeup.
- The KIND checks are local-only; document the commands in the learnings file so M2/M4 can reuse them.

## Commit / PR strategy

- M0 produces at most one small commit: `docs(memory): record memory feasibility validation findings and plan deltas` (kaos-ai-docs repo, no Copilot trailer per that repo's convention). If harnesses are promoted into the KAOS repo as committed scratch, that is a separate KAOS commit with the Copilot co-author trailer — but the default is to keep harnesses local and commit only the learnings.
- No stacked PR is required for M0 if it is local-only; if opened, it is a docs/learnings PR with no production code.

## Out of scope (later phases)

All production code: the long-term adapter and working store as real modules (M1), the service (M2), the runtime client (M3), the CRD/operator (M4), scope enforcement and erasure (M5), the installer (M6), and HA/durable-queue/e2e/docs (M7). M0 only proves the pieces compose and records what the real Mem0 contract looks like.
