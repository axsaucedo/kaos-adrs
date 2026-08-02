# ADR 0002 — Decision attribution via counterfactual replay (layer B)

- **Status.** Proposed
- **Date.** 2026-08-03
- **Depends on.** [stage 10](../research/10-causal-attribution-methods.md), [S2 learnings](../impl/learnings/S2-ablation-replay-contract.md), [S7 learnings](../impl/learnings/S7-uncertainty-calibration.md) (interface finding, prior sourcing), [ADR 0001](./adr_0001_trajectory-schema-and-ingestion.md)
- **Constrains.** [ADR 0004](./adr_0004_visualization-tui.md) (the replay debug panel renders this contract's result objects)

## Context

Layer B answers *why* — which context item, step, or component caused an outcome — in a way that is falsifiable, which no observability vendor and no LLM-judge "root cause" feature offers. Stage 10 narrowed this to a strict statistical contract; spike S2 implemented and calibrated that contract at scale (FPR 0/400, coverage 97–100%, boundary abstention 1,199/1,200, all taxonomy states reachable, a real-model case localized), and S2/S7 surfaced concrete interface findings. The risk to manage is scope creep toward an agent runtime; the discipline is that xai only analyzes.

## Decision

### The kernel is a user-supplied adapter with five operations

`restore(checkpoint) / apply(intervention) / run_suffix(policy, budget) / evaluate(trajectory)` plus a named **`reference_arm()`** no-intervention resampling operation (S7-P4 finding: forcing same-policy resampling through `apply(keep)` is semantically strained). xai never executes agents itself; adapters bind to the application, a benchmark harness, or an OpenAI-compatible endpoint. Checkpoints and interventions are dataclasses aligned with the ADR-0001 replay manifest; every adapter declares a **versioned runtime binding** (model/runtime pins) that is stamped into results.

### The statistical contract is the S2-calibrated engine, unchanged

Risk-difference estimand, reference + intervention arms, Wilson per-arm intervals with Newcombe difference CIs, sequential batches of 16 against a caller-declared practical threshold δ, budget tiers (`screen` 24/arm, `standard` 128, `confirm` 256, `custom`), Holm for confirmatory candidate sets with exploratory results retained alongside, and the full ten-state result taxonomy as the return type. The empirical calibration table from S2 ships in the docs as the contract's evidence. Sequential stopping was measured at 94.9% vs 95% nominal coverage — no correction, and the probe that would detect future degradation stays in the test suite.

### Budgets are typed; abstention has a declared escalation policy

Replay caps and cost ceilings are separate budget axes producing distinct taxonomy states (`insufficient_evidence` vs `budget_exhausted`). What happens when a high-priority candidate abstains at the screen tier — continue, escalate tier, or stop — is a caller-declared policy, never an implicit retry.

### Seed coupling is an explicit mode

Common-random-number pairing (proven with local seeded engines) is declared per adapter; hosted providers without seed guarantees run uncoupled, and the docs state that CRN results are conservative relative to the uncoupled calibration (S2-P3 finding). The library never implies paired randomness it cannot verify.

### Guided screening: uncertainty prior with quality monitoring

Candidate ordering may take a per-step prior from the cheap layer-F uncertainty channel (or any caller-supplied score). Measured economics (S2-P4): a good prior saves ~25% of replay cost, an adversarial one costs ~24%, and sourcing the prior from the ~-66% residual channel costs ~5.75× what it saves — so the residual channel is never the prioritization prerequisite. The engine monitors prior quality online (is the prior-ranked order finding effects earlier than chance?) and reports it in the result object.

### Hierarchy and interactions per stage 10

Group/provenance-cluster effects before individual effects; declared coalitions for suspected interactions; Shapley reserved for small candidate sets with its budget expressed in permutations/rollouts, not an opaque sample count.

## Consequences

- B is falsifiable end to end: every claim arrives with effect, CI, counts, fidelity, and an abstention-capable status — the differentiation from judge-prose is structural, not rhetorical.
- Requiring a user adapter is friction; the mitigations are the OpenAI-endpoint reference adapter (S2-P4's real-model case generalized) and the KAOS pattern in the [interface overview](./library-interface-overview.md).
- Boundary-effect workloads land in abstention by design; documentation must set this expectation loudly.
- The planted-cause benchmark harness (unit SCMs now; Aegis/TraceElephant fixtures later) stays in-tree as the standing validity check for any estimator change.

## Alternatives considered

- **LLM-judge root-cause analysis (with or without replay garnish).** Rejected as the core: unfalsifiable, the exact demand-risk stage 10 warns about; judges are admitted only as labeled noisy evaluators inside the outcome protocol.
- **Single-arm replay against the recorded run.** Rejected: the recorded run is not an estimated baseline; the reference arm doubles as the replay-fidelity diagnostic (S2 exercised `low_replay_fidelity` deliberately).
- **Fixed-N designs.** Rejected: sequential batching with the measured stopping behavior dominates on cost; the coverage probe showed the bias is negligible at these settings.
- **Learned/LLM localizers as verdict sources.** Rejected per stage 10: admissible only as proposal distributions for candidate ordering — exactly the guided-screening slot, with monitoring.
- **Building a replay sandbox/runtime into xai.** Rejected: non-goal; world-state restoration is the application's competence, xai's job is the contract around it.

## Follow-up

- Reference adapter for OpenAI-compatible endpoints (generalizing S2-P4) in the first implementation increment.
- Aegis and TraceElephant fixture integration for the benchmark harness.
- Group-sequential coverage re-check if batch size or stopping rules ever change.
