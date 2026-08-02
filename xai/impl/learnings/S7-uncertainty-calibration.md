# S7 learnings — logit-uncertainty calibration and the mismatch detector (gates the F cheap channel)

Spike S7 executed 2026-08-02 in four phase-gated Codex sessions on the F track (P4 cross-track on the A/B session, reusing S2's kernel). All four phases passed — P4 with an honest negative verdict. Evidence in `tmp/spikes/s7/` (datasets, battery, stratification/perturbation/tie analyses, conjunction harness, four phase reports). Model throughout: Qwen3-0.6B (S3-pinned revision), S4 F16 GGUF on the llama.cpp `b10217` Metal harness; signals extracted server-side pre-sampling; fidelity vs HF eager fp32 max delta 0.0038 nats.

## Verdict

**The cheap always-on channel is validated — with a precise, narrower-than-hoped claim.** On a balanced thinking-mode workload, `q90_logit_entropy_raw` is a transfer-stable error ranker (cross-temperature AUROC 0.884 [0.776, 0.960] and 0.906 [0.792, 0.987]); its **ranking survives the bf16 serving regime but calibrated probabilities do not**; and the three-channel mismatch conjunction **did not beat the single internal channel** on this workload — the stage-11 skepticism was warranted and is now measured, before anything was claimed publicly.

## The workload-regime finding (P1→P2 steer)

GSM8K on 0.6B with thinking disabled yields 5.9% accuracy — and on that imbalanced hard slice every aggregation's transfer CI includes chance (consistent with stage 11's near-chance literature results). The steer: same pins, thinking mode enabled (cap 512, `in_thinking` per-step flag). Accuracy rose to 42%, and a champion emerged. **Whether logit uncertainty ranks errors is a property of the workload regime, not of the signal** — the F channel must ship with per-deployment validation, never a blanket claim. The hard slice is retained as adverse telemetry.

## The champion and its honest name

`q90_logit_entropy_raw` (0.9-quantile of per-step full-vocabulary entropy), selected by a pre-declared minimax-transfer rule with CI-clear-of-chance requirement. Two entangled behaviors, separated by stratification (P3):

- **Non-completion detection:** all 239/239 thinking traces that hit the 512-token cap were incorrect; q90-entropy correlates with length (Spearman 0.583). Reasoning "spiral" is itself an agent-relevant trajectory signal — but it must not wear a correctness-probability label.
- **Within-completed ranking:** completed-only AUROC 0.811 [0.622, 0.982] — the signal still ranks correctness conditional on finishing, though held-out negatives are few (n=3).

Shipping form: **trajectory-uncertainty telemetry with validated non-completion/spiral-risk utility, not a general correctness probability** — with calibration scope (model hash, task family, decoding configs, calibration-set id) attached per stage 11's naming contract.

## Serving-regime robustness (the campaign-mandated cell)

Perturbing entropies by the GPU-measured bf16 batching drift (±0.106 nats uniform; Gaussian σ=0.053; 20 repetitions): worst-case champion AUROC loss **0.018** — ranking is robust. Worst-case ECE increase **+0.136** — calibrated probabilities are not. **F-ADR requirement:** `*_raw` ranking signals may ship under batching as-is; any `*.calibrated` field requires a declared batch-invariance/numerical-regime contract. Ties (top-2 margin < τ=0.01) are sparse on this workload and shift the champion by ≤0.003 AUROC, but the tie flag ships anyway: a tie step is never evidence of conviction in the emitted token (the campaign's bf16 tie flipped tokens).

## The mismatch conjunction: an honest negative (P4)

Cross-track test on 60 planted items (problematic / healthy / honest-uncertain), channels: stated confidence (structured 0–10 self-report), q90 entropy, and same-policy replay instability via the S2 kernel (12 fresh replays/item, 720 total):

| Detector | Precision | Recall | F1 |
|---|---:|---:|---:|
| internal (q90) alone | **0.457** | **0.762** | **0.571** |
| replay alone | 0.455 | 0.714 | 0.556 |
| stated alone | 0.293 | 0.571 | 0.387 |
| internal ∧ replay | 0.455 | 0.476 | 0.465 |
| triple conjunction | 0.333 | 0.190 | 0.242 |

The mechanism is visible in the per-class distributions: entropy and replay both separate *healthy* from *unhealthy*, but neither separates *confidently-wrong* from *honestly-uncertain* — and the stated-confidence channel, which would have to carry that separation, is informationless at this model scale (median 5/10 across all classes, inverted means). The conjunction therefore only destroys recall. Additionally, the expensive confirmatory channel (replay, ~4,900 generated tokens/item) did not improve on the free channel it was meant to confirm.

**What this does and does not mean:** stage 7's `STATED_VS_INTERNAL_MISMATCH` diagnostic is not validated on this workload/scale and must not ship as a claimed detector; the constituent channels remain individually useful (internal as the ranking telemetry, replay as causal evidence via S2's contract). Open question for larger models: verbalized confidence may become informative at scale — the harness exists to re-test cheaply.

## Cross-track interface finding (for the B ADR)

The S2 four-method kernel expressed the replay-instability use case unchanged, but same-policy resampling had to be phrased as `apply(context_inclusion/keep)` — semantically valid, slightly artificial. A named no-intervention/reference-arm operation is worth considering while preserving the four-method kernel.

## Flags for the F ADR

- The cheap channel's first shippable increment is exactly as the campaign priced it: raw entropy/margin/top-1 per step, zero-patch, always-on; per-deployment calibration fitted and scoped, or not shipped.
- Non-completion/spiral risk graduates to a first-class derived signal (cap-hit + sustained high entropy), independent of correctness claims.
- The mismatch detector moves to research-status pending a larger-model stated-confidence channel; do not name it in the public diagnostic taxonomy yet.
