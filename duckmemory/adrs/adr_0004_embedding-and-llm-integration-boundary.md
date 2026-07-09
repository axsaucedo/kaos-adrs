# ADR-0004 — Embedding and LLM integration boundary

**Status:** Accepted

## Context

This is the decision the [high-level components index](./adr_high_level_components.md) deliberately left open: how much of the intelligence loop lives inside the engine versus with the host. It determines whether DuckMemory is a self-contained end-to-end memory engine (text in, memories out) or a storage/retrieval core with a bring-your-own-models contract. [DUCK-R1](../research/DUCK-R1-duckdb-extension-ecosystem.md) section 3 establishes that every option is technically viable in a DuckDB extension (flockmtl performs LLM calls in SQL; quackformers runs local embedding inference from Rust); the question is purely architectural. Three surfaces are in play: **embedding generation** (needed by both write and recall), **fact extraction** (turning folded turns into atomic facts), and **digest summarization** (the medium-term tier's narrative).

## Options and trade-offs

### Option A — Pure storage/retrieval (host provides everything)

The engine accepts pre-computed embeddings and pre-extracted facts; it never opens a network connection.

- **Pros.** Maximum portability (works air-gapped, in WASM-adjacent contexts, under any compliance regime); fully deterministic and trivially testable; zero credential handling; no latency or failure modes inside SQL statements; the engine's correctness is independent of any model.
- **Cons.** Every host must build an embedding pipeline before the first recall works — the single biggest adoption cliff for the "memory engine in a database" story; recall-by-text (the natural agent call) is impossible without host glue; the end-to-end project goal is unmet.

### Option B — Embeddings in-engine, LLM work host-side

The engine can call a configured OpenAI-compatible embedding endpoint; extraction and summarization remain host recipes.

- **Pros.** Recall and write become self-contained (`memory_recall_text('what does the user prefer?')` just works), which is the majority of day-to-day calls; embedding calls are cheap, fast, deterministic-ish (same input → same vector), and low-risk compared to generative calls; one credential, one endpoint shape (the OpenAI embeddings API is the de-facto universal contract, served by OpenAI, Azure, Ollama, LiteLLM, vLLM, TEI and others); testable with a trivial stub server.
- **Cons.** Network I/O inside query execution (mitigable with batching and short timeouts); a credential enters the database process (mitigated by DuckDB's secrets manager, never persisted in extension tables); offline hosts fall back to Option A behaviour.

### Option C — Full end-to-end in-engine (embeddings + extraction + summarization)

`memory_fold` calls a chat-completion endpoint to extract facts and summarize digests, flockmtl-style.

- **Pros.** The strongest possible story: one SQL call performs write → fold → extract → consolidate; zero host intelligence required; matches the original end-to-end ambition most literally.
- **Cons.** Generative calls are slow (seconds), expensive, non-deterministic, and failure-prone — embedding them inside SQL statements makes fold latency unbounded and tests model-dependent; prompt engineering becomes engine API surface (extraction quality disputes become bug reports); the concurrency picture from [ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md) (mutex-guarded retained connection) serializes long LLM calls behind a lock; and KAOS's evidence ([DUCK-R2](../research/DUCK-R2-reference-architectures.md)) is that extraction wants batching, retries, and background execution — exactly what a daemonless engine lacks.

### Option D — Local embedding inference in-engine (quackformers-style)

- **Pros.** Self-contained *and* offline.
- **Cons.** Bundles model weights and an inference runtime into the extension binary (size, platform matrix, licensing), fixes model choice at build time, and duplicates what Ollama-class local servers already expose through the Option B endpoint shape; rejected as a core path — Option B with a local endpoint covers the offline case better.

## Decision

**A layered contract: Option A is always available, Option B is the shipped convenience, Option C is deferred, Option D is rejected.**

- **Layer 0 (always).** Host-provided embeddings and host-side extraction are first-class and permanent: every write and recall path accepts vectors directly, and `memory_fold` remains deterministic (evict, version the digest with a verbatim-window fallback summary, return the folded batch) so a host-side extractor can consume the batch and write facts back. The engine never *requires* a network.
- **Layer 1 (shipped, opt-in by configuration).** An in-engine embedding client: `memory_embed(text)` scalar function calling a configured OpenAI-compatible embeddings endpoint, plus `memory_recall_text(...)`/`memory_context_text(...)` conveniences that embed the query then delegate to the Layer 0 macros. Configuration via extension settings (`memory_embedding_endpoint`, `memory_embedding_model`) with the API key resolved through **DuckDB's secrets manager** — never stored in extension tables. Batching for multi-row embedding, short default timeout (5s), and a hard degradation rule: embedding failure fails the *convenience* call with a clear error, never corrupts state, and Layer 0 remains usable.
- **Layer 2 (deferred, seam reserved).** In-engine extraction/summarization is not shipped in v1. The fold contract (returned folded batch, digest versioning, open `kind` on facts) is the reserved seam: a future `memory_extract` can slot in without schema or surface breakage once the retained-connection execution model is proven under long-running calls. This is a deferral on evidence, not a rejection — recorded so the decision is revisited after real usage data.

## Consequences

- **Positive.** The adoption path is smooth at both ends: a laptop agent gets text-in/memories-out with two settings and a secret, while a framework with its own pipeline uses pure Layer 0 and the engine stays deterministic; testing needs only a stub HTTP server for Layer 1 and nothing for Layer 0; the end-to-end goal is met for the hot path (recall/write) where it matters daily, and deliberately unmet for the slow path (extraction) where a daemonless engine is the wrong executor today.
- **Negative.** Extraction quality is the host's problem in v1 — DuckMemory without a host extractor accumulates verbatim-fallback digests and manually written facts only; two recall entry points (vector and text) must stay behaviorally identical, a documented test invariant.
- **Follow-on.** P3 implements Layer 1 with a stub-server SQLLogicTest harness; the Layer 2 revisit criterion is recorded here: implement in-engine extraction when (a) the retained-connection model has proven safe under multi-second calls and (b) at least one real host demonstrates the deterministic fold + host extraction loop is the adoption blocker.

## Alternatives considered

The options above are the alternatives; the layered decision subsumes A and B, defers C with an explicit revisit criterion, and rejects D (local inference bundling) in favour of pointing local endpoints at Layer 1's universal API shape.
