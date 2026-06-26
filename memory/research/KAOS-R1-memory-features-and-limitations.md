# KAOS-R1 — Current memory features and limitations

This document is the requirements baseline for the KAOS memory investigation. It describes, with source citations, exactly how memory works in KAOS today, what architectural properties that design has, and where its concrete limitations and gaps are. Later research stages refer back to this document when defining selection criteria and the target design.

The findings here are drawn from a curated reading of the implementation rather than from prior discussion: the runtime memory module, its runtime integration, the control-plane CRD and reconciliation that configure it, and the user-facing documentation. The in-scope sources are listed at the end under [Context manifest](#context-manifest).

## Summary

KAOS memory is a fully custom, hand-rolled **conversation-log** subsystem. It records a bounded, ordered stream of typed events per session and replays a recent slice of that stream as Pydantic AI `message_history` on each agent run. It offers two real backends — an in-process store and a Redis-backed distributed store — plus a no-op backend for disabling memory. It is configured declaratively through an Agent CRD block that the operator translates into `MEMORY_*` environment variables on the agent pod.

What KAOS memory is **not**: it is not a semantic or long-term memory. There is no retrieval by relevance, no embeddings or vector search, no summarization or consolidation, no knowledge/entity extraction, no cross-session or per-user memory, and no notion of importance or forgetting beyond recency-based eviction. Memory is a chronological tail of the current conversation, capped by count.

## Architecture overview

Memory is defined by a single abstract base class with three concrete backends, all in one module.

- `Memory` (ABC) — the interface every backend implements, plus shared helpers for event creation and Pydantic AI bridging. Source: `pydantic-ai-server/pais/memory.py:68-227`.
- `LocalMemory` — in-process storage backed by a per-session bounded `deque`. Source: `memory.py:230-370`.
- `NullMemory` — a no-op implementation whose methods succeed silently and store nothing. Source: `memory.py:373-410`.
- `RedisMemory` — distributed storage backed by Redis hashes, lists, and a sorted-set index. Source: `memory.py:413-695`.

The runtime selects a backend at server construction time via `_create_memory` and threads a single `Memory` instance through the `AgentServer`. Source: `pydantic-ai-server/pais/server.py:646-664`.

## Data model

Two dataclasses define the stored shape. Source: `memory.py:16-65`.

- `MemoryEvent` — a single event with `event_id`, `timestamp` (UTC), `event_type` (string), `content` (arbitrary), and `metadata` (dict). It serializes to and from a plain dict for storage. Source: `memory.py:16-43`.
- `SessionMemory` — a session container with `session_id`, `user_id`, `app_name`, an `events` deque, and `created_at` / `updated_at` timestamps. Source: `memory.py:46-65`.

Event types are an open string vocabulary, not an enum. The set used in practice is: `user_message`, `agent_response`, `tool_call`, `tool_result`, `delegation_request`, `delegation_response`, `task_delegation_received`, `access_outcome`, and `error`. Sources: documentation table in `docs/python-framework/memory.md`, and emission sites in `server.py:399-503` and `memory.py:188-215`.

`MemoryEvent.metadata` can carry OpenTelemetry trace context. `create_event` enriches metadata with the current trace context when OTel is enabled, linking stored events to traces. Source: `memory.py:104-123`.

## The `Memory` interface

The ABC declares the storage contract and provides shared, non-abstract helpers.

Abstract storage operations (`memory.py:71-102`):

- `create_session(app_name, user_id, session_id=None) -> session_id`
- `get_session(session_id) -> SessionMemory | None`
- `get_or_create_session(session_id, app_name, user_id) -> session_id`
- `add_event(session_id, event_or_type, content=None, metadata=None) -> bool`
- `get_session_events(session_id, event_types=None) -> list[MemoryEvent]`
- `list_sessions(user_id=None) -> list[str]`
- `delete_session(session_id) -> bool`

Shared concrete helpers on the ABC:

- `create_event(...)` — constructs a `MemoryEvent` with a generated id and optional trace metadata. Source: `memory.py:104-123`.
- `build_conversation_context(session_id, max_events=20) -> str` — renders recent `user_message` / `agent_response` events as a plain `User:` / `Assistant:` transcript. Source: `memory.py:125-140`.
- `build_message_history(session_id, context_limit=6) -> list | None` — reconstructs Pydantic AI `ModelRequest` / `ModelResponse` objects from stored events, excluding the latest user prompt and truncating to the last `context_limit` replayable events. Only `user_message` and `agent_response` events are replayed into history. Source: `memory.py:142-176`.
- `store_pydantic_message(session_id, msg)` — converts Pydantic AI tool-call and tool-return parts into `tool_call` / `tool_result` (or `delegation_request` / `delegation_response` when the tool name begins with `delegate_to_`) events. Source: `memory.py:178-215`.
- `get_memory_stats()`, `cleanup_old_sessions(max_age_hours=24)`, `close()` — default implementations that backends override. Source: `memory.py:217-227`.

### Pydantic AI bridge

The bridge is the load-bearing integration with the agent runtime. On each run the runtime calls `build_message_history` to produce `message_history`, and after the run it calls `store_pydantic_message` for each new message plus `add_event(..., "agent_response", ...)` for the final output. Sources: `server.py:401-436`, `server.py:485-489`.

The bridge is lossy by construction. `build_message_history` replays only `user_message` and `agent_response` events into history; tool calls and tool results are stored but not reconstructed into the replayed `message_history`, so prior tool interactions do not re-enter the model context on subsequent turns. Source: `memory.py:170-176`.

## Backends

### LocalMemory

In-process storage keyed by `session_id` in a plain dict, with each session's events held in a `deque(maxlen=max_events_per_session)`. The deque bound gives O(1) automatic eviction of the oldest events once a session exceeds its cap. Source: `memory.py:230-304`.

Session-count is bounded separately: before creating a new session, `_cleanup_sessions_if_needed` removes the oldest ~10% of sessions (by `updated_at`) once `max_sessions` is reached. A time-based `cleanup_old_sessions` also exists but is not invoked on a schedule. Sources: `memory.py:358-370`, `memory.py:342-356`.

Properties: fast, dependency-free, and entirely **per-pod and non-persistent**. State is lost on restart and is not shared across replicas. `get_or_create_session` carries a `TODO` acknowledging a race condition under concurrent requests (no lock). Source: `memory.py:269-276`.

### NullMemory

A no-op backend: every method returns success and stores nothing, `get_session` returns `None`, and event/session listings return empty. Used when memory is disabled, giving stateless agents with zero memory overhead. Source: `memory.py:373-410`.

### RedisMemory

Distributed, persistent storage with a deliberate key layout. Source: `memory.py:413-695`.

- Session metadata is a Redis hash at `kaos:memory:session:<id>` (HSET/HGETALL).
- Events are a Redis list at `kaos:memory:events:<id>`, appended with RPUSH and capped with LTRIM to `max_events_per_session` (append-only conversation log).
- A sorted set `kaos:memory:sessions` indexes sessions by last-update timestamp for listing and cleanup.
- Writes use a single pipeline (RPUSH + LTRIM + HSET + ZADD + EXPIRE) for atomicity, and both session and event keys carry a TTL (`session_ttl_hours`, default 24h) for automatic retention. Sources: `memory.py:537-572`, `memory.py:483-509`.

It adds index hygiene (`list_sessions` reaps sorted-set entries whose keys have expired) and de-duplicates events by `event_id` when reading. Sources: `memory.py:601-633`, `memory.py:582-599`. Like `LocalMemory`, `get_or_create_session` carries a `TODO` to make check-and-create atomic (SETNX). Source: `memory.py:530-535`.

Properties: survives pod restarts and is shared across replicas, enabling horizontal scaling of the agent runtime. It is still a per-session capped event log; Redis is used as a durable list store, not as a search or vector index.

## Runtime integration

`_create_memory` maps settings to a backend: `NullMemory` when memory is disabled; `RedisMemory` when `memory_type == "redis"` and a Redis URL is set; otherwise `LocalMemory`. A `redis` type with no URL logs a warning and falls back to `LocalMemory`. Source: `server.py:646-664`.

Per-run lifecycle (`server.py`):

- Setup ensures the session exists, records the incoming `user_message`, and builds `message_history` bounded by `memory_context_limit`. Source: `server.py:393-406`.
- After a (non-streaming) run, each new Pydantic AI message is persisted via `store_pydantic_message`, then the final `agent_response` is recorded. The streaming path mirrors this. Sources: `server.py:430-436`, `server.py:485-489`.
- Error and access-control outcomes are also recorded as events (`error`, `access_outcome`). Source: `server.py:499-503`.

HTTP surface: `GET /memory/events` and `GET /memory/sessions` are always enabled (used by the UI and for debugging), exposing stored events and session ids. Source: `server.py:247-276`.

Settings (`AgentServerSettings`) expose the tunables consumed by `_create_memory`: `memory_enabled`, `memory_type`, `memory_context_limit`, `memory_max_sessions`, `memory_max_session_events`, `memory_redis_url`. Source: `pydantic-ai-server/pais/serverutils.py:402-408`.

## Control-plane configuration

The Agent CRD carries a `MemoryConfig` block. Source: `operator/api/v1alpha1/agent_types.go:51-80`.

- `enabled` (default `true`) — when false, `NullMemory` is used.
- `type` (default `local`, enum `local|redis`).
- `contextLimit` (default `6`, 1–100) — replayed-history size.
- `maxSessions` (default `1000`, 1–100000).
- `maxSessionEvents` (default `500`, 1–10000).

The agent controller translates these into `MEMORY_*` env vars on the pod. Notably, when `type == redis` and the user has not set `MEMORY_REDIS_URL` in `spec.container.env`, the controller injects the operator's `DEFAULT_REDIS_URL` — so the Redis endpoint is an operator-level default, not part of the CRD schema. Source: `operator/controllers/agent_controller.go:599-653`.

There is no dedicated memory CRD, no shared memory resource across agents, and no per-user or namespace-scoped memory object — memory is purely a per-Agent configuration that yields a per-Agent (or, with Redis, per-Redis-instance) store.

## Documentation coverage

User docs describe the three backends, env/CRD configuration, the enabled/disabled gating, the Pydantic AI bridge and event-to-message mapping, the event-type vocabulary, session/event APIs, the always-on endpoints, and Redis usage. Source: `docs/python-framework/memory.md`. A worked Redis example exists at `docs/examples/redis-memory.md`. The docs accurately reflect the implementation and confirm the "recent-events context window" framing.

## Features (what works today)

- Pluggable backend behind a single ABC: local, Redis, and null.
- Per-session, ordered, typed event log with rich event vocabulary (messages, tool calls, delegations, errors, access outcomes).
- Automatic bounded retention: per-session event cap and per-store session cap, plus Redis TTL.
- Pydantic AI bridge that gives multi-turn conversational continuity within a session.
- Distributed, persistent, multi-replica operation via Redis with atomic pipelined writes and index hygiene.
- Declarative CRD configuration reconciled to env vars, with an operator-level default Redis URL.
- Disable path (`NullMemory`) for stateless agents.
- OpenTelemetry trace context attached to events; always-on inspection endpoints for the UI.

## Limitations and gaps

These define the headroom that production-grade memory must address. They are grouped by theme.

### Memory model is a recency-capped conversation log

- No semantic / long-term memory: storage and recall are chronological, not relevance-based.
- No retrieval: there is no query-by-similarity, no embeddings, and no vector index; `build_message_history` simply takes the last N replayable events. Source: `memory.py:167-176`.
- No summarization or consolidation: old events are evicted, not compressed, so information beyond the window or the cap is lost rather than distilled.
- No knowledge/entity extraction and no knowledge graph: events are opaque content blobs.
- No importance, salience, or forgetting policy beyond recency/TTL eviction; deque/LTRIM drop the oldest events regardless of value. Sources: `memory.py:254`, `memory.py:560`.

### Scope is per-session only

- No cross-session memory and no per-user profile/memory: `user_id` is stored and can filter `list_sessions`, but nothing aggregates or recalls across a user's sessions. Sources: `memory.py:320-323`, `memory.py:601-633`.
- No shared or organizational memory across agents; each Agent configures its own store.

### Bridge fidelity

- Tool calls and results are persisted but not replayed into `message_history`, so prior tool context does not re-enter the model on later turns. Only `user_message` / `agent_response` are reconstructed. Source: `memory.py:170-176`.
- `memory_context_limit` (default 6) is a hard truncation; long conversations silently lose earlier turns from the model's view.

### Durability, scaling, and consistency

- `LocalMemory` is per-pod and volatile: no persistence across restarts and no sharing across replicas, so any multi-replica deployment must use Redis.
- Concurrency hazards: `get_or_create_session` has documented race conditions in both `LocalMemory` (no lock) and `RedisMemory` (non-atomic check-and-create). Sources: `memory.py:272`, `memory.py:530`.
- Redis is the only distributed backend; there is no SQL/document/vector store option, and the Redis endpoint is an operator-wide default rather than a per-tenant configurable.
- Session eviction is approximate and unscheduled for the local backend (oldest-10% on create; time-based cleanup exists but is not driven by a scheduler). Sources: `memory.py:358-370`, `memory.py:342-356`.

### Operability and governance

- No first-class multi-tenancy or isolation primitives beyond key prefixes and `user_id` filtering; no per-tenant quotas, encryption-at-rest options, or access control on the always-on `/memory/*` endpoints. Source: `server.py:247-276`.
- Observability is limited to event-level trace metadata and basic counts (`get_memory_stats`); there are no memory-specific metrics for retrieval quality, eviction rates, or store health.
- No schema/versioning/migration story for stored events, and no export/import or backup primitives beyond raw Redis.

## Implications for later stages

The current system is a solid, simple **working memory** layer with a clean backend abstraction and a real distributed option, but it lacks every capability associated with long-term agentic memory: relevance retrieval, summarization/consolidation, cross-session and per-user memory, knowledge structuring, and principled forgetting. The selection criteria in later stages should weigh these gaps against the cost of extending the custom implementation versus adopting a dedicated memory layer, while preserving the properties KAOS already values: a clean pluggable interface, Kubernetes-native declarative configuration, a Pydantic AI data plane, and a viable distributed backend.

## Context manifest

In scope (read for this document):

- `pydantic-ai-server/pais/memory.py` (full module).
- `pydantic-ai-server/pais/server.py` memory integration (`_create_memory`, run lifecycle, `/memory/*` endpoints).
- `pydantic-ai-server/pais/serverutils.py` memory settings (`402-408`).
- `operator/api/v1alpha1/agent_types.go` `MemoryConfig` (`51-80`).
- `operator/controllers/agent_controller.go` memory env wiring (`599-653`).
- `docs/python-framework/memory.md` and `docs/examples/redis-memory.md`.

Out of scope (intentionally excluded): the broader ecosystem survey, tooling catalogue, and target design — these are the subjects of later research documents and must not pre-empt this baseline.
