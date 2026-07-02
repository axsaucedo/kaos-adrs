# ADR 0003 — Memory interface and runtime data plane

- **Status.** Proposed
- **Date.** 2026-06-30
- **Component.** 3 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md), [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md), [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md), [KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)
- **Constrains.** ADR 0004 (deployment topology and control plane), ADR 0005 (multi-tenancy and grouping).

## Context

[ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) fixes the conceptual model and [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md) chooses Mem0 as the long-term engine while keeping short-term memory owned by KAOS. This record decides the runtime contract that joins them: the `Memory` abstraction in the Pydantic AI data plane, the redesign of the short-term tier, the long-term operation set, how recalled context reaches the agent, and where scope and observability boundaries sit.

The current `Memory` abstraction is short-term tier-only. Sessions hold an event deque bounded by a fixed maximum length, `build_message_history` replays only `user_message` and `agent_response` events while dropping tool calls, tool results, and delegations, and overflow is handled by truncation. There are no long-term operations. KAOS is in alpha, so this record is not constrained by backward compatibility: the interface, configuration keys, and storage choices are redesigned for the target shape rather than preserved. Source surfaces: `pydantic-ai-server/pais/memory.py`, `pydantic-ai-server/pais/server.py` (`_create_memory`), `pydantic-ai-server/pais/serverutils.py`.

[KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md) established that short-term memory must not be delegated to Mem0 — the vector engine embeds every turn, exposes no ordered raw-turn store, and is not replica-safe for high-frequency writes — so the short-term tier stays a KAOS-owned plain store, consolidated onto the same Postgres instance Mem0 uses for its vector store.

## Decision

### One extended `Memory` abstraction

There is a single `Memory` abstraction, extended from the short-term-only contract into a tiered one. Long-term operations — write/extract, recall, consolidate, forget — are added to the same abstraction; a backend that serves only short-term memory leaves them unimplemented or no-op. The contract is shaped around the realities of [ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md): scope is a first-class argument on every operation, writes are extraction-bearing, and recall is relevance search. Because KAOS is in alpha, the existing method surface and `MEMORY_*` configuration are redesigned rather than preserved; there is no compatibility shim. Both tiers expose a single write verb `add` (mirroring the long-term engine's own `add`) rather than divergent `append`/`write` names, so the store surfaces read uniformly.

### Short-term tier: token budget with opt-in rolling summary

The short-term tier is bounded by a configurable token budget rather than a fixed event count, with an event-count ceiling retained only as a hard safety cap. Recent turns are kept verbatim until the token budget (or hard cap) is reached; on overflow the oldest turns beyond the budget are evicted, always keeping at least the most recent turn. Eviction has two modes, selected by configuration:

- **Recency window (default).** Overflowing turns are dropped. This is the LangChain buffer-window behaviour: cheap, no model call, and the durable record still lives in the long-term tier. Rolling summarization is **disabled by default** — for most agents a bounded recency window is sufficient, and summarizing on every overflow is unnecessary cost.
- **Rolling summary (opt-in).** When explicitly enabled, the overflowing turns are folded into a single rolling summary instead of dropped, so nothing is lost from the short-term view. The fold is **one summariser call over the whole overflow chunk** — per overflow event, not per message (the MemGPT / LangChain summary-buffer pattern) — and runs **off the response hot path**: the write returns immediately after the cheap insert, the overflow turns are marked pending and removed from the active window synchronously, and the summariser call is scheduled asynchronously, triggered by the overflow at write time (not by a separate store-polling job). Folded turns are transient — deleted once absorbed into the summary — so the store does not grow unboundedly per scope.

Both the token budget and whether summarization is enabled are configuration, surfaced through the control plane in [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md). This matches established practice in comparable frameworks ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).

### Short-term tier storage: a plain table on the shared Postgres

Short-term memory is persisted as plain relational rows — session, role, content, and created time (a per-turn metadata column is deferred until a consumer needs it, per KEEP IT SIMPLE) — co-located with the long-term store, with no embeddings and recency-ordered retrieval. It is never on Redis and never delegated to Mem0; it is a cheap insert-and-recency-scan rather than a vector operation ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)). [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) realises "co-located" per storage mode: in `external` mode the short-term table lives on the **same Postgres instance** that backs Mem0's pgvector long-term store; in `local` mode it is a SQLite table in the same single container as the embedded Chroma store. Either way the short-term tier follows the storage mode automatically and shares the long-term store's datastore rather than introducing a separate one. The provisioning of that datastore is an [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) concern; this record fixes only that the short-term tier is relational and co-resident with the long-term store.

### Message-history bridge: full-fidelity replay

The Pydantic AI message-history bridge replays the full interaction, including `ToolCallPart`, `ToolReturnPart`, and delegation parts, so a continuing run sees its own prior tool use rather than a text-only reconstruction. Overflow is summarized rather than truncated, consistent with the short-term tier bound. This corrects the current behaviour where tool and delegation events are stored but dropped on replay.

```text
# replayed message_history for a continuing run
ModelRequest[UserPromptPart "what's the weather in NYC?"]
ModelResponse[ToolCallPart search(city="NYC")]      # previously dropped, now replayed
ModelRequest[ToolReturnPart search -> "rainy, 12C"]  # previously dropped, now replayed
ModelResponse[TextPart "It's rainy and 12C in NYC."]
```

### Long-term operation set and execution shape

The long-term surface is recall, write/extract, consolidate, and forget. **Recall is synchronous** on the agent hot path and low-latency: a relevance search returning scoped facts. **Write/extract, consolidate, and forget are asynchronous**, run off the hot path, because extraction is LLM-gated and KAOS autonomous loops emit many events ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)). The background execution mechanism is an [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md) concern; this record fixes only the synchronous-versus-asynchronous split of the interface.

### Recall presentation: structured block by default, tools opt-in

Recalled long-term context is presented to the agent as a **structured memory block** injected into the system context by default — deterministic, always-on, and cheap. In addition, **opt-in memory tools** (a save and a load/search tool, in the kagent and ADK style) can be enabled so an agent can deliberately store a finding or query memory mid-run. Both the default block and the optional tools are configurable per agent, surfaced through the control plane in [ADR 0004](./adr_0004_deployment-topology-and-control-plane.md). Recalled facts are not injected as fabricated prior turns in the message history.

### Scope injection: server-side, never trusted from the caller

Tenant and agent scope on every memory operation is injected at the `Memory` backend boundary from the authenticated request context and the agent's verifiable identity — the user principal and the AIB `client_id` from [ADR 0001](./adr_0001_memory-model-and-lifecycle-operations.md) — and is never read from caller-supplied or model-supplied arguments. Because Mem0's isolation is application-level filtering with no row-level security ([ADR 0002](./adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md)), the backend is the enforcement point: a recall or write that cannot resolve a trusted scope fails closed rather than querying an unscoped store. The full multi-tenancy and grouping model is owned by [ADR 0005](./adr_0005_multi-tenancy-agent-grouping-and-governance.md); this record fixes that scope is a server-side-injected, non-spoofable argument.

### Observability boundary: ABC method spans with engine sub-spans

OpenTelemetry instrumentation sits at the `Memory` abstraction method boundary, so every backend emits uniform spans (`kaos.memory.recall`, `kaos.memory.write`, `kaos.memory.consolidate`, `kaos.memory.forget`), with engine-specific work (embedding, vector search, extraction) nested as child spans inside the engine backend. This guarantees uniform coverage regardless of backend while still exposing engine detail where it matters, and follows KAOS's existing `tracer.start_as_current_span("kaos.…")` convention (`pydantic-ai-server/pais/a2a.py`, `server.py`). The instrumentation is emitted by KAOS regardless of Mem0's own telemetry.

## Consequences

- The data plane gains a tiered memory contract: a relational, token-budgeted, summarizing short-term tier and a Mem0-backed long-term tier, behind one abstraction.
- The platform consolidates the short-term and long-term tiers onto one datastore — a shared Postgres in `external` mode or a single-container SQLite-plus-Chroma in `local` mode ([ADR 0004](./adr_0004_deployment-topology-and-control-plane.md)) — and drops the separate Redis memory dependency.
- Continuing and autonomous runs replay full-fidelity history including tool and delegation steps, fixing a real loss in the current bridge.
- Recall is cheap and deterministic by default, with agent-driven memory tools available when wanted; both are per-agent configuration consumed by the control plane.
- Tenant isolation is enforced in the data plane at the backend boundary, not delegated to the engine, and fails closed.
- Memory operations are uniformly observable across backends.
- Because alpha allows breaking changes, the existing `Memory` surface and `MEMORY_*` configuration are replaced; deployments are migrated rather than transparently upgraded.
- The memory-service package is organised by layer into a few cohesive modules rather than many single-responsibility micro-files (`stores.py` — the two atomic stores plus the scope, token-counting, and model-client engine they need; `config.py` — typed config and environment resolution; `app.py` — the HTTP surface: schemas, routes, presentation, background runner, entrypoint), per the KEEP IT SIMPLE principle. Files stay well under an ~800-line ceiling without fragmenting into ~100-line units.

## Alternatives considered

- **Compose separate short-term and long-term interfaces.** Rejected: one abstraction with optional long-term operations is simpler and matches how the runtime already selects a single backend.
- **Delegate short-term memory to Mem0 (one engine, both tiers).** Rejected on the embedding-per-turn cost, the absence of a public ordered raw-turn store, the process-local non-replica-safe internal buffer, and concurrency and isolation issues under high-frequency writes ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).
- **Keep short-term memory on Redis.** Rejected: pgvector on a single shared Postgres is the more durable, multi-tenant-friendly, and operationally simpler system of record, and consolidating to one datastore is a goal ([KAOS-R11](../research/KAOS-R11-short-term-memory-storage.md)).
- **Token-buffer without summarization.** Considered as a first step; rejected as the committed shape because summarization is configurable and matches comparable frameworks, though it may ship after the plain token-budget.
- **Inject recall as fabricated prior turns.** Rejected: a structured block is clearer and avoids polluting the verbatim history.
- **Preserve the current interface for compatibility.** Rejected: alpha permits breaking changes, and the current event-deque-and-text-only contract is the thing being redesigned.

## Follow-up

- ADR 0004 fixes the Postgres provisioning, the background queue and workers for asynchronous writes and consolidation, the central-service topology, and the high-availability engineering; and surfaces the short-term tier budget, summarization toggle, and recall-presentation options as control-plane configuration.
- ADR 0005 fixes the full multi-tenancy, scope-hierarchy, and agent-grouping model that the server-side scope injection enforces.
- The reusable Pydantic AI adapter's packaging boundary (in-tree versus a standalone published package) is decided alongside this interface.
