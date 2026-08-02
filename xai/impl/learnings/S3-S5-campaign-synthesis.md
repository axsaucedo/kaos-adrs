# S3–S5 campaign synthesis — what the parametric-instrumentation validation proved

This document is the cross-spike synthesis of the S3, S4, and S5 validation campaign (executed 2026-08-01, local CPU tiers plus a one-day CUDA tier on a disposable NVIDIA L4). It consolidates the conclusions that are currently distributed across the three per-spike learnings and the research-plan campaign block into a single read for the F ADR. The per-spike detail, exact pins, and evidence remain in [S3](./S3-parametric-span.md), [S4](./S4-llamacpp-internal-signal.md), and [S5](./S5-ebpf-semantic-recovery.md); the reproducible infrastructure is in [the GPU cluster setup record](../gpu-validation-cluster-setup.md).

## The one-line result

Every internal signal layer F needs can be extracted, on both CPU and GPU, at a level that scales with how much of the serving stack the operator controls — and the one hard boundary (exact activation values on GPU without cooperation) is now mapped precisely, with mechanism, rather than left as an assumption.

## The three signal channels and where each lands

Layer F carries three distinct channels. They have different costs, different intrusiveness, and different CPU-vs-GPU stories, and conflating them is the main modelling error to avoid.

| Channel | CPU | GPU | Lever it requires |
|---|---|---|---|
| **Uncertainty** (full-vocabulary entropy, top-two margin, top-one probability) | exact | exact | Zero-patch. vLLM `--logits-processors`, llama.cpp public API. Always-on. |
| **Residual / probe scalar** (a named activation reduced to a bounded scalar) | exact, bitwise | exact, tolerance-based | Cooperative. SGLang `--forward-hooks` (zero patch), vLLM runner patch, llama.cpp `cb_eval`. Opt-in eager diagnostic on GPU. |
| **Cost** (per-request GPU/CPU time) | zero-touch | zero-touch | eBPF uprobes (CPU) / CUPTI env-var injection (GPU). No server change. |

The uncertainty channel is the cheap, shippable-now baseline; it was numerically shown that truncated top-k API logprobs cannot reconstruct entropy (>1 nat error), so this must be produced server-side, which is exactly what the zero-patch processor does. The residual channel is the differentiator but carries a real cost on GPU (below). The cost channel is universally zero-touch but measures different things on CPU and GPU and must not be reused naively across them.

## The intrusiveness ladder, now priced on real hardware

From least to most intrusive, with the empirical cost attached:

1. **API logprobs** — free, no control required, but approximate uncertainty only; cannot reconstruct exact entropy. The ceiling for closed-provider models.
2. **Zero-patch server logits** — exact uncertainty, keeps production CUDA graphs on, measured **~-23% decode throughput** on vLLM GPU. The always-on channel where F controls serving.
3. **Cooperative residual hook/patch** — exact named-activation scalar. SGLang via the supported `--forward-hooks` flag with no engine patch; vLLM via a version-sensitive runner patch. Requires eager execution, measured **~-66% decode throughput** (SGLang -65.8%, vLLM -66.9%), of which the hook itself is only -8.5% to -10.3% — the eager-mode penalty dominates. Therefore an opt-in, bounded, sampled diagnostic, not always-on.
4. **eBPF / CUPTI zero-touch** — cost on both CPU and GPU with no server change; exact residual values on **CPU only** (device-memory boundary on GPU). The specialist niche for appliances the operator cannot modify.

The decision rule that falls out: **cooperative in-process instrumentation is the default when you control serving; zero-touch eBPF is the niche for when you cannot touch the server; uncertainty is the universal baseline; API-only is the uncertainty ceiling.** The level is set by *control of the serving process*, not by CPU-vs-GPU.

## The capability matrix by operator posture

- **Operator controls the server** (self-hosted vLLM / SGLang / llama.cpp): full stack — exact uncertainty always-on, exact residual/probe via cooperative plugin, cost via eBPF/CUPTI. Proven on GPU, the environment that matters in production.
- **Operator can observe but not modify** (someone else's container, a fixed appliance): cost zero-touch always; uncertainty via API (approximate); exact residual only on **CPU llama.cpp with a debug-matched build**, and **not at all on GPU**.
- **API-only model** (closed provider): uncertainty ceiling, approximate, from logprobs. No residual, no cost. Layers A and B remain fully available; F is simply absent — which is by design, F is additive.

## Two structural findings that reshape the F design

**1. Python forward hooks and production CUDA graphs are incompatible — on both engines, by different mechanisms.** SGLang registers hooks after graph capture, so they are absent from captured graphs and fire only on eager forwards. vLLM registers before capture, but its compiled and full/piecewise graph paths still suppress the Python side effect. In both, a graph-replayed decode step produces zero callbacks, and a missing callback must never be read as a zero-valued observation. Consequently exact residual observation currently requires eager mode, which is the source of the ~-66% cost. This makes a graph-aware engine-supported observation interface a measured performance requirement to pursue upstream, not an API nicety — and the ecosystem is already converging on cooperative-plugin extraction (vLLM-Lens from UK AISI, IBM vLLM-Hook), which independently reproduced our request-attribution bookkeeping (`query_start_loc` / `req_ids`).

**2. GPU numerics are tolerance-based, not bitwise.** The CPU tiers achieved bitwise-exact and even 0.0-delta concurrency invariance. GPU bf16 continuous batching does not: residual scalars drift up to ~0.05 and entropy up to ~0.106 nats concurrent-vs-sequential, and a genuine top-two-logit tie flipped one output token relative to fp32. Every acceptance criterion for the remaining internal-signal spikes (S6, S7) must therefore be tolerance-based and token-aware, and the trajectory schema (S1) must carry an epistemic numerics flag distinguishing `exact` from `tolerance` scalars so a consumer can tell a bitwise-CPU reading from a bf16-GPU one.

## The GPU semantic-recovery ceiling, stated precisely

Zero-touch eBPF recovers host-resident graph *structure* under CUDA (the T2 census still enumerates every node and finds the target tensor), but **cannot recover exact activation *values* on GPU**. The mechanism: the tensor data lives in VRAM behind a CUDA unified-virtual-address mapping that appears as a `---p` process VMA; a `/proc/<pid>/mem` read of it *succeeds and returns zeros* rather than erroring — a false-evidence hazard now mandated as a fail-closed check. No host staging copy exists for the target tensor, and CUDA IPC requires the owning process to export a handle. The only way to read VRAM on the host is a device-to-host copy issued by code inside the owning CUDA context — which is cooperation by definition. Exact GPU values therefore route to the cooperative S4 `cb_eval` path; a minimal engine assist (an env-selected target-tensor callback that copies one row at the safe boundary) is the lightest cooperative form. Untested and left open: an in-process CUDA interposer (`LD_PRELOAD` wrapping CUDA calls) and debugger-attach (`cuda-gdb`) — genuine no-source-change value paths, but with unproven reliability, ownership, and lifetime semantics. Given the ecosystem convergence on cooperative plugins, following that design is judged a better bet than reverse-engineering VRAM.

## What is proven, what is deferred

**Proven on real hardware, safe to claim:** exact server-side uncertainty on both engines zero-patch; exact residual probes on both CUDA engines (SGLang without a patch); zero-touch cost on CPU and GPU; the full agent-`traceparent` → server span → canonical `xai.parametric.observe` / `xai.cost.observe` pipeline with bounded scalars, affirmative negative controls, and zero content/tensor leakage; one OTLP emitter with thin per-backend adapters; and the precisely-mapped GPU value-recovery ceiling.

**Not yet claimable:** that any *specific* learned probe (semantic-entropy, refusal-direction) is valid and calibrated — that is S6/S7, which gate the F *probe* channel (not the instrumentation). And TP/PP multi-rank cardinality (stage-12 assertion #10), which needs a short multi-GPU session; a single L4 could not test it.

## Net effect on the F ADR

The F ADR is fully unblocked on feasibility, transport, and cost. Its remaining open sub-decisions are narrow: per-token vs per-request span cardinality; SGLang-first vs a maintained vLLM patch as the first residual backend; the exact provenance schema; and the loss-tolerant exporter contract. The probe *channel* within F still waits on S6/S7. Nothing F structurally needs was found to be missing.
