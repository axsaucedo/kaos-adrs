# Spike S7 — Logit-uncertainty calibration and the mismatch detector

**Validates:** C4's cheap, always-on channel — whether server-side entropy/margin, honestly named as raw telemetry, supports a validated per-deployment calibration and a defensible multi-channel mismatch diagnostic for layer A. Runs **before S6** (this is the first shippable F increment; S6's residual probes are the expensive opt-in tier). Gates the F **probe channel** together with S6.
**Research inputs:** [stage 11](../research/11-probe-and-latent-monitor-science.md) (probe-free channel, the runnable-spike verification recipe, mismatch-detector reframing), [S3 learnings](../impl/learnings/S3-parametric-span.md) (zero-patch extraction paths, measured bf16 drift ~0.106 nats, the near-zero-margin token tie), [S3–S5 synthesis](../impl/learnings/S3-S5-campaign-synthesis.md).
**Execution:** phase-gated Codex sessions, one resumable session for the F track; per-phase briefs, orchestrator reviews each gate. Scratch under `ethical/xai/tmp/spikes/s7/`; reports at `tmp/spikes/s7/PHASE<n>-REPORT.md`; learnings to `impl/learnings/S7-uncertainty-calibration.md`. Local CPU only — the GPU behaviors are already priced; their measured deltas are injected as perturbations.

## What this spike must prove (or honestly disprove)

1. On one concrete workload with deterministic correctness labels, some aggregation of per-step entropy/margin/top-1 **ranks errors better than chance** (AUROC materially > 0.5) — stage 11 documents workloads where logit statistics sit at 0.504–0.569, so a near-chance result is a *legitimate finding*, not a failure of the spike: the channel then ships as raw telemetry only, and S6's learned probes carry the ranking burden.
2. Where ranking works, a **fitted monotonic calibrator** (isotonic) achieves useful ECE on a held-out later window, and the calibration **survives the serving numerical regime**: perturbing entropies by the measured bf16 batching drift (~0.106 nats) and re-evaluating must not collapse ECE/AURC — else the channel declares a batch-invariance contract as a deployment precondition.
3. The **near-zero-margin tie case** is handled: steps with |top-2 logit margin| below a tie threshold get an explicit `tie` flag, because the campaign showed the sampled top token is nondeterministic there — a mismatch detector must never read a tie as model conviction in the emitted token.
4. The **mismatch conjunction** (stated confidence high ∧ internal uncertainty high ∧ replay instability high) identifies genuinely problematic steps better than any single channel — or evidence it does not, before it is ever claimed publicly. Replay instability is the *budgeted confirmatory* channel sourced from S2's harness (the cost asymmetry: cheap channels lead, replay confirms).

## Workload and extraction

Pinned small model (Qwen3-0.6B, the campaign's model, revision-pinned) on a labelled short-answer task with deterministic scoring (a fixed sampled subset, order-pinned, of a public QA/arithmetic set — exact choice recorded in P1). Signals extracted server-side via the campaign-proven zero-patch path (llama.cpp public API or the vLLM CPU logits-processor from S3's fixtures — reuse, don't rebuild). Replay each held-out prompt across a temperature/sampling grid (≥3 temperatures × 2 sampling configs) with per-step full-vocabulary entropy, top-2 logit margin, and top-1 probability captured per stage 11's field names (`*.raw`, never "confidence").

## Verification loops

1. **Extraction fidelity:** server-extracted signals match an HF eager fp32 harness within declared tolerance on a probe subset (the S3 loop, reused).
2. **Metric battery:** per candidate aggregation (mean, max-entropy, min-margin, quantiles, length-normalized sum) — AUROC, AUPRC, Brier, ECE after isotonic calibration, risk-coverage AURC, threshold stability across the temperature grid.
3. **Temporal split:** calibrate on the first window, evaluate on a later window — drift is measured, not assumed away.
4. **Drift robustness:** re-run the battery with entropy perturbed ±0.106 nats (and margin-derived scores through the tie flag) — the deployment-regime cell.
5. **Conjunction ablation:** detector variants {stated-only, entropy-only, replay-only, pairwise, triple} on a step set with planted problematic steps — precision/recall per variant.

## Phases

1. **P1 — Workload + extraction dataset.** Pin model/task/split; run the grid; land one tidy dataset (per-step signals × config × outcome labels) plus loop 1. Gate: dataset on disk with a schema note and fidelity assertion table.
2. **P2 — Calibration battery.** Loops 2–3 over all aggregations; pick (or reject) a champion aggregation with the full table. Gate: the metric table and an explicit verdict sentence — "ranks errors on this workload" or "near-chance, telemetry-only".
3. **P3 — Serving-regime robustness + ties.** Loop 4; implement and evaluate the tie flag (threshold swept, tie prevalence reported); state the batch-invariance verdict. Gate: robustness table; the channel's shipping claim drafted in stage-11's honest-naming form.
4. **P4 — Mismatch conjunction (runs in M3, after S2 delivers the replay harness).** Planted problematic steps (wrong-but-confident answers via prompt manipulation); stated confidence extracted from verbalized self-reports; replay instability from S2's harness on the same steps; loop 5. Gate: the conjunction-vs-single-channel table — the stage-11 mismatch-detector verdict.

## Steer triggers

- **P2 near-chance across all aggregations** — do not iterate aggregations hoping; accept the telemetry-only verdict, bring S6 forward with higher priority (the learned probe becomes the only ranking candidate), and reshape P4 to test the conjunction with entropy as a *weak* channel.
- **P3 drift perturbation collapses calibration** — the F ADR must require the batch-invariance contract or per-regime calibrators; P4's detector thresholds must be re-fit under perturbation.
- **Tie prevalence non-negligible at sampling temperatures** (>a few % of steps) — the tie flag graduates from special-case to a first-class schema field; feed back to S1's channel shape.
- **Stated-confidence extraction unreliable** (model won't verbalize consistently) — swap to a structured self-report prompt format before running the conjunction; do not proceed with a noisy stated channel.

**Fail-fast:** if P1's extraction cannot pass loop 1 within the session budget, stop — the fixtures from S3 are the known-good path and divergence means an environment problem, not a research finding. Each phase self-limits at ~45 min wall-clock before reporting for steering.
