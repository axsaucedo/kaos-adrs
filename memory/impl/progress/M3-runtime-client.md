# M3 — runtime memory client — progress

Status: complete.

The central memory service from the previous phase is now wired into the agent runtime (`pydantic-ai-server`, package `pais`). The runtime gains a tiered memory contract, a fail-soft service client, server-side scope derivation, a full-fidelity short-term tier bridge, an opt-in recall presentation, and the end-to-end run-path integration that recalls before a run and persists turns after it. The work was done on a branch stacked off the memory-service branch, every task committed individually with a comprehensive functional message, using an additive-first approach so the entire existing runtime suite stays green (327 passed, 10 skipped) alongside the new memory tests.

## Tasks

1. **Tiered memory contract** — `memory.py` gains `ScopeLevel`, `MemoryScope` (with `to_payload`), and `RecalledMemory` (facts + short-term slice + block + `degraded`), plus `recall`/`write`/`forget` on the `Memory` ABC with no-op defaults. Short-term-only backends (Local, Redis, Null) inherit the no-ops, so recall returns empty and write/forget accept without a long-term tier — existing behaviour is unchanged.
2. **Service client backend** — `ServiceMemory` speaks the four service endpoints (`/v1/recall`, `/v1/write`, `/v1/forget`, probes) over a shared `httpx.AsyncClient`. Every call is fail-soft by default: recall degrades to empty on any error, write returns not-accepted (or raises only under `strict`), each wrapped in a `kaos.memory.*` span. The legacy session methods are no-ops so the client composes with the existing run path.
3. **Server-side scope derivation** — `scope_from_deps` builds the request `MemoryScope` purely from the authenticated security context (principal, actor) and the agent's identity plus session id, taking no scope argument from the model or a tool, so a caller can never widen or redirect the scope it is entitled to. The `level` is fixed by agent configuration.
4. **Full-fidelity message-history bridge** — `pydantic_message_to_turns` renders every part of a Pydantic AI message (user, assistant text, tool calls, tool returns, delegation) as faithful text turns, and `reconstruct_message_history` rebuilds a `ModelRequest`/`ModelResponse` history from the short-term tier, prepending the rolling summary as leading context so overflow is represented by the summary rather than truncation.
5. **Recall presentation + opt-in tools** — `memory_tools.py` adds the `RecallPresentation` enum (`block`/`tools`/`both`), the gating helpers, and `MemoryToolset` exposing `save_memory`/`search_memory`. Tool calls derive their scope server-side (the model supplies only content/query), so the tool surface cannot escalate scope. `build_memory_toolset` returns a toolset only when the presentation exposes tools.
6. **Run-path integration** — `_create_memory` selects `ServiceMemory` when `MEMORY_STORE_ENDPOINT` is set (else the short-term-only Redis/Local backends, or Null when disabled). `_prepare_run` derives the scope, recalls long-term facts plus the short-term tier, reconstructs history from the short-term tier when present (falling back to the local event log), and injects the recalled block as leading system context under `block`/`both`. A fail-soft `_write_turns` helper persists every run turn into the short-term tier off the response path, on both the non-streaming and streaming paths. The memory settings (endpoint, scope, recall presentation, failure mode, short-term token budget, rolling summary, agent identity) are added to `AgentServerSettings`, and the opt-in memory toolset is registered when the presentation exposes tools.

## Validation

- `pytest tests/ -v` — 327 passed, 10 skipped (whole runtime suite plus the new contract/client/scope/bridge/presentation tests).
- `make lint` — `black --check` clean, `ty` clean.
- Local runtime↔service smoke: the runtime `ServiceMemory` client driven against a locally running M2 service (local storage mode) confirms writes land, recall replays prior turns into the short-term context and block, a dead service degrades recall to empty and write to not-accepted without raising, and forget clears the scope.

Findings and the deltas to fold into M4 are recorded in [`../learnings/M3-runtime-client.md`](../learnings/M3-runtime-client.md).

## Review-driven redesign (supersedes the initial specifics above)

PR review reshaped several of the choices recorded above; the following supersede the corresponding task descriptions, and the full rationale lives in [`../learnings/runtime-memory-api-and-tooling.md`](../learnings/runtime-memory-api-and-tooling.md):

- **`ServiceMemory` is renamed `RemoteMemory`** — the runtime-side client for the remote KAOS memory service, sitting beside `LocalMemory`/`RedisMemory`/`NullMemory`. It is not a Mem0 client; Mem0 stays embedded in the service.
- **Recall presentation is replaced by an automatic baseline plus additive tools** — enabling memory always recalls-and-injects before a run and flushes-and-extracts after it; `memory.tools: all|read|write` layers `save_memory`/`search_memory` on top. The `RecallPresentation` enum is removed.
- **Private scope fails closed** — `scope_from_deps` raises rather than returning an ambiguously-owned partition; the qualified `kaos://agent/{namespace}/{name}` identity is the owner.
- **The memory surface is carved into a published `kaos-memory` library** — the wire contract, `MemoryServiceClient`, the service, and the Pydantic AI integration (`[pydantic-ai]` extra: message adapters, scope derivation, toolset) now live in one library layered behind dependency extras. `RemoteMemory` becomes a thin adapter over `MemoryServiceClient`, and `pais.memory`/`pais.memory_tools` re-export the library symbols. The runtime depends on `kaos-memory[pydantic-ai]`, resolved from source in dev/CI/image and published to PyPI in the release pipeline. See [ADR 0004](../../adrs/adr_0004_deployment-topology-and-control-plane.md).
- **The recall block carries long-term facts only** — conversational continuity flows solely through reconstructed message history, removing the earlier duplication of the summary and recent window across the block and the replayed history.

The runtime suite is green at 335 passed / 10 skipped with black and ty clean after the redesign; the library's service suite is 67 passed / 4 skipped.
