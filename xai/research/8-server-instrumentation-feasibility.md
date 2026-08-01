# Stage 8 — Server-side instrumentation feasibility: eBPF, engines, and transport

> Authored from this session's design analysis and a web-verification pass (August 2026), not migrated. Part of the [research plan](./0-research-plan.md); components **C4 — Parametric instrumentation** and **C5 — Signal transport & correlation**. Reads alongside [stage 7](./7-parametric-enriched-traces.md) (the concept these signals feed). This is a **feasibility** document: the design half (where to instrument, plugin-not-fork, monitor-vs-deep) is synthesis; the factual half (engine internals, eBPF limits, engine status) is an external substrate to be independently checked by the deep-research prompt [`deep-research-prompts/8-support-engine-introspection-and-ebpf.md`](./deep-research-prompts/8-support-engine-introspection-and-ebpf.md) and proven by spikes **S3** (vLLM/SGLang), **S4** (llama.cpp/Ollama), and **S5** (eBPF cost span). Treat the tier map as a hypothesis until those return.

> **Post-research correction (2026-08-01, from [stage 12](./12-otel-propagation-and-transport.md)):** the transport survey confirms the architecture and the vLLM/SGLang/Triton tiers, but **downgrades the llama.cpp/Ollama tier**: neither documents native W3C trace-context continuation or OTel export at all, so that row is "needs verification / source-integration required", weaker than the "medium — callback-level" grade below. SGLang also needs version pinning (a 2026 model-gateway release injected outbound context without extracting inbound, creating new trace roots). The corrected per-server statuses in stage 12 supersede the tier map below wherever they differ; spike S3 adjudicates any conflict with the pending stage-8-support survey.

## The architectural correction that reframes everything

An earlier sketch assumed instrumentation happens *inside the agent* by wrapping the model object — the in-process Hugging Face transformers case. That is the notebook/dev reality; in production it is virtually never true. The agent (LangGraph/CrewAI/custom loop) is one service; the model sits behind an **inference server** (vLLM, SGLang, TGI, Ollama) reached over an OpenAI-compatible HTTP endpoint. The agent sees tokens in, tokens out — maybe top-k logprobs. Activations, residual stream, attention, and any probe-able internal state **exist only inside the server process.** The agent cannot see them.

So the instrumentation boundary is the **inference server**, not the agent, and the two processes' evidence must be correlated by OpenTelemetry / W3C Trace Context propagation: the agent's request carries a `traceparent` header, and the server attaches its internal-state readings as a child span under the same trace. xai then loads the merged trace, where the parametric channel is populated for whichever steps were served by an instrumented server. ([Stage 12](./deep-research-prompts/12-otel-propagation-transport.md) researches whether each server actually continues an incoming trace context; S3 confirms it against running code.)

This reframing is what makes F defensible rather than a me-too: it lands the parametric layer in a spot the incumbents cannot occupy — see the last section.

## Two meanings of `instrument_`, kept separate

The `instrument_<thing>` surface is really two jobs with very different difficulty:

```
[instrumented vLLM/SGLang server]  ──emits──►  xai.parametric.* OTel spans
      (instrument_vllm — HARD)                        │
                                              same trace context as agent
                                                       │
                          ┌────────────────────────────┼──────────────────────────┐
                          ▼                             ▼                           ▼
                   instrument_otel              instrument_logfire         instrument_langfuse
                   (raw OTLP — REAL)            (thin flavour)             (thin flavour)
                                                       │
                                                       ▼
                                             xa.load(...) → A diagnostics / B replay
```

- **`instrument_<server>` — produce the signals.** `instrument_vllm`, `instrument_sglang`, `instrument_ollama`. The hard, architecture-specific engineering: get inside the forward pass, compute probe/uncertainty/attention signals, map them back to the right request. Where the value and the cost both live.
- **`instrument_<otel-backend>` — route the signals.** `instrument_otel`, `instrument_logfire`, `instrument_langfuse`. Mostly thin: Logfire and Langfuse both ingest OTLP, so if the server emits GenAI-semantic-convention spans with an `xai.parametric.*` attribute namespace, supporting them is largely exporter/span-shape configuration. **OTel is the real target; the others are convenience wrappers.** Build one OTLP emitter and thin per-backend adapters, not three pipelines.

## eBPF: right tool for the cost channel, wrong tool for the interpretability channel

The instinct to avoid instrumentation with eBPF is worth taking seriously, and the answer is a layer mismatch, not immaturity.

**eBPF observes machinery; probes need meaning.** eBPF attaches to syscalls, user-space functions (uprobes), network, and — the frontier — GPU kernels. The [bpftime](https://eunomia.dev/bpftime/documents/gpu/) project compiles eBPF to PTX and injects it into CUDA binaries at runtime, so you *can* now observe GPU-internal execution (block/thread indices, memory-access patterns, per-kernel timing) without touching the server, closing the ["GPU observability gap"](https://eunomia.dev/blog/2025/10/14/the-gpu-observability-gap-why-we-need-ebpf-on-gpu-devices/). But what it surfaces is *execution behavior*, not *labeled tensors*: a `cudaLaunchKernel` uprobe tells you a kernel launched, [not what happens inside the GPU](https://eunomia.dev/tutorials/47-cuda-events/), and even in-kernel probes see thread indices and raw memory addresses, not "this buffer is the layer-12 residual stream for request X's last token."

That last clause is the crux. A probe reading needs a *semantically identified* activation — a specific layer, token position, and request. That identity is a **model-graph concept** that exists in the framework (PyTorch's module tree), not in the kernel/PTX world, where it is float32 bytes at a VRAM address inside a fused batch of interleaved requests. Recovering it via eBPF means reverse-engineering each architecture's memory layout from raw addresses, per model, per version — vastly more brittle than the framework hook that gets the same tensor for free. So:

- **eBPF / bpftime / CUPTI → the cost channel.** Per-request GPU time, memory pressure, kernel-launch and batching behavior, correlated to trace spans. Genuinely zero-touch, and it feeds layer B's `explain_cost`. Worth having (spike **S5**).
- **Framework hooks → the interpretability channel.** Uncertainty, probes, attention. Unavoidably needs the model graph.

**But "needs the model graph" is not "needs a fork."** For any PyTorch-based engine the signal comes from `torch.nn.Module.register_forward_hook`, attachable from a **load-time plugin** — additive, external, no vendor patch. A linear probe is then one matmul on a tensor already in hand. So `instrument_vllm` is realistically "ship a plugin that registers forward hooks," not "maintain a vLLM fork" — provided continuous batching lets you attribute each hook fire to the right request, which is exactly what spike **S3** tests.

## The engine/server landscape

The key distinction is **server vs engine**: a *server* wraps an *engine* with an API, scheduling, and multi-model routing; the engine does the kernel execution. [NVIDIA Triton](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/backend/README.html) is the clarifying example — it is backend-agnostic, running vLLM (via its Python backend), TensorRT-LLM (via a C++ executor backend), or PyTorch/ONNX/TensorFlow, all in one server process. Triton is a *server*; the engine is whichever backend is configured. So "does Triton just use vLLM" — no; vLLM is one of its backends.

Engines to instrument, with 2026 status and interpretability-hook difficulty:

| Engine | Runtime | Where it's used | Hookability for probes |
|---|---|---|---|
| **vLLM** | PyTorch | The OSS default; also a Triton backend, under SageMaker LMI, BentoML, Ray Serve, KServe, most hosted platforms | **Easy** — forward-hook plugin |
| **SGLang** | PyTorch | Now the throughput leader for shared-prefix / RAG / multi-turn workloads ([~29% over vLLM on H100 for Llama 3.1 8B](https://www.yottalabs.ai/post/best-llm-inference-engines-in-2026-vllm-tensorrt-llm-tgi-and-sglang-compared)); rising for agentic loads | **Easy** — forward-hook plugin |
| **TensorRT-LLM** | Compiled C++/TRT engines | [Production NVIDIA standard](https://gigagpu.com/best-llm-inference-engines-2026/) at high volume; served via Triton or `trtllm-serve` | **Hard** — no runtime module graph; activations need an engine rebuild with debug tensors marked as outputs |
| **llama.cpp** | C++/GGML | Engine under **Ollama**, **LM Studio**, LocalAI, `llama-server`; CPU/edge/local | **Medium** — no PyTorch hooks; ggml callback patches; tensors are in host RAM, so eBPF is less hopeless here than on GPU |
| **MLX** | Apple/Metal (Python) | Mac local | **Easy-ish** — Python-level, small segment |
| **TGI** | Rust + multi-backend | **Dead as a target** — [entered maintenance Dec 2025; EOL-directed to vLLM/SGLang/llama.cpp/MLX in March 2026](https://www.huggingface.co/blog/tgi-multi-backend) | Skip |

Servers / control planes (where spans should surface, not usually where you hook): **Triton** (backend-agnostic), **Ollama** & **LM Studio** (llama.cpp fronts), **Ray Serve / KServe / Seldon / BentoML** (K8s runtimes deploying the engines above), and pure proxies like **LiteLLM** (routing only — nothing to hook).

**Targeting that falls out of this:** the addressable majority is PyTorch, and **one forward-hook plugin pattern covers vLLM and SGLang both** — and by extension vLLM-under-Triton, vLLM-under-SageMaker/BentoML/Ray, since you hook the engine, not the server. That is a large, growing, self-hosted slice from one piece of engineering. TensorRT-LLM is the painful gap and also the biggest *production* NVIDIA footprint, so it gets **logit-derived signals only** (entropy/logprob margin need no activations) until someone does the debug-tensor rebuild. llama.cpp/Ollama is callback-level (spike **S4**).

## The vLLM limitation, explained

vLLM is built for **throughput, not introspection**, which creates two concrete obstacles that define the monitor-vs-deep split:

1. **It does not hand you intermediate activations.** In HF transformers, `output_hidden_states=True` returns the residual stream at every layer. vLLM runs the forward pass through fused, optimized kernels and returns only final logits (plus optional top-k logprobs). There is no public hook for layer-N activations — you register a forward hook via a load-time plugin on the torch modules (feasible) but you are working against a stack designed to not materialize those tensors.
2. **Continuous batching mixes requests.** vLLM packs tokens from many concurrent requests into the same forward pass (paged attention + continuous batching). So "the activation for request X at step T" is not a clean tensor slice — you must map from vLLM's internal sequence/block bookkeeping back to a specific request to attribute a probe reading correctly. That mapping is the fiddly part, and it is the specific risk spike **S3** exists to retire.

The practical consequence:

- **Monitor mode — production-viable on vLLM.** Logit-uncertainty needs *nothing new* (logits are already there). A linear probe is one matmul plus a stored vector — cheap enough to run inline per step, tiny memory, scalar output. Deployable in a throughput server.
- **Deep mode — dev/lab, HF transformers.** Full activation capture, SAE features, attention maps, gradient attribution. Heavy, slow, memory-hungry — a single-request debugging configuration.

Ollama is *more* closed than vLLM, not less — a llama.cpp convenience wrapper with a minimal introspection surface — so there you work at the llama.cpp/ggml layer or accept only logit/logprob-derived signals. Net: the depth of the parametric channel **varies by server**, and xai should declare per-server what it can emit rather than promise uniform coverage.

## The one honest operational cost

Everything in the A→B arc is "pip install, point at your existing traces." F is not: it asks the user to run an **instrumented build of their inference server**. That is a heavier commitment, and it applies only to the open-weights self-hosted segment (API-model users get A/B only, which is fine — F is additive). But that segment — teams self-hosting for compliance or cost — is precisely the audience that already has audit needs, and for them there is no competitor.

## Why the intersection is structurally defensible

Nobody else can stand here: observability vendors **never touch inference** (they consume spans emitted by the agent SDK; they cannot emit activations); interpretability labs **never touch agents** (in-process single-model analysis, no trajectories, no tools, no OTel correlation); eval frameworks touch neither. "Agent-level explanations backed by both a behavioral experiment and the model's internal state" is a claim only something sitting at the server-instrumentation × trajectory-analysis intersection can make. Vendors can copy the diagnostics and labs can out-research the probes, but the **corroboration loop** — [stage 7](./7-parametric-enriched-traces.md)'s synergy 3 — is the thing that requires being in both places at once.

## Feasibility gates (what remains unproven)

- **S3 (make-or-break):** load-time forward-hook plugin on vLLM/SGLang emitting a correct per-request probe scalar + logit entropy into a `traceparent`-correlated OTel span, under continuous batching, with no engine fork.
- **S4:** the ceiling of what the llama.cpp/Ollama (C++/GGML) tier can expose — at minimum logit-uncertainty.
- **S5:** an eBPF/CUPTI cost span attributable to a specific request, zero-touch, feeding `explain_cost`.
- **Deep-research prompt 8-support:** independent verification of the engine hookability matrix, the eBPF/bpftime capability boundary, and current engine status, with primary sources — since the tier map above is a web-informed hypothesis, not yet proven against each stack.

## Sources

[Triton backends](https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/backend/README.html) · [TGI multi-backend / maintenance](https://www.huggingface.co/blog/tgi-multi-backend) · [2026 engine comparison](https://www.yottalabs.ai/post/best-llm-inference-engines-in-2026-vllm-tensorrt-llm-tgi-and-sglang-compared) · [2026 engines overview](https://gigagpu.com/best-llm-inference-engines-2026/) · [eBPF GPU observability gap](https://eunomia.dev/blog/2025/10/14/the-gpu-observability-gap-why-we-need-ebpf-on-gpu-devices/) · [bpftime GPU](https://eunomia.dev/bpftime/documents/gpu/) · [CUDA event tracing](https://eunomia.dev/tutorials/47-cuda-events/)
