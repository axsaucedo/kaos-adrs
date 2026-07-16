# P1 learnings — `kaos-evals` library and runner

Learnings from implementing the [P1 plan](../../plan/P1-eval-library-and-runner.md) (branch `feat/kaos-evals-library`, eight commits, 46 package tests green, `pydantic-ai-server` untouched and green).

## Engine validation (all three hypotheses passed)

- Pinned `pydantic-evals==2.11.0` with `pydantic-ai==2.11.0` aligned. Note `pydantic-evals` installs `pydantic-ai-slim`; the full `pydantic-ai` pin is what provides `OpenAIChatModel`/`OpenAIProvider` for judges.
- `Dataset.evaluate(task, max_concurrency=..., repeat=..., progress=False)` covers both execution controls directly — `repeat` is now a first-class keyword, slightly ahead of what [KAOS-E5-1](../../research/KAOS-E5-1-pydantic-evals.md) recorded.
- `LLMJudge` routes through an explicit `OpenAIChatModel(provider=OpenAIProvider(base_url=..., api_key=...))`; a local OpenAI-compatible stub received the judge call with no real key, confirming the `ModelAPI` routing decision of [adr_0001](../../adrs/adr_0001_eval-model-contract-and-harness-engine.md).
- Engine sharp edge: `LLMJudge` `score`/`assertion` output config must be a mapping (`{"include_reason": True}`); the annotation accepts literal `True` but 2.11.0 raises at runtime on `.get()`. The harness constructs judge output explicitly and never hits the edge.
- `EvaluationReportAdapter.dump_json()`/`validate_json()` round-trip losslessly: scores, labels, assertions, reasons, durations, repeat source-case names, and trace/span IDs all survive — the boundary mapping needed no supplements.
- Engine evaluator failures surface per case in `ReportCase.evaluator_failures`, mapping cleanly onto the inconclusive-evaluator failure kind of [adr_0002](../../adrs/adr_0002_execution-model-and-runner.md).

## Implementation learnings

- The `kaos-memory` layering transplanted cleanly: core (`pydantic`, `pyyaml`, `opentelemetry-api`) with `[runner]`/`[dev]` extras; lint via black + pinned `ty@0.0.55`.
- The cross-component test used the real `AgentServer` (no stub fallback needed): sibling `pydantic-ai-server` and `kaos-memory` installed editable in the eval CI env, `DEBUG_MOCK_RESPONSES` for determinism, invoked through `LocalTarget` over `httpx.ASGITransport`.
- Ambient repo drift, not touched: `pydantic-ai-server`'s Makefile invokes unpinned `uvx ty`, which resolved the newly-released `ty 0.0.59` and reports five pre-existing `unused-ignore-comment` warnings; the repo's established pin (`ty@0.0.55`) is green. A repo-wide ty-pin follow-up is recorded for later, outside the evals track.

## Plan deltas for P2

- None structural: the runner entrypoint, artifact schema (`summary.json` + `report.json`), env/flag surface, and exit codes landed as planned, so the operator phase can wire the Job exactly as [adr_0003](../../adrs/adr_0003_control-plane-eval-crd-operator-and-cli.md) describes.
- The runner image Dockerfile (deferred from this phase) should mirror `kaos-memory/Dockerfile` and install `kaos-evals[runner]` only — the cross-component editable-install arrangement is a test-env concern, not an image concern.
