# S8 learnings — the end-to-end integration prototype (gate between the ADRs and implementation)

Spike S8 executed 2026-08-03 in five phase-gated Codex sessions on one long-lived context-loaded session. All five phases passed. Unlike S1–S7, the code is committed and reviewable: branch **`spike/s8-integration`** in the `xai` source repo, prototype package `spike_s8/xai_proto/`, six comprehensive commits (`816577f` core → `4b6820a` replay → `50c7473` diagnostics/parametric → `d2c1a1e` TUI → `7da1a4e` demo → `db870bd` hardening). Full suite: 30 tests green including the slow statistical-calibration marker.

## Verdict

**The ADRs and the proposed split assemble into one working system.** A single command (`spike_s8/demo/run_demo.py`) runs the whole arc — generate a real tool-using agent run with OTLP capture → ingest to the canonical dataframe → diagnose → plant-and-localize a wrong-context effect via `explain()` with its statistical contract → attach real uncertainty signals → signal-aware re-diagnosis → static HTML report and the three-pane TUI. Recorded mode is deterministic (two from-scratch runs byte-identical, same `material_effect` verdict); live mode ran against the real Qwen3-0.6B with real tool calls and honestly returned `direction_uncertain` where the evidence did not support more. The split is viable: every seam finding below is an amendment, not a redesign.

## What the prototype proves per ADR

- **ADR 0001:** the schema/ingest/trajectory seams hold under packaging; all S1 assertions pass through the packaged paths; adapters stayed thin.
- **ADR 0002:** the full contract (five-op protocol with `reference_arm`, taxonomy, budgets, guided screening) survives productization; the reduced calibration check (null FPR 0/50, planted-effect power matching S2) runs as a CI slow marker; the live endpoint adapter reproduces S2-P4's localization.
- **ADR 0003:** F-additivity holds byte-for-byte through the package; real S7 signals join as `internal` events; `non_completion_risk` fires on a genuine capped trace; the probe registry fails closed.
- **ADR 0004:** the TUI is buildable strictly over the public API (one API addition was needed — below), snapshot-testable deterministically, and the replay panel's watch-batches-land loop works as designed. The TUI-first decision stands.

## Consolidated seam findings (amendments to the proposed split)

1. **pandas-3 null coercion:** canonical nulls must be object-backed explicitly or serialization silently degrades — `xai/schema` owns dtype policy, stated in the split.
2. **Validate at the canonical-model boundary, not per adapter:** adapters remain thin flat-record builders; schema validation happens once before the dataframe boundary.
3. **Replay provenance is not executable state:** a `not_captured` slot cannot restore a runtime; concrete checkpoints/evaluators/runtime bindings stay adapter-owned and `explain()` must never invent them.
4. **Candidate identity crosses domains:** context-item identities must be shared between trace and application checkpoint; boundaries are never inferred from message strings.
5. **`explain()` needs a public progress stream:** final-result-only forced the TUI toward private access; the batch progress callback (added, backward-compatible) must survive the split — or graduate to an event iterator.
6. **Replay cost needs adapter-reported units:** token/wall-time/monetary ceilings require measured adapter callbacks, not relabeled replay counts.
7. **Fidelity never defaults to perfect:** endpoint action-match rate is null until measured or supplied; only synthetic runtimes may declare 1.0 by construction.
8. **Per-token internal rows are additive but volumetric:** 512 events per 512-token generation — production needs lazy projection/aggregation options while keeping scalar provenance.
9. **Extractor context is signal provenance:** cap-hit detection needs the requested max-step budget carried with the signals; entropy alone cannot infer it.
10. **The live serving boundary, stated honestly:** the stock llama.cpp OpenAI server does not expose per-token logits for the exact endpoint token stream — the demo runs the pinned standalone extractor (same model/seed/task, labeled `s8-live-s7-reproduction`), proving transport and join, not token-identity capture. This is precisely the serve-package integration the split assigns to `packages/xai-serve-llamacpp` (a server-side hook or unified runner), now with a concrete requirement.

## Operational notes

The phase-gated single-session pattern held for code as it did for research: six reviewable commits, each a green-suite gate; the one public-API change arose from a real consumer (the TUI) rather than speculation. `spike_s8/README.md` documents install, both demo modes, test tiers, and the commit-per-phase review guide.

## What this gates

Implementation increment A (0.4.0) can start from this branch's shape with the ten amendments applied; the branch itself remains a prototype (namespace `xai_proto`) and is the reference, not the merge candidate.
