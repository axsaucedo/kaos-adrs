_A practical guide to always-on agents, task state, budgets, cancellation, and Kubernetes-native orchestration, using KAOS v0.4.0 as the worked example._

---

There is an exciting pattern emerging as “always-on” autonomous agents that work proactively in the background which has been taken to massive popularity with tools like OpenClaw. This basically is the idea of moving away from Chat-based interactions for your agent to process the request, and instead having an agent proactively taking over tasks and not only carrying them out autonomously, but even continue extending towards other new self-started requests through an infinite loop.

This is an interesting new architectural innovation which has set a clear path where agentic systems are going.

A 24/7 agent with local memory, skills, integrations, private self-hosted execution, and a heartbeat-style loop that keeps checking the world even when you are not prompting it.

And although OpenClaw was one of the first movers, the rest of the frameworks are also following (+ catching up): LangGraph, CrewAI, OpenAI Agents SDK, Google ADK…

…and as part of this trend, we also ventured into the world of autonomous agentic systems at scale with the K8s Agent Orchestration System (KAOS), which led us through the good, the bad and the ugly of these patterns.

In this post we want to share the learnings designing, developing and scaling autonomous agentic patterns, including what actually changes when an agentic loop becomes an autonomous workload, and why Kubernetes starts to become relevant once you need to orchestrate many of them. I will use KAOS v0.4.x as the concrete implementation example, but the goal here is for everyone to familiarise the primitives you need whether you use KAOS, OpenClaw, LangGraph, CrewAI, Google ADK, Semantic Kernel, OpenAI's Agents SDK, or a loop you wrote yourself.

## #The Useful Part of the Hype

The phrase "autonomous agent" is overloaded enough to be almost useless.

Sometimes it means a chatbot that keeps working in the background. Sometimes it means a stateful graph workflow. Sometimes it means a coding agent running a long task. Sometimes it means a multi-agent organization with delegation and handoffs. And sometimes it just means "we put `while True` around the model call".

But there is a useful distinction here - a normal tool-using agent is usually request/response:

1. User asks a question.
    
2. Agent calls the model.
    
3. Model decides whether to use tools.
    
4. Tools return data.
    
5. Agent returns an answer.
    

An autonomous agent in the context of this post, ignores whether a human is waiting on the other side of the HTTP response.

The work may continue. The environment may change. The agent may run again. It may call tools repeatedly. It may need to remember what happened last time. It may need to be interrupted. It may need to survive a restart. It may need to run alongside hundreds of other agents that are doing similar things.

The hard part is not making the model call itself again. That takes a loop. The hard part is making that loop safe to run when nobody is staring at the terminal.

## #AI Agents 101: The Loop Everyone Starts With

Most agent systems begin with a deceptively simple loop:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
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

This is the core pattern behind a lot of the current wave of agentic software.

This loop is powerful, but it is still usually bounded by a request.

## #What Changes When the Loop Keeps Running?

The naive autonomous version looks like this:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
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

This is useful as a mental model. It is also not something I would want to deploy.

There is no identity for the work. No state machine. No budget. No cancellation. No inspection path. No ownership model. No persistence story. No scoped task lifecycle. No answer to the question "what is this agent doing right now?"

Once the loop runs without a synchronous caller, the engineering problem changes:

|Request/response agent|Autonomous agent|
|---|---|
|User waits for an answer|Work continues after the caller leaves|
|Loop ends with a response|Loop may run periodically or indefinitely|
|Failure is a request error|Failure becomes an operational incident|
|Context can be request-local|Needs task state, memory, and persistence boundaries|
|Tool calls happen inside one request|Tool calls may become ongoing side effects|
|Debugging starts with one trace|Debugging starts with task history, memory, state, and logs|

This is the main thesis:

> Autonomy is not the loop. Autonomy is the operating model around the loop.

## #The Missing Primitive: A Unit of Agent Work

If the agent can keep working after the caller leaves, this is where we start the need to introduce an ability to reason around the tasks being performed.

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
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

This does not look like an AI breakthrough. It looks like ordinary distributed-systems plumbing.

Production autonomous agents inherit all the boring concerns that make systems operable:

- submission,
    
- lifecycle state,
    
- output capture,
    
- error reporting,
    
- cancellation,
    
- retention,
    
- auditing,
    
- ownership.
    

If a user starts a long-running research task and closes the browser, they need a task ID. If an agent monitors a Kubernetes namespace, an operator needs to know whether it is working, stuck, failed, or canceled. If a tool starts returning bad data, you need to know which tasks used it.

## #Budgets Are Not Just About Cost

The first reason people add budgets is usually cost. But budgets are also safety controls:

|Budget|What it bounds|
|---|---|
|max iterations|runaway reasoning loops|
|max runtime|stuck or excessively long work|
|max tool calls|API pressure and side effects|
|token/cost budget|spend and context growth|
|per-iteration timeout|one blocked tool/model call|

A minimal check can be as simple as:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
def budget_exhausted(budgets, started_at, iteration, tool_calls):
    if budgets.max_iterations and iteration >= budgets.max_iterations:
        return "max_iterations"
    if budgets.max_runtime_seconds and time.monotonic() - started_at >= budgets.max_runtime_seconds:
        return "max_runtime_seconds"
    if budgets.max_tool_calls and tool_calls >= budgets.max_tool_calls:
        return "max_tool_calls"
    return None
```

## #Why OpenClaw, LangGraph, CrewAI, ADK and the Others Point in the Same Direction

OpenClaw's design pattern is meant to keep a private, self-hosted agent running with memory, integrations, skills, and a heartbeat. Let’s have a look at how other frameworks approach it:

|Framework|Approach|
|---|---|
|LangGraph|Durable, stateful agent orchestration.|
|CrewAI|Crews, flows, memory, guardrails, and human-in-the-loop controls|
|OpenAI Agents SDK|Gives developers a managed loop with sessions.|
|Google ADK|Frames the problem around production agents, graph workflows, evaluation, debugging, context management, and deployment|

The abstractions and approaches are different in some cases, but the same primitives keep reappearing in the source code implementation, including:

- state,
    
- tools,
    
- memory,
    
- guardrails,
    
- tracing,
    
- human intervention,
    
- deployment,
    
- resumability,
    
- task control.
    

Once agents stop being one-off prompt handlers, frameworks have to become work managers. They need to manage units of agent work, not just model calls. And when we have to take it to the next level of scale, this is where things get more complicated…

## #Kubernetes Enters the Picture

A platform cannot guarantee that the model will reason correctly. But if we have a way in which we can abstract some of these complex agentic concepts into architectural abstractions, we can then answer practical questions that become unavoidable when you run many agents:

- Where does each agent run?
    
- What identity does it have?
    
- Which tools can it reach?
    
- Which secrets can it read?
    
- What network is it allowed to access?
    
- How do we restart it?
    
- How do we observe it?
    
- How do we isolate it?
    
- How do we scale it?
    

AI workloads are moving away from short-lived stateless requests, and more toward coordinated agents that run constantly, maintain context, use tools, execute code, and communicate over longer periods.

If OpenClaw is one vision of the always-on agent, Kubernetes is one answer to the fleet question:

> What happens when every team, service, workflow, or tenant wants its own autonomous agents?

At that point you need scheduling, identity, isolation, policy, rollouts, configuration, and observability. Basically we need the same things we already learned to need for microservices, except the workload is now non-deterministic, tool-using, and stateful.

We made infrastructure much harder again.

## #Scaling Your Agent KAOS

To make this less abstract, let’s dive into it with a Kubernetes example using Pydantic AI and KAOS.

KAOS is a Kubernetes-native agent orchestration framework. It defines agents, MCP tool servers, and model APIs as Kubernetes resources. We recently released the new autonomous/A2A milestone, which supports asynchronous task lifecycle, JSON-RPC task methods, autonomous self-looping execution, budgets, cancellation, task history, CLI/UI debugging, and examples.

We’ll cover it with a fun example, where we’ll have a Production Operations Agent which will monitor a Kubernetes cluster - namely this will include:

- an agent with a monitoring goal,
    
- a read-only Kubernetes service account,
    
- an MCP server exposing Kubernetes tools,
    
- a reporting tool,
    
- a model API,
    
- budgets and task controls,
    
- an endpoint for async task interaction.
    

The key part of the Agent configuration looks like this:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
apiVersion: kaos.tools/v1alpha1
kind: Agent
metadata:
  name: cluster-monitor
spec:
  modelAPI: monitor-modelapi
  model: "smollm2:135m"
  mcpServers:
    - monitor-k8s-mcp
    - monitor-report-mcp
  config:
    description: "Autonomous cluster monitoring agent"
    instructions: |
      You are a Kubernetes cluster monitoring agent.
      List pods, check status, and generate a health report.
    autonomous:
      goal: "Monitor the Kubernetes cluster health. List pods, check their status, and generate a health report."
      intervalSeconds: 60
      maxIterRuntimeSeconds: 120
    taskConfig:
      maxIterations: 5
      maxRuntimeSeconds: 300
      maxToolCalls: 20
```

These are some of the key configurations:

- `autonomous.goal` defines the persistent objective.
    
- `intervalSeconds` controls the loop cadence.
    
- `maxIterRuntimeSeconds` bounds one iteration.
    
- `taskConfig` gives bounded defaults for async tasks.
    
- MCP servers define the tools.
    
- Kubernetes RBAC defines what those tools can actually access.
    

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
flowchart TB
    Agent[Agent: cluster-monitor]
    Goal[Autonomous goal]
    Model[ModelAPI]
    K8sMCP[MCP: Kubernetes read-only tools]
    ReportMCP[MCP: report formatter]
    RBAC[Read-only RBAC]
    Memory[Memory/events]

    Goal --> Agent
    Agent --> Model
    Agent --> K8sMCP
    Agent --> ReportMCP
    K8sMCP --> RBAC
    Agent --> Memory
```

Monitoring is a good use-case for autonomous agents, as the goal persists over time, the environment changes, and the agent needs tools but should be heavily constrained.

## #Continuous Mode vs Async Task Mode

Another design decision that we had to come across which was interesting was the distinction between “continuous autonomous execution” and “async task execution”.

Continuous mode does what it suggests, runs in the background with a goal, and infinitely iterates towards that goal: i.e. when the pod starts, it begins working toward that goal. In this case it is daemon-like: monitoring, checking, reporting, maintaining, watching.

Async task mode is the superset capability that allows the framework to execute without user / API interaction once the task is submitted; it would just not loop once the goal is achieved or the budgets are depleated.

For an example of an Async task, a caller sends a task, gets a task ID, and the agent continues working in the background. The caller can later inspect or cancel it.

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
{
  "jsonrpc": "2.0",
  "method": "SendMessage",
  "id": 1,
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "Research recent autonomous agent frameworks and summarize findings."
        }
      ]
    },
    "configuration": {
      "mode": "autonomous"
    }
  }
}
```

Through the KAOS CLI, that becomes:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
kaos agent a2a send researcher \
  --message "Research recent autonomous agent frameworks and summarize findings." \
  --async
```

Then the caller can poll:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
{
  "jsonrpc": "2.0",
  "method": "GetTask",
  "id": 2,
  "params": {"id": "task_abc123"}
}
```

Or cancel:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
{
  "jsonrpc": "2.0",
  "method": "CancelTask",
  "id": 3,
  "params": {"id": "task_abc123"}
}
```

## #Task State Is Not Memory

Another small but important lesson that we had to reason about was that task state and memory are not the same thing; this is obvious when saying it out-loud, but it was important to figure out what we need to have available where for the agent framework to have the right context.

We found that task state should be small and stable:

- submitted,
    
- working,
    
- completed,
    
- failed,
    
- canceled,
    
- budget exhausted.
    

Memory can be richer:

- user messages,
    
- agent responses,
    
- tool calls,
    
- tool results,
    
- delegations,
    
- observations,
    
- session history.
    

If you mix them, your task API becomes noisy and your memory system becomes responsible for lifecycle control. That is a bad trade.

Keep task state external and crisp. Keep memory useful for reasoning and debugging.

## #Debugging Many Autonomous Agents

The debugging story changes as soon as the work is no longer attached to one waiting user - everything gets exponentially harder.

You need to answer:

- What task did I start?
    
- Is it still running?
    
- What did it do?
    
- Which tools did it call?
    
- What did those tools return?
    
- Did it hit a budget?
    
- Can I stop it?
    

KAOS exposes that through CLI and UI paths:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
kaos agent a2a send <agent> --message "..." --async
kaos agent a2a get <agent> --task-id <id>
kaos agent a2a cancel <agent> --task-id <id>
```

The UI adds agent-card inspection, SendMessage, task viewer, auto-polling, cancellation, task history, and memory conversation views.

## #How You Could Build the Basics Yourself

You do not need a full framework to understand the minimal shape.

Start with a single-iteration primitive:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
async def run_agent_once(goal, history) -> tuple[str, int]:
    messages = build_messages(goal, history)
    response = await run_agent(messages, tools)
    return response.text, response.tool_call_count
```

Then wrap it in the smallest useful control loop:

NoneBashCSSCC#GoHTMLObjective-CJavaJavaScriptJSONPerlPHPPowershellPythonRubyRustSQLTypeScriptYAMLCopy

```
async def run_autonomous_task(task, budgets, cancel_event):
    started_at = time.monotonic()
    iteration = 0
    tool_calls = 0

    task.state = TaskState.WORKING

    while True:
        if cancel_event.is_set():
            task.state = TaskState.CANCELED
            return task

        reason = budget_exhausted(budgets, started_at, iteration, tool_calls)
        if reason:
            task.events.append({"type": "budget.exhausted", "reason": reason})
            task.state = TaskState.COMPLETED
            return task

        output, calls = await run_agent_once(task.goal, task.history)
        task.output = output
        task.history.append({"iteration": iteration, "output": output})
        tool_calls += calls
        iteration += 1

        if calls == 0:
            task.state = TaskState.COMPLETED
            return task
```

This is not production-ready. It does not handle persistence, retries, distributed workers, authentication, policy, observability, or recovery after process restart.

But it shows the skeleton:

- task identity,
    
- state transitions,
    
- budgets,
    
- cancellation,
    
- output,
    
- history,
    
- completion detection.
    

If you use an existing framework, look for where these pieces live. If you write your own runtime, add them before the first demo becomes a production dependency.

## #When Not to Make It Autonomous

There is a temptation to turn every useful agent into a background process.

Autonomy is helpful when:

- the environment changes over time,
    
- the goal persists beyond one request,
    
- the work is too long for a synchronous response,
    
- the agent can safely observe or act with scoped tools,
    
- the user benefits from periodic or event-driven progress.
    

Autonomy is a poor fit when:

- the action is high-risk and lacks approval controls,
    
- tool permissions are broad or unclear,
    
- success criteria are vague,
    
- cancellation is missing,
    
- progress cannot be inspected,
    
- cost or side effects are unbounded.
    

## #Lessons for Production Autonomous Agents

Here are the patterns I would carry into any autonomous-agent system.

### #1. Start with the loop, but design the task contract early

The agentic loop is the easy part to prototype, however the task contract is what makes it operable.

### #2. Separate continuous autonomy from bounded background work

An agent that monitors forever and an agent that writes a report in the background need different controls.

### #3. Treat budgets as safety controls

Budgets bound cost, time, tool side effects, API pressure, and runaway reasoning.

### #4. Keep task state separate from memory

Task state is the external lifecycle, memory is the execution context, and mixing them makes APIs noisy and debugging harder.

### #5. Scope tools with permissions

Autonomy becomes risky through tools, ensure you support this with read-only service accounts, scoped roles, network policy, and secret boundaries matter more than the prompt.

### #6. Build cancellation into the first version

Cancellation is not an advanced feature, it is a foundational feature that should be integrated by design.

### #7. Use Kubernetes for workload concerns, not reasoning quality

Kubernetes can help with lifecycle, identity, permissions, isolation, networking, rollouts, and observability - but it will not make a bad model / agent less bad.

### #8. Instrument everything

Agent loops are variable, non-deterministic, and tool-heavy: Traces, logs, metrics, task IDs, and memory events are how you understand them later. This is something that we skimmed through in this post, if you are interested on a more in-depth post on this you should check out: [Monitoring KAOS: Observability for Multi-Agent Systems](https://hackernoon.com/production-observability-for-multi-agent-ai-with-kaos-otel-signoz).
