# M7 — Productionisation, hardening, and documentation — learnings

Decisions, deltas, and gotchas from bringing the memory feature to a shippable state. The scope was deliberately calibrated against what earlier phases already shipped (health/readiness probes, replica control, the failure-mode contract, committed memory e2e) so productionisation added only the genuinely missing essentials and recorded explicit defer decisions for the rest.

## External memory stores default to two replicas, guarded by a PodDisruptionBudget

External-mode stores are stateless over a shared Postgres, so they scale horizontally. The operator now defaults an external store to two replicas when the count is not set (local single-writer stores stay at one) and attaches a `PodDisruptionBudget` pinning `minAvailable=1` so voluntary disruptions cannot drain the fleet to zero. The load-bearing detail: the CRD previously carried a static `+kubebuilder:default=1` on `replicas`, which the API server materialises on every object, making the field non-nil and defeating any mode-aware default in the controller. The default marker had to be removed so the controller's mode-aware default (`nil → external 2 / local 1`) actually applies; the `Minimum=1` validation stays. The PDB is reconciled away when a store drops back to a single replica, since a `minAvailable=1` budget over one replica would block all voluntary evictions.

## The failure-mode contract was already complete; the gap was cross-component proof

Soft/strict was already implemented and unit-covered at every layer independently: the service degrades long-term recall to short-term-only and maps a strict write/forget failure to a 500 (`kaos-memory` `test_recall`/`test_write`/`test_summary_forget`); the client degrades recall to empty and re-raises only under `failure_mode="strict"` (`pais` `test_remote_memory`); and the operator holds an agent Ready-but-`MemoryDegraded` when its bound store is missing or warming up, gating only initial creation (`operator` `agent_memory_test`). The one seam not covered was the client-service boundary itself. That gap was closed by wiring the real `MemoryServiceClient` to a real service app over an in-process ASGI transport and asserting the degrade/raise behaviour travels across HTTP. Recall is intentionally always-soft — there is no strict recall — because a recall failure must never take down a turn; only writes and forgets honour strict.

## ty narrows test doubles only at a typed call site

The service-app constructor `MemoryService(longterm=..., short_term=...)` is typed to `LongTermStore`/`ShortTermStore`. Passing a lightweight fake directly to it makes `ty` reject the argument, but routing the same fake through an untyped helper (`_app(longterm, short_term)`) erases the narrowing and type-checks clean — the established pattern the pre-existing `test_recall` fakes already rely on. New tests that construct the service from doubles must go through such a helper rather than calling the constructor inline.

## Durable extraction queue: keep in-process fire-and-forget (decision)

**Decision: keep the in-process fire-and-forget extraction model. Do not build the durable at-least-once queue in this phase.**

The current model is `BackgroundRunner`: a bounded `ThreadPoolExecutor` that runs long-term extraction, consolidation, forgetting, and short-term fold off the response path, with a fixed bounded retry (three attempts) per task, a give-up hook that records a failure counter without crashing the service, and a drain on graceful shutdown. The synchronous append to the short-term window is the durable path and happens on the request; only the long-term extraction of an evicted batch is deferred to the runner.

Rationale:

- The loss window is narrow and bounded. Enqueued-but-unrun tasks drain on graceful shutdown (SIGTERM), so a rolling upgrade or scale-down does not lose extraction. Loss is confined to a hard, ungraceful kill (SIGKILL / node loss) of a replica with in-flight or queued extraction, or to a task that exhausts its retries. The durable short-term tier is unaffected in every case — only the derived long-term facts of the in-flight batch are at risk, and those are re-derivable from subsequent turns over the same scope.
- The cost of the alternative is real. A Postgres `SKIP LOCKED` job table adds a schema, an enqueue-on-write path, a polling worker, visibility-timeout and dead-letter handling, and replica-safe claim semantics — a standing operational surface for a guarantee that alpha does not require and that duplicates durability the short-term tier already provides for the raw turns.
- It is reversible. Extraction is funnelled through a single `scheduler` seam (`Callable[[thunk], None]`), so swapping the in-process runner for a durable-queue-backed scheduler is a localised change when the evidence justifies it.

**Trigger to revisit (build the durable queue when any holds):** memory writes must survive ungraceful replica termination with an at-least-once guarantee on long-term extraction (a hard product/compliance requirement, not best-effort); or measured extraction loss under real autonomous-loop event volume exceeds an acceptable rate; or replicas are routinely terminated ungracefully (spot/preemptible nodes) such that the graceful-drain assumption does not hold. Until then, the fire-and-forget model with bounded retry and graceful drain is the v1 execution model, consistent with adr_0004's explicit deferral.
