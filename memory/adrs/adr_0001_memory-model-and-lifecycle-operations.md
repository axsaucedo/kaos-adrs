# ADR 0001 — Memory model and lifecycle operations

- **Status.** Proposed
- **Date.** 2026-06-29
- **Component.** 1 of 5 ([adr_high_level_components](./adr_high_level_components.md))
- **Depends on.** [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md), [KAOS-R2](../research/KAOS-R2-memory-ecosystem-research.md), [KAOS-R7](../research/KAOS-R7-target-picture.md), [KAOS-R8](../research/KAOS-R8-production-memory-adoption-in-frameworks.md), [KAOS-R9](../research/KAOS-R9-procedural-temporal-memory-in-agent-systems.md)
- **Defers to.** ADR 0002 (memory implementation: engine selection and tier coverage) for every choice this record marks as engine-dependent.

## Context

KAOS today exposes a single working-memory tier through the `Memory` abstraction (Local, Redis, Null backends), bounded to the live per-run message history bridged into Pydantic AI. There is no long-term tier, no scope dimension beyond a session/user key, and no consolidation, retrieval scoring, or forgetting. The target picture ([KAOS-R7](../research/KAOS-R7-target-picture.md)) calls for an engine-agnostic memory model with multiple conceptual lanes, hierarchical scoping, and lifecycle operations, with the implementing engine chosen separately so the model stays durable while engines remain swappable.

This ADR settles only the conceptual memory model and the lifecycle operations over it: the taxonomy and which tiers are committed, the metadata envelope, the scope-addressing structure including A2A delegation propagation, and the semantics of retrieval, consolidation, and forgetting. It does not pick an engine, a topology, or a CRD; those are later records. Many parameters here are deliberately left as policy with sensible defaults, because their precise behaviour depends on the engine chosen in ADR 0002.

## Decision

### Memory tiers (capability-tiered, not all-at-once)

Working memory is committed unconditionally: it is table stakes, owned by KAOS and Pydantic AI as the live per-run message-history bridge, and is never delegated to an external engine regardless of later choices. Semantic and episodic memory together form the committed long-term core, matching the production norm of collapsing them into one store while keeping them distinguishable in metadata ([KAOS-R8](../research/KAOS-R8-production-memory-adoption-in-frameworks.md), [KAOS-R9](../research/KAOS-R9-procedural-temporal-memory-in-agent-systems.md)). Temporal (bi-temporal validity) and procedural (skills) are deferred as later capability tiers: temporal is delivered rigorously only by Graphiti-class engines and procedural is coding-agent-centric and the least standardised, so both depend on the engine decision in ADR 0002. Even where an engine logs validity intervals, recall must remain available through vector and text search so questions of the form "who was president in 2002" resolve without a dedicated temporal query API. <!-- PLACEHOLDER: final tier set and temporal/procedural commitment revisited once ADR 0002 fixes engine capabilities -->

### Scope-addressing structure (hybrid hierarchical path)

Scope is a hierarchical, segmented path with prefix-sharing: a small set of canonical roots (tenant, user, agent, session) plus a deployment-defined segmented path, where two scopes sharing a prefix share memory above the divergence point and are isolated below it. The path anchors to stable, verifiable identities rather than ephemeral keys — the user principal and the agent's AIB `client_id` — so memory persists across redeploys and stays auditable; a per-deployment UUID is insufficient because it orphans memory on restart and is not verifiable across agents. <!-- PLACEHOLDER: canonical root set and segment grammar revisited with ADR 0002 -->

### A2A delegation propagation

Today an agent delegating to another passes its full session working memory and nothing else. The model extends this so the delegate inherits a configurable scope prefix by default — shared above, isolated below — making cross-agent sharing follow the same prefix semantics as static scopes. <!-- PLACEHOLDER: practical sketch of B's scope on delegation, and the binding to RemoteAgent/DelegationToolset, finalised in component 5 once ADR 0002 fixes the engine -->

### Metadata envelope (universal core, per-tier extensions)

Every item carries a universal core envelope — id, scope path, event and ingestion time, provenance, importance, access stats, retention/pin policy, trace linkage, identity anchors (principal, agent `client_id`) — plus optional per-tier extension fields. No multimodality at this stage; the envelope assumes text. Conflict resolution, importance scoring, and aliasing are engine-dependent and deferred to ADR 0002.

### Retrieval, consolidation, forgetting

Retrieval is configurable weighted relevance with importance and recency decay, with a reranker option, defaulted to fixed sensible values; consolidation is hybrid threshold/event-driven plus periodic, always background; forgetting offers decay, importance threshold, pinning, non-lossy temporal invalidation, and hard erasure as declarative policy. All three are heavily engine-shaped. <!-- PLACEHOLDER: scoring, consolidation, and forgetting semantics confirmed against ADR 0002 engine capabilities -->

### Working-tier bound

Token-budget with progressive summarization rather than turn-count eviction, subject to ADR 0002. <!-- PLACEHOLDER -->

## Consequences

Positive: a durable, engine-agnostic model that commits the high-certainty tiers now and isolates engine-dependent detail behind explicit placeholders; identity anchored to AIB makes scopes verifiable and survivable. Negative: several behaviours are unresolved pending ADR 0002, so this ADR cannot be marked Accepted until the engine decision lands. Follow-on: ADR 0002 fixes tiers, retrieval, consolidation, forgetting, conflict resolution; component 5 finalises grouping and A2A binding.

## Alternatives considered

Commit all five tiers immediately — rejected: temporal and procedural depend on engine capabilities not yet chosen. Discrete fixed scope levels only — rejected for the hybrid path's flexibility. Random UUID scope keys — rejected: not stable or verifiable across redeploys and A2A.
