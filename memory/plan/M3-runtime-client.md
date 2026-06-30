# Runtime data-plane integration — implementation plan

**Branch (KAOS)**: `feat/memory-runtime-client`, stacked off `feat/memory-service` (M2); PR targets `feat/memory-service`.
**Tracking issue**: TBD (do not reference in commits/branches/PR text).

> **Stacking-base note (read first).** Per [`proposed-split.md`](./proposed-split.md): `M2 → {M3, M4} → M5`. M3 makes the agent runtime consume the M2 service through a redesigned `Memory` contract. It and M4 are **siblings** off M2; whichever lands first, the other rebases onto its tip (the only overlap is the env contract the operator sets, finalised in M4). **Before starting, re-read [`../impl/learnings/M2-memory-service.md`](../impl/learnings/M2-memory-service.md)** and the live HTTP surface M2 shipped, and fold deltas in.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message; **no** phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Run python tests locally (`cd pydantic-ai-server && make test`); push the PR and confirm CI green. Alpha: breaking changes OK — the existing `Memory` surface and `MEMORY_*` config are replaced, not preserved.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work) posted as a PR comment (not committed). Copy this plan to `plan/M3-runtime-client.md` and write `impl/progress/M3-*.md` + `impl/learnings/M3-*.md`.

## Problem statement

Make the agent runtime consume the central memory service through a redesigned, tiered `Memory` contract. Under the alpha clean-break stance ([adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md)) the working-only event-deque `Memory` and the `MEMORY_*` configuration are replaced: the runtime gains a **service-client backend** that calls M2 for recall (synchronous, hot path) and write/forget; the message-history bridge is fixed to replay **full-fidelity** history including tool calls, tool returns, and delegation parts; recalled long-term context is injected as a **structured memory block** by default with **opt-in save/load memory tools**; and tenant/agent **scope is derived and injected server-side** from the authenticated request context and the agent's verifiable identity (`AgentDeps`), never from caller- or model-supplied arguments. Hooks wire into the agent run, the autonomous loop, and A2A delegation.

## Current-state grounding (researched)

- `pais/memory.py` (695 lines): `Memory` ABC + `LocalMemory`/`RedisMemory`/`NullMemory`; `build_message_history` (`:142`) replays only `user_message`/`agent_response` and drops tool/delegation events; `store_pydantic_message` (`:178`); overflow truncates.
- `pais/server.py:646-665` `_create_memory(settings)` selects the backend from `MEMORY_*` env; `:692-752` constructs `AgentDeps(memory=…)` per request, calls `build_message_history` before the run and `store_pydantic_message`/`add_event` after, and builds the agent with `deps_type=AgentDeps`.
- `pais/tools.py:55-108` `DelegationToolset` passes `ctx.deps.memory` + `session_id` into `execute_delegation`; `:130-144` loads `get_session_events` and forwards recent user/assistant context to sub-agents — the A2A working-memory hand-off point.
- `pais/a2a.py` hosts the autonomous loop / `TaskManager`; it emits many events ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md)), so writes must stay off the hot path (M2 already runs extraction in the background; the runtime just calls `write` and returns).
- Operator sets `MEMORY_ENABLED|TYPE|REDIS_URL|CONTEXT_LIMIT|MAX_SESSIONS|MAX_SESSION_EVENTS` at `operator/controllers/agent_controller.go:599-633`; M3 redesigns the runtime side of this contract and M4 finalises the operator side (the slim Agent block → new env).
- `AgentDeps` (`pais/serverutils.py`) already carries identity/session context the scope derivation needs (principal, the agent's AIB `client_id`, `session_id`).

## Design plan (how it fits)

Redesign `pais/memory.py` into the tiered contract and add a service-client backend; keep a `NullMemory` for the disabled path. New shape:

- **`Memory` ABC (tiered).** Keep the working-tier methods the runtime needs for message-history assembly, and add `recall(scope, query, …)`, `write(scope, events)`, `forget(scope)`. A working-only/null backend leaves long-term ops no-op. The contract is shaped around M2's HTTP surface, not an abstract algebra ([adr_0002](../adrs/adr_0002_memory-implementation-mem0-and-pydantic-ai-integration.md)).
- **`ServiceMemory(Memory)`.** An `httpx`-backed client of M2: `recall`→`POST /v1/recall`, `write`→`POST /v1/write`, `forget`→`POST /v1/forget`; working-tier reads for message-history come from the service (the working tier lives in the service per [adr_0004](../adrs/adr_0004_deployment-topology-and-control-plane.md), so the runtime no longer holds an in-process deque). Fail-soft: a recall error yields working-only/empty context and a degraded span, never an exception that aborts the turn.
- **Scope derivation.** A `scope_from_deps(AgentDeps)` helper builds the request scope (principal, agent `client_id`, `session_id`, and the per-agent `scope` selector) server-side and attaches it to every service call. The model never supplies scope. (The `scope` enum value comes from the Agent block; M3 plumbs it through, M5 makes enforcement non-optional/fail-closed.)
- **Message-history bridge (full fidelity).** Rewrite `build_message_history` to replay `ToolCallPart`, `ToolReturnPart`, and delegation parts (not just text), sourced from the service's working tier, with overflow represented by the service's rolling summary rather than truncation. Fix `store_pydantic_message` to persist all part types.
- **Recall presentation.** Inject the recalled block into the system context by default; add opt-in `save_memory`/`search_memory` tools (kagent/ADK style) gated by the Agent's `recall.presentation: block|tools|both`. Recalled facts are never injected as fabricated prior turns.
- **Config.** Replace `_create_memory` + `MEMORY_*` with the new env contract (`MEMORY_STORE_ENDPOINT`, `MEMORY_SCOPE`, `MEMORY_SHORT_TERM_TOKEN_BUDGET`, `MEMORY_ROLLING_SUMMARY`, `MEMORY_RECALL_PRESENTATION`, `MEMORY_FAILURE_MODE`, `MEMORY_ENABLED`), consumed from the slim Agent block M4 sets. Per-agent budget/summary/presentation are passed to the service as request policy.
- **OTel.** Spans at the `Memory` method boundary (`kaos.memory.recall|write|forget`) with the service's engine sub-spans nested via trace propagation, following the existing `kaos.*` convention.

## Numbered TODOs

1. **Tiered `Memory` ABC + Null backend.** Redesign the ABC in `pais/memory.py`: working-tier methods used by the bridge + `recall`/`write`/`forget`; remove the in-process `deque` ownership from the contract; keep `NullMemory` no-op for the disabled path. Delete `LocalMemory`/`RedisMemory` (alpha clean break) or reduce `Local` to a thin test double. **Validate**: unit tests for the ABC shape and Null no-op; `cd pydantic-ai-server && pytest tests/ -k memory -v && make lint`.

2. **`ServiceMemory` client.** Implement the `httpx` client of M2 with fail-soft recall, `write`, `forget`, and working-tier reads; configurable endpoint/timeout; per-request policy (budget, summary, presentation, failureMode). **Validate**: unit tests against a stub M2 server (or `respx`) — recall/write/forget call the right routes, a recall error degrades to working-only, timeouts fail soft; `pytest tests/test_service_memory.py -v`.

3. **Scope derivation from `AgentDeps`.** Add `scope_from_deps` building the server-side scope (principal, agent `client_id`, `session_id`, selector) and attach it to every service call; ensure no code path reads scope from model/tool arguments. **Validate**: unit tests — scope built from deps, model-supplied scope ignored; `pytest tests/test_scope_injection.py -v`.

4. **Full-fidelity message-history bridge.** Rewrite `build_message_history`/`store_pydantic_message` to round-trip `ToolCallPart`/`ToolReturnPart`/delegation parts from the service working tier, with rolling-summary overflow. **Validate**: unit tests — a continuing run replays its own prior tool calls (the [adr_0003](../adrs/adr_0003_memory-interface-and-runtime-data-plane.md) example), overflow is summarized not truncated; `pytest tests/test_message_history.py -v`.

5. **Recall presentation (block + opt-in tools).** Inject the recalled block by default; add `save_memory`/`search_memory` tools gated by `recall.presentation`. Wire into the agent build alongside existing toolsets. **Validate**: unit tests — block injected by default, tools registered only when enabled, both when `both`; `pytest tests/test_recall_presentation.py -v`.

6. **Wire run + autonomous loop + delegation; replace config.** Replace `_create_memory`/`MEMORY_*` with the new env contract and construct `ServiceMemory`; call `recall` before the run and `write` after (and within the autonomous loop in `pais/a2a.py`); update `DelegationToolset` (`pais/tools.py`) so the A2A hand-off uses the service working tier and carries the delegated scope prefix context (the inheritance policy itself is M5). **Validate**: unit/integration tests — a run recalls then writes via the service, the autonomous loop writes without blocking, delegation forwards working context from the service; `pytest tests/ -v && make lint`.

7. **End-to-end runtime↔service check + PR.** Run the agent runtime against a locally-running M2 service (both started locally; capture to `./tmp/null`) and confirm: recall injects prior-session facts, writes land in the background, a continuing run replays tool calls, and a recall failure degrades the turn rather than aborting it. **Validate**: a scripted local check green; `make test && make lint`. Write `impl/progress/M3-*.md` + `impl/learnings/M3-*.md`, copy this plan, push `feat/memory-runtime-client`, open the stacked PR into `feat/memory-service`, confirm CI green, write the gitignored `REPORT.md` (M0–M3) and post it as a PR comment.

## Validation per task

- Per-TODO: `cd pydantic-ai-server && python -m pytest tests/ -v && make lint`. The runtime suite runs in KAOS CI (`python-tests`).
- The full runtime↔service integration is local/e2e (needs M2 running) and documented in `REPORT.md`; promote a minimal version into e2e in M7.

## Commit / PR strategy

- `feat/memory-runtime-client` stacked off `feat/memory-service`; one comprehensive commit per TODO; PR into `feat/memory-service`; Copilot co-author trailer; CI green. `REPORT.md` gitignored, posted as a PR comment.
- M3 and M4 are siblings off M2; coordinate the env contract (the `MEMORY_*` keys M3 reads and M4 sets) so whichever rebases second matches the other.

## Out of scope (later phases)

The operator deploying the service and setting the new env from the slim Agent block (M4 — M3 defines the env contract it consumes); non-optional fail-closed scope enforcement, A2A prefix-inheritance policy, and erasure semantics (M5 — M3 only plumbs scope through and forwards delegated context); install integration (M6); HA, metrics, durable queue, e2e promotion, docs (M7).
