# Spike S1 — Trace ingestion → trajectory dataframe (co-developed with stage 9)

**Validates:** C1 — that one canonical normalized trajectory schema can be populated from at least two real trace sources with the same logical events landing in the same fields, while carrying the replay-manifest slots (stage 10) and the reserved parametric evidence channel (stage 12 + S3–S5 campaign shape). Gates the **A ADR**.
**Research inputs:** [stage 9 brief in the research plan](../research/0-research-plan.md), [stage 10](../research/10-causal-attribution-methods.md) (replay manifest), [stage 12](../research/12-otel-propagation-and-transport.md) (canonical span shape), [S3–S5 synthesis](../impl/learnings/S3-S5-campaign-synthesis.md) (cost channel, provenance block, numerics flag).
**Execution:** phase-gated Codex sessions, one resumable session for the A/B track; per-phase briefs only, orchestrator reviews each gate. Scratch under `ethical/xai/tmp/spikes/s1/`; per-phase reports at `tmp/spikes/s1/PHASE<n>-REPORT.md`; learnings to `impl/learnings/S1-trace-ingestion.md`; the schema spec itself is the stage-9 document (`research/9-trajectory-schema-canonicalization.md`), drafted by the orchestrator from the phase evidence.

## What this spike must prove

1. One real agent run, captured through **two independent source paths** (a Langfuse export and raw OTLP/OpenInference), normalizes into **one trajectory dataframe** with the same logical events in the same fields.
2. The schema carries stage 10's **replay-manifest slots** (model-visible message state, tool schemas/versions, sampling parameters, policy identity, evaluator version, state hashes) — populated where the source provides them, **explicitly null** where it does not; the coverage gap per source is itself a deliverable.
3. The reserved parametric channel matches what the campaign proved necessary: `xai.parametric.observe` **and** the sibling `xai.cost.observe`, a required **provenance block** (engine+version, backend/graph mode, attribution mode, build-ID), and the **epistemic numerics flag** (`exact` vs `tolerance`).

## Verification loops

1. **Cross-source alignment:** for every logical event (LLM call, tool call, tool result, agent step boundary), assert the two adapters produce rows with equal values in the canonical fields (id-mapped, order-preserved); differences are enumerated, not averaged away.
2. **Round-trip fidelity:** dataframe → canonical JSON → dataframe is lossless for canonical fields.
3. **Manifest audit:** every replay-manifest slot is asserted populated-or-null with a per-source provenance tag — no silently missing columns.
4. **Channel reservation test:** synthesize a campaign-shaped `xai.parametric.observe`/`xai.cost.observe` span pair (from the S3 evidence fixtures) and assert it joins the trajectory without schema change.

## Phases

1. **P1 — Real run, dual capture.** Build a minimal real tool-using agent (OpenAI SDK loop, 2–3 tool calls, against a local pinned small model or recorded fixture) instrumented twice: (a) Langfuse SDK → Langfuse export (self-hosted container, then export API/file), (b) OpenInference/OTel instrumentation → OTLP file exporter via a local collector. Gate: one run, two export artifacts on disk, both containing the same logical events (eyeballed count match), plus a written inventory of what each source actually contains.
2. **P2 — Concrete span-shape extraction.** From the two artifacts plus the published OTel GenAI semconv and OpenInference specs (pinned versions), extract the concrete field inventories and produce the **coverage matrix**: candidate canonical field × source → present/derivable/absent. Gate: the matrix plus a proposed minimal canonical field list; the orchestrator drafts stage 9 from this before P3 proceeds.
3. **P3 — Two adapters, one dataframe.** Implement the two adapters into the candidate schema; run verification loops 1–2. Gate: alignment assertions pass or the divergences are precisely documented as schema decisions for stage 9.
4. **P4 — Manifest + parametric channel.** Add replay-manifest columns (loop 3) and the reserved channel test (loop 4), including provenance block and numerics flag. Gate: full assertion table; final report feeding the stage-9 spec and the S1 learnings doc.

## Steer triggers (rewrite the next brief instead of advancing verbatim)

- The two sources disagree on **event boundaries** (e.g. Langfuse observation nesting vs OTel span tree) such that id-mapping needs heuristics — stop, decide the canonical event model in stage 9 first.
- Langfuse export lacks fields the replay manifest needs (likely: tool schema versions, sampling params) — decide per-field whether the schema demands them (null-with-provenance) or drops them, before P4.
- Tool-call ↔ tool-result linkage is not reconstructible from one source — this reshapes the canonical schema's linkage keys and must be settled before adapters harden.

**Fail-fast:** if P3 cannot align the two sources on even the LLM-call core (model, messages, usage) within the session budget, stop — that is a finding that the canonical schema needs a lossy-union design, and it goes to the orchestrator, not into more adapter code. Each phase self-limits at ~45 min wall-clock before reporting for steering.
