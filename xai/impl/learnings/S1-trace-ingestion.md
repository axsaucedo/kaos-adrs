# S1 learnings — trace ingestion → trajectory dataframe (gates the A ADR)

Spike S1 executed 2026-08-02 in four phase-gated Codex sessions (per-phase briefs, orchestrator-reviewed gates), co-developing [stage 9](../../research/9-trajectory-schema-canonicalization.md). All four phases passed. Evidence lives in the source repo's gitignored `tmp/spikes/s1/` (immutable fixtures, adapters, assertion outputs, four phase reports).

## Verdict

**S1 passes; the A ADR is unblocked on ingestion feasibility.** One deterministic real tool-using agent run, captured independently through a self-hosted Langfuse (`3.224.4`, pinned images) and OpenInference/OTLP (pinned instrumentor + collector), normalizes via two small adapters (125 / 140 lines) into one canonical 31-column dataframe — lossless under JSON round-trip, field-aligned across sources with **zero unexpected divergences** after one schema amendment, carrying the full replay-manifest provenance audit and the campaign-shaped parametric channel.

## What was proven

1. **Dual capture of identical logical structure.** The same scripted agent run (3 LLM calls, 2 tool calls/results, one root) produced matching logical events through both instrumentation paths; a checker asserted counts, root grouping, parent links, messages/usage, and tool payloads on both exports.
2. **Coverage is measured, not assumed.** A 53-row coverage matrix against pinned specs — OTel GenAI at commit `8484f22` (all GenAI span shapes still stability-level *Development*; only the core envelope, `error.type`, `server.*` are Stable), OpenInference `v0.1.31`, Langfuse `3.224.4` export — with every cell evidence-referenced: OTel 37 present/6 derivable/10 absent; OpenInference 30/10/13; Langfuse 30/7/16.
3. **Normalization holds at field level.** Cross-source alignment keys on kind + logical tree position; 84 divergences enumerated, all expected under the stage-9 provenance model (timestamp precision, wrapper-default sampling, finish-reason/completion-id availability, tool-result typing, display names). Round-trip dataframe → canonical JSON → dataframe is digest-stable.
4. **The replay boundary is explicit.** Per stage 10's manifest: messages, tool schemas, and partial sampling parameters are recoverable (`derived`) from both sources; policy identity/revision, seed, tool implementation versions, resource snapshots, evaluator version, and state hashes are `not_captured` **in every evaluated source**, each with a source-specific reason — 72/72 slot leaves explicit, no silent nulls. This is the empirical baseline for what replay-grade capture must add.
5. **The parametric channel joins without schema change.** Campaign-shaped `xai.parametric.observe` + `xai.cost.observe` INTERNAL fixtures (flattened attributes for OTLP; nested `metadata.xai` for Langfuse) ingest as `internal`-kind events joined by run id and parent linkage, preserve the provenance block and `numerics.mode=tolerance` through round-trip, and leave a parametric-free trajectory **byte-for-byte unaffected** — F is additive at the schema level, as designed.

## Findings that changed the schema (folded into stage 9)

- **Event `name` is source-assigned display, not identity.** Instrumentation libraries name the same logical event differently (`OpenAI-generation` vs `ChatCompletion`); alignment must never key on it.
- **`internal` joined the `kind` enumeration** (`run`/`llm`/`tool`/`internal`) as the parametric evidence carrier.
- The five normalization decisions (single root envelope; declared `time_precision` + derived `order_key`; typed-value `{raw, parsed, media_type, source_type}` envelopes; sampling-origin enum; cost/registry as extensions) all survived implementation contact unchanged.

## Notable cross-source hazards for adapter authors

- Langfuse's public trace API returns observations **non-chronologically**; order must be reconstructed from timestamps + parentage. Its export also injects wrapper-default sampling values (`top_p=1`, penalties) the caller never sent, and parses lexical tool outputs into JSON types (`"42"` → `42`) — both must be provenance-tagged, not merged.
- OpenInference preserves the full raw provider response (finish reason, completion id derivable); the Langfuse export does not — nullable-with-provenance is the only honest representation.
- Timestamp precision differs by three orders of magnitude (ns vs ms); declaring precision beats pretending uniformity.

## Flags for the A ADR

- The canonical core (identity/linkage, kinds, full message + tool-schema state, model identity, sampling with origins, usage, typed tool payloads, status, timing) is populatable from both major source families today; adapters are small and mechanical once the five policies are fixed.
- Replay-grade capture (seed, policy revision, tool implementation versions, state hashes) does not exist in current instrumentation ecosystems — layer B's manifest requirements imply an *capture-side* recommendation (what an agent should additionally record), not just an ingestion feature.
- The OTel GenAI conventions are still Development-stability and now live in a separate repository; adapter versioning must pin spec commits, and a semconv-bump contract test belongs in the A implementation plan.
