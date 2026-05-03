# Writing Style for the Autonomous Agents Article

This file captures the style target for `BLOGPOST_COMPLETE_V2.md`, based on the two reference posts:

- "Production Observability for Multi-Agent AI (with KAOS + OTel + SigNoz)"
- "With Claude Code, Software Engineering Moves Up the Abstraction Stack"

The goal is not to copy those posts. The goal is to preserve the same authorial feel: practical, technical, mildly opinionated, exploratory, and grounded in what happens when you actually build systems.

## Core Voice

Use a practitioner voice, not an analyst voice.

Preferred:

> I kept coming back to the same uncomfortable question: if this agent is supposed to run without me watching it, what is the operating model?

Avoid:

> Modern autonomous agents require robust lifecycle management, observability, and orchestration primitives.

The second sentence is true, but it sounds like generic AI copy. The first sounds like someone who hit the problem while building.

## Opening Pattern

The opening should start with the live industry moment, not with KAOS internals.

For this article, the opening should reference OpenClaw and similar frameworks early because they represent the current always-on agent direction:

- always-on personal agents,
- stateful long-running graph agents,
- multi-agent crews,
- SDK-managed tool loops,
- agents deployed as cloud/Kubernetes workloads.

Then the article should pivot to the real question:

> The interesting part is not that the loop can run again. The interesting part is what happens when there are hundreds of these loops, each with tools, memory, permissions, budgets, and a task lifecycle.

## Sentence Rhythm

Use shorter paragraphs than a typical technical whitepaper. Make sections readable as a sequence of small arguments.

Good rhythm:

1. Concrete observation.
2. Short implication.
3. Technical expansion.
4. Code/table/diagram.
5. Practical takeaway.

Avoid long summary paragraphs that try to explain every concept at once.

## Rhetorical Style

Use questions as pivots.

Examples:

- "Well, what is it?"
- "So what actually changes?"
- "Where does Kubernetes enter the picture?"
- "What does the minimal version look like?"

This mirrors the reference posts, which often move from a concrete observation to a broader question before going technical.

## KAOS Balance

KAOS should be the worked example, not the protagonist.

Bad framing:

> KAOS v0.4.0 adds autonomous execution, A2A task lifecycle, budgets, and UI debugging.

Better framing:

> To make the operating model concrete, I will use KAOS v0.4.0 as the example implementation. The APIs are KAOS-specific, but the shape of the problem is not.

## Industry Framing

Do not save the framework survey until the middle of the post. The reader is likely arriving because they have heard about autonomous agents, OpenClaw, LangGraph, CrewAI, OpenAI Agents SDK, Google ADK, or similar tools.

Open with that landscape, then explain the internals.

The industry framing should make the use case clear:

- one always-on agent is interesting;
- many always-on agents become an orchestration problem;
- Kubernetes becomes relevant when agents need identity, isolation, scheduling, permissions, networking, observability, and lifecycle control.

## Avoid ChatGPT/Gemini Texture

Avoid:

- "In today's rapidly evolving landscape..."
- "This comprehensive guide explores..."
- "It is crucial to understand..."
- "Robust, scalable, and production-ready..."
- perfectly symmetrical lists that sound generated;
- generic transitions like "Now that we've covered X, let's dive into Y."

Prefer:

- "This is where the demo starts lying to you."
- "That sounds boring. It is also the difference between a useful agent and a runaway process."
- "Kubernetes does not make the agent smarter. It makes it operable."
- "Calling the model again is easy. Operating the loop is the system."

## Technical Detail Style

Use code to reveal the shape of the problem, not to dump implementation.

Preferred:

```python
if cancel_event.is_set():
    task.state = TaskState.CANCELED
    return task
```

Then explain why it matters operationally.

Avoid long source excerpts in the final article. Keep the deeper extraction files as supporting material.

## Ending Pattern

The ending should be practical and slightly philosophical, like the reference posts.

It should land on a concise thesis:

> The future autonomous-agent stack will not be defined only by better prompts or smarter models. It will be defined by the operating layer around the loop: tasks, budgets, permissions, memory, cancellation, observability, and an infrastructure substrate that can run many agents without turning them into mystery processes.

