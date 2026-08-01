# S3: parametric span from a throughput inference server

## Outcome

S3 proved the local mechanics for a bounded parametric evidence channel on a pinned vLLM CPU server: numerical ground truth, W3C continuation, L0 and L1 logits access, an L2 residual probe under continuous batching, canonical OpenTelemetry child spans, lifecycle correctness, exporter isolation, and portable OTLP/HTTP backend configuration. The local stage-12 matrix closes 11 of 12 assertions; rank/worker duplication is deferred to the P5 CUDA run. The supported-extension finding is mixed: vLLM 0.23.0 can expose full logits without a source patch, but residual observations still require a targeted patch because its general-plugin contract has neither a post-model-load callback nor request-row metadata.

The authoritative scope and phase gates are in the [S3 plan](../../plan/S3-parametric-span.md). Span hierarchy, bounded attributes, lifecycle expectations, backend transport, and the acceptance matrix follow the [OpenTelemetry propagation and transport research](../../research/12-otel-propagation-and-transport.md).

## Reproducible ground truth and pins

The reference model is `Qwen/Qwen3-0.6B` at immutable revision `c1899de289a04d12100db370d81485cdf75e47ca`; the Llama fallback was not used. The Hugging Face path used Python 3.12.6, PyTorch 2.7.1, Transformers 4.53.2, eager CPU float32, greedy generation, seed 314159, three pinned prompts, and six generated steps per prompt. It emitted full-vocabulary entropy, top-two logit margin, top-one probability, and a probe scalar per step. Two complete runs were JSON-identical.

The final cross-engine probe convention follows S4: `numpy.default_rng(20260801)`, a 1,024-dimensional float32 unit vector with SHA-256 `be20dfa1bd53444ff4d6f5fd840586659b59355b0de850ca94e091bec56a9843`, index-order dot product with double accumulation, decoder block 14 post-residual at the last token, and HF `hidden_states[15]` equal to llama.cpp `l_out-14`. HF float32 versus the S4 F16 GGUF oracle passed all 18 shared values with mean absolute probe delta 0.00548175 and maximum 0.01581758 under the declared 0.2 cross-engine tolerance.

The server pin is the official native arm64 image `vllm/vllm-openai-cpu:v0.23.0-arm64`, image ID `sha256:edb1bf2d12af164a924971ad9d1edf6b28c7c7606410f997d2370e20e9296`, repository digest `sha256:3732dc3183478eb6e215f8d0aae863c79ce8eead4f601d185bd6983dc2e31392`. It ran float32 eager with model length 128, `max-num-seqs=2`, and the V1 CPU runner because Model Runner V2 requires Triton in this image.

## Trace continuation

The agent uses `opentelemetry.propagate.inject` rather than constructing W3C headers manually. Phase 1 captured a valid sampled `traceparent` and proved its trace and parent IDs matched the active agent span. Phase 2 sent the same carrier through the OpenAI Python SDK to the real server and programmatically found one `llm_request` server span per request with the same trace ID and the agent client span as parent. Phase 3 placed every model observation directly beneath that server span. An unsampled `flags=00` parent still completed inference but exported no spans, while sampled parents exported normally, confirming parent-based behavior.

## L0: useful logits, impossible exact entropy

OpenAI top-five logprobs matched the HF selected-token logprob with mean/max absolute delta 0.0000041174/0.0000113249 and top-two margin with 0.0000163322/0.0000419319. The returned five probabilities covered 0.8102803 probability mass on average and only 0.4032426 at minimum, so exact entropy is not reconstructible. Summing only the observed entropy contributions produced mean/max error 1.2453155/4.2068157 nats; renormalizing top five produced 1.1785813/3.9328550 nats. Neither approximation was exact on any of 18 steps.

## L1: zero-patch full-logit access

vLLM 0.23.0 serving accepts a configured logits processor through `--logits-processors`. A 49-line spike processor received the full-vocabulary row, computed entropy, top-two margin, top-one probability, and token ID, then returned logits unchanged. It required zero vLLM source lines. Across 18 rows, vLLM versus HF mean/max absolute deltas were 0.0000083703/0.0000360012 for entropy, 0.0000163184/0.0000419617 for margin, and 0.0000022509/0.0000079274 for top-one probability; all token IDs were exact.

The important contract subtlety is `is_argmax_invariant`. Declaring it true allowed greedy sampling to skip the processor, which is a valid optimization for a transform that cannot change argmax but surprising for an observer whose side effect is the evidence. Declaring false forced invocation while still returning logits unchanged. Production observational processors need an explicit execution contract rather than relying on mutation semantics.

## L2 route (a): general-plugin negative evidence

The `vllm.general_plugins` entry point was exercised in the API process, model-registry subprocess, engine core, and worker. Every callback was argument-free and ran before a model runner, input batch, or scheduler object existed. The worker invocation occurred during `init_worker`, before `CPUModelRunner.load_model`. The callback could register model classes and other global facilities, but it could not obtain the loaded model, register a post-load forward hook, observe per-step batch rows, or receive a stable request identity. Global monkey-patching from the callback would only disguise an unsupported core override and was not counted as a plugin success.

## L2 route (b): targeted patch and concurrency

The Phase 3 patch added 88 lines to two installed-package files with no repository fork. In `CPUModelRunner.load_model`, it registered a forward hook on `model.model.layers[14]`. Qwen3 returns the MLP contribution and residual separately, so the canonical post-block residual is `output[0] + output[1]`. The hook read the inherited V1 runner's private `input_batch.req_ids` and `num_scheduled_tokens` arrays, treated request rows as contiguous in that order, selected each request's cumulative last row, and computed the S4 dot product with float32 inputs and index-order double accumulation. The OTel helper joined the bounded records to the completed request and emitted the canonical children.

Sequential vLLM float32 versus HF float32 passed the strict 0.0001 tolerance with mean absolute probe delta 0.00000191625 and maximum 0.00000769890. With `max-num-seqs=2`, four interleavings paired the pinned prompt with `List three prime numbers:`. Every pinned six-step scalar was bit-identical to sequential execution: mean and maximum delta were exactly 0.0 in all four trials, and real two-request forwards were present.

The mapping is fragile. It depends on private V1 runner state and update timing, contiguous packed rows in `req_ids` order, Qwen3's two-tensor decoder output, the `model.model.layers[14]` path, and a prefix relation between worker-internal and API request IDs. It is not validated for V2, tensor/pipeline parallelism, speculative decoding, disaggregated prefill/decode, or multiple workers. The JSONL channel is a correctness oracle, not production IPC.

## Observation Plugin RFC gap analysis

The proposed vLLM Observation Plugin interface would eliminate most of the runner patch if decode observations are implemented. Its model-runner-owned hook and `LayerObservation` request/token offsets address the two failures of general plugins. The following five requirements are ready to post as upstream feedback:

1. Define a stable semantic observation point such as `post_decoder_block_residual`, not only an architecture-specific forward return.
2. Provide explicit request and token-row offsets for prefill and decode under chunking, prefix caching, speculative decoding, and disaggregated execution.
3. Provide a stable request/choice identifier shared with the server trace lifecycle, without internal-prefix parsing.
4. Expose a bounded observation handoff or active request context so scalar spans can be parented without patching tracing internals.
5. Specify tensor ownership, clone/copy behavior, callback timing, and lifetime so plugins can reduce immediately and never retain raw activations.

The RFC's initial prefill scope is insufficient for this per-generation-step probe; decode observation is mandatory. Its estimated eager-mode throughput cost also needs measurement in P5.

## Canonical span and privacy contract

The server emits `xai.parametric.observe` INTERNAL spans with instrumentation scope `org.ethicalai.xai.parametric`, parented directly under `llm_request`. Attributes include the parametric channel and schema, model/revision, probe identity/version/score, layer and token index, `claimed_cot_faithfulness=false`, `raw_activations_exported=false`, `raw_logits_exported=false`, and `content_included=false`. Collector assertions verified kind, scope, trace ID, parent span ID, bounded scalar attributes, and negative controls. No prompt, completion, token string, logits vector, hidden vector, or raw activation is exported.

The spike emits one child per finalized token observation. The stage-12 recommendation prefers one bounded span per model request, so per-token children versus one aggregate span remains an F ADR cardinality decision. Either choice must preserve the same privacy controls and must not make the model return internal evidence to the caller.

## Lifecycle and cancellation ordering

Successful streaming produced one ended server span and 12 unique child observations. A client close after two chunks produced one ended abort span and exactly two child observations. A 50 ms timeout before model execution produced one ended abort span and no fabricated score. Every finalized scalar had exactly one child with a unique span ID and contiguous token index; there were no orphan parents or duplicate server spans.

The first cancellation run exposed a race: an in-flight worker forward appended a third scalar after the API process had already read the scalar channel and ended the abort span. Phase 4 added 47 changed lines relative to the Phase 3 image. Abort trace state is retained, EngineCore acknowledges the abort before trace finalization, and a cross-process lock plus finalization marker serializes the final worker write with export. This proves the required lifecycle ordering but is deliberately not a production design. The public observation contract needs an engine-owned, exactly-once request-finalization callback and bounded scalar buffer.

## Export failure isolation

The collector was removed after chunk two of a 60-token stream. Generation completed all 60 chunks in 10.247 seconds, the health endpoint remained good, and the server did not error or block. After the collector restarted, the export contained one server span and all 60 child spans. OpenTelemetry Python 1.42.1 used its default in-memory `BatchSpanProcessor` queue and the OTLP/gRPC exporter's retry loop, so this bounded outage retried and delivered rather than dropping.

The defaults are not durable delivery: queue capacity is 2,048 spans, scheduled delay 5 seconds, maximum batch 512, export timeout 30 seconds, and the gRPC exporter makes six jittered exponential-backoff attempts for retryable errors. Queue overflow, retry exhaustion, process exit, or a longer outage can drop telemetry. Layer F must remain loss-tolerant and inference must never wait for backend recovery.

## Backend transport contracts

One canonical emitter targeted three local OTLP/HTTP protobuf receivers through configuration only. Raw collector used `/v1/traces` with no auth. The Logfire-shaped receiver used `/v1/traces` with an `Authorization` write-token header. The Langfuse-shaped receiver used `/api/public/otel/v1/traces`, HTTP Basic authorization, and `x-langfuse-ingestion-version: 4`. Every protobuf decoded and retained the exact `xai.parametric.*` namespace.

No real Logfire or Langfuse endpoint was contacted, no account was used, and no environment credential was searched for or read. The result proves the documented ingestion boundary and thin-adapter shape, not hosted indexing, UI rendering, or query behavior. The emitter remains backend-neutral; destination configuration owns endpoint, protocol, and headers.

## Local stage-12 acceptance matrix

| # | Assertion | Status |
|---:|---|---|
| 1 | Valid agent W3C carrier | PASS |
| 2 | Server continues the agent trace | PASS |
| 3 | Context/request identity survives local server process boundaries | PASS |
| 4 | Request-safe batching attribution | PASS |
| 5 | Scalar emission without raw tensors | PASS |
| 6 | Stable success/stream/cancel/timeout lifecycle | PASS |
| 7 | Deterministic parent-based sampling | PASS |
| 8 | No tracer-provider conflict | PASS |
| 9 | Raw/Logfire/Langfuse local contracts retain namespace | PASS |
| 10 | TP/PP/DP rank duplication controlled | GPU-DEFERRED |
| 11 | No accidental content capture | PASS |
| 12 | Export failure isolated from inference | PASS |

The local result is 11 pass, 0 fail, and 1 GPU-deferred. The process-boundary pass is functional: worker-produced scalars are correctly joined into the continued request trace, but vLLM 0.23.0 does not emit a standalone per-request worker span.

## P5 GPU runbook pointer

P5 remains the CUDA phase defined by the [S3 plan](../../plan/S3-parametric-span.md). It must run SGLang's supported `--forward-hooks` mechanism and `req_pool_indices` side table, repeat the aligned oracle and concurrent-decoy tests, compare CUDA graphs on/off, validate vLLM V2/GPU and TP=2 before the intended TP/PP/DP topology, add prefix-cache and speculative-decode cases, and measure tokens/s plus latency with the hook disabled/enabled. The local streaming, cancellation, timeout, sampling, and collector-outage suite should be rerun unchanged on the GPU architecture. No P5 execution was performed during this phase.

## Open items for the F ADR

- Decide whether the first supported backend is SGLang-only until vLLM's Observation Plugin lands, or whether a pinned, maintained vLLM patch is acceptable.
- Decide per-token child spans versus one per-request aggregate, with an explicit cardinality and export budget.
- Require a stable semantic residual point, request/choice identity, decode row map, and exactly-once finalization callback in any supported engine adapter.
- Replace file IPC and request-prefix joins with a bounded in-process or engine-owned scalar channel; raw tensors must never cross the boundary.
- Define loss-tolerant exporter behavior and observability for dropped scalar spans without coupling inference success to telemetry success.
- Hold V2/GPU, TP/PP/DP cardinality, speculative decoding, CUDA-graph behavior, and throughput overhead as release gates, not documentation caveats.
- Keep hosted Logfire/Langfuse rendering/query validation as optional deployment certification; the core contract is ordinary OTLP and must not require backend SDK types.
