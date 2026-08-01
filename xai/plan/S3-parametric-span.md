# Spike S3 — Parametric span from a throughput inference server

**Validates:** C4+C5 — the make-or-break assumption for layer F: that a supported (or near-supported) extension point on a real inference server can emit a per-request probe scalar + logit statistics as a `traceparent`-correlated OTel span, without forking the engine.
**Research inputs:** [stage 8](../research/8-server-instrumentation-feasibility.md), [stage 8-support](../research/8-support-engine-introspection-and-ebpf.md) (SGLang-first correction), [stage 12](../research/12-otel-propagation-and-transport.md) (12-assertion acceptance matrix, canonical span shape), [stage 11](../research/11-probe-and-latent-monitor-science.md) (signal naming: raw telemetry, never "confidence").
**Execution:** Codex sessions orchestrated phase-by-phase (one `codex exec` per phase, `resume` carries context; the orchestrator reviews each phase gate before advancing). Scratch under `ethical/xai/tmp/spikes/s3/`; per-phase report at `tmp/spikes/s3/PHASE<n>-REPORT.md`; final learnings to `kaos-ai-docs/xai/impl/learnings/S3-parametric-span.md`.

## Environment reality (M1 Max, 32 GB, no NVIDIA GPU)

SGLang's `--forward-hooks` — the one *officially supported* activation contract — requires CUDA, so it cannot run locally. The spike therefore splits into a **local tier** that proves every mechanic that does not require CUDA, and a **GPU tier** that is fully specified and scripted here but executes only when a CUDA box is available (cloud burst or cluster). This is not a fallback compromise: the local tier answers most of the 12-assertion matrix (trace continuation, plugin loading, request attribution under continuous batching, span lifecycle, export isolation, backend contract tests), because vLLM's CPU backend runs the same scheduler, batching, and OTel code paths as CUDA — what it cannot answer is CUDA-graph behavior, TP/PP cardinality, and real throughput overhead.

## Intrusiveness ladder (what each rung buys, at what cost)

| Rung | Mechanism | Emits | Intrusiveness / cost | Verdict source |
|---|---|---|---|---|
| L0 | OpenAI API logprobs (top-k) | top-token logprob, top-k margin | zero — any server, but NO exact entropy (truncated top-k) | stage 8-support |
| L1 | Server-native OTel + logits access (custom logits processor where supported) | exact entropy, margin, per-request | low — supported contract on TRT-LLM; needs verification on vLLM serve path | stage 8-support |
| L2 | **Forward hook on residual stream** (SGLang `--forward-hooks`; vLLM = patch until Observation RFC lands) | probe scalar per step | medium — the layer-F target; request-row mapping is the hard part | stage 8-support |
| L3 | Hidden-state extraction (vLLM 0.18 KV-connector path) | full selected-layer vectors | high — deep mode, ~268 MB/4 layers/8k tokens; not a monitor primitive | stage 8-support |
| L4 | Engine fork with inline fused probe op | everything, minimal overhead | maximal — explicitly out of scope (non-goal) | — |

The spike measures the L1→L2 boundary precisely: what each rung costs and what breaks it.

## Verification loops (source of truth)

1. **Numerical ground truth:** an HF `transformers` eager harness (same checkpoint, fp16/fp32, greedy, fixed seed) computes per-step entropy, top-2 margin, and the probe scalar (`w·h` at the chosen layer, fixed released probe vector or random-but-pinned `w`). Every server-extracted value must match within a declared tolerance (fp16 accumulation differences are expected — the tolerance itself is a finding).
2. **Batching self-consistency:** the same prompt run (a) alone and (b) concurrently with 3–7 decoy prompts must yield identical scalars (bit-tolerance) and correct span parentage. This is the strongest cheap test of request-row attribution — no ground-truth harness needed.
3. **Trace integrity:** agent-side client span and server-side `xai.parametric.observe` span share a trace ID; parentage per stage 12's hierarchy; asserted programmatically from exported OTLP, not eyeballed in a UI.
4. **Contract tests:** exported spans replayed into a raw collector, Logfire, and Langfuse; assert `xai.parametric.*` attributes survive per backend.

## Phases (each ends at a gate; orchestrator reviews the report before the next)

1. **P1 — Reference harness + trace skeleton (local).** Build the HF eager ground-truth harness (small model: Qwen3-0.6B or Llama-3.2-1B) emitting per-step entropy/margin/probe-scalar to JSON. Build the minimal agent client: OpenAI SDK + `propagate.inject`, OTLP export to a local collector container. Gate: ground-truth JSON for 3 pinned prompts; agent client emits a valid `traceparent`, captured and asserted.
2. **P2 — vLLM CPU: trace continuation + logit channel (local).** vLLM (pinned release) in an aarch64 Linux container, CPU backend. Verify inbound `traceparent` continuation into vLLM's OTel spans; extract logprobs via API (L0) and attempt exact entropy via logits-processor path (L1) on the serve path. Compare against P1 ground truth. Gate: one merged trace (agent + server spans, shared trace ID) + entropy match or a documented L1 blocker on the serve path.
3. **P3 — vLLM CPU: the L2 probe attempt (local, the hard one).** Attempt the residual probe scalar via the least-intrusive workable route, in order: (a) general-plugin entry point + `named_modules()` hook (expected to fail per stage 8-support — document exactly *why*: what the plugin cannot see); (b) minimal targeted patch (count the lines — "how small is the patch" is the finding); (c) evaluate whether the Observation Plugin RFC's proposed interface would suffice (write the gap analysis). Then the batching self-consistency loop (verification 2) under concurrent requests. Gate: probe scalar matching ground truth in single-request mode + the concurrency attribution verdict + patch-size report.
4. **P4 — Span shape + backend contract tests (local).** Emit the full stage-12 canonical `xai.parametric.observe` span (bounded attributes, affirmative negative controls); streaming/cancellation/timeout lifecycle tests (exactly-once); export-failure isolation (kill the collector mid-generation, assert generation unaffected); replay to collector/Logfire/Langfuse and assert attribute preservation. Gate: the local subset of stage 12's matrix — each assertion pass/fail in a table.
5. **P5 — SGLang GPU tier (deferred until CUDA box).** Scripted and containerized in P1–P4 style but executed on a CUDA host: `--forward-hooks` with a real hook factory; request-identity mapping via `req_pool_indices` side table; CUDA-graph on/off behavior; TP=2 cardinality; throughput overhead measurement (tokens/s with hook on/off). Everything is prepared as runnable scripts + a written runbook so the GPU session is hours, not days.

**Fail-fast:** if P3(a) and P3(b) both fail to produce a correct scalar under batching within the session budget, stop and report — that is a finding that reshapes the F ADR (it means layer F waits on the vLLM RFC or leads with SGLang-only). Each phase self-limits at ~45 min wall-clock before reporting status for steering.
