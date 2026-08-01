# Spike S4 — llama.cpp internal signals via the public graph callback

**Validates:** C4 on the local/edge engine tier — that llama.cpp's public `cb_eval` (`ggml_backend_sched_eval_callback`) can deliver named-tensor residual access and per-sequence logit statistics from a custom libllama host, and what the stock-`llama-server` gap costs.
**Research inputs:** [stage 8-support](../research/8-support-engine-introspection-and-ebpf.md) (cb_eval is public and sees *named* ggml tensors; tensors not reliably host-RAM; stock server needs a patch; Ollama exposes nothing), [stage 12](../research/12-otel-propagation-and-transport.md) (llama.cpp = needs-verification for OTel; wrapper insufficient for internals).
**Execution:** Codex sessions phase-by-phase (`codex exec` + `resume`), orchestrator-gated. Scratch under `ethical/xai/tmp/spikes/s4/`; reports `tmp/spikes/s4/PHASE<n>-REPORT.md`; learnings to `kaos-ai-docs/xai/impl/learnings/S4-llamacpp-internal-signal.md`.
**Environment:** fully local (M1 Max) — this is the one spike with zero hardware gap. CPU backend first (deterministic, host-RAM tensors), Metal second (tests the "tensors not in host RAM" claim on unified memory).

## Why S4 matters beyond its own tier

Its **CPU-backend capture harness is the ground-truth oracle for S5** (the eBPF spike): S5's externally-recovered values are validated by exact comparison against cb_eval values read in-process from the same tensors in the same run. S4 also decides whether xai's llama.cpp story is "thin custom host" (acceptable) or "upstream a server flag" (better; the finding feeds an upstream proposal).

## Intrusiveness ladder

| Rung | Mechanism | Emits | Cost / intrusiveness |
|---|---|---|---|
| L0 | `llama-server` API + logprobs | top-k margin (no exact entropy over API) | zero |
| L1 | Custom libllama host, `llama_get_logits_ith` | exact full-vocab entropy, margin, per-sequence | low — public API, ~hundreds of lines of host code |
| L2 | **cb_eval callback, observe named residual tensor, host-side dot product** | probe scalar per decode | medium — public API; per-backend copy semantics; callback-epoch bookkeeping |
| L3 | Insert a GGML dot-product node into the graph (probe computed in-graph) | probe scalar, minimal copy | higher — graph modification, near-patch territory |
| L4 | Patch stock `llama-server` to expose cb_eval as a plugin flag | everything, standard deployment shape | patch — measured in lines; candidate upstream PR |

## Verification loops

1. **HF eager ground truth** (shared with S3): same architecture in `transformers` (fp32/fp16) vs llama.cpp F16 GGUF — same prompts, greedy, per-step entropy/margin/probe-scalar within declared tolerance; quantized GGUF (Q4/Q8) then measured against F16 to quantify what quantization does to probe scalars (a finding stage 11 flagged as unknown).
2. **Callback-epoch accounting:** stage 8-support warns the scheduler may invoke the callback multiple times per `llama_decode`; assert exactly one captured value per (sequence, token, layer) via the ask/observe protocol and decode-epoch counter.
3. **Multi-sequence batch attribution:** `llama_batch` with 4 interleaved sequences; per-sequence scalars must equal their single-sequence runs.
4. **Backend equivalence:** CPU vs Metal captures on identical inputs within tolerance; document the Metal copy/sync cost per read.

## Phases

1. **P1 — Build + L1 logit channel (local).** Pin and build llama.cpp (CPU + Metal); small GGUF (Qwen3-0.6B / Llama-3.2-1B, F16). Custom host: submit batch, read `llama_get_logits_ith`, compute exact entropy/margin per step per sequence, JSON out. Verify vs HF ground truth. Gate: L1 numbers matching within tolerance, CPU backend.
2. **P2 — cb_eval residual capture (the core).** Wire `cb_eval`/`cb_eval_user_data`; enumerate observed tensor names for one decode (the name census is itself a deliverable — which architectures name residual boundaries how); select the residual node; capture and dot-product against pinned `w`; epoch accounting per verification 2. Gate: probe scalar per step matching HF within tolerance, exactly-once per epoch, CPU.
3. **P3 — Batching + Metal.** Multi-sequence attribution (verification 3); then Metal backend: does cb_eval fire, what do reads cost, tolerance vs CPU (verification 4). Also produce the **S5 oracle artifact**: a run harness that logs `(decode_epoch, seq_id, tensor_name, data_ptr, first-8-floats, probe_scalar)` for every captured tensor — S5 diffs its eBPF-recovered values against this file. Gate: attribution correct; Metal verdict; oracle artifact produced and documented.
4. **P4 — Packaging verdict + OTel emission.** Wrap the host as a minimal OpenAI-compatible endpoint (or sidecar to `llama-server` for L0/L1 only — document what's lost); extract inbound `traceparent`, emit the stage-12 canonical span from the host. Then the L4 assessment: patch `llama-server` to accept a `--eval-callback-plugin`-style flag, count the lines, write the would-be upstream proposal. Gate: merged agent+host trace; patch-size and upstreamability report.

**Fail-fast:** if P2 cannot identify a stable residual tensor name for the chosen architecture within the session budget, capture the name census and stop for steering (the fix is likely a different observation node, not more effort). Phases self-limit at ~45 min wall-clock before reporting.
