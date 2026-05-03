# Comprehensive Outline: Autonomous Agents as Operational Workloads

## Working Titles

1. **Autonomous Agents Are Workloads Now**
2. **The Engineering Behind Autonomous Agents: Loops, Budgets, Tasks, and Kubernetes**
3. **From Agentic Loops to Autonomous Workloads**
4. **How to Make Autonomous Agents Operable**
5. **Autonomous Agents Need More Than a Loop**

Recommended title:

> **Autonomous Agents Need More Than a Loop**

Subtitle:

> A practical guide to agent loops, task state, budgets, cancellation, and Kubernetes-native deployment, using KAOS v0.4.0 as the worked example.

## Target Length

4,500-6,000 words.

## Core Thesis

Autonomous agents are becoming long-running operational workloads, not just smarter chat sessions. Once agents can loop, call tools, remember context, and act without a user waiting on the request, the engineering problem shifts from prompt design to lifecycle control: goals, budgets, cancellation, memory, task state, tool permissions, observability, and deployment substrate.

## Section 1: Hook - The Moment an Agent Stops Being a Request

Approx. 400 words.

Opening scenario:

- You have an agent that works when a user asks a question.
- It calls tools and returns a good answer.
- Then someone asks it to keep watching a system, produce periodic reports, and act when something changes.
- That is no longer just a chat endpoint. It is a workload.

Key line:

> Calling the model again is easy. Operating the loop is the hard part.

Purpose:

- Establish reader-interest problem.
- Make clear this is not primarily a KAOS article.
- Preview the practical arc: loop -> autonomy -> production controls -> Kubernetes -> KAOS example -> build-it-yourself basics.

## Section 2: The Simple Agentic Loop

Approx. 600 words.

Explain a normal tool-calling loop:

```python
async def run_agent(messages, tools, max_steps=5):
    for step in range(max_steps):
        response = await model.chat(messages, tools=tools)

        if response.tool_calls:
            for call in response.tool_calls:
                result = await tools[call.name](**call.arguments)
                messages.append({"role": "tool", "content": result})
            continue

        return response.text
```

Explain:

- model decides,
- tool executes,
- result returns to context,
- loop continues,
- final text ends the loop.

Reader takeaway:

The agentic loop is the baseline; autonomy is what happens when that loop is no longer tied to one synchronous user request.

Visual:

Basic loop diagram.

## Section 3: What Changes When the Loop Becomes Autonomous

Approx. 700 words.

Contrast table:

| Request/response agent | Autonomous agent |
| --- | --- |
| User waits | Work continues in background |
| Loop ends with answer | Loop may continue indefinitely |
| Request context is enough | Needs task state and memory |
| Errors are request failures | Errors become operational incidents |
| Tool calls are per request | Tool calls may create ongoing side effects |

Introduce production controls:

- goal,
- trigger,
- task identity,
- state transitions,
- budgets,
- cancellation,
- memory,
- permissions,
- observability.

Use line:

> Autonomy is not the loop. Autonomy is the control plane around the loop.

## Section 4: The Industry Is Converging on the Same Primitives

Approx. 600 words.

Mention frameworks briefly:

- OpenClaw: always-on personal assistant with heartbeat, integrations, local memory.
- LangGraph: long-running, stateful workflows with durable execution and human-in-the-loop.
- CrewAI: role-based crews, flows, state, guardrails, observability.
- OpenAI Agents SDK: managed loop, handoffs, guardrails, sessions, tracing.
- Google ADK: production agents, context management, graph workflows, cloud/GKE deployment.
- LlamaIndex/Haystack: agentic workflows over knowledge/RAG pipelines.
- Semantic Kernel/Microsoft: plugin/API integration and enterprise middleware.

Do not turn this into a comparison table in the article body. Use it to show convergence:

- state,
- tools,
- handoffs,
- memory,
- human review,
- tracing/evaluation,
- deployment.

Key point:

> Frameworks differ in abstraction, but they are all moving beyond "call a model" toward "manage a unit of agent work."

## Section 5: Why Kubernetes Enters the Conversation

Approx. 700 words.

Argument:

Autonomous agents need workload primitives:

- identity,
- lifecycle,
- networking,
- secrets,
- permissions,
- storage,
- scaling,
- observability,
- isolation.

Kubernetes is not magic for agents; it is a mature substrate for workloads.

Reference Agent Sandbox:

- AI shifted from short-lived calls to coordinated agents that run constantly.
- Agents may need persistent identity, secure scratchpads, code execution isolation, suspension/resumption, stable networking.

Introduce CRDs:

> A CRD can describe autonomy as desired state: this agent, using these tools, should pursue this goal with these budgets.

Visual:

Kubernetes autonomous-agent workload architecture.

## Section 6: A Practical Example with KAOS v0.4.0

Approx. 1,000 words.

Transition:

> To make this concrete, let's use KAOS v0.4.0 as the worked example. The APIs are KAOS-specific, but the patterns are not.

Explain KAOS briefly:

- Kubernetes-native AI agent orchestration framework.
- Agents, MCPServer tools, ModelAPI.
- A2A JSON-RPC for agent task protocol.
- UI/CLI for debugging.

Example use case:

Autonomous Kubernetes cluster monitor:

- read-only RBAC,
- Kubernetes MCP tool,
- report-generation MCP tool,
- model API,
- Agent CRD with autonomous goal.

YAML excerpt:

```yaml
config:
  autonomous:
    goal: "Monitor the Kubernetes cluster health. List pods, check their status, and generate a health report."
    intervalSeconds: 60
    maxIterRuntimeSeconds: 120
  taskConfig:
    maxIterations: 5
    maxRuntimeSeconds: 300
    maxToolCalls: 20
```

Explain:

- continuous mode starts on pod boot,
- taskConfig controls A2A async tasks,
- RBAC controls tool access,
- memory records what happened,
- task events record state.

Visual:

KAOS autonomous monitor architecture.

## Section 7: Continuous Mode vs Async Task Mode

Approx. 900 words.

This is the central technical distinction.

### Continuous mode

- configured in CRD,
- starts on pod startup,
- loops indefinitely,
- per-iteration timeout and interval,
- monitoring/daemon fit.

### Async task mode

- triggered by A2A `SendMessage`,
- returns a task ID,
- bounded by budgets,
- polling/cancel through `GetTask`/`CancelTask`,
- completion when no tool calls are made.

Include JSON:

```json
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"type": "text", "text": "Research this topic and summarize findings"}]
    },
    "configuration": {"mode": "autonomous"}
  }
}
```

CLI:

```bash
kaos agent a2a send researcher \
  --message "Research this topic and summarize findings" \
  --async
```

Key line:

> Continuous describes the workload. Async describes the caller contract.

## Section 8: How You Could Build the Basics Yourself

Approx. 900 words.

Include simplified components:

### Task state

```python
class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
```

### Budgets

```python
if budgets.max_iterations and iteration >= budgets.max_iterations:
    return stop("max_iterations")
```

### Cancellation

```python
if cancel_event.is_set():
    task.state = TaskState.CANCELED
    return
```

### Completion

```python
if tool_call_count == 0:
    task.state = TaskState.COMPLETED
    return
```

Explain:

- this is intentionally not a full framework,
- it shows the missing control plane,
- teams can use framework primitives or implement these boundaries around their own runtime.

## Section 9: Debugging and Human Control

Approx. 600 words.

Explain why UI/CLI matter:

- background work must be inspectable,
- humans need to cancel,
- task history helps reconnect after caller exits,
- memory explains what happened inside the loop.

KAOS examples:

- A2A debug screen,
- Agent card,
- SendMessage,
- task viewer,
- task history,
- memory conversation view,
- CLI get/cancel.

Key point:

> If you cannot inspect or stop an autonomous agent, you have not deployed an autonomous workload. You have launched a mystery process.

## Section 10: Lessons for Production Autonomous Agents

Approx. 700 words.

Practical lessons:

1. Start with the loop, but design the task contract early.
2. Separate continuous autonomy from bounded background tasks.
3. Treat budgets as safety controls.
4. Keep task state separate from memory.
5. Scope tools with permissions.
6. Build inspection and cancellation into the first version.
7. Use Kubernetes for workload concerns, not reasoning quality.
8. Prefer explicit goals over vague autonomy.
9. Instrument everything.

## Section 11: Conclusion

Approx. 300 words.

Close with:

> The hard part of autonomous agents is not making a model call itself again. That takes a loop. The hard part is making that loop safe to run when nobody is staring at the terminal.

End with practical framing:

- autonomous agents need goals,
- task state,
- budgets,
- cancellation,
- memory,
- permissions,
- observability,
- deployment substrate.

Mention KAOS lightly as an example:

> KAOS v0.4.0 is one concrete implementation of these ideas on Kubernetes, but the core patterns apply whether you use KAOS, LangGraph, CrewAI, ADK, OpenAI's SDK, or a loop you wrote yourself.

## Source Mapping

| Article section | Source artifacts |
| --- | --- |
| Basic loop | `AGENTIC_LOOP_BASICS.md` |
| Industry convergence | `INDUSTRY_RESEARCH.md`, `FRAMEWORK_SURVEY.md` |
| Kubernetes | `KUBERNETES_AUTONOMOUS_AGENTS.md` |
| KAOS example | `RELEASE_CONTEXT.md`, `KAOS_AUTONOMOUS_OVERVIEW.md`, `COMMITS_FULL.md` |
| Lessons | all research and style guide |

