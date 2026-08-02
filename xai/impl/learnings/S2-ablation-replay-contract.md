# S2 learnings — context ablation replay with a statistical contract (gates the B ADR)

Spike S2 executed 2026-08-02 in four phase-gated Codex sessions on the A/B track (per-phase briefs, orchestrator-reviewed gates). All four phases passed. Evidence in the source repo's gitignored `tmp/spikes/s2/` (kernel, engine, calibration grid results, four phase reports).

## Verdict

**S2 passes; the B ADR is unblocked on the statistical contract.** The stage-10 kernel — `restore / apply / run_suffix / evaluate` as a user-supplied adapter, xai never owning the runtime — is implementable small, drives a sequential two-arm risk-difference engine whose error rates hold empirically at scale, abstains for the right reasons at the falsifiability boundary, and runs unchanged over a real llama.cpp model where it localizes a planted wrong-context effect. The F→B synergy is now a measured number, not a thesis.

## The calibration grid (the core result)

4,800 main-grid replications (planted deltas {0, 0.1, 0.25, 0.5} × budget tiers screen/24, standard/128, confirm/256 per arm × ≥300 replications; δ=0.10, α=0.05; Wilson per-arm intervals, Newcombe difference CI, batch-16 sequential stopping, Holm for candidate sets, the full ten-state stage-10 taxonomy):

- **False positives:** 0/400 `material_effect` reports in every null cell (95% upper bound 0.95% — under nominal α).
- **Coverage:** 97.25–100% across all positive-delta cells (nominal 95%); the sequential-stopping bias probe measured coverage at the stopping time at 94.90% vs 95% nominal — no correction needed.
- **The boundary cell (Δ exactly = δ):** 1,199/1,200 abstentions (`insufficient_evidence`), not effect claims — the discipline of saying "we do not know" for the right reason, demonstrated at scale.
- **Deliberate failures:** restoration failure, reference-arm drift, and cost-ceiling levers each mapped to their correct taxonomy status (`restoration_failed`, `low_replay_fidelity`, `budget_exhausted`) 30/30 with diagnostic fields populated. No taxonomy state is dead code.

## The F→B synergy, quantified (Phase 4)

Sequential screening over 8 candidates (1 planted cause, 7 nulls), screen tier, ≥200 replications per ordering:

- A cheap uncertainty prior with rank-biserial correlation **+0.806** to the truth reduces mean screening cost to **0.748×** the uninformed baseline (−25.2%, −73.5 wasted suffix calls).
- An adversarial prior (−0.796) raises cost to **1.237×** (+23.7%) — the failure mode when the cheap channel is wrong is symmetric and real; prior quality must be monitored, not assumed.
- **The cost asymmetry, closed numerically:** at the campaign-measured ~-66% throughput for residual extraction, sourcing the prior from the residual channel over the guided workload would cost ≈5.75× more call-equivalents than the prior saves. **Uncertainty guides (always-on, near-free), replay is the causal evidence, residual confirms after screening** — now arithmetic, not slogan.

## The real-model case

The same four-method interface, unchanged, over Qwen3-0.6B via the S7-pinned llama.cpp Metal runner: a planted wrong-fact context snippet flips the model's answer (Lyon vs Paris); the engine reports the culpable snippet `material_effect` (effect 1.0, 16 replays/arm) and the innocuous snippet as an honest abstention (`direction_uncertain` at the 24/arm screen cap). Restoration fidelity checks (4/4 deterministic action matches) keep the fidelity floor operational even under zero outcome variance from seed coupling.

## Flags for the B ADR

- **CRN conservatism:** paired common-random-number replay makes the independent-arm Newcombe interval conservative; uncoupled adapters (hosted providers with no seed guarantee) need their own calibration cell — seed-coupling mode is an explicit ADR commitment, per Causal Agent Replay's local-vs-hosted distinction.
- **Versioned runtime bindings:** the adapter binds to a specific model/runtime pin; the result object must carry it.
- **Typed budget dimensions:** replay caps and cost ceilings are distinct budget axes and produced distinct taxonomy states; a single opaque "samples" budget would erase that.
- **Prior-quality monitoring and escalation:** guided screening needs a live check that the prior is helping (the adversarial cell shows the cost of not noticing), and a declared escalation policy when high-priority screen candidates abstain (continue, escalate tier, or stop must be caller-declared).
- Boundary-effect workloads (true effect ≈ δ) land in abstention by design; user documentation must set that expectation — it is the contract working, not failing.
