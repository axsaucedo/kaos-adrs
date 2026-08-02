# S6 learnings — first-probe validation: SEP and refusal direction (gates the F probe channel with S7)

Spike S6 executed 2026-08-02/03 in four phase-gated Codex sessions on the F track (plus one recovery session). All four phases passed — two of them by documenting honest negatives, which is what the gates were designed to allow. Evidence in `tmp/spikes/s6/` (labelled dataset, activations, probes, causal battery, perturbation cells, four phase reports + recovery note). Model throughout: the pinned Qwen3-0.6B (revision `c1899de2`), HF eager fp32 activations; generation on the S4 llama.cpp Metal harness.

## Verdict

**One narrow surviving prototype, one near-chance research probe, one preserved negative causal reproduction.** The Semantic Entropy Probe at the second-last-token position, layer 17, is a *restricted prototype* — in-distribution held-out AUROC 0.711 [0.615, 0.802], robust to serving-regime numerical drift — but its token-before-generation variant is near-chance (0.528), its cross-task transfer is near-chance, and **it does not reliably beat the free q90-entropy channel off-distribution**. The refusal direction *failed its causal gate* on this model: a clean negative reproduction, research-only. At 0.6B scale, the learned-probe tier does not yet out-earn the free channel — the F ADR's probe channel ships behind per-deployment validation and a scale caveat, exactly as stage 11's evidence hierarchy predicted.

## SEP (probe a): what held and what did not

- **Recipe fidelity:** reproduced from the official OATML pipeline (commit `02e2167`, MIT; paper arXiv:2406.15927) with a documented deviations table (Qwen ChatML transport, thinking disabled, TriviaQA-only binarization threshold 1.372 nats, MPS-fp16 NLI with a CPU/fp32 pilot cross-check). Labels: 400 prompts × 10 samples, strict bidirectional DeBERTa entailment, 134 low / 266 high SE, 4/400 flagged by programmatic audit (marginal clustering artifacts on malformed 0.6B outputs — accepted as documented label noise; the pilot audit's verdict "acceptable with caveats, not visibly broken" held at full scale).
- **In-distribution:** SLT layer 17 AUROC 0.711 [0.615, 0.802] with separate isotonic calibration — a real but modest signal, well below the paper's larger-model numbers. TBG (the paper's recommended deployment position) near-chance at this scale: **position matters and must be validated per checkpoint, not assumed from the paper.**
- **Cross-task transfer (the deployment question):** frozen TriviaQA-trained probe scored on the S7 GSM8K workload — near-chance, and not reliably better than free q90 entropy on the same items. **The headline F-ADR input: at small scale the learned probe does not beat the free channel off-distribution**, so the probe tier's value case rests on larger models and in-distribution use.
- **Serving-regime robustness (P4):** perturbing test activations at and above the campaign-measured bf16 drift scale (±0.05 absolute ≈ 6% of median component magnitude; plus stricter row-RMS-scaled variants): worst AUROC loss 0.0038, worst Brier +0.0071 — the verdict survives; **no `exact`-numerics gate required** for the ranking claim. Fixed-threshold operating points (TPR@5%FPR worst −0.050) still need monitoring. Explicitly scoped: synthetic component noise, not end-to-end bf16 batching validation.

## Refusal direction (probe b): a clean negative reproduction

Methodology pinned to the official Arditi et al. pipeline (arXiv:2406.11717, Apache-2.0). On Qwen3-0.6B: **no candidate direction passed the recipe's induced-refusal selection threshold** — the model violates the selection premise. The documented relaxed candidate then failed the causal battery: ablation moved harmful-prompt refusal 25.0%→12.5% but separated from norm-matched random controls by only one prompt; signed addition produced 0% refusal at every dose, identical to controls. Collateral accuracy unchanged (baseline near floor). Verdict: **research-only; preserved as a negative causal-control reproduction, never registered as a refusal/safety probe.** The causal-validation bar is real and small models can fail it wholesale — which is precisely why the bar exists.

## Infrastructure learning (orchestration)

The full NLI clustering and activation-capture jobs, launched as background children of a Codex session shell, **died on session exit (SIGHUP)** and cost ~45 minutes of silent stall. The recovery pattern that worked: relaunch under `nohup setsid` (verify PPID 1), append-mode logs, per-unit checkpoint shards with a `--resume` flag, atomic final assembly, and a `check_jobs.sh` liveness script. Any brief that leaves compute running past the session must mandate this pattern up front.

## Registry and provenance (the part that shipped clean)

Both probes carry full stage-11 provenance objects (checkpoint hash, layer, position convention, recipe pins, validation distributions, calibrator id, claim text) and **fail-closed loaders that reject a mismatched checkpoint revision** — demonstrated, not asserted. The SEP claim text follows stage 11's wording (a model- and checkpoint-specific linear estimate of semantic entropy; not a probability the answer is false); the refusal object's claim text states it measures a direction associated with refusal behavior in the listed suite, not harmfulness or safety.

## Flags for the F ADR

- The probe channel is **opt-in eager diagnostics** economically as well as mechanically: the residual channel's ~-66% throughput cost dominates probe arithmetic, and at small scale the free S7 telemetry matches the learned probe off-distribution. Prefer the free channel wherever its narrower claim suffices.
- Per-checkpoint validation is non-negotiable: position choice (TBG vs SLT) inverted between the paper's models and this one; a probe registry entry without measured stats on the exact checkpoint is not shippable.
- Extraction bookkeeping should align with the ecosystem's `query_start_loc`/`req_ids` convention (vLLM-Lens, IBM vLLM-Hook) rather than reinventing it.
- A scale-escalation experiment (repeat S6 on a 7–8B checkpoint) is the single highest-value follow-up: both probes' failures are plausibly scale artifacts, and the harnesses are now fully reusable.
