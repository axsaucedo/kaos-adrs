# Image and Visual Plan

The final article should be diagram-rich like the OTel post, but visuals should clarify the broader autonomous-agent engineering story rather than advertise KAOS.

## Visual 1: Basic Agentic Loop

Purpose:

Show the baseline loop before autonomy.

Diagram:

```mermaid
flowchart LR
    U[User Request] --> M[Model]
    M --> D{Need tool?}
    D -->|Yes| T[Tool Call]
    T --> R[Tool Result]
    R --> M
    D -->|No| A[Final Answer]
```

Caption:

> A basic agentic loop is still request/response: the model calls tools until it can answer.

## Visual 2: Autonomous Loop with Control Plane

Purpose:

Show the new operational pieces.

```mermaid
flowchart TD
    G[Goal] --> S[Task Submitted]
    S --> W[Working]
    W --> B{Budget OK?}
    B -->|No| C[Complete: Budget Exhausted]
    B -->|Yes| I[Run Agent Iteration]
    I --> T{Tool Calls?}
    T -->|Yes| M[Store Memory]
    M --> W
    T -->|No| Done[Completed]
    W --> X{Cancel?}
    X -->|Yes| Cancel[Canceled]
```

Caption:

> Autonomy is the control plane around the loop: task state, budgets, memory, and cancellation.

## Visual 3: Continuous vs Async Task Mode

Purpose:

Show the article's central distinction.

```mermaid
flowchart LR
    subgraph Continuous Mode
        C1[Pod Starts] --> C2[Load CRD Goal]
        C2 --> C3[Run Iteration]
        C3 --> C4[Sleep interval]
        C4 --> C3
    end

    subgraph Async Task Mode
        A1[SendMessage] --> A2[Return Task ID]
        A2 --> A3[Background Loop]
        A3 --> A4{Done/Budget/Cancel?}
        A4 -->|No| A3
        A4 -->|Yes| A5[Terminal Task]
    end
```

Caption:

> Continuous mode is a daemon-like workload. Async task mode is a bounded background job with a caller-visible task contract.

## Visual 4: Kubernetes Autonomous-Agent Architecture

Purpose:

Explain why Kubernetes is relevant.

```mermaid
flowchart TB
    CRD[Agent CRD] --> Operator[Operator / Controller]
    Operator --> Pod[Agent Runtime Pod]
    Pod --> Model[Model API]
    Pod --> Tools[MCP Tools / APIs]
    Pod --> Memory[(Memory / Task Store)]
    Pod --> Obs[Telemetry]
    RBAC[ServiceAccount + RBAC] --> Pod
    Secret[Kubernetes Secret / External Secret] --> Pod
    User[User / Another Agent] --> A2A[A2A / Task API]
    A2A --> Pod
```

Caption:

> Kubernetes does not solve reasoning, but it provides lifecycle, identity, permissions, secrets, networking, and observability for autonomous workloads.

## Visual 5: KAOS Cluster Monitor Case Study

Purpose:

Show the practical example.

```mermaid
flowchart TB
    Agent[Agent: cluster-monitor]
    Goal[Autonomous Goal]
    Model[ModelAPI: Ollama / hosted model]
    K8sMCP[MCP: Kubernetes read-only tools]
    ReportMCP[MCP: report formatter]
    RBAC[Read-only RBAC]
    Memory[Memory Events]

    Goal --> Agent
    Agent --> Model
    Agent --> K8sMCP
    Agent --> ReportMCP
    K8sMCP --> RBAC
    Agent --> Memory
```

Caption:

> A practical autonomous agent needs a goal, tools, permissions, model access, memory, and a way to inspect output.

## Screenshots to Capture If Environment Is Available

Optional, not blocking:

1. KAOS UI agent list with autonomous badge.
2. Agent detail page showing autonomous config.
3. A2A debug screen with agent card and SendMessage.
4. A2A task viewer with task state/history.
5. Memory conversation view showing tool calls/results.

## Optional GIF

Mirror the OTel post style with a short GIF:

1. Open Agent detail page.
2. Send async A2A message.
3. Watch task state update.
4. Open task history.
5. Open memory view.

Caption:

> Sending and inspecting an autonomous A2A task through the KAOS UI.

## Visual Style

- Prefer clean Mermaid diagrams for conceptual sections.
- Use screenshots only for KAOS-specific sections.
- Keep captions explanatory.
- Avoid visuals that require the reader to already know KAOS.

