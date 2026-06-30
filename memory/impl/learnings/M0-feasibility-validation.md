# Memory feasibility validation — findings and plan deltas

## Verdict

**GO.** All five load-bearing hypotheses behind the memory architecture hold against running code. Six harnesses in the gitignored `./tmp/memory/` exercise each hypothesis with assertions and pass. The Mem0-as-a-library design, scope pre-filtering, ModelAPI routing, server-owned working tier, Pydantic AI bridge, and both storage shapes are all confirmed. The deltas below are API-shape corrections to fold into M1–M7, not design reversals.

## Environment and exact versions

Validated on macOS, Python 3.13.6, Docker and KIND available. Throwaway venv at `./tmp/memory/.venv`. Resolved versions actually installed (pin these in M1):

- `mem0ai` **2.0.10** (the 2.x line — materially different API from the 1.x sketch the ADRs assumed; see deltas)
- `chromadb` 1.5.9, `pgvector/pgvector:pg16` (container), `psycopg` 3.3.4 with `psycopg_pool`
- `litellm` 1.90.1, `pydantic-ai` 2.1.0, `tiktoken` (cl100k_base)

## Hypotheses — confirmed

1. **Mem0 runs as a library against both Chroma and pgvector with scope filters applied inside the vector query.** Harness 02 (Chroma) and 03 (pgvector) write identical-embedding facts for different owners and prove a scoped search never returns another owner's fact, even when it is an exact nearest neighbour — i.e. **pre-filtering**, not lossy post-filtering. Both stores pre-filter correctly.
2. **Extraction and embedding route through an OpenAI-compatible base URL (the KAOS ModelAPI/LiteLLM binding).** Harness 04 points Mem0's LLM and embedder at a mock OpenAI server via `openai_base_url`; `add(infer=True)` extracts and stores a fact and `search` recalls it, with all model traffic observably hitting the proxy (1 chat + 3 embedding calls).
3. **Token-budget working tier with a rolling summary is cheap on a plain relational table.** Harness 05 implements the SQLite working table, counts tokens with a real tokenizer, and folds overflow into a rolling summary (via the proxy) while keeping recent turns verbatim and retaining raw rows for re-derivation. Eviction is by summarization, not truncation.
4. **Recalled facts surface to a Pydantic AI run, and full-fidelity history replays.** Harness 06 injects recall as an instructions block consumed by the run, and round-trips a `ModelRequest`/`ModelResponse` history including a `ToolCallPart`/`ToolReturnPart` through the official type adapter with matching tool-call ids, then replays it into a new run.
5. **Both storage shapes stand up durably.** Harness 03 proves the `external` premise (two independent Mem0 clients on one Postgres see each other's writes — a restarted stateless replica re-attaches losslessly). Harness 07 proves the `local` premise (embedded Chroma + SQLite on one directory survive a process teardown and re-open — the single-container PVC restart).

## Deltas to fold into the plans

1. **[M1, M2, M3] Mem0 2.x API shape differs from the ADR/1.x sketch.** `add(messages, *, user_id=, agent_id=, run_id=, infer=True, ...)` and `search(query, *, top_k=, filters=, threshold=, rerank=, ...)`. Owner scoping at **search** time is via the `filters` dict (`{"user_id": ..., "agent_id": ..., "run_id": ...}`), not positional kwargs. `delete(memory_id)`. M1's `LongTermStore` adapter must target these signatures and pin `mem0ai==2.0.10` (or the chosen 2.x).

2. **[M5, ADR 0005] `search` requires at least one owner id in `filters`** (`user_id`/`agent_id`/`run_id`) and raises `ValueError` otherwise — a pure "no-filter shared" recall is **not** allowed. The `shared` scope therefore cannot map to "no owner filter"; it must map to a **dedicated shared owner key** (e.g. a fixed `agent_id`/group id representing the store-wide shared namespace, or a shared `user_id`). Update ADR 0005's scope→filter table: `private→agent_id`, `user→user_id`, `session→run_id`, `shared→a reserved shared owner id`. Mem0 2.x also supports rich filter operators and `AND/OR/NOT`, which gives M5 room for composite scope rules.

3. **[M1, M4] Embedding dimension and provider config.** Init Mem0 with a recognised embedder provider (`openai`) — the `MemoryConfig` pydantic validator rejects unknown provider names at config time, so a custom embedder must be swapped onto `m.embedding_model` after `from_config` (used in the harnesses) or registered properly. For real deployments the embedder is `openai` pointed at the ModelAPI base URL. Chroma config rejects `embedding_model_dims`; it infers dims from the first vector. pgvector config **accepts** `embedding_model_dims` and needs it set to the embedding model's dimension.

4. **[M1] `external` mode needs `psycopg[pool]`.** Mem0's pgvector store imports `psycopg_pool.ConnectionPool`; `psycopg[binary]` alone is insufficient. M1/M2 dependency pins for external mode must include `psycopg[pool]` (or `psycopg2`).

5. **[M2, M7] Disable Mem0 telemetry.** Mem0 enables PostHog analytics by default (observed "Multiple active PostHog clients" warnings; outbound analytics). The memory service must disable this (env/config) so it does not phone home from clusters — add to M2 service config and call it out in M7 hardening.

6. **[M2] Optional NLP extra.** Mem0 logs "spaCy is not installed" and disables lemmatisation-based dedup without `mem0ai[nlp]`. Hash-based dedup still works. M2 should decide whether to install the `[nlp]` extra (better dedup, larger image) — default to **without** for image size unless dedup quality requires it.

7. **[M2, M7] Recall quality differs by store: Chroma has no keyword/hybrid (BM25) search; pgvector does.** Mem0 warns that hybrid scoring is disabled on Chroma. So `local` mode is semantic-only while `external` (pgvector) can do hybrid. Document this as an expected capability difference between modes (not a bug) and prefer pgvector where recall quality matters.

8. **[M3] Pydantic AI bridge specifics (2.1.0).** Instructions/recall blocks attach to `ModelRequest.instructions` (not stored as a message part) — M3's recall-as-block presentation should pass recall via `instructions` (or a system block) per run. Full-fidelity replay uses `ModelMessagesTypeAdapter.dump_python`/`validate_python`; `ToolCallPart(tool_name, args, tool_call_id)` and `ToolReturnPart(tool_name, content, tool_call_id)` round-trip losslessly and are accepted as `message_history`.

9. **[M5] Mem0 2.x `add(infer=True)` is a single-call V3 pipeline** returning `{"memory": [{"text": ...}]}` (not the older two-call extract-then-update flow). The extraction LLM call uses `response_format={"type": "json_object"}`. M5/M2 prompt-shaping and any extraction-prompt overrides target this single additive-extraction call. Agent-scoped adds (`agent_id` set, no `user_id`) append an agent-context suffix to the system prompt — relevant to how `private` scope behaves.

10. **[M2, M4, M7] KIND packaging was deferred, not skipped.** A true in-cluster deploy needs the M2 service image, which does not exist in M0. The data-durability cores are already proven at the library layer (deltas above). M2 builds the image; M4 authors the `local` (single container, Chroma+SQLite, one PVC, single replica) and `external` (pgvector + Postgres, stateless replicas) manifests; M7 promotes the restart-durability checks to committed e2e on KIND. The harness shapes here are the reference for those manifests.

## Harness index (reference for later phases)

- `02_chroma_scope.py` — Chroma scope pre-filtering + owner-less rejection.
- `03_pgvector_scope.py` — pgvector scope pre-filtering + shared-state across clients (external HA premise).
- `04_model_routing.py` + `mock_openai.py` — extraction/embedding routed through a ModelAPI-style base URL.
- `05_working_tier.py` — token-budget working table with rolling summary (server-owned working tier).
- `06_pydantic_bridge.py` — recall-as-block + full-fidelity tool-call history replay.
- `07_local_persistence.py` — local single-container Chroma+SQLite PVC restart durability.

These stay local under `./tmp/memory/` (gitignored). Only this learnings document is committed.
