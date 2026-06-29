# KAOS-R10 — Engine assessment for the memory implementation decision

This document captures the build-versus-adopt assessment and engine comparison that supports the memory-implementation decision ([adr_high_level_components](../adrs/adr_high_level_components.md) component 2, drafted as ADR 0002). It builds directly on the final selection ([KAOS-R6](./KAOS-R6-tool-selection.md)) and the per-tool deep dives, adding three things R6 did not: a separated risk model (licence risk versus open-core/lock-in risk), an implementation-effort estimate from measured library sizes, and a verified survey of Pydantic AI integration paths. It exists because the decision now hinges on which engine KAOS adopts, and that choice needed sharper evidence on lock-in, effort, and integration than the original pipeline carried.

## Build, hybrid, or adopt

Three top-level shapes were weighed against the model committed in [ADR 0001](../adrs/adr_0001_memory-model-and-lifecycle-operations.md) (working owned by KAOS; semantic plus episodic the committed long-term core; temporal and procedural deferred; hybrid scope anchored to verifiable identity).

- **Build custom end-to-end.** Perfect fit and zero new infrastructure, but every long-term capability — retrieval, embeddings, extraction, consolidation, forgetting — is built and maintained in-house, duplicating a solved problem and slowing production.
- **Hybrid: KAOS working tier plus an external long-term engine.** Honours the one firm invariant that KAOS and Pydantic AI own the live message-history bridge, lets development run a local backend and production an engine, and confines adoption to the long-term tier. This is the selected shape.
- **Full end-to-end third party.** Fewest moving parts only if a single engine has a live conversation buffer; among the candidates only Redis AMS does, so "full" is viable only with AMS and otherwise breaks the invariant.

## Separated risk model

Licence risk and lock-in risk are distinct. Licence risk concerns the legal terms of the code that runs; all five candidates are Apache-2.0, so all are low. Open-core/lock-in risk concerns whether the OSS edition is complete enough alone or whether needed features sit behind a paid tier — a product-strategy property independent of the licence.

| Option | Licence risk | Maturity risk | Ops/infra risk | Open-core/lock-in risk |
| --- | --- | --- | --- | --- |
| KAOS-custom | none | medium | none | none |
| Mem0 | low | low | medium | medium — full graph memory, managed HA, governance are Platform-only |
| Redis AMS | low | high (no tagged releases) | low (reuses Redis) | low |
| Zep/Graphiti | low | low | high (Neo4j) | high — hard per-tenant isolation needs Neo4j Enterprise |
| Cognee | low | high (Beta) | high | low |
| Memobase | low | medium | low | medium — multi-tenancy is Cloud-only |

The two highest-delta tools are Mem0 (graph and HA behind SaaS) and Memobase (tenancy Cloud-only); the rest gate nothing KAOS needs.

## Implementation effort and library size

Measured core source (tests and examples excluded) gives a sense of what a from-scratch build replaces: Memobase server ~12k, Redis AMS ~16k, Mem0 ~31k, Graphiti ~37k, Cognee ~120k lines of Python. AMS is the simplest complete two-tier engine; Cognee's tri-store pipeline is an order of magnitude larger and not realistically self-built. KAOS already has the working tier, `Memory` ABC, and Redis, so reaching an AMS-equivalent semantic/episodic tier is on the order of 5–10k lines plus ongoing retrieval tuning — feasible, but it rebuilds maturity (retrieval quality, write-cost control) that Mem0 and AMS already provide under Apache-2.0. Temporal and procedural would add substantially more.

## Pydantic AI integration paths (verified)

None of the five ships a maintained native Pydantic AI adapter: Mem0 has cookbooks only, AMS ships a LangChain tool, and Graphiti's previously assumed integration was disproven in [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md). A GitHub search found only a 7-star demonstration repo (`rjaskonis/pydantic-ai-mem0`), a single-user tutorial wrapper rather than a package. Because Pydantic AI exposes message history only, KAOS owns the bridge regardless and every engine integrates as a hand-written `Memory(ABC)` subclass — so integration cost does not differentiate the engines, and there is a clear opportunity for KAOS's Mem0 backend to be the most robust public integration. Sketch:

```python
class Mem0Memory(Memory):  # KAOS keeps the working tier; this adds long-term
    def __init__(self):
        self.m = AsyncMemory(config=...)  # vector store reachable, models via ModelAPI
    async def add_event(self, session_id, event, *, scope):
        await super().add_event(session_id, event)
        await self.m.add(event.text, user_id=scope.principal, agent_id=scope.client_id)
    async def recall(self, query, *, scope):
        return await self.m.search(query, user_id=scope.principal, agent_id=scope.client_id)
```

Scope maps onto the verifiable identities ADR 0001 anchors to: user principal and the agent's AIB `client_id`. AMS uses the same subclass but can also back the working tier and offers a `/v1/memory/prompt` endpoint returning pre-merged `messages[]`.

## Recommendation

Mem0 as primary, Redis AMS as the pragmatic alternative where infrastructure delta dominates, Graphiti retained as the deferred temporal tier. Mem0 maximises capability and maturity with permissive licensing and clean scope mapping; its only real lock-in is graph memory and managed HA behind the SaaS, neither needed for the committed semantic/episodic core. The custom build is rejected as primary because it rebuilds ~16k lines of solved engine work, and Memobase/Cognee are set aside on tenancy and stability respectively.

## Caveats

Library sizes are point-in-time line counts, indicative of relative scale rather than effort. Open-core boundaries are vendor strategy and may shift. Star counts and integration availability are as of June 2026. Mem0's removal of the external graph store from OSS and its API churn are noted in [KAOS-R5-1](./KAOS-R5-1-mem0.md) and remain the main adoption watch-items.

## Context manifest

In scope: [KAOS-R6](./KAOS-R6-tool-selection.md) selection and the five deep dives [KAOS-R5-1](./KAOS-R5-1-mem0.md) through [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md); the model in [ADR 0001](../adrs/adr_0001_memory-model-and-lifecycle-operations.md); measured library sizes and a GitHub integration search. Out of scope: the broad catalogue and the final ADR 0002 decision, which this informs.
