# Stage 8-support — Engine introspection & eBPF feasibility (deep-research verification)

> Deep-research output (ChatGPT deep research, imported 2026-08-01) produced from [`deep-research-prompts/8-support-engine-introspection-and-ebpf.md`](./deep-research-prompts/8-support-engine-introspection-and-ebpf.md), independently verifying the factual substrate of [stage 8](./8-server-instrumentation-feasibility.md). Part of the [research plan](./0-research-plan.md). Citations appear as opaque `citeturn...` tokens from the research tool; load-bearing version-specific claims (SGLang `--forward-hooks`, vLLM Observation Plugin RFC status, TensorRT-LLM 1.2 backend removal) are spot-verified by the spikes, which adjudicate any conflict with stage 8 or stage 12.

# Engineering Feasibility of Model-Internal Telemetry in Open-Weights Inference Servers

## Executive determination

The proposed layer F is technically feasible, but **not as one uniform load-time plugin across all major inference engines**. As of August 1, 2026, SGLang is the only reviewed high-throughput server with a documented, first-class facility that directly matches the desired loading model: it accepts a Python hook factory at server startup, resolves target modules against `model.named_modules()`, and installs standard PyTorch forward hooks once during model-runner initialization. vLLM has a general plugin system and a newly merged hidden-state extraction pathway, but its generic activation-observation API remains an open RFC rather than a stable extension point. Current TensorRT-LLM has changed architecture completely: release 1.2 removed the compiled TensorRT engine backend and now runs exclusively through a PyTorch backend, making the original compiled-engine assumption obsolete for current releases. citeturn12view1turn10search1turn8view2turn23search7turn23search11

The exact feasibility verdicts below apply to the requested design, meaning **per-generation-step logit statistics plus a residual-stream probe, correctly assigned to a request and exported without modifying the engine’s source tree**. A server that can return logprobs but cannot expose a residual stream does not receive a “supported plugin” verdict for monitor mode.

| Engine or server | Monitor mode: probe scalar plus logit stats | Deep mode: transient full activations | Engineering qualification |
|---|---|---|---|
| **vLLM** | **requires fork/patch** | **requires fork/patch** | Logit APIs and selected hidden-state extraction are supported, but there is no released generic inline activation-observation plugin. The hidden-state extractor is a specialized speculative-decoding/KV-connector path, not a cheap probe hook. |
| **SGLang** | **supported plugin** | **supported plugin** | Native `--forward-hooks` is the closest exact fit. Deep mode should be treated as eager, single-request debugging; production request correlation and CUDA-graph behavior remain spike risks. |
| **TensorRT-LLM 1.2+** | **supported plugin** | **supported plugin** | This means supported logits-processor and out-of-tree model/additional-output extension—not a generic PyTorch forward-hook plugin. |
| **llama.cpp library** | **supported plugin** when embedded in a custom host; **requires fork/patch** for stock `llama-server` | **supported plugin** when embedded; **requires fork/patch** for stock `llama-server` | The public evaluation callback is real, but there is no load-time module-plugin loader in the stock server. GPU tensors are not necessarily in host RAM. |
| **Ollama** | **requires fork/patch** | **requires fork/patch** | Ollama does not expose llama.cpp’s graph callback or an equivalent engine plugin through its public server configuration. |
| **MLX / `mlx-lm.server`** | **requires fork/patch** | **requires fork/patch** | Logits processors are supported, but MLX has no documented module-forward-hook equivalent and the server has no activation plugin API. |
| **NVIDIA Triton Inference Server** | **requires fork/patch** of the model or underlying backend | **requires fork/patch** of the model or underlying backend | Triton supports custom backends and tracing, but cannot introspect an opaque backend’s internal tensors on its own. |

“Patch” does not always mean maintaining a hostile long-lived fork. In several cases it can be a small upstreamable adapter, a replacement model class registered out of tree, or a custom server wrapper. The distinction is that the engine does **not currently promise the required behavior through a documented public contract**.

The safest first implementation target is therefore **SGLang**, initially with one GPU, tensor parallelism disabled, one active request, CUDA graphs disabled, and one residual-layer hook. It has the only reviewed API whose documented purpose explicitly includes logging intermediate activations and exporting hidden states from loaded model submodules. citeturn12view1

## vLLM and SGLang

**vLLM.** vLLM’s documented general plugin system loads Python entry points in worker processes and allows components such as model architectures to be registered. Its endpoint-plugin mechanism adds HTTP routes but deliberately does not introduce a new engine-access path; its I/O-processor plugins operate on pooling-model inputs and outputs rather than generative forward-pass tensors. Out-of-tree custom operations are also supported, but a custom operation is not a generic interception point for an arbitrary existing model’s residual stream. Consequently, merely placing `register_forward_hook` inside a `vllm.general_plugins` entry point would be an implementation accident: the public plugin contract does not provide the loaded model object, the currently scheduled batch, or the request-to-row map required by layer F. citeturn0search0turn0search3turn0search5turn0search8

That limitation is explicitly recognized by vLLM’s March 2026 “Observation Plugin” RFC. The RFC states that developers currently need substantial modifications to intercept activations, proposes an `ObservationPlugin` and manager that receive hidden states plus request mapping, and identifies continuous-batch attribution as a core design problem. Its proposed first implementation is prefill-oriented; decode interception is described as conflicting with CUDA graphs, with an eager-mode path estimated in the RFC at roughly a 25% throughput reduction. The associated phased implementation work described the actual GPU-model-runner interception as a later phase, not part of the initial API scaffolding. As of the research cutoff, this remained proposed work rather than a released extension contract. citeturn8view2

vLLM nevertheless gained an important no-fork **hidden-state extraction system** in version 0.18.0. It routes selected verifier-layer hidden states through speculative-decoding plumbing into dummy KV-cache layers, then uses the extensible KV Connector API to transfer them, initially to per-request safetensors files. This design deliberately reuses vLLM’s paged memory management so that chunked prefill, preemption, prefix caching, and concurrent requests remain trackable. The official write-up gives a concrete memory example: four FP16 layers from an 8,000-token, 4,096-dimensional sequence require about 268 MB. citeturn10search1turn10search4

That extractor is valuable for **deep-mode research**, but it is the wrong primitive for monitor mode. It allocates and moves complete hidden vectors, requires speculative-model configuration, and initially returns a file path rather than a scalar emitted inline. A July 2026 RFC proposed returning hidden states inline and keyed by request ID, while acknowledging payload scaling with token count, selected layers, and hidden dimension and initially restricting the interface to comparatively simple request shapes. citeturn8view3

vLLM’s logit-side support is considerably stronger. Its APIs expose generated-token logprobs and top-logprobs, and request logging can include request IDs. Those facilities are enough for token logprob and top-two margin. They are **not enough for exact entropy** unless full-vocabulary logits or probabilities are made available: entropy cannot in general be reconstructed from a truncated top-\(k\) distribution. A custom logits processor may see logits internally, but this should be validated against the specific vLLM serving API and CUDA-graph path rather than assumed from the OpenAI-compatible response. citeturn0search4turn0search6turn0search7turn0search11

The resulting vLLM verdict is:

- **Monitor mode: requires fork/patch.** Logit statistics are supported, but the inline residual probe and request-row mapping are not yet a released observation-plugin contract.
- **Deep mode: requires fork/patch for arbitrary full activation or attention capture.** Selected hidden states are a significant supported, out-of-tree exception through the extraction/KV-connector system, but that system does not constitute generic model-graph hooks.

**SGLang.** SGLang’s current `--forward-hooks` option is a documented startup extension. Each JSON hook specification names target modules using glob patterns over `model.named_modules()` and supplies an importable hook factory such as `my_package.hooks:make_hook`. SGLang invokes the factory, attaches the returned callable with `module.register_forward_hook`, and does so once in `ModelRunner.initialize()`. The documented callback has the ordinary `(module, inputs, output)` PyTorch signature, and the feature is explicitly described as suitable for logging intermediate activations, debugging internals, and exporting hidden states. citeturn11search0turn11search1turn12view1

This is an actual supported extension point, not monkey-patching. It came from the user-defined-hooks work represented by PR #13217 and is now present in current server arguments and source documentation. The registration code matches module names with `fnmatch`, dynamically imports the factory, and calls `register_forward_hook` on each match. Disabled hooks add no hook work; enabled overhead is determined by the selected modules and hook body. citeturn12view1

The remaining SGLang issue is **identity, not tensor access**. The public hook signature contains no request ID, trace context, scheduler request object, or row-to-request descriptor. SGLang’s internal execution path converts a CPU-side `ScheduleBatch` into a GPU-oriented `ForwardBatch`; attention backends consume request-pool indices, sequence lengths, and packed-token metadata. Those internal structures can in principle recover row membership, but they are not part of the documented hook-factory contract. citeturn13search6turn13search7turn14view3

For decode, one output row commonly corresponds to one active sequence, making a `req_pool_idx → request ID` side table plausible. Prefill is harder because a batch can contain variable numbers of new tokens per request, chunked prefill, cached prefixes, and potentially speculative-verification rows. The plugin must therefore consume the same offsets and sequence metadata as the scheduler; assuming that output row \(i\) simply equals HTTP request \(i\) is unsafe.

CUDA graphs are the other unresolved issue. SGLang supports graph capture and replay in its optimized attention paths. Python module hooks are straightforward during ordinary eager forwards, but the hook documentation does not define whether a submodule hook is invoked on every graph replay, only during capture, or around a higher-level replay wrapper. Deep mode should therefore explicitly disable CUDA graphs unless a runnable test proves that the selected module remains on an ordinary Python forward path. SGLang’s attention-backend documentation itself distinguishes ordinary forward execution from graph capture and replay, underscoring that these are separate execution paths. citeturn11search7

The SGLang verdict is:

- **Monitor mode: supported plugin.** The activation read itself is officially supported. Exact request/trace attribution may still need a small upstream mapping API if no stable runtime context is exposed to the hook.
- **Deep mode: supported plugin, dev-only.** Use eager execution and one request; do not infer production feasibility merely because a hook can clone an output tensor.

SGLang also exposes ordinary per-request logprob options, so margin and selected-token logprob do not need to be recomputed in the activation hook. Current request objects carry explicit request identifiers, and contemporary request structures also include options such as returned entropy in some paths, but the stable public behavior should be verified against the exact release selected for the spike. citeturn13search2

## TensorRT-LLM and Triton

**TensorRT-LLM.** The third design assumption requires the largest correction. TensorRT-LLM release 1.2 removed the TensorRT engine backend, the `trtllm-build`, `trtllm-refit`, and `trtllm-prune` commands, checkpoint-conversion scripts, and the `backend="tensorrt"` option. The documented migration path says that PyTorch is now the sole execution backend and Hugging Face checkpoints load directly without an engine-build step. Therefore, “TensorRT-LLM is compiled and has no runtime module graph” is now a statement about the **legacy backend**, not current TensorRT-LLM. citeturn23search7turn23search11

The current PyTorch backend remains marked beta, and its APIs may change, but it provides two strong extension paths. First, custom logits processors are officially supported. The processor receives a request ID, the logits tensor, token history, CUDA stream pointer, and optional client ID. A batched processor is also available to reduce callback overhead. NVIDIA’s documentation warns that synchronizing the stream slows the whole pipeline, which directly supports the design requirement that calculations stay on the supplied stream and that CPU export be asynchronous. citeturn23search1turn23search10turn23search15

Second, `SamplingParams.additional_model_outputs` can request named outputs such as `hidden_states` and `attentions`. Results are attached per sequence as context and generation outputs. The contract is model-dependent: the model’s forward implementation must return a dictionary containing `logits` and the requested auxiliary tensors. Thus a probe scalar can be implemented by an out-of-tree model class that returns `probe_score`, avoiding a TensorRT-LLM source fork while still changing the model implementation. It is **not** a universal hook that can be attached to every stock model by configuration alone. citeturn23search0turn23search2turn23search12turn23search14

Request attribution is better specified than in generic forward hooks. The logits processor receives `req_id`; generated results expose a unique `request_id`; additional outputs are attached to a particular completion sequence. The engine still performs overlap scheduling and packed batching, so an internal layer output may have a packed token dimension rather than a simple `[requests, hidden]` shape. The model implementation must use the supplied forward metadata rather than infer request boundaries from tensor shape. citeturn23search1turn23search6

The TensorRT-LLM verdict is therefore:

- **Monitor mode: supported plugin**, using the documented request-aware logits processor plus a model-provided additional scalar. This is a supported out-of-tree extension, not `register_forward_hook`.
- **Deep mode: supported plugin** for outputs that the model implementation exposes, including hidden states and attention where implemented. Adding a missing output requires an out-of-tree model implementation but not a core fork.

For historical deployments pinned to the removed compiled TensorRT backend, the original design claim remains substantially correct. TensorRT debugging requires tensors to be marked as outputs or debug tensors when constructing/building the network, followed by runtime debug-listener or output handling. There is no late-bound PyTorch module graph in a serialized TensorRT plan. Such a deployment can provide logits normally, but adding residual activations requires rebuilding the plan or replacing the model artifact. citeturn4search6turn4search8turn4search15

**NVIDIA Triton Inference Server.** Triton’s extension boundary is the backend. A backend can wrap TensorRT, PyTorch, ONNX Runtime, Python, or custom C/C++ logic; Triton sends one or more inference requests to that backend and receives the declared model outputs. Python-based backends implement `TritonPythonModel`, while native backends implement the Triton Backend API. These are supported extension mechanisms, but neither gives Triton generic visibility into an opaque backend’s intermediate graph. citeturn21search0turn21search4turn21search7turn21search10

A custom Triton backend can compute a probe because it owns the model call. An ensemble can post-process logits if logits are already declared outputs. Conversely, a Triton wrapper around vLLM, TensorRT, or another engine cannot synthesize a residual stream that the underlying backend never returns. The LibTorch backend is also based on serialized TorchScript/PT2 model artifacts rather than an arbitrary live Python object exposed to a server plugin, so model changes must be incorporated into the serialized model or backend. citeturn21search2turn21search5

Triton does preserve request boundaries at the backend API even when its scheduler dynamically batches requests. That makes result-to-request assignment tractable for a custom backend. It does not solve the second layer of batching inside an LLM backend such as vLLM or TensorRT-LLM; that backend must still return request-associated auxiliary outputs.

The Triton verdict is:

- **Monitor mode: requires fork/patch of the model or underlying backend.** Logit-only post-processing is supported when logits are declared outputs.
- **Deep mode: requires fork/patch of the model or backend.** It is not feasible as a Triton-server-only plugin.

Triton is, however, a strong place to terminate trace context. It supports OpenTelemetry export and client-side context injection, and custom backends can report custom trace activities that become spans. Thus it can carry `traceparent` and export xai-generated values once the backend has produced them; it cannot produce the values by itself. citeturn21search3turn21search12turn21search13

## llama.cpp, Ollama, and MLX

**llama.cpp.** The fourth design assumption is half right. llama.cpp does not expose PyTorch modules, but its public `llama_context_params` includes `cb_eval` and `cb_eval_user_data`, whose type is `ggml_backend_sched_eval_callback`. The GGML backend scheduler invokes this callback for graph nodes: first with `ask=true` to let the callback select nodes, and then with `ask=false` after the selected node is available for observation. The callback is wired into graph execution by `ggml_backend_sched_set_eval_callback`. This is a real, public graph-observation hook. citeturn17view0turn17view2turn18view3

The callback sees a named `ggml_tensor`, which is a better semantic starting point than a CUDA kernel address. It can inspect tensor name, dimensions, type, operation, and backend placement and can request contents using the backend tensor-copy APIs. This permits a custom host application to select a residual node and either copy it or arrange an additional GGML probe computation. It does not make stock `llama-server` a load-time plugin host: the callback must be supplied when constructing the `llama_context`, so the stock server needs a configuration/loader patch or must be replaced by a thin custom server linked against libllama. citeturn16view0turn17view0turn18view0

The assertion that tensors “live in host RAM” is incorrect. llama.cpp supports CUDA, HIP, Vulkan, SYCL, Metal, RPC, dedicated-GPU buffers, integrated-GPU buffers, CPU/GPU hybrid inference, and tensor parallelism. The backend API explicitly distinguishes CPU, dedicated GPU, integrated GPU, accelerator, and meta devices. `ggml_backend_tensor_get` can copy a tensor to host memory, but for a dedicated-GPU tensor that is a device-to-host operation and may introduce synchronization. citeturn15search0turn18view0

The callback’s granularity also differs from “once per generated token.” The backend scheduler may split a graph across devices or execute multiple subgraphs; users have observed multiple callback rounds for one `llama_decode` call. The `ask` phase exists specifically so selected nodes can influence how the scheduler batches graph execution. A plugin therefore needs a decode-call epoch and selected tensor identity rather than incrementing a token counter on every callback invocation. citeturn7search6turn17view0

Request mapping has some useful primitives. A `llama_batch` can contain multiple sequences, and every submitted token can carry one or more `llama_seq_id` values plus its position. Requested logits are stored in batch order, and `llama_get_logits_ith` returns the corresponding full-vocabulary row. Thus a custom host knows sequence identity at submission and can retain a batch-row map. The graph callback itself receives only the tensor and user data, not the `llama_batch`; the host must place current batch metadata into that user-data context before calling `llama_decode`. citeturn18view2turn17view3

For monitor mode, the preferable implementation is not to copy an entire residual to CPU. A GGML-native dot product should be inserted into the graph, or the selected tensor should be copied only on CPU/host-unified deployments. Inserting a new graph node is more intrusive than observing an existing one and may require a small model-graph patch. Merely using the callback to call `ggml_backend_tensor_get` on every GPU decode step risks serializing the graph.

The llama.cpp verdict is consequently:

- **Monitor mode: supported plugin for a custom embedding application; requires fork/patch for stock `llama-server`.** Full logits and per-sequence batch IDs are public. A truly cheap GPU-resident probe may still require adding a GGML graph operation.
- **Deep mode: supported callback for a custom embedding application; requires fork/patch for stock `llama-server`.** Device-to-host copies make it suitable only for the intended single-request debug mode.

No maintained upstream load-time activation plugin was found. The public callback itself is the relevant upstream mechanism, and ad hoc activation-capture code should be built around it rather than around CUDA memory interception.

**Ollama.** Ollama’s public user-facing extension surfaces are model import, Modelfiles, REST APIs, and client libraries, not execution-graph callbacks. Current Ollama may run models through its own Go engine or through a patched, pinned llama.cpp-derived runner, depending on model architecture and modality. Reports from 2026 explicitly distinguish Ollama’s own model implementations from its llama.cpp fallback, and packaging discussions note that Ollama requires its own patched `llama-server` build rather than an interchangeable stock binary. citeturn19search3turn19search5turn19search9

There is no documented option that forwards a user-supplied `cb_eval`, loads a shared-library instrumentation plugin, or returns arbitrary intermediate tensors. A Modelfile changes model configuration and adapters, not the runner’s graph. Therefore both monitor and deep modes require an Ollama patch, a custom runner, or bypassing Ollama and running an instrumented llama.cpp host directly. Ollama’s vendored-engine lag and dual-engine architecture also make internal patches more maintenance-intensive than a direct llama.cpp integration. citeturn19search1turn19search4turn19search8

**MLX and MLX-LM.** MLX’s documented extension mechanism is custom CPU or Metal operations. `mlx-lm` supports user-supplied samplers and logits processors, which receive current logits and token history, so margin, selected-token logprob, and—if the complete logits are retained—entropy can be calculated in the generation loop without changing the core framework. citeturn20search5turn20search13

There is no documented MLX equivalent of `torch.nn.Module.register_forward_hook`, and `mlx_lm.server` exposes no activation-hook loader. Capturing a residual therefore requires wrapping or modifying the selected model layer’s `__call__`, replacing a module in the model tree, or editing the model definition to return an auxiliary value. Python makes such monkey-patching easy, but ease is not the same as a supported extension contract.

The bundled MLX-LM HTTP server is explicitly described as a basic server not recommended for production. Its 2026 issue history also shows continuing concurrency, KV-cache, and mixed-request correctness work. Alternative servers such as `vllm-mlx` and oMLX add continuous batching and richer cache management, but they are separate serving implementations rather than activation plugins. MOLA, another third-party serving extension, explicitly reports requiring a local MLX-LM patch for its detached batching API. citeturn20search0turn20search3turn20search6turn20search7turn20search12

The MLX verdict is:

- **Monitor mode: requires fork/patch** for a residual probe; logit-only statistics are supported through logits processors.
- **Deep mode: requires fork/patch** or an unsupported model wrapper. Unified memory makes host access less discontinuous than on a discrete GPU, but materializing and retaining tensors still consumes memory bandwidth and can force lazy MLX computations to evaluate.

MLX is a reasonable later desktop-development target, particularly because Apple unified memory reduces explicit device-to-host-copy complexity. It is not the safest first proof of the requested server-plugin architecture.

## Inline cost and request attribution

A single scalar linear probe is arithmetically tiny. For residual width \(d\), one dot product requires approximately \(2d\) floating-point operations. At \(d=4{,}096\), that is about 8,192 operations; at \(d=8{,}192\), about 16,384. One BF16 probe vector occupies 8 KiB or 16 KiB respectively. For a decode batch of 64 active sequences, the corresponding matrix-vector operation is roughly 0.52 or 1.05 million operations and returns only 256 bytes if scores are kept as FP32.

The operative cost is therefore usually **not arithmetic throughput**. It is:

1. launching an otherwise unfused GPU operation;
2. reading the residual again from device memory;
3. preserving CUDA-graph compatibility;
4. handling tensor-parallel sharding;
5. transferring scores to the CPU without a synchronizing `.item()` or `.cpu()` call;
6. mapping output rows to requests; and
7. serializing and exporting telemetry away from the GPU-worker hot path.

For a batch of 64 and \(d=8{,}192\), scanning one BF16 residual consumes about 1 MiB of activation traffic per selected layer per decode iteration, before considering caches and probe-weight reads. That is modest on a modern GPU but not free when repeated at every token and replicated across tensor-parallel ranks. A practical implementation should keep probe weights resident on the same device, run one batched matrix-vector or narrow GEMM, write \(B\) scalar results into a preallocated device buffer, copy them asynchronously to a pinned ring buffer, and export them from another thread or process.

Tensor parallelism changes the “one cheap matmul” statement. If the residual is sharded across hidden dimension, each rank can compute a partial dot product with the matching probe shard, after which the scalar requires an all-reduce. If the selected hook is placed after a residual all-gather, no new collective is needed, but memory traffic may be higher. Pipeline parallelism means the request/trace map must also reach the stage containing the selected layer. These are implementation details that only a real engine run will resolve.

Full-vocabulary uncertainty has a different cost profile. A top-two margin can often reuse the sampler’s existing top-\(k\) work. Exact entropy requires a stable log-sum-exp and probability-weighted reduction across the full vocabulary. For batch 64, vocabulary 128,000, and BF16 logits, one entropy pass reads about 16 MiB of logits per decode step, plus reduction intermediates. That may be more expensive than the residual probe. Returning top-\(k\) logprobs over HTTP is not equivalent to computing exact entropy internally.

Deep mode scales with full tensor size. A residual tensor for \(N\) token rows, width \(d\), and element size \(s\) consumes \(Nds\) bytes per selected layer. The vLLM example of 8,000 tokens, four layers, width 4,096, and FP16 is approximately 268 MB; all layers would be several gigabytes. Attention probabilities can be worse because an unfused conceptual attention matrix grows quadratically with prompt length, while optimized FlashAttention-style kernels may never materialize that matrix as an inspectable tensor at all. citeturn10search1

Request attribution should be designed as an engine adapter, not inferred from tensor dimensions:

| Engine | Mapping primitive | Remaining problem |
|---|---|---|
| **vLLM** | Request IDs, scheduler request state, and the hidden-state extractor’s request-keyed output | A generic hook does not currently receive the scheduled row map; chunked prefill, preemption, and speculative rows must be handled. |
| **SGLang** | Request IDs at the API/scheduler layer and GPU `req_pool_indices`/sequence metadata | The documented hook receives neither ID map nor trace context. |
| **TensorRT-LLM** | Request ID in logits processors and per-sequence additional outputs | Packed token order and tensor-parallel execution still matter inside custom model outputs. |
| **llama.cpp** | Per-token `llama_seq_id`, positions, requested-logit rows, and host-owned batch | The graph callback receives no batch object; current batch metadata must be attached through callback user data. |
| **Triton** | Backend receives distinct request objects even after server batching | An underlying LLM backend may perform a second, independent continuous-batching stage. |
| **MLX servers** | Server-owned request/slot objects | No public activation callback receives those objects. |

The W3C trace ID should therefore be stored in an engine-side request registry keyed by the engine’s stable request or sequence identifier. A hook should emit an internal compact record such as `(request_key, generation_index, layer, probe_id, score, margin)` into a queue. OpenTelemetry span creation, attribute conversion, sampling, and network export should happen outside the model-runner thread. Creating and exporting a span synchronously for every token would risk making telemetry overhead larger than the probe itself.

## eBPF, CUPTI, bpftime, and OpenTelemetry

The fifth assumption is substantially confirmed, with one important qualification: low-level instrumentation can physically observe more than timing, but it cannot **generically assign model semantics** to what it sees.

CUPTI is designed to trace CUDA runtime and driver calls, kernel launches, memory copies, memsets, allocation activity, PC samples, and performance metrics. Activity records provide timestamps, kernel names, device, context, stream, transferred byte counts, and correlation IDs linking a runtime or driver invocation to the resulting GPU activity. This is enough to build kernel timelines, launch counts, copy-volume metrics, memory-allocation histories, occupancy/performance-counter views, and CPU-to-GPU causal correlation. citeturn21search1turn21search6turn21search11turn21search15turn21search16turn21search17

Ordinary eBPF can add process, syscall, network, scheduler, library-call, and CUDA API observations through tracepoints, uprobes, USDT, and related hooks. Existing “zero instrumentation” AI observability projects such as AgentSight use that boundary to observe agent processes and encrypted-provider traffic, not model residual streams. citeturn22search2turn22search3turn22search4turn22search7

bpftime’s GPU work, originating in eGPU and now merged into bpftime, goes further. It JIT-translates eBPF bytecode to PTX, injects probes into running GPU kernels, supports shared CPU/GPU maps, and can dynamically add or remove low-level GPU probes. Its published capability is therefore not limited to launch timing: an injected probe can inspect selected registers, addresses, counters, and memory events inside an instrumented PTX kernel. citeturn22search0turn22search1

That does **not** make bpftime a generic residual-stream extractor. At PTX/kernel level, a probe sees instructions, registers, pointers, thread/block indices, and memory operations. The logical fact that “this address range is layer 18’s post-attention residual for request `abc`, token 42” lives in the model graph, scheduler, allocator, and tensor metadata above the kernel. Fused kernels may keep partial values only in registers or shared memory; allocators reuse addresses; tensor-parallel ranks hold shards; quantization changes representation; CUDA graphs replay the same addresses for different batches; and one kernel can process rows from many requests.

Recovering an activation with bpftime is possible only after supplying engine- and kernel-specific knowledge such as the relevant kernel variant, exact program point, pointer argument, shape, layout, rank, batch-row map, and request membership. At that point the system is no longer backend-agnostic instrumentation; it is a reverse-engineered, version-pinned activation patch expressed at PTX level. It is less reliable than using the engine’s graph-level tensor object and should not be the production monitor path.

The realistic “cost channel” boundary is:

- **Supported:** kernel duration, launch count, stream occupancy, memcpy bytes and direction, allocation/free activity, API-to-kernel correlation, GPU counters, CPU scheduling, network timing, and per-batch GPU work.
- **Conditionally supported:** per-request cost when the application emits request-associated ranges or when a request owns distinct launches.
- **Not exactly supported under continuous batching:** splitting one shared kernel’s duration among the several requests whose tokens occupied that batch. Any division is an allocation model—equal share, token-weighted share, counterfactual estimate—not a directly observed fact.
- **Not generically supported:** named residual streams, layer-specific hidden states, attention heads, logical tokens, or probe concepts.

NVTX or engine-provided external correlation IDs can bridge application phases to CUPTI records, but that still labels a launch or range rather than reconstructing the contents and semantics of its tensors. NVIDIA describes NVTX as an application annotation API; GPU-device-code NVTX ranges themselves are not the mechanism for arbitrary per-thread semantic tracing. citeturn22search10turn21search15

No existing reviewed project was found that already performs the complete requested combination: **extracting residual-stream probe scores or attention attributions from a throughput inference server and emitting those model-internal values as OpenTelemetry spans correlated to the caller’s W3C trace**. The closest official components are complementary rather than complete:

- Triton can ingest propagated OpenTelemetry context and lets custom backends report custom span activities, but it does not obtain model internals automatically. citeturn21search3turn21search12
- vLLM has request observability and selected hidden-state extraction, but its generic activation-observation plugin remains proposed rather than an OTel-exporting implementation. citeturn10search1turn8view2
- AgentSight provides eBPF-based process and interaction observability, not in-server activations. citeturn22search4
- General AI observability stacks instrument HTTP, agent orchestration, model invocation, prompts, responses, and token counts—not residual tensors. citeturn22search6turn22search13

Layer F would therefore be a new integration, although it can reuse standard OTel propagation/export and existing engine-specific signal sources.

## Assumption corrections and spike risks

**Assumption one — PyTorch hooks and cheap probes: needs revision.** The underlying PyTorch statement is correct, and SGLang now proves that a server can expose it as a supported load-time facility. It is not correct to generalize that capability to vLLM: vLLM’s released general plugins do not provide a documented loaded-model activation hook, and its own observation RFC identifies that gap. A linear probe’s arithmetic is cheap, but graph replay, an extra launch, tensor-parallel reduction, device-to-host transfer, and request mapping can dominate. citeturn12view1turn8view2

**Assumption two — vLLM batching makes attribution the hard part: confirmed.** vLLM’s observation RFC and hidden-state-extraction design both treat mapping, chunked prefill, preemption, memory lifetime, and asynchronous transfer as first-class problems. The same problem exists in SGLang and other continuous-batching systems, although each uses different scheduler metadata. citeturn8view2turn10search1turn10search4

**Assumption three — TensorRT-LLM requires compiled-engine rebuilds: obsolete for current releases.** It remains correct for legacy serialized TensorRT plans, but TensorRT-LLM 1.2 removed that backend. Current TensorRT-LLM is PyTorch-only and officially supports request-aware logits processors and model-defined hidden-state/attention outputs. The design documents should separate “legacy TensorRT plan” from “current TensorRT-LLM.” citeturn23search0turn23search1turn23search7turn23search11

**Assumption four — llama.cpp tensors are reachable through callbacks and live in host RAM: partially confirmed, partially false.** The GGML evaluation callback is public and useful. Tensors may reside in CPU, dedicated-GPU, integrated-GPU, accelerator, remote, or split buffers; reading them on the host can require a backend copy and synchronization. Stock llama-server and Ollama do not expose the callback as a load-time plugin. citeturn17view0turn18view0turn18view3turn15search0

**Assumption five — eBPF/CUPTI are cost channels, not semantic activation channels: confirmed with nuance.** CUPTI observes execution and memory activities. bpftime/eGPU can inject code into PTX and inspect low-level values, but it does not infer model-graph identity, tensor names, logical requests, or residual semantics. Exact per-request GPU cost is also unavailable for kernels shared by a continuously batched set of requests unless the engine contributes attribution metadata. citeturn21search11turn21search15turn22search1

The recommended implementation sequence is:

**S3 on SGLang first, with a vLLM comparison.** Attach one hook to one architecturally stable residual boundary, run a GPU-resident batched probe, and record only scalar scores. Begin in eager single-request mode, then enable continuous batching, CUDA graphs, tensor parallelism, chunked prefill, prefix caching, and speculative decoding one at a time. This is the fastest route to proving the intended load-time-plugin architecture because SGLang’s hook API is already official. A parallel vLLM micro-spike should determine whether its hidden-state connector can be adapted to scalar-only transfer or whether the Observation Plugin RFC must land before a supported implementation is possible.

**S4 on llama.cpp.** Build a small libllama host that supplies `cb_eval`, filters by tensor name and dimensions, and associates callback invocations with the submitted `llama_batch`. Test CPU, Metal/unified memory, and discrete CUDA separately. Compare copying a residual to host with inserting or reusing a GGML dot-product node. Only after that should a minimal `llama-server` patch or upstream plugin-loader proposal be considered.

**S5 on eBPF/CUPTI.** Treat this strictly as a cost-channel experiment. Correlate an inbound `traceparent` to engine request IDs, scheduler batches, CUDA API calls, and CUPTI kernels; then quantify what fraction of GPU work can be assigned exactly, what fraction is shared, and how stable correlation remains under CUDA graphs and multiple streams. A bpftime sub-spike may instrument one known kernel to demonstrate that values can be observed while semantic tensor identity cannot be recovered without engine-specific metadata.

Those runnable spikes are required to retire the following risks:

1. **Hook execution under optimization.** Documentation cannot prove whether a selected SGLang hook executes on every CUDA-graph replay, only during capture, or after compiler/module fusion.
2. **Stable residual boundary.** Model implementations differ in whether a layer output is pre-residual, post-attention residual, post-MLP residual, tuple-wrapped, tensor-parallel sharded, or fused away.
3. **Batch-row identity.** Only execution can validate mapping through decode, chunked prefill, prefix-cache hits, request preemption, speculative verification, beam or multi-sequence output, and aborted requests.
4. **Actual throughput impact.** Kernel launch latency, stream synchronization, allocator behavior, asynchronous copy, and OTel queue contention cannot be established from FLOP counts.
5. **Distributed behavior.** Tensor-, pipeline-, expert-, and data-parallel deployments may invoke hooks on several ranks and require scalar reduction, rank selection, or deduplication.
6. **llama.cpp callback semantics across backends.** Callback count, tensor naming, scheduler splits, and host-copy behavior vary between CPU, Metal, CUDA, Vulkan, and hybrid placement.
7. **Exactness of the cost channel.** CUPTI can measure shared batch kernels accurately but cannot reveal an objectively correct per-request division without scheduler-provided membership and an explicit allocation policy.
8. **Trace-context lifetime.** `traceparent` must survive API parsing, queues, scheduler admission, worker IPC, distributed ranks, cancellation, and streaming completion without relying on thread-local context that disappears before GPU execution.
9. **Backpressure and failure isolation.** The server must continue generating when the OTel collector is slow or unavailable; a bounded, lossy telemetry queue is likely necessary.
10. **Numerical equivalence.** The probe must be evaluated at the intended residual point and precision without modifying model output, graph capture, sampling, or quantization behavior.