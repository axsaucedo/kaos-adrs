# S3: parametric span from a throughput inference server

## Outcome

S3 proved a bounded parametric evidence channel from local mechanics through real CUDA execution: numerical ground truth, W3C continuation, L0 and zero-patch L1 logits access, an L2 residual probe under continuous batching, canonical OpenTelemetry child spans, lifecycle correctness, exporter isolation, portable OTLP/HTTP backend configuration, request-safe GPU attribution, CUDA-graph behavior, and production-relative overhead. The combined stage-12 matrix closes 11 of 12 assertions. Assertion 10, TP/PP/DP rank cardinality, remains deferred because the campaign host had one L4 and TP/PP were never attempted.

The supported-extension finding is now precise. SGLang 0.5.16 exposes its officially supported `--forward-hooks` activation path and passed the full residual oracle and concurrent row-shift gate without an engine patch. vLLM 0.26.0 exposes full logits through `--logits-processors` without a patch, but per-token residual observation still requires a targeted model-runner patch because neither its general-plugin contract nor its batch logits-processor contract provides a loaded-layer activation callback. On both engines, Python forward-hook side effects disappear under the production compiled/CUDA-graph path, so exact residual observation is currently an opt-in eager diagnostic rather than an always-on production channel. The production default should use zero-patch logits observation and reserve residual probes for bounded diagnostic sessions until engines provide a graph-aware semantic observation interface.

The authoritative scope and phase gates are in the [S3 plan](../../plan/S3-parametric-span.md). Span hierarchy, bounded attributes, lifecycle expectations, backend transport, and the acceptance matrix follow the [OpenTelemetry propagation and transport research](../../research/12-otel-propagation-and-transport.md).

## Reproducible ground truth and pins

The reference model is `Qwen/Qwen3-0.6B` at immutable revision `c1899de289a04d12100db370d81485cdf75e47ca`; the Llama fallback was not used. The Hugging Face path used Python 3.12.6, PyTorch 2.7.1, Transformers 4.53.2, eager CPU float32, greedy generation, seed 314159, three pinned prompts, and six generated steps per prompt. It emitted full-vocabulary entropy, top-two logit margin, top-one probability, and a probe scalar per step. Two complete runs were JSON-identical.

The final cross-engine probe convention follows S4: `numpy.default_rng(20260801)`, a 1,024-dimensional float32 unit vector with SHA-256 `be20dfa1bd53444ff4d6f5fd840586659b59355b0de850ca94e091bec56a9843`, index-order dot product with double accumulation, decoder block 14 post-residual at the last token, and HF `hidden_states[15]` equal to llama.cpp `l_out-14`. HF float32 versus the S4 F16 GGUF oracle passed all 18 shared values with mean absolute probe delta 0.00548175 and maximum 0.01581758 under the declared 0.2 cross-engine tolerance.

The server pin is the official native arm64 image `vllm/vllm-openai-cpu:v0.23.0-arm64`, image ID `sha256:edb1bf2d12af164a924971ad9d1edf6b28c7c7606410f997d2370e20e9296`, repository digest `sha256:3732dc3183478eb6e215f8d0aae863c79ce8eead4f601d185bd6983dc2e31392`. It ran float32 eager with model length 128, `max-num-seqs=2`, and the V1 CPU runner because Model Runner V2 requires Triton in this image.

The SGLang GPU pin is official tag `docker.io/lmsysorg/sglang:v0.5.16`, multi-platform index digest `sha256:7b6a35df9839fd593a94a1eaee82d7777f472225d9f3ad1f8a2e0cb2bd1785d0`, and executed linux/amd64 manifest digest `sha256:984699c298a95b73c469b2191403ddc85fd780506e13c39c4afff3845e27bc6c`. It contains SGLang 0.5.16 at commit `fdebc938f7f4d16fe6b9f55dcd9a767cf0899ea1` and PyTorch 2.11.0+cu130. The model ran bfloat16 on one NVIDIA L4 with TP=1, PP=1, and DP=1.

The vLLM GPU pin is official tag `docker.io/vllm/vllm-openai:v0.26.0`, multi-platform index digest `sha256:ffb2d59b1c059a5bd8d781320c9f5189de8293693b7d95da54befddaa54abf52`, and executed linux/amd64 manifest digest `sha256:770fe65b2c73ee74a5c42165cf3433de4048cc2cd9c57a937ca4e35aba5aa87b`. It contains vLLM 0.26.0 at build commit `ffd46bfab2128bb84146050e98b51a617c6575ab` and PyTorch 2.11.0+cu130. The server selected the V1 engine core with the V2 GPU Model Runner, bfloat16, asynchronous scheduling, prefix caching, torch.compile, and full/piecewise CUDA graphs by default.

## Trace continuation

The agent uses `opentelemetry.propagate.inject` rather than constructing W3C headers manually. Phase 1 captured a valid sampled `traceparent` and proved its trace and parent IDs matched the active agent span. Phase 2 sent the same carrier through the OpenAI Python SDK to the real server and programmatically found one `llm_request` server span per request with the same trace ID and the agent client span as parent. Phase 3 placed every model observation directly beneath that server span. An unsampled `flags=00` parent still completed inference but exported no spans, while sampled parents exported normally, confirming parent-based behavior.

## L0: useful logits, impossible exact entropy

OpenAI top-five logprobs matched the HF selected-token logprob with mean/max absolute delta 0.0000041174/0.0000113249 and top-two margin with 0.0000163322/0.0000419319. The returned five probabilities covered 0.8102803 probability mass on average and only 0.4032426 at minimum, so exact entropy is not reconstructible. Summing only the observed entropy contributions produced mean/max error 1.2453155/4.2068157 nats; renormalizing top five produced 1.1785813/3.9328550 nats. Neither approximation was exact on any of 18 steps.

## L1: zero-patch full-logit access

vLLM 0.23.0 serving accepts a configured logits processor through `--logits-processors`. A 49-line spike processor received the full-vocabulary row, computed entropy, top-two margin, top-one probability, and token ID, then returned logits unchanged. It required zero vLLM source lines. Across 18 rows, vLLM versus HF mean/max absolute deltas were 0.0000083703/0.0000360012 for entropy, 0.0000163184/0.0000419617 for margin, and 0.0000022509/0.0000079274 for top-one probability; all token IDs were exact.

The important contract subtlety is `is_argmax_invariant`. Declaring it true allowed greedy sampling to skip the processor, which is a valid optimization for a transform that cannot change argmax but surprising for an observer whose side effect is the evidence. Declaring false forced invocation while still returning logits unchanged. Production observational processors need an explicit execution contract rather than relying on mutation semantics.

The same zero-patch surface works on vLLM 0.26.0's V2 GPU runner. A 66-line observer emitted exactly 18 sequential rows, 18 repeat rows, and 33 rows for three pinned requests plus short and long decoys; real callback batch sizes were 1, 3, 4, and 5. `BatchUpdate` exposes row additions, removals, and moves but not request IDs, so the OpenAI `vllm_xargs` extension carried a caller-defined request identifier into `SamplingParams.extra_args`, and the processor maintained the row map through every batch mutation. No row was unattributed. Returning the logits unchanged was non-perturbing: the baseline and observed token hashes were identical.

Against the HF float32 oracle, the bfloat16 GPU mean/max absolute deltas were 0.0296103/0.105978 for entropy, 0.0555784/0.129305 for top-two margin, and 0.00759419/0.0235261 for top-one probability. Concurrent-versus-sequential deltas were nonzero because GPU batch shape changes numerics: mean/max 0.0108719/0.0321517 for entropy, 0.0347222/0.125 for margin, and 0.00511251/0.0288251 for top-one probability. One default-mode step had equal top-two bfloat16 logits: the observer's `torch.topk` reported the HF token `Italy`, while the sampler's tie resolution emitted `France`. GPU oracle checks must therefore align by finalized token and report tie-driven token divergence rather than assuming CPU float32 token identity.

## L2 route (a): general-plugin negative evidence

The `vllm.general_plugins` entry point was exercised in the API process, model-registry subprocess, engine core, and worker. Every callback was argument-free and ran before a model runner, input batch, or scheduler object existed. The worker invocation occurred during `init_worker`, before `CPUModelRunner.load_model`. The callback could register model classes and other global facilities, but it could not obtain the loaded model, register a post-load forward hook, observe per-step batch rows, or receive a stable request identity. Global monkey-patching from the callback would only disguise an unsupported core override and was not counted as a plugin success.

## L2 route (b): targeted patch and concurrency

The Phase 3 patch added 88 lines to two installed-package files with no repository fork. In `CPUModelRunner.load_model`, it registered a forward hook on `model.model.layers[14]`. Qwen3 returns the MLP contribution and residual separately, so the canonical post-block residual is `output[0] + output[1]`. The hook read the inherited V1 runner's private `input_batch.req_ids` and `num_scheduled_tokens` arrays, treated request rows as contiguous in that order, selected each request's cumulative last row, and computed the S4 dot product with float32 inputs and index-order double accumulation. The OTel helper joined the bounded records to the completed request and emitted the canonical children.

Sequential vLLM float32 versus HF float32 passed the strict 0.0001 tolerance with mean absolute probe delta 0.00000191625 and maximum 0.00000769890. With `max-num-seqs=2`, four interleavings paired the pinned prompt with `List three prime numbers:`. Every pinned six-step scalar was bit-identical to sequential execution: mean and maximum delta were exactly 0.0 in all four trials, and real two-request forwards were present.

The GPU port validated the concept on vLLM 0.26.0's V2 Model Runner, but not by applying the old patch verbatim. The original 88 additions were 45 CPU-runner lines plus 43 OTel-helper lines. With OTel already proved and out of GPU scope, the V2 numerical port required 41 additions and zero deletions in `vllm/v1/worker/gpu/model_runner.py`. V2 builds a local `InputBatch` per execution rather than retaining the old CPU runner's persistent mapping fields, so the patch added a one-line handoff to the hook, used `req_ids[i]` for identity, and selected `query_start_loc_np[i+1]-1` as request `i`'s last packed row. Sequential eager bfloat16 passed 18/18 against HF under tolerance 0.2 with mean/max absolute delta 0.0147260/0.0396061. The five-request decoy run emitted exactly 33 rows at batch sizes 1, 3, 4, and 5; pinned concurrent-versus-sequential mean/max deltas were 0.0160857/0.0531631.

The patch-maintenance conclusion is stronger, not weaker: private row surfaces changed materially between v0.23.0 V1 CPU and v0.26.0 V2 GPU even though the semantic probe did not. The V2 patch still depends on private runner timing, Qwen3's `output[0] + output[1]` return convention, the `model.model.layers[14]` path, internal request-ID prefixes, and eager execution. It is not validated for TP/PP, speculative decoding, disaggregated prefill/decode, the legacy v0.26.0 GPU runner, or multiple workers. Prefix caching remained enabled throughout the GPU oracle, concurrency, and benchmark runs and caused no observed blocker, but there was no dedicated cache-off or purpose-built cache-hit invariance cell. The JSONL channel remains a correctness oracle, not production IPC.

## GPU-supported SGLang activation path

SGLang 0.5.16's `--forward-hooks` option is a real supported hook-factory contract, not a stage-8 assumption. A mounted 68-line module registered a standard forward hook on `model.layers.14`; no installed SGLang source changed. With prefill and decode graph backends disabled and overlap scheduling disabled, the hook emitted exactly one scalar for every finalized token: three prefill observations that predict step 0 and fifteen decode observations for steps 1-5. HF float32 versus SGLang bfloat16 passed 18/18 under tolerance 0.2 with mean/max absolute delta 0.0140332/0.0298548. Mounting the module without `--forward-hooks` emitted zero scalars, and hook-disabled, hook-enabled sequential, and hook-enabled concurrent token hashes were identical.

SGLang exposes `rids[i]` and `req_pool_indices[i]` for each logical batch row. Five concurrent requests reached decode batch size 5; after the three-token decoy finished, the batch shrank to 4 and all three pinned requests shifted rows while their pool indices stayed stable. Attribution through the real row shift passed, all 18 pinned tokens remained exact, and concurrent-versus-sequential scalar mean/max deltas were 0.0138765/0.0389554. This establishes tolerance-based GPU concurrency invariance, not bitwise invariance.

Prefill is packed and uses different row math from decode. For request `i`, SGLang selected `extend_start_loc[i] + extend_seq_lens_cpu[i] - 1`, the last uncached/extended prompt-token row in the current forward; `rids[i]` and `req_pool_indices[i]` still name the logical request. Decode uses one row per active request. Prefill and decode records were explicitly labeled and never silently mixed. With the default overlap scheduler, a six-token request produced one prefill plus six decode callbacks because the scheduler computes one token ahead of API finalization. The strict oracle disabled overlap; production overlap requires joining candidates to scheduler finalization and discarding the final look-ahead record.

## Observation Plugin RFC gap analysis

The proposed vLLM Observation Plugin interface would eliminate most of the runner patch if decode observations are implemented. Its model-runner-owned hook and `LayerObservation` request/token offsets address the two failures of general plugins. The following five requirements are ready to post as upstream feedback:

1. Define a stable semantic observation point such as `post_decoder_block_residual`, not only an architecture-specific forward return.
2. Provide explicit request and token-row offsets for prefill and decode under chunking, prefix caching, speculative decoding, and disaggregated execution.
3. Provide a stable request/choice identifier shared with the server trace lifecycle, without internal-prefix parsing.
4. Expose a bounded observation handoff or active request context so scalar spans can be parented without patching tracing internals.
5. Specify tensor ownership, clone/copy behavior, callback timing, and lifetime so plugins can reduce immediately and never retain raw activations.

The RFC's initial prefill scope is insufficient for this per-generation-step probe; decode observation is mandatory. The GPU tier measured the eager-mode cost rather than leaving it hypothetical: exact residual observation reduced production-baseline decode throughput by 65.76% on SGLang and 66.85% on vLLM. A supported graph-aware decode observation path is therefore a performance requirement, not merely an API-cleanliness request.

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

## Stage-12 acceptance matrix

| # | Assertion | Status |
|---:|---|---|
| 1 | Valid agent W3C carrier | PASS — local |
| 2 | Server continues the agent trace | PASS — local |
| 3 | Context/request identity survives server process boundaries | PASS — local trace join; GPU request identity re-proved |
| 4 | Request-safe batching attribution | PASS — local + SGLang GPU + vLLM V2 GPU |
| 5 | Scalar emission without raw tensors | PASS — local + both GPU engines |
| 6 | Stable success/stream/cancel/timeout lifecycle | PASS — local |
| 7 | Deterministic parent-based sampling | PASS — local |
| 8 | No tracer-provider conflict | PASS — local |
| 9 | Raw/Logfire/Langfuse local contracts retain namespace | PASS — local |
| 10 | TP/PP/DP rank duplication controlled | DEFERRED — the campaign box had one L4; TP/PP were never attempted |
| 11 | No accidental content capture | PASS — local + scalar-only GPU evidence |
| 12 | Export failure isolated from inference | PASS — local |

The combined result is 11 pass, 0 fail, and 1 precisely scoped deferral. GPU execution re-proved the numerically and architecturally sensitive parts of assertions 3-5 and 11; it did not repeat the already-closed trace lifecycle, sampling, backend transport, or collector-outage tests. The process-boundary pass is functional: worker-produced scalars are correctly joined into the continued request trace locally, but vLLM 0.23.0 does not emit a standalone per-request worker span.

## P5 GPU execution result

The CUDA campaign defined by the [S3 plan](../../plan/S3-parametric-span.md) executed as four reviewed phases on one L4. The detailed phase reports (`PHASE1-REPORT.md` through `PHASE4-REPORT.md`) and pulled evidence remain spike artifacts under gitignored `ethical/xai/tmp/spikes/s3gpu/`; they are not committed documentation dependencies or links. The campaign verified the official SGLang hook surface and pins, eager oracle and row-shift attribution, CUDA-graph behavior and overhead, then the vLLM zero-patch logits path and V2 residual port. TP/PP were excluded because the host had one GPU. Speculative decoding was skipped by the reviewed Phase 4 bound.

The graph matrix establishes the same production constraint through different engine mechanisms. SGLang registers configured hooks only after CUDA-graph capture, so a Python hook is absent from captured graphs and fires only on eager forwards. Its three pinned requests produced 18 callbacks with both graph backends disabled, 15 when only prefill graphs were enabled, 3 when only decode graphs were enabled, and 0 under both defaults. The default captured decode maximum on the L4 was batch size 24; a size-25 decode fell back to eager and produced callbacks, which are partial fallback evidence rather than a complete observation stream. vLLM installs the V2 hook before profiling and capture, but its explicit full-graph replay and compiled piecewise paths still suppress the Python/file side effect; the pinned default run produced zero residual callbacks, while `--enforce-eager --no-async-scheduling` produced all 18. Neither engine may interpret a missing graph-replay callback as a zero-valued observation.

The cost decomposition used the same 32-request, approximately 128-token-prompt, 64-output-token, concurrency-8 corpus with warmup and two repetitions. SGLang production default delivered 1,127.64 decode tokens/s and exact eager observation delivered 386.11, a 65.76% reduction. Disabling graphs plus overlap accounted for a 61.84% reduction; adding the scalar hook to the matched eager configuration cost a further 10.27%. vLLM production default delivered 1,108.36 tokens/s and exact eager observation delivered 367.39, a 66.85% reduction. Its matched eager/no-async baseline was 401.50, so the scalar patch cost 8.50% and disabling production graph/scheduler optimizations dominated. vLLM zero-patch logits observation retained graphs and async scheduling, delivered 853.92 tokens/s, and cost 22.96% versus its production baseline. These are correctness-first synchronous scalar/JSONL measurements, not optimized exporter ceilings.

The operational recommendation is consequently asymmetric. Full-logit processors are the always-on channel where their approximately 23% reference overhead is acceptable and can be optimized without changing engine execution mode. Exact residual probes should be an explicitly enabled eager diagnostic with a bounded duration and cardinality budget until SGLang or vLLM provides a graph-aware semantic activation interface. Any production adapter must join overlap/look-ahead candidates to finalized tokens, keep request identity explicit, align oracle comparisons by token, and emit only bounded scalars.

## Open items for the F ADR

- Use SGLang's supported `--forward-hooks` path as the first residual backend. If vLLM residual support ships before the Observation Plugin, treat its pinned 41-line V2 runner patch as an opt-in diagnostic adapter with explicit version ownership, not as a generally portable integration.
- Decide per-token child spans versus one per-request aggregate, with an explicit cardinality and export budget.
- Require a stable semantic residual point, request/choice identity, decode row map, graph-aware execution contract, and exactly-once finalization callback in any supported engine adapter.
- Replace file IPC and request-prefix joins with a bounded in-process or engine-owned scalar channel; raw tensors must never cross the boundary.
- Define loss-tolerant exporter behavior and observability for dropped scalar spans without coupling inference success to telemetry success.
- Hold TP/PP/DP cardinality and speculative decoding as remaining release gates. V2/GPU numerical correctness, CUDA-graph behavior, prefix-caching-enabled operation, and reference overhead are now measured; a dedicated prefix-cache-hit gate remains optional hardening.
- Make GPU acceptance token-aware and tolerance-based. Bfloat16 ties can change finalized tokens, and correct continuous-batch attribution does not imply bitwise scalar invariance.
- Keep hosted Logfire/Langfuse rendering/query validation as optional deployment certification; the core contract is ordinary OTLP and must not require backend SDK types.
