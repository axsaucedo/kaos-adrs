# Spike S2 — Context ablation replay with a statistical contract

**Validates:** C3 — that reference-arm + intervention-arm replay with a real statistical contract produces falsifiable effect estimates with controlled error rates, and abstains for the right reasons when it cannot. Gates the **B ADR**.
**Research inputs:** [stage 10](../research/10-causal-attribution-methods.md) (estimand, arms, Wilson intervals, budgets, result taxonomy, replay manifest, adapter interface), [S3–S5 synthesis](../impl/learnings/S3-S5-campaign-synthesis.md) (cost asymmetry: uncertainty guides, residual confirms), S1 (manifest slots the harness consumes).
**Execution:** phase-gated Codex sessions on the A/B track session (after S1's gates); per-phase briefs, orchestrator reviews each gate. Scratch under `ethical/xai/tmp/spikes/s2/`; reports at `tmp/spikes/s2/PHASE<n>-REPORT.md`; learnings to `impl/learnings/S2-ablation-replay-contract.md`.

## What this spike must prove

1. The stage-10 kernel is implementable small: `restore(checkpoint) → apply(intervention) → run_suffix(policy, budget) → evaluate(trajectory)` against a **user-supplied adapter** — xai never becomes the runtime.
2. The statistical contract holds empirically: risk-difference estimand, both arms replayed, Wilson intervals, fixed batches of ~16 with sequential stopping, per-arm cap ~256 (screen/standard budget tiers), Holm adjustment for a small confirmatory candidate set, and the ten-state result taxonomy (`material_effect` … `budget_exhausted`).
3. Against **planted synthetic effects of 0, 0.1, 0.25, 0.5**: empirical false-positive rate is controlled at nominal, interval coverage is nominal, and when the budget cannot resolve an effect the harness returns `insufficient_evidence` — it abstains rather than reports.

## The synthetic testbed (ground truth by construction)

A seeded stochastic mock agent whose failure probability is an explicit function of which context items are present — a unit SCM per stage 10's evidence ladder. One designated context item shifts P(failure) by the planted delta; decoy items have zero effect; one correlated pair tests the group-intervention safeguard. Replays are cheap (no real LLM), so the calibration experiment can run thousands of trials — the point is validating the **statistics**, not the model. A second, small real-model variant (pinned local model, seeded, one real prompt-ablation case) closes the loop that the adapter interface fits a real replay, without pretending to measure calibration on it.

## Verification loops

1. **FPR control:** planted effect 0, many independent harness runs → fraction reporting `material_effect` must be ≤ nominal α (binomial CI around it).
2. **Coverage:** across planted 0.1/0.25/0.5, the reported interval contains the true delta at ≥ nominal rate.
3. **Abstention correctness:** small effects under the screen budget must land in `insufficient_evidence`, not `negligible_effect` — the two are asserted as distinct outcomes; `negligible_effect` only when the interval is inside ±δ.
4. **Taxonomy reachability:** `restoration_failed`, `low_replay_fidelity`, and `budget_exhausted` are each triggered deliberately (broken checkpoint, drifted reference arm, tiny cap) and produce the right status — no state is dead code.
5. **Result object:** every report carries effect, CI, per-arm replay counts, fidelity level, multiplicity adjustment, and status — the stage-10 JSON shape.

## Phases

1. **P1 — Testbed + adapter kernel.** The seeded synthetic agent, the four-method adapter interface, checkpoint/intervention objects consuming S1's manifest field names. Gate: deterministic replay under a fixed seed; planted effect recoverable by brute force (large-N sanity run).
2. **P2 — Statistical engine.** Two arms, Wilson intervals, batch-16 sequential stopping against the δ-threshold decision rule, budget tiers, Holm for the candidate set, full taxonomy mapping. Gate: unit tests on the decision rule (synthetic binomial draws, no agent) — stopping and mapping behave as specified.
3. **P3 — Calibration experiment.** The full grid: planted {0, 0.1, 0.25, 0.5} × budget tiers × ≥200 replications; measure FPR, coverage, abstention rate, mean replays-to-decision (the stopping-cost curve). Loops 1–4. Gate: the calibration table — the core deliverable of the spike.
4. **P4 — Guided screening + real-adapter case.** (a) Order candidates by a cheap per-step uncertainty proxy (planted to correlate with the true cause, then planted to anticorrelate) and measure replays-to-decision vs unguided — quantifying the F→B synergy and its failure mode when the prior is wrong; note the campaign's cost asymmetry (the residual channel at ~-66% throughput cannot be the prior; uncertainty at ~-23% or free API level can). (b) The one real-model adapter case. Gate: guided-vs-unguided table + real-case transcript; final report.

## Steer triggers

- **Coverage below nominal in P3** — the interval method or the stopping rule is biased (sequential stopping can distort coverage); stop, switch to a group-sequential-corrected interval before rerunning the grid, and record the correction as a B-ADR requirement.
- **FPR above nominal with Holm applied** — the candidate-set multiplicity model is wrong; re-derive before continuing.
- **Abstention degenerate** (screen tier abstains on 0.5 effects, or standard tier never abstains on 0.1) — re-examine δ and batch sizing; the budget defaults in the B ADR come from this observation.
- **Adapter interface fails the real-model case** (something the four methods cannot express) — that is a stage-10 interface finding; amend the interface before P4 completes, not after the ADR.

**Fail-fast:** if P2's decision rule cannot pass its unit tests within the session budget, stop and report — the contract, not the code, is then wrong. Each phase self-limits at ~45 min wall-clock before reporting for steering.
