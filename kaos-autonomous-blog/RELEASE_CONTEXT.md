# KAOS v0.4.0 Autonomous Agents Release Context

## Source

- Release: <https://github.com/axsaucedo/kaos/releases/tag/v0.4.0>
- Compare: <https://github.com/axsaucedo/kaos/compare/v0.3.1...v0.4.0>
- Main case-study repo: <https://github.com/axsaucedo/kaos>

## Release Summary

KAOS v0.4.0 was the A2A/autonomous-agent milestone. The release is useful for the article because it contains a concrete implementation of the broader production-autonomy problem:

- Give agents a task lifecycle instead of only a chat endpoint.
- Let agents run without a synchronous user request waiting for the answer.
- Separate always-on autonomous loops from bounded async work.
- Add budgets, cancellation, state inspection, memory, and debugging surfaces.
- Expose these controls through Kubernetes CRDs, CLI, and UI.

The article should not present this as "what KAOS shipped." The reader-facing framing is: this is what starts to appear when autonomous agents become operational workloads.

## Release Highlights

The published release notes describe v0.4.0 as delivering:

- A2A TaskManager/TaskStore support with JSON-RPC methods, OpenTelemetry task observability, and async task execution semantics.
- Autonomous agent configuration, budget enforcement, startup execution, and E2E coverage across the operator and Python runtime.
- FastMCP 3.0 and `fastmcp-codemode` runtime support.
- UI screens for A2A debugging, autonomous status/configuration, task history, and memory conversation inspection.
- CLI commands and examples around `kaos agent a2a` and autonomous deployments.

## PR Context

| PR | Title | Article-Relevant Insight |
| --- | --- | --- |
| [#104](https://github.com/axsaucedo/kaos/pull/104) | A2A TaskStore & JSON-RPC endpoint | A production agent needs a task contract: submit, get, cancel, state transitions, history, artifacts, and protocol-level errors. |
| [#108](https://github.com/axsaucedo/kaos/pull/108) | FastMCP 3.0 | Tool runtime upgrades matter because autonomy is only useful if the agent can safely and reliably act through tools. |
| [#109](https://github.com/axsaucedo/kaos/pull/109) | fastmcp-codemode runtime | Code/tool execution becomes a substrate for autonomous agents, not just a demo feature. |
| [#110](https://github.com/axsaucedo/kaos/pull/110) | Autonomous self-looping agent execution | Adds the core self-loop: goal, iteration, tool-call counting, budgets, startup mode, and A2A-triggered mode. |
| [#112](https://github.com/axsaucedo/kaos/pull/112) | Split continuous and async task modes | The key conceptual refinement: always-on agents and bounded background tasks are different workload types. |
| [#113](https://github.com/axsaucedo/kaos/pull/113) | Simplify TaskEvent to state transitions only | Separates task contract state from execution memory; a useful design lesson for readers. |
| [#114](https://github.com/axsaucedo/kaos/pull/114) | UI autonomous and A2A debug support | Debuggability is part of autonomy: agent card, SendMessage, task polling/cancel, history, and memory views. |
| [#115](https://github.com/axsaucedo/kaos/pull/115) | Replace `a2a --mode` with `--async` | Terminology matters: "autonomous" describes a workload behavior, while "async" describes the task execution contract. |

## The Main Case-Study Distinction

KAOS v0.4.0 eventually distinguishes two patterns:

### Continuous autonomous mode

- Configured in the Agent CRD through `spec.config.autonomous.goal`.
- Starts when the pod starts.
- Loops indefinitely until the pod is stopped, restarted, deleted, or canceled.
- Uses per-iteration controls such as `intervalSeconds` and `maxIterRuntimeSeconds`.
- Best fit: monitoring, maintenance, daemon-style work, recurring checks.

### A2A async task mode

- Triggered through A2A `SendMessage`.
- Returns a task ID for polling rather than requiring a synchronous response.
- Uses overall budgets such as `maxIterations`, `maxRuntimeSeconds`, and `maxToolCalls`.
- Completes when the agent can answer without making more tool calls, when a budget is exhausted, or when the task is canceled/fails.
- Best fit: long-running user-initiated work, research, analysis, background tasks.

This distinction is one of the strongest article points: production autonomy is not a single mode. Teams need to decide whether they are building an always-on worker, a bounded background task, or a synchronous chat-like interaction.

## Source Files to Use as Evidence

| Area | Files |
| --- | --- |
| A2A task model and loop | `pydantic-ai-server/pais/a2a.py` |
| Server startup and route wiring | `pydantic-ai-server/pais/server.py` |
| A2A agent card and delegation | `pydantic-ai-server/pais/serverutils.py` |
| CRD API | `operator/api/v1alpha1/agent_types.go` |
| Operator env plumbing | `operator/controllers/agent_controller.go` |
| CLI workflows | `kaos-cli/kaos_cli/agent/a2a.py`, `kaos-cli/kaos_cli/agent/deploy.py` |
| Autonomous docs | `docs/python-framework/autonomous.md` |
| A2A docs | `docs/python-framework/a2a-tasks.md` |
| Executable example | `docs/examples/autonomous-agent.md`, `examples/autonomous-agent.ipynb` |
| Production sample | `operator/config/samples/6-autonomous-monitor.yaml` |
| UI debugging | `kaos-ui/src/components/agent/*`, `kaos-ui/src/lib/k8s/a2a.ts`, `kaos-ui/src/types/a2a.ts` |

## Article-Framing Notes

Use the release as evidence for broader lessons:

1. A simple agentic loop is not enough once the loop can continue without a user waiting.
2. Agents need workload contracts: goal, status, history, output, artifacts, state, and cancellation.
3. Budgets are a safety primitive, not just a cost-control feature.
4. Memory and task state answer different questions:
   - Task state: "What is this unit of work doing?"
   - Memory: "What happened during execution?"
5. Kubernetes is useful because autonomous agents look like workloads:
   - CRDs define desired autonomous behavior.
   - Controllers turn it into pods/services/config.
   - RBAC constrains what tools can do.
   - Platform observability and lifecycle semantics already exist.
6. The practical reader takeaway should be how to design these pieces, whether they use KAOS or not.

