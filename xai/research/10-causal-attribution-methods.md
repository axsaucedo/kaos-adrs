# Stage 10 — Causal attribution methods for agent trajectories

> Deep-research output (ChatGPT deep research, imported 2026-08-01) produced from [`deep-research-prompts/10-causal-attribution.md`](./deep-research-prompts/10-causal-attribution.md). Part of the [research plan](./0-research-plan.md). Citations appear as opaque `citeturn...` tokens from the research tool rather than resolvable URLs; load-bearing novel claims (new benchmarks, version-specific behavior, enacted regulation numbers) should be spot-verified against primary sources before being relied on in an ADR, and claims flagged for spike verification are validated, not trusted.

# Causal and Counterfactual Attribution for LLM-Agent Trajectories

## Decision-oriented assessment

The literature available through **August 1, 2026** supports the proposed `xai` Layer B claim, but only under a deliberately narrow statistical and operational contract:

> Given a recorded decision state, a defined outcome function, a declared intervention, and a replay environment whose fidelity is measured, estimate how the intervention changes the distribution of an observed action or downstream outcome; report uncertainty, replay coverage, and reasons the effect may be unidentified.

That claim is materially stronger than trace summarization, LLM-as-judge failure prose, or ordinary observability. It is also substantially weaker—and more defensible—than asserting that a component was *the* unique philosophical or legal cause of a failure.

The closest direct match is **Causal Agent Replay**, released in June 2026. It formalizes a trajectory as a structural causal model, supports interventions on actions, observations, context, and policy, reruns the stochastic suffix, and reports confidence intervals. It also introduces a Monte-Carlo Shapley estimator for interacting steps. However, its validation is limited to small synthetic SCMs, its repository is an early prototype rather than a released package, and its current adapters do not solve faithful restoration of arbitrary side-effecting tools. citeturn21view4turn3view3turn3view4turn23view2

The rest of the field divides into three categories:

| Category | What it actually establishes | Representative work |
|---|---|---|
| **Executed interventional attribution** | A specified edit or resampling changed—or did not demonstrably change—an outcome under a particular replay environment | Causal Agent Replay, DoVer, parts of CausalFlow, dynamic TraceElephant |
| **Counterfactual repair/localization** | An oracle or generated replacement at a step can repair a failed run; therefore that step is a plausible repair locus | AgenTracer data construction, CausalFlow, CHIEF |
| **Trace-based diagnosis** | A learned model, graph analysis, invariant checker, or LLM judge predicts the likely responsible step or agent from recorded evidence | Who&When baselines, AgentRx, CDC-MAS, CHIEF, AgenTracer inference |

Only the first category directly supports an effect-size statement such as “removing document D reduced the probability of tool call X by 0.31.” The second supports a sufficiency-style claim—“at least one replacement at this step repaired the run”—but can confound causal importance with the quality of the replacement generator. The third is useful for triage and replay-budget allocation, but does not become causal merely because its output is called a “root cause.”

No surveyed system is production-ready as a provider-neutral attribution layer. The engineering opportunity for `xai` is therefore real: package the statistical and replay contracts that the papers describe incompletely, while treating learned and LLM-judge localizers only as candidate generators.

## Counterfactual replay under stochastic policies

### The estimand must be explicit

A recorded trajectory can be represented as

\[
\tau=[s_0,(a_1,o_1),\ldots,(a_T,o_T),Y],
\]

where \(s_t\) is the exact model-facing state, \(a_t\) is an action sampled from the agent policy, \(o_t\) is an environment or tool observation, and \(Y\) is a user-supplied outcome. Causal Agent Replay defines interventions including resampling an action from the unchanged policy, forcing an action, replacing an observation, editing context, and switching policy from a point onward. Because the policy is stochastic, an intervention produces a distribution of counterfactual trajectories rather than one definitive alternative history. citeturn21view4turn3view0

For `xai`, each result should therefore identify all of the following:

| Field | Example |
|---|---|
| Target | `tool_call.name == "issue_refund"` or final task failure |
| Intervention | Remove retrieved document D at decision step 6 |
| Held fixed | Prefix through step 5; model version; tool schemas; world snapshot |
| Resampled | Agent decisions from step 6 onward |
| Effect | Risk difference, action-survival difference, mean outcome shift, or odds ratio |
| Population | Replays from this recorded state, not all possible users or all deployments |
| Fidelity | Exact, snapshot-restored, recorded-observation, simulated, or live approximate |
| Uncertainty | Confidence interval plus replay count and stopping rule |

That contract avoids a common ambiguity in the literature: “counterfactual” may mean same-policy resampling, an oracle correction, an LLM-generated repair, or merely asking another LLM what might have happened.

### How many replays are needed

For a binary outcome under one intervention, a conservative fixed-sample approximation for a two-sided 95% confidence interval with worst-case half-width \(h\) is

\[
K \approx \frac{1.96^2}{4h^2}.
\]

This gives approximately:

| Desired half-width for one probability | Replays |
|---:|---:|
| ±0.10 | 97 |
| ±0.05 | 385 |
| ±0.025 | 1,537 |

For an effect defined as the difference between two independently estimated Bernoulli probabilities, using equal replay counts in the factual-replay and intervention arms, the conservative requirement per arm is approximately

\[
K_{\text{arm}}\approx \frac{1.96^2}{2h^2}.
\]

| Desired half-width for a probability difference | Replays per arm | Total replays |
|---:|---:|---:|
| ±0.10 | 193 | 386 |
| ±0.05 | 769 | 1,538 |
| ±0.025 | 3,074 | 6,148 |

These are worst-case planning numbers, not universal requirements. Fewer samples suffice when outcomes are far from 0.5, when effects are large, or when valid paired randomness reduces variance. Conversely, stepwise multiple testing, rare outcomes, low replay fidelity, and heavy-tailed continuous scores require more.

Causal Agent Replay uses Wilson intervals for intervention outcome probabilities, bootstrapping for some effect differences, and normal-approximation intervals for its Monte-Carlo Shapley estimates. It correctly treats a hosted-model rerun as stochastic rather than pretending that temperature zero guarantees identity. citeturn3view1turn3view2turn3view3

A practical library should not default immediately to hundreds of calls per candidate. A defensible staged budget is:

1. **Screening:** about 12–24 paired or balanced replays per candidate, explicitly labeled exploratory.
2. **Confirmation:** extend promising candidates to roughly 60–120 replays per arm.
3. **High-confidence report:** continue until a predeclared interval-width or decision boundary is reached, often hundreds of calls.
4. **Abstention:** stop at a hard cost ceiling and return `insufficient_evidence`, not the current point estimate as a verdict.

Repeatedly checking an ordinary fixed-sample interval and stopping when it crosses zero inflates false-positive rates. Adaptive replay should use a confidence sequence, an alpha-spending rule, or a predeclared batch schedule. This is an important omission in much of the current agent-attribution literature.

**Runnable spike:** implement Bernoulli factual/intervention replay with Wilson intervals, fixed batches of 16, and a maximum of 256 per arm. On synthetic effects of 0, 0.1, 0.25, and 0.5, measure empirical false-positive rate, interval coverage, stopping cost, and abstention rate. This should be validated rather than inferred from paper-level examples.

### What happens to the stochastic suffix

There are several distinct causal questions:

**Total suffix effect.** Change step \(t\), then allow every downstream model decision and tool call to evolve naturally. This answers whether the intervention changed the eventual system outcome through all downstream pathways. It is usually the most operationally relevant estimand, but early interventions inherit substantial downstream variance.

**Action-survival effect.** Modify context or an observation at step \(t\), then measure whether the same observed action—or an equivalence-class match—still occurs. This is narrower and cheaper than evaluating a full final outcome. It is useful for questions such as whether an untrusted document controlled a tool call.

**Controlled direct effect.** Change one variable while holding downstream mediators fixed or coupling their randomness. This can separate a decision’s direct influence from later rerolling, but it may create an unnatural trajectory and is difficult with hosted APIs. Causal Agent Replay notes that common random numbers would be useful for direct-effect estimation but are difficult once contexts diverge. citeturn3view4turn3view5

**Repair existence.** Generate \(K\) candidate replacements and report success if any repairs the outcome. CausalFlow uses this pattern: a candidate step receives several proposed alternatives—three in its reported experiments—and its Causal Responsibility Score is positive if at least one replacement flips failure to success. This establishes that a repair was found at that locus, not the probability that the original component caused the failure under the original policy. citeturn12view0turn12view1

Causal Agent Replay also identifies a “run-forward confound”: resampling an early step rerolls every later stochastic decision, so a large effect at an early step does not by itself prove that the early step is the point where failure became committed. Its proposed point-of-commitment rule selects the latest step whose effect interval excludes zero. That is a useful localization heuristic, but it should be exposed as a named rule rather than presented as a generally identified causal fact. citeturn3view1turn3view2turn3view3

### Restoring tool and world state

A valid rerun requires more than reconstructing an LLM prompt. OpenTelemetry GenAI and OpenInference can capture model invocation parameters, messages, tool definitions, tool calls, and tool results when the corresponding content recording is enabled. They are semantic conventions, however, not transaction logs for databases, browsers, filesystems, external APIs, clocks, secrets, user simulators, or sub-agent processes. citeturn5search5turn5search29turn5search6turn5search26

A provider-neutral replay layer therefore needs an explicit **world-state restoration interface**. Four fidelity levels are useful:

| Replay mode | What is restored | Valid claims | Main limitation |
|---|---|---|---|
| **Recorded-observation replay** | The original tool results are returned from the trace | Effect of changing model-visible context or action while tool observations are held fixed | Cannot test effects mediated through changed tool arguments or changed external data |
| **Snapshot replay** | Database, files, browser/session, environment variables, clock, and tool service state are reset to a saved checkpoint | Total effect within the captured sandbox | Requires application-specific snapshot adapters |
| **Forkable simulation** | A deterministic or stochastic simulator is cloned at the intervention point | Controlled benchmark and predeployment effects | Simulator-to-production validity may be weak |
| **Live approximate replay** | Current external services are called, ideally through dry-run or idempotent endpoints | Effect under present-day external state | Conflates intervention with world drift; unsafe for side effects |

ToolSandbox illustrates the right underlying primitive: its execution context stores dialogue and world state and records a snapshot at every turn, including settings, contacts, messages, and reminders. It is open source, but it is a benchmark environment rather than a general replay standard. citeturn22view0

DoVer preserves the prefix, applies a targeted edit to a message, plan, or instruction, and resumes the system from the intervention point. Its results show that checkpoint-based intervention can validate or refute some debugging hypotheses, but its implementation is tied to specific agent frameworks and benchmark environments. citeturn17view3turn17view4

CausalFlow uses actual downstream execution where a deterministic executor is available, as on its code benchmark, but substitutes predictive outcome modeling on several other domains. Its causal status therefore varies by benchmark: an executed repair is stronger evidence than a repair accepted by a predictive model or LLM consensus panel. citeturn12view1turn11view0

Causal Agent Replay’s present repository can integrate with several agent frameworks but re-executes tools through adapters and explicitly does not solve arbitrary real-world side effects. Its own paper lists side-effecting real tools as outside the demonstrated scope. citeturn4view0turn3view5

`xai` should make restoration quality machine-readable, for example:

```text
EXACT_SNAPSHOT
RECORDED_OBSERVATIONS
DETERMINISTIC_SIMULATOR
PREDICTIVE_SIMULATOR
LIVE_IDEMPOTENT
LIVE_UNCONTROLLED
RESTORATION_FAILED
```

An effect from `LIVE_UNCONTROLLED` should never be merged numerically with an effect from `EXACT_SNAPSHOT` without stratification.

**Runnable spike:** implement a minimal replay adapter over a SQLite-backed tool agent. Hash the database, files, tool schemas, clock, environment configuration, and model-facing prefix before every replay. Inject deliberate restoration failures and verify that the API returns `invalid_replay` rather than an effect estimate.

## Method landscape and engineering readiness

### Core trajectory and component attribution methods

| Method | Precise supportable claim | Compute and interaction handling | Validation | Availability and maturity |
|---|---|---|---|---|
| **Causal Agent Replay, 2026** | Under a recorded state and specified intervention, resampling or editing step \(t\) changed the downstream outcome distribution by an estimated amount. | Single-step analysis is roughly \(O(TK)\) suffix replays. Monte-Carlo Shapley evaluates many step coalitions across sampled permutations and replay batches; it allocates credit across interactions rather than assigning the full joint effect to every step. citeturn21view4turn3view2turn3view3 | Synthetic SCMs only: a planted pivotal step and a two-step interaction. No published validation on deployed production agents. citeturn21view4turn3view4 | OSS, Apache-2.0. Repository supports hosted and local backends but is not yet published as the advertised package. **Research prototype; best conceptual fit, not production-ready.** citeturn23view2turn4view0 |
| **AgentSHAP, 2025** | Which tool *availability* most contributed to reproducing the full-tool response’s semantics for one prompt. It does not establish why a particular tool was called at a particular trajectory step. | Exact cost is \(2^n\) tool subsets; the proposed approximation evaluates leave-one-out plus sampled subsets, reported as \(n+\rho(2^n-n-1)\). Tool coalitions give Shapley-style marginal contributions, but the paper acknowledges that it does not directly characterize synergies and ignores ordering. citeturn8view0turn8view1turn8view2 | API-Bank level-one tasks with eight tools and GPT-4o-mini; stability and removal tests, not deployed-system causal validation. citeturn8view1turn8view2 | OSS implementation in the TokenSHAP repository, MIT; no active package release was indicated in the reviewed repository. **Prototype for static tool-set attribution.** citeturn8view3 |
| **AgenTracer, 2025** | A trained model predicts the agent and step likely responsible for a failure. Its data builder can additionally show that replacing a selected action with oracle guidance repaired a training trajectory. | Inference is approximately one specialized-model pass over a trajectory. Training-data creation is expensive: counterfactual oracle replay plus programmed fault injection over thousands of trajectories. Interactions are learned implicitly, not reported as identifiable component effects. citeturn2view2turn9search11 | Evaluated on Who&When and through downstream feedback in agent frameworks; the paper reports improvements over large proprietary models and task-success gains, but not calibrated causal effect estimates on deployed production failures. citeturn2view2 | An official usable OSS artifact was not established from the primary paper sources reviewed. **Research model/localizer, not an attribution library.** |
| **CausalFlow, 2026** | At least one generated replacement for a candidate step produced—or was predicted to produce—a validated successful repair with limited edit distance. | Approximately \(O(TK)\) proposal-and-rerun operations, with \(K=3\) proposals per candidate in reported experiments, plus proposer/critic/meta-critic judging. It tests candidates individually and does not Shapley-decompose multi-step interactions. citeturn12view0turn12view1 | More than 3,000 tasks across arithmetic, code, QA, and medical browsing; reported failed-run repair rates vary by domain. Some domains use deterministic execution, others predictive outcome models. citeturn12view1turn12view2 | Paper/preprint; no official OSS repository was located in the reviewed primary material. **Research-only counterfactual repair framework.** citeturn20search3turn20search7 |
| **DoVer, 2025–2026** | A concrete hypothesis is supported, refuted, or remains unresolved according to whether a targeted edit followed by checkpointed re-execution repairs the task or advances milestones. | Cost depends on the number of hypotheses and intervention trials; each accepted hypothesis can require a full suffix rerun. Multiple independently successful repairs are allowed rather than forced into unique blame. citeturn17view3turn16search18 | Magnetic-One on GAIA/AssistantBench-derived failures and AG2 on GSMPlus; reported 18–28% recovery in the first setting and 49% in the second. These are benchmark frameworks, not production deployments. citeturn17view4 | Official Microsoft page says project code will be available, but a generally usable released library was not verified here. **Strong research prototype and replay-infrastructure reference.** citeturn17view4 |
| **CDC-MAS / Automatic Failure Attribution, 2025** | Under its discovered causal graph and simulated “normal” component behavior, a step or agent is predicted to be causally associated with failure. | Agent-level Shapley-style decomposition plus causal discovery over engineered trace features. Interactions are handled through graph structure and Shapley at the agent level, but identification depends on causal sufficiency and correctness of the learned graph. citeturn6search0turn6search2 | Who&When and TRAIL-style benchmark traces; reported step accuracy remains modest. No real production interventional validation was presented. citeturn6search2 | Paper-only in the primary sources reviewed. **Research method, not runtime-ready.** |
| **CHIEF, 2026** | Given a reconstructed hierarchical dependency graph and virtual oracles, a candidate is predicted to be a root cause rather than a propagated symptom. | LLM-based trace parsing and graph construction, hierarchical backtracking to prune candidates, then progressive counterfactual screening. It models dependencies better than flat temporal scanning but relies on generated graph edges and virtual-oracle fidelity. citeturn17view5 | Who&When only; paper reports gains over eight baselines and explicitly lists single-benchmark validation and hallucinated graph edges as limitations. citeturn17view5 | Replication package linked by the paper; licensing of the package was not established from the reviewed source. **Research prototype.** citeturn17view5 |
| **AgentRx, 2026** | An invariant-checking pipeline and final LLM judge identify the first critical step and failure category supported by an auditable violation log. | Multiple LLM stages generate static and step-conditioned invariants, check them, and run a final judge. It does not execute interventions, and interactions are represented only through generated constraints and the judge’s reasoning. citeturn21view1turn20academia39 | A 115-failure benchmark across API workflows, incident management, and web/file tasks. It improves localization over trace-based baselines but remains judge-mediated. citeturn20academia39turn21view1 | OSS, MIT, installable from GitHub. **Runnable diagnostic prototype; useful Layer A baseline, not causal Layer B evidence.** citeturn21view1 |

Two cautionary cases matter for an engineering decision.

First, **GraphTracer** originally claimed graph-guided failure tracing and production-system gains, but its arXiv entry was withdrawn in December 2025 because of a fundamental methodological error affecting the validity of the main results. It should not be used as positive evidence for the design, though its information-dependency-graph idea remains a useful hypothesis for candidate pruning. citeturn20search2

Second, learned localizers such as AgenTracer, AgentRx, CHIEF, or CDC-MAS can be useful as **proposal distributions**: rank likely intervention points, then spend replay budget on the top candidates. Their prediction score must not be exposed as a causal effect or confidence interval unless followed by actual intervention data.

### How interactions are handled

There are four materially different treatments of interactions:

| Treatment | Consequence |
|---|---|
| **Independent one-at-a-time ablation** | Misses AND, XOR, redundant, and compensating causes; often assigns weak effect to every individually necessary coalition member |
| **Shapley over coalitions** | Splits a coalition’s value among components according to average marginal contribution; expensive and dependent on the chosen coalition value and intervention semantics |
| **Graph or SCM structure** | Represents mediators and dependencies, but requires correct causal edges and sufficient observed state |
| **Learned joint reasoning** | May detect patterns across components but offers no guaranteed decomposition, uncertainty calibration, or intervention semantics |

Causal Agent Replay is the strongest surveyed implementation of the second approach. Its synthetic AND-style experiment recovers approximately equal credit for two jointly necessary steps and near-zero credit for an irrelevant step. It also warns that coalition evaluations should not be reused in a way that spuriously eliminates Monte-Carlo variance. citeturn3view2turn3view3turn3view4

For `xai`, full step-level Shapley should be optional and visibly expensive. A more tractable default is hierarchical:

1. Group spans into causally meaningful components: retrieved context, planner decision, tool selection, tool arguments, observation, memory write, delegation, and final response.
2. Screen groups with one-at-a-time interventions.
3. Test pairwise or domain-declared interaction sets.
4. Run Monte-Carlo Shapley only over the reduced candidate set.
5. Preserve a residual “unallocated interaction or omitted component” term rather than forcing all outcome variation onto tested steps.

**Runnable spike:** create two- and three-cause SCMs with AND, OR, XOR, duplicated evidence, mediator, and suppressor structures. Compare single ablation, pairwise interaction scores, exact Shapley, and budgeted Monte-Carlo Shapley for accuracy, interval coverage, and model-call cost.

## Context and RAG attribution adapted to sequential decisions

Static context-attribution work is valuable primarily as a **query-allocation and surrogate-modeling toolkit**, not as an off-the-shelf answer to agent causality.

### ContextCite

ContextCite samples random subsets of context sources, computes the probability of the original response under each ablated context, and fits a sparse linear surrogate with Lasso. The coefficient for each source is treated as its attribution. The paper shows an example using 32 ablations for 98 context sources and evaluates with top-\(k\) log-probability drop and linear datamodeling score. citeturn17view0turn18view1

Its precise claim is:

> The fitted surrogate predicts how including or excluding a source changes the model probability assigned to an already generated response.

This is not yet a sequential-decision effect. It teacher-forces or scores the fixed response rather than sampling a new agent trajectory, does not restore external world state, and assumes that a sparse linear surrogate adequately captures context interactions. Correlated or redundant documents can make individual Lasso coefficients unstable even when group prediction remains accurate.

ContextCite is nevertheless the most mature static component surveyed: it has an MIT-licensed repository and a PyPI package. citeturn17view1turn18view3

An agent-compatible adaptation would replace response likelihood with one of three values:

\[
v(S)=P(A_t=a_t^{obs}\mid \text{context subset }S),
\]

\[
v(S)=P(Y=1\mid \text{context subset }S,\text{suffix replay}),
\]

or

\[
v(S)=E[Y\mid \text{context subset }S,\text{suffix replay}].
\]

The first is relatively cheap if a provider exposes tool-call log probabilities or repeated action sampling. The second and third require state restoration and full suffix replay.

### CAMAB and bandit allocation

The Context Attribution Multi-Armed Bandit approach treats context segments as arms and adaptively chooses subsets using a combinatorial or linear Thompson-sampling formulation. Its reward is based on preserving the original response’s likelihood, and its reported experiments compare a fixed budget of 60 rounds with ContextCite- and KernelSHAP-style baselines. citeturn1search1turn2view4

The transferable idea is **adaptive allocation of expensive ablations**. In an agent library, a bandit can allocate replay calls toward documents or memory entries with uncertain but potentially large effects.

The non-transferable assumptions are equally important. Single-answer context attribution has a fixed target response and a comparatively stationary reward. In a multi-step agent, removing one document may alter the next tool, the available future observations, termination time, and the meaning of later context. A linear contextual-bandit posterior may therefore underestimate interactions and nonstationarity.

**Runnable spike:** compare uniform document ablation, Thompson-sampled ablation, and a sparse-surrogate strategy on a synthetic RAG agent with 50 documents, two planted causes, ten correlated duplicates, and a stochastic tool-choice suffix. Measure effect-estimation error per model call rather than only top-document retrieval.

### RAGONITE and removal-based evidence attribution

RAGONITE defines evidence influence through the similarity between the original answer and a response regenerated after removing an evidence item. It was evaluated on a hand-created conversational enterprise-RAG dataset, but remains a static answer-attribution method. citeturn2view5

Its useful contribution is the practical removal test; its limitation is that one regenerated answer per evidence item is not a statistically reliable effect estimate under a stochastic model. Similarity also answers “did the text change?” rather than “did the probability of a consequential action or task outcome change?”

### Agent-specific security attribution

AttriGuard applies parallel counterfactual tests to determine whether a proposed agent action survives attenuation or removal of untrusted observations. Its use of teacher-forced shadow replay is a valuable bridge between static context attribution and agent decisions because it tries to avoid rerolling unrelated parts of the action-generation process. The method is narrow—it is designed for indirect-prompt-injection defense rather than general causal debugging—and the reviewed paper did not establish a general OSS library. citeturn6academia24turn13search6

The main design lesson is to expose both:

- **Action-conditioned attribution:** did the same action remain supported after context removal?
- **Free-running outcome attribution:** after removal, what outcomes emerged when the suffix was allowed to change?

The former is easier to localize; the latter is closer to deployment consequences.

### Transfer verdict

Static RAG methods can be reused for segmentation, subset selection, sparse surrogate fitting, and budget allocation. They cannot be transferred unchanged because they generally lack:

- temporal state,
- tool and world restoration,
- stochastic suffix uncertainty,
- action equivalence definitions,
- mediation through future observations,
- and explicit treatment of out-of-support trajectories.

For `xai`, these methods should live behind the same intervention protocol as step replay, not as a separate “RAG explanation” subsystem.

## Falsifiable benchmark strategy

### A planted-cause benchmark is non-optional

Causal Agent Replay explicitly argues for validation against synthetic SCMs with known ground truth and demonstrates a pivotal-step case and a two-step interaction. That is the correct starting principle, but the published suite is too small to establish general reliability. citeturn21view4turn3view3turn3view4

A useful `xai` benchmark should generate executable trajectories from a known structural model, not merely ask annotators which log line appears erroneous. Each scenario should expose:

- a fully specified initial world state,
- stochastic policy mechanisms,
- deterministic or seeded tool transitions,
- exact intervention hooks,
- an executable outcome oracle,
- and analytically known or high-precision Monte-Carlo ground-truth effects.

The benchmark matrix should include at least these planted structures:

| Family | Planted structure | Failure mode tested |
|---|---|---|
| Single cause | One observation or action changes failure probability | Basic localization |
| Delayed cause | Early context affects a much later tool call | Symptom versus origin |
| Mediator | Context → plan → tool call → outcome | Direct versus total effect |
| AND interaction | Two components are jointly required | Single-ablation failure |
| OR redundancy | Either of two components is sufficient | Under-attribution of redundant causes |
| XOR or suppressor | Effect appears only conditionally | Sign reversal and interaction |
| Correlated duplicate context | Several near-identical documents encode one cause | Coefficient instability |
| Tool-state cause | Same tool input has different result under world state | Restoration validity |
| Policy-only cause | Model change alters action with context fixed | Policy intervention |
| Negative control | Component is visibly suspicious but causally irrelevant | False-positive control |
| Small effect | True effect below practical threshold | Abstention and equivalence |
| Replay drift | Environment changes between runs | Fidelity detection |
| Unidentified case | Required state was not recorded | Principled refusal |

For every generated case, store both the **causal graph** and the **declared intervention semantics**. A step may have zero direct effect but a large total effect; the benchmark should not mark one of those interpretations unconditionally “wrong.”

### Aegis as a scalable fault-injection source

Aegis, accepted at ICLR 2026, constructs 9,533 trajectories with context-aware injected failures across six multi-agent frameworks and six task domains. It releases code, data, and trained models under an MIT-licensed repository. citeturn21view2turn21view0turn23view0

Aegis is highly relevant for scaling a planted-fault corpus, but its labels are “the agent and error mode that the manipulator altered,” which is not automatically identical to the causal effect of that alteration. An injected corruption may be corrected downstream, may have no effect on the outcome, or may accidentally alter several variables.

A defensible reuse protocol is:

1. Begin from a demonstrably successful executable trajectory.
2. Apply one typed intervention through the Aegis injection machinery.
3. Verify that the intended state variable—and only declared descendants—changed.
4. Repeatedly execute both factual and injected worlds.
5. Retain the case only if the injection creates a measurable effect with a sufficiently narrow interval.
6. Record the injected locus, actual total effect, direct effects where identifiable, and all successful compensating interventions.

This converts “known edit location” into “known causal effect.”

**Runnable spike:** run 100 Aegis injections and audit how often the manipulated step is actually outcome-causal, how often downstream recovery neutralizes it, and how often the injection produces collateral trace changes. This is exactly the kind of paper claim that should be validated locally.

### Reusing Who&When correctly

Who&When contains logs from 127 LLM multi-agent systems and annotates the responsible agent and decisive error step. The associated repository describes 184 failure tasks drawn from algorithm-generated CaptainAgent and handcrafted Magnetic-One systems, with labels for responsible agent, decisive step, and natural-language explanation. The best reported baseline reached about 53.5% agent-level accuracy and 14.2% step-level accuracy. citeturn15view0turn16search7turn2view6

Its strengths are realistic long traces, multiple agent architectures, and a standardized localization target. Its limitation is fundamental: the labels are expert judgments over recorded failures, not outcome distributions obtained from controlled interventions. A method can disagree with an annotator because the method is wrong, because the annotation is ambiguous, or because multiple distinct repairs exist.

`xai` should therefore use Who&When for:

- agent and step top-1 accuracy,
- top-\(k\) and mean reciprocal rank,
- distance in steps from the annotated decisive locus,
- comparison against LLM-judge baselines,
- and analysis of whether replay evidence agrees with or contradicts the human label.

It should not report “causal accuracy” on Who&When alone.

A useful extension would be **Who&When-Replay**: select a manageable subset, reconstruct the executable framework and state, package outcome functions, and run declared interventions around the annotated step and nearby alternatives. Cases that cannot be faithfully reconstructed should remain a separate observational split.

### TraceElephant as the stronger real-agent benchmark

TraceElephant, released and accepted at ACL 2026, contains 220 annotated failures from 380 executions across Captain-Agent, Magentic-One, and SWE-Agent. It records model inputs and outputs, inter-agent messages, tool logs, configuration metadata, and provides executable environments. The benchmark reports that full observability substantially improves attribution over output-only traces and that dynamic replay further improves step-level accuracy. citeturn17view6turn18view5turn18view7turn23view1

It is a better integration target than Who&When for an early `xai` replay prototype because the execution context is more complete and the environments are reproducible. However, its primary labels are still expert “responsible agent” and “earliest inevitable step” annotations. Dynamic replay in the reported experiments is mostly single-step probing, not exhaustive estimation of intervention effects with calibrated intervals. citeturn18view6turn18view7

The repository is public under CC BY 4.0. That license is suitable for benchmark artifacts and documentation but should be reviewed carefully before copying code into an Apache- or MIT-licensed library, because Creative Commons licenses are not generally preferred software licenses. citeturn23view1

### Metrics that matter

A complete evaluation should report four metric families.

**Localization**

\[
\text{Top-1}, \quad \text{Top-}k,\quad \text{MRR},\quad
|t_{\text{pred}}-t_{\text{true}}|,
\]

plus separate component, agent, and step scores. Who&When and TraceElephant primarily use exact agent- and step-level accuracy. citeturn15view0turn18view7

**Effect estimation**

Use mean absolute error, root-mean-square error, sign accuracy, and rank correlation against the planted risk difference or mean outcome effect. For Shapley estimators, include efficiency residual:

\[
\left|\sum_i \hat{\phi}_i-\left(v(N)-v(\varnothing)\right)\right|.
\]

**Calibration and abstention**

Measure empirical confidence-interval coverage, average interval width, false discovery rate, false “no effect” rate, and selective risk as a function of abstention. Calibration should be stratified by replay fidelity and effect magnitude.

**Stability and cost**

Report rank correlation or top-\(k\) overlap across model seeds, provider backends, and replay batches; model calls, generated tokens, tool calls, wall-clock time, external API cost, and snapshot-restoration failures. AgentSHAP’s use of attribution-vector cosine similarity is one possible stability measure, but it should be supplemented by effect and ranking stability. citeturn8view1turn8view2

## Statistical contract and insufficient-evidence outcomes

### Effect sizes and intervals

The primary default should be an interpretable effect on an outcome chosen by the caller:

\[
\widehat{\Delta}
=
\widehat{E}[Y\mid do(I)]
-
\widehat{E}[Y\mid do(I_0)].
\]

For binary failure or action occurrence, report risk difference first. Risk ratios and odds ratios may be supplementary but behave poorly when baseline events are rare or zero. For continuous task scores, report mean difference and, where distributions are skewed, a quantile or probability-of-improvement measure.

The observed factual run is not by itself a statistically estimated baseline distribution. A robust implementation should usually replay both:

- a **reference arm**, reconstructing the recorded state and rerunning the unchanged policy; and
- an **intervention arm**, applying the declared edit.

This serves two purposes. It estimates ordinary stochastic variability and provides a replay-fidelity diagnostic: if the reference arm almost never reproduces an equivalent action or outcome, counterfactual comparisons around the recorded run may be poorly supported.

Where the model and environment permit shared seeds or coupled random streams, paired effects can reduce variance. Pairing must be logged, and the library must not imply paired randomness for hosted providers that do not guarantee it. Causal Agent Replay explicitly distinguishes exact or near-exact local seeded replay from irreducibly nondeterministic hosted replay. citeturn3view1turn3view2turn23view2

### Correlated and redundant context

Ordinary feature attribution becomes unstable when documents, memory entries, or messages are correlated. Three different questions should not be conflated:

**Interventional deletion:** What happens if this exact component is removed while all others remain? This is operationally clear but may create an implausible context.

**Conditional replacement:** What happens if the component is replaced by a plausible draw conditional on related context? This stays closer to the observed data distribution but requires a defensible conditional generator.

**Group intervention:** What happens if the whole semantic cluster, provenance group, or retrieval source is removed? This is usually the most stable option for duplicated RAG evidence.

Recommended safeguards are:

- cluster near-duplicate or same-provenance context before attribution;
- report group effects before individual effects;
- test pairwise or declared coalitions for likely interactions;
- show coefficient or rank instability across ablation samples;
- avoid calling a Lasso or Shapley allocation uniquely causal when redundant evidence permits several equivalent allocations;
- retain the actual intervention semantics in the result object.

ContextCite’s sparse linear model is efficient when only a few sources matter, but sparsity does not itself resolve correlated-source identification. citeturn18view1turn17view0

### Multiple comparisons

Testing \(m\) steps independently at a nominal 5% threshold can produce false discoveries even when no step matters. The API should support:

- Holm or Bonferroni control for a small confirmatory candidate set;
- false-discovery-rate control for exploratory screening;
- simultaneous bootstrap or max-statistic intervals when correlated candidate effects are jointly estimated;
- and a clear distinction between unadjusted exploratory intervals and adjusted confirmatory intervals.

Causal Agent Replay’s per-step confidence intervals are a useful start, but a production library should make family-wise candidate testing explicit rather than leaving the user to interpret many overlapping intervals. citeturn3view1turn3view2

### A principled result taxonomy

A binary “causal/not causal” return value is statistically and operationally inadequate. The result should distinguish:

| Status | Meaning |
|---|---|
| `material_effect` | Interval lies beyond a user-defined practical threshold \(\delta\) |
| `negligible_effect` | Interval lies entirely within \([-\delta,+\delta]\) |
| `insufficient_evidence` | Interval still includes both meaningful effect and negligible/no effect |
| `direction_uncertain` | Interval includes meaningful positive and negative effects |
| `out_of_support` | Intervention creates states/actions outside declared support |
| `low_replay_fidelity` | Reference replay does not adequately reproduce the recorded decision regime |
| `restoration_failed` | World or prefix state could not be reconstructed |
| `budget_exhausted` | Cost ceiling reached before a decision criterion |
| `outcome_unavailable` | No reproducible outcome function or verifier exists |
| `nonidentifiable` | Available interventions cannot distinguish competing causal structures |

This allows the library to say “we do not know” for the right reason. In particular, `negligible_effect` is evidence of practical equivalence; `insufficient_evidence` is not.

Coverage limits should accompany every report:

```json
{
  "estimand": "risk_difference",
  "reference_probability": 0.72,
  "intervention_probability": 0.39,
  "effect": -0.33,
  "confidence_interval": [-0.48, -0.16],
  "reference_replays": 96,
  "intervention_replays": 96,
  "multiplicity_adjustment": "holm",
  "replay_fidelity": "EXACT_SNAPSHOT",
  "action_match_rate_reference": 0.81,
  "outcome_evaluator": "deterministic_rule_v3",
  "status": "material_effect",
  "practical_threshold": 0.10
}
```

## Design decisions and open problems for `xai`

### Recommended Layer B scope

The first viable release should implement a small causal-analysis kernel rather than a universal replay engine:

1. **Canonical intervention protocol.** Define interventions over canonical trajectory objects: context inclusion, observation replacement, action forcing, same-policy resampling, tool availability, policy substitution, and component-group toggles.
2. **User-supplied replay adapter.** `xai` should call an adapter supplied by the application or benchmark. It should not become an agent runtime, trace store, or sandbox product.
3. **Outcome protocol.** Prefer deterministic rules, test suites, environment predicates, or human-validated structured scores. LLM judges may be accepted as noisy evaluators but must be labeled as such and replicated.
4. **Reference and intervention arms.** Estimate both unless the estimand explicitly conditions on the single observed trajectory.
5. **Uncertainty-first results.** Return effect, interval, sample count, fidelity, support diagnostics, and abstention status.
6. **Hierarchical attribution.** Begin with components or causal groups, then refine to steps; reserve Shapley for small candidate sets.
7. **Candidate localizers as optional plugins.** AgentRx-like invariant checks, graph methods, or LLM judges can rank candidates but may not emit causal verdicts.
8. **Benchmark harness, not eval runner.** Include fixtures and adapters for synthetic SCMs, Aegis injections, Who&When metadata, and TraceElephant, while leaving task execution to the source framework.

### Replay budget

A reasonable default policy is:

| Mode | Budget | Intended use |
|---|---:|---|
| `screen` | 16–24 replays per arm | Candidate prioritization only |
| `standard` | Up to 128 per arm | Medium-to-large effects |
| `confirm` | Up to 512 per arm | Narrower intervals and adjusted testing |
| `custom` | User-specified sequential rule | High-stakes or rare outcomes |

The library should estimate projected cost before execution and allow global, per-candidate, and per-coalition budgets. For Shapley analysis, the budget should be expressed separately as number of permutations, coalition rollouts, and suffix executions; a single opaque “samples” parameter will make costs difficult to predict.

### State restoration

The trace schema should include a **replay manifest** adjacent to, but distinct from, OpenTelemetry or OpenInference fields:

```text
policy identity and revision
sampling parameters and provider seed, when meaningful
system/developer instructions
tool schemas and tool implementation versions
full model-visible message state
external-resource snapshot identifiers
clock and timezone
random-number stream identifiers
user-simulator state
sub-agent identity and configuration
secret/reference handles, never raw secrets by default
outcome-evaluator version
state hashes before and after replay
```

The critical provider-neutral abstraction is not “replay this span.” It is:

```python
restore(checkpoint) -> RestorationReport
apply(intervention) -> InterventionReport
run_suffix(policy, budget) -> CounterfactualTrajectory
evaluate(trajectory) -> Outcome
```

That interface lets applications use database snapshots, mocked tool observations, browser containers, deterministic simulators, or live dry-run services without `xai` owning any of them.

### Benchmark priorities

The minimum credible evidence ladder is:

- **Unit SCMs:** exact ground truth for estimators and interactions.
- **Stateful synthetic agents:** real prompts and tools over a forkable world.
- **Aegis-derived planted failures:** scalable and diverse, after effect verification.
- **Who&When:** comparability with judge-based localization.
- **TraceElephant:** executable real-framework integration and replay fidelity.
- **At least one partner deployment:** retrospective, side-effect-safe replay of real failures with independently defined outcome rules.

Until the final tier exists, the project should say “validated on synthetic and public agent benchmarks,” not “validated on deployed agents.”

### Differentiation from LLM-judge root-cause prose

The differentiation should be structural and visible in the API:

| LLM-judge diagnosis | `xai` causal attribution |
|---|---|
| Reads trace and writes a plausible explanation | Declares and executes an intervention |
| Often relies on rationale or visible error language | Uses actions, observations, state, and outcome changes |
| Produces an uncalibrated label or prose | Produces an effect estimate and interval |
| May confuse propagated symptom with origin | Tests earlier and later candidate loci |
| Does not require replay fidelity | Reports restoration and reference-replay fidelity |
| Usually has no falsifiable counterfactual | Emits replay artifacts sufficient to reproduce the test |
| Tends to force a root cause | Can return negligible effect, insufficient evidence, or nonidentifiable |
| Explanation may cite hidden reasoning | Never treats chain-of-thought or judge rationale as causal ground truth |

AgentRx and CHIEF demonstrate that structured logs, generated constraints, and causal graphs can improve trace-based diagnosis, but both ultimately rely on generated reasoning or virtual oracles. Their outputs are valuable supporting evidence, not substitutes for intervention results. citeturn21view1turn17view5

### Open problems

**Faithful replay across hosted providers remains unsolved.** Even with identical visible parameters, provider-side batching, kernels, model revisions, routing, and hidden system behavior may change. The correct response is to measure reference replay behavior and characterize an empirical policy, not claim bit-for-bit reproducibility. citeturn3view1turn3view2

**World restoration is application-specific.** Telemetry standards can carry model-facing state but cannot automatically rewind a bank ledger, web search index, browser session, human user, or third-party service. The library needs explicit adapters and fidelity grades rather than pretending trace completeness solves state completeness. citeturn5search5turn5search6turn22view0

**Counterfactual repairs are intervention-generator dependent.** Failure to find a successful replacement may mean the step is not causal, or merely that the proposer failed. CausalFlow’s binary repair-existence score and oracle-guided approaches such as AgenTracer and CHIEF must therefore report proposal coverage and generator identity. citeturn12view0turn12view1turn2view2turn17view5

**Unique blame is often not identified.** DoVer observes that multiple distinct interventions can independently repair a run. Redundant causes, compensating mechanisms, and alternative plans make “the responsible step” an unnatural target in some systems. A set of sufficient repairs or an effect allocation may be more faithful. citeturn17view3turn17view4

**Shapley values answer a cooperative-game allocation question, not an unqualified causal one.** Their meaning depends on the coalition value, the baseline, whether absent components are deleted or replaced, and how impossible coalitions are handled. `xai` should name the exact game and intervention semantics in every Shapley report.

**Outcome functions are part of the causal specification.** A deterministic business predicate, unit test, milestone graph, semantic similarity score, and LLM judge define different causal questions. ToolSandbox’s milestone-DAG approach and DoVer’s progress metrics show that intermediate structured outcomes can be more informative than a single final pass/fail bit. citeturn22view0turn17view3

**Observed traces may omit the actual decision context.** TraceElephant reports substantial gains when model inputs and system configuration are added to output-only traces, reinforcing that a provider-neutral canonical schema must retain the state each component actually observed—not merely chronological messages. citeturn18view7turn23view1

**There is no established calibration benchmark.** Existing work emphasizes localization accuracy, repair rate, or attribution stability; little evidence establishes nominal confidence-interval coverage over realistic agent trajectories. This is a tractable place for `xai` to lead: publish planted effects, replay data, empirical coverage, abstention curves, and cost curves.

The strongest defensible product position is therefore:

> `xai` does not infer faithful causes from an agent’s prose. It turns recorded state and user-declared interventions into reproducible counterfactual experiments, estimates changes in action or outcome distributions, quantifies uncertainty and replay fidelity, tests interacting components when budget permits, and explicitly abstains when the trace or environment cannot support the claim.