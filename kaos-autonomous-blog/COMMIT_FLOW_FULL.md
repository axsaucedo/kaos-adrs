# Implementation Flow: From A2A Tasks to Autonomous Workloads

This document turns the v0.4.0 commits into a coherent engineering narrative. It is not intended to be pasted directly into the article; it is the evidence base.

## Phase 1: Add a Task Contract Around Agents

The first A2A work created a task lifecycle around the existing agent runtime.

Key changes:

- Task states: submitted, working, completed, failed, canceled, input-required.
- Task messages and history.
- JSON-RPC envelope and method dispatch.
- Agent card updates for protocol discovery.
- Local and null task managers.

Why this matters:

The runtime already knew how to answer a chat request. The missing abstraction was a durable-enough "unit of work" that could be submitted, inspected, and controlled.

Article insight:

> Autonomous agents need APIs that look less like chat completions and more like job control.

## Phase 2: Add A2A Protocol Surface

The JSON-RPC endpoint made the task model accessible:

- `SendMessage`
- `GetTask`
- `CancelTask`
- later `ListTasks`
- legacy aliases for earlier `tasks/send`, `tasks/get`, `tasks/cancel`

Agent cards exposed capabilities and supported protocols. Remote agents could prefer A2A and fall back to chat completions.

Why this matters:

Agent-to-agent systems need discovery and a shared protocol. Without this, every sub-agent call is just another bespoke HTTP request.

Article insight:

> Interoperability is a lifecycle problem as much as a message-format problem: agents need to discover each other, delegate work, and understand task state.

## Phase 3: Add Autonomous Looping

The autonomous work extended the task model:

- autonomous task submission,
- background execution,
- budget checks,
- iteration messages,
- tool-call counting,
- output capture,
- completion detection,
- cancellation and failure handling.

The runtime exposed a reusable primitive:

```text
_run_agent(message, session_id) -> (response_text, tool_call_count)
```

That is an important architectural split. The server owns "run the agent once." The task manager owns "decide whether and when to run it again."

Article insight:

> A production autonomous loop should be built around a single-iteration primitive, not tangled directly into HTTP request handling.

## Phase 4: Add Kubernetes Startup Autonomy

Startup-activated autonomous mode let a Kubernetes Agent resource define a goal. When the pod starts, the agent begins looping.

This turned autonomy into desired state:

```yaml
spec:
  config:
    autonomous:
      goal: "Monitor the Kubernetes cluster health."
      intervalSeconds: 60
      maxIterRuntimeSeconds: 120
```

Why this matters:

For monitoring and maintenance workloads, there may be no user request. The autonomous behavior is part of the workload itself.

Article insight:

> Kubernetes CRDs let autonomy become a deployable contract: this agent exists to pursue this goal with these operational limits.

## Phase 5: Split Continuous Mode from Async Task Mode

The architecture was refined after initial implementation:

- Continuous mode: CRD-started, loops indefinitely, per-iteration limits.
- Async task mode: A2A-triggered, budget-limited, completes when no tool calls are made.

This was the conceptual inflection point of the release.

Why this matters:

"Autonomous" was doing too much work as a word. The system needed two separate operational concepts:

1. A daemon-like agent that keeps watching or acting.
2. A background task that should eventually finish.

Article insight:

> Autonomy describes how work proceeds; async describes how callers interact with that work. They should not be confused.

## Phase 6: Simplify Events and Clarify Memory

TaskEvent was simplified to state transitions:

- `task.submitted`
- `task.working`
- `task.completed`
- `task.failed`
- `task.canceled`
- `autonomous.budget.exhausted`

Iteration-level detail moved out of TaskEvent and stayed in memory/conversation events.

Why this matters:

Task APIs should not become verbose execution logs. They need to be stable and easy to inspect. Detailed execution history belongs in memory and observability.

Article insight:

> Task state and agent memory answer different operational questions. Keeping them separate makes debugging easier.

## Phase 7: Add Human Debugging Surfaces

The UI added:

- A2A agent card display.
- SendMessage form.
- async task toggle.
- Get/cancel task panel.
- auto-polling.
- task history sidebar.
- memory conversation view.

The CLI added:

- `kaos agent a2a send`
- `kaos agent a2a get`
- `kaos agent a2a cancel`
- `--async` for background work.

Why this matters:

Autonomy without inspection is not production-ready. Users and operators need to see what is running and intervene.

Article insight:

> The control plane for autonomous agents is not just code. It is also the UI, CLI, and observability path that lets a human understand and stop the work.

## Phase 8: Add a Practical Example

The release includes a cluster-monitor sample:

- read-only Kubernetes RBAC,
- Kubernetes MCP tool,
- Python-string report-generation tool,
- hosted model API,
- autonomous Agent with a cluster health goal.

Why this matters:

Monitoring is a natural autonomous-agent use case:

- there is an ongoing goal,
- the environment changes over time,
- the agent needs tools,
- the agent should be constrained by permissions,
- output accumulates in memory.

Article insight:

> The most persuasive autonomous-agent examples are operational: monitor, inspect, summarize, and alert under explicit permissions.

## Final Narrative

The implementation evolved from "agent as chat endpoint" toward "agent as controllable workload":

```text
chat endpoint
  -> task state
  -> JSON-RPC/A2A protocol
  -> background execution
  -> autonomous loop
  -> continuous vs async separation
  -> budgets and cancellation
  -> UI/CLI/debugging
  -> Kubernetes-native examples
```

That is the shape the article should explain.

