# ADR 0001 — Canonical trajectory schema and ingestion (layer A)

- **Status.** Proposed
- **Date.** 2026-08-03
- **Depends on.** [stage 9](../research/9-trajectory-schema-canonicalization.md), [stage 12](../research/12-otel-propagation-and-transport.md), [S1 learnings](../impl/learnings/S1-trace-ingestion.md), [campaign synthesis](../impl/learnings/campaign-synthesis.md)
- **Constrains.** [ADR 0002](./adr_0002_decision-attribution-replay.md) (replay manifest), [ADR 0003](./adr_0003_parametric-instrumentation.md) (internal event kind), [ADR 0004](./adr_0004_visualization-tui.md) (what the TUI renders)

## Context

Layer A needs one canonical trajectory representation that every major trace source projects into, that B's replay and F's signals join without breaking changes, and that behaves like a dataframe because the library's identity is "the pandas of agent traces". Spike S1 proved the load-bearing assumptions on real exports: a Langfuse export and an OpenInference/OTLP capture of the same run normalize into one dataframe with zero unexpected divergences under the stage-9 policies; the replay-capture gap is real and must be represented, not papered over; and campaign-shaped parametric spans join additively. The published specs are unstable (OTel GenAI conventions are stability-level Development in a newly separated repository; OpenInference has no stability labels), so the schema must own its stability rather than inherit any single spec's.

## Decision

### The stage-9 canonical model is the schema

One run envelope plus a tree of events in four kinds (`run`, `llm`, `tool`, `internal`), the common envelope (identity/linkage, declared `time_precision`, derived `order_key`, status, source provenance), the LLM/tool payloads, the nullable-with-provenance replay manifest (per-slot `captured/derived/not_captured/not_applicable`), and the reserved parametric channel with required provenance block and `numerics.mode = exact | tolerance`. The five ratified normalization policies (single root; declared precision; typed values `{raw, parsed, media_type, source_type}`; sampling-origin enum; cost/registry as extensions) and the S1 amendments (`name` is display-only; alignment keys on kind + tree position) are normative. [Stage 9](../research/9-trajectory-schema-canonicalization.md) is the spec of record; this ADR commits it.

### Representation: one events dataframe with typed accessors

`Trajectory` wraps a single pandas dataframe (one row per event, envelope fields as columns, structured payloads as dict-valued columns) plus typed accessors (`traj.events.llm`, `traj.replay`, `traj.signals`) that project views. Canonical JSON is the interchange form; dataframe → JSON → dataframe is lossless (S1-proven, digest-stable).

### Ingestion: bundled thin adapters, spec-pinned, contract-tested

Adapters ship inside the library (`langfuse`, `otlp` covering OTel GenAI + OpenInference, `json` with declared mapping as the escape hatch). Each adapter pins the spec/source versions it was validated against (S1's measured pins are the initial set) and carries contract tests against immutable fixture exports; a semconv/source bump is a test-gated adapter change, not a silent drift. Adapters are mechanical (~130 lines each in S1) — smallness is a maintained property.

### The replay manifest ships as schema plus capture guidance

Every LLM event carries the manifest with explicit per-slot states. Because S1 measured that no current instrumentation captures seed, policy revision, tool implementation versions, snapshots, evaluator version, or state hashes, the library also ships a short capture-side recommendation (what an agent should additionally record to reach replay-grade traces) — the schema exposes the gap; the guidance closes it for users who control their agent.

## Consequences

- B's checkpoint objects and F's span shapes are fixed by this schema; both were co-validated in the campaign, so no rework is expected.
- Users get stable canonical fields regardless of upstream spec churn; the cost is adapter maintenance, bounded by contract tests and pinned fixtures.
- Provenance-everywhere makes the dataframe slightly heavier than a naive flattening; this is the price of the honesty contract and is deliberate.
- The `json` mapping escape hatch prevents the adapter set from becoming a gate on adoption.

## Alternatives considered

- **Adopt OpenInference (or OTel GenAI) wholesale as the canonical schema.** Rejected: both are moving targets (Development stability, repository moves), neither carries the replay manifest, typed-value, sampling-origin, or numerics semantics the campaign proved necessary; S1's coverage matrix shows neither is a superset of the required core.
- **Adopt the Langfuse export shape.** Rejected: vendor-specific, injects wrapper defaults, parses lexical values, omits finish reason/completion id — S1 documented each of these as hazards requiring normalization.
- **Multi-table relational representation (events/messages/tools as separate frames).** Rejected for v1: heavier API surface for marginal gain at trajectory scale; dict-valued payload columns with typed accessors preserve the single-frame pandas idiom. Revisit if trajectory sizes demand it.
- **Adapter plugins via entry points (third-party adapters out of tree).** Deferred, not rejected: the entry-point mechanism can be added compatibly later; starting bundled keeps the contract-test discipline in one place.

## Follow-up

- Semconv-bump contract test in CI against the pinned OTel GenAI repository.
- Phoenix/Weave export fixtures added to the contract-test set when first requested by a real user.
