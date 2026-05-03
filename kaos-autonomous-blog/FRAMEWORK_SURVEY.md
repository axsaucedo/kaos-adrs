# Framework Survey: Autonomous Agents and Orchestration

This survey is intentionally practical. It is not trying to pick a winner; it identifies what each framework emphasizes and how that maps to production autonomy.

## Source Register

Primary or official sources used:

- OpenClaw docs: <https://clawdocs.org/>
- LangGraph overview: <https://docs.langchain.com/oss/python/langgraph/overview>
- LangSmith deployment / LangGraph platform docs: <https://docs.langchain.com/langgraph-platform/>
- CrewAI docs: <https://docs.crewai.com/>
- OpenAI Agents SDK docs: <https://openai.github.io/openai-agents-python/>
- Google Agent Development Kit docs: <https://google.github.io/adk-docs/>
- Microsoft Agent Framework docs: <https://learn.microsoft.com/en-us/agent-framework/>
- Semantic Kernel overview: <https://learn.microsoft.com/en-us/semantic-kernel/overview/>
- LlamaIndex agents docs: <https://docs.llamaindex.ai/en/stable/use_cases/agents/>
- Haystack agents docs: <https://docs.haystack.deepset.ai/docs/agents>

## OpenClaw

OpenClaw is the closest reference point for always-on personal autonomy.

Official docs describe it as:

- an autonomous agent that runs 24/7 with a heartbeat system,
- connected to many integrations/channels,
- model-provider agnostic,
- extensible through Markdown/YAML skills,
- private by default with local memory,
- security-focused with optional sandboxing and hardening guides.

Source: <https://clawdocs.org/>

Article use:

OpenClaw is useful for explaining always-on autonomy as a user-facing assistant pattern:

```text
heartbeat -> check inbox/tasks/context -> decide action -> use tools -> update memory -> repeat
```

Contrast with KAOS:

- OpenClaw is oriented toward personal/self-hosted assistant workflows and multi-channel access.
- KAOS is oriented toward Kubernetes-native agent workloads, CRDs, A2A, MCP tools, and cluster operations.

The article should not frame them as direct competitors. They represent different deployment centers of gravity.

## LangGraph / LangSmith Deployment

LangGraph describes itself as a low-level orchestration framework and runtime for long-running, stateful agents. Its docs emphasize:

- durable execution,
- human-in-the-loop,
- comprehensive memory,
- debugging with LangSmith,
- production deployment for stateful long-running workflows.

Source: <https://docs.langchain.com/oss/python/langgraph/overview>

LangSmith Deployment adds managed infrastructure for agent workloads, including Studio debugging, state inspection, deployment options, agent composition, MCP, and A2A support.

Source: <https://docs.langchain.com/langgraph-platform/>

Article use:

LangGraph is a strong example of the "stateful workflow" school of agent engineering. It is a good reference when discussing graphs, state checkpoints, inspection, branching, and human intervention.

## CrewAI

CrewAI positions itself around collaborative agents, crews, and flows. Its docs emphasize:

- agents with tools, memory, knowledge, and structured outputs,
- flows that orchestrate steps, manage state, persist execution, and resume long-running workflows,
- tasks and processes with guardrails, callbacks, and human-in-the-loop triggers,
- observability and enterprise deployment surfaces.

Source: <https://docs.crewai.com/>

Article use:

CrewAI is useful for the role/team mental model: give agents roles, assign tasks, and coordinate a crew. It is less useful as the primary Kubernetes workload example, but important in the industry survey because many teams encounter autonomy first through role-based abstractions.

## AutoGen / Microsoft Agent Framework

Microsoft's Agent Framework documentation positions the framework around robust, future-proof agentic AI solutions.

Source: <https://learn.microsoft.com/en-us/agent-framework/>

Historically, AutoGen has been associated with conversational multi-agent systems: agents exchange messages, critique, refine, and hand off work. Microsoft is increasingly aligning agent tooling around enterprise frameworks, Semantic Kernel, and Azure integration.

Article use:

Use this category to discuss conversation-centric multi-agent orchestration:

- useful for research/coding/review workflows,
- natural human-in-the-loop points at message turns,
- less explicit as a Kubernetes-native lifecycle abstraction unless paired with platform infrastructure.

## OpenAI Agents SDK

OpenAI's Agents SDK docs define a small set of primitives:

- agents as LLMs equipped with instructions and tools,
- agents as tools / handoffs,
- guardrails,
- built-in agent loop,
- function tools,
- MCP server tool calling,
- sessions,
- human-in-the-loop,
- tracing,
- sandbox agents.

Source: <https://openai.github.io/openai-agents-python/>

The docs also explicitly distinguish using lower-level APIs when you want to own the loop, tool dispatch, and state handling yourself.

Article use:

OpenAI Agents SDK is useful for showing the "managed loop" approach. It gives developers a runtime for the loop, handoffs, tools, guardrails, and tracing, while still leaving deployment architecture to the application/platform.

## Google Agent Development Kit

Google ADK positions itself as an open-source framework for building, debugging, and deploying production agents in Python, TypeScript, Go, and Java.

Its docs emphasize:

- multi-agent orchestration,
- graph-based workflows,
- evaluation,
- debugging,
- deployment to Google Cloud, Cloud Run, and GKE,
- context management,
- hands-off managed task structures,
- iterative model requests,
- tool calls,
- recording data,
- parallel jobs,
- failure handling,
- resuming stopped tasks.

Source: <https://google.github.io/adk-docs/>

Article use:

ADK is a strong source for the claim that agent frameworks are moving from prototypes toward production-grade managed task structures.

## Semantic Kernel

Semantic Kernel describes itself as a lightweight, open-source development kit for building AI agents and integrating models into C#, Python, or Java codebases.

It emphasizes:

- enterprise readiness,
- telemetry support,
- hooks and filters,
- modular plugins,
- automating business processes through existing APIs,
- connecting code to evolving model providers.

Source: <https://learn.microsoft.com/en-us/semantic-kernel/overview/>

Article use:

Semantic Kernel is useful when discussing plugin/tool abstractions and enterprise integration, especially for teams already in the Microsoft/Azure ecosystem.

## LlamaIndex Agents

LlamaIndex defines an agent as an automated reasoning and decision engine that can:

- break complex questions into smaller ones,
- choose tools and tool parameters,
- plan tasks,
- store previously completed tasks in memory.

It offers prebuilt agents and full-control custom workflows.

Source: <https://docs.llamaindex.ai/en/stable/use_cases/agents/>

Article use:

LlamaIndex is strongest for knowledge-heavy and RAG-centered agent use cases: research assistants, report generation, customer support, and workflows over documents/data.

## Haystack Agents

Haystack's agent documentation shows a tool-calling pipeline pattern:

- a chat generator emits tool calls,
- a router detects whether tool calls are present,
- a tool invoker executes them,
- collected messages are fed back to the generator until a final reply exists.

Source: <https://docs.haystack.deepset.ai/docs/agents>

Article use:

Haystack is a useful example of the agentic loop expressed as a pipeline. It helps explain that "agent frameworks" are often control-flow runtimes around model/tool interactions.

## Survey Takeaways

| Pattern | Framework examples | Article point |
| --- | --- | --- |
| Always-on assistant | OpenClaw | Autonomy can be a persistent background service. |
| Stateful graph/workflow | LangGraph, Google ADK | Long-running agents need state, checkpoints, and inspection. |
| Role/team abstraction | CrewAI | Multi-agent collaboration can be modeled as roles and tasks. |
| Conversation-centric orchestration | AutoGen / Microsoft Agent Framework | Agent collaboration can be a controlled message exchange. |
| Managed loop SDK | OpenAI Agents SDK | Tool calls, handoffs, sessions, guardrails, and tracing can be runtime primitives. |
| Plugin/API integration | Semantic Kernel | Enterprise autonomy depends on safe access to existing systems. |
| Knowledge/RAG agents | LlamaIndex, Haystack | Many agents are reasoning loops over data and retrieval tools. |
| Kubernetes-native workload | KAOS, Agent Sandbox, kagent-style platforms | Deployment substrate becomes part of autonomy. |

## How This Shapes the Article

The article should avoid a framework bake-off. Instead, use the survey to show convergence:

- Frameworks are adding state.
- Frameworks are adding human intervention.
- Frameworks are adding tracing/evaluation.
- Frameworks are adding tool/runtime integration.
- Platforms are adding deployment abstractions for long-running agents.

That convergence supports the main thesis: autonomous agents are becoming workloads.

