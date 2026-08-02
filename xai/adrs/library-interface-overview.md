# xai library interface overview — how a user interfaces with A, B, and F

This is the high-level user-facing view of the revitalized `xai` library that the four ADRs commit to ([ADR 0001](./adr_0001_trajectory-schema-and-ingestion.md) schema/ingestion, [ADR 0002](./adr_0002_decision-attribution-replay.md) attribution, [ADR 0003](./adr_0003_parametric-instrumentation.md) parametric, [ADR 0004](./adr_0004_visualization-tui.md) visualization). It shows the API surface a user touches, the workflows for integrating specific tracing/serving stacks, and a production reference setup using KAOS. Everything shown is grounded in campaign-validated capability ([campaign synthesis](../impl/learnings/campaign-synthesis.md)); nothing here promises what a spike refuted.

## The three-sentence pitch

`xai` turns agent trajectories into decision evidence. Load a trace from any major source into one canonical dataframe, run deterministic diagnostics, and — when you need to know *why* — replay counterfactuals with a real statistical contract instead of an LLM-judge guess. If you self-host your model, `xai`'s server-side instrumentation adds internal signals (uncertainty, cost, optional probes) to the same trajectory, with honest epistemic labeling throughout.

## Layer A — load, inspect, diagnose

```python
import xai

# One canonical trajectory from any source (auto-detected or explicit)
traj = xai.load("trace-export.json")                      # plain JSON / OTLP file
traj = xai.load_langfuse(host, keys, trace_id="…")        # Langfuse export API
traj = xai.load_otlp("otlp-run.json")                     # collector file export

traj.df            # the canonical events dataframe (pandas) — one row per event
traj.events        # typed accessors: traj.events.llm, traj.events.tool, traj.events.internal
traj.replay        # the replay manifest with per-slot provenance (captured/derived/not_captured)

report = traj.diagnose()          # deterministic layer-A diagnostics
report.findings                    # e.g. tool-error-loops, retry storms, context growth, non-completion/spiral risk
report.to_frame()                  # sliceable, groupable — the pandas idiom, like 2017 xai's metrics_plot
```

Design commitments a user can rely on: the dataframe schema is the stage-9 canonical model (four event kinds, provenance everywhere, explicit nulls); ingestion never invents precision or intent; a trajectory without parametric signals is byte-for-byte unaffected by the F machinery.

## Layer B — ask why, get a falsifiable answer

```python
# The user supplies the replay adapter — xai is not an agent runtime
class MyReplayAdapter:
    def restore(self, checkpoint) -> RestorationReport: ...
    def apply(self, intervention) -> InterventionReport: ...
    def run_suffix(self, policy, budget) -> CounterfactualTrajectory: ...
    def evaluate(self, trajectory) -> Outcome: ...
    # optional: reference_arm() — named no-intervention resampling

result = xai.explain(
    traj, adapter=MyReplayAdapter(),
    candidates=traj.context_items(step=7),     # what to ablate
    outcome=my_outcome_rule,                   # deterministic rule preferred; judges labeled as noisy
    budget="screen",                           # screen(24/arm) | standard(128) | confirm(256) | custom
    delta=0.10,                                # practical-effect threshold
)

result.status          # material_effect | negligible_effect | insufficient_evidence | … (10 states)
result.effect          # risk difference with Newcombe CI
result.to_json()       # the full evidence object: arms, counts, fidelity, adjustment, estimand
```

The contract the campaign validated: false positives controlled at nominal, coverage held, and at the boundary the library abstains — `insufficient_evidence` is a first-class answer, not a failure. Screening order can be guided by the layer-F uncertainty channel (`xai.explain(..., prior=traj.signals.uncertainty)`) — measured ~25% replay savings when the prior is good, with built-in prior-quality monitoring because a wrong prior costs symmetric waste.

## Layer F — internal signals from your own serving stack (additive, optional)

Server side, per engine (no engine forks, zero or near-zero patch — see ADR 0003 for the tier ladder):

```bash
# vLLM: documented logits-processor flag — exact entropy/margin, CUDA graphs stay on (~-23%)
vllm serve $MODEL --logits-processors xai_serve.vllm:UncertaintyProcessor

# SGLang: supported forward-hooks flag — adds the residual/probe channel (opt-in eager, ~-66%)
python -m sglang.launch_server --model $MODEL --forward-hooks xai_serve.sglang:probe_hook

# llama.cpp: cb_eval plugin binary; Ollama users run the same GGUF via instrumented llama-server
```

Agent side, nothing changes except context propagation (`traceparent`), which serious stacks already do. Signals arrive as `xai.parametric.observe` / `xai.cost.observe` INTERNAL spans that join the trajectory automatically:

```python
traj.signals.uncertainty       # per-step logit_entropy_raw, top2_margin_raw, top1_probability_raw (+ tie flag)
traj.signals.cost              # per-request GPU/CPU time (zero-touch eBPF/CUPTI channel)
traj.signals.provenance        # engine, version, graph mode, numerics: exact | tolerance
report = traj.diagnose()       # A-diagnostics now include uncertainty spikes and non-completion/spiral risk
```

Honest-naming contract (enforced in the schema): raw signals are never called confidence; calibrated fields exist only with a fitted, scoped, versioned calibrator; probes carry fail-closed registry provenance and per-checkpoint measured stats.

## Debugging visually — the TUI

```bash
xai debug trace-export.json        # Textual TUI: trajectory tree → step detail → replay panel
```

Three panes (ADR 0004): the trajectory tree with per-step diagnostic/signal badges; the step inspector (messages, tool payloads, uncertainty sparkline, provenance); and the replay panel — pick candidates, launch an `xai.explain` run against your adapter, watch the sequential batches land, and read the taxonomy verdict with its CI. `traj.to_html("report.html")` exports a static shareable view; there is no server, no dashboard, no store (explicit non-goals).

## Integration workflows

| Your stack | Workflow |
|---|---|
| **Langfuse** | Export via the public API → `xai.load_langfuse(...)`. Known quirks handled by the adapter: non-chronological observations, wrapper-default sampling params (provenance-tagged), parsed tool outputs (raw preserved). |
| **OTel GenAI / OpenInference** (LangChain, LlamaIndex, pydantic-ai, custom) | Tee your existing OTLP pipeline: add a collector file/OTLP exporter → `xai.load_otlp(...)`. No re-instrumentation. |
| **Arize Phoenix / vendor backends** | Same OpenInference spans — export and load; contract tests pin the attribute mapping per source. |
| **Plain JSON logs** | `xai.load(path, format="json", mapping=…)` with a declared field mapping — the escape hatch. |
| **Self-hosted vLLM / SGLang** | Add the serve-side flag (above); collector routes `xai.*` spans with the rest; trajectory gains `signals`. |
| **Ollama / llama.cpp** | Run the same GGUF under the instrumented `llama-server` plugin (Ollama's own server has no extension point — documented ceiling). |
| **Closed API providers** | Layers A and B fully available; F absent by design (API logprobs cannot reconstruct exact entropy — measured >1 nat error). |

## Production reference: KAOS

KAOS (K8s Agent Orchestration System) is the reference production shape: agents/models/tools as CRDs, every agent a `pydantic-ai-server` pod with process-global OTel (W3C TraceContext propagated across agent→agent and agent→model hops), a cluster OTel Collector fanning out to SigNoz/Jaeger. `xai` plugs in at three points, none of which require new transport:

1. **Trace plane (A/B):** the cluster collector adds one exporter tee (file or OTLP push) for `xai` ingestion; KAOS spans already carry `agent.name`, `session.id`, `gen_ai.request.model`, tool and delegation targets, which map onto the canonical schema's envelope and payloads. `xai.explain` replays run against an adapter built on the agent's own OpenAI-compatible endpoint (KAOS agents expose `/v1/chat/completions`), with the replay manifest populated from the CR spec (model pin, tool schemas from MCPServer CRs) — closing part of the capture gap S1 measured.
2. **Serving plane (F):** a `ModelAPI` backed by a vLLM deployment adds the logits-processor flag via its pod spec — the cheap channel lights up cluster-wide for every agent using that ModelAPI. LiteLLM-proxy ModelAPIs get the API-tier ceiling (approximate uncertainty only); Ollama-hosted ModelAPIs are the documented no-extension case.
3. **Debug plane:** `xai debug` runs anywhere with access to the exported traces — an operator laptop over SSH, a cluster job — because it is a TUI, not a service.

## What xai deliberately does not do

No trace store, no dashboard/server, no eval runner, no guardrail engine, no agent runtime, no SAE training, no "LLM SHAP over tokens"; CoT and judge rationales are never presented as faithful causes; internal signals are never named confidence or deception; the mismatch detector stays out of the shipped taxonomy until validated at scale.
