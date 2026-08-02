# Stage 9 — Trajectory schema canonicalization

This document defines the minimal canonical trajectory schema that OTel GenAI semantic conventions, OpenInference, and Langfuse exports all project into — the C1 core that gates the A ADR. It is co-developed with spike S1 and grounded in S1's empirical evidence: one real tool-using agent run captured through two independent instrumentation paths (Langfuse `3.224.4` self-hosted export; OpenInference/OTLP via collector), plus concrete field inventories extracted from the pinned published specs. The evidence artifacts (per-source field inventories, the 53-row coverage matrix with every cell evidence-referenced, and the raw exports used as immutable fixtures) live in the S1 spike workspace and are summarized in [the S1 learnings](../impl/learnings/S1-trace-ingestion.md) when the spike completes.

**Spec pins for this stage:** OTel GenAI semantic conventions at repository commit `8484f22ff8069267f37cb1be54bcebbf1972b682` (schema `1.42.0-dev`, core semconv `v1.43.0`; the GenAI conventions now live in their own repository and all GenAI span shapes are stability-level Development — only the core span envelope, `error.type`, and `server.*` are Stable). OpenInference at tag `python-openinference-semantic-conventions-v0.1.31` (commit `59ea35e`; no per-field stability labels exist, so fields are taken as published at the tag). Langfuse as observed from the `3.224.4` public trace-export API. These pins date this document; adapters version against them.

## Design principles

1. **Small canonical core, explicit provenance everywhere.** The core is the field set both real exports populate today. Everything else is nullable-with-provenance: a reserved key whose absence states *why* it is absent (`captured` / `derived` / `not_captured` / `not_applicable`), never a silent null. The coverage gap is data, not an error.
2. **Never invent precision or intent.** No padding milliseconds into nanoseconds, no array order as causality, no wrapper defaults presented as requested parameters, no lexical `"42"` silently coerced to numeric `42`.
3. **The schema is a projection target, not a superset.** Fields that exist only in one spec's aspirational surface (e.g. OTel memory operations, evaluation spans) are out of the core; they join later as extensions without breaking changes.
4. **The parametric evidence channel is reserved from day one** in the shape the S3–S5 campaign proved necessary — this is the "minimal reserved schema shape decided now, in the schema, before any adapter ships" open question from the research plan, answered.

## The canonical model

A **trajectory** is one run envelope plus an ordered list of events. Events form a tree via parent linkage; three kinds cover the S1 evidence: `run` (root), `llm`, `tool`. Agent/sub-agent nesting reuses `run`-kind events below the root; further kinds (retrieval, evaluation) are additive later.

### Common event envelope

| Field | Status | Notes |
|---|---|---|
| `run_id` | required | OTel/OpenInference `traceId`; Langfuse trace `id` |
| `event_id` | required | `spanId` / observation `id` |
| `parent_event_id` | required, nullable | null identifies the root event |
| `kind` | required | `run` / `llm` / `tool` (`AGENT`,`SPAN`→`run`; `LLM`,`GENERATION`→`llm`; `TOOL`→`tool`) |
| `name` | required | source span/observation name |
| `started_at`, `ended_at` | required | normalized UTC |
| `time_precision` | required | `nanosecond` (raw OTLP) / `millisecond` (Langfuse API export) — declared, never upgraded |
| `order_key` | required, derived | `(started_at, parent_event_id, source event id)`; labeled derived — a display order, not a causal sequence |
| `status`, `error` | required, nullable | normalized from OTel status/`error.type` or Langfuse level/statusMessage |
| `source` | required | provenance object: source kind, artifact, source field(s), direct-vs-derived marker |
| `session_id`, `user_id` | nullable + provenance | native in both specs, populated only when supplied |

### LLM event payload

| Field | Status | Notes |
|---|---|---|
| `model_id` | required | requested-vs-response ambiguity retained in provenance (OTel distinguishes `gen_ai.request.model` / `gen_ai.response.model`; the others don't) |
| `provider` | nullable + provenance | `llm.system`/`llm.provider` / `gen_ai.provider.name`; derived for Langfuse from the wrapper scope |
| `input_messages`, `output_messages` | required | full ordered model-visible message state, tool calls and tool-result messages included |
| `tool_schemas` | required array | complete JSON Schema definitions as advertised to the model |
| `sampling` | required object | each entry `{value, origin, source_field}` with `origin ∈ requested / wrapper_default / provider_default / unknown` — decision 4 below |
| `usage` | required | `input_tokens`, `output_tokens`, `total_tokens` (total computed only when absent, marked derived) |
| `finish_reason` | nullable + provenance | direct in OpenInference/OTel; absent from the Langfuse export |
| `raw_completion_id` | nullable + provenance | derivable from OpenInference raw response; absent in Langfuse |

### Tool event payload

| Field | Status | Notes |
|---|---|---|
| `tool_name` | required | |
| `tool_call_id` | nullable, derived | joined to the preceding LLM tool call by parent, order, and name — neither source puts the call id on the tool event natively |
| `input`, `output` | required, typed value | the decision-3 envelope: `{raw, parsed, media_type, source_type}` |
| `schema_version`, `implementation_version` | nullable + provenance | absent in every evaluated source — a first-class gap stage 10 requires the schema to expose |

### Replay manifest (stage 10's requirement, reserved as one nullable object)

`replay` with per-slot provenance states (`captured` / `derived` / `not_captured` / `not_applicable`): `policy{id,revision}` · `sampling{parameters,seed}` · `instructions.system_developer` · `tools{schemas,implementation_versions}` · `model_visible_messages` · `external_resource_snapshot_ids` · `evaluator_version` · `state_hashes{input,output}`.

S1's empirical verdict: message state, tool schemas, and partial sampling parameters are derivable from both real exports; **policy identity/revision, seed, tool implementation versions, resource snapshots, evaluator version, and state hashes are absent from every evaluated source.** OTel defines `gen_ai.request.seed` but no evaluated export carried a value; `gen_ai.data_source.id` is identity, not an immutable snapshot. The distinction between "instrumentation did not support it", "run did not use it", and "adapter lost it" is exactly what the per-slot state encodes — TraceElephant's finding that output-only traces degrade attribution makes these slots schema requirements, not options.

### Reserved parametric evidence channel (S3–S5 campaign shape)

Two sibling channels join the trajectory as `kind`-neutral INTERNAL events correlated by `run_id`/parent linkage: **`xai.parametric.observe`** (uncertainty and residual/probe scalars) and **`xai.cost.observe`** (per-request compute cost). Every parametric event carries a required provenance block — `engine{name,version}`, `backend_graph_mode` (eager vs graph), `attribution_mode`, `build_id` — and the epistemic **`numerics.mode = exact | tolerance`** flag distinguishing bitwise-CPU readings from bf16/batch-variant GPU readings; without it the observed/correlational/causal honesty contract leaks at the schema boundary. Carrier verdict from S1: all three transports carry such a foreign span without data-model violation (OTel/OpenInference as flattened bounded custom attributes — span attributes are scalars/homogeneous arrays, so nested provenance flattens or JSON-serializes; Langfuse as a generic `SPAN` observation with the block under JSON `metadata`, never occupying Langfuse's own model/cost fields). Scalar-only, bounded attributes; no tensors, no content — per the stage-12 contract.

## The five normalization decisions (ratified)

1. **Root representation.** One canonical run envelope plus one root event. Langfuse's top-level trace maps to the envelope and its root observation to the root event; OTLP's trace id maps to the envelope and the root agent span to the root event. Never synthesize a second root, never discard the Langfuse root observation's timing.
2. **Timestamps and ordering.** Normalized UTC plus a declared `time_precision`; a deterministic derived `order_key` for display; array order is never causality (the Langfuse API returns observations non-chronologically).
3. **Typed values.** Tool/LLM inputs and outputs use the `{raw, parsed, media_type, source_type}` envelope. Equality comparisons may use `parsed` under an explicit policy; replay and audit always retain the source lexical form (the evidence case: OpenInference preserved `"42"` as text/plain, Langfuse parsed it to number `42`).
4. **Sampling provenance.** Every sampling entry carries its origin; wrapper defaults (Langfuse added `top_p=1` and penalty defaults the caller never sent) are never merged into requested parameters; seed stays null unless actually captured.
5. **Cost and model-registry fields.** API model identity lives in the core; registry ids and monetary cost live in an optional extension with currency, calculation method, pricing revision, and provenance. A registry id never substitutes for a model API id; an unpopulated cost slot never becomes zero cost.

## Coverage summary and what gates A

Of the 53 candidate canonical fields evaluated: OTel GenAI 37 present / 6 derivable / 10 absent; OpenInference (spec + real export) 30 / 10 / 13; Langfuse export 30 / 7 / 16. The shared populated core — identity/linkage, event kinds, full message and tool-schema state, model identity, core sampling values, token usage, tool inputs/results, status, timing — is sufficient for layer A's diagnostics and for B's intervention targeting; the absent set is concentrated in the replay manifest, which is why those slots are provenance-tracked rather than assumed.

Remaining for spike S1 to prove against this spec: the two adapters normalizing both real exports into one dataframe with field-level alignment assertions (S1-P3), and the manifest-slot audit plus the parametric-channel join test with campaign-shaped fixture spans (S1-P4). Divergences those phases surface are folded back here before the A ADR cites this document.
