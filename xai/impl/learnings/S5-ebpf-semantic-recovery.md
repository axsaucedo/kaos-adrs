# S5: eBPF semantic recovery learnings

## Outcome

S5 established the final zero-touch llama.cpp observation ladder across CPU and GPU. On CPU, Linux uprobes recovered decode cost and batch identity, walked the ggml graph with a 100% semantic census, read the selected residual row at a validated post-compute boundary, reproduced every tested float and probe scalar bit-for-bit, adapted across a release, architecture, and quantization without tool code changes, and emitted bounded cost and parametric evidence in one trace. On GPU, CUPTI environment-variable injection recovered request-correlated kernel cost without an inference-engine patch, and eBPF still recovered host-resident graph structure, but exact activation values stopped at the CUDA device-memory boundary. The final ladder is therefore T0/T1 CPU cost plus CUPTI GPU cost zero-touch; T2 structure zero-touch on both CPU and GPU; T3 exact values zero-touch on CPU only, with GPU exact values requiring cooperation in the owning CUDA context. The result supports constrained product capabilities for pinned self-hosted llama.cpp deployments and remains complementary to the S3/S4 in-process path, not a generic replacement.

The authoritative scope, pinning ladder, and verification loops are in the [S5 plan](../../plan/S5-ebpf-semantic-recovery.md). The capability boundary and the GPU questions resolved here follow the [engine introspection and eBPF research](../../research/8-support-engine-introspection-and-ebpf.md).

## Environment: Docker Desktop was not enough

The macOS host was an M1 Max, so eBPF had to run in a Linux VM. Docker Desktop's arm64 LinuxKit kernel `6.10.14-linuxkit` exposed `/sys/kernel/btf/vmlinux` and ran a basic bpftrace `BEGIN` program, but a real test-binary uprobe failed during `perf_event_open` with an I/O error. BTF visibility alone was therefore not a sufficient workbench test.

The fail-fast switch to Colima succeeded on Ubuntu 24.04.1 arm64 with kernel `6.8.0-50-generic`, readable BTF, bpftrace 0.20.2, and an unstripped test binary that received exactly five of five uprobe calls. Phase 1 initially used the default 2 GiB profile and had to stop K3s under model memory pressure. Phase 2 created a dedicated `s5` profile with four CPUs and 8 GiB, isolating the spike from K3s and leaving 7.7 GiB visible to the guest. The product lesson is to gate on an actual uprobe, not kernel version or BTF presence, and to describe Docker Desktop LinuxKit as unsupported for this tested path.

BCC was installed and attempted in the dedicated VM, but the Colima kernel had no matching `/lib/modules/6.8.0-50-generic/build`, no installable matching header package, and no `kheaders` module. BCC could not compile its BPF module. bpftrace completed T0 through T4; a production high-rate reader should prefer a prebuilt libbpf CO-RE object against available BTF rather than depend on guest kernel headers.

## Pins and model correction

The llama.cpp baseline was release `b10217`, commit `ddd4ec1428a6201e18975ea52b07c71e0f9aef26`. The Linux S4 harness was built inside Colima as an arm64 static CPU `RelWithDebInfo` executable with `-O2 -g -fno-omit-frame-pointer`, debug info, symbols, and frame pointers. The Phase 3 census-equivalent oracle option changed the scratch harness build ID to `486e859b383d07dc0b67134fe993ce84b3e21002`; llama.cpp itself was not patched.

Phase 1 used a community `SaisExperiments/Qwen3-0.6B-F16-GGUF` file, SHA-256 `9fc17fc9e12dc119c771ddcfb376d965af8b014b78a8a2d2723350cc4f8346ba`, after incorrectly concluding that the official ggml-org repository lacked F16. Phase 2 corrected the pin to `ggml-org/Qwen3-0.6B-GGUF/Qwen3-0.6B-f16.gguf` at revision `b5f37287796e5be0ea3dab2e7430873fb3f73e49`, SHA-256 `ab9004daf660cd6a6ba1c07556e74fcceb2b756063ccce3f9c69d3a637b361cc`. Phase 1 cost results remain explicitly labeled as community-model results; Phase 2 onward used the S4-aligned official file.

The S4 probe vector remained the 4,096-byte normalized float32 vector with SHA-256 `be20dfa1bd53444ff4d6f5fd840586659b59355b0de850ca94e091bec56a9843`.

## T0 and T1: the cost channel

T0 attached a uprobe and uretprobe to `llama_decode`, stored entry time by TID, and emitted every call duration. Each Phase 1 request contained one chat-templated prefill plus fifteen one-token decode calls, with one separate two-token CLI initialization call excluded from the request distribution. The eBPF request sums were 3,947.022 ms, 5,482.402 ms, and 5,559.671 ms for the three pinned prompts. Reconstruction from the process's own reported prompt and generation rates differed by 0.79%, 0.33%, and 0.07% respectively. Whole-process wall time was not useful as a compute truth because SSHFS model loading, page residency, and the initial 2 GiB memory pressure dominated it.

T1 read `llama_batch` through the public API argument. On arm64 the by-value 56-byte batch is passed indirectly, making `arg1` the address of the caller's copy. The initial reads recovered `n_tokens` coherently on every call. The completed multi-sequence run used generated offsets `pos=24`, `n_seq_id=32`, and `seq_id=40`, then recovered all 28 expected rows from a position-major interleaving of sequence IDs `0`, `2`, `4`, and `6`. Prefill had 24 rows with lengths `5`, `4`, `10`, and `5`; the next generation batch was exactly `(pos, seq_id) = (5,0), (4,2), (10,4), (5,6)`.

The cost readings were converted to `xai.cost.observe` internal spans with `xai.cost.source=ebpf.uprobe`, `xai.cost.zero_touch_readings=true`, per-call batch token counts, duration, and no content. T0/T1 are the broadly useful rung: they need public symbol and struct knowledge but no graph semantics.

The spike did not establish a trustworthy steady-state overhead percentage. Phase 1 compared single cold/warm runs under memory and page-cache noise, while later full-row bpftrace emission was intentionally inefficient. A supported capability needs alternating attached/unattached resident-model trials.

## DWARF and build identity

The layout pipeline uses pahole against the exact unstripped target, with a tested streaming `readelf --debug-dump=info` fallback. It records the ELF build ID and target SHA-256, rejects missing required fields, and writes JSON constants keyed to the build. The b10217 harness layout was `ggml_tensor` size 336 with `ne=16`, `nb=48`, `op=80`, `data=248`, and 64-byte `name=256`; `ggml_cgraph` size 96 with `n_nodes=4` and `nodes=16`; `llama_batch` size 56 with `n_tokens=0`, `pos=24`, `n_seq_id=32`, and `seq_id=40`.

The supported attach wrapper verifies the target ELF build ID, layout-file build ID, and generated-program build ID before invoking bpftrace. Crossed b10217/b10218 artifacts were refused before attach. Direct bpftrace invocation can bypass this policy and is not the supported path.

This separation is central to maintainability: struct offsets are generated deployment data, not constants in reader code. A stripped production binary can still be supported only if its exact build ID matches a trusted offset record generated from an equivalent debug build.

## T2: exact semantic skeleton

The backend wrapper symbols existed but were not executed by the statically linked CPU harness. Boundary counts showed three `llama_decode` and three `ggml_graph_compute` hits but zero `ggml_backend_graph_compute` or async wrapper hits, so the allowed CPU fallback was required.

The generated T2 bpftrace program walked the `ggml_cgraph.nodes` array with user-memory reads and emitted tensor name, numeric op, and all four dimensions under an explicit node bound. Against the Linux harness's in-process `--census` truth, it matched all 986 Qwen nodes positionally by name and shape, with no missing, extra, or truncated events. All 28 `l_out-*`, 28 `ffn_inp-*`, and 28 `ffn_out-*` names were present. A normal three-prompt capture emitted 18,316 node events across 47 compute calls without truncation.

The Linux S4 oracle contained 24 `l_out-14` records. Comparing it with the macOS oracle produced 192/192 exact first-eight floats and 24/24 exact probe scalars with zero observed cross-OS/toolchain drift. ASLR-dependent data pointers were excluded.

## T3: exact external values

T3 stashed the selected `ggml_tensor *` in a TID-keyed map at `ggml_graph_compute` entry and read it at the matching uretprobe. It derived the last-token row as `(ne[1] - 1) * nb[1]`, read `tensor->data`, and emitted each f32 value as its raw 32-bit representation. `llama_decode` entry supplied decode epoch, first sequence ID, token count, and start time, so records were keyed by `(decode_epoch, seq_id, tensor_name)` and could also carry T0/T1 cost.

The primary census-equivalent run used one-node scheduling while the same process wrote its in-process oracle. All 24 identities, 192 first-eight values, 24 complete 1,024-float rows, 24,576 individual float bits, and 24 external probe scalars matched exactly. The normal multi-node run produced the same exact result.

In normal mode `l_out-14` was node 525 of 526, the final indexed graph node. Reading at graph-compute return therefore occurred before any later node in that graph could reuse the selected buffer. Data pointers were reused across decode epochs, but each epoch's content was exact. This does not prove safe timing for earlier graph nodes; the within-graph buffer-reuse race remains a required per-role gate.

The kernel verifier rejected a 1,024-node scan combined with name comparison because the jump sequence became too complex. A bound of 600 loaded and covered the tested 526-node graph. The map must carry this bound and a deployment must fail closed when its graph exceeds it.

The first full normal run used bpftrace's default 64 perf-ring pages and emitted only 19,775 of 24,576 values. Every emitted value and every first-eight group was correct, identifying transport pressure rather than tensor corruption. Setting `BPFTRACE_PERF_RB_PAGES=1024` recovered all values. One `printf` event per float was acceptable for proof but should become bounded structured row chunks with explicit loss counters.

The optimized harness accumulated the scalar with arm64 fused double multiply-add. A Python multiply followed by addition differed by one binary64 unit. The external validator mirrored the executable with sequential libc `fma(double(weight), double(value), accumulator)` and then matched every oracle scalar exactly. Exact comparison requires pinning accumulation semantics, not merely saying “double precision.”

## Brittleness results

| Axis | Change | T2 | T3 | Classification | Tool code changes |
|---|---|---:|---:|---|---:|
| Version | b10217 to latest available b10218 | 986/986 | 3,072/3,072 values, 3/3 scalars | needs-map-regen | 0 |
| Architecture | Qwen3-0.6B to Llama-3.2-1B | 502/502 | 6,144/6,144 values, 3/3 scalars | needs-map-regen | 0 |
| Quantization | Qwen F16 to Q8_0 | 986/986 | 3,072/3,072 values, 3/3 scalars | works-unchanged | 0 |

The official tag query found only b10218 beyond b10217, so the version result is a one-release sample rather than the requested wider jump. The build ID changed and therefore required regeneration, but every required offset, structure size, and Qwen name/shape remained unchanged. Fresh layout regeneration plus the complete map-driven gate took 46.929 measured automation seconds after the unstripped binary existed; fresh compilation and human approval were excluded.

The architecture axis used the official ggml-org-hosted `Llama-3.2-1B-Instruct-Q4_K_M.gguf` at repository revision `5390c7c41cbd6f261f7f205fc0c5ae61bbdca650`, SHA-256 `6f85a640a97cf2bf5b8e764087b1e83da0fdb51d7c9fab7d0fece9385611df83`. The same `l_out-*`, `ffn_inp-*`, and `ffn_out-*` conventions appeared for all 16 layers. Map data changed the midpoint target from layer 14 to layer 8 and width from 1,024 to 2,048. All selected-family activations remained f32.

The Q8_0 file was pinned to the same official Qwen revision with SHA-256 `361cc68159042c36ebff7715dc5a2e4612153e88f3e9c9c234820849d6dc9e1d`. Its complete 986-entry name/shape sequence matched F16, all 84 target-family activations remained f32, and no map value or tool code changed.

## T4 map and regeneration cost

The T4 `arch-map.json` separates architecture semantics from deployment and build layout. Architecture data defines family, role, `l_out-{layer}` convention, midpoint-floor layer policy, f32 dtype, and the `uretprobe:ggml_graph_compute` lifetime requirement. Deployment data defines llama.cpp tag, build ID, target path, model revision and SHA, layer count, width, probe SHA, graph bound, and perf-ring pages. Offsets remain exclusively in the build-ID layout file.

The map covers Qwen3 b10217 F16, Qwen3 b10217 Q8_0, Qwen3 b10218 F16, and Llama-3.2 b10217 Q4_K_M. A single host command accepts map, case key, layout, and output directory, enters the dedicated VM, verifies hashes and identities, emits T2/T3 programs, runs both truths, and writes exact validation.

The final Qwen one-command proof matched 986/986 census nodes and 3,072/3,072 values in 51.271 seconds: 14.970 seconds for hash validation and generation, then 36.301 seconds for both gates. The final Llama proof matched 502/502 nodes and 6,144/6,144 values in 30.840 seconds: 5.384 seconds generation and 25.456 seconds gates.

New architecture onboarding is three human steps: pin and inspect one representative census, add one architecture/deployment entry plus probe data, then run and approve the exact gate. Automation after entry authoring measured 30.840 seconds for Llama; model download and human semantic approval were excluded. New release onboarding is also three steps: build the unstripped pin, regenerate layout and deployment data, then run and approve the gate. Automation after build measured 46.929 seconds for b10218; clean compilation and review were excluded. Both paths required zero reader code changes.

## Merged zero-touch trace

The final Qwen run emitted cost and value readings from the same generated eBPF program. For decode epoch zero and sequence zero it observed five batch tokens, 151,025 microseconds of decode time, and an external `l_out-14` scalar of `0.3908777477007417`.

The file exporter produced one trace with a logical `chat` CLIENT span, an `inference` INTERNAL span, and sibling `xai.cost.observe` and `xai.parametric.observe` INTERNAL children. The cost span carried `xai.cost.source=ebpf.uprobe`, zero-touch status, decode duration, batch count, and sequence ID. The parametric span used the canonical evidence schema, model/probe identity, layer and token index, score, `xai.parametric.source=ebpf.uprobe`, and affirmative false controls for claimed chain-of-thought faithfulness, engine cooperation requirement, inference-engine patching, raw activations, raw logits, and content.

The evidence spans contained no `gen_ai.usage.*`, activation row, logits, prompt, or completion. Mechanical validation passed one-trace identity, parentage, unique span IDs, canonical sources, bounded payload, and negative controls. The trace used deterministic offline parentage because no real inbound traceparent was retained; a serving wrapper must map W3C context to PID, decode epoch, and sequence ID.

The scratch in-process callback existed only as exact validation truth. The eBPF reader neither called nor consumed it, normal scheduling also matched exactly, and llama.cpp inference-engine source was not patched.

## GPU tier: CUPTI cost and semantic-recovery ceiling

The GPU tier reused llama.cpp `b10217` at commit `ddd4ec1428a6201e18975ea52b07c71e0f9aef26`, the official Qwen3 F16 model and probe pins above, and an unstripped x86_64 CUDA `RelWithDebInfo` build on an NVIDIA L4 with driver 595.71.05 and CUDA 13.2. The server offloaded all 29 layers and used CUDA model, KV, and compute buffers. llama.cpp source remained unchanged; the phase evidence remains in the gitignored `tmp/spikes/s5gpu/` spike directory rather than this documentation repository.

### CUPTI zero-touch GPU cost

A small shared library exported `InitializeInjection`, enabled CUPTI concurrent-kernel and memcpy Activity API records, and was loaded through `CUDA_INJECTION64_PATH`. This is environment-variable injection into an unmodified server binary, not an inference-engine source patch. CUPTI timestamps were calibrated to `CLOCK_MONOTONIC`; bpftrace uprobes supplied `llama_decode` entry and return timestamps, and the client supplied monotonic request boundaries.

The three pinned greedy requests each produced six `llama_decode` calls, 2,658 kernels, and one observed kernel stream. Their summed GPU kernel times were 32.650 ms, 32.622 ms, and 32.736 ms. Per-decode activity was deterministic in this run: the prefill interval contained 533 kernels and each of the following five generation intervals contained 425, with kernel-time sequences of `5.793, 5.412, 5.364, 5.359, 5.360, 5.362` ms, `5.766, 5.415, 5.359, 5.361, 5.361, 5.360` ms, and `5.886, 5.413, 5.360, 5.358, 5.361, 5.358` ms. Baseline and injected output text matched exactly.

Attribution confidence is high only for the measured shape: one PID, one active slot, sequential requests, and one kernel stream. The unmodified server exposes no request ID in CUPTI records, so time-plus-stream attribution becomes ambiguous with overlapping requests, multiple streams, continuous batching, or multiple GPUs. CUPTI correlation IDs identify CUDA launches rather than llama.cpp requests; shared work would need an explicit allocation model or a cooperative request marker.

The CPU-vs-GPU accounting gap was material. CUPTI-injected `llama_decode` entry-to-return sums were 18.928 ms, 11.644 ms, and 14.556 ms per request, all below the corresponding 32.650 ms, 32.622 ms, and 32.736 ms GPU kernel sums because `llama_decode` returns after asynchronous submission. A uretprobe under CUDA therefore measures synchronous host submission, not completed GPU execution. In one baseline pass followed by one injected pass on a resident model, summed eBPF entry-to-return time increased 28.82%, client request wall time increased 5.08%, and llama.cpp-reported prompt-plus-generation time increased 5.54%. The approximately 5% end-to-end result is directional; it is not a steady-state support limit without alternating repetitions.

### T2 survives CUDA, but graph position does not

Fresh `pahole` output from the CUDA build reproduced the relevant b10217 layouts: `ggml_tensor` size 336 with `ne=16`, `nb=48`, `op=80`, `data=248`, `name=256`, and `buffer=8`; `ggml_cgraph` size 96 with `n_nodes=4` and `nodes=16`. A walker attached to `ggml_backend_graph_compute_async` enumerated every backend-scheduled graph node for one prefill and one decode call. Each decode exposed split graph sizes 1 and 985, totaling the server's logged 986 nodes, and the capture emitted all 1,972 expected node records without truncation or transport loss.

`l_out-14` remained enumerable in host-resident metadata at node 524 of the 985-node split. Its shapes were `1024 x 5 x 1 x 1` during prefill and `1024 x 1 x 1 x 1` during decode. This proves that T2 semantic structure survives CUDA, but not that CPU graph maps are portable: CPU normal scheduling placed `l_out-14` at node 525 of a 526-node graph, while the CUDA server exposed backend-split graphs with different positions and cardinality. GPU maps must include backend schedule and graph-bound identity and fail closed when either changes.

### T3 stops at CUDA device memory

Exact zero-touch GPU value recovery failed for a precise mechanism, not an unresolved implementation bug. The full evidence chain was:

1. The server offloaded 29/29 layers and placed `l_out-14` in the large accelerator split.
2. `l_out-14->data` was `0x78a5ba000000`, inside a `78a5b9e00000-78a5ca000000 ---p` CUDA unified-virtual-address reservation rather than ordinary host or pinned-host tensor storage.
3. A root `/proc/<pid>/mem` read at that address returned success and 16 zero bytes. Those zeros were not the activation: CPU page tables did not expose the device allocation. This is a fail-closed hazard because a device read can look superficially successful.
4. The pinned llama.cpp CUDA source uses device allocation for ordinary CUDA buffers, defines pinned host memory as a distinct buffer type, and performs D2H through the backend `get_tensor` path with `cudaMemcpyAsync` and synchronization in the owning process and context.
5. CUPTI observed six 607,744-byte D2H output/logit copies per request and prompt-cache KV traffic at later request transitions, but no D2H pattern staging `l_out-14`; the 4,096-byte copies present were H2D.
6. CUDA IPC is cooperative: the allocation owner must export a memory handle before another process can import it. An unrelated CUDA context cannot make a raw UVA number readable.

No valid activation row existed from which to compute the pinned index-order double probe scalar, and treating the `/proc` zeros as values would have created false evidence. The demonstrated ceiling is therefore host-resident T2 semantics plus CUPTI cost under zero-touch observation; exact device values require execution in the owning CUDA context at a scheduler-approved lifetime boundary.

The minimum reliable assist is an opt-in target-tensor callback in the llama.cpp backend scheduler: select a name such as `l_out-14` through deployment configuration, synchronize at the approved post-compute boundary, use the existing backend tensor-get path to copy only the selected last-token f32 row, and expose either that bounded row or the final scalar. An environment variable alone does not provide this today; implementing the callback is engine cooperation. The proven S4 `cb_eval` path is the preferred production route because it already owns scheduler timing, backend-safe copying, request context, and lifecycle. A CUDA-aware in-process preload helper remains a separate unproven option rather than part of the S5 result.

## Verdict

T4 is a viable but narrow xai capability on CPU: offer opt-in zero-touch exact internal signals for pinned self-hosted CPU llama.cpp on Linux when patching or replacing the server is undesirable, with signed allowlisted maps, exact build-ID checks, and fail-closed preflight gates. On GPU, offer two narrower zero-touch capabilities: CUPTI request-correlated kernel cost for supported sequential attribution shapes, and host-resident T2 graph structure with backend-specific maps. Do not advertise generic semantic recovery across arbitrary engines or accelerators, and do not describe GPU exact values as zero-touch.

The CPU result is more than a research trick because value recovery, cross-architecture mapping, release regeneration, quantization stability, and canonical trace export all passed without reader changes. The GPU phase sharpened rather than extended that claim: cost and semantic structure survived, while exact values hit the owning-context boundary. The combined capability remains constrained by Linux privilege, binary/debug identity, verifier bounds, transport sizing, tensor lifetime, request correlation, backend-specific graph schedules, and narrow CPU and GPU evidence matrices.

S4's cooperation path remains preferable when xai controls the deployment and is required for exact GPU activation values. Its proof exposed existing `cb_eval` plumbing through a 96-line llama-server plugin patch and gains scheduler-approved timing, request context, lifecycle ownership, backend-safe tensor copies, and a plausible Metal path. A small explicit ABI is less fragile than reverse-engineered process memory and is the minimum reliable bridge across device memory.

S5 is worth the fragility when the deployment is a pinned llama.cpp appliance or fleet, rebuilding is prohibited or operationally undesirable, privileged observation is acceptable, and cost or structural evidence has enough audit, forensic, diagnostic, or edge value to justify maintaining a compatibility database. Exact zero-touch values additionally require CPU-resident tensors. When those conditions do not hold, use S4 cooperation; when GPU cooperation is unavailable, report CUPTI cost and optionally T2 structure, never inferred device values.

## Hard constraints

- Linux kernel and working uprobes are mandatory; the tested Docker Desktop LinuxKit path failed.
- The exact target needs DWARF or a trusted shipped build-ID offset record.
- Target ELF, layout, and generated program must agree before attach.
- Graph walking is verifier-bounded and must report/refuse truncation.
- Perf-ring capacity and structured loss accounting are product requirements.
- Tensor timing is role-specific; non-final-node buffer reuse remains unproven.
- Per-float bpftrace output must be replaced by bounded structured chunks for production.
- CUPTI environment-variable injection is zero-source-patch but not zero-overhead; the measured end-to-end delta was approximately 5% in one directional before/after sample.
- Under CUDA, `llama_decode` uretprobe time measures host submission rather than completed GPU execution; GPU cost requires an activity timeline or equivalent completion signal.
- CUPTI time-plus-stream attribution is proven only for sequential single-stream requests. Overlap, multiple streams, continuous batching, and multiple GPUs remain ambiguous without cooperative markers or an explicit allocation model.
- GPU graph metadata remains host-readable, but backend splits change graph cardinality and node position. CPU maps are not portable to CUDA, and GPU maps must pin backend schedule and graph bounds.
- A CUDA device UVA can appear as a `---p` process VMA and `/proc/<pid>/mem` can return zero bytes with success. Readers must classify buffer residency and reject such bytes rather than interpret them as activations.
- Exact device values require the owning CUDA context, a cooperatively exported CUDA IPC handle, or an in-process backend-safe copy at a proven lifetime boundary. Unrelated D2H logits or KV traffic do not prove target-tensor staging.
- Fused GPU kernel semantics and bpftime/PTX value observation remain unproven.
- The release evidence is one tag jump, the architecture evidence is Qwen3 plus Llama-3.2, the exact-value runtime evidence is CPU in one process, and the GPU evidence is one Qwen3 F16 build on one NVIDIA L4.
- Multi-sequence identity was proven at T1, but shared graph cost division remains an allocation model.
- Steady-state CPU probe overhead, steady-state CUPTI overhead gates, and real traceparent correlation remain open.

## Deferred P5 and F ADR inputs

The completed GPU tier answered the first P5 questions: CUPTI injection recovered sequential single-stream request-correlated kernel timelines; T2 graph census survived CUDA with backend-specific splits; device-memory lifetime and residency inspection established that zero-touch T3 values are not reachable through eBPF or `/proc`; and directional overhead measured approximately 5% end to end. It also established the product routing rule that exact GPU values belong to the cooperative S4 `cb_eval` and backend-copy path rather than the S5 zero-touch claim.

What remains deferred is a safe bounded bpftime/PTX experiment if permitted, concurrent and continuous-batching attribution, multi-stream and multi-GPU correlation, a CUDA-aware in-context preload helper assessment, steady-state alternating overhead gates, event-loss stress tests, a pinned kernel-variant map if kernel semantics are ever claimed, and a wider GPU release/architecture/quantization matrix. An exact GPU-aware oracle remains necessary only for a future cooperative or in-context value path; it is not a missing validation step for the demonstrated negative ceiling.

The F ADR must decide separate support labels for CPU exact values, GPU CUPTI cost, and GPU T2 structure; signed-map provenance and revocation; fail-closed fallback behavior; a wider release/architecture CI matrix; libbpf CO-RE chunk transport; eBPF and CUPTI privilege/injection policy; serving-boundary trace correlation; continuous-batching allocation semantics; steady-state CPU and CUPTI overhead limits; rejection rules for CUDA UVA reads; and the selection rule between S4 cooperation, S5 zero-touch, CUPTI cost, and T0/T1-only evidence.
