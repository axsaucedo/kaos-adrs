# Relevant Diff and Source Excerpts

This file captures the high-signal implementation excerpts needed for the article. The full raw release diff can be regenerated from the KAOS repo with:

```bash
cd /Users/asaucedo/Programming/agentic/kaos
git diff v0.3.1..v0.4.0
```

The curated excerpts below are enough to support the article's claims without turning the writing package into an unreadable patch dump.

## 1. Task Model and Lifecycle

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
class TaskState(str, Enum):
    """A2A task lifecycle states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INPUT_REQUIRED = "input-required"


VALID_TRANSITIONS: Dict[TaskState, set] = {
    TaskState.SUBMITTED: {TaskState.WORKING, TaskState.CANCELED, TaskState.FAILED},
    TaskState.WORKING: {
        TaskState.COMPLETED,
        TaskState.FAILED,
        TaskState.CANCELED,
        TaskState.INPUT_REQUIRED,
    },
    TaskState.INPUT_REQUIRED: {TaskState.WORKING, TaskState.CANCELED, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELED: set(),
}
```

Article use: introduce the idea that autonomous work needs lifecycle state, not just logs.

## 2. Task Events as State Transitions

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
EVENT_TASK_SUBMITTED = "task.submitted"
EVENT_TASK_WORKING = "task.working"
EVENT_TASK_COMPLETED = "task.completed"
EVENT_TASK_FAILED = "task.failed"
EVENT_TASK_CANCELED = "task.canceled"
EVENT_AUTONOMOUS_BUDGET_EXHAUSTED = "autonomous.budget.exhausted"
```

Article use: explain the separation between "what state is the task in?" and "what happened during execution?" The former belongs to task events; the latter belongs to memory/conversation events.

## 3. Continuous Autonomous Config vs Async Task Budgets

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
@dataclass
class AutonomousConfig:
    """Per-iteration config for CRD-activated autonomous execution.

    A value of 0 means unlimited (no limit enforced) for that budget.
    """

    goal: str = ""
    interval_seconds: int = 0
    max_iter_runtime_seconds: int = 60


@dataclass
class TaskBudgets:
    """Overall budget limits for A2A async task execution.

    A value of 0 means unlimited (no limit enforced) for that budget.
    """

    max_iterations: int = 10
    max_runtime_seconds: int = 300
    max_tool_calls: int = 50
    interval_seconds: int = 0
```

Article use: this is the compact technical expression of the main conceptual distinction.

## 4. LocalTaskManager as the Execution Boundary

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
class LocalTaskManager(TaskManager):
    """In-process task manager with internal dict storage and synchronous execution.

    Encapsulates task creation, state management, execution via process_fn,
    and OTel instrumentation. process_fn(message, session_id) -> (response, tool_call_count).
    """
```

Article use: show that the runtime separates "how to run the agent once" from "how to manage a task around that run."

## 5. Autonomous Submission Returns Immediately

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
async def submit_autonomous(
    self,
    goal: str,
    session_id: Optional[str] = None,
    budgets: Optional[TaskBudgets] = None,
    autonomous_config: Optional[AutonomousConfig] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Task:
    """Submit an autonomous run. Spawns background task, returns immediately."""
    ...
    self._transition(task.id, TaskState.WORKING, "Autonomous execution started")
    ...
    bg_task = asyncio.create_task(
        self._execute_autonomous(
            task.id,
            goal,
            task.session_id,
            budgets=effective_budgets,
            autonomous_config=autonomous_config,
        )
    )
    self._running_tasks[task.id] = bg_task
    return task
```

Article use: explain why async autonomous work needs task IDs, polling, cancellation, and retained state.

## 6. Budget Checks

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
if not is_autonomous:
    if budgets.max_iterations > 0 and iteration >= budgets.max_iterations:
        msg = f"Budget exhausted: max_iterations ({budgets.max_iterations}) reached"
        task.add_event(
            EVENT_AUTONOMOUS_BUDGET_EXHAUSTED,
            {"reason": "max_iterations", "iterations": iteration},
        )
        last_response = msg
        break

    elapsed = time.monotonic() - loop_start
    if budgets.max_runtime_seconds > 0 and elapsed >= budgets.max_runtime_seconds:
        msg = f"Budget exhausted: max_runtime_seconds ({budgets.max_runtime_seconds}s) reached"
        task.add_event(
            EVENT_AUTONOMOUS_BUDGET_EXHAUSTED,
            {"reason": "max_runtime_seconds", "elapsed": round(elapsed, 1)},
        )
        last_response = msg
        break

    if budgets.max_tool_calls > 0 and total_tool_calls >= budgets.max_tool_calls:
        msg = f"Budget exhausted: max_tool_calls ({budgets.max_tool_calls}) reached"
        task.add_event(
            EVENT_AUTONOMOUS_BUDGET_EXHAUSTED,
            {"reason": "max_tool_calls", "total_tool_calls": total_tool_calls},
        )
        last_response = msg
        break
```

Article use: budgets are a safety primitive. They bound cost, time, and side-effect exposure.

## 7. Completion Detection

Source: `pydantic-ai-server/pais/a2a.py` at `v0.4.0`.

```python
if not is_autonomous and tool_call_count == 0:
    logger.info(
        f"Autonomous run {task_id} completed after {iteration} iterations"
    )
    break
```

Article use: a simple but powerful pattern: if a bounded task iteration produces no tool calls, treat the text answer as completion.

## 8. CRD Surface

Source: `operator/api/v1alpha1/agent_types.go` at `v0.4.0`.

```go
// AutonomousConfig configures autonomous (self-looping) agent execution.
// When a goal is set, the agent self-loops on startup with per-iteration budgets.
// For bounded async tasks triggered via A2A, use taskConfig.
type AutonomousConfig struct {
    // Goal is the objective the agent works toward autonomously.
    // Setting this activates autonomous execution on agent startup.
    Goal string `json:"goal,omitempty"`

    // IntervalSeconds is the pause between autonomous loop iterations.
    IntervalSeconds *int32 `json:"intervalSeconds,omitempty"`

    // MaxIterRuntimeSeconds is the maximum wall-clock time per iteration.
    MaxIterRuntimeSeconds *int32 `json:"maxIterRuntimeSeconds,omitempty"`
}

// TaskConfig configures budget limits for A2A async task execution.
type TaskConfig struct {
    MaxIterations *int32 `json:"maxIterations,omitempty"`
    MaxRuntimeSeconds *int32 `json:"maxRuntimeSeconds,omitempty"`
    MaxToolCalls *int32 `json:"maxToolCalls,omitempty"`
}
```

Article use: Kubernetes CRDs can express autonomy as desired state, not just deployment metadata.

## 9. A2A CLI Shape

Source: `kaos-cli/kaos_cli/agent/a2a.py` at `v0.4.0`.

```python
async_task: bool = typer.Option(
    False, "--async", help="Execute as async task (returns task ID for polling)."
)
...
if async_task:
    params["configuration"] = {"mode": "autonomous"}
```

Article use: terminology changed from "mode autonomous" to "async" to clarify that the CLI flag describes the task execution contract.

## 10. UI Debugging Surface

Source: `kaos-ui/src/components/agent/AgentA2ADebug.tsx` at `v0.4.0`.

```tsx
<TabsTrigger value="send" data-testid="a2a-tab-send">
  <Radio className="h-3 w-3 mr-1.5" />
  Send Message
</TabsTrigger>
<TabsTrigger value="tasks" data-testid="a2a-tab-tasks">
  <Clock className="h-3 w-3 mr-1.5" />
  Get / Cancel Task
</TabsTrigger>
```

Article use: production autonomy needs operational UX. The debugger is not a nice-to-have; it is how humans regain control over background work.

