# xai — the target interface, walked through

*This is the alignment document for what xai should actually be. It walks the proposed target interface through three real-world scenarios, pushed to the limit of what the validated machinery can support. It supersedes the earlier prototype walkthrough (in git history) after the review verdict on it was correct: single-trace inspection with row-level diagnostics is dashboard territory, and per-token signal dumps carry no standalone value. Status markers throughout: ✅ built and validated (S8/campaign) · 🔶 machinery validated, interface proposed · 🧪 proposed, needs a spike.*

## The one-paragraph thesis

Your observability dashboard shows you *what happened* in any trace — spans, latencies, token counts, error rates. It cannot tell you three things: **what caused a failure** (it correlates, never verifies), **what is driving a failure *mode* across your fleet** (it aggregates metrics, not causes), and **what will break before you ship a change**. xai is the analysis layer for exactly those three questions, with one engine underneath all of them — statistically-contracted counterfactual replay — and, when you self-host the model, an internal-signal plane whose job is not "show me entropy" but *make the whole loop affordable*: rank every run by risk so the expensive verification lands only where it matters, and gate the worst runs live.

---

## Scenario 1 — The incident: "our agent told a customer to cancel their insurance policy"

A support agent gave harmful advice in production. The ticket is escalated; "the model hallucinated" is not an acceptable root cause — legal wants to know *what specifically caused this output* and product wants a fix that provably prevents recurrence.

```python
import xai

run = xai.load(incident_trace)                       # ✅ any source: Langfuse, OTLP/OpenInference, JSON
sus = run.suspects()                                  # 🔶 ranked intervention candidates for THIS outcome:
                                                      #    retrieved chunks, memory entries, system-prompt sections,
                                                      #    tool results, upstream agent messages — each a typed,
                                                      #    replayable intervention target, not a text blob
```

`suspects()` is where diagnostics earn their keep — not "token count grew" but *"these are the seven things that entered this decision's context, ranked by prior plausibility (uncertainty at ingestion, provenance class, anomaly vs the fleet baseline)"*. Then the interrogation:

```python
verdict = xai.explain(
    run, outcome=gave_cancellation_advice,            # your deterministic outcome rule
    candidates=sus.top(5),
    adapter=xai.adapters.openai_endpoint(agent_url),  # ✅ replays against your own agent
    budget="standard",
)
verdict.ranked()
```

```text
cause                                        effect   95% CI          status            n/arm
kb_chunk#4471 ("policy lapse workaround…")   +0.62    [0.44, 0.77]    material_effect   128
memory("user asked about cancelling", 3d)    +0.11    [-0.02, 0.24]   insufficient_ev.  128
system_prompt§"be maximally helpful"         +0.03    [-0.08, 0.14]   negligible_effect 128
```

A stale KB chunk causes the harmful advice in 62% of counterfactual worlds; the "be maximally helpful" prompt line — everyone's favorite scapegoat — is exonerated with an interval. ✅ *This exact contract is built and calibrated (FPR 0/400, honest abstention); what's proposed is the `suspects()` layer and the typed intervention vocabulary beyond context-removal.*

And because the answer has to leave the engineering org:

```python
packet = verdict.to_packet(policy=xai.packets.EU_AI_ACT)   # 🧪 stage-13 decision-evidence packet:
packet.write("incident-4471-evidence.html")                #    the decision record, counterfactual results as
                                                           #    first-class fields, applicability determination,
                                                           #    redaction profile — evidence, not a screenshot
```

Close the loop so it *stays* fixed:

```python
xai.testing.assert_no_material_effect(                     # 🧪 the causal regression test, in CI forever
    fixture_run, candidate="kb_chunk#4471", budget="screen")
```

**Why a dashboard can't do this:** it can show you chunk #4471 *was in the context*. It cannot tell you the advice disappears in the world where it isn't — that requires executing counterfactuals under a statistical contract, and producing an artifact that survives hostile review.

---

## Scenario 2 — The fleet: "task success dropped 6 points this month and nobody knows why"

Nothing "failed" — no errors, no latency spike. Ten thousand runs, a slow bleed. This is where trajectories become a *dataset*, which is the actual meaning of "the pandas of agent traces":

```python
fleet = xai.cohort(langfuse, project="support-agent",      # 🔶 streams from your existing backend —
                   since="30d", outcome=csat_rule)          #    xai is NOT a trace store; the backend is
fleet.df                                                    # one row per RUN: outcome, structure, costs, signals
```

```python
modes = fleet.failures().cluster()                          # 🧪 failure-mode discovery: trajectory-shape +
modes.summary()                                             #    outcome clustering, MAST-taxonomy-mapped labels
```

```text
mode                                    runs   rate    trend    example
A: wrong-policy-cited                    412   4.1%    ▲ 2.9pt  run_8812…
B: tool-retry-spiral → gave up           233   2.3%    ▲ 1.1pt  run_9917…
C: refused in-scope request              105   1.0%    ▬        run_7734…
```

Now the step no other tool has — cause *mining* across the cohort, then cause *verification* by replay on a stratified sample:

```python
hyp = modes["A"].mine_causes()                              # 🧪 what do these 412 runs share that the 9,600
                                                            #    healthy ones don't? retrieved-doc overlap, tool
                                                            #    versions, prompt-template revision, time windows,
                                                            #    upstream-agent identity — candidate generators,
                                                            #    NEVER verdicts (stage-10 discipline)
verified = modes["A"].explain(hyp.top(3), adapter=adapter,  # 🔶 replay-verify on a stratified sample of the
                              sample=40, budget="screen")   #    cluster — the S2 engine, run per-sampled-run,
verified.coverage()                                         #    aggregated with the same interval discipline
```

```text
cause                                  cluster coverage   95% CI       verdict
kb_doc "2024-pricing.md" (stale)       64%                [51, 75]     material_effect
retriever@2.3.1 rerank change          22%                [12, 35]     insufficient_evidence → escalate?
prompt template r41 tone edit           3%                [0, 11]      negligible_effect
```

*"A stale pricing doc explains two-thirds of your regression, with intervals"* — that sentence, produced mechanically from traces you already collect, is the product. **Dashboard ceiling:** it could have shown you mode A's rate rising. Everything after that line is causal machinery it doesn't have.

---

## Scenario 3 — The change: "can we ship this prompt/model/tool update?"

Today teams ship agent changes on vibes plus a handful of evals. The counterfactual engine inverts this — run the *same* golden trajectories under both configurations and attribute every behavioral delta to the change, before production:

```python
diff = xai.diff(golden_runs, adapter_a=current, adapter_b=candidate,   # 🧪 paired replay under both configs
                outcomes=[task_success, tone_rule, cost])
diff.regressions()
```

```text
outcome        Δ        95% CI          verdict           where (drill-down)
task_success   -0.04    [-0.07,-0.01]   material_effect   concentrated in mode-C-like refusals
tone_rule      +0.02    [-0.01,+0.05]   insufficient_ev.
cost/run       -18%     [-22,-14]       material_effect   shorter tool loops
```

…and the causal test suite from Scenario 1 runs in CI on every PR that touches a prompt, a tool schema, or the model pin. ✅ *Paired common-random-number replay and its conservatism are already measured (S2); the `diff` orchestration and CI harness are the new surface.*

---

## Where F actually earns its place (the reframe)

Raw per-token entropy is worthless as a headline feature — correct. Its value is *economic and operational*, and only exists because we proved (campaign, on real GPUs) that self-hosted serving can emit exact uncertainty nearly free while dashboards ingesting API responses mathematically cannot reconstruct it:

1. **Triage: making Scenarios 1–3 affordable.** Replay costs real money. The cheap signal plane ranks every run by internal risk so verification budget lands only on the tier that needs it — measured ~25% replay savings from a good prior, and at fleet scale the difference between "verify 40 sampled runs" and "verify 10,000". `fleet.risk_tiers()` 🔶 is the F→B synergy as one method call.
2. **The live gate.** `xai.gate(policy="block_on_spiral")` 🧪 as a serving-side hook: the non-completion/spiral signal (validated: 239/239 capped runs were failures) plus risk tier, gating or escalating a run *while it is still running*. A dashboard alerts you after the customer saw the answer; a gate needs per-token server-side signals — structurally self-hosted-only, structurally ours.
3. **The drift sentinel.** `fleet.watch_regime()` 🧪: internal-signal distributions shift when a quantization, engine upgrade, or template change alters model behavior — *before* outcome metrics move. The provenance/numerics plane (engine, graph mode, `exact|tolerance`) that looked like pedantry in v1 is exactly what makes cross-regime comparison honest.

Signals never appear as a feature; they appear as *cheaper verification, earlier warning, and a gate*.

---

## The TUI, reframed to match

Not a trace browser — an **investigation board** 🔶: open on a cohort, panes are *failure modes → representative runs → suspects → replay verdicts*, and the thing you watch live is verification landing across a cluster, not one trace's spans. Single-run drill-down (the current three panes ✅) remains as the leaf level. Same for `to_html`: the artifact it renders is the evidence packet, not a span dump.

---

## Built vs proposed — the honest ledger

| Capability | Status |
|---|---|
| Canonical ingest, cohort-less single-run load, replay manifest | ✅ built (S8) |
| The statistical replay contract, taxonomy, budgets, endpoint adapter | ✅ built + calibrated (S2/S8) |
| Cheap uncertainty channel, spiral signal, provenance/numerics plane | ✅ validated (S3/S7), packaging pending |
| `suspects()` typed-intervention candidates; intervention vocabulary beyond context-removal | 🔶 stage-10 design, needs building |
| `cohort()` streaming from backends; fleet dataframe; `risk_tiers()` | 🔶 straightforward on validated parts |
| Failure-mode clustering; cross-run cause mining | 🧪 the genuinely new research+build surface |
| Cohort-level verified coverage (`explain` over stratified samples) | 🔶 S2 engine + orchestration |
| `diff()` paired config comparison; causal CI assertions | 🧪 new surface on measured foundations |
| Evidence packets (stage 13) | 🧪 designed in research, zero code |
| Live gate; drift sentinel | 🧪 signals validated, productization unproven |
| Investigation-board TUI | 🔶 leaf level built; board level new |

**Proposed next step:** pick the one scenario that must be undeniable at launch — my recommendation is Scenario 2, because fleet-level *verified* root-causing is the widest moat and exercises everything else — and run an S9 spike shaped like S8: build that scenario's interface end to end against a synthetic-but-realistic fleet (planted failure modes, so the verdicts are checkable), and let the walkthrough of *that* replace this document's 🧪 markers with ✅.
