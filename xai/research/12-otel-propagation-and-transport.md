# Stage 12 — OTel propagation and transport

> Deep-research output (ChatGPT deep research, imported 2026-08-01) produced from [`deep-research-prompts/12-otel-propagation-transport.md`](./deep-research-prompts/12-otel-propagation-transport.md). Part of the [research plan](./0-research-plan.md). Citations appear as opaque `citeturn...` tokens from the research tool rather than resolvable URLs; load-bearing novel claims (new benchmarks, version-specific behavior, enacted regulation numbers) should be spot-verified against primary sources before being relied on in an ADR, and claims flagged for spike verification are validated, not trusted.

# Distributed Trace Correlation for `xai` Model-Internal Signals

## Engineering conclusion

The proposed architecture is sound: the agent process should create the logical GenAI client span, inject W3C `traceparent` and `tracestate` into the OpenAI-compatible HTTP request, and the inference server should extract that context before creating its HTTP-server, inference, and `xai` model-internal spans. A propagated `CLIENT` span normally becomes the parent of a remote `SERVER` span; subsequent work inside the inference process is represented by `INTERNAL` spans. Trace correlation depends on the shared trace ID and parent span ID, not on the processes using the same SDK, programming language, instrumentation library, or telemetry vendor. citeturn15search0turn16search14turn18search10

The strongest implementation path in the investigated server set is:

| Component | Trace-context continuation | Custom signal emission | Engineering assessment |
|---|---|---|---|
| **vLLM** | **Supported** in current tracing code and documentation | **Partial**: OTel tracer and instrumentation helpers exist, but a stable model-runner plugin contract for per-request custom spans is not clearly documented | Best initial Layer F target; spike S3 must prove the worker-level context and probe hook |
| **SGLang** | **Supported/partial by version and entry path**: current core source extracts W3C context; model-gateway propagation had a documented 2026 defect and fix history | **Partial**: internal tracing structures accept attributes, but the extension surface is not documented as a stable public plugin API | Good second target; spike S3 must pin an exact release and direct-server versus gateway behavior |
| **NVIDIA Triton** | **Supported** from documented releases supporting propagated OTel context | **Partial**: custom backend activities can produce spans, but arbitrary per-span attribute attachment is less clearly documented | Viable where `xai` owns a Triton backend or model wrapper |
| **Ollama** | **Needs verification; no native support documented in the reviewed official material** | **Needs verification; likely requires a server patch or wrapper** | Do not advertise native continuation until tested against a pinned release |
| **llama.cpp / `llama-server`** | **Needs verification; no native support documented in the reviewed official material** | **Needs verification; likely requires source-level integration** | Treat as an adapter requiring modification, not as an already OTel-aware server |

For telemetry destinations, raw OTLP and Logfire can remain configuration-only targets. Langfuse is also an OTLP target, but its HTTP-only ingestion protocol, authentication headers, trace-root expectations, and attribute mapping make its adapter slightly more opinionated. citeturn14search4turn23view3turn22search8turn23view4turn23view5

The status terms used here are deliberately strict:

| Status | Meaning |
|---|---|
| **Supported** | Official documentation or current official source explicitly implements the capability |
| **Partial** | Required primitives exist, but an additional instrumentor, version condition, custom hook, or operational rule is required |
| **Needs verification** | The reviewed official material does not document the behavior, or only indirect/negative evidence is available |

## Trace context and canonical span hierarchy

### What the HTTP boundary must do

W3C Trace Context defines `traceparent` as the portable representation of an incoming request’s position in a trace graph. Its version-00 form contains a 16-byte trace ID, an 8-byte parent ID, and trace flags. `tracestate` is a companion list for tracing-vendor-specific state; it is optional, opaque to unrelated vendors, and must not be repurposed for application payloads or internal-state readings. citeturn15search0turn15search1

A participating client updates the `parent-id` to identify its outbound operation while preserving the trace ID. A receiving server extracts that context and starts its server span against the extracted context. When that server later calls another service, it injects a new `traceparent` whose parent ID identifies the current operation. This is the standard mechanism by which a trace crosses process and service boundaries. citeturn15search0turn16search14

In OpenTelemetry terms, `Inject` writes the current context into a mutable carrier such as HTTP headers, while `Extract` reads an incoming carrier and returns a context containing the remote `SpanContext`. The server must pass that extracted context when creating its first span; merely parsing or logging the header does not continue the trace. citeturn16search14turn16search0

For `xai`, the expected hierarchy is:

```text
agent invocation                         INTERNAL
└── chat <served-model>                  CLIENT   [GenAI logical client span]
    └── POST /v1/chat/completions        CLIENT   [optional HTTPX transport span]
        └── POST /v1/chat/completions    SERVER   [inference-server HTTP ingress]
            └── inference <served-model> INTERNAL [server/model execution]
                └── xai.parametric.observe
                                             INTERNAL [aggregated internal evidence]
```

The extra HTTP client span is normal when both a logical GenAI instrumentor and HTTPX instrumentation are enabled. OpenTelemetry explicitly allows a logical client span to contain a protocol-level client span; context injected by the inner HTTP client then makes the remote HTTP server span its child. citeturn17search5turn18search10

A direct parent relationship from the logical GenAI client span to the inference-server span is also valid when the application manually injects the logical span’s context and does not produce a separate HTTP transport span. `xai` should accept both shapes rather than require one exact number of intermediate spans.

### GenAI semantic conventions and their current boundary

The current GenAI semantic-convention work is maintained in the dedicated OpenTelemetry GenAI repository. It defines conventions for GenAI clients, agents, tools, MCP, and provider-specific APIs, but the conventions remain under active development and have continued to change through 2026. citeturn19view0turn20view0turn17search20turn18search2

Current agent conventions distinguish remote `invoke_agent` client spans from in-process `invoke_agent` internal spans. They also define agent lifecycle and tool-execution concepts such as `create_agent`, workflow invocation, planning, and `execute_tool`; recent releases added tool-call argument/result attributes and refined the split between agent and inference attributes. citeturn17search2turn18search2

For a remote model call, the standard logical inference span is a `CLIENT` span. Its name follows the operation-and-model pattern, and applicable attributes include `gen_ai.operation.name`, requested and response model identifiers, provider identity, finish reasons, response ID, token usage, streaming information, `server.address`, and `error.type`. Sensitive input/output content is optional and subject to capture controls. citeturn16search2turn18search11turn18search2

There is not yet a stable GenAI semantic convention for the server-side inference engine hierarchy or for model-internal evidence. An active OpenTelemetry proposal explicitly identifies the present client-centric gap, the lack of a standardized inference-engine span type, and risks such as double-counting tokens if client and server spans are interpreted identically. citeturn19view3

Consequently, `xai` should not describe the internal-signal span as a standardized GenAI inference span. The safe design is:

- Put standard `gen_ai.*` operation and token attributes on the logical client span and, where useful, the server’s actual inference-operation span.
- Give the HTTP ingress span `SpanKind.SERVER` and ordinary HTTP semantic-convention attributes.
- Give model execution and internal-signal spans `SpanKind.INTERNAL`.
- Put model-internal evidence under a separately governed `xai.*` namespace.
- Do not set `gen_ai.operation.name` or token-usage attributes on the signal child span unless that span genuinely represents an additional inference operation; this avoids backend metric double counting while server-side conventions remain unsettled. citeturn18search10turn17search5turn19view3

### Parent choice and streaming lifetime

The incoming `traceparent` should normally be injected while the logical model-client span is current. If HTTPX instrumentation creates a transport span, its newly generated span ID will be injected and the remote server will attach beneath it. If no HTTP transport instrumentation is enabled, manual injection should use the logical model-client span’s current context.

For streaming responses, the HTTP and logical inference spans should cover the documented lifetime of the streaming call rather than end when only the first headers or first token arrive. The internal-signal span should end when the aggregate is finalized, normally at generation completion, cancellation, timeout, or error. Current GenAI conventions include streaming indicators and time-to-first-chunk information, while generic RPC conventions define streaming spans over the lifetime of the stream. citeturn18search2turn17search7

The server should respect the propagated trace flags and use a parent-based sampling strategy. During S3, use always-on recording at both processes to remove sampling as a confounder; production can then move to parent-based root-ratio sampling. W3C requires continuation of the relevant trace flags when the trace ID is retained. citeturn15search0

## Agent clients and framework propagation

### The important distinction: instrumentation versus propagation

An LLM or agent instrumentor can create useful logical spans without instrumenting the underlying HTTP transport. Conversely, HTTPX instrumentation can propagate trace context while knowing nothing about agents, tools, prompts, token counts, or model semantics. A complete deployment usually needs both layers:

```text
OpenInference / OpenLLMetry / framework-native instrumentation
    → logical agent, tool, workflow, and LLM spans

OpenTelemetry HTTPX instrumentation or explicit header injection
    → W3C propagation over the actual OpenAI-compatible HTTP request
```

OpenInference and OpenLLMetry are OpenTelemetry-based instrumentation ecosystems covering OpenAI and common agent frameworks. Their documented purpose is to create and export AI-observability spans; the reviewed package-level documentation does not establish that installing only a logical OpenAI, LangChain, CrewAI, or LlamaIndex wrapper also instruments every underlying HTTP client and injects W3C headers. citeturn21search0turn21search1

Therefore, the engineering rule should be: **never infer transport propagation from the presence of logical LLM spans**. Verify the outgoing request or explicitly instrument the transport.

### Client and framework status

| Client or framework path | Logical tracing | Outbound `traceparent` status | Required `xai` guidance |
|---|---|---|---|
| **Plain OpenAI Python SDK alone** | None natively beyond SDK behavior | **Partial/manual** | Supply `extra_headers`/default headers manually, or instrument its HTTPX client |
| **OpenAI Python SDK plus OTel HTTPX instrumentation** | HTTP client span; add OpenInference/OpenLLMetry for GenAI detail | **Supported** | Preferred generic OpenAI-compatible path |
| **LangGraph / LangChain** | Framework-native LangSmith OTel, OpenInference, or OpenLLMetry can create workflow/agent/LLM spans | **Partial** unless the underlying HTTP transport is also instrumented | Pair framework instrumentor with HTTPX/requests instrumentation |
| **CrewAI** | OpenInference and OpenLLMetry integrations exist | **Partial**; provider/LiteLLM transport must be checked | Instrument the actual provider client or inject explicitly |
| **LlamaIndex** | OpenInference and OpenLLMetry integrations exist | **Partial**; depends on the selected LLM integration and transport | Instrument the actual OpenAI/httpx client |
| **Custom OpenAI-SDK loop** | Manual or OpenAI instrumentor | **Supported when HTTPX is instrumented; otherwise manual** | Make propagation a library-level invariant |

#### Plain OpenAI Python SDK

The official OpenAI Python SDK uses HTTPX for both synchronous and asynchronous clients and exposes per-request `extra_headers` as well as configurable HTTP clients. The SDK documentation does not promise native OpenTelemetry propagation, so the SDK alone should be treated as a header-capable transport rather than a trace-context instrumentor. citeturn21search4

OpenTelemetry’s HTTPX instrumentor traces all instrumented client requests. Its implementation injects propagation headers before invoking the underlying HTTP transport, which is the required behavior for an OpenAI-compatible call. citeturn21search2turn10search3

This gives two valid implementations:

```python
# Automatic transport propagation
HTTPXClientInstrumentor().instrument()
client = OpenAI(base_url=inference_url, api_key="...")

# Or explicit propagation when global HTTPX instrumentation is undesirable
headers: dict[str, str] = {}
propagate.inject(headers)
client.chat.completions.create(
    model=model,
    messages=messages,
    extra_headers=headers,
)
```

The automatic approach is preferable where the process already uses an OpenTelemetry SDK, because it handles both `traceparent` and configured propagators consistently. Manual injection is useful when the application must avoid an additional generic HTTP client span or when a framework hides its HTTP client but permits model-call headers. OpenTelemetry’s Python documentation provides the corresponding manual inject/extract pattern. citeturn16search0

#### LangGraph and LangChain

LangChain and LangGraph can produce OpenTelemetry traces through LangSmith’s OTel support, and OpenInference’s LangChain instrumentor supports LangChain versions built on LangGraph. OpenLLMetry also lists LangGraph and LangChain among supported frameworks. citeturn12search0turn14search10turn11search1turn21search0

Those mechanisms establish the application-level trace but do not by themselves prove that every provider request carries `traceparent`. When `ChatOpenAI` or an equivalent wrapper ultimately calls the OpenAI Python SDK, HTTPX instrumentation is the cleanest propagation layer. Where a custom LangChain model wrapper sends requests through `requests`, `aiohttp`, LiteLLM, or another client, its corresponding OTel transport instrumentor is needed.

The crucial test is not whether a LangGraph run appears in a backend; it is whether the actual outbound `/v1/chat/completions` or `/v1/responses` request contains a `traceparent` whose trace ID matches the active LangGraph/LLM span.

#### CrewAI

OpenInference provides CrewAI instrumentation, and OpenLLMetry lists CrewAI and LiteLLM among its supported integrations. These integrations can establish CrewAI task, agent, and model-call spans, but transport propagation depends on the provider stack selected by the CrewAI deployment. citeturn11search4turn21search0turn21search1

For `xai`, CrewAI should be documented as **partial by default**: instrument CrewAI for logical spans, then instrument the actual LiteLLM/OpenAI HTTP client or add propagated headers through the model configuration. Do not promise end-to-end server continuation solely from `CrewAIInstrumentor().instrument()`.

#### LlamaIndex

OpenInference provides a LlamaIndex instrumentor, and OpenLLMetry lists LlamaIndex support. These instrumentors create LlamaIndex-level traces but the outbound model request still depends on the selected provider integration. citeturn21search0turn21search1turn14search7

A LlamaIndex application using the OpenAI Python client should instrument HTTPX. A LlamaIndex application using a non-HTTPX transport should instrument that transport or explicitly propagate a carrier through the provider adapter.

### Recommended agent-side contract

The provider-neutral `xai` integration should expose a small helper rather than build framework-specific transport code:

```python
def inject_trace_headers(
    headers: MutableMapping[str, str] | None = None,
) -> MutableMapping[str, str]:
    carrier = headers if headers is not None else {}
    opentelemetry.propagate.inject(carrier)
    return carrier
```

Framework adapters should only determine where to pass the resulting headers. They should not construct `traceparent` manually, parse trace IDs, or introduce a private correlation header.

The helper should preserve user-supplied headers and allow the globally configured propagator to decide whether to include `traceparent`, `tracestate`, and baggage. `xai` should discourage baggage for model-internal data: baggage is propagated broadly, whereas internal readings belong on server-produced telemetry.

## Inference servers and extension surfaces

### Server capability matrix

| Server | Incoming context continuation | Native OTel export | Custom per-request span attributes | Overall status |
|---|---|---|---|---|
| **vLLM** | Explicit `TraceContextTextMapPropagator().extract(headers)` in current tracing API | OTLP endpoint and detailed tracing options | Instrumentation wrappers accept attributes; resource extras are supported; stable probe-plugin hook not documented | **Supported / partial** |
| **SGLang core server** | Current source has `traceparent`/`tracestate` extraction and starts request tracing from external context | `--enable-trace`, `--otlp-traces-endpoint` | Internal trace structures support attributes/events, but stable public hook unclear | **Supported / partial** |
| **SGLang model gateway** | Documented W3C propagation, but a May 2026 defect showed inbound context was not extracted in an affected version | OTel gateway tracing | Extension behavior depends on gateway/core path | **Partial; pin and test version** |
| **Ollama** | No native continuation documented in reviewed official repository/docs | No native server OTel tracing documented | No stable tracing/plugin hook documented | **Needs verification** |
| **llama.cpp** | No native continuation documented in reviewed official repository/docs | No native server OTel tracing documented | Requires source integration or an external wrapper for model-internal data | **Needs verification** |
| **NVIDIA Triton** | Documented propagated context support from release 24.01 onward | OTLP/HTTP export | Custom backend trace activities can create spans; arbitrary attribute API needs confirmation | **Supported / partial** |

### vLLM

Current vLLM tracing documentation exposes `extract_trace_context(headers)`, which uses `TraceContextTextMapPropagator().extract(headers)`. It also exposes tracer initialization, worker tracer initialization, manual instrumentation, and context propagation through environment variables for child or worker processes. citeturn23view0

vLLM’s tracer initializer accepts extra resource attributes and configures an OTLP span exporter. Its instrumentation wrapper accepts a span name and attribute dictionary and starts a span against either the active local context or a context reconstructed from propagated environment state. citeturn23view0

The vLLM server exposes an OTLP trace endpoint option and detailed-trace collection controls. Earlier vLLM proof-of-concept documentation shows a client and vLLM server span appearing in one trace when the request carries trace context. citeturn2search0turn2search1turn2search5

This supports a **Supported** status for inbound continuation and native export. It does not yet establish a supported, version-stable plugin API for retrieving hidden states or probe outputs and attaching a request-specific scalar to the right model-execution span.

**S3 confirmation required:** the `traceparent` extracted by the OpenAI-compatible API process remains associated with the same request after transfer into the engine and model-worker process. Current source contains worker-context mechanisms, but the exact parentage through the target serving architecture must be observed, not inferred. citeturn23view0

**S3 confirmation required:** a Layer F plugin can run at the desired model layer without patching core scheduling logic, identify the correct request when continuous batching combines multiple sequences, and obtain either the active span or an explicit request trace context.

**S3 confirmation required:** the plugin can create one child `INTERNAL` span or set attributes on a request-specific inference span without modifying global tracer-provider ownership.

**S3 confirmation required:** streaming completion, cancellation, timeout, client disconnect, and engine error all end the custom span exactly once.

**S3 confirmation required:** tensor-parallel, pipeline-parallel, and multiprocess execution do not create unrelated trace roots or duplicate one probe span per rank unless that behavior is deliberately selected.

**S3 confirmation required:** the installed vLLM release’s built-in exporter protocol matches the intended collector configuration, or the adapter can use the project’s existing provider/exporter without initializing a conflicting global provider.

### SGLang

SGLang’s current server arguments document native OTel tracing via `--enable-trace`, selectable trace modules, and `--otlp-traces-endpoint`. citeturn23view1

Current SGLang source defines `traceparent` and `tracestate` as accepted trace headers, extracts external context using `TraceContextTextMapPropagator`, and stores an external trace carrier on the per-request trace context before creating request spans. fileciteturn1file0L1-L2

The SGLang model-gateway documentation describes W3C Trace Context propagation and injection into upstream worker requests. However, a May 13, 2026 issue documented a gateway path that injected outbound context without first extracting incoming context, thereby creating a new root trace. The issue was closed through a subsequent change, making exact release pinning material to the status. citeturn3search0turn3search1

Accordingly, direct current-core continuation is **Supported**, while a general claim covering all SGLang releases and gateway arrangements is only **Partial**.

**S3 confirmation required:** record the exact SGLang commit or release under test and whether the request enters the core OpenAI server directly or passes through the model gateway.

**S3 confirmation required:** verify that the trace ID in the incoming `traceparent` survives tokenizer, scheduler, worker, and tensor-parallel boundaries and that the custom signal span has the intended agent-side ancestor.

**S3 confirmation required:** determine whether the internal trace classes and attribute dictionaries constitute a usable extension point or merely an internal implementation detail likely to change.

**S3 confirmation required:** demonstrate a request-safe hook for probe computation under batching, prefix caching, speculative decoding, disaggregated prefill/decode, and streaming.

**S3 confirmation required:** verify that a scalar emitted by a worker does not become an orphan span when its context is serialized or copied between processes and threads.

**S3 confirmation required:** test both OTLP/gRPC and OTLP/HTTP where applicable, because server flags and backend ingestion protocols do not have identical support.

### Ollama

Ollama provides an OpenAI-compatible API, and client-side observability projects such as OpenLLMetry can instrument calls made to Ollama. That does not imply that the Ollama server extracts incoming W3C context or emits server-side OTel spans. The reviewed official repository and server material did not document native `traceparent` continuation, an OTLP exporter, or a public span-extension hook. citeturn7search11turn21search0

The correct status is therefore **Needs verification**, not definitively “unsupported.” A reverse proxy or auto-instrumented HTTP wrapper could create a correlated server span, but such a wrapper would not have access to model internals. Layer F would probably require modification of Ollama’s server/runner boundary or a specially instrumented backend.

`xai` documentation should avoid grouping “Ollama support” with vLLM/SGLang support until a pinned Ollama build demonstrates both context extraction and a model-internal callback.

### llama.cpp

`llama-server` provides an OpenAI-compatible HTTP interface, but the reviewed official material did not document native OpenTelemetry trace continuation or OTLP export. citeturn8search5

The status is **Needs verification** for context continuation and custom attributes. Because llama.cpp is source-available and its inference loop is local to the server, a direct integration is technically plausible: extract the incoming W3C context in the HTTP route, carry a request trace handle into generation, and create an `xai` span at the point where the desired logits or hidden-state aggregate is available. That is an implementation proposal, not a documented existing capability.

An HTTP proxy alone is insufficient for Layer F because it cannot observe activations or model-layer outputs. It can establish cross-service trace structure, but the internal signal still requires code inside the inference process.

### NVIDIA Triton

Triton’s tracing documentation states that propagated OpenTelemetry context is supported from version 24.01 and that a request carrying propagated context is traced irrespective of ordinary trace-rate or trace-count settings. Triton exports OTel traces through OTLP/HTTP and records request/model identifiers and parent information on its spans. citeturn7search0turn7search3

Triton’s custom-backend trace API lets a backend report named activities; matching custom `_START` and `_END` activities can produce custom spans. Triton also supports custom resource attributes through trace configuration or standard OTel resource settings. citeturn7search0

That supports **Supported** continuation and **Partial** custom emission. A Triton backend can create a model-internal sub-operation span, but the reviewed documentation is clearer about custom activity spans and resource attributes than about attaching arbitrary numeric attributes such as `xai.parametric.probe.score` to those generated spans. A custom backend can always use an OTel SDK directly if Triton’s trace API is too restrictive, provided it parents the SDK span from the request’s extracted context.

Triton is not itself the same deployment shape as a drop-in OpenAI-compatible vLLM server; `xai` would normally target a Triton backend, ensemble component, or OpenAI-facing service deployed in front of Triton.

### S3 acceptance matrix

Spike S3 should be considered complete only when all of the following are demonstrated against pinned vLLM and SGLang versions:

| S3 assertion to confirm | Evidence required |
|---|---|
| The agent emits a valid W3C carrier | Captured outbound HTTP headers showing `traceparent`, and `tracestate` when configured |
| The server continues rather than restarts the trace | Agent and server spans share a trace ID; server parent ID equals the expected outbound client-span ID |
| Context survives server process boundaries | API, engine, scheduler, and worker spans remain in one trace |
| The plugin is request-safe under batching | Two concurrent prompts produce correctly separated probe scores and span parents |
| A scalar can be emitted without raw tensors | OTLP payload contains only the bounded `xai.parametric.*` scalar/aggregate fields |
| The signal span has stable lifecycle behavior | Success, stream, cancellation, timeout, and error tests all produce one properly ended span |
| Sampling is deterministic | Always-on test works first; parent-based sampling then follows incoming trace flags |
| No global-provider conflict occurs | Agent/server can coexist with an existing SDK or documented server exporter configuration |
| Backends retain the namespace | Raw collector, Logfire, and Langfuse tests show the exact `xai.parametric.*` keys or a documented mapping |
| Rank and worker duplication is controlled | Expected cardinality under TP/PP/DP is asserted in an automated test |
| No accidental content capture occurs | Export confirms no prompts, completions, token strings, logits vectors, hidden states, or activations |
| Export failure does not affect inference | Collector outage or backpressure neither blocks nor crashes generation |

## OTLP backends and adapter thickness

### Destination capability matrix

| Destination | External spans accepted | Cross-service trace rendering | Arbitrary `xai.parametric.*` attributes | Adapter status |
|---|---|---|---|---|
| **Raw OTel Collector** | **Supported** | **Supported** by ordinary trace ID/parent ID | **Supported** | Configuration only |
| **Pydantic Logfire** | **Supported** from standard OTel SDKs and collectors | **Supported** for polyglot/distributed services | **Supported** as ordinary span attributes | Thin endpoint/auth adapter |
| **Langfuse** | **Supported** through its OTLP endpoint | **Supported with root-span and project-routing caveats** | **Partial**: ingestion is supported; UI/query mapping of unrecognized attributes should be contract-tested | Thin endpoint/auth plus mapping policy |

### Raw OTLP

OTLP is already the canonical transport. The inference adapter should produce normal OTel spans and hand them to the process’s configured `TracerProvider` and `SpanProcessor`. A collector can receive spans from the agent process and inference process, batch them, redact or transform attributes, and route the same data to one or more destinations. OTel Collector processors are explicitly designed to transform, filter, enrich, and redact telemetry in flight. citeturn16search7turn22search13

No `xai`-specific exporter is necessary for a raw collector. The adapter consists of endpoint/protocol/TLS/header configuration and resource attributes such as `service.name`. It should support standard environment variables rather than invent parallel configuration where the server permits that.

The most portable direct protocol is OTLP over HTTP/protobuf, because both Logfire and Langfuse accept HTTP ingestion while Langfuse does not require or universally expose OTLP/gRPC on its public ingestion endpoint. Where users already operate a collector, the processes can use either supported OTLP protocol to reach the collector and let the collector handle backend-specific export.

### Pydantic Logfire

Logfire documents direct ingestion from alternative OpenTelemetry clients using an OTLP endpoint and authorization token. It accepts telemetry from standard OTel SDKs rather than requiring spans to be created by Logfire’s own Python API. citeturn23view3turn14search11

Logfire also documents receiving data from any OTel source and joining spans from polyglot services into the same distributed trace when context is propagated. Its distributed-tracing guidance describes HTTP clients injecting `traceparent` and servers extracting it to reconstruct the full tree. citeturn14search4turn14search0

Custom span attributes are retained in the OTel attribute collection and can be queried as attributes. Therefore an `xai.parametric.*` namespace does not require conversion to a Logfire-specific object model. citeturn14search4

The Logfire adapter can be limited to:

```text
protocol       = OTLP/HTTP protobuf, or supported standard OTLP route
endpoint       = Logfire OTLP trace endpoint
headers        = Authorization bearer/write token
resource       = normal OTel service attributes
span mapping   = none
```

A user deploying an OTel Collector can instead configure the Logfire exporter there; `xai` then needs no Logfire code at all. Logfire describes itself as an OTel-compliant backend and documents collector-side filtering or transformation for sensitive attributes. citeturn14search2

**Backend status: Supported** for externally produced spans, cross-service traces, and custom namespaces.

### Langfuse

Langfuse exposes an OTLP endpoint intended to receive traces from standard OpenTelemetry libraries, OpenLLMetry, OpenLIT, and other OTel producers. It maps evolving GenAI semantic-convention attributes into Langfuse’s observation model. citeturn22search8turn23view4

The current ingestion path uses OTLP over HTTP, with Langfuse-specific endpoint and authentication headers. In its v4 model, observations share the OTel trace ID rather than requiring a separately generated Langfuse trace object. citeturn13search0turn23view5

Externally produced spans can therefore participate in a trace not originated by a Langfuse SDK, provided that:

- all spans are sent to the same Langfuse project or tenant;
- trace and parent IDs are preserved;
- a root span is included so Langfuse can create the trace correctly;
- trace-level fields needed for filtering—such as user, session, release, tags, or metadata—are propagated to each relevant span according to Langfuse’s current ingestion rules. citeturn13search0turn13search12turn22search8

Langfuse explicitly supports metadata and maps recognized OTel/GenAI attributes. Its metadata helpers impose backend-facing naming and length rules for propagated metadata, including alphanumeric-key and 200-character-value constraints in that helper path. citeturn22search1

For `xai.parametric.*`, the transport-level answer is positive: the data are valid OTel attributes and can be submitted through Langfuse’s OTLP endpoint. The stronger assertion—every arbitrary array or numeric namespace is displayed and queryable in precisely the same form in the Langfuse UI—should be treated as **Partial** until an ingestion contract test verifies it. Langfuse’s documentation emphasizes attribute mapping rather than promising that every unknown attribute receives a first-class field. citeturn22search8

The Langfuse adapter should therefore consist of:

```text
protocol       = OTLP/HTTP protobuf
endpoint       = /api/public/otel
headers        = Basic authentication + current ingestion-version header
resource       = normal OTel service attributes
span mapping   = optional mapping for Langfuse-specific display/filter fields
trace rule     = ensure the root span is exported
```

The adapter should not convert spans to Langfuse’s legacy ingestion objects. OTLP is the current path, and the v4 migration documentation centers the data model on OTel trace IDs and spans. citeturn23view5

**Backend status: Supported** for external and cross-service OTel spans; **Partial pending contract test** for exact preservation and query/display semantics of all `xai.parametric.*` forms.

### How thin the adapters can be

A single emitter can serve all three targets:

```python
@dataclass(frozen=True)
class OtlpTarget:
    endpoint: str
    protocol: Literal["http/protobuf", "grpc"]
    headers: Mapping[str, str]
    resource_attributes: Mapping[str, str]
```

The backend-specific code should only resolve this configuration:

| Target | Required variation |
|---|---|
| Raw collector | Endpoint, TLS, optional tenant headers, HTTP or gRPC |
| Logfire | Logfire endpoint and authorization header |
| Langfuse | Langfuse OTLP/HTTP endpoint, Basic authentication, ingestion-version header, optional Langfuse display attributes |

The span-building logic, context extraction, privacy policy, namespace, and signal schema must be identical across targets.

An even cleaner deployment is:

```text
agent process ─────┐
                   ├── OTLP → user's OTel Collector → Logfire and/or Langfuse
inference server ──┘
```

This removes backend credentials from Layer F, centralizes batching and redaction, and makes multi-destination export a collector concern. It also aligns with `xai`’s non-goal of becoming a trace store or observability platform.

## Privacy, bounded attributes, and evidence labeling

### Trace context contains correlation only

Neither `traceparent` nor `tracestate` should contain prompt text, probe results, model names chosen for confidentiality, user identifiers, activation hashes, or any other application data. W3C explicitly prohibits personally identifiable information in those fields and describes their purpose as trace correlation and tracing-vendor state. citeturn15search0

The only information crossing the HTTP boundary for correlation should normally be the standard propagation fields. The model-internal result is computed and exported by the inference server after request acceptance; it need not be transmitted back to the agent or placed in baggage.

### Record aggregates, not tensors

OpenTelemetry attributes can carry primitives, arrays, maps, and other `AnyValue` forms, but richer and nested values have greater processing overhead. SDKs also apply attribute-count and length-limit rules; the standard default attribute-count limit is 128, while default value length may be unlimited unless configured. citeturn22search0turn22search2turn22search6

`xai` should impose a stricter schema than the protocol permits:

| Signal | Safe representation | Do not export |
|---|---|---|
| Probe result | Scalar score, calibrated label, threshold, probe/version ID | Hidden vector, probe input tensor, full classifier weights |
| Logit uncertainty | Entropy, margin, variance, mean/p95, bounded token count | Full vocabulary logits, per-token probability matrix |
| Attribution summary | Fixed top-k feature IDs and scores, with small `k` | Full attribution vector or layer-by-token matrix |
| Layer information | Numeric layer index or stable component label | Raw activation values |
| Model identity | Served model ID and immutable revision where operationally acceptable | Filesystem paths, credentials, private registry tokens |
| Sampling | Boolean sampled flag and numeric rate | User-level sampling rationale containing PII |

A reasonable first production budget is one model-internal span per model request, fewer than roughly 32 `xai.*` attributes, top-k no larger than 10, and no individual string value larger than 512–2,048 characters. Those figures are an `xai` policy recommendation, not an OTel requirement.

Arrays should be parallel, bounded primitive arrays rather than a large JSON document:

```text
xai.parametric.attribution.feature_ids = ["f17", "f203", "f91"]
xai.parametric.attribution.scores      = [0.41, 0.27, 0.11]
```

Do not export raw token strings when those tokens can reveal prompts or generated content. Prefer feature categories, token positions, controlled vocabulary IDs, or keyed hashes only where the privacy model permits later correlation.

### Content capture must be opt-in

The standard GenAI attributes for input messages, output messages, system instructions, and retrieval queries carry explicit warnings that they may contain sensitive user or PII data. Instrumentations may filter or truncate those values, and large optional content is not recommended by default. citeturn16search2

Layer F should not enable prompt/completion capture as a side effect of enabling internal signals. The signal schema should include affirmative negative controls such as:

```text
xai.evidence.channel                    = "parametric"
xai.evidence.schema.version             = "1.0"
xai.evidence.claimed_cot_faithfulness   = false
xai.parametric.raw_activations_exported = false
xai.parametric.raw_logits_exported      = false
xai.parametric.content_included         = false
```

These fields make the evidence channel explicit and guard against a UI or downstream analyst presenting a probe reading as faithful chain-of-thought.

### Redaction and limits belong in two places

First, the server-side emitter should enforce an allowlist. A probe adapter should construct attributes from a typed schema rather than serialize a callback’s arbitrary Python dictionary or tensor object.

Second, the collector should enforce defense-in-depth. OTel Collector processors can filter, transform, prune, and redact telemetry before backend export. citeturn22search13turn22search10

Recommended collector policy:

```text
allow:
  xai.evidence.*
  xai.parametric.*
  approved gen_ai model/usage fields
  standard service, deployment, HTTP, and error fields

deny or redact:
  activation*
  hidden_state*
  logits_vector*
  prompt*
  completion*
  authorization*
  api_key*
  cookie*
```

Set `OTEL_SPAN_ATTRIBUTE_COUNT_LIMIT` and `OTEL_SPAN_ATTRIBUTE_VALUE_LENGTH_LIMIT` explicitly in Layer F deployments rather than relying on unlimited value lengths. The OTel environment-variable specification standardizes these controls. citeturn22search6

### Cardinality and versioning

Attribute keys should form a fixed schema. Do not generate keys containing layer numbers, token positions, probe labels, request IDs, or model names:

```text
bad:  xai.parametric.layer.17.probe.toxicity.score
good: xai.parametric.probe.score = 0.14
      xai.parametric.probe.name  = "toxicity"
      xai.parametric.layer.index = 17
```

Every reading should carry enough provenance to be interpreted without carrying the underlying tensor:

```text
xai.parametric.probe.name
xai.parametric.probe.version
xai.parametric.probe.score
xai.parametric.probe.label
xai.parametric.probe.threshold
xai.parametric.calibration.id
xai.parametric.model.revision
xai.parametric.layer.index
xai.parametric.sampled
```

Calibration IDs, probe versions, and model revisions should be low-length stable identifiers rather than serialized configurations. Full calibration artifacts belong in versioned files or registries, not span attributes.

## Recommended transport design

### Canonical server-side shape

The canonical `xai` shape should use a server-owned child span rather than overloading the agent’s client span:

```text
Span
  name: "xai.parametric.observe"
  kind: INTERNAL

Parent
  preferred: server-side "inference <model>" INTERNAL span
  fallback: HTTP SERVER span when no distinct inference span exists

Instrumentation scope
  name: "org.ethicalai.xai.parametric"
  version: <xai package version>

Resource
  service.name: "inference-vllm" | "inference-sglang" | ...
  service.version: <server version>
  deployment.environment.name: <environment>
  xai.inference.backend.name: "vllm" | "sglang" | "triton" | ...

Core span attributes
  xai.evidence.channel: "parametric"
  xai.evidence.schema.version: "1.0"
  xai.evidence.claimed_cot_faithfulness: false

  xai.parametric.model.id: <served model>
  xai.parametric.model.revision: <immutable revision, when available>

  xai.parametric.probe.name: <probe>
  xai.parametric.probe.version: <version>
  xai.parametric.probe.score: <double>
  xai.parametric.probe.label: <optional bounded string>
  xai.parametric.probe.threshold: <optional double>
  xai.parametric.calibration.id: <optional bounded ID>
  xai.parametric.layer.index: <optional int>

  xai.parametric.uncertainty.entropy.mean: <optional double>
  xai.parametric.uncertainty.entropy.p95: <optional double>
  xai.parametric.uncertainty.margin.mean: <optional double>
  xai.parametric.token_count: <optional int>

  xai.parametric.attribution.feature_ids: <optional bounded string[]>
  xai.parametric.attribution.scores: <optional bounded double[]>

  xai.parametric.raw_activations_exported: false
  xai.parametric.raw_logits_exported: false
  xai.parametric.content_included: false

Error behavior
  error.type: <exception/error class when failed>
  span status: ERROR only when the signal operation itself fails
```

The internal-signal span should not repeat `gen_ai.usage.input_tokens` or `gen_ai.usage.output_tokens`; those belong to the inference operation. It may repeat a bounded model identifier for standalone queryability, but should not masquerade as another `chat` or `generate_content` operation. This follows the current absence of server-engine GenAI span conventions and avoids token metric duplication. citeturn19view3

### Server adapter interface

The per-backend Layer F adapter should implement only four responsibilities:

```python
class InternalSignalAdapter(Protocol):
    def extract_request_context(
        self,
        headers: Mapping[str, str],
    ) -> Context: ...

    def bind_request_context(
        self,
        request_id: str,
        context: Context,
    ) -> None: ...

    def observe_model_state(
        self,
        request_id: str,
        model_state: ModelStateView,
    ) -> InternalSignal: ...

    def emit_signal(
        self,
        request_id: str,
        signal: InternalSignal,
    ) -> None: ...
```

`ModelStateView` should expose only the minimum server-local data needed for aggregation. It should not provide a generic “serialize tensor” capability. `InternalSignal` should be a typed, bounded object whose conversion to span attributes is shared across all inference backends.

The adapter should prefer the inference server’s existing active/request span when one exists. Otherwise it should extract the incoming W3C context and create an `INTERNAL` span directly beneath the server ingress. It must never create a new trace ID merely because the agent and inference server use different tracer providers.

### One emitter, configuration-only destinations

The emitter should be a normal OTel tracer configured once per process:

```text
TracerProvider
  Resource(service.name, service.version, backend)
  ParentBased sampler
  BatchSpanProcessor
  OTLP exporter
```

The same emitted span must be valid for:

```text
raw collector:
  standard OTLP endpoint and optional headers

Logfire:
  standard OTLP endpoint + Logfire authorization

Langfuse:
  OTLP/HTTP endpoint + Basic authentication
  + ingestion-version header
  + optional Langfuse-specific trace metadata
```

No backend-specific span classes are needed. Logfire requires only transport configuration. Langfuse may justify a small attribute-policy adapter for first-class filtering and display, but not a separate telemetry model or exporter implementation. citeturn23view3turn22search8turn23view5

### Final recommendation

Adopt W3C Trace Context as the only correlation protocol and OTLP as the only emission protocol.

On the agent side, instrument the logical agent/LLM layer with OpenInference, OpenLLMetry, or framework-native OTel, and independently guarantee HTTP propagation through OTel HTTPX instrumentation or explicit `propagate.inject`. Do not claim that an agent instrumentor automatically propagates headers unless that exact package combination has an integration test.

On the server side, target vLLM first and SGLang second. Both have credible current OTel foundations, but S3 must prove the model-worker hook, request isolation under batching, multiprocess context continuity, custom scalar export, and streaming lifecycle on pinned versions. Treat Triton as supported where a custom backend is feasible. Treat Ollama and llama.cpp as source-integration targets until native continuation is documented and demonstrated.

Emit one bounded `xai.parametric.observe` `INTERNAL` span per model request, parented beneath the server inference span, with fixed scalar/short-array attributes, explicit provenance, and affirmative declarations that raw activations, raw logits, content, and faithful chain-of-thought are not being exported.

Keep the backend layer thin: endpoint, protocol, authentication headers, and—only for Langfuse—optional mappings for first-class trace metadata. The canonical implementation should prefer exporting both processes to the user’s existing OpenTelemetry Collector, leaving storage, dashboards, trace rendering, redaction, and multi-backend routing outside `xai`.