# KAOS-E1 — Current KAOS evaluation surface and limitations

## Overview

KAOS does not currently implement an evaluation capability as a product concept. It does, however, expose most of the lower-level mechanisms from which one could be built: deterministic model substitution, programmatic and HTTP agent invocation, A2A task lifecycle APIs, bounded autonomous execution, tool and delegation instrumentation, an OTLP export path, Kubernetes reconciliation patterns, and extensive unit and KIND-based end-to-end tests.

The important distinction is between testing a known behavior and evaluating an agent over a declared corpus. Existing tests hand-author one deployment and one or a few prompts, select canned model turns through `DEBUG_MOCK_RESPONSES`, and assert HTTP responses, Kubernetes state, memory events, or task transitions. No repository-owned type represents an evaluation case, dataset, evaluator, score, result set, threshold, comparison, or run. A repository-wide search for evaluation terminology finds only unrelated Python/OPA expression evaluation and Kubernetes' inherited Flocker `datasetName` fields, not an agent-evaluation subsystem.

The closest architecture already present is therefore a composition of three planes: the agent runtime supplies execution and trajectory signals; telemetry supplies an online observation stream; and the operator supplies declarative lifecycle, image selection, dependency resolution, and gateway exposure. None of these planes currently performs scoring.

## Runtime testing and mocking surfaces

### Deterministic model substitution

`DEBUG_MOCK_RESPONSES` is the principal deterministic runtime seam. `_build_mock_model_function()` reads the environment variable, parses a JSON list or treats a non-list/non-JSON value as a one-item sequence, and captures it in mutable `_MockResponseState`; each model call consumes the next entry, falling back to `[no more mock responses]` after exhaustion (`pydantic-ai-server/pais/serverutils.py:239-287`).

Mock entries that parse as an object containing `tool_calls` become Pydantic AI `ToolCallPart` values with name, arguments, and call ID; other entries become `TextPart` output (`pydantic-ai-server/pais/serverutils.py:254-285`). This permits deterministic plain replies, MCP calls, delegation calls, and multi-step agentic loops without a live model.

Model resolution has three explicit paths: a caller-supplied model object wins; then `DEBUG_MOCK_RESPONSES` produces a `FunctionModel`; otherwise a configured ModelAPI becomes either a string-mode `FunctionModel` or an `OpenAIChatModel` (`pydantic-ai-server/pais/serverutils.py:290-325`). A programmatic harness can consequently inject Pydantic AI `TestModel`, `FunctionModel`, or another model directly, while a deployed harness can inject only environment configuration unless it supplies a custom runtime image.

The mock state is reset at the start of every external chat request (`pydantic-ai-server/pais/server.py:503-515`). A `LocalTaskManager` instead receives the reset function as its per-task setup hook (`pydantic-ai-server/pais/server.py:128-138`), allowing A2A tasks to begin from the deterministic template. Autonomous iterations intentionally consume the shared response sequence across iterations rather than resetting every iteration.

This seam is useful for protocol and orchestration conformance, but it is not a realistic quality evaluation by itself: the model decision is predetermined, and there is no case identity, expected output, rubric, or score attached to the sequence.

### Programmatic agent execution

`create_agent_server()` is the high-level construction seam. It loads settings, initializes logging and OTel, parses MCP and peer-agent configuration, selects memory and task-manager backends, resolves the model, assembles MCP/delegation/memory toolsets, and either creates or augments a Pydantic AI agent (`pydantic-ai-server/pais/server.py:757-810`). It returns an `AgentServer`, whose FastAPI application is available as `server.app` and whose runtime agent is available internally.

`AgentServer._run_agent(message, session_id)` is the smallest complete non-streaming run boundary: it prepares prompt/history/dependencies/usage limits, calls `self._agent.run`, derives the output and tool-call count, persists new messages and response events, and returns `(response_text, tool_call_count)` (`pydantic-ai-server/pais/server.py:475-501`). An in-process evaluation library could call this boundary, although its underscore marks it private and its return value omits the full Pydantic AI result, usage, timings, and structured trajectory.

`AgentServer._process_message()` is the shared streaming/non-streaming path used by HTTP handling. The streaming branch exposes progress chunks when model responses contain tool calls and delegates actual node execution to Pydantic AI (`pydantic-ai-server/pais/server.py:503-570`). An eval harness can therefore use the public HTTP API for stable black-box behavior or the private `_run_agent` seam for faster white-box execution, but KAOS currently publishes no dedicated evaluator-facing runner interface.

The test helper `make_test_server()` demonstrates direct construction: it accepts an injected model, memory, sub-agents, limits, and task-manager selection, constructs `PydanticAgent[AgentDeps]`, and returns an `AgentServer` (`pydantic-ai-server/tests/helpers.py:21-73`). This is the strongest existing prototype for an in-process eval fixture.

### HTTP and server routes

`AgentServer` mounts its normal routes, the A2A routes, identity propagation, and optional HTTP instrumentation on one FastAPI application (`pydantic-ai-server/pais/server.py:140-187`). The runtime exposes health/readiness, agent-card discovery, OpenAI-compatible `POST /v1/chat/completions`, memory inspection, and root-path A2A JSON-RPC.

The chat-completions path wraps both non-streaming and streaming work in a `server-run` SERVER span and invokes `_process_message()` (`pydantic-ai-server/pais/server.py:570-620`). This is the most interoperable black-box hook because existing CLI and E2E code already understand it.

The OpenAI-compatible response gives a harness final content and a session identifier, while streaming additionally surfaces progress events. It does not return a normalized trajectory, evaluator metadata, cost, per-tool assertions, or score.

### A2A tasks and autonomous execution

The A2A `TaskManager` abstraction owns synchronous messages, autonomous submission, listing, retrieval, cancellation, waiting, and shutdown (`pydantic-ai-server/pais/a2a.py:225-290`). `LocalTaskManager` stores tasks in memory, executes ordinary tasks inline, and launches autonomous tasks with `asyncio.create_task` (`pydantic-ai-server/pais/a2a.py:292-380`). `NullTaskManager` is the disabled/no-op alternative.

The root `POST /` route dispatches JSON-RPC (`pydantic-ai-server/pais/a2a.py:1086-1092`). `SendMessage` extracts text and `contextId`, preserves message metadata, invokes either `send_message` or `submit_autonomous`, and returns the serialized task (`pydantic-ai-server/pais/a2a.py:930-1000`). `GetTask`, `ListTasks`, and `CancelTask` provide polling and lifecycle control. This gives an external harness a natural asynchronous run ID and status API.

Autonomous A2A submission accepts maximum iterations, runtime, tool calls, and interval; the loop enforces those budgets and records a budget-exhausted event (`pydantic-ai-server/pais/a2a.py:977-994`, `pydantic-ai-server/pais/a2a.py:593-630`). Completion for bounded asynchronous mode is inferred when an iteration makes no tool calls (`pydantic-ai-server/pais/a2a.py:716-726`). Startup autonomous mode instead runs continuously with only a per-iteration timeout and is launched during server lifespan when a goal is configured (`pydantic-ai-server/pais/server.py:191-215`).

An eval runner could reuse A2A tasks for long-running cases and cancellation, but task state is process-local, task output is a single final string, event history records lifecycle rather than a complete multi-agent trajectory, and continuous autonomous mode has no natural evaluation completion criterion.

### Delegation and multi-agent execution

`DelegationToolset` dynamically exposes active peer agents as model-callable tools and executes through `execute_delegation` (`pydantic-ai-server/pais/tools.py:55-109`). Delegation reconstructs recent user/assistant context from memory, appends the delegated task, calls `RemoteAgent.process_message`, and converts failures into textual tool results (`pydantic-ai-server/pais/tools.py:111-157`).

`RemoteAgent` prefers A2A when the peer card advertises JSON-RPC and falls back to the peer's `/v1/chat/completions` endpoint; the fallback extracts the first response choice (`pydantic-ai-server/pais/serverutils.py:175-230`). This makes deployed multi-agent behavior invocable without eval-specific transport.

The current surface can assert that delegation occurred through mock tool calls, memory events, or spans. It cannot declaratively assert delegation topology, ordering, argument quality, handoff context, per-agent contribution, prohibited hops, or end-to-end trajectory invariants.

## Observability and trace-based evaluation potential

### Runtime OTel wiring

Telemetry is opt-in and initializes only when `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` are present and the SDK is not disabled (`pydantic-ai-server/pais/telemetry.py:130-169`). Initialization installs W3C trace-context and baggage propagation, OTLP/gRPC exporters for traces, metrics, and logs, and a root logging handler (`pydantic-ai-server/pais/telemetry.py:174-210`). Exporter TLS, headers, and related behavior remain configurable through standard OTel environment variables.

`create_agent_server()` initializes the SDK and globally instruments Pydantic AI with a configured instrumentation version (`pydantic-ai-server/pais/server.py:740-768`). Pydantic AI therefore supplies model/agent/tool spans and generative-AI attributes, while KAOS adds server, task, autonomous, and delegation spans.

The `server-run` span carries attributes assembled per session and stays active for the complete response generation path (`pydantic-ai-server/pais/server.py:570-620`). KAOS delegation produces `delegate.<agent>` with `agent.delegation.target`, error status, and exception recording (`pydantic-ai-server/pais/tools.py:120-157`).

A2A adds `kaos.task.submit`, `kaos.task.submit_autonomous`, `kaos.task.cancel`, task execution spans, `kaos.autonomous.run`, and `kaos.autonomous.iteration`; attributes include session/task identifiers, autonomous mode, iteration number, configured budgets, and final state (`pydantic-ai-server/pais/a2a.py:315-420`, `pydantic-ai-server/pais/a2a.py:560-574`, `pydantic-ai-server/pais/a2a.py:647-650`). Metrics include `kaos.tasks`, `kaos.task.duration`, `kaos.delegations`, and `kaos.delegation.duration` (`pydantic-ai-server/pais/a2a.py:195-217`, `pydantic-ai-server/pais/telemetry.py:218-232`).

The memory client also emits `kaos.memory.recall` and `kaos.memory.write` spans with scope level, degraded state, fact count, and turn count (`kaos-memory/kaos_memory/client.py:105-171`). These are evaluation-adjacent because memory correctness and degradation can affect an agent run.

### Collector destinations and control-plane wiring

The Agent CRD exposes `config.telemetry.enabled` and an OTLP gRPC endpoint, while advanced settings pass through standard environment variables (`operator/api/v1alpha1/agent_types.go:123-136`). The Agent controller translates telemetry configuration into runtime environment variables (`operator/controllers/agent_controller.go:939-944`); ModelAPI and MCPServer controllers use the same shared environment-building pattern, and LiteLLM config enables OTel success/failure callbacks (`operator/controllers/modelapi_controller.go:522-544`, `operator/controllers/modelapi_controller.go:736-778`).

The Helm chart provides global `telemetry.enabled` and `telemetry.endpoint` defaults but does not itself embed a collector (`operator/chart/values.yaml:253-260`). `kaos system install --monitoring-enabled` installs either Jaeger or SigNoz and passes its in-cluster OTLP endpoint into Helm (`kaos-cli/kaos_cli/system/__init__.py:141-150`, `kaos-cli/kaos_cli/install/__init__.py:387-391`). Jaeger resolves to `http://jaeger.<namespace>:4317`; SigNoz resolves to `http://signoz-otel-collector.<namespace>:4317` (`kaos-cli/kaos_cli/install/observability.py:288-292`). A user may instead configure any external OTLP collector.

### Feasibility and limits of online evaluation

Trace-based evaluation is technically feasible because a collector can observe the full distributed trace across server, model, tool, delegation, A2A, and memory operations, with W3C propagation joining hops. A trace consumer could calculate latency, failures, tool/delegation counts, budget exhaustion, and some trajectory rules without changing invocation.

The current trace schema is insufficient as a complete evaluation contract. There is no evaluation ID, dataset/case ID, candidate version, expected answer, rubric, ground truth, score, evaluator version, or pass/fail attribute. Prompt/output capture follows upstream Pydantic AI instrumentation settings rather than a KAOS-owned stable schema. Sampling, retention, sensitive-content handling, trace finality, and cross-trace aggregation are collector concerns, and KAOS has no consumer that converts traces into durable evaluation results.

## Invocation and exposure paths

### CLI invocation

`kaos agent invoke` accepts one agent name, one message, optional namespace/local port, streaming, and optional user identity (`kaos-cli/kaos_cli/agent/__init__.py:318-351`). It is an interactive single-invocation command, not a batch or file-driven runner.

Without gateway routing, the command locates `service/agent-<name>`, starts a `kubectl port-forward`, and posts one OpenAI-compatible chat request to localhost (`kaos-cli/kaos_cli/agent/invoke.py:153-229`). Non-streaming sends the same single user message and prints response content (`kaos-cli/kaos_cli/agent/invoke.py:251-270`). There is no structured JSON result option intended for aggregation, concurrency, repetitions, dataset input, output file, or threshold-based exit status.

When a user is specified or the CLI is configured to route through the gateway, invocation posts to `/<namespace>/agent/<name>/v1/chat/completions` and optionally attaches the cached bearer token (`kaos-cli/kaos_cli/agent/invoke.py:73-92`, `kaos-cli/kaos_cli/agent/invoke.py:164-171`). The extra output concerns authorization verdicts rather than evaluation results.

The CLI also exposes `kaos agent a2a` commands, so scripts can submit and inspect task lifecycle through JSON-RPC, but there is no repository-provided batch orchestrator. Shell/Python loops over `invoke` or direct HTTP are possible external workarounds, not a KAOS evaluation surface.

### In-cluster and external reachability

The Agent controller creates a ClusterIP Service named `agent-<name>` on port 8000 when exposure is enabled (`operator/controllers/agent_controller.go:379-429`, `operator/controllers/agent_controller.go:1127-1158`). In-cluster clients can address the Service directly when security policy permits.

With Gateway API enabled, the controller creates an HTTPRoute for the Agent and uses the path convention `/<namespace>/agent/<name>`; internal ModelAPI, MCP, peer-agent, and memory endpoints can also be rewritten through the gateway so identity and authorization policies apply (`operator/controllers/agent_controller.go:304-306`, `operator/controllers/agent_controller.go:509-556`). External access therefore depends on the Envoy Gateway address, LoadBalancer/MetalLB or port-forwarding, and any configured authentication.

The E2E harness uses the same convention through `GATEWAY_URL`, constructing resource URLs as `/<namespace>/<resource-type>/<name>` (`operator/tests/e2e/conftest.py:20-63`). This is directly reusable for black-box eval execution against KIND or another cluster.

## Existing test harnesses

### Runtime unit and integration tests

The Pydantic AI server test suite uses pytest/pytest-asyncio, injected `FunctionModel`/`TestModel` behavior, FastAPI clients, local/null memory, `RemoteAgent` fakes, and the shared `make_test_server()` factory. Tests cover chat, streaming, agentic loops, tool limits, A2A JSON-RPC and task storage, autonomous budgets, string-mode parsing, telemetry, memory, and identity (`pydantic-ai-server/tests/helpers.py:1-73`; representative files `pydantic-ai-server/tests/test_agent_server.py`, `pydantic-ai-server/tests/test_agentic_loop.py`, `pydantic-ai-server/tests/test_a2a_jsonrpc.py`, and `pydantic-ai-server/tests/test_autonomous.py`).

These patterns prove that runs can be isolated and asserted quickly in process. Their assertions are bespoke Python assertions per scenario; there is no reusable case schema or scorer registry.

### KIND end-to-end tests

`operator/tests/e2e` is a pytest harness against a real Kubernetes cluster and Gateway API. Shared helpers apply custom-resource dictionaries, wait for deployments/CR readiness, construct gateway URLs, poll health, and manage installation and namespace lifecycle (`operator/tests/e2e/conftest.py:20-131`, `operator/tests/e2e/conftest.py:221-260`).

Individual suites stand up ModelAPI, Agent, MCPServer, and MemoryStore resources and assert basic chat, tool calling, multi-agent delegation, A2A lifecycle, autonomous budgets, authorization, and persistence. Determinism is commonly introduced by placing `DEBUG_MOCK_RESPONSES` in Agent container environment, for example in `operator/tests/e2e/test_agentic_loop_e2e.py:28-49`, `operator/tests/e2e/test_multi_agent_e2e.py:33-53`, and `operator/tests/e2e/test_autonomous_e2e.py:21-55`.

This is a useful cluster-backed executor template: unique namespaces isolate runs, readiness helpers gate execution, gateway HTTP is the black-box boundary, and Kubernetes cleanup contains side effects. It is too slow and test-specific to serve directly as a general evaluation engine, and it provides no aggregation or result persistence.

### Executable documentation

The examples harness executes selected `docs/examples/*.md` files as Jupytext notebooks and treats process success as the assertion; test logic intentionally lives in Markdown rather than duplicated Python (`operator/tests/e2e/test_examples_e2e.py:1-43`). Examples include custom MCP, KAOS Monkey, multi-agent telemetry, memory, authorization, custom agent, and autonomous behavior (`operator/tests/e2e/test_examples_e2e.py:45-184`).

Examples use deterministic mock responses where needed; `docs/examples/memory.md:65-113` explicitly uses `DEBUG_MOCK_RESPONSES`, and `docs/examples/custom-agent.md:175` injects it through deployment CLI arguments. This pattern resembles executable benchmark narratives but lacks machine-readable cases and scores.

### kaos-memory tests

`kaos-memory/tests` separates fakes and fixtures from focused contract, client, model, storage, background work, health, telemetry, and service-E2E tests. The service E2E tests compose real application layers with faked external dependencies, while unit tests assert degradation and strict/soft failure behavior. This supports the structural lesson that a future eval service can test contract/client/service independently rather than requiring Kubernetes for all correctness checks.

## Reusable control-plane patterns

### MemoryStore CRD and central-service reconciliation

`MemoryStore` is the closest precedent for introducing a first-class KAOS capability backed by a shared service. Its CRD owns model references, storage, extraction/summarization, failure mode, telemetry, container overrides, replicas, and status (`operator/api/v1alpha1/memorystore_types.go:83-170`). The reconciler resolves dependencies before workload creation, creates or updates a Deployment and ClusterIP Service, optionally creates local PVC storage, adds a PDB for multi-replica external mode, creates gateway/security resources, and publishes readiness and endpoint status (`operator/controllers/memorystore_controller.go:48-141`, `operator/controllers/memorystore_controller.go:198-250`, `operator/controllers/memorystore_controller.go:437-523`, `operator/controllers/memorystore_controller.go:525-606`).

An evaluation service could reuse this lifecycle for a central API/result service. Evaluation execution itself differs: finite workloads map more naturally to Jobs than the always-on Deployment used by MemoryStore.

### ModelAPI references

The Agent spec declares the pair `{modelAPI, model}`: a same-namespace ModelAPI resource name plus a model identifier that must be supported (`operator/api/v1alpha1/agent_types.go:239-250`). The Agent reconciler fetches the ModelAPI, gates on readiness, and validates model support before constructing the runtime Deployment (`operator/controllers/agent_controller.go:117-175`).

MemoryStore generalizes the same pair into role-specific summarization and embedding references (`operator/api/v1alpha1/memorystore_types.go:83-101`). Its controller resolves both same-namespace resources, gates on readiness, and injects the resolved endpoint and model names (`operator/controllers/memorystore_controller.go:144-184`). An LLM-as-judge should reuse this pair rather than embedding provider URLs or credentials in an eval definition.

### Per-agent configuration binding

The Agent CRD nests behavior under `spec.config`, including reasoning limits, tool-call mode, memory, telemetry, autonomous execution, and task budgets (`operator/api/v1alpha1/agent_types.go:140-185`). `config.memory` demonstrates an optional per-agent binding with defaults, validation, a named central resource, scope, tools, client parameters, and failure mode (`operator/api/v1alpha1/agent_types.go:72-119`).

This is a precedent for small runtime opt-ins such as online evaluation sampling or trace annotations. Offline evaluation definitions should remain separate resources so datasets, repetitions, judges, and results do not inflate every Agent spec.

### Jobs

The operator does not create Kubernetes `Job` resources today. No controller imports or owns `batch/v1.Job`, and repository searches for controller-side Job construction are empty. Existing reconcilers create long-running Deployments, Services, routes/policies, PVCs, and PDBs. A finite eval-run Job would therefore be a new controller-owned resource pattern, not a reuse of existing Job code.

### Helm images and system installation

The chart centralizes component images under `defaultImages`, including agent runtime, MCP runtimes, LiteLLM, Ollama, and memory service (`operator/chart/values.yaml:31-42`). Controllers receive these defaults and allow resource-level container image overrides. A future eval runner/service image fits this existing selection and release-version mechanism.

`kaos system install` exposes optional platform integrations for monitoring, Gateway API, MetalLB, authentication, token exchange, and development pgvector memory, plus repeatable `--set` as an escape hatch (`kaos-cli/kaos_cli/system/__init__.py:129-205`). Monitoring installation also wires the chosen collector endpoint into global telemetry. An eval service integration flag could follow this pattern if the capability is optional; CRDs and controller support should not require installing a bundled results backend unless that is an explicit product choice.

## kaos-memory as a structural template

`kaos-memory` is one Python distribution and service image with a framework-independent contract, async HTTP client, service application, configuration, storage adapters, and telemetry. `contract.py` owns Pydantic request/response and scope types; `client.py` owns transport and failure semantics; `app.py` composes the FastAPI edge and domain service; `stores.py` isolates outbound persistence/model dependencies; and `telemetry.py` owns service instrumentation (`kaos-memory/kaos_memory/contract.py:1-180`, `kaos-memory/kaos_memory/client.py:1-180`, `kaos-memory/kaos_memory/app.py:1-140`).

The package declares a lightweight base plus optional dependency groups for service and Pydantic AI integration, and an executable service entry point (`kaos-memory/pyproject.toml:1-61`). This lets library consumers depend on contracts/client without importing the complete service stack.

An eval package could mirror that shape: contract types for datasets, cases, evaluators, runs, and results; a client; a runner library; an optional FastAPI service; storage adapters; and optional Pydantic AI/judge integrations. The useful template is separation of contract, transport, domain orchestration, and infrastructure—not memory-specific storage behavior.

## Precise gap list

1. **No dataset or case representation.** KAOS can accept a single prompt through chat or A2A, but no type groups N inputs with stable case IDs, optional conversation history, variables, fixtures, ground truth, reference outputs, tags, splits, or metadata. The nearest extension points are the OpenAI/A2A input schemas for execution and `kaos_memory.contract` as a model for a framework-independent Pydantic contract.

2. **No evaluator abstraction.** Assertions live directly in pytest functions. There is no interface for deterministic exact/contains/regex/JSON/schema checks, semantic similarity, tool-call rules, safety/policy checks, custom code, or model-based grading. The nearest extension is the injected-model and test-helper pattern in `pydantic-ai-server/tests/helpers.py`, but scoring must be separated from agent execution.

3. **No N-case run orchestrator.** `kaos agent invoke` sends one message and A2A submits one task. Nothing expands a dataset into cases, controls concurrency and repetitions, seeds or isolates sessions, applies timeouts/retries, handles partial failure, or aggregates completion. The nearest extension is A2A `TaskManager` for lifecycle semantics or a new finite Kubernetes Job runner for cluster execution.

4. **No LLM-as-judge wiring.** Model resolution exists for agents and MemoryStore role models, but no evaluator can resolve `{modelAPI, model}`, build a rubric prompt, demand structured judge output, retry invalid judgments, or record judge provenance and usage. The nearest reusable surface is MemoryStore's role-specific model-reference resolution.

5. **No evaluation result contract or persistence.** A2A tasks are in-memory and return one output; memory storage holds conversational facts/events; OTLP backends hold operational telemetry. None stores case inputs, candidate outputs, individual evaluator scores, explanations, aggregate metrics, errors, timestamps, versions, or artifacts as an eval result. A new result contract and explicit storage lifecycle are required; neither memory nor traces should be overloaded as the canonical result database.

6. **No reporting or comparison.** There is no terminal/JSON/HTML report, pass-rate summary, slice/tag breakdown, baseline comparison, statistical uncertainty, flaky-case analysis, or link from an Agent/version to its runs. The closest current surfaces are CLI printing and observability UIs, neither of which understands evaluation semantics.

7. **No declarative evaluation CRD.** Existing CRDs declare Agents, ModelAPIs, MCPServers, and MemoryStores only. There is no resource that selects an agent, dataset, evaluators, judge models, repetitions, concurrency, budgets, thresholds, result destination, or cleanup policy, and no status with run progress/conditions/summary.

8. **No finite eval workload controller.** Controllers reconcile services as Deployments and do not create Jobs. There is no mechanism to materialize an evaluation declaration into a versioned runner pod, watch Job completion, retry infrastructure failures, capture artifacts, update status, or garbage-collect runs.

9. **No scheduled or regression execution.** Autonomous mode is a self-looping agent goal, not a benchmark scheduler. KAOS has no cron/schedule field, repository/Agent-change trigger, baseline policy, quality gate, alert, or retention rule. The nearest Kubernetes primitive would be CronJob or controller-created Jobs, both absent from current operator behavior.

10. **No online trace scoring pipeline.** OTel exports enough data for operational rules, but KAOS defines no trace consumer, stable evaluation semantic conventions, sampling policy, completion detector, evaluator attachment, or score export/storage. Online evaluation would extend telemetry with eval/run/case identity and introduce an asynchronous scoring service rather than placing judge calls on the agent request path.

11. **No stable trajectory contract.** `_run_agent` collapses execution to text plus tool-call count; streaming emits transient progress; A2A events describe task state; memory events are persistence-oriented; OTel spans depend partly on upstream conventions. No API returns a canonical ordered sequence of prompts, model responses, tool arguments/results, delegation hops, token usage, timing, and errors suitable for evaluators.

12. **No multi-agent trajectory assertions.** Delegation is observable through tools, spans, and some memory events, but there is no way to declare required/forbidden agents, hop counts, ordering, handoff fields, per-agent rubrics, convergence rules, or final-answer attribution. This would extend `DelegationToolset`/A2A observation rather than change delegation execution itself.

13. **No environment and fixture model.** E2E tests hand-create namespaces and resources, while runtime tests inject Python fakes. An eval case cannot declare MCP fixtures, external-service mocks, Kubernetes seed state, secrets, memory preloads, teardown, or side-effect assertions. The nearest surface is the E2E fixture/helper layer, which must be made declarative and safely scoped before general use.

14. **No isolation and reset semantics.** Mock responses reset per external request, but memory, remote systems, and Kubernetes side effects may persist. There is no declared policy for fresh session, fresh agent, fresh namespace, memory snapshot/reset, or shared-state cases, so repeatability and parallel execution cannot be guaranteed.

15. **No reproducibility/provenance envelope.** Current runs do not canonically record Agent generation/spec hash, container image digest, model endpoint and model name, evaluator/judge versions, dataset version, mock seed, tool/MCP versions, runtime limits, or telemetry schema version. Kubernetes status and spans expose fragments, but not one immutable manifest attached to results.

16. **No cost, token, or latency budgets as evaluation criteria.** Autonomous tasks enforce iterations/runtime/tool calls operationally, and Pydantic AI telemetry may emit usage, but an eval cannot declare per-case or aggregate thresholds, normalize model pricing, or fail a run based on efficiency. Execution budgets and scoring thresholds need distinct semantics.

17. **No quality threshold or gate semantics.** Pytest exits on assertions, but a KAOS eval has no definition of required evaluators, weighted scores, minimum pass rate, critical-case policy, infrastructure-error treatment, or final run conclusion. This is necessary for CI/regression use and should be part of the eval contract, not inferred by a CLI.

18. **No evaluation CLI/API.** There is no `kaos eval` surface to create, run, watch, cancel, list, inspect, compare, or export evaluations. `kaos agent invoke`, A2A commands, `kubectl`, and observability UIs are lower-level building blocks only.

19. **No local-to-cluster parity.** In-process tests and KIND tests use different bespoke orchestration. There is no runner contract that can target a local `AgentServer`, an existing HTTP endpoint, or a declared in-cluster Agent while producing the same result schema and evaluator behavior.

20. **No security and governance model for eval data.** Gateway authorization controls invocation and OTel configuration controls export, but datasets, reference answers, captured prompts/outputs, judge inputs, tool results, and reports have no access policy, redaction, tenant/namespace boundary, retention, or secret-handling rules. Trace capture alone is not an acceptable substitute because prompt/output data may be sensitive.

## Requirements the gaps imply

A minimum offline capability needs a versioned, framework-independent contract for dataset, case, evaluator, run specification, case result, evaluator result, aggregate summary, and provenance. It must support deterministic evaluators first, with LLM judges as an optional evaluator using the existing `{modelAPI, model}` reference pattern.

Execution needs one runner contract with adapters for in-process `AgentServer`, OpenAI-compatible HTTP, and A2A asynchronous tasks. Every adapter must emit the same canonical trajectory and usage envelope, isolate case sessions, apply explicit timeouts/budgets, and distinguish candidate failure, evaluator failure, and infrastructure failure.

The control plane needs a namespaced declarative resource and reconciler for finite runs, most naturally backed by Jobs, with dependency readiness, image defaults, conditions/progress, cancellation, cleanup, and result-location status. A separate long-running service is justified only for shared result/query APIs or online scoring, following the MemoryStore Deployment/Service pattern.

Results must be durable outside process-local A2A storage and outside the telemetry backend. The storage contract must retain per-case evidence, scores and explanations, aggregates, artifacts, and immutable provenance, while the CLI/API provides run/watch/list/show/compare/export and machine-readable exit semantics for CI.

Online evaluation should build on OTLP rather than a second instrumentation stack, but it needs KAOS-owned semantic conventions for run/case/agent identity, a trace-completion and sampling policy, asynchronous evaluator workers, and linkage from scores back to traces. It must not add judge latency to the live agent path by default.

Multi-agent and stateful evaluation require first-class trajectory events, fixture/environment declarations, reset policies, side-effect assertions, and authorization/redaction/retention controls. These are requirements for reproducibility and safe regression use, not optional reporting enhancements.
