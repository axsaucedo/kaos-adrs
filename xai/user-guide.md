# Debugging an agent with xai — a walkthrough

*This is the hands-on companion to the [README](./README.md): a walkthrough of the actual working interface, in the order you would really use it. Every output below is real — captured from the `spike_s8` prototype on branch `spike/s8-integration` (namespace `xai_proto`; the shipped library will be `xai`). Where the prototype's interface is still rough, you'll see a **prototype note** — those are the proposed-interface discussion points.*

---

Your agent answered a user's question wrong. You have its trace — from Langfuse, or your OTel pipeline, wherever — and the usual observability view tells you *what happened*: this many spans, this much latency, these tool calls. It does not tell you *why the answer was wrong*. That's the walk we're taking: load the trace, let diagnostics point at suspects, then interrogate the leading suspect with counterfactual replay until we have an answer we could defend — or an honest "the evidence doesn't say."

Setup, once:

```bash
git checkout spike/s8-integration
uv venv spike_s8/.venv && uv pip install --python spike_s8/.venv/bin/python -e "spike_s8[tui]"
```

## Act 1 — Load the trace

One call, any source. Auto-detection looks at the file's shape (OTLP `resourceSpans`, Langfuse `observations`, or canonical JSON); `load_langfuse(...)` / `load_otlp(...)` exist when you want to be explicit.

```python
from xai_proto import load
traj = load("spike_s8/tests/fixtures/otlp-run.json")
traj.df.shape
```

```text
(6, 31)
```

Six events, thirty-one canonical columns. This is the whole mental model: **a trajectory is a dataframe** — one row per event, and everything else in the library is a view or an operation over it.

```python
traj.df[["event_id", "kind", "name"]]
```

```text
        event_id kind           name
ebe9369a54550bc8  run   s1-agent-run
2ddb1453e478ab1e  llm ChatCompletion
6c09d1935ac3b875 tool     calculator
ee7245325fbf91d7  llm ChatCompletion
21be2e4609d7b1b8 tool    fake_search
```

A root run, LLM calls, tool calls — the tree is in the `parent_event_id` column. `traj.events.llm` / `.tool` / `.internal` give you the filtered views, and `traj.to_json()` round-trips losslessly when you want to persist the canonical form.

One more thing worth looking at before debugging anything — what this trace *can and cannot support*:

```python
traj.replay.llm.iloc[0]["replay"]     # per-slot states, abridged
```

```text
replay.sampling.parameters: derived        replay.policy.id: not_captured
replay.tools.schemas: derived              replay.sampling.seed: not_captured
replay.model_visible_messages: derived     replay.state_hashes.input: not_captured
```

Every replay-relevant slot says whether it was `captured`, `derived`, or `not_captured` — never a bare null. Here the messages, tool schemas, and sampling parameters are recoverable; the seed and policy identity are not, which is typical of today's instrumentation and exactly what the library will tell you when it limits what replay can promise.

## Act 2 — Ask what's wrong: `diagnose()`

```python
report = traj.diagnose()
report.to_frame()[["code", "severity", "message"]]
```

On our richer fixture (the same run with real per-token signals attached — more on where those come from in Act 4):

```text
               code severity                                                          message
     context_growth  warning                   LLM input tokens grew monotonically by 100.0%.
   missing_manifest  warning                     Replay manifest has 9 uncaptured slot types.
  uncertainty_spike  warning          8 generation steps exceed the robust entropy threshold.
non_completion_risk    error Generation hit its cap or ended in a sustained high-entropy run.
```

Deterministic checks, no LLM judging the LLM. Each finding carries the `event_ids` it refers to (your join back into `traj.df`) and structured evidence — `uncertainty_spike`, for instance, tells you the threshold, the median, and the exact steps that crossed it. The `non_completion_risk` error is the campaign-validated spiral signal: this generation hit its token cap, and in our validation *every* capped generation was a failure.

So diagnostics have pointed at a suspect step. Now the real question.

## Act 3 — Ask *why*: `explain()`

This is the library's core claim: instead of asking a judge model to write a plausible root-cause paragraph, we **rerun the counterfactual**. Remove the suspect context item, replay the suffix enough times in both worlds, and measure whether the failure rate actually moves — with confidence intervals, and with the honesty to abstain when the budget can't resolve it.

You bring the replay runtime, because xai is not an agent framework. That's a small adapter with five methods — `restore` a checkpoint, `apply` an intervention, `reference_arm` (rerun unchanged), `run_suffix` (rerun modified), `evaluate` (deterministic outcome rule). Two reference adapters ship: a synthetic one (used below — instant, deterministic, great for learning the API) and `OpenAIEndpointReplayAdapter`, which points at any OpenAI-compatible endpoint — including your own agent.

```python
candidate = traj.context_items(0)[0]      # the message candidates of the first LLM call

result = explain(
    traj,
    adapter=my_adapter,        # your runtime binding
    candidates=[candidate],    # what we suspect
    outcome=None,              # None → the adapter's evaluate(); or pass your own rule
    budget="screen",           # 24 replays/arm; "standard"=128, "confirm"=256
    delta=0.10,                # "practically meaningful" = ≥10-point failure-rate shift
)
```

Watch what comes back — this is the evidence object, verbatim (abridged):

```json
{
  "status": "material_effect",
  "effect": 0.5,
  "estimand": "risk_difference_reference_minus_intervention",
  "ci": {"lower": 0.156, "upper": 0.710, "method": "newcombe_wilson_hybrid_score"},
  "per_arm_probabilities": {"reference": 0.6875, "intervention": 0.1875},
  "per_arm_replay_counts": {"reference": 16, "intervention": 16},
  "fidelity": {"declared_floor": 0.8, "mode": "DETERMINISTIC_SIMULATOR"},
  "seed_coupling": "common_random_numbers",
  "adjustment": {"label": "exploratory", "alpha": 0.05},
  "runtime_binding": {"engine": "synthetic-scm", "model_id": "bernoulli-agent"}
}
```

Read it like a lab result: *with* the suspect context item the agent failed 69% of the time; *without* it, 19%. The risk difference is +0.50 and the entire 95% interval sits above our 0.10 threshold — so the verdict is `material_effect`, reached after only 16 replays per arm because the effect was large enough for the sequential engine to stop early. The object also tells you how much to trust it: paired seeds, a fidelity floor, an exploratory (unadjusted) label, and the exact runtime it ran against.

Now the part that makes this trustworthy — **what happens when the evidence is weaker**. Same call, but the true effect is smaller:

```json
{
  "status": "insufficient_evidence",
  "effect": 0.29,
  "ci": {"lower": 0.016, "upper": 0.513},
  "per_arm_replay_counts": {"reference": 24, "intervention": 24}
}
```

The point estimate (+0.29) *looks* above threshold — a judge-based tool would happily declare a root cause here. But the interval still includes practically-negligible values, the screen budget is exhausted, and so the answer is **"we don't know yet"**, with the numbers to prove it. Your options are explicit: escalate the budget (`escalation=ESCALATE` reruns abstentions at the standard tier), or accept the abstention. The full vocabulary is ten states — four interval verdicts (`material_effect`, `negligible_effect`, `insufficient_evidence`, `direction_uncertain`) plus six typed failure modes (`restoration_failed`, `low_replay_fidelity`, `out_of_support`, `budget_exhausted`, `outcome_unavailable`, `nonidentifiable`) so a broken replay never masquerades as a causal finding.

Two more parameters you'll care about in practice: `prior=` orders candidates by a cheap uncertainty score so the culpable item is tested early (measured ~25% replay savings when the prior is good — and the result object reports the prior's observed quality, because a wrong prior costs you symmetrically), and `progress=` streams per-batch counts, which is what the TUI uses to animate the run.

> **Prototype notes (Act 3):** `outcome=` is a required keyword even when `None`; `explain()` currently takes executable state from the adapter's `default_checkpoint` rather than reading `traj`; `alpha` and automatic Holm adjustment aren't exposed at this convenience layer yet; candidate IDs must match between trace and checkpoint (shared identity is your job). All four are on the increment-A amendment list.

## Act 4 — Where the internal signals come from

Everything so far worked on any trace. If you *also* self-host your model, one server-side flag (vLLM logits processor, SGLang hook, llama.cpp plugin — see [ADR 0003](./adrs/adr_0003_parametric-instrumentation.md)) makes the server emit per-token internal signals as `xai.parametric.observe` spans on the same trace. Client-side, they just appear:

```python
traj.signals.uncertainty.head()
```

```text
 step  logit_entropy_raw  top2_logit_margin_raw  top1_probability_raw  top2_logit_tie  cap_hit
    0           0.005319               8.517315              0.999585           False    False
    1           0.000003              17.569174              1.000000           False    False
    2           0.113254               3.815722              0.977565           False    False
    3           0.000243              11.668139              0.999982           False    False
    4           0.288713               2.388523              0.915938           False    False
```

Per generation step: the model's next-token entropy, the top-two logit margin, the top-one probability, a near-tie flag, and cap-hit. Names end in `_raw` deliberately — this is telemetry, not "confidence"; calibrated probabilities exist only where a fitted, scoped calibrator has been attached. And every signal carries its measurement regime:

```text
 channel                 engine_name engine_version backend_graph_mode numerics_mode
 xai.parametric.observe    llama.cpp        b10217              eager     tolerance
```

`numerics_mode: tolerance` tells you these came from a bf16-style serving regime — comparable within tolerance, not bitwise. The additivity contract is symmetrical and real: the same `diagnose()` call on the signal-free trace produced exactly the two trace-only findings; with signals present, `uncertainty_spike` and `non_completion_risk` appear. Nothing else changes — byte-for-byte.

## Act 5 — See it: the TUI and the HTML report

```bash
python -m xai_proto.tui spike_s8/tests/fixtures/signals-trace.json
```

Three panes. The **trajectory tree** (left) is your map — kind glyphs, `!` markers on events with findings, and signal badges rolled up onto each LLM:

```text
◆ s1-agent-run
◉ !ChatCompletion
⚙ calculator
◉ !ChatCompletion
⚙ fake_search
◉ !ChatCompletion
· xai.parametric.observe ×512 entropy_mean=0.590 entropy_max=2.731 cap_hit=True
```

That last line is 512 real per-token signal events summarized into badges — `cap_hit=True` is your spiral suspect, visible at a glance.

Select an event and the **step inspector** (right-top) shows the full model-visible state — messages in/out with tool-call structure, tool payloads with raw *and* parsed values shown separately, sampling parameters each tagged with their origin (`requested` vs wrapper default), usage, and the replay-manifest slots colour-coded by capture state:

```text
LLM  ChatCompletion            status: ok
MESSAGES IN  [{"role": "user", "content": "Calculate 6*7, then fake-search the meaning of the result."}]
MESSAGES OUT [{"role": "assistant", "tool_calls": [{"function": {"name": "calculator", "arguments": "{\"expression\":\"6*7\"}"}}]}]
SAMPLING     temperature: 0 (requested) · max_tokens: 64 (requested)
USAGE        in 20 · out 8 · total 28 (captured)
```

The **replay panel** (right-bottom) is Act 3 made interactive: the selected step's candidate context items with checkboxes, a budget selector, the δ input, and RUN — batches land live via the progress stream, the verdict line ends with the status colour-coded by taxonomy, and a history table accumulates your runs (status, effect, CI, counts, fidelity) so you can compare candidates side by side:

```text
candidate message:2ddb1453e478ab1e:0: Calculate 6*7, then fake-search the meaning of the result.
budget=screen delta=0.10 status=not_run        ← RUN turns this into the live verdict line
```

For sharing, `traj.to_html("report.html", replay_results=[result])` writes a single self-contained file — tree, every event inspector, findings, and your replay verdicts — inline CSS, no server, opens anywhere.

## Where this leaves you

The loop you just walked — *load → diagnose → suspect → replay → verdict (or honest abstention) → visualize* — is the product. Next steps, roughly in order of ambition: run it yourself (`spike_s8/demo/run_demo.py --recorded` replays this whole walkthrough; `--live` does it against a real local model); point `OpenAIEndpointReplayAdapter` at your own agent's endpoint with a real checkpoint and outcome rule; flip a serve-side flag on a model you host and watch `traj.signals` populate. And when a result matters, read the whole evidence object — fidelity, seed coupling, adjustment label, manifest gaps — because the library will always show you exactly how much its answer is worth.

*Interface feedback from writing this guide is tracked as the prototype notes above plus the [S8 seam amendments](./impl/learnings/S8-integration.md) — together they are the proposed-interface changes for implementation increment A.*
