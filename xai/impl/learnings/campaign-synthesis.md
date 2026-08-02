# Full spike-campaign synthesis — all seven spikes complete; A, B, and F are ADR-ready

This document consolidates the entire validation campaign: S3/S4/S5 (parametric instrumentation, executed 2026-08-01 with a GPU tier — synthesized in [S3-S5-campaign-synthesis](./S3-S5-campaign-synthesis.md), which remains the F-instrumentation detail) and S1/S2/S7/S6 (executed 2026-08-02/03, orchestrated as two parallel phase-gated Codex tracks with milestone barriers). Per-spike detail: [S1](./S1-trace-ingestion.md), [S2](./S2-ablation-replay-contract.md), [S7](./S7-uncertainty-calibration.md), [S6](./S6-first-probe-validation.md). Every load-bearing assumption behind the three-layer arc has now been either validated on runnable evidence or precisely refuted before anything was claimed publicly.

## The one-line result

**A is buildable, B's statistical contract holds, and F splits cleanly into a validated cheap always-on channel and a probe tier that is honest about not yet earning its keep at small scale** — with every boundary (replay capture gaps, serving-regime numerics, probe transfer, the mismatch detector) mapped by measurement rather than assumption.

## Layer verdicts

- **A (trajectory diagnostics) — unblocked by S1 + stage 9.** One canonical schema (four event kinds, five ratified normalization policies, provenance everywhere) is populated from both major source families by ~130-line adapters with zero unexpected divergences; the parametric channel joins additively without schema change. The empirical replay boundary is a first-class finding: no current instrumentation captures seed, policy revision, tool implementation versions, or state hashes — B-grade replay implies a capture-side recommendation, not just ingestion.
- **B (decision attribution) — unblocked by S2.** The four-method kernel + sequential two-arm engine delivers controlled error rates at scale (FPR 0/400, coverage 97–100%, sequential-stopping coverage 94.9% vs 95 nominal) and abstains at the falsifiability boundary (1,199/1,200 at Δ=δ). It localizes a real planted wrong-context effect on a live model. The F→B synergy is now arithmetic: a good cheap prior saves ~25% of replay cost, a bad one costs ~24%, and a residual-channel prior would cost ~5.75× what it saves — **uncertainty guides, replay decides, residual confirms.**
- **F (parametric instrumentation) — two-tier verdict.** The *cheap channel* (zero-patch entropy/margin, ~-23% with graphs on) is validated end to end: `q90_logit_entropy_raw` is a transfer-stable ranker on a balanced workload (AUROC 0.88–0.91 across temperatures), its ranking survives measured bf16 drift, and non-completion/spiral risk emerges as a first-class derived signal. The *probe tier* (residual channel, ~-66% eager-only) is mechanically proven (S3–S5) but scientifically restricted at 0.6B: SEP is an in-distribution restricted prototype (SLT layer 17, AUROC 0.711) that does not beat the free channel off-distribution; the refusal direction is a clean negative causal reproduction. Probe-tier value rests on larger checkpoints and per-deployment validation.

## The negative results that shape the public story

These were bought cheaply now instead of expensively after launch:

1. **The mismatch detector is not validated.** The three-channel conjunction (stated ∧ internal ∧ replay) lost to the single internal channel (F1 0.242 vs 0.571) because stated confidence is informationless at 0.6B and neither remaining channel separates confidently-wrong from honestly-uncertain. `STATED_VS_INTERNAL_MISMATCH` stays out of the shipped diagnostic taxonomy pending a larger-model stated channel.
2. **Learned probes do not automatically beat free telemetry.** SEP's cross-task transfer is near-chance and does not out-rank q90 entropy where it matters (off-distribution); probe position validity inverted versus the paper (SLT works, TBG near-chance). Per-checkpoint measured validation is the only shippable form.
3. **The causal bar is real.** The refusal-direction recipe's own selection threshold rejected every candidate on this model, and the relaxed candidate failed its controls — exactly the outcome the norm-matched-control battery exists to catch.
4. **Calibrated probabilities need a numerics contract; rankings do not.** bf16 drift leaves AUROCs intact (worst losses 0.004–0.018 across S6/S7 cells) but breaks ECE (worst +0.136): `*_raw` ranking signals ship under batching; `*.calibrated` fields require a declared batch-invariance/regime contract.

## Cross-cutting design facts for the ADRs

- **Provenance is the schema's spine:** per-slot replay states, sampling origins, typed values, source-assigned display names, the `exact|tolerance` numerics flag, and fail-closed probe registries all reduced to one principle — absence and derivation are always explicit.
- **Cost asymmetry orders the layers:** free API/logprob telemetry → ~-23% zero-patch exact uncertainty → replay budgets (16–256/arm, taxonomy-governed) → ~-66% opt-in residual probes. Each tier must justify itself against the one below; two of the campaign's negatives came from a higher tier failing to.
- **Interface findings to fold in:** a named no-intervention/reference-arm operation alongside the four-method kernel (S7-P4); `internal` as a canonical event kind (S1-P4); versioned runtime bindings, typed budget dimensions, prior-quality monitoring, and abstention-escalation policy in B's result contract (S2-P4).

## Orchestration learnings (the campaign itself)

Two parallel long-lived Codex sessions with per-phase briefs, orchestrator-reviewed gates, named steer triggers, and milestone barriers completed all four spikes in one day. Steers that changed outcomes: the S7 workload rebalance (thinking mode — without it the F channel would have been wrongly written off as near-chance), the S1 name-field policy, the S6-P2 cross-task comparison design, and the S6 background-job recovery. Operational rule earned the hard way: any compute expected to outlive a Codex session must be `nohup setsid`-detached (verify PPID 1) with per-unit checkpoints, resume flags, and atomic final assembly.

## What remains before/alongside the ADRs

- **Deferred mechanical item:** TP/PP rank cardinality (stage-12 assertion #10) — short multi-GPU session, blocks nothing.
- **Highest-value follow-up experiment:** repeat S6 (+ S7's stated-confidence channel) on a 7–8B checkpoint — every restricted/negative probe verdict is plausibly a scale artifact, and the harnesses are reusable as-is.
- **Then:** the A, B, and F ADRs (all unblocked; F's probe channel documented as restricted-prototype tier), `plan/proposed-split.md`, and implementation.
