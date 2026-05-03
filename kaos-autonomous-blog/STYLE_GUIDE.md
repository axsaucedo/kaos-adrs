# Style Guide and Positioning

## Positioning Rule

The article is not "KAOS v0.4.0 release notes."

The article is:

> A practical engineering guide to what changes when agentic loops become autonomous, long-running workloads.

KAOS is the worked example, in the same way the OpenTelemetry post used KAOS as the concrete system for exploring agent observability.

## Target Reader

Primary reader:

- application/platform engineer,
- familiar with APIs and Kubernetes basics,
- interested in agentic AI,
- may have built simple tool-calling agents,
- has not yet operated autonomous agents in production.

Secondary reader:

- engineering leader evaluating agent frameworks,
- developer advocate / technical founder,
- infrastructure engineer thinking about AI workloads.

## Tone

Use:

- practical,
- technical,
- explanatory,
- mildly opinionated,
- grounded in implementation details,
- accessible to engineers who do not know KAOS.

Avoid:

- release-note language,
- hype,
- "this changes everything" claims,
- unexplained protocol acronyms,
- excessive framework comparison tables in the main article,
- too much KAOS-specific file/function naming outside deep-dive sections.

## Structural Pattern from the OTel Post

The OTel post works because it follows a useful pattern:

1. Relatable production problem.
2. Why agentic systems differ from traditional APIs.
3. Simple mental model and code snippet.
4. Practical use case.
5. Concrete framework implementation.
6. Deep technical explanation.
7. Debugging/operations walkthrough.
8. Lessons readers can apply elsewhere.

Apply the same pattern here:

1. Relatable autonomy problem.
2. Why autonomous agents differ from request/response agents.
3. Simple agentic loop.
4. What changes when the loop keeps running.
5. Practical use case: autonomous cluster monitor.
6. KAOS case study.
7. Build-it-yourself minimal implementation.
8. Lessons and tradeoffs.

## Useful Opening Style

Preferred opening:

> You've built an agent that works well when a user is waiting for the answer. It calls tools, reasons over results, and returns something useful. Then someone asks it to keep going: watch this system, check every few minutes, take action when something changes, and tell me when it matters.
>
> That is not just a longer prompt. It is a different workload.

This mirrors the OTel post's direct production scenario without copying it.

## KAOS Balance

Recommended article balance:

| Content type | Approximate share |
| --- | --- |
| Domain challenge and mental model | 35% |
| Industry/framework context | 15% |
| KAOS case study | 25% |
| Build-it-yourself implementation ideas | 15% |
| Lessons/closing | 10% |

KAOS should appear after the reader understands the general problem.

Preferred transition:

> To make this concrete, let's use KAOS v0.4.0 as a worked example. The specific APIs are KAOS-specific, but the patterns are the ones you need in any production autonomous-agent system.

## Required Reader-Reusable Material

Include material that readers can implement without KAOS:

- basic agentic loop pseudocode,
- autonomous self-loop pseudocode,
- task state enum,
- budget checks,
- cancellation path,
- memory vs task state distinction,
- deployment checklist.

## Required KAOS Case-Study Material

Include:

- Agent CRD with `autonomous.goal`,
- continuous mode vs A2A async task mode,
- A2A `SendMessage` / `GetTask`,
- CLI `kaos agent a2a send --async`,
- cluster-monitor sample,
- UI/CLI debugging,
- memory/task state separation.

## Section-Level Style

Each section should answer one reader question:

- "What problem am I solving?"
- "Why does this differ from normal APIs?"
- "What is the minimal version?"
- "Where does this break in production?"
- "What does a real implementation look like?"
- "What should I copy into my own system?"

Use short lead paragraphs, then code/table/diagram.

## Code Style

Use pseudocode when explaining general patterns. Use real-ish YAML/JSON/Bash for the KAOS case study.

Preferred:

```python
if budgets.max_iterations and iteration >= budgets.max_iterations:
    return stop("max_iterations")
```

Avoid long source-code dumps. Source excerpts belong in `COMMITS_FULL.md`, not the final article.

## Diagrams

Use diagrams to compress concepts:

- basic agentic loop,
- autonomous loop with task state,
- continuous vs async modes,
- Kubernetes deployment architecture,
- task/memory/observability boundary.

The OTel article used diagrams and screenshots effectively. This article should do the same, but only where they clarify the workload model.

## Terminology

Use consistently:

- **agentic loop**: a model/tool loop that may still be request/response.
- **autonomous loop**: repeated agentic execution toward a goal without a synchronous user waiting.
- **continuous mode**: startup-triggered, daemon-like, indefinite loop.
- **async task mode**: request-triggered, task-ID-based, bounded background execution.
- **task state**: external lifecycle state.
- **memory**: internal/execution history and context.
- **budget**: guardrail over iterations/time/tools/cost.
- **cancellation**: external stop path.

Avoid:

- using "autonomous" as a synonym for every background task,
- implying all autonomous agents should run forever,
- implying Kubernetes makes model behavior safe,
- claiming a framework is production-ready without citing its docs or qualifying the claim.

## Ending Style

The ending should be practical, not promotional.

Preferred closing idea:

> The hard part of autonomous agents is not making a model call itself again. That takes a loop. The hard part is making that loop safe to run when nobody is staring at the terminal: scoped tools, explicit goals, budgets, cancellation, memory, task state, and an infrastructure layer that treats the agent as a workload.

