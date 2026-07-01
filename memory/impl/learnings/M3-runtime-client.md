# Runtime memory client — findings and plan deltas

## Outcome

The central memory service is now integrated into the agent runtime end to end: the runtime recalls before a run and persists turns after it, through a fail-soft service client, with scope derived server-side and never from the model. The M2 deltas held at the client boundary — the client speaks the four endpoints with a fail-soft default, owner presence is populated per scope level, and a `202`/`degraded` write is treated as success without waiting on extraction. The notes below are the M3-specific learnings to fold into M4 (the operator and the `MemoryStore` CRD that deploys the service and configures the runtime).

## Confirmed in code

- **Recall serves both tiers in one call.** `/v1/recall` returns long-term `facts`, the working slice (`summary` + `recent`), and the ready-to-inject `block` together, so a single recall drives both the injected long-term context and the reconstructed message history. There is no separate working-read endpoint; the runtime does not make two round trips.
- **The hot path never blocks on memory.** Recall degrades to empty on any failure and history falls back to the local event log; writes run off the response path and are fail-soft. A run completes even with the memory service down — the turn is simply not persisted to the long-term working tier. This is the contract M4's readiness gating must respect: an agent with an unreachable memory service still serves, degraded.
- **Scope is server-derived and unspoofable.** Both the run path and the memory tools build the scope via `scope_from_deps` from the security context and agent identity; the model supplies only content/query. The `level` is fixed by configuration. M4's CRD → runtime env mapping should surface only the `level` and identity, never a per-request scope.

## Deltas to fold into M4

1. **[M4] The runtime is configured entirely by `MEMORY_*` env.** The service-client path activates on `MEMORY_STORE_ENDPOINT`; the rest of the behaviour is `MEMORY_SCOPE`, `MEMORY_RECALL_PRESENTATION`, `MEMORY_FAILURE_MODE`, `MEMORY_SHORT_TERM_TOKEN_BUDGET`, `MEMORY_ROLLING_SUMMARY`, and `AGENT_IDENTITY`. The operator's Agent → Deployment mapping should project the `MemoryStore` binding onto these; the endpoint is the service's in-cluster address.
2. **[M4] Agent identity is the private-scope owner.** `scope_from_deps` uses the agent's identity (operator-provided `AGENT_IDENTITY`, else the minted actor) as the `agent_client_id`. M4 should export the agent's stable identity into the runtime so `private` scope is stable across restarts, mirroring how the security identity is already wired.
3. **[M4] Readiness must not hard-block on the memory service.** Because the run path is fail-soft, an agent should still become ready with the memory service unreachable; the memory binding is a soft dependency for serving. Persistence loss is the real cost, so M4 may surface a degraded condition, but it should not gate the agent's own readiness on the store the way a hard dependency would.
4. **[M4] Presentation and scope level are per-agent policy.** `RecallPresentation` (block/tools/both) and `MemoryScope.level` are fixed per agent, not per request. The CRD should express these as agent-level fields; the runtime already refuses to let a tool or model widen them.

## Implementation deviations to carry forward

- **Additive-first, not a clean break.** Rather than replacing the working-only backends, the tiered contract was added as non-breaking `Memory` ABC defaults, so Local/Redis/Null inherit no-op recall/write/forget and the entire existing suite stays green. `ServiceMemory` is the only backend overriding the long-term methods. Consequence: the runtime still has three working-tier backends; the service client is the production long-term path. A later phase can retire Redis/Local if the service becomes mandatory, but nothing in alpha requires that churn now.
- **RedisMemory was kept, not deleted.** The plan floated an alpha clean break dropping Redis. It was retained because it still provides a valid distributed working tier and its tests pass; removing it would delete working code and tests for no functional gain at this stage. `_create_memory` simply prefers `ServiceMemory` when an endpoint is configured.
- **User turns are written once, from the run's new messages.** To avoid double-writing, `_prepare_run` does not write the incoming user turn to the service; instead `_write_turns` persists every turn from the run's `new_messages()` (user echo, assistant, tool/delegation) after the run. The local event log still records the user turn in `_prepare_run` for back-compat, but that is a no-op for the service backend.
- **The block is injected as a leading `SystemPromptPart`, not a user turn.** The recalled long-term block is prepended as `ModelRequest([SystemPromptPart(...)])` so it reads as context rather than a synthetic user message.

## Working-tier fidelity gap to carry forward

- **The working tier stores `(role, text)` turns, so tool-call fidelity is text, not structured.** `pydantic_message_to_turns` renders tool calls/returns/delegation as faithful *text* turns (e.g. `[called tool X(args)]`, `[tool result X: ...]`) and `reconstruct_message_history` rebuilds non-user turns as `TextPart`. A continuing run therefore replays tool history as readable text, not as re-executable structured `ToolCallPart`/`ToolReturnPart`. This is sufficient for context continuity and is the intended tier contract, but any future need for structured replay (e.g. resuming a tool loop mid-flight) would require a richer working-tier payload than text turns. M4/M7 should note this as a known limitation, not a regression.

## Delegation note

- **Cross-agent delegation still forwards working context via the local event log.** `DelegationToolset`/`execute_delegation` were left on the existing session-event path in this phase; wiring delegated runs to the service working tier under a delegated scope is deferred. It is a targeted follow-up (M4 or a later phase) rather than part of the runtime client contract.
