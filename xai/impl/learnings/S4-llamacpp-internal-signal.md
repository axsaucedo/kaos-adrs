# S4: llama.cpp internal signal learnings

## Outcome

S4 established a working llama.cpp L1 and residual-signal path, verified it against the S3 Hugging Face implementation, exercised CPU batching and Metal, emitted the canonical bounded OpenTelemetry evidence span, and measured the packaging gap in stock `llama-server`. The recommended near-term integration is a thin custom libllama host for L1 plus bounded internal probes. A stock-server sidecar remains useful for L0 request and timing evidence but cannot recover residuals. A small upstream callback-plugin hook is technically feasible and is the preferred long-term route if llama.cpp maintainers accept the extension point.

The authoritative scope and verification loops are in the [S4 plan](../../plan/S4-llamacpp-internal-signal.md). The telemetry contract follows the [OpenTelemetry propagation and transport research](../../research/12-otel-propagation-and-transport.md), and the callback and zero-touch alternatives are framed by the [engine introspection and eBPF research](../../research/8-support-engine-introspection-and-ebpf.md).

## Reproducible pins

The work used llama.cpp release tag `b10217` at commit `ddd4ec1428a6201e18975ea52b07c71e0f9aef26`, resolved on 2026-08-01. The CPU target was an unstripped arm64 `RelWithDebInfo` static build with debug symbols, `GGML_METAL=OFF`, `GGML_BLAS=OFF`, `GGML_ACCELERATE=OFF`, `GGML_NATIVE=ON`, and `GGML_LTO=OFF`. The separate Metal target changed only the Metal configuration and embedded the Metal library.

The model was the official `ggml-org/Qwen3-0.6B-GGUF/Qwen3-0.6B-f16.gguf` at repository revision `b5f37287796e5be0ea3dab2e7430873fb3f73e49`, SHA-256 `ab9004daf660cd6a6ba1c07556e74fcceb2b756063ccce3f9c69d3a637b361cc`. All comparisons used the three pinned prompts and greedy generation.

## L1 channel and runtime census

The host submits explicit `llama_batch` values and reads each requested full-vocabulary row with `llama_get_logits_ith`. It computes stable full-vocabulary entropy, top-two logit margin, and top-one probability before emitting one JSON record per generated token. Two CPU runs were byte-identical, every argmax token matched the generated token, and all sanity bounds passed.

The `cb_eval` census for the first prompt's five-token prefill observed 986 offered graph nodes and selected all 986 exactly once. It contained 706 unique names, no unnamed events, 818 `f32` tensors, 168 `f16` tensors, and CPU host buffers throughout. Static candidates were all present: `ffn_inp-0` through `ffn_inp-27`, `ffn_out-0` through `ffn_out-27`, `l_out-0` through `l_out-27`, `result_norm`, and `result_output`. The notable divergence from a name-only static reading was shape: layers 0 through 26 retained `[1024, 5]`, while final-layer `l_out-27` and `result_norm` had already gathered the requested output row to `[1024]`; `result_output` was `[151936]`.

Qwen3-0.6B has layers 0 through 27. S4 defines its probe boundary as `l_out-14`, the upper-middle post-MLP residual addition and input to layer 15. On prefill it is an `f32` `ADD` tensor with shape `[1024, token_rows]`; on one-token decode it is `[1024]`. This is an implementation convention tied to the pinned architecture and llama.cpp graph naming, not a portable semantic identifier.

The unit probe vector is `numpy.random.default_rng(20260801).standard_normal(1024).astype(float32)`, divided by `numpy.linalg.norm`, then cast and saved as little-endian float32. Its SHA-256 is `be20dfa1bd53444ff4d6f5fd840586659b59355b0de850ca94e091bec56a9843`. The host copies the selected row through `ggml_backend_tensor_get` and accumulates the dot product in double precision over float32 inputs.

## Accounting and non-perturbation

Callback count is not token count. The host creates a decode epoch before every `llama_decode`, stores sequence and submitted-row metadata in `cb_eval_user_data`, and keys a capture by `(decode_epoch, seq_id, token_position, tensor_name)`. In single-sequence mode each decode offered 986 tensors, selected `l_out-14` once, and produced exactly one observation. Across 24 generated steps, two independent oracle and accounting runs were byte-identical.

The complete 24-step L1 output was byte-identical across the Phase 1 baseline, the extended host with no callback, two callback-enabled runs, the Phase 3 oracle run, the default pause-disabled run, and an explicit `--pause-before-decode 0` run. The baseline SHA-256 was `a7c041fd189270a396b1b5a110ebed4648fe6c10543b93e2d25dd5fac121aaab`. This establishes non-perturbation for the tested CPU configuration.

## Batching and sequence attribution

One logical `llama_batch` interleaved four sequences by position, using sequence IDs `0`, `2`, `4`, and `6`. The host-owned map connected each submitted `seq_id`, position, and logit-request bit to the physical tensor row produced by llama.cpp's sequential scheduler. Prefill retained multiple rows per physical sequence, so the selected row was that sequence's requested final prompt position rather than the interleaved submitted batch index. Later one-token decodes produced shape `[1024]`, making the physical row zero while attribution still came from the map.

Contiguous sequence IDs `0`, `1`, `2`, and `3` caused equal-length pieces to be packed into multi-column physical graph batches. That valid packing changed CPU reduction shape and introduced small floating-point differences from isolated single-sequence runs. Non-consecutive IDs forced one physical sequence group per ID and produced exact equality for all 32 residual vectors, probe scalars, generated tokens, and L1 rows against the single-sequence references. This is a reproducibility configuration, not necessarily the throughput-optimal production choice. In this mode one logical epoch produced four physical target observations and 4,168 `ask=true` calls.

## Metal

All 24 Metal `l_out-14` captures reported buffer type `MTL0` and `ggml_backend_buffer_is_host=false`. Apple unified memory therefore does not permit treating the graph tensor as a public host pointer; `ggml_backend_tensor_get` remains the required portable read path. The copy-call timing for a 4 KiB row was 1.1545 microseconds mean and 1.417 microseconds p95, with a 6.458 microseconds maximum. These values exclude the scheduler synchronization performed before the `ask=false` callback and must not be interpreted as total instrumentation overhead.

All 24 Metal tokens matched CPU. Metal versus CPU mean and maximum absolute deltas were `0.00421195 / 0.04723740` for residual elements, `0.00492183 / 0.01580429` for probe scalars, `0.00468152 / 0.01822536` for entropy, `0.01056055 / 0.02967834` for margin, and `0.00109239 / 0.00400094` for top-one probability; all declared tolerances passed.

## Cross-engine results

For the 18 steps shared with S3, all greedy token IDs matched. Hugging Face eager float32 versus llama.cpp F16 GGUF mean and maximum absolute deltas were `0.00488185 / 0.02009540` nats for entropy, `0.01020416 / 0.02972221` for top-two margin, and `0.00122996 / 0.00397654` for top-one probability. All were below the declared S4 tolerances.

S3 subsequently adopted S4's exact probe vector and residual-boundary convention. Its aligned comparison passed all 18 probe values with mean absolute delta `0.00548175` and maximum absolute delta `0.01581758`, below the declared `0.2` tolerance. This closes the aligned cross-engine probe gate while retaining the expected HF float32 versus GGUF F16 numerical drift.

## S5 oracle identity

The macOS CPU oracle contains 24 records, one for each of three prompts and eight steps, with `decode_epoch`, `seq_id`, `tensor_name`, process-relative `data_ptr`, first eight floats, and probe scalar. The exact executable is `/Users/asaucedo/Programming/ethical/xai/tmp/spikes/s4/build-cpu/s4_l1_host`, SHA-256 `913635fa76c1f5c9e2b33901cd1070466b101b8b86338bcf18548537ca8b7064`, with 3,884 global symbols. Its dSYM UUID is `B2C6051B-8C7F-304B-ABA5-911A5E3FBCEB`. `--pause-before-decode` defaults to zero and exists only to give S5 an attach window. ASLR makes saved pointers process-relative, and the Mach-O executable cannot be uprobed inside the Linux S5 environment; S5 must rebuild the portable host at the same llama.cpp pin and generate a Linux-native oracle.

## OpenTelemetry result

Phase 4 used a Python OpenAI-compatible `/v1/completions` sidecar around the exact Phase 3 CPU binary. This avoided changing the S5 target. The sidecar extracts inbound W3C `traceparent`, invokes the host through subprocess stdio, aggregates eight token rows, and creates telemetry only after the callback-owned files have been consumed. The request-level probe score is the arithmetic mean of the eight `l_out-14` token scalars; entropy p95 uses nearest rank. Both choices are encoded in probe name/version and implementation documentation.

The collector file export mechanically proved one shared trace with `s4-agent` `agent.openai.request` as a CLIENT span, `s4-host` `inference Qwen3-0.6B` as its direct INTERNAL child, and exactly one `xai.parametric.observe` INTERNAL child. The observe span used instrumentation scope `org.ethicalai.xai.parametric` and 16 bounded scalar or identity attributes. It included model and probe identity, layer 14, token count, probe score, entropy mean and p95, margin mean, and affirmative negative controls `raw_activations_exported=false`, `raw_logits_exported=false`, and `content_included=false`. No prompt, completion, activation, or logit value was attached to the span. The host binary SHA-256 remained unchanged after the endpoint run.

## Stock llama-server gap and patch assessment

Stock `llama-server` does not expose the callback fields even though `common_params` already carries them into `llama_context_params`. The S4 clone-side proof added `--eval-callback-plugin PATH`, a versioned C factory struct, `dlopen` or `LoadLibrary` lifecycle management, and assignment to the existing callback fields. It changed 96 lines total: 95 insertions and one deletion across five files. A clean CPU `llama-server` build passed, and generated help contained the new option. The proof diff and upstream-style design note remain spike artifacts; no fork, commit, issue, pull request, or upstream communication was created.

The proposal requires trusted native plugin paths, fatal load and ABI validation before model creation, no hot reload, safe destructor ordering, and an explicit warning that callbacks execute on the inference path. Plugins must cheaply reject most of the 986 offers, use backend copies, keep raw tensors out of telemetry, and move export work to a host-owned registry. A real upstream discussion must decide whether this extension point belongs in the server or an embedding example and must add cross-platform and router-child tests.

## Packaging verdict

The thin custom host is the recommended xai integration now. It is the only tested path that preserves full L1 logits, stable residual selection, explicit batch attribution, exactly-once accounting, Metal-safe copies, and host-controlled privacy and telemetry boundaries. Its cost is owning a small serving surface and tracking llama.cpp graph-name changes at pinned upgrades.

A sidecar around unmodified `llama-server` is operationally simplest but supports only L0 request, response, timing, token-count, and any public logprob evidence. It cannot access `l_out-14`, cannot reproduce the aligned probe, and cannot honestly emit the parametric residual claim. Use it only when L0 is the declared capability.

The upstream plugin path can combine stock server behavior with internal access and is the preferred long-term packaging direction, but it is not an available dependency until maintainers accept and stabilize an ABI. xai should keep the custom host as the reference and validation oracle, pursue the small extension point through normal human-led upstream discussion, and avoid a long-lived server fork.

## Open items for the F ADR

- Define capability tiers explicitly: stock sidecar as L0, public logits as L1 where available, and callback-backed bounded residual probes as the internal tier.
- Decide whether the production contract pins llama.cpp tag, model revision, tensor name, shape, dtype, probe bytes, accumulation order, and aggregation rule as one versioned probe identity.
- Choose throughput versus bitwise reproducibility for multi-sequence serving; contiguous sequence IDs are valid but should not promise isolated-run equality.
- Set a Metal synchronization and callback-overhead budget using end-to-end decode timing, not only the post-synchronization 4 KiB copy timing.
- Decide the upgrade gate for runtime census divergence and whether missing or reshaped `l_out-14` disables the probe rather than falling back silently.
- Make raw activation, raw logit, and content non-export enforceable policy and retain only bounded request-level scalars in telemetry.
- Record the upstream decision and fallback: accepted plugin ABI, custom-host ownership, or explicit L0-only stock-server support; do not normalize a private server fork as the default.
- Incorporate S5's Linux-native oracle and eBPF results, including cross-OS drift and symbol/build-identity requirements, before deciding whether zero-touch recovery is a supported path or only a diagnostic technique.
