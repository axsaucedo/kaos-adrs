# Stage 7 — Parametric-enriched traces: concept and synergies

> Authored from this session's design analysis (not migrated). Part of the [research plan](./0-research-plan.md); components **C4 — Parametric instrumentation** and **C5 — Signal transport & correlation**. Reads alongside [stage 2](./2-landscape-interpretability.md) (interpretability landscape), the [direction synthesis](./6-direction-synthesis.md) (where this is Proposal F), and [stage 8](./8-server-instrumentation-feasibility.md) (the feasibility of producing these signals). This is a **design-synthesis** document: it argues for a specific architecture. Its load-bearing feasibility assumptions are flagged inline and gated on spike **S3** (make-or-break), spike **S6** and [stage 11](./deep-research-prompts/11-probe-latent-monitors.md) (probe validity), and [stage 10](./deep-research-prompts/10-causal-attribution.md) (attribution). Nothing here is settled until those return.

## The idea in one line

Layers A and B explain agent behavior from the *outside* — from what went into and came out of each model call. When the agent runs on a **self-hosted open-weights model whose inference the user controls**, xai can additionally instrument the model's forward pass and attach **internal-state signals** to the same trajectory, so the same diagnostics and the same causal replay can correlate a behavioral cause with the model's own internal evidence. The end-state pitch this unlocks is explanations where **the behavioral experiment and the model's internal state corroborate each other** — a claim no observability vendor and no interpretability lab is structurally positioned to make (see [stage 8](./8-server-instrumentation-feasibility.md) for why).

This is Proposal F. It is strictly **additive**: the closed-API majority keeps the full value of A and B without it; F only lights up for the open-weights self-hosted segment.

> **Post-research corrections (2026-08-01, from [stage 11](./11-probe-and-latent-monitor-science.md)):** the probe examples below are illustrative, and the imported probe-science research grades them: logit entropy/margin ship as raw telemetry (never named "confidence"); the first credible learned probe is a **Semantic Entropy Probe** (MIT recipe) and the second a **refusal-direction projection** (Apache-2.0, best causal-intervention evidence); **deception, honesty, truth, and sycophancy probes are research-only** (elicitation leakage, baseline shift, task dependence, adaptive evasion) and must not appear in a calibrated namespace. `STATED_VS_INTERNAL_MISMATCH` stands only as a *multi-channel mismatch detector* (stated confidence ∧ measured internal uncertainty ∧ replay instability), not as a "live CoT-unfaithfulness detector" or lie detector — the corrected framing supersedes the wording below wherever they differ.

## The evidence channels

When inference is instrumented (mechanics and feasibility in [stage 8](./8-server-instrumentation-feasibility.md)), each generation step can carry, ordered by cost:

- **Logit-derived uncertainty — free.** Output-distribution entropy and top-token logprob margin. The server already computes logits; no probe, no extra forward work. Gives a per-step "how confident was the model here" channel with zero marginal cost.
- **Linear-probe readings — cheap.** A stored weight vector dotted with the residual stream at a chosen layer: refusal-direction score, deception/honesty, sycophancy, internal-confidence. One matmul per probe per step. Deployable inline. Validity is the shaky part — see the epistemic labelling below and the calibration synergy.
- **Attention / attribution summary — moderate.** Which context tokens the step attended to or was most sensitive to — an approximate saliency prior over the context.
- **SAE features — expensive, opt-in, lab-only.** Sparse-autoencoder feature activations. Heavy; supported through adapters to existing tools ([SAELens](./2-landscape-interpretability.md)/Neuronpedia), never a trainer xai ships.

## Epistemic-status labelling (non-negotiable)

Every channel enters the trajectory tagged by how much it can be trusted as a *cause*, and the three tiers are kept visually and structurally distinct so no downstream consumer conflates them:

- **Observed** — what actually happened (messages, tool calls, outcomes, logits). Fact.
- **Correlational** — probe readings, attention/attribution, and chain-of-thought text. A signal that *co-occurs* with behavior; never asserted as the cause on its own. Chain-of-thought sits here explicitly: [stage 2](./2-landscape-interpretability.md) records the ~25% hint-mention faithfulness finding — CoT is a monitor, not ground truth, and so is a probe.
- **Causal** — an effect established by intervention (layer B's ablation/replay). The only tier allowed to make a "because" claim.

This labelling is what keeps F inside the project's non-goals: it consumes internal signals as evidence, but the causal claim always comes from a tested intervention, not from a probe or a rationale.

## The three synergies (why this is more than "F bolted on")

The value is not the extra telemetry — it is how the internal channels interlock with A and B. This is the design claim of the stage.

### 1. Internal signals become new A-diagnostics

Deterministic checks that are impossible from behavior alone:

- `STATED_VS_INTERNAL_MISMATCH` — the output says "I'm confident" while the uncertainty probe reads high. This is a **live chain-of-thought-unfaithfulness detector**, operationalizing the research finding that models do not say what they think.
- `INTERNAL_WARNING_IGNORED` — the uncertainty probe spiked and the agent proceeded without verifying or hedging.

These join the layer-A diagnostic set as new flags with an internal-evidence span attached, subject to the same human-correction workflow as the behavioral diagnostics.

### 2. Parametric signals make B cheaper

Layer B's cost is replay count — ablating, say, 40 context elements × 10 reruns is 400 executions. The attention/attribution channel provides a **prior**: rank context elements by internal attribution and spend replays only on the top candidates. Guided search instead of brute force — plausibly an order of magnitude fewer replays for the same confidence. **Assumption to validate:** that internal attribution actually predicts replay-confirmed causes well enough to prune — measurable directly once S2 (replay) and S3 (signals) both exist.

### 3. B validates the probes — and this is the differentiator

Probes are correlational and their validity is the weakest link in all white-box work ([stage 11](./deep-research-prompts/11-probe-latent-monitors.md) surveys exactly how weak). But B can adjudicate them: if the probe says "doc_3 triggered the refusal direction" **and** B's replay shows removing doc_3 flips the outcome 9/10, the correlational reading is causally confirmed. Run this systematically and you get **per-probe calibration statistics** — which probes hold up under intervention, on which model, for which behavior. Shipping probes *with measured calibration* is precisely the falsifiability discipline that is meant to be the library's signature, and it is the honest answer to "why should I trust a probe."

## What it unlocks over black-box A/B

Concretely, questions A/B alone cannot answer, that the corroboration loop can:

- "Did the model *internally* register the safety-relevant fact it then ignored, or did it never represent it?" (probe reading at the decision step vs behavior).
- "Was the confident-sounding wrong answer confidently wrong internally, or was the model uncertain and the text masked it?" (stated-vs-internal mismatch).
- "Of the twelve retrieved documents, which did the model actually attend to when it made the call?" (attribution prior, then confirmed by targeted ablation).

Each is a behavioral finding *and* an internal finding that agree — or, just as usefully, disagree, which is itself a flagged result.

## Monitor mode vs deep mode

The channels split by how much they cost to produce, which maps onto where they can run (full engine detail in [stage 8](./8-server-instrumentation-feasibility.md)):

- **Monitor mode** — logit-uncertainty and linear-probe scalars. Cheap enough to run inline in a throughput server. This is the production-viable channel and the primary target.
- **Deep mode** — full activation capture, SAE features, gradient attribution. Heavy; a development/debugging configuration on a single-request box, not a serving cluster.

Designing for both from the start means the trajectory schema reserves the parametric evidence channel now (see [stage 9](./0-research-plan.md), schema canonicalization), so instrumented-model spans drop in without a breaking change whether they carry a single entropy scalar or a full deep-mode payload.

## Assumptions this stage rests on (feasibility gates)

This design is contingent, and the contingencies are concrete:

- **S3 is make-or-break.** If a load-time forward-hook plugin cannot emit a correct per-request probe scalar on vLLM/SGLang under continuous batching, the whole "instrument the server, correlate into the trace" mechanism needs rethinking. [Stage 8](./8-server-instrumentation-feasibility.md) argues it is a plugin, not a fork; S3 proves or refutes it.
- **Probe validity (S6, [stage 11](./deep-research-prompts/11-probe-latent-monitors.md)).** If published probes do not discriminate on held-out data, the probe channel ships as "experimental" or not at all; the logit-uncertainty channel (probe-free) survives regardless.
- **Attribution-as-prior (synergy 2)** and **replay-validates-probe (synergy 3)** are both empirically checkable the moment S2 and S3 coexist, and should be measured before either is claimed in public docs.

## Non-goals preserved

- Adapters to existing interpretability tools (Captum remote-vLLM attribution, Inseq, SAELens/Neuronpedia), never a new SAE trainer or circuit-discovery framework.
- Store probe scores and top-k attributions in spans; **never** export raw activations.
- Internal signals are separately-labeled correlational evidence; the causal claim always comes from a tested intervention.
- F is additive; it must never become a requirement that degrades the closed-API A/B experience.
