# KAOS-E5-1 — Pydantic Evals

Deep dive on [pydantic-evals](https://pypi.org/project/pydantic-evals/), the evaluation harness from the Pydantic AI team, assessed as the engine to embed in a KAOS-owned eval runner. All claims verified against the [official docs](https://pydantic.dev/docs/ai/evals/evals/) (ai.pydantic.dev/evals redirects there) and the [pydantic/pydantic-ai source](https://github.com/pydantic/pydantic-ai/tree/main/pydantic_evals).

## 1. Core contract: Dataset, Case, Evaluator

The mental model is three nouns ([core concepts](https://pydantic.dev/docs/ai/evals/core-concepts)): a `Dataset` is a static, serializable collection of test cases plus dataset-level evaluators; a `Case` is one scenario; an "Experiment" is one execution of a task function against all cases, producing an `EvaluationReport`.

- [`Case`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/dataset.py) fields: `name: str | None`, `inputs: InputsT`, `metadata: MetadataT | None`, `expected_output: OutputT | None`, and per-case `evaluators`. `Dataset[InputsT, OutputT, MetadataT]` is generic over all three, giving type-checked datasets.
- The task under test is any callable taking the case inputs: `Dataset.evaluate(task, ...)` accepts `Callable[[InputsT], Awaitable[OutputT]] | Callable[[InputsT], OutputT]` — both sync and async functions work ([dataset.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/dataset.py)). `evaluate_sync()` is a blocking wrapper with identical parameters.
- `evaluate()` parameters (verified in source): `name`, `max_concurrency: int | None = None`, `progress: bool = True`, `retry_task`, `retry_evaluators`, `task_name`, `metadata` (attached to the experiment), `repeat: int = 1` (run each case N times), and `lifecycle` ([case lifecycle hooks](https://pydantic.dev/docs/ai/evals/how-to/lifecycle)).
- Concurrency: by default all cases (and evaluators) run concurrently; `max_concurrency` caps parallelism, `max_concurrency=1` forces sequential execution for debugging ([concurrency docs](https://pydantic.dev/docs/ai/evals/how-to/concurrency)).
- Retries: [retry strategies](https://pydantic.dev/docs/ai/evals/how-to/retry-strategies) are built on [Tenacity](https://tenacity.readthedocs.io/) via `retry_task` / `retry_evaluators` configs (`stop`, `wait`, `retry`, `reraise`, `before_sleep`); exhausted evaluator retries are recorded as `EvaluatorFailure` rather than aborting the run. There is no built-in per-task timeout in `Dataset.evaluate` — timeouts must be enforced inside the task (e.g. HTTP client timeout) or asserted after the fact with `MaxDuration`.
- Task exceptions do not kill the experiment: failed cases land in `EvaluationReport.failures` as `ReportCaseFailure` entries ([reporting source](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/reporting/__init__.py)).

Minimal shape of a KAOS-style experiment (API names verified against [dataset.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/dataset.py)):

```python
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EqualsExpected, MaxDuration

dataset = Dataset(
    cases=[Case(name='greeting', inputs='Hello', expected_output='Hi there')],
    evaluators=[EqualsExpected(), MaxDuration(seconds=10)],
)

async def task(inputs: str) -> str:
    # KAOS: HTTP call to the deployed agent's OpenAI-compatible endpoint
    return await call_agent(inputs)

report = dataset.evaluate_sync(task, max_concurrency=5)
```

## 2. Dataset serialization

- `dataset.to_file(path, fmt='yaml'|'json'|None, schema_path=...)` writes YAML or JSON (format inferred from extension) and by default also emits a companion JSON schema file (e.g. `my_dataset_schema.json`) referenced via `$schema` for IDE autocomplete/validation ([dataset management](https://pydantic.dev/docs/ai/evals/how-to/dataset-management)).
- Loading: `Dataset.from_file(path, fmt=None, custom_evaluator_types=(), ...)`, plus `from_text()` and `from_dict()`. Datasets that reference custom evaluators must pass those classes via `custom_evaluator_types` so the serialized evaluator specs can be reconstructed ([dataset.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/dataset.py)).
- `Dataset.model_json_schema_with_evaluators(custom_evaluator_types, ...)` generates the JSON schema programmatically; an async `generate_dataset()` helper can bootstrap datasets with an LLM ([dataset management](https://pydantic.dev/docs/ai/evals/how-to/dataset-management)).
- Versioning story: there is no built-in dataset versioning — datasets are plain YAML/JSON files, and the docs' implicit answer is git plus separate files per suite (smoke/regression/comprehensive). Evaluators, by contrast, can declare `get_evaluator_version()` so results can be filtered by evaluator version in dashboards ([evaluator.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/evaluator.py)). Any dataset-version-to-results linkage is something KAOS would have to own (e.g. content hash in `experiment metadata`).

## 3. Evaluator library and scoring model

Built-in case-level evaluators, verified against [evaluators/common.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/common.py) and the [built-in evaluators docs](https://pydantic.dev/docs/ai/evals/evaluators/built-in):

- `Equals(value)` and `EqualsExpected()` — exact match against a literal or the case's `expected_output` (skips when `expected_output is None`).
- `Contains(value, case_sensitive=True, as_strings=False)` — substring/element/dict-subset containment, returns an `EvaluationReason` with an explanation.
- `IsInstance(type_name)` — type check by class name.
- `MaxDuration(seconds: float | timedelta)` — task latency assertion.
- `LLMJudge(...)` and `GEval(criteria, evaluation_steps, score_range=(1, 5), ...)` — LLM-based judging (see section 4); GEval implements chain-of-thought [G-Eval](https://pydantic.dev/docs/ai/evals/evaluators/built-in) scoring.
- `HasMatchingSpan(query: SpanQuery)` — OTel span assertions (section 5).
- The `DEFAULT_EVALUATORS` tuple on `main` additionally includes agent-trajectory evaluators — `ToolCorrectness`, `TrajectoryMatch`, `ArgumentCorrectness`, `MaxToolCalls`, `MaxModelRequests` — plus report-level `ConfusionMatrixEvaluator` and `PrecisionRecallEvaluator` for classification-style datasets ([built-in docs](https://pydantic.dev/docs/ai/evals/evaluators/built-in)); these are recent additions, so pin the package version before relying on them.

Custom evaluators subclass the [`Evaluator`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/evaluator.py) dataclass and implement `evaluate(self, ctx: EvaluatorContext) -> EvaluatorOutput | Awaitable[EvaluatorOutput]` — the framework auto-detects sync vs async. `EvaluatorContext` exposes `name`, `inputs`, `metadata`, `expected_output`, `output`, `duration`, `span_tree`, `attributes`, and `metrics` ([context.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/context.py)).

The scoring model is by return type: `EvaluatorOutput = EvaluationScalar | EvaluationReason | Mapping[str, ...]` where `EvaluationScalar = bool | int | float | str` — a `bool` becomes an assertion (pass/fail), `int`/`float` a score, `str` a label, and `EvaluationReason(value, reason)` attaches a justification; a mapping returns several named results from one evaluator ([evaluator.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/evaluator.py)).

## 4. LLMJudge specifics

Verified against [llm_as_a_judge.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/llm_as_a_judge.py) and the [LLMJudge docs](https://pydantic.dev/docs/ai/evals/evaluators/llm-judge):

- Fields: `rubric: str` (required), `model: Model | KnownModelName | str | None = None`, `include_input: bool = False`, `include_expected_output: bool = False`, `model_settings: ModelSettings | None = None`, `score: OutputConfig | False = False`, `assertion: OutputConfig | False = OutputConfig(include_reason=True)` — i.e. by default it emits a pass/fail assertion with a reason; enabling `score` adds a 0.0–1.0 numeric score, and both can be produced simultaneously.
- Under the hood it calls a Pydantic AI agent with structured output `GradingOutput` (`reason: str`, `pass: bool`, `score: float`), via helper functions `judge_output`, `judge_input_output`, `judge_output_expected`, `judge_input_output_expected`.
- Default judge model: module-level `_default_model = 'openai:gpt-5.2'`, overridable globally with `set_default_judge_model()` or per-evaluator via `model`.
- Custom base URL (the KAOS LiteLLM/ModelAPI case): `model` accepts any Pydantic AI `Model` object, so an `OpenAIChatModel('<name>', provider=OpenAIProvider(base_url=..., api_key=...))` pointed at an OpenAI-compatible proxy works ([pydantic-ai OpenAI-compatible models docs](https://pydantic.dev/docs/ai/models/openai/)); with plain model strings like `'openai:gpt-4o'`, the base URL comes from the `OPENAI_BASE_URL` / `OPENAI_API_KEY` environment variables. Both routes are compatible with routing judge traffic through the KAOS ModelAPI.
Judge routed through an OpenAI-compatible proxy (the ModelAPI pattern):

```python
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_evals.evaluators import LLMJudge

judge = LLMJudge(
    rubric='Response answers the question without fabricating facts.',
    model=OpenAIChatModel(
        'gpt-4o',  # model name as exposed by the LiteLLM proxy
        provider=OpenAIProvider(base_url='http://modelapi.kaos.svc/v1', api_key='...'),
    ),
    include_input=True,
    score={'include_reason': True},
)
```

- Caveat from the docs: judges are non-deterministic; recommended mitigations are `temperature=0.0` via `model_settings`, repeated runs, and validating the judge against human-labeled cases ([LLMJudge docs](https://pydantic.dev/docs/ai/evals/evaluators/llm-judge)).

## 5. Trajectory / span-based evaluation — and the remote-agent catch

- When [Logfire](https://pydantic.dev/docs/logfire/) is installed and configured (`pip install 'pydantic-evals[logfire]'` + `logfire.configure()`), the harness records the OTel spans emitted during each task invocation into a `SpanTree`, exposed as `ctx.span_tree` to evaluators; the docs state plainly that "span-based evaluation requires `logfire` to be installed and configured" ([span-based docs](https://pydantic.dev/docs/ai/evals/evaluators/span-based)). Without it, accessing `ctx.span_tree` raises `SpanTreeRecordingError` ([context.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/context.py)) — so span assertions do not work with a bare OTel SDK setup; the `logfire` package is the capture mechanism even though the data is standard OTel (a Logfire cloud account/token is a separate concern from local capture, e.g. `logfire.configure(send_to_logfire=False)` keeps it local).
- `HasMatchingSpan(query=SpanQuery(...))` asserts on the tree declaratively: name equals/contains/regex, attribute key-values, span status, min/max duration, and structural conditions (ancestor/descendant/child queries, `not_`/`and_`/`or_` combinators); `SpanTree.find(...)` and `SpanNode` (name, duration, attributes, timestamps, parent/children) support custom trajectory evaluators ([span-based docs](https://pydantic.dev/docs/ai/evals/evaluators/span-based)).
- The remote-agent catch (critical for KAOS): span capture is in-process — the `SpanTree` only contains spans created inside the harness process during the task function's execution. If the task function is an HTTP call to an agent running in another pod, the tree will contain the HTTP client span but none of the remote agent's internal spans (model calls, tool calls), because those are exported by the agent pod's own tracer to its collector, never to the harness. Trace-context propagation (W3C `traceparent` on the HTTP request) will correlate both halves in a shared backend, but pydantic-evals has no mechanism to fetch remote spans back into `ctx.span_tree`. For KAOS this means `HasMatchingSpan`-style trajectory checks on deployed agents require either (a) a KAOS-owned custom evaluator that queries the tracing backend by trace ID after the task returns, or (b) running the agent code in-process inside the runner, which defeats the purpose of evaluating the deployed artifact.

## 6. Reporting and result export

- `Dataset.evaluate()` returns an [`EvaluationReport`](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/reporting/__init__.py) with `name`, `cases: list[ReportCase]`, `failures: list[ReportCaseFailure]`, `analyses: list[ReportAnalysis]` (from report-level evaluators), `experiment_metadata`, and optional `trace_id`/`span_id` linking the run to its trace.
- Each `ReportCase` carries `inputs`, `output`, `expected_output`, `metadata`, `task_duration`, `total_duration`, `metrics`, and the evaluator results split into `scores`, `labels`, and `assertions` dicts of `EvaluationResult` (name, value, reason, source spec, evaluator_version).
- Console output: `report.print(include_input=..., include_output=..., include_durations=...)` / `render()` produce a rich table with per-case results and an averages row; `averages()` returns a `ReportCaseAggregate`, `case_groups()` groups multi-run (`repeat > 1`) results, and `print`/`render` accept a baseline report for diff-style comparison ([reporting source](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/reporting/__init__.py)).
- Structured export: `EvaluationReport` is a dataclass, but the module ships `EvaluationReportAdapter = TypeAdapter(EvaluationReport[Any, Any, Any])` (and `ReportCaseAdapter`), so `EvaluationReportAdapter.dump_python(report)` / `dump_json(report)` yields fully structured JSON — exactly what a KAOS-owned results store needs; no scraping of console output required.

```python
from pydantic_evals.reporting import EvaluationReportAdapter

report_json = EvaluationReportAdapter.dump_json(report)  # -> KAOS results store
gate_ok = all(r.value for case in report.cases for r in case.assertions.values())
```

## 7. Experiments, comparison, and viewing

- Every experiment emits OTel traces (experiment span, per-case spans, task and evaluator spans); with the `logfire` extra configured, runs appear in Logfire's "Evals: Datasets & Experiments" UI with pass rates, timings, and checkbox-driven side-by-side comparison of experiments over the same cases ([Logfire evals guide](https://pydantic.dev/docs/logfire/evaluate/evals/)).
- Comparison is otherwise DIY-but-supported: the same dataset run against different task versions yields comparable reports, and `report.print(baseline=other)` diffs two runs locally ([core concepts](https://pydantic.dev/docs/ai/evals/core-concepts)).
- OSS self-hosted viewing: there is no OSS eval-viewer from Pydantic. Logfire is a commercial SaaS (self-hosting exists only as an [enterprise offering](https://pydantic.dev/docs/logfire/reference/self-hosted/overview/)); the raw spans are standard OTel and can go to any backend (Jaeger, Grafana Tempo), but the dedicated experiment/comparison UI is Logfire-specific. A KAOS results store fed from the serialized `EvaluationReport` is the realistic self-hosted path.

## 8. Maturity

- Lives inside the [pydantic/pydantic-ai monorepo](https://github.com/pydantic/pydantic-ai/tree/main/pydantic_evals) as the `pydantic_evals` package, versioned in lockstep with pydantic-ai (depends on `pydantic-ai-slim` at the matching version); latest release at time of writing is [2.11.0 on PyPI](https://pypi.org/project/pydantic-evals/), MIT licensed, Python >=3.10, core deps only `pydantic`, `pydantic-ai-slim`, `rich`, `logfire-api`, `anyio`, `pyyaml` ([pyproject.toml](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pyproject.toml)).
- Release cadence tracks pydantic-ai's frequent releases; the API surface has been reorganized recently (new trajectory/report-level evaluators, retry/lifecycle/repeat parameters), so KAOS should pin an exact version and treat upgrades as deliberate. The package explicitly positions itself as usable with "arbitrary stochastic functions", not only Pydantic AI agents ([PyPI](https://pypi.org/project/pydantic-evals/)).

## 9. How it would embed in KAOS

The fit is clean: a KAOS eval runner (Kubernetes Job or service) loads a `Dataset` from a YAML/JSON artifact (ConfigMap/volume sourced from a KAOS Eval CRD), and the task function is a thin async HTTP client that calls the deployed agent's OpenAI-compatible chat endpoint (or A2A) — pydantic-evals neither knows nor cares that the "task" is a remote pod. `max_concurrency` maps to a CRD field, `retry_task` absorbs transient network/agent errors, `experiment_metadata` carries agent image/revision and dataset hash, and `LLMJudge` is routed through the ModelAPI/LiteLLM proxy via an `OpenAIChatModel` with a custom `base_url`. After the run, the runner serializes the report with `EvaluationReportAdapter.dump_json()` into the KAOS results store, evaluates pass/fail gates (e.g. assertion pass rate, score thresholds from `averages()`), and sets CRD status accordingly.

What KAOS must own around the engine: (1) results persistence and history — pydantic-evals keeps nothing between runs; (2) dataset versioning/identity (content hash into `experiment_metadata`); (3) gating logic and CRD status semantics — the library reports, it does not judge release-worthiness; (4) judge model routing and credentials via ModelAPI; (5) remote-trace correlation — propagate `traceparent` from the task function and, if trajectory checks are required, a custom evaluator that pulls the agent pod's spans from the OTel backend by trace ID, since `ctx.span_tree` only sees harness-local spans; (6) the runner image and scheduling itself.

Risks / gaps:

- Span-based/trajectory evaluators are effectively blind to remote agents' internals — the headline `HasMatchingSpan` feature needs KAOS-built backend-query plumbing to be useful in-cluster ([span-based docs](https://pydantic.dev/docs/ai/evals/evaluators/span-based)).
- Span capture requires the `logfire` package even for local-only use; a bare OTel SDK is not enough ([span-based docs](https://pydantic.dev/docs/ai/evals/evaluators/span-based)).
- No built-in per-case timeout; a hung agent HTTP call must be bounded by the client, or the Job's `activeDeadlineSeconds`.
- No dataset versioning, no results storage, no run history or regression detection — all KAOS-owned ([dataset management](https://pydantic.dev/docs/ai/evals/how-to/dataset-management)).
- The polished experiment-comparison UI is Logfire SaaS; the OSS path is raw OTel plus KAOS's own report store ([Logfire evals guide](https://pydantic.dev/docs/logfire/evaluate/evals/)).
- API is young and moving (new evaluators and `evaluate()` parameters landing on `main`); version pinning and an internal adapter layer around `Dataset`/`EvaluationReport` are advisable.
- `LLMJudge` defaults to an OpenAI model string; unless KAOS always injects an explicit `model`, a misconfigured runner would silently try to reach OpenAI directly instead of the ModelAPI ([llm_as_a_judge.py](https://github.com/pydantic/pydantic-ai/blob/main/pydantic_evals/pydantic_evals/evaluators/llm_as_a_judge.py)).
