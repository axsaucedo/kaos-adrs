# Agentic Loop Basics: From Chat Response to Autonomous Workload

This document is the reader-oriented technical baseline for the article. It should be understandable without knowing KAOS.

## 1. The Basic Agentic Loop

A normal chat completion is a single model call:

```python
response = await model.chat(messages)
return response.text
```

An agentic system adds tools and repeats until the model can answer:

```python
async def run_agent(messages, tools, max_steps=5):
    for step in range(max_steps):
        response = await model.chat(messages, tools=tools)

        if response.tool_calls:
            for call in response.tool_calls:
                result = await tools[call.name](**call.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                })
            continue

        return response.text

    raise RuntimeError("agent exceeded max_steps")
```

This loop is the foundation for many agent systems:

1. The model observes the current conversation and tool results.
2. It decides whether it has enough information.
3. If not, it calls a tool.
4. The tool result goes back into context.
5. The model tries again.

The important point: the loop is still request/response. A user sends a request and waits for the answer.

## 2. What Changes When the Loop Becomes Autonomous

Autonomy changes the control plane around the loop.

Instead of:

```text
user request -> loop -> response
```

you now have:

```text
goal -> repeated loop iterations -> state/memory/output -> continue, stop, or wait
```

That creates new engineering questions:

| Question | Why it matters |
| --- | --- |
| What is the goal? | The agent needs a stable objective between iterations. |
| Who starts the work? | A user request, a schedule, a pod startup, a webhook, or another agent. |
| How long may it run? | Without limits, a loop can burn tokens, call tools forever, or create side effects. |
| How do you stop it? | Humans and systems need cancellation. |
| How do you inspect it? | Background work needs task state, logs, memory, and output. |
| What can it touch? | Tools need permissions, secrets, and scoped identities. |
| What survives restart? | Long-running work often needs durable memory or recoverable task state. |

## 3. A Minimal Autonomous Loop

The simplest autonomous loop re-injects the goal on every iteration:

```python
async def run_autonomous(goal, tools, interval_seconds=60):
    memory = []

    while True:
        messages = [
            {"role": "system", "content": "You are an autonomous worker."},
            {"role": "user", "content": goal},
            *memory[-20:],
        ]

        response = await run_agent(messages, tools)
        memory.append({"role": "assistant", "content": response})

        await sleep(interval_seconds)
```

This is useful but dangerous. It has no budget, cancellation, task state, or error handling.

## 4. Add a Task Model

Once work can outlive the request, give it an identity and state:

```python
class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class Task:
    id: str
    goal: str
    state: TaskState
    output: str = ""
    history: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
```

Now a caller can ask:

- What is the task ID?
- Is it still working?
- What did it output?
- Can I cancel it?
- What state transitions happened?

## 5. Add Budgets

Budgets are not only cost controls. They are safety controls.

```python
@dataclass
class Budgets:
    max_iterations: int = 10
    max_runtime_seconds: int = 300
    max_tool_calls: int = 50


def budget_exhausted(budgets, started_at, iteration, tool_calls):
    if budgets.max_iterations and iteration >= budgets.max_iterations:
        return "max_iterations"
    if budgets.max_runtime_seconds and time.monotonic() - started_at >= budgets.max_runtime_seconds:
        return "max_runtime_seconds"
    if budgets.max_tool_calls and tool_calls >= budgets.max_tool_calls:
        return "max_tool_calls"
    return None
```

Budgets should be checked between iterations, not only at the end, because external tools may have side effects.

## 6. Add Cancellation

A background loop should observe cancellation regularly:

```python
async def run_task(task, budgets, cancel_event):
    started_at = time.monotonic()
    iteration = 0
    tool_calls = 0

    task.state = TaskState.WORKING

    while not cancel_event.is_set():
        reason = budget_exhausted(budgets, started_at, iteration, tool_calls)
        if reason:
            task.events.append({"type": "budget.exhausted", "reason": reason})
            task.state = TaskState.COMPLETED
            return

        output, calls = await run_agent_once(task.goal, task.history)
        task.output = output
        tool_calls += calls
        iteration += 1

        if calls == 0:
            task.state = TaskState.COMPLETED
            return

    task.state = TaskState.CANCELED
```

The cancellation path matters as much as the happy path. It is how operators keep autonomy bounded.

## 7. Continuous Mode vs Async Task Mode

There are at least two kinds of autonomous execution:

| Mode | Control pattern | Stop condition | Example |
| --- | --- | --- | --- |
| Continuous autonomous mode | Starts with the workload and keeps looping | Pod/process stops, explicit cancel, unrecoverable error | Cluster monitor, inbox watcher, incident sentinel |
| Async task mode | Starts from a request and returns a task ID | Completion, budget, cancel, failure | Research job, report generation, code review |

This distinction is central to the final article. Many conversations about autonomous agents mix these two patterns, but they have different operational contracts.

## 8. Memory vs Task State

Avoid using one log for everything.

Task state answers:

```text
What is this unit of work doing?
```

Memory answers:

```text
What happened during execution, and what context should the agent remember?
```

That separation keeps APIs clean:

- `GetTask` can return task status, events, output, and history.
- Memory can retain user messages, tool calls, tool results, and agent responses.
- Observability can correlate both with traces and logs.

## 9. The Minimal Production Checklist

Before calling an agent "autonomous," ask whether it has:

- A clear goal.
- A loop boundary.
- A task identity.
- State transitions.
- Budget controls.
- Cancellation.
- Tool permissions.
- Memory/history.
- Observability.
- A human inspection path.

The article should use this checklist as the bridge from simple agentic loops to the KAOS case study.

