# ADR 0003 — Parametric instrumentation (layer F): a two-tier channel architecture

- **Status.** Proposed
- **Date.** 2026-08-03
- **Depends on.** [stage 8](../research/8-server-instrumentation-feasibility.md), [stage 11](../research/11-probe-and-latent-monitor-science.md), [stage 12](../research/12-otel-propagation-and-transport.md), [S3–S5 synthesis](../impl/learnings/S3-S5-campaign-synthesis.md), [S7 learnings](../impl/learnings/S7-uncertainty-calibration.md), [S6 learnings](../impl/learnings/S6-first-probe-validation.md), [ADR 0001](./adr_0001_trajectory-schema-and-ingestion.md)

## Context

Layer F instruments the inference server (never the agent — the model virtually never runs in-process) to emit internal signals as trace-correlated spans that A consumes and B exploits. The seven-spike campaign priced every rung of the intrusiveness ladder on real hardware, validated the cheap channel end to end, mapped the GPU zero-touch ceiling precisely, and — critically — established where the expensive tier does *not* yet pay for itself. The architecture must encode those economics, not just the mechanics.

## Decision

### F ships as two tiers plus a cost channel, priced and labeled

| Tier | Mechanism | Cost (measured) | Status |
|---|---|---|---|
| **1 — Uncertainty (always-on default)** | Zero-patch logits processors: vLLM `--logits-processors`, SGLang equivalent, llama.cpp public API | ~-23% decode, CUDA graphs stay on | **Validated, first shippable increment** |
| **2 — Residual/probe (opt-in eager diagnostic)** | SGLang `--forward-hooks` (supported flag, first backend); vLLM version-pinned runner patch; llama.cpp `cb_eval` | ~-66% decode (eager-mode penalty dominates) | Mechanically proven; probe validity restricted (below) |
| **Cost (zero-touch)** | eBPF uprobes (CPU) / CUPTI env-var injection (GPU) | ~5% directional | Validated; the niche for un-modifiable servers |

Signals emit as `xai.parametric.observe` / `xai.cost.observe` INTERNAL spans (ADR 0001's `internal` kind): bounded scalars only, no tensors, no content, affirmative negative controls, one OTLP emitter with thin per-backend config (raw collector / Logfire / Langfuse contract-tested). Every span carries the provenance block (engine+version, graph mode, attribution mode, build id) and `numerics.mode` (`exact` bitwise-CPU vs `tolerance` bf16-GPU).

### Tier 1 content and semantics

Per-step `logit_entropy_raw`, `top2_logit_margin_raw`, `top1_probability_raw`, the tie flag (|margin| < τ ⇒ the sampled token is not evidence of conviction — a measured bf16 hazard), and the derived non-completion/spiral-risk signal (cap-hit + sustained high entropy; S7: 239/239 capped traces were failures). Naming contract from stage 11 is schema-enforced: `*_raw` never presented as confidence; `*.calibrated` fields require a named, versioned, scoped calibrator — and because bf16 batching drift breaks calibration (worst ECE +0.136) while leaving ranking intact (worst AUROC −0.018), **calibrated fields additionally require a declared batch-invariance/numerical-regime contract; raw ranking signals do not**.

### Tier 2 economics and the probe registry

The residual channel exists for probes and deep diagnostics, opt-in and sampled, never always-on (eager-mode cost) and never the prior for B's screening (5.75× uneconomic, S2-P4). Request-row attribution follows the ecosystem's convergent `query_start_loc`/`req_ids` bookkeeping (vLLM-Lens, IBM vLLM-Hook) rather than a bespoke scheme. Probes ship only through the **fail-closed registry**: full provenance (checkpoint hash, layer, position convention, recipe pins, validation distributions, calibrator id, claim text), loaders that reject mismatched checkpoints (S6-demonstrated), and **per-checkpoint measured stats as a shipping precondition** — S6 showed probe position validity inverts between checkpoints (SLT worked where the paper's TBG did not) and that at 0.6B the learned probe does not beat Tier 1 off-distribution. Initial registry: SEP as `prototype (restricted: in-distribution, listed checkpoint)`; refusal direction as `research-only (negative reproduction)`; the mismatch detector is **not** in the shipped taxonomy.

### Engine support policy

SGLang first for Tier 2 (the one supported-path contract); vLLM Tier 2 as a maintained version-pinned patch until its observation-interface RFC lands (the graph-aware observation interface is a measured performance requirement to pursue upstream — the -66% is graph-disable, not hook cost); llama.cpp via `cb_eval` plugin (the Ollama answer is "run the same GGUF under instrumented `llama-server`" — Ollama itself has no extension point); TensorRT-LLM logits-tier only; closed APIs are the documented uncertainty ceiling (top-k logprobs cannot reconstruct entropy — >1 nat measured error). Zero-touch eBPF value recovery is CPU-only (the GPU VRAM ceiling is precisely mapped: UVA reads return misleading zeros — a mandated fail-closed check); GPU exact values require the cooperative path by definition.

## Consequences

- F is additive end to end: no signals, no schema change, no cost to A/B users (S1-proven byte-identity). API-model users lose nothing they could have had.
- The two-tier framing turns the campaign's cost measurements into user-facing defaults: Tier 1 on when you control serving; Tier 2 a deliberate diagnostic decision with a stated throughput bill.
- Honest labeling is structural (schema-enforced), which protects the project's core differentiation — evidence, not vibes.
- Maintaining the vLLM patch until the RFC lands is a real ongoing cost; SGLang-first bounds it.
- The probe tier's current value story is thin at small scale; the registry discipline means it can strengthen with scale without any architecture change.

## Alternatives considered

- **Engine fork with fused probe ops.** Rejected: explicit non-goal; maintenance-hostile; the plugin/patch ladder reached every needed signal.
- **Agent-side instrumentation.** Rejected: the model is not in-process with the agent; stage 8's core finding stands.
- **eBPF-first architecture.** Rejected as default: zero-touch exact values are CPU-only and per-architecture-pinned; it remains the documented niche for appliances the operator cannot modify.
- **Always-on residual channel.** Rejected: -66% eager cost; contradicted by both the throughput measurements and the S2 prior economics.
- **Shipping probes on paper stats.** Rejected: S6's position inversion and transfer failure make per-checkpoint measurement the only defensible bar.
- **API-logprob entropy reconstruction.** Rejected: numerically refuted (>1 nat error); the API tier is honestly labeled approximate.

## Follow-up

- Upstream engagement: vLLM observation-interface RFC; SGLang hook-contract stability test in CI.
- Deferred mechanical item: TP/PP rank cardinality (stage-12 assertion #10) on a short multi-GPU session.
- Scale-escalation rerun of S6/S7 probe and stated-confidence cells on a 7–8B checkpoint — the single highest-value experiment for Tier 2's value story.
