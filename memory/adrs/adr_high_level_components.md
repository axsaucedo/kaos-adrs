# KAOS memory ADRs — high-level components

This document opens the architecture-decision phase for KAOS memory. The research stages ([KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md) through [KAOS-R7](../research/KAOS-R7-target-picture.md)) established the current implementation and its gaps, the ecosystem, the tooling landscape, a selection, and an unrestricted target picture. The target picture describes the components and conceptual memory lanes at a high level; this document decomposes that picture into the **high-level components that each require an architecture decision record (ADR)**, so the design work can proceed component by component.

The intent here is deliberately *coarse*. The components below are bundled rather than finely segregated: each one groups a set of closely-coupled decisions that are best made together, so the ADR set stays small and coherent instead of fragmenting into many narrow records. Each component listed will become one ADR (occasionally a small number, if a decision later proves too large to bundle), and this document is the index that anchors them.

## How this relates to the research

The components are derived directly from the target picture in [KAOS-R7](../research/KAOS-R7-target-picture.md), grounded in the requirements baseline [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md) and the ecosystem vocabulary [KAOS-R2](../research/KAOS-R2-memory-ecosystem-research.md), and constrained by the selection in [KAOS-R6](../research/KAOS-R6-tool-selection.md). Where an ADR weighs an option, the per-tool deep dives ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md) through [KAOS-R5-5](../research/KAOS-R5-5-redis-agent-memory-server.md)) are the evidence base. ADRs decide; they do not re-litigate the research. Each ADR records what was chosen, why, and the consequences, citing the research rather than repeating it.

The research remit was *informed but not constrained* by the available tooling. The ADRs are the opposite: they are where the unrestricted target is reconciled with what is buildable and adoptable now, producing concrete, committed decisions with a status lifecycle.

## Components requiring an ADR

The six components below cover the full target surface. They are ordered by dependency: earlier components establish contracts that later ones build on. Cross-cutting concerns that belong to no single component are listed separately afterwards.

### 1. Memory interface and runtime data plane

- **Scope.** The `Memory` abstraction in the Pydantic AI runtime and its extension from today's working-memory-only contract into a two-layer interface (working memory plus a long-term sub-interface for write/extract, search/recall, consolidate, forget). Includes the recall and write hooks around an agent run, the strategy for injecting recalled context (a structured memory block versus tools), the Pydantic AI message-history bridge and its fidelity fixes (replaying tool calls, summarizing rather than truncating), and the point at which tenant scope is injected. Source surfaces: `pydantic-ai-server/pais/memory.py`, `pydantic-ai-server/pais/server.py` (`_create_memory`), `pydantic-ai-server/pais/serverutils.py`.
- **Key decisions.** Whether working and long-term memory are one interface or two composed interfaces; the long-term sub-interface method set and its synchronous-versus-asynchronous shape; how recalled context is presented to the agent; how the existing backends and `MEMORY_*` configuration remain backward-compatible; where the OpenTelemetry boundary sits.
- **Primary inputs.** [KAOS-R7](../research/KAOS-R7-target-picture.md) data plane; [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md) current interface; [KAOS-R5-5](../research/KAOS-R5-5-redis-agent-memory-server.md) two-tier model.
- **Dependencies.** Foundational. Most other components depend on this contract.

### 2. Memory model and lifecycle operations

- **Scope.** The conceptual memory lanes and the operations over them: the target taxonomy (working, episodic, semantic, profile, relational/temporal, procedural) and which tiers are committed and in what order; the common metadata envelope every item carries (id, scope, event/ingestion time, provenance, importance, access stats, retention/pin policy, trace linkage); the retrieval scoring model (hybrid recall scored by relevance, importance, and recency with decay); consolidation/reflection; and forgetting/retention policy semantics.
- **Key decisions.** Which tiers are in scope versus deferred, and their sequence; the metadata-envelope schema that keeps tiers interoperable and the engine swappable; the retrieval scoring formula and its configurability; the consolidation trigger and schedule model; the forgetting primitives (decay, pinning, non-lossy temporal invalidation, hard erasure) and how they are expressed as policy.
- **Primary inputs.** [KAOS-R7](../research/KAOS-R7-target-picture.md) memory model and retrieval/consolidation/forgetting; [KAOS-R2](../research/KAOS-R2-memory-ecosystem-research.md) taxonomy; [KAOS-R5-2](../research/KAOS-R5-2-zep-graphiti.md) temporal model; [KAOS-R5-4](../research/KAOS-R5-4-memobase.md) profiles.
- **Dependencies.** Builds on component 1; constrains component 3 (the engine must support the chosen operations) and component 5 (policy fields on the CRD).

### 3. Long-term engine integration and selection

- **Scope.** The build-versus-adopt boundary and the adapter contract that maps the long-term sub-interface onto a concrete engine; confirmation and framing of the selected engines (Mem0 as primary, the Redis Agent Memory Server as secondary) and how a backend is swapped; where embedding and extraction models bind (references to KAOS `ModelAPI` resources); and where KAOS must supplement engine gaps (OpenTelemetry instrumentation, scope and tenancy enforcement).
- **Key decisions.** Confirming Mem0 as primary against the engine-adapter contract; the contract that lets multiple engines coexist behind one interface; how model references flow into the engine; the explicit list of capabilities KAOS wraps around the engine rather than inheriting from it.
- **Primary inputs.** [KAOS-R6](../research/KAOS-R6-tool-selection.md) selection; [KAOS-R5-1](../research/KAOS-R5-1-mem0.md) Mem0; [KAOS-R5-5](../research/KAOS-R5-5-redis-agent-memory-server.md) Redis AMS; [KAOS-R7](../research/KAOS-R7-target-picture.md) design principles and the capabilities-no-tool-provides section.
- **Dependencies.** Depends on components 1 and 2; constrains components 4 and 5.

### 4. Deployment topology and execution model

- **Scope.** How the long-term engine is run and how its work is scheduled: central shared service versus embedded library, and the default for a multi-tenant fleet; the split between the synchronous, low-latency recall hot path and background extraction/consolidation; the background job system (queue and workers); high availability, resilience, and blast-radius handling (timeouts, circuit breaking, graceful degradation to working memory, caching, replicas and disruption budgets); and the engineering needed to make a stateful engine server horizontally scalable.
- **Key decisions.** The default topology and when the embedded alternative applies; the background execution mechanism (reuse of the existing Redis-backed queue versus a dedicated worker workload); the degradation contract when memory is unavailable; how the Mem0 server's singleton instance and per-container history store are made HA-safe ([KAOS-R5-1](../research/KAOS-R5-1-mem0.md)); per-tenant rate and quota enforcement on the shared service.
- **Primary inputs.** [KAOS-R7](../research/KAOS-R7-target-picture.md) deployment-topology and storage/distribution sections; [KAOS-R5-1](../research/KAOS-R5-1-mem0.md) statefulness caveats; [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md) autonomous-loop event volume.
- **Dependencies.** Depends on components 1 and 3; informs the workloads the operator manages in component 5.

### 5. Control plane: MemoryStore CRD, operator, and datastore binding

- **Scope.** The new `MemoryStore` (or similarly named) CRD describing a long-term backend by capability and policy, and the slim memory block the Agent CRD retains to select a store and set per-agent scope and budget; the operator's reconciliation responsibilities (deploying the memory-service and worker workloads, wiring credentials as secrets, scheduling consolidation/forgetting jobs, exposing health and metrics, validating model references); datastore binding via connection and secret references rather than lifecycle ownership; polyglot store selection per tier; and ownership of schema versioning and migration. Source surfaces: `operator/api/v1alpha1/agent_types.go`, `operator/controllers/agent_controller.go`.
- **Key decisions.** The CRD schema and its capability-versus-vendor framing; the relationship between the Agent CRD and the `MemoryStore`; precisely what the operator deploys versus binds (reaffirming that underlying databases are externally operated, bring-your-own dependencies); the mapping of storage tiers to concrete stores (vector, optional graph, relational, Redis); and where schema migration and versioning live.
- **Primary inputs.** [KAOS-R7](../research/KAOS-R7-target-picture.md) control-plane and storage/distribution sections; [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md) current control plane; [KAOS-R6](../research/KAOS-R6-tool-selection.md) engine-agnostic direction.
- **Dependencies.** Depends on components 3 and 4; pairs with component 6 for the governance fields it carries.

### 6. Multi-tenancy, security, and governance

- **Scope.** Isolation and governance as first-class properties: the scope hierarchy (session, user, agent, tenant/organization); the isolation modes spanning shared-store-with-scope-filtering through store-per-tenant; authentication and authorization on the always-on `/memory/*` endpoints; and the governance feature set — encryption at rest, per-tenant quotas, audit logging, export/import and backup, schema migration, and right-to-erasure deletion.
- **Key decisions.** The enforced isolation model and how scope filtering is made non-optional at the data layer; the authentication mechanism for memory endpoints; which governance features are core versus deferred; and how erasure and export propagate across tiers and through the underlying engine.
- **Primary inputs.** [KAOS-R7](../research/KAOS-R7-target-picture.md) multi-tenancy and governance sections; [KAOS-R1](../research/KAOS-R1-memory-features-and-limitations.md) governance gaps; the isolation findings across [KAOS-R5-1](../research/KAOS-R5-1-mem0.md) through [KAOS-R5-5](../research/KAOS-R5-5-redis-agent-memory-server.md).
- **Dependencies.** Cross-cuts components 1, 2, and 5; depends on the scope model defined in component 1.

## Cross-cutting concerns

These are not separate components; each ADR addresses them within its own scope rather than deferring them to a single record.

- **Observability.** OpenTelemetry instrumentation of every memory operation, emitted by KAOS regardless of the engine's native observability maturity ([KAOS-R7](../research/KAOS-R7-target-picture.md) observability section). The interface ADR fixes the instrumentation boundary; each subsequent ADR states the spans and metrics its surface emits. If this grows beyond a cross-cutting concern it may be promoted to its own ADR.
- **Backward compatibility and migration.** Every decision keeps existing agents working unchanged and treats the long-term tier as additive, per the migration direction in [KAOS-R7](../research/KAOS-R7-target-picture.md). Each ADR states its compatibility impact.
- **Security defaults.** Secret-based credentials, no operator-wide datastore default, and least-privilege scope are assumed by every component, not only component 6.

## Dependency and sequencing

The components form a dependency chain rather than a flat list. Component 1 (the interface) is the foundation; component 2 (the model and operations) defines what the interface must carry; component 3 (engine integration) chooses what implements it; component 4 (topology and execution) decides how it runs; component 5 (control plane) makes it declarative and operable; and component 6 (multi-tenancy and governance) cross-cuts the data and control planes. A reasonable authoring order is 1, then 2 and 3, then 4, then 5, then 6 — with the cross-cutting concerns settled inside each.

## ADR conventions

- **Filename.** ADRs use `adr_NNNN_<slug>.md` with a zero-padded sequence number and a short kebab-case slug (for example `adr_0001_memory-interface-and-data-plane.md`). This index uses the descriptive name `adr_high_level_components.md` and is not itself a numbered decision.
- **Numbering.** Numbers are assigned in authoring order and are provisional until an ADR is written; additional ADRs may slot in as decisions are split out. The numbering reflects the order decisions are recorded, not a strict mapping to the six components.
- **Status lifecycle.** Each ADR carries a status: `Proposed`, `Accepted`, `Superseded` (by a named later ADR), or `Deprecated`. Superseding never edits the original record; it adds a new one and updates the status.
- **Structure.** Each ADR follows a consistent shape: title and status; context (the problem and the relevant research, cited); the decision; consequences (positive, negative, and follow-on work); and alternatives considered with the reason each was not chosen. References link back to the research documents rather than restating them.
- **Authoring style.** ADRs follow the repository [CONVENTIONS](../CONVENTIONS.md): single-line paragraphs and list items, Markdown links for cross-references, repository-relative paths for KAOS source, and no references to phases, tasks, or plan steps in the document body.
