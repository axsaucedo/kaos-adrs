# Spike S6 — First-probe validation (Semantic Entropy Probe + refusal direction)

**Validates:** C4's learned-probe claims — whether either recommended first probe passes its gate on a pinned checkpoint with honest statistics, in the numerical regime it would actually serve in. Runs **after S7** (the cheap channel is validated first; this is the expensive opt-in tier, carrying the measured ~-66% eager-mode cost when served live). Gates the F **probe channel** together with S7.
**Research inputs:** [stage 11](../research/11-probe-and-latent-monitor-science.md) (SEP as first target with the MIT pipeline, refusal direction as second with the Apache-2.0 causal-validation pipeline, shipped-claim wording, probe-registry provenance), [S3–S5 synthesis](../impl/learnings/S3-S5-campaign-synthesis.md) (bf16 activation drift ~0.05, ecosystem `query_start_loc`/`req_ids` convergence, opt-in eager framing).
**Execution:** phase-gated Codex sessions on the F track session (after S7 P3); per-phase briefs, orchestrator reviews each gate. Scratch under `ethical/xai/tmp/spikes/s6/`; reports at `tmp/spikes/s6/PHASE<n>-REPORT.md`; learnings to `impl/learnings/S6-first-probe-validation.md`. Local CPU; activations from an HF eager harness on a pinned small checkpoint (probe validity is a statistical property of the checkpoint, not of the serving engine — the serving-regime question is handled by the perturbation cell, using the campaign's measured GPU deltas).

## What this spike must prove (per-probe gate, pass or documented research-only)

1. **Semantic Entropy Probe (a):** reproduced from its MIT-licensed recipe on a pinned checkpoint at the token-before-generation position (second-last-token variant retained for comparison). Measured on held-out data **and on agent-relevant traces**: AUROC/AUPRC, Brier after fitting a separate calibrator, and TPR at fixed low FPR. Ships as `prototype` with stage 11's exact claim wording ("model- and checkpoint-specific linear estimate of semantic entropy … not a probability that the answer is false") — or fails its gate and is documented research-only.
2. **Refusal direction (b):** reproduced from the Apache-2.0 pipeline **including the causal checks** — signed addition and projection removal produce monotonic behavioral effects, against norm-matched random-direction controls, with collateral-loss measurement. This is the reference case for causal validation, not a harmfulness detector, and its claim wording says so.
3. **Serving-regime robustness (both):** perturb validation activations by the campaign-measured GPU deltas (residual scalar drift up to ~0.05, tolerance-not-bitwise) and re-check AUROC and calibration — a probe validated only on clean fp32 activations is not validated for deployment. Acceptance thresholds are tolerance-based and token-aware throughout; never bitwise.
4. **Registry provenance:** each probe artifact carries the full stage-11 provenance metadata (checkpoint hash, layer, position convention, training data recipe, validation distributions, calibrator id) and a load-time compatibility check that **rejects** a mismatched checkpoint.

## Verification loops

1. **Label fidelity (SEP):** semantic-entropy training labels computed per the source recipe (N sampled generations per prompt, semantic clustering); a subsample is manually audited for clustering sanity before any probe is trained on them.
2. **Held-out + shifted evaluation (SEP):** metrics on the recipe's own distribution, then on an agent-relevant trace set (tool-augmented QA steps from the S1/S7 fixtures), then under prompt/decoding shift — three columns, no cherry-picking.
3. **Causal battery (refusal):** dose-response monotonicity for signed addition; behavioral suppression under projection removal; both null under norm-matched random directions; collateral degradation quantified on a neutral task.
4. **Perturbation cell (both):** loop 2/3 headline metrics recomputed under activation noise at the measured GPU magnitudes; a probe passes only if its verdict survives.
5. **Compatibility rejection:** loading either probe against a different checkpoint/revision fails loudly with the provenance diff.

## Phases

1. **P1 — SEP data generation (started early, in M2, alongside S7: it is the slow part).** Pinned checkpoint; prompt set assembled; N-sample generation sweep for semantic-entropy labels; clustering + label audit (loop 1). Gate: labelled dataset with audit note — no probe training yet.
2. **P2 — SEP training + evaluation.** Probe fit at both positions; calibrator fit separately; loop 2's three-column evaluation; TPR@fixed-FPR. Gate: the SEP metric table and a provisional pass/research-only verdict.
3. **P3 — Refusal direction.** Extraction per the published pipeline; loop 3 in full. Gate: causal-battery table with controls — the pass criterion is the *controls*, not the headline effect.
4. **P4 — Robustness + registry + verdict.** Loop 4 perturbation cell for both probes; loop 5 compatibility rejection; final per-probe verdicts with claim wording; eager-diagnostic framing (cost note pointing at the measured ~-66%, extraction bookkeeping aligned with the vLLM-Lens/IBM `query_start_loc`/`req_ids` convention rather than reinvented). Gate: final report; learnings doc; the F-ADR probe-channel input.

## Steer triggers

- **Loop 1 clustering audit fails** (labels don't reflect semantic multiplicity on this small model) — stop; a SEP trained on bad labels is worse than no probe. Either fix the clustering model or pick the recipe's own evaluation model size; do not proceed to P2 on unaudited labels.
- **P2 passes held-out but fails agent-relevant traces** — that is the *expected* stage-11 risk (cross-distribution calibration); the verdict is "prototype, listed distributions only", and the learnings must say the agent-trace gap explicitly. Do not iterate on the agent set to force a pass.
- **P3 effects present but controls also fire** — the direction is not specific; verdict research-only; this is a headline finding for the F ADR (the causal-validation bar is real).
- **P4 perturbation flips a verdict** — the probe requires the exact-numerics (CPU/eager) regime; it ships, if at all, gated on the `exact` numerics flag from S1's schema.
- **CPU sampling budget makes P1 infeasible at useful N** — shrink the prompt set before shrinking N-per-prompt (label quality beats dataset size); if still infeasible, that is a real finding about probe-recipe cost, reported, not silently degraded.

**Fail-fast:** if the published pipelines cannot be reproduced at all on the pinned checkpoint (recipe rot, dependency breakage) within one session budget per probe, stop and report — reproduction failure of the *reference* pipelines is itself an F-ADR input. Each phase self-limits at ~45 min wall-clock before reporting for steering.
