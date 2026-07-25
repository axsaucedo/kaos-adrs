# Whose Memory Is It? Building Multi-Tenant, Multi-Tier Memory for AI Agents (Part 2)

_This is a 4-part series on how agents remember: building short-, medium- and long-term memory that scales across users, agents, and kubernetes clusters._

---

Two users talk to the same agent, backed by the same memory store. Alice mentions her API keys rotate on Fridays. The next day bob asks the agent what it knows about deployment schedules. Whether alice's fact can appear in that answer is the whole multi-tenancy problem in one exchange, and it is decided by the scope model long before the model sees a prompt.

Recently I spent some time extending the Kubernetes Agent Orchestration System (KAOS) to support multi-tiered memory persistence (aka short-, medium- and long-term memory). Along the way I hit most of the same issues that anyone would whilst building or integrating multi-tiered memory into a multi-tenant system, so I thought it would be useful to compile the learnings, design choices and examples into this series. This second part covers the design core: the three memory tiers and the scope model, drawing on the research across ~30 memory tools and frameworks from Part 1 and on the implementation that now ships as the `MemoryStore` resource in KAOS. The objective throughout the series:

> Let's make the memory layer BORING, so that the agents can continue to be the fun part.

In [Part 1](link-when-published) we surveyed ~30 memory engines, built a working taxonomy, and landed on adopting [Mem0](https://github.com/mem0ai/mem0) as a library behind our own interface, together with the list of gaps (observability, tenant isolation, kubernetes packaging, framework bridging) that become our integration work.

This part is in two halves. The first half designs the **three memory tiers**: a verbatim short-term window bounded by tokens, a medium-term rolling narrative digest, and extracted long-term facts, each with its own store, lifecycle, and injection path. The second half answers the title question with the **scope model**: three concentric read levels (`session`, `agent`, `user`) bound to verified identity, a `maxReadScope` ceiling agreed between agent and store, and enforcement that keeps the model, or a compromised prompt, from widening any of it. The part closes with five lessons on tier and scope design that carry beyond KAOS.

As with my previous posts on [observability for agentic systems](https://hackernoon.com/production-observability-for-multi-agent-ai-with-kaos-otel-signoz) and [autonomous always-on agentic patterns](https://hackernoon.com/autonomous-agentic-systems-a-practical-guide-to-always-on-agents), I use KAOS as the concrete implementation example, but the goal is to provide practical intuition for the primitives (tiers, scopes, folding, degradation), so that it applies whether you use KAOS, Mem0 directly, LangGraph, CrewAI, or a memory layer you wrote yourself.

The series:

* **Part 1: What agent memory is and what to build on.** The taxonomy, the baseline implementations everyone starts with, and the engine landscape from surveying ~30 tools.
* **Part 2 (this post): Tiers and scopes for multi-tenant agents.** The three-tier design and the answer to whose memory it is.
* **Part 3: Memory as infrastructure.** The Kubernetes `MemoryStore` resource, its deployment topology, and how to integrate it in your own agent (coming soon...).
* **Part 4: Agent memory in action.** A worked example that runs end to end on a secured cluster, with real outputs (coming soon...).

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

The write path is where the answer starts. A single conversation is authored by an agent, on behalf of a user, inside a session, on one store, so the service records all of that attribution on every stored record as provenance. Writes are therefore compound and invariant, while a read resolves to a single scope level and is a matter of policy. That separation is what lets one write be recalled at several levels later without being duplicated, because the same fact an agent stored for Alice carries her `user_id`, the agent identity, and the session at once, so recalls at different levels each find it through a different owner key.

```mermaid
graph LR
  W["one stored fact<br/>agent_id + user_id + session_id"]
  W -->|"session read"| S["found: same conversation"]
  W -->|"agent read"| A["found: same agent x alice"]
  W -->|"user read"| U["found: alice on any agent"]
```

For reads, KAOS uses three concentric levels, where each wider level contains the previous one:

```mermaid
graph LR
  subgraph user["user: the verified user across all agents"]
    subgraph agent["agent: this agent x this user"]
      session["session: the current conversation"]
    end
  end
  store["store: whole-store view<br/>(operators only, part 4)"]
```

The level chooses the radius of the view; the identity always comes from the gateway-verified request headers, never from the request body or the model. This gives each level one documented meaning under each security posture:

| Level     | Meaning                                            | With user auth on             | With user auth off             |
| --------- | -------------------------------------------------- | ----------------------------- | ------------------------------ |
| `session` | the current conversation                           | current agent x user x session | current agent x session       |
| `agent`   | this agent's memory of the verified context        | current agent x user          | this agent's whole pool        |
| `user`    | the verified user across all agents on the store   | current user, across agents   | rejected at deploy time        |

Two properties of this table are worth pausing on. First, every level is principal-bound: `agent` narrows to a two-key `{agent_id, user_id}` partition whenever a verified principal is present, so Alice and Bob get separate memory on the same agent with no per-agent configuration, and it widens to the agent's whole pool only when there is no user identity to bind to. Second, even `session` reads check the principal: a request that presents a session id together with the wrong identity gets an empty result, so knowing a session id is never enough to read a conversation.

One more view exists, and it is deliberately absent from the table. The whole-store view (`store`: everything every agent and user wrote to the store) is for operators: inspection and erasure across the entire store. The memory service refuses it on any request arriving through an agent, so no grant, tool, or prompt can reach it; the only path to it is the cluster-operator one that Kubernetes RBAC already gates. A terminology note that saved us real confusion: identity groups (the `groups` claim in a token, used for authorization grants) and the memory store are different things, which is why the whole-store scope is named `store` and never "group".

```mermaid
graph LR
  M["model / prompt"] --> G["gateway + agent identity"] -->|"store level: refused"| SVC["memory service"]
  OP["operator (kubectl port-forward,<br/>gated by RBAC)"] -->|"store level: allowed"| SVC
```

Because the read levels are totally ordered, an agent's entitlement does not need to be a list of allowed levels; it collapses to a single maximum, `maxReadScope`. The automatic baseline recall runs at that effective ceiling, and the `search_memory` tool's `level` enum becomes every level up to and including it, so an unentitled level is not something the model can even express, which is the fail-closed rule from earlier applied to the read path. The `MemoryStore` carries its own `maxReadScope` ceiling (default `agent`), and an agent may not claim above its store's, so cross-agent `user` reads exist only where the store owner deliberately raised the ceiling.

```mermaid
graph LR
  MS["MemoryStore<br/>maxReadScope: user"] --> A["Agent<br/>maxReadScope: agent<br/>(must not exceed store)"]
  A --> T["search_memory level enum:<br/>[session, agent]"]
  A --> R["automatic recall at: agent"]
```

Who must be identified is not something an agent declares; it follows from the cluster's security posture. When the cluster runs user authentication, every write must carry a verified principal, and the store rejects one that arrives without it; when agent authentication is on, a stable agent identity is required the same way. Agents can neither opt out of these requirements nor demand more than the cluster provides, which removes a whole class of misconfiguration: an agent claiming `maxReadScope: user` on a cluster with no user identity is rejected at its own deploy time instead of failing at runtime. The rejection lives on the reader only, since a store's ceiling grants permission and performs no reads, so a store declaring `user` on such a cluster stays healthy and its ceiling simply remains unclaimed. Autonomous agents need no exception, because a self-initiated iteration runs with the agent's own identity as its principal, satisfying the same requirements uniformly, so a loop's memory stays private to the loop.

This scope model is probably the obvious choice; the trickier question is how do we enable the sharing boundary itself. There were a few design options for this:

1. **Many groups inside one MemoryStore.** One store holds the memories of several groups at once. This sounds efficient, however it means building and operating a whole group-management layer: an API to create and delete groups and to add and remove members, per-group quotas, and a single store whose failure affects every group in it. The storage side of this is actually straightforward, as a group key on every record is all the data layer needs. The real cost is the management surface around it.
2. **One group per MemoryStore.** The store itself is the group: whichever agents are bound to the same store share it, so membership is just the existing binding and no new API is needed. The cost is that every group needs its own store deployment, and sharing across two groups means binding to a second store. 
3. **Hierarchical scope paths.** A richer model where scopes are nested paths (for example `org:team:agent`) and agents share memory up to the point where their paths diverge. Every version of this I drafted ended up re-creating an authorization system that the two simpler options already covered.

Interestingly enough, when looking at how the managed platforms handle this, they expose a two-level version of the same tradeoff. Each one has a hard container that their control plane creates and manages, and lighter logical partitions inside it. A few examples:
* [Mem0 platform](https://docs.mem0.ai/platform/platform-vs-oss): A project is the container that memories cannot cross, and the user and agent partitions live within it, with API keys scoped to the project.
* [Vertex Memory Bank](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview): Provisions one Memory Bank per Agent Engine instance, and within it memories are partitioned by scope, with retrieval only returning memories whose scope exactly matches the request.
* [Zep Cloud](https://www.getzep.com/platform/graphiti/): Each subject (a user, or a group via their group-graph API) gets its own isolated context graph, and the cloud platform is the control plane that manages millions of them.

Based on these tradeoffs, I went for one group per MemoryStore, which enforces this at the control plane: the store itself is the sharing boundary, which is exactly why the whole-store read scope is named `store`. This meant that I don't have to build a full intra-store group management layer, and the data layer simply records the store's group key as internal metadata on each record. 

The way it's designed to is set up to support finer grouping at the `MemoryStore` level by design, as we basically are storing everything under one global group per store.

Now that we adopted these design choices, we realised that there were a few caveats that came up, which we had to accept / address:

* **Security Attack Surfaces**: Interesting research such as [AgentPoison](https://arxiv.org/abs/2407.12784)  show the impact of poisoning memory (ie 0.1% poisoned memory yields over 80% attack success), as well as [MINJA](https://arxiv.org/abs/2503.03704) which shows that an attacker needs no write access at all, because if the agent writes its own memory from conversations then every user is a write path. **To mitigate this**, KAOS  derives the scope server-side from the authenticated agent identity, fail-closed, and never from model- or tool-supplied arguments.
* **Right to Erasure**: Compliance requirements such as GDPR mean you must be able to answer "delete everything you know about this user" reliably, and in a multi-tier design the same information lives in several derived forms at once (raw turns, summaries, extracted facts, and their embeddings), so deleting from one tier is not enough. **To mitigate this**, KAOS implements `forget` as a single operation that fans out across all three tiers in one pass, deleting the short-term rows, the summaries, and the scope-filtered long-term facts. Note this is destruction, which is different from supersession, where facts are merely marked invalid but kept for history.

Now that we have sorted the tiers and the access scopes, let's distil the lessons from this part before we make it all run as infrastructure in part 3.

## Lessons for Production Agentic Memory

Here are the patterns from this part that I would carry into any agentic memory system.

### 1. Separate conversational continuity from learned knowledge

Same-session verbatim windows and cross-session distilled facts are different tiers with different stores, lifecycles, and failure modes. Conflating them is the root of most memory design mistakes.

### 2. Raw turns are the source of truth and everything else is a projection

Digests, facts, and embeddings are lossy, recomputable views. Keep the verbatim record durable and you can survive both a lost extraction and a change of mind about your extraction strategy.

### 3. Keep narrative digests out of the vector store

Extraction engines shred input into atomic facts, whereas a rolling summary's value is its continuity. Store digests relationally, inject them whole, and feed the engine raw turns only.

### 4. Never let the model choose the scope, and never let recall become policy

Derive scope server-side from authenticated identity, fail closed, with the filter inside the vector query. When the model is allowed to search, bound the levels it can reach with a `maxReadScope` ceiling rendered as the tool's own enum, so an injection cannot widen the reach beyond what the agent was granted. Treat what comes back as untrusted data with provenance, since memory poisoning and cross-session injection are demonstrated attacks with published success rates.

### 5. The store is the group

Sharing topology can be a deployment choice instead of an authorization system, with scope filtering within a store and physical isolation by deploying a store per tenant.

## Closing Thoughts for Part 2

This part turned the engine decision from Part 1 into a memory model: three tiers with distinct lifecycles and stores, and a scope model that derives the answer to "whose memory is it?" from verified identity rather than from anything the model says. Together they are the conceptual core of the series.

A model on paper is not a system. In part 3 we make this design exist as infrastructure: the `MemoryStore` kubernetes resource, the topology decision behind it, the degradation contract that keeps a memory outage from taking an agent down, and how you can integrate the same pattern in your own agent from scratch. Stay tuned.

**The series:**

* **Part 1: What agent memory is and what to build on.** The taxonomy, the baseline implementations everyone starts with, and the engine landscape from surveying ~30 tools.
* **Part 2 (this post): Tiers and scopes for multi-tenant agents.** The three-tier design and the answer to whose memory it is.
* **Part 3: Memory as infrastructure.** The Kubernetes `MemoryStore` resource, its deployment topology, and how to integrate it in your own agent (coming soon...).
* **Part 4: Agent memory in action.** A worked example that runs end to end on a secured cluster, with real outputs (coming soon...).
