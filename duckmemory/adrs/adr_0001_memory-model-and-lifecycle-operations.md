# ADR-0001 — Memory model and lifecycle operations

**Status:** Accepted

## Context

DuckMemory needs a conceptual memory model before any SQL surface or storage schema can be designed: which memory tiers exist, what every stored item carries, how memories are partitioned across agents/users/sessions, how recall is scored, and how memories are consolidated and forgotten. The KAOS memory effort proved a production-shaped model ([DUCK-R2](../research/DUCK-R2-reference-architectures.md) section 1) whose concepts transfer to an embedded engine, but an embedded engine serves a wider range of hosts — from a single local agent script to a framework wanting only a fact store — so the model must be layered rather than monolithic. Component 1 of the [high-level components index](./adr_high_level_components.md) defines this record's remit.

## Decision

### Tier taxonomy

DuckMemory commits three tiers, all shipped in the initial version, with the long-term fact store usable entirely on its own:

- **Short-term (turns).** Verbatim conversation events (user/agent/tool messages) scoped to a session, append-only, bounded by a configurable budget (token estimate with an event-count cap). This is the raw substrate consolidation folds from.
- **Medium-term (digest).** One rolling narrative summary per session, stored as append-only versioned rows; the latest version is the live digest. Digest text is produced by whoever runs consolidation (host-provided in the core contract; optionally engine-generated per [ADR-0004](./adr_0004_embedding-and-llm-integration-boundary.md)). Digests are never vector-indexed.
- **Long-term (facts).** Atomic memory items (extracted facts, notes, preferences, episodic records) carrying an embedding for semantic recall plus searchable text for keyword recall. This tier is the heart of the engine and has no dependency on the other two: a host may write facts directly and never use turns or digests.

Profile, temporal (bi-temporal validity), and procedural tiers are **deferred**: production evidence ([KAOS-R8](../../memory/research/KAOS-R8-production-memory-adoption-in-frameworks.md)) shows semantic/episodic facts plus a conversation window cover the dominant use, and the envelope below leaves room to add tiers without schema breakage.

### Metadata envelope

Every item carries: `id` (UUID), `kind` (tier discriminator and, for facts, an open subtype such as `fact`, `preference`, `episode`), `content` (text), scope keys (below), `event_at` (when the remembered thing happened, defaulting to ingestion), `created_at` (ingestion), `source` (free-form provenance), `importance` (float 0–1, default 0.5), `access_count` and `last_accessed_at` (recall statistics, updated by recall), `pinned` (boolean), `expires_at` (nullable TTL), and `metadata` (open JSON for host extensions). This envelope is the interoperability contract across tiers and the substrate the scoring model reads.

### Scope model

Scope is a **flat set of four nullable owner-key columns**: `namespace`, `agent_id`, `user_id`, `session_id`, with `namespace` always present (defaulting to `default`). Recall and erasure filter by exact match on every key the caller provides; keys the caller omits are unconstrained. Sharing levels are therefore expressed by *which keys a host writes and queries with* — private-to-agent memory sets `agent_id`, per-user memory sets `user_id`, fleet-shared memory sets only `namespace` — rather than by an enum the engine interprets. Hierarchical sharing (a KAOS-style scope path) is encoded by the host into `namespace` if needed; the engine stays agnostic.

There is no trusted boundary in an embedded engine ([DUCK-R2](../research/DUCK-R2-reference-architectures.md) section 1), so scope is a correctness and organization feature: its enforced property is that scope filtering happens as **pre-filtering inside every retrieval query** (never post-filtering a top-k result), preserving the correctness guarantee the KAOS research identified.

### Retrieval scoring

Hybrid recall scores candidates with a **weighted linear fusion** of four normalized signals: semantic relevance (cosine similarity of embeddings), keyword relevance (BM25, normalized), recency (exponential decay over `event_at` with configurable half-life, default 30 days), and importance (the stored float, amplified by pinning). Default weights are 0.55 relevance, 0.20 keyword, 0.15 recency, 0.10 importance; all four weights and the half-life are configurable per recall call. When the caller supplies no query embedding the semantic term drops out and weights renormalize; likewise for keyword-less recall. Recall updates `access_count`/`last_accessed_at` on returned facts.

### Consolidation

Consolidation ("fold") is the operation that moves a session's oldest short-term turns out of the live window once the budget is exceeded: evicted turns are marked folded (not deleted), the session digest gains a new version covering them, and the evicted batch is returned to the caller so extraction (host- or engine-driven per [ADR-0004](./adr_0004_embedding-and-llm-integration-boundary.md)) can write resulting facts. The trigger model is threshold-based (fold when the live window exceeds `budget`, folding down to `target`), but *when* folding executes is an execution-model question settled in [ADR-0002](./adr_0002_sql-interface-and-embedded-execution-model.md).

### Forgetting

Four primitives: **decay** (recency weighting in scoring — ranking-only, never deletion), **pinning** (exempts an item from TTL expiry and boosts importance), **TTL expiry** (items past `expires_at` are excluded from recall and physically removed by an explicit purge operation), and **hard erasure** (synchronous scope-targeted deletion across all three tiers in one call, the right-to-erasure primitive).

## Consequences

- **Positive.** The fact store stands alone, so the simplest host integration is one INSERT and one recall query; the flat scope columns map directly onto indexed pre-filtering `WHERE` clauses ([ADR-0003](./adr_0003_storage-indexing-and-retrieval.md)); the envelope is stable across deferred tier additions; scoring is a pure function over envelope columns, implementable in SQL and unit-testable in isolation.
- **Negative.** Hosts wanting hierarchical prefix-sharing must encode it into `namespace` themselves; deterministic (non-LLM) digests are weaker than KAOS's summarized digests unless the host supplies summaries; ranking-only decay means an unmaintained store grows until the host purges.
- **Follow-on.** Token estimation for the budget needs a cheap deterministic heuristic (chars/4) documented as approximate; the purge operation and erasure fan-out must be covered by tests before any distribution.

## Alternatives considered

- **Long-term facts only (no turns/digest).** Simplest possible engine, but abandons the end-to-end goal — every host rebuilds the window/fold pipeline KAOS proved is the hard, valuable part; rejected.
- **Enum scope levels (KAOS's `private|user|shared|session`).** Clean in a system that owns identity, but an embedded engine cannot verify identities, and the enum forces one sharing topology on all hosts; flat keys express the same four levels and more; rejected.
- **Hierarchical scope paths in the engine.** Maximum flexibility, but prefix semantics complicate every query and index, and [DUCK-R2](../research/DUCK-R2-reference-architectures.md) shows flat keys served KAOS in production; hosts can encode hierarchy into `namespace`; rejected for the core.
- **Reciprocal-rank fusion instead of weighted linear scoring.** RRF is robust to incomparable score scales, but it discards the recency/importance signals unless they form their own ranked lists, and its output is harder to explain to hosts; weighted fusion with documented normalization is chosen, with RRF revisitable in [ADR-0003](./adr_0003_storage-indexing-and-retrieval.md) once real relevance data exists.
- **Automatic background decay-deletion.** Requires a daemon an embedded engine does not have, and silent deletion is hostile to hosts; explicit purge chosen instead.
