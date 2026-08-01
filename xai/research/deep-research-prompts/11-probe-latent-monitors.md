# Deep-research prompt — stage 11: probe & latent-monitor science

Copy everything in the fenced block below into ChatGPT deep-research mode as a single prompt. The block is self-contained. When results come back, save them as `xai/research/11-probe-and-latent-monitor-science.md` with inline citations preserved.

```
You are doing deep research to support a specific open-source engineering decision, not a general literature review. Read the context, then do the task.

CONTEXT — the project. `xai` (github.com/EthicalML/xai) is an open-source library from The Institute for Ethical AI & ML, first released in 2017 as a tabular explainability/fairness toolkit, now being revitalized in 2026 for agentic LLM systems. It is a provider-neutral analysis layer over agent traces (OpenTelemetry GenAI / OpenInference), in three layers: (A) trajectory schema + deterministic diagnostics + sliced metrics; (B) causal attribution via ablation/counterfactual replay with uncertainty; (F) optional parametric instrumentation of self-hosted open-weights inference servers that emits internal-state signals as trace-correlated OpenTelemetry spans. Firm non-goals: no trace store, dashboard, eval runner, guardrail engine, agent runtime, or sparse-autoencoder trainer; and chain-of-thought and LLM-judge rationales are never presented as faithful causal ground truth.

CONTEXT — why this matters. Layer F wants to emit, per generation step, cheap internal-state signals from a self-hosted open-weights model: logit-derived uncertainty (probe-free) and a small number of linear-probe readings on the residual stream. These become new evidence channels that layer A's diagnostics and layer B's replay consume — e.g. a "stated confidence high but internal uncertainty high" mismatch as a live chain-of-thought-unfaithfulness signal. The whole idea depends on probes being valid enough to ship. We need to know which probes are real, how well they work, and what we can honestly claim.

TASK. Survey the state of linear probes and latent monitors on LLM internal activations, 2024–2026, for runtime explainability. Cover:
1. Specific probes and their evidence: uncertainty/confidence, refusal direction, deception/honesty, sycophancy, and any other behaviorally-validated directions. For each — the activation site/layer read, how it is trained, measured accuracy and false-positive behavior, robustness across models/architectures and under distribution shift, and reproducibility.
2. Probe-free internal signals: logit entropy and top-token logprob-margin as uncertainty proxies — how well they track calibrated confidence, and their limits.
3. The validity debate: correlation vs causation for probing classifiers, known confounds, and how ablation/steering is used to causally validate that a probe direction actually drives behavior.
4. Availability: which probes have published weights or reproducible training recipes, and under what license; note key players (e.g. Goodfire open SAEs, academic probe releases).
5. Production plausibility: which of these are credible enough to ship as calibrated vs experimental in an OSS library, and what a library would have to measure/caveat to ship one responsibly.

For every probe/method report maturity (research-only / prototype / production), compute cost at inference time, and licensing/availability.

OUTPUT. Structured markdown with inline citations to primary sources at each claim. Prefer 2024–2026 sources. Explicitly flag any claim that a runnable spike (train/apply one probe, measure separation on held-out data, ablate to check causality) could verify. End with the open problems and a recommendation on which one or two probes are the safest first targets for a shipped-but-clearly-caveated internal-signal channel.
```
