# KAOS-R6 — Final selection

This document makes the final selection for KAOS production-grade memory. It defines explicit selection criteria derived from the KAOS requirements baseline in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the ecosystem best practice in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md), scores the five shortlisted candidates from the deep dives ([KAOS-R5-1](./KAOS-R5-1-mem0.md) through [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md)) together with the KAOS-custom baseline, and selects the top options to carry into the target design. The in-scope inputs are listed in the [Context manifest](#context-manifest).

This stage narrows from the five-plus-baseline field of [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md) to a top one-to-two recommendation. The target picture in [KAOS-R7](./KAOS-R7-target-picture.md) is deliberately *not* constrained to the selected tools — it describes the ideal end state, for which the selection here is the most realistic near-term realization.

## Selection criteria

The criteria below are derived directly from the two grounding documents. Each criterion names its origin so the rationale is auditable. They are grouped into capability, fit, and risk, and weighted to reflect what KAOS values most.

### Capability criteria (what the memory layer must do)

- **C1 — Long-term capability coverage.** Semantic/long-term memory, summarization/consolidation, cross-session and per-user memory, knowledge structuring, and principled forgetting. Origin: the entire "Limitations and gaps" section of [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and the capability ladder in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). **Weight: high.**
- **C2 — Retrieval quality.** Relevance-ranked recall blended with importance and recency, ideally hybrid (semantic + keyword + structural). Origin: the canonical `relevance × importance × recency` formula and hybrid/temporal findings in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). **Weight: high.**
- **C3 — Working/long-term tiering fit.** Alignment with KAOS's existing working-memory tier so adoption *adds* a long-term tier rather than replacing the conversation log. Origin: the working-vs-long-term split in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) and the existing per-session log in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md). **Weight: medium.**

### Fit criteria (how well it fits KAOS specifically)

- **C4 — Kubernetes-native deployability.** Self-hostable in a customer cluster, ideally with Helm/operator packaging and clean horizontal scaling. Origin: KAOS is Kubernetes-native and CRD-driven ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) control-plane section). **Weight: high.**
- **C5 — Infrastructure delta.** New datastores/workloads required relative to what KAOS already runs (notably Redis). Origin: the operator-level Redis default and Redis backend in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); the low-infra-delta soft filter in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). **Weight: high.**
- **C6 — Integration fit behind the `Memory` ABC.** A clean library/REST/MCP boundary that drops in behind KAOS's existing pluggable interface on the Pydantic AI data plane. Origin: the `Memory` ABC and Pydantic-AI-is-message-history-only findings in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). **Weight: high.**
- **C7 — Multi-tenancy and isolation.** Per-user/tenant scoping suitable for multi-tenant agent fleets. Origin: the multi-tenancy gaps in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md) and hierarchical scoping in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md). **Weight: high.**
- **C8 — Observability alignment.** OpenTelemetry-native instrumentation matching KAOS's existing trace-context-on-events approach. Origin: OTel trace context on memory events and the observability gap in [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md). **Weight: medium.**
- **C9 — Model-access alignment.** Use of LiteLLM/OpenAI-compatible and Ollama providers consistent with KAOS's ModelAPI proxy. Origin: KAOS ModelAPI (LiteLLM/Ollama) context. **Weight: medium.**

### Risk criteria (what could go wrong)

- **C10 — Licensing and governance.** Permissive license (Apache/MIT) with no distribution-blocking terms or feature-gated essentials. Origin: the licensing hard/soft filters in [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md). **Weight: high.**
- **C11 — Maturity and stability.** Release discipline, API stability, and production-readiness signals versus churn risk. Origin: maturity assessments across the R5 deep dives. **Weight: medium.**
- **C12 — Write-path cost and latency.** The LLM cost and latency of extraction/summarization, and whether it can run off the agent hot path. Origin: the hot-path-vs-background trade-off in [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); KAOS autonomous loops emit many events ([KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)). **Weight: medium.**

## Scoring

Scores are qualitative — **H** (strong), **M** (adequate), **L** (weak) — synthesized from the deep dives, not numeric precision. They express relative fit against each criterion for KAOS specifically.

| Criterion (weight) | Mem0 | Zep/Graphiti | Cognee | Memobase | Redis AMS | KAOS-custom |
| --- | --- | --- | --- | --- | --- | --- |
| C1 Long-term coverage (H) | H | H | H | M | H | L |
| C2 Retrieval quality (H) | H | H | H | M | H | L |
| C3 Tiering fit (M) | M | M | M | M | H | H |
| C4 K8s deployability (H) | M | L | M | M | M | H |
| C5 Infra delta (H) | M | L | L | M | H | H |
| C6 `Memory` ABC fit (H) | H | M | M | M | H | H |
| C7 Multi-tenancy (H) | M | H | H | L | M | L |
| C8 Observability/OTel (M) | L | H | H | H | L | H |
| C9 Model-access fit (M) | H | M | H | H | H | H |
| C10 Licensing (H) | H | H | H | H | H | H |
| C11 Maturity/stability (M) | H | H | M | M | M | M |
| C12 Write cost/latency (M) | M | L | L | H | M | H |

### Reading the scores

- **No candidate dominates.** Each external tool buys long-term capability (C1/C2) that KAOS-custom lacks, but pays somewhere in fit or risk. KAOS-custom inverts this: perfect fit and zero new infrastructure, but it must build every capability.
- **The graph/hybrid leaders (Zep/Graphiti, Cognee)** score highest on capability, multi-tenancy, and observability, but lowest on infrastructure delta, deployability, and write cost — they import a graph database and an LLM-heavy ingestion pipeline.
- **The Redis-native and vector-first options (Redis AMS, Mem0)** score best on integration fit and (for AMS) infrastructure delta, at the cost of weaker observability (neither is OTel-native) and, for AMS, maturity.
- **Memobase** is the cheapest write path and a clean stack, but its weak self-hosted multi-tenancy (C7=L) is a direct conflict with KAOS's multi-tenant model, and its profile-only recall caps capability.

## Per-candidate synthesis

### Mem0 — the mature vector-first default

Mem0 is the "default to beat": the most adopted dedicated layer, Apache-2.0, with pluggable backends (including Redis and pgvector), clean library integration behind the `Memory` ABC, and strong capability. Its weaknesses for KAOS are non-fatal but real: no official Helm chart, PostHog-not-OTel observability, application-level-only tenant isolation, and an actively-changing API. It is the safest capability-rich adoption and the lowest-friction integration of the capable options. See [KAOS-R5-1](./KAOS-R5-1-mem0.md).

### Redis Agent Memory Server — the best architectural and infrastructure fit

AMS is the only candidate whose **two-tier model mirrors KAOS's own** and whose store is **Redis**, the technology KAOS already operates — giving it the smallest conceptual and infrastructure delta, plus LiteLLM model access that matches KAOS's ModelAPI. Its costs are a Redis Stack requirement (over plain Redis), the absence of OpenTelemetry, no Helm chart, and a young project with no tagged releases. See [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md).

### Zep/Graphiti — the capability ceiling, the operational floor

Graphiti is the most capable design — temporal knowledge graph, non-lossy invalidation, richest retrieval, and OTel-native — and is the right reference for the [KAOS-R7](./KAOS-R7-target-picture.md) ceiling. But it is the heaviest to operate (Neo4j/FalkorDB, Enterprise for hard per-tenant isolation), the most expensive to write to, and has no Graphiti-native packaging or Pydantic AI adapter. It is a strong future option once a graph tier is justified, not the lowest-risk first adoption. See [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md).

### Cognee — capable and open, but early and heavy

Cognee matches much of Graphiti's capability with a hybrid model, full Apache-2.0 openness, ACL multi-tenancy, and OTel-native observability — but a heavy dependency footprint, file-based defaults that don't scale, and a Beta, churn-prone API make it a watch-and-revisit rather than a first pick. See [KAOS-R5-3](./KAOS-R5-3-cognee.md).

### Memobase — cheap and clean, but narrow and weakly multi-tenant

Memobase has the best write-cost profile, OTel+Prometheus observability, and a modest Postgres+Redis stack, but its profile-only recall and **weak self-hosted multi-tenancy** disqualify it as a primary for KAOS's multi-tenant fleets. It is a candidate for the profile/user-memory sub-problem, not the whole layer. See [KAOS-R5-4](./KAOS-R5-4-memobase.md).

### KAOS-custom — perfect fit, all capability still to build

The baseline keeps KAOS's clean interface, CRD-native configuration, existing Redis backend, OTel integration, and zero new dependencies — but every long-term capability (retrieval, embeddings, summarization, cross-session/user memory, forgetting) must be built and maintained in-house. See [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md).

## Selection

The selection is a **primary plus a secondary**, with KAOS-custom retained as the integration substrate.

### Retained substrate: the KAOS `Memory` interface

Regardless of which engine is adopted, KAOS keeps and extends its own `Memory` ABC, CRD configuration, and working-memory tier. [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md) establishes that Pydantic AI provides message history only, so KAOS owns the long-term layer either way; the decision is *what backs it*, not *whether KAOS has an interface*. The selected tools are integrated as long-term backends behind that interface, not as replacements for it.

### Primary selection: Mem0

**Mem0 is selected as the primary long-term backend.** It maximizes capability (C1/C2) with the lowest integration friction (C6), a permissive license (C10), the strongest maturity and ecosystem (C11), pluggable backends that let KAOS reuse Redis/pgvector (C5 partly mitigated), and model-access alignment (C9). Its principal gaps — no Helm chart, no OTel, app-level isolation — are addressable by KAOS at the integration layer: KAOS supplies the Kubernetes packaging and CRD wiring it already does for other components, wraps Mem0 to emit KAOS-native OTel spans, and enforces tenant scope in the `Memory` backend (which KAOS must do for any application-level-isolation tool). Running Mem0 in library mode inside the Pydantic AI runtime keeps the deployment footprint minimal.

### Secondary selection: Redis Agent Memory Server

**Redis Agent Memory Server is selected as the secondary/alternative**, preferred where **infrastructure-delta and architectural fit dominate** the decision. Its two-tier model and Redis storage make it the most natural incremental extension of KAOS's existing memory, and its LiteLLM alignment fits the ModelAPI story. It is the recommended choice if a deployment wants to minimize new datastores and is comfortable with the Redis Stack upgrade and the maturity/observability trade-offs; KAOS would again supply OTel instrumentation and Kubernetes packaging.

### Why not the others as primary

Zep/Graphiti and Cognee deliver more capability but at an operational and maturity cost that is disproportionate for a *first* production-grade step; they are explicitly carried forward as the capability reference for [KAOS-R7](./KAOS-R7-target-picture.md) and as future graph-tier options. Memobase's weak self-hosted multi-tenancy rules it out as a primary for KAOS's multi-tenant model, though its profile model informs the user-memory design. KAOS-custom alone is rejected as the primary because rebuilding mature retrieval, extraction, and consolidation in-house duplicates what Mem0/AMS already provide under permissive licenses — but it is retained as the substrate that hosts them.

## Implications for the target picture

[KAOS-R7](./KAOS-R7-target-picture.md) should describe an end state that is **engine-agnostic at the interface** and **tiered by capability**: KAOS's `Memory` interface and CRD surface own working memory and orchestrate a pluggable long-term backend, with Mem0 (or Redis AMS) as the realistic near-term backend and the temporal-knowledge-graph approach (Graphiti) as the capability ceiling for a later graph tier. The target should not be limited to what the selected tools provide today — it should name desirable capabilities (e.g. principled consolidation/forgetting, reflection, hierarchical org-level scoping, native OTel throughout, CRD-driven memory resources) even where no single surveyed tool delivers them.

## Context manifest

In scope (read for this document): the requirements baseline [KAOS-R1](./KAOS-R1-memory-features-and-limitations.md); the ecosystem best practice [KAOS-R2](./KAOS-R2-memory-ecosystem-research.md); the shortlist rationale and first-pass matrix [KAOS-R4](./KAOS-R4-tool-comparison-and-selection.md); and the five per-tool deep dives [KAOS-R5-1](./KAOS-R5-1-mem0.md), [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md), [KAOS-R5-3](./KAOS-R5-3-cognee.md), [KAOS-R5-4](./KAOS-R5-4-memobase.md), [KAOS-R5-5](./KAOS-R5-5-redis-agent-memory-server.md).

Out of scope (intentionally excluded): the broad tooling catalogue ([KAOS-R3](./KAOS-R3-memory-tooling.md)) beyond what the shortlist already distilled, and the unrestricted target design ([KAOS-R7](./KAOS-R7-target-picture.md)) which follows this selection. Scores are qualitative judgments synthesized from the deep dives; vendor benchmark and maturity figures referenced in those dives remain approximate or unverified.
