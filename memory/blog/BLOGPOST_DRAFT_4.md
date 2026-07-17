# Agentic Memory: A Journey Across the Galaxy

_How agents remember: building short-, medium- and long-term memory that scales across users, agents, and groups._

---

LLMs are stateless by design, and without added memory logic every session starts from zero. 

A number of dedicated memory layers have emerged (and continue emerging almost daily) to tackle this, each with different approaches and tradeoffs. Which one should you adopt?

Recently I spent some time extending the Kubernetes Agent Orchestration System (KAOS) to support multi-tiered memory persistence (aka short-, medium- and long-term memory). Along the way I hit most of the same issues that anyone would whilst building or integrating multi-tiered memory into an agentic system, so I thought it would be useful to compile all the learnings, design choices and examples. 

Hopefully this post is useful for anyone looking to do this on their own project. My objective:

> Let's make the memory layer BORING, so that the agents can continue to be the fun part.

This post includes the research findings from exploring ~38 tools, including tools like [Mem0](https://github.com/mem0ai/mem0), [Zep/Graphiti](https://github.com/getzep/graphiti), [Letta (MemGPT)](https://www.letta.com/), [Cognee](https://github.com/topoteretes/cognee), [Memobase](https://github.com/memodb-io/memobase), [Redis Agent Memory Server](https://github.com/redis/agent-memory-server), as well as native implementations in [OpenAI's products](https://openai.com/index/memory-and-new-controls-for-chatgpt/), [Claude](https://claude.com/blog/memory), [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview), [CrewAI](https://docs.crewai.com/introduction), and [Google ADK](https://google.github.io/adk-docs/), among many others.

I also share the learnings and best practices that came out of navigating through a large number of architecture tradeoffs, and getting my hands dirty on the implementation that now ships as a distributed, highly available, and scalable `MemoryStore` resource that any agent can bind to. 

As with my previous posts on [observability for agentic systems](https://hackernoon.com/production-observability-for-multi-agent-ai-with-kaos-otel-signoz) and [autonomous always-on agentic patterns](https://hackernoon.com/), I will use KAOS as the concrete implementation example, but the goal is to provide practical intuition for the primitives (tiers, scopes, folding, degradation), so that it applies whether you use KAOS, Mem0 directly, LangGraph, CrewAI, or a memory layer you wrote yourself.

## A Working Taxonomy of Agent Memory

"Memory" is one of the most overloaded words in agentic systems, so it is worth separating it from the concepts it gets conflated with, such as:

- The **context window**, which holds working state for a single model call.
- **Session history**, which holds an auditable transcript of what was said.
* **Prompt telemetry**, which holds the specific prompts relative to events in the system.

To be more precise we can look at Princeton University's paper on [Cognitive Architectures for Language Agents (CoALA)](https://arxiv.org/abs/2309.02427) to provide a more precise definition for "Memory" in agentic systems. We can define "Memory" as the component that holds the short-, medium- and long-term information an agent carries across turns and sessions to inform its reasoning.

This research paper quoted also provides a useful taxonomy for "memory types" that we will use to reason about the latter sections. This includes the memory types for episodic, semantic, procedural and temporal memory. 

These memory types are also mentioned in the Berkeley paper that released [MemGPT](https://arxiv.org/abs/2310.08560), as well as how the Stanford paper on large-scale LLM simulations [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) structured their memory event stream.

The formal definition of these memory types (+ a few examples) is outlined as follows:

| Memory type          | What it holds                                  | Example                                                     |
| -------------------- | ---------------------------------------------- | ----------------------------------------------------------- |
| Short-term (working) | verbatim recent turns of the live conversation | "the user just said port 8080"                              |
| Episodic             | records of specific past events                | "on Tuesday the deploy failed twice"                        |
| Semantic             | distilled, durable facts                       | "the user prefers blue-green deploys"                       |
| Procedural           | learned skills and how-tos                     | "here is how we roll back this service"                     |
| Temporal             | facts with validity intervals                  | "Joe *was* in a relationship until March, but not anymore." |

In practice what I found out however is that most frameworks only implement a small number of these, namely **short-term** is always present, **episodic and semantic** are bundled (the only difference is whether time is preserved), **procedural** tends to be present mainly in coding agents (eg creating skills, commands, extensions), and **temporal** tends to be replaced with "forgetting memory" functionality instead, or embedded with episodic/semantic.

These appear more informally defined as:
* **Conversational continuity**: The agent remembers what was said three turns ago; a *same-session* problem. 
* **Learned knowledge**: The agent remembers what it figured out last week; a *cross-session* problem. 

For example, frameworks like [LangGraph](https://docs.langchain.com/oss/python/langgraph/persistence) separate thread-scoped checkpointers from a cross-thread store. Another example is [Letta](https://docs.letta.com/guides/core-concepts/memory/memory-blocks), which separates always-in-context memory blocks from an archival tier. 

Most of the design mistakes I made early came from either trying to tackle all of these "memory-types" separately, by bundling sub-optimally, or by oversimplifying too much. 

But before we dive into the implementation, let's cover the basics.

## Memory 101: The Version Everyone Starts With

Almost every agent system starts with the same memory implementation:

```python
memory = []

async def handle_message(user_message):
    memory.append({"role": "user", "content": user_message})
    response = await run_agent(memory[-20:], tools)
    memory.append({"role": "assistant", "content": response})
    return response
```

And to be honest, the original KAOS memory was exactly this. It was an in-process queue with a max length, which ensured it was replaying the last N events into the next prompt.

The second version everyone builds is "just embed everything":

```python
async def handle_message(user_message):
    hits = await vector_store.search(embed(user_message), top_k=5)
    context = "\n".join(h.text for h in hits)
    response = await run_agent([context, user_message], tools)
    await vector_store.add(embed(user_message), user_message)
    return response
```

This is better, but this is not memory in the form that we introduced eariler, it is just a better search mechanism across the prompt history.

Another tempting alternative as the next step is "context windows are huge now, just replay everything". 

However this is not a great approach, and there are some benchmarks like [UCLA's Bench on Long-Term Interactive Memory](https://arxiv.org/abs/2410.10813), which showed that models reasoning over full ~115K-token interaction histories lose 30-60% accuracy versus the same models given oracle retrieval. 

If we look at it from a feature / functionality standpoint, we can summarise the gaps between the base and the production implementation as follows:

| Naive memory                         | Production memory                                                      |
| ------------------------------------ | ---------------------------------------------------------------------- |
| Last-N turns, unbounded token growth | Token-budgeted window with principled eviction                         |
| Verbatim replay of everything        | Distilled facts, separated from the transcript (eg long- / short-term) |
| One user, one process                | Many tenants, many agents, many replicas                               |
| Memory lives inside the agent pod    | Memory survives restarts and is shared across the fleet                |
| Writes block the response            | Extraction runs off the hot path                                       |
| Nothing is ever forgotten            | Decay, retention, and right-to-erasure                                 |
| Memory failure crashes the turn      | Memory failure degrades the turn                                       |

In this case we can position "production memory" a tiered, scoped, context-specific and dynamic store, as opposed to purely a vector database connected to an agent. 

Achieving this in a way that scales does get complex, as we need to decide who can see each memory tier, when we store facts, and how the agent behaves when memory fails. 

However now that we have the conceptual foundation in place, we can start looking at these functionalities relative to the frameworks available.

## Choosing an Engine: Build, Adopt, or Wrap

Before designing anything, I surveyed the landscape thoroughly, assessing dozens of tools across three tiers, and we will cover the scope, approach and learnings in this section, starting with an overview of all the tiers as follows.

**Tier 1: Dedicated memory frameworks.** 
This tier encompasses purpose-built frameworks whose whole job is agent memory. From the longer list, we reduced it to the actively maintained ones:

| Candidate | Approach | Store | Strength | Weakness |
| --- | --- | --- | --- | --- |
| [Mem0](https://github.com/mem0ai/mem0) | extracts facts from conversations into a vector store and recalls them by similarity | Qdrant, pgvector, others | most adopted, cleanest library integration | no OTel, tenant isolation only at application level |
| [Zep / Graphiti](https://github.com/getzep/graphiti) | builds a temporal knowledge graph where facts carry validity intervals and provenance | Neo4j or FalkorDB | richest memory model, time-aware fact invalidation | heaviest to operate, costliest writes |
| [Cognee](https://github.com/topoteretes/cognee) | combines a knowledge graph with vector search, populated by an extract-and-load pipeline | LanceDB by default, Postgres or Neo4j optional | multi-tenancy and OTel built in | early stage, heavy dependencies, changing API |
| [Memobase](https://github.com/memodb-io/memobase) | maintains structured user profiles and event timelines, with no embeddings on the hot path | Postgres + Redis | cheapest write path | profile-only recall, weak self-hosted multi-tenancy |
| [Redis Agent Memory Server](https://github.com/redis/agent-memory-server) | serves two memory tiers (working and long-term) behind one REST API | Redis | the two-tier model mirrors what agents actually need | young project, no OTel |

What this tier taught me is that the architectural differences are really differences in recall pattern and write cost. Vector-first designs answer "what do we know about X" cheaply, graph-first designs answer "how did this fact change over time" at the price of an LLM-heavy ingestion pipeline plus a graph database. The profile-first designs answer "who is this user" with no embeddings on the hot path at all, and the two-tier designs bake in the working-versus-long-term split directly. 

There were also clear shared gaps, mainly at the infrastructure level; none of them enforces tenant isolation below the application level, and almost none ships OpenTelemetry, so whichever one you pick, scope enforcement and observability become your integration work. That shared gap shaped the KAOS design more than any individual feature did.

It's also worth noting that several of these libraries also offer an enterprise tier, so it was important to validate that basic features are not gated behind a paywall (similar to what we previously experienced with Google ADK and Vertex). More specifically [Mem0's own platform-versus-OSS documentation](https://docs.mem0.ai/platform/platform-vs-oss) gates temporal reasoning, memory decay, webhooks, export, analytics, and auto-scaling behind the managed platform, and [Zep draws the line](https://www.getzep.com/platform/graphiti/) at governed multi-tenancy and compliance, with the OSS Graphiti engine giving you a single context graph to run yourself. The pattern across vendors is that the memory algorithms are open while the operational maturity is the commercial product, which previews the exact layer a platform adopting one of these engines has to build.

**Tier 2. Agent frameworks with native memory.** 
This tier encompasses the embedded memory functionality across end-to-end agentic frameworks, and included the usual suspect / popular frameworks like [LangGraph's Store and LangMem](https://docs.langchain.com/oss/python/langgraph/persistence), [CrewAI memory](https://docs.crewai.com/introduction), [LlamaIndex memory](https://docs.llamaindex.ai/), [Google ADK](https://google.github.io/adk-docs/)'s MemoryService, and the [Microsoft Agent Framework](https://github.com/microsoft/agent-framework). These were reviewed for their design choices, but adopting one for its memory means importing a second agent runtime next to your own, so they served as references and not as candidates.

The learning from this tier is actually what they all had in common. Every framework independently separates session-scoped state and cross-session knowledge, such as how LangGraph has thread-scoped checkpointers versus its cross-thread Store. 

There was also a clear separation between "local playground" and "production grade" when it comes to memory for all frameworks. 

* [LangGraph](https://docs.langchain.com/oss/python/langgraph/add-memory): In-memory store is for development, but it's recommended to use a database-backed checkpointer and store for production. 
* [Google ADK](https://adk.dev/sessions/memory/): Heavier paywall, as it only offers the `InMemoryMemoryService` as open source, but anything serious would need to use Vertex AI. 
* [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/get-started/memory): Defaults to an in-memory context provider, with durable state via first-party Cosmos checkpoint storage, and ships a first-party `Mem0ContextProvider`.
* CrewAI: Community documented replacing its native store with Mem0 after hitting redeploy and user-isolation gaps. 

Also interesting learnings from agent harnesses and coding agents:

* [OpenClaw](https://docs.openclaw.ai/reference/AGENTS.default): layers markdown memory files (`MEMORY.md`, dated notes, per-skill `SKILL.md`) and runs a "Skill Workshop" where the agent proposes new skills from successful conversations for human approval. 
* [Hermes agent](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md): Uses skills explicitly as procedural memory, which are auto-proposed after repeated successful tool-call patterns, carry semver versions bumped on each self-improvement, and follow an anti-sediment principle where a skill should get shorter and sharper over time.
* [Claude Code skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview): Uses progressive disclosure, loading only ~100 tokens of skill metadata until a skill is triggered.

Native memory is increasingly an extensible interface where the shipped default is a placeholder, which means memory is being externalized by design across the ecosystem, and the dominant production pattern is framework plus engine. This is something that we had to take into consideration as well.

**Tier 3. Managed and commercial services.** 
This tier included commercial services with managed memory platforms, which provided insights on the broader design of the system and the interactions with the memory, as opposed to just the design of the memory capability itself. These included the [Mem0 Platform](https://mem0.ai/), [Zep Cloud](https://www.getzep.com/), [Letta Cloud](https://www.letta.com/), [OpenAI memory](https://openai.com/index/memory-and-new-controls-for-chatgpt/), and [Google's Vertex Memory Bank](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/agent-engine/memory-bank/overview). 

The learnings from this tier were also quite helpful to understand some of the architectural and feature tradeoffs that were done at the platform level. Every managed platform has the same two-layer model: namely 1) an explicit, user-curated layer (eg. OpenAI's saved memories, Claude's editable memory summary) that is visible/available at the surface, and that is build on top of; 2) an automatically inferred and consolidated layer (eg. OpenAI's chat-history reference, Vertex Memory Bank's LLM extraction with per-scope deduplication and contradiction checks) where the memory store/retrieval algorithms live.

There was however a clear distinction on the scope in which memory is available across each platform: For Claude, memory scope is per project, in Vertex scope is per identity with configurable memory "topics", and Zep scopes per subject graph. None of them defaults to one global memory per account, which makes it clear that there is a design decision required on the isolation boundary.

#### Conclusions from Surveying the Ecosystem

Given the review was done in context of KAOS, the lens / considerations through which these were reviewed included the following non-exhaustive list:
* Long-term capability coverage
* Retrieval quality
* Embeddability as a library
* Pluggable storage backends
* Infrastructure delta / overhead
* Multi-tenancy hooks
* Observability
* Licensing
* Maturity
* Write-path cost

Based on these, the library that clearly stood out was **Mem0**. At least at the time of writing, Mem0 maximized the features and capabilities with the lowest integration friction. Mem0 also has the strongest ecosystem maturity, and pluggable stores. 

It's however worth noting that despite Mem0 being the right choice for this context, one learning that may seem obvious in retrospect was that **there is no "Perfect Candidate".** The graph-first leaders (Graphiti, Cognee) have the most features but at the highest cost. Low-delta options (Redis AMS) buy fit at maturity cost. Building it yourself directly on the raw vector or graph stores, which we also weighed as the baseline option, allows you to have all the features and fit, but at the cost of rebuilding mature extraction and retrieval that already exists under permissive licenses.

This also applies to the numbers the frameworks publish about themselves. Interestingly enough, Mem0's own research supports that extraction-based memory improves latency and cost, however it does not improve raw accuracy: in [Mem0's own evaluation](https://arxiv.org/abs/2504.19413) on LoCoMo, a full-context baseline beats Mem0 on raw accuracy (72.9% vs 66.9%), while memory buys a 91% cut in p95 latency (1.44s vs 17.1s) and over 90% fewer tokens per conversation. At fleet scale that trade is exactly right, since you cannot ship 17-second turns and 26K-token replays, but it is a trade you should make knowingly.

As part of this, despite Mem0 being the strongest choice, it became clear that **adopting a memory engine means choosing which 60% of the system you do not have to build, and committing to build the remaining 40% around it**. 

For Mem0, this meant working on the bridge to close some of the gaps, particularly at the infrastructure and interoperability layer. These included:

* Enabling telemetry by instrumenting every operation and ensure correlation+consistency with the broader KAOS telemetry.
* Introduce tenant isolation, as this is enforced at the Mem0 application level, so enforce scope through the memory service.
* Bundle up the kubernetes packaging to ensure high availability and scalability as a distributed service.
* Bridge the short- and medium-term memory with a native integration with the Pydantic AI server that we have built as part of KAOS.

Based on these initial decisions we were able to proceed with the architectural choices at the end-to-end agent level.

## Designing our Memory Architecture: The Three Tiers

As we now locked the decision to go forward with Mem0 as the memory library, we can move to the broader design architecture for the distributed memory tiers in KAOS.

Based on the requirements, we needed to support three tiers: a short-term window, a medium-term summary, and long-term "facts". These are intuitively used as follows:

| Tier        | What it holds                                                                     | When it updates                                      | Backing                      |
| ----------- | --------------------------------------------------------------------------------- | ---------------------------------------------------- | ---------------------------- |
| Short-term  | The context window of the live session, bounded by a token budget                 | Every turn (cheap append)                            | Relational rows              |
| Medium-term | Rolling summary per session, versioned so past summaries stay accessible          | On compaction, when the window hits its token budget | Relational rows, append-only |
| Long-term   | Atomic facts extracted from context window, keyed by scope, recalled semantically | In the background, after compaction                  | Mem0 into the vector store   |

Defining these tiers allow us to formalise the following design decisions:

* Long-term memory functionality is enabled via Mem0; short- and medium-term memory are custom; These three tiers should cohesively integrate as a single interoperable unit.
* Medium- and long-term extraction **is lossy**. There's definitely some interesting approaches where [we could enable provenance](https://arxiv.org/abs/2605.04897), however I decided to keep this out of scope at least for now.
* Medium- and long-term extraction are always **off the write path**; when compaction threshold is crossed, as opposed to in every insert, which is also how [Mem0's own platform behaves](https://docs.mem0.ai/core-concepts/memory-operations), processing memory additions in the background and returning a pending event to poll.
* The medium-term summary stays **out of the vector store**: Mem0 wants atomic, individually revisable facts, whereas a summary is a narrative whose whole value is its continuity, so it is stored as a plain relational row and injected verbatim, and only the raw evicted turns are handed to Mem0 for extraction.
* Underneath all three tiers, the **raw turns are the source of truth** and everything else (summaries, facts, embeddings) is a recomputable projection, which is also what makes lossy extraction and fire-and-forget background processing acceptable.
* Temporal (bi-temporal validity) and procedural (aka skill persistence) memory are deliberately **deferred** in its explicit form; but achievable through the long-term memory.

 These definitions also allow us to design the singel coherent service that offers the short-, medium- and long-term memory tiers; the **"MemoryStore Service"**.

```mermaid
graph LR
  subgraph agent["Agent pod"]
    rt["Agent runtime<br/>(remote memory client)"]
  end
  subgraph svc["MemoryStore service"]
    st["Short-term window<br/>(relational rows)<br/>Verbatim turns, token-budgeted"]
    mt["Medium-term summary<br/>(relational, append-only)<br/>One rolling window per session"]
    lt["Long-term facts<br/>(Mem0 -> vector store)<br/>Extracted + deduplicated"]
  end
  store[("Storage<br/>dev: SQLite + Chroma<br/>prod: Postgres + pgvector")]
  rt -->|recall / write / forget| svc
  st --- store
  mt --- store
  lt --- store
```


We will cover more on the `MemoryStore` service in the kubernetes section below, but before we do that, we need to talk about another important (+ tricky) topic; access scopes.

## Scopes: Whose Memory Is It Anyway?

Every memory operation in a multi-tenant fleet needs an answer to "whose memory is it?". And the answer has to come from the design of the system components. 

In KAOS the choice was to go for a deliberately flat model; a single `scope` value per agent, mapped by the service onto exactly one owner key, as follows:

| `scope`           | Owner key                     | Who shares it                         |
| ----------------- | ----------------------------- | ------------------------------------- |
| `session`         | `run_id = <session id>`       | Only this conversation session        |
| `agent` (default) | `agent_id = <agent identity>` | Only this agent.                      |
| `user`            | `user_id = <user identity>`   | Every agent serving the same user.    |
| `group`           | `agent_id = "kaos:group"`     | Every agent + user in the same group. |

This scope model is probably the obvious choice; the trickier question is how do we enable these shared scopes. There were a few design options for this:

1. **Many groups inside one MemoryStore.** One store holds the memories of several groups at once. This sounds efficient, however it means building and operating a whole group-management layer: an API to create and delete groups and to add and remove members, a group key on every record, per-group quotas, and a single store whose failure affects every group in it.
2. **One group per MemoryStore.** The store itself is the group: whichever agents are bound to the same store share it, so membership is just the existing binding and no new API is needed. The cost is that every group needs its own store deployment, and sharing across two groups means binding to a second store. 
3. **Hierarchical scope paths.** A richer model where scopes are nested paths (for example `org:team:agent`) and agents share memory up to the point where their paths diverge. Every version of this I drafted ended up re-creating an authorization system that the two simpler options already covered.

Although the most intuitive choice initially could be the first one, interestingly enough the second model is the one that most (if not all) managed platforms expose. A few examples:
* [Mem0 platform](https://docs.mem0.ai/platform/platform-vs-oss): A project is the container that memories cannot cross; API keys are scoped to a project, and the user and agent partitions live within it.
* [Vertex Memory Bank](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview): Provisions one Memory Bank per Agent Engine instance, and within it memories are partitioned by scope, with retrieval only returning memories whose scope exactly matches the request.
* [Zep Cloud](https://www.getzep.com/platform/graphiti/): Each subject (a user, or a group via their group-graph API) gets its own isolated context graph, and the cloud platform is the control plane that manages millions of them.

Based on this, I decided to go for option 2 as well. This means that the four scope levels are supported via the same `MemoryStore`, and are backed by a multi-tenant database layer.

There are two interesting caveats that also become important when we consider access control in these memory choices:

* **Post-retrieval filtering**: Some database engines apply scope filters after the retrieval step, which means that in some cases a query expecting a number of results may return less than expected. This is a known consideration on [pgvector as it post-filters by default](https://dev.to/franckpachot/no-pre-filtering-in-pgvector-means-reduced-ann-recall-1aa1), and it is why engines like [Qdrant filter inside the index traversal](https://qdrant.tech/documentation/manage-data/multitenancy/). **To mitigate this**, I validated the pre-filtering behaviour on both Chroma and pgvector before committing to the design.
* **Security Attack Surfaces**: Interesting research such as [AgentPoison](https://arxiv.org/abs/2407.12784)  show the impact of poisoning memory (ie 0.1% poisoned memory yields over 80% attack success), as well as [MINJA](https://arxiv.org/abs/2503.03704) which shows that an attacker needs no write access at all, because if the agent writes its own memory from conversations then every user is a write path. **To mitigate this**, KAOS  derives the scope server-side from the authenticated agent identity, fail-closed, and never from model- or tool-supplied arguments.
* **Right to Erasure**: Compliance requirements such as GDPR mean you must be able to answer "delete everything you know about this user" reliably, and in a multi-tier design the same information lives in several derived forms at once (raw turns, summaries, extracted facts, and their embeddings), so deleting from one tier is not enough. **To mitigate this**, KAOS implements `forget` as a single operation that fans out across all three tiers in one pass, deleting the short-term rows, the summaries, and the scope-filtered long-term facts. Note this is destruction, which is different from supersession, where facts are merely marked invalid but kept for history.

Now that we have sorted the tiers and the access scopes, we can move forward to the end-to-end platform implementation.

## Kubernetes Enters the Picture: Memory as Infrastructure

Now that we have all the separate pieces, it's required make a decision on how do we stitch them together; as part of this, I needed to go through several architectural design choices. We'll go through a few of these in this section.

The first design decision was, which data store should we go for? Should we go for FAISS? Chroma? pgvector? Milvus? Pinecone? 

The answer did not need to be a single store, because the requirements differ between a local development loop and a production fleet. 

* ***For development** the priority is zero external dependencies, so the store should be embeddable in the service container. 
* **For production** the priorities are durability, horizontal scaling, and reusing infrastructure you already operate. 

This ruled out SaaS-only options (Pinecone), library-only indexes with no persistence or filtering story (FAISS), and dedicated clusters that would add heavy new infrastructure (Milvus, Weaviate), and landed on two storage modes with the same service code on top of both:

```mermaid
flowchart LR
  MS[MemoryStore service]
  subgraph dev["local mode (development)"]
    C["Chroma (embedded)<br/>long-term vectors"]
    S["SQLite<br/>short + medium tiers"]
    PVC[("one PersistentVolume")]
    C --- PVC
    S --- PVC
  end
  subgraph prod["external mode (production)"]
    PG[("Postgres + pgvector<br/>all tiers, all durable state")]
  end
  MS --> dev
  MS --> prod
```

The second design decision was, where the memory engine runs. Should it run runs **inside every agent** as a library? as a **side-car** next to every pod? or as a **central service component**?. 

Embedding in the engine looks attractive at first, but the challenges compound with the number of agents. Namely as LLM calls for extraction land on the serving process, every agent replica opens its own datastore connections, every agent image carries the engine and its dependencies, and replicas of the same agent silently diverge in what they remember. 

Instead, going for the central option gives us the opposite: LLM extraction lands on the `MemoryStore` service, agents only interact with the respective store, agent images can use only the client, and scales with replicas horizontally. Here's the visual overview:

```mermaid
flowchart TB
    subgraph agents["Agent fleet"]
      A1[Agent: assistant]
      A2[Agent: researcher]
      A3[Agent: cluster-monitor]
    end
    subgraph ms["MemoryStore service (2 replicas, stateless)"]
      API["Tiered memory API<br/>recall / write / forget"]
      BG["Background workers<br/>folding + extraction"]
    end
    PG[("Postgres + pgvector<br/>(all durable state)")]
    SUM["ModelAPI: summarization"]
    EMB["ModelAPI: embeddings"]

    A1 & A2 & A3 -->|HTTP| API
    API --> PG
    BG --> PG
    BG --> SUM
    BG --> EMB
```


The third design decision was the failure contract: namely, what should happen if the memory service is unreachable? 

The decision here was that **Memory should be an augmentation and not a hard dependency**, so a memory outage should degrade an agent and never stop it.

That means that in KAOS, **recall is always soft**. If the long-term tier is unavailable, recall returns short-term-only context and the turn proceeds, so a recall failure can never fail a user's request (configurable with the failure mode).

And the fourth design decision was the architectural abstraction of "Memory" as an infrastructure component in Kubernetes. In this case it meant codifying the `MemoryStore` resources into a specification that is described as follows:

```yaml
apiVersion: kaos.tools/v1alpha1
kind: MemoryStore
metadata:
  name: shared-memory
spec:
  engine: mem0
  storage:
    type: external          # or "local" for dev: Chroma + SQLite on a PVC
    external:
      provider: pgvector
      connectionSecretRef:
        name: pgvector-dsn
        key: dsn
  models:
    summarization:
      modelAPI: my-modelapi
      model: gpt-4o-mini
    embedding:
      modelAPI: my-modelapi
      model: text-embedding-3-small
```

To provide the intuition on the one we landed on, here's what these mean:
* `storage.type`: provides the `local` type for dev and `external` for prod.
* `storage.local.provider` / `storage.external.provider`: embedded Chroma plus SQLite for local (one container on a PersistentVolume, single replica); Postgres with pgvector for external, referenced through a `connectionSecretRef` as a bring-your-own database.
* `storage.external.embeddingDims`: the vector dimensions of the embedding model.
* `replicas`: defaults by mode, 1 for local (the volume is single-writer) and 2 for external (the service is stateless over Postgres, guarded by a disruption budget).
* `models.summarization` / `models.embedding`: references to `ModelAPI` resources instead of provider keys, so the memory system's LLM calls go through the same gateway, quotas, and observability as every other component.
* `extraction.concurrency`: the bound on background extraction workers.
* `defaultFailureMode`: `soft` or `strict` write behaviour for bound agents, overridable per agent.

And the fifth design decision was how all of this ships as code. The whole memory layer is packaged as `kaos-memory`, a single Python package that provides both the client and the server: the runtime imports the thin client, the `MemoryStore` deployment runs the service, and both import one shared wire contract so the two cannot drift apart. We will cover the package in more detail in the integration section below.

These were some of the major design decisions worth highlighting, there were quite a lot of others but I'd never finish the blog post if we cover all of them. A few honorable mentions are: wrapping Mem0 as a library inside the service instead of running the stock Mem0 server, which provides none of the tiering, scope injection, or telemetry; serializing compaction through database advisory locks so multiple service replicas can fold the same session without double-folds; and shipping without a durable extraction queue, since the short-term tier is the recoverable source of truth and a queue is only worth building once measurement shows it is needed.

Now that we have all the major pieces threaded together, we can now dive into a hands on example to show how it all works in practice.

## Worked Example: Memory Across Sessions, Scopes, and Failures

Let's now take a practical end-to-end example that exercises the three claims this post has been making: that memory persists across sessions automatically, that scopes actually isolate, and that a memory outage degrades an agent without stopping it. The setup consists of a `ModelAPI`, a `local`-mode `MemoryStore` (embedded Chroma plus SQLite on a PersistentVolume, no external database), and two `Agent`s bound to the same store with different scopes.

```mermaid
graph LR
    subgraph store["MemoryStore: shared-memory"]
      G[("group partition")]
      P[("agent partition")]
    end
    A1[Agent: memory-agent<br/>scope: group] -->|recall + flush| G
    A2[Agent: private-agent<br/>scope: agent] -->|recall + flush| P
```

### Part 1: Cross-Session Continuity

Deploy a store and bind the first agent to it (a `local`-mode store, so this runs on any cluster with no external database):

```yaml
apiVersion: kaos.tools/v1alpha1
kind: Agent
metadata:
  name: memory-agent
spec:
  modelAPI: memory-modelapi
  model: gpt-4o-mini
  config:
    instructions: |
      You are a helpful assistant with long-term memory. Remember facts the
      user tells you and recall them in later conversations.
    memory:
      type: remote
      memoryStore: shared-memory
      scope: group
      tools: all
      failureMode: soft
```

Before running it, it is worth separating the two mechanisms this config enables. Binding a store applies an **automatic baseline** unconditionally: the runtime recalls relevant memory and injects it before every run, and flushes the conversation for persistence and extraction after every run, with no involvement from the model. The `tools` field layers **explicit, model-driven tools** on top of that baseline:

| `tools` | Exposed | The model can… |
| --- | --- | --- |
| _(unset)_ | none | rely purely on automatic recall/persist |
| `read` | `search_memory` | look facts up mid-reasoning |
| `write` | `save_memory` | distil and save a durable fact on demand |
| `all` | both | save and search explicitly |

So in the walkthrough below, the cross-session recall works even with `tools` unset; the tools are there for when the model should decide what is worth remembering. Note two deliberate conservatisms in this design. The tools are **additive and off by default**, and that default is now empirically backed, since [a 2026 systematic study of memory poisoning](https://arxiv.org/abs/2606.04329) found that the agents which write to and retrieve from memory most aggressively are the most exploitable. And the tools do **not** take a scope, because the model supplies queries and content while the service derives the scope from the agent's identity, the fail-closed rule from earlier applied at the tool boundary where it matters most.

Session 1: tell the agent a fact. This is an ordinary chat request, and the runtime persists the conversation to the central store after the run (note `kaos agent invoke` takes an explicit namespace, as it does not inherit the kubectl context):

```bash
kaos agent invoke memory-agent -n memory-example \
  -m "My favourite deployment port is 8080"
```

```
Port-forwarding to agent-memory-agent:8000...
Sending message: My favourite deployment port is 8080

Response:
Noted, your favourite deployment port is 8080.
```

Now verify the integration by asking the **memory service** directly, instead of trusting the agent's word for it:

```bash
kubectl port-forward -n memory-example svc/memorystore-shared-memory 18080:8080 &
curl -s http://localhost:18080/v1/recall \
  -H 'content-type: application/json' \
  -d '{"scope": {"level": "group"}, "query": "deployment port", "include_short_term": true}'
```

```json
{"facts": [],
 "short_term": {"recent": [
    ["user", "My favourite deployment port is 8080"],
    ["assistant", "Noted, your favourite deployment port is 8080."]]},
 "medium_term": {"summary": ""}, "block": "", "degraded": false}
```

The response contains the turn we just sent, which proves the write path works. Note the distinction between this request and the security discussion earlier: the curl here is an operator's debug view, run from inside the cluster boundary with a port-forward, at the same trust level as `kubectl` itself. The fail-closed scope rule applies to the *model channel*: an agent's tool call can never choose its scope, because the runtime derives it server-side from the agent identity. Direct access to the service is governed by the cluster network (NetworkPolicy, and the gateway when enabled), not by the model.

Then open a **completely new session**:

```bash
kaos agent invoke memory-agent -n memory-example \
  -m "What deployment port did I choose earlier?"
```

The automatic recall pulls the earlier turns from the store and injects them before the model runs, so the agent answers from memory it was never handed in this session. One honesty note on reading the output: this walkthrough runs a deterministic mock model so it is reproducible on any laptop, and a mock's reply text does not depend on the injected context, so the functional evidence is always the service state rather than the reply. Recall from the service again and both sessions' turns are there, giving one cross-session memory read and written by both.

### Part 2: Scope Isolation and the Right to Erasure

The `group` scope above shares memory across every agent bound to the store. To see the isolation side, deploy a second agent bound to the *same* store, but with the default `agent` scope, so its memory is private to its own identity:

```yaml
apiVersion: kaos.tools/v1alpha1
kind: Agent
metadata:
  name: private-agent
spec:
  modelAPI: memory-modelapi
  model: gpt-4o-mini
  config:
    instructions: |
      You are a helpful assistant with long-term memory.
    memory:
      type: remote
      memoryStore: shared-memory
      scope: agent
      failureMode: soft
```

Ask it about the port from Part 1:

```bash
kaos agent invoke private-agent -n memory-example \
  -m "What deployment port did I choose earlier?"
```

```
Port-forwarding to agent-private-agent:8000...
Sending message: What deployment port did I choose earlier?

Response:
I don't have any earlier context about a deployment port.
```

Both agents talk to the same service, the same database, and the same tables, however the service filters every operation by the owner key derived from each agent's identity (the operator injects `AGENT_IDENTITY=kaos://agent/memory-example/private-agent`). Checking the private partition against the service shows what isolation actually looks like. The partition is not empty, since the automatic baseline has just persisted the private agent's own question and reply into it, and that is precisely the point: it holds its own conversation and nothing from the group, with no trace of the `8080` fact:

```bash
curl -s http://localhost:18080/v1/recall \
  -H 'content-type: application/json' \
  -d '{"scope": {"level": "agent", "agent_client_id": "kaos://agent/memory-example/private-agent"}, "query": "deployment port", "include_short_term": true}'
```

```json
{"facts": [],
 "short_term": {"recent": [
    ["user", "What deployment port did I choose earlier?"],
    ["assistant", "I don't have any earlier context about a deployment port."]]},
 "medium_term": {"summary": ""}, "block": "", "degraded": false}
```

Erasure is the other side of scoping, and it is one operation. A single `forget` erases everything the scope holds, across all three tiers:

```bash
curl -s http://localhost:18080/v1/forget \
  -H 'content-type: application/json' \
  -d '{"scope": {"level": "group"}}'
```

```json
{"forgotten": true, "degraded": false}
```

Recall the `group` scope again and it comes back empty across every tier, so the next `memory-agent` session starts from nothing:

```json
{"facts": [], "short_term": {"recent": []}, "medium_term": {"summary": ""}, "block": "", "degraded": false}
```

### Part 3: Unplugging the Memory

The failure contract from the Kubernetes section says a memory outage should degrade an agent and never stop it, and this is directly testable: delete the store out from under a running agent.

```bash
kubectl delete memorystore shared-memory -n memory-example
kaos agent invoke memory-agent -n memory-example -m "Are you still there?"
```

The invocation succeeds and the agent replies normally, with no memory backing it. Instead of an outage, the operator surfaces the state as a condition:

```bash
kubectl get agent memory-agent -n memory-example \
  -o jsonpath='{.status.conditions[?(@.type=="MemoryDegraded")]}'
```

```json
{"lastTransitionTime": "2026-07-17T13:57:32Z",
 "message": "MemoryStore shared-memory not found",
 "reason": "MemoryStoreNotReady", "status": "True", "type": "MemoryDegraded"}
```

Re-apply the `MemoryStore` and wait for it to become ready again:

```bash
kubectl apply -n memory-example -f memorystore.yaml
kubectl wait -n memory-example memorystore/shared-memory \
  --for=jsonpath='{.status.ready}'=true --timeout=180s
```

The agent picks its memory back up on the next turn, with no restarts and no code involved, and the condition clears:

```json
{"lastTransitionTime": "2026-07-17T14:08:37Z",
 "message": "MemoryStore shared-memory is ready",
 "reason": "MemoryHealthy", "status": "False", "type": "MemoryDegraded"}
```

Memory behaving as augmentation is precisely this: the difference between an incident and a status condition. As a closing note on this example, running it end-to-end for this post surfaced a real bug (a race in the CLI's port-forward startup that could silently swallow connection failures), which is its own small lesson: worked examples that actually run are also a test suite for your product.

## How You Can Integrate It In Your Agent From Scratch

As with the autonomous loop, you don't need a framework to understand the minimal shape. Let's first look at the framework-agnostic skeleton of the design from this post, so the load-bearing choices are visible in ~30 lines, and then at the packaged version you can integrate directly. Tiered memory is a wrapper around the agent run:

```python
async def run_with_memory(session_id, user_message, memory, agent):
    # 1. RECALL: assemble the memory block (never let this fail the turn)
    try:
        window = await memory.window(session_id, token_budget=4000)
        digest = await memory.digest(session_id)
        facts = await memory.search(scope=memory.scope, query=user_message, top_k=5)
    except MemoryError:
        window, digest, facts = await memory.window_only(session_id), None, []

    context = build_memory_block(digest, facts)   # structured block, injected once

    # 2. RUN
    response = await agent.run(context, window, user_message)

    # 3. PERSIST: append is cheap and synchronous; distillation is not
    await memory.append(session_id, user_message, response)

    # 4. FOLD + EXTRACT: always off the response path
    if await memory.over_budget(session_id):
        background(memory.fold_and_extract, session_id)

    return response
```

The skeleton shows the load-bearing choices: recall wrapped so failure degrades instead of raising, the digest and facts injected as one structured block instead of fake conversation turns, the cheap verbatim append on the hot path, and the expensive fold-and-extract pushed to the background the moment the token budget trips.

What it deliberately does not show, and what you must add before this becomes a production dependency: server-side scope enforcement, the erasure fan-out across tiers, the soft/strict write contract, OpenTelemetry on every operation, and a service boundary so a fleet shares one memory instead of one process hoarding it.

Alternatively, you can adopt the packaged version of exactly this design: the `kaos-memory` package mentioned in the design section. It is pip-installable and deliberately layered behind extras. The core carries the wire contract and the `MemoryServiceClient`, `[service]` adds Mem0, the vector store, and the FastAPI service, and `[pydantic-ai]` adds the runtime adapters, server-side scope derivation, and the memory toolset:

```bash
pip install kaos-memory                  # wire contract + MemoryServiceClient
pip install "kaos-memory[pydantic-ai]"   # + runtime adapters and the memory toolset
```

The part of the package I would call genuinely novel relative to the ecosystem is that **medium-term memory is a first-class tier**. The two-tier (working plus long-term) split is the industry norm, and the rolling, versioned session summary that keeps continuity across compaction is a concept the surveyed engines do not ship. The package owns the short- and medium-term tiers relationally, wraps Mem0 for the long-term tier, and exposes all three behind the single recall, write, and forget contract used throughout this post.

The core install gives you the `MemoryServiceClient` against a running MemoryStore service:

```python
from kaos_memory import MemoryServiceClient, Scope

client = MemoryServiceClient(endpoint="http://memorystore-shared-memory:8080")
scope = Scope(level="group")

recalled = await client.recall(scope, query=user_message, include_short_term=True)
response = await agent.run(recalled, user_message)
await client.write(scope, turns=[("user", user_message), ("assistant", response)])
```

Recall degrades to empty context on failure instead of raising, writes honour the soft or strict failure mode, and every call emits the `kaos.memory.*` telemetry spans covered in the observability post.

If your agent runs on Pydantic AI, the `[pydantic-ai]` extra adds the helpers that wire the pieces from this post together: server-side scope derivation, the explicit memory tools, and full-fidelity history replay.

```python
from kaos_memory.pydantic_ai import (
    scope_from_deps, build_memory_toolset, reconstruct_message_history,
)
from kaos_memory.pydantic_ai.toolset import MemoryTools

# derive the scope from the authenticated request context; by design
# there is no way for the model or a tool to pass a scope in
scope = scope_from_deps(deps, level="group", agent_identity=agent_identity)

# expose save_memory / search_memory to the model (the tools carry no scope argument)
toolset = build_memory_toolset(MemoryTools.ALL, scope.level, agent_identity)

# rebuild message history from the short-term turns plus the rolling summary,
# so overflow is represented by summarization instead of truncation
history = reconstruct_message_history(recalled.short_term.recent, recalled.medium_term.summary)

result = await agent.run(user_message, message_history=history, toolsets=[toolset])
```

## When NOT to Add Long-Term Memory

Like autonomy, memory has become a checkbox feature, and the temptation is to switch it on for everything. It has a measurable break-even, as [a 2026 cost-performance analysis](https://arxiv.org/abs/2603.04814) finds long-context actually wins on raw recall for short interactions, with fact-based memory becoming cost-favorable only after roughly ten turns at 100K-token scale. Long-term memory earns its cost when:

- users or goals persist across sessions and personalization compounds,
- a fleet of agents benefits from shared operational knowledge,
- agents run [always-on autonomous loops](https://hackernoon.com/), the biggest memory producers and consumers, since nobody is there to repeat the context to them,
- the same facts keep being re-established at the start of every session.

It is a poor fit when:

- interactions are genuinely single-shot, where session history already covers it,
- you cannot yet answer the erasure question, since memory without deletion is a liability and not a feature,
- tenancy boundaries are unclear, where every memory becomes a potential leak vector,
- you cannot afford the extraction cost of additional LLM calls for every remembered conversation,
- an outage of the memory path would be treated as an outage of the agent, in which case memory has become a hard dependency and the design should be revisited before scaling.

One caution applies even when memory *is* the right call, which is that remembering and staying current are different problems. The newest agentic-memory evaluations find a distinctive failure mode where agents treat stale prior-session state as if it were still true instead of re-checking it ([Momento](https://arxiv.org/abs/2606.00832)), meaning a recalled fact is a hypothesis about the present state that may require re-validation.

## Lessons for Production Agentic Memory

Here are the patterns I would carry into any agentic memory system.

### 1. Memory is augmentation

Design the outage path first, so that recall degrades to the short-term window, writes retry in the background, and a memory outage never takes a serving agent down.

### 2. Separate conversational continuity from learned knowledge

Same-session verbatim windows and cross-session distilled facts are different tiers with different stores, lifecycles, and failure modes. Conflating them is the root of most memory design mistakes.

### 3. Raw turns are the source of truth and everything else is a projection

Digests, facts, and embeddings are lossy, recomputable views. Keep the verbatim record durable and you can survive both a lost extraction and a change of mind about your extraction strategy.

### 4. Keep narrative digests out of the vector store

Extraction engines shred input into atomic facts, whereas a rolling summary's value is its continuity. Store digests relationally, inject them whole, and feed the engine raw turns only.

### 5. Never let the model choose the scope, and never let recall become policy

Derive scope server-side from authenticated identity, fail closed, with the filter inside the vector query. Treat what comes back as untrusted data with provenance, since memory poisoning and cross-session injection are demonstrated attacks with published success rates.

### 6. The store is the group

Sharing topology can be a deployment choice instead of an authorization system, with scope filtering within a store and physical isolation by deploying a store per tenant.

### 7. Keep extraction off the hot path

The user is already waiting on one LLM call, so never make them wait on the memory system's LLM too. Append synchronously and distil in the background.

### 8. Adopt the engine and own the contract

Wrap the memory engine behind your own interface, and adopt it for the right reason, which is latency and token cost at scale, since raw accuracy can actually favour full-context baselines. Every gap in the engine you select becomes your integration layer, so choose the gaps you know how to fill.

### 9. Budget memory in tokens

The context window is the real constraint and turns vary wildly in size, which makes turn counts a poor proxy. Token budgets belong to the same family of safety controls as the iteration and cost budgets from the autonomous post.

### 10. Build erasure before you need it

"Forget everything about this user" must be one operation that fans out across every tier and every derived projection, and it is a different operation from temporal supersession, which preserves history. Retrofitting either across a live system is far harder than designing them in.

## Closing Thoughts: Making Memory Boring

In the observability post I argued the goal is *boring debugging*, and in the autonomy post that the loop is easy while the operating model is the work. Memory completes the trilogy, and the shape of the lesson is the same.

The extraction models and retrieval tricks will keep improving underneath you, and the research is still openly arguing about where memory systems lose information. What makes agent memory production-grade is instead the tiered structure, the durable source of truth, the non-spoofable scopes, the degradation contract, the background write path, and the one-shot erasure.

If your memory system is boring (a store outage is a degraded condition instead of an incident, "whose memory is this?" has a structural answer, and deletion is one operation) then your agents get to be the interesting part.

