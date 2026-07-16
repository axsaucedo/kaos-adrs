# KAOS Memory Blog Post — "Agentic Memory at Scale"

Working folder for the third KAOS blog post, covering the learnings from designing and integrating memory into KAOS. Companion to the two published posts:

1. **Monitoring Agentic Systems** — `otel-blogpost/kaos-agentic-observability-otel.md` (final)
2. **Autonomous "Always-On" Agentic Patterns** — `kaos-autonomous-blog/BLOGPOST_COMPLETE_V3.md` (final)

## Files in this folder

| File | Purpose |
|---|---|
| `README.md` | This index: source material, approach, and process notes for later iterations |
| `BLOG-ANALYSIS.md` | Breakdown of the two published posts into outlines, the shared style contract, and improvement opportunities |
| `OUTLINE_PROPOSED.md` | The proposed outline for this post (approved before drafting) |
| `BLOGPOST_DRAFT_1.md` | First full draft against the approved outline (mermaid diagrams in place of UI screenshots) |
| `BLOGPOST_DRAFT_2.md` | Second draft: v2 citation set woven in (~16 verified sources) + content adoptions (honest accuracy framing, source-of-truth/projections rule, memory-poisoning threat grounding, supersession≠erasure, break-even heuristic) — current canonical draft |
| `STYLE_REVISION_PLAN.md` | Style rules (neutral academic register, no em-dashes, no LLM-formulaic constructions, personable-touch budget) and the audited change outline for draft 3 |
| `REFERENCES_PROPOSED.md` | Citation proposal (v2 consolidated) mapped to draft sections, plus superseded v1/external-report assessments |
| `RESEARCH_SOURCES.md` | Verified source bank (~40 sources across foundations, benchmarks, security, tenancy/erasure/temporal, production systems) — reusable for later iterations and other posts |

Drafts follow the established naming from prior folders: `BLOGPOST_DRAFT_*.md` → `BLOGPOST_REVIEWED.md` → `BLOGPOST_COMPLETE*.md`, with the highest-numbered/final file being canonical.

## Source material

### KAOS user-facing documentation (the shipped implementation)
- `../../../kaos/docs/operator/memory-architecture.md` — tiers, scope model, topology, control/data plane, design rationale table
- `../../../kaos/docs/operator/memorystore-crd.md` — MemoryStore CRD reference, storage modes, HA, binding
- `../../../kaos/docs/examples/memory.md` — runnable worked example (deploy store + agent, cross-session recall, tools, scopes)

### Architecture decisions
- `../adrs/adr_high_level_components.md` — ADR index and component decomposition
- `../adrs/adr_0001` … `adr_0005` — memory model, Mem0 selection/integration, runtime interface, topology/control plane, multi-tenancy/governance

### Research (selection story)
- `../research/KAOS-R4-tool-comparison-and-selection.md` — screening logic, shortlist (Mem0, Zep/Graphiti, Cognee, Memobase, Redis AMS, custom baseline), first-pass matrix
- `../research/KAOS-R6-tool-selection.md` — scored criteria (C1–C12), per-candidate synthesis, primary (Mem0) + secondary (Redis AMS) selection
- `../research/KAOS-R2` (ecosystem/taxonomy), `KAOS-R5-*` (per-tool deep dives), `KAOS-R7` (target picture), `KAOS-R8` (production adoption), `KAOS-R9` (procedural/temporal tiers) — supporting citations

### Implementation plan and process
- `../plan/proposed-split.md` — M0–M7 phasing, bottom-up principles, current-state baseline, deferred list
- `../../duckmemory/learnings/P1–P3-learnings.md` — process learnings (limited blog value; skim only)

## Approach (process for this and future blog posts)

1. **Analyse the prior finals** into outlines and extract the shared style contract (`BLOG-ANALYSIS.md`) — hook grounded in an ecosystem trend, single thesis callout, framework-agnostic framing with KAOS as worked example, naive-code-then-what-breaks, trade-off tables, build-it-yourself section, when-not-to section, numbered lessons, cross-links.
2. **Propose an outline** (`OUTLINE_PROPOSED.md`) mapping each section to its source documents, and identify deliberate improvements over the prior posts. User reviews before drafting.
3. **Draft section by section** against the approved outline, keeping citations to primary sources and real, runnable snippets from the shipped docs.
4. **Review passes** for style-contract conformance and technical accuracy against the ADRs/docs, then finalize.

Key improvement levers identified for this post (details in `BLOG-ANALYSIS.md`): a recurring decision→why rationale table device; showing the real selection process (criteria-scored comparison); a fully verifiable walkthrough (no screenshot placeholders); explicit "counterintuitive insight" callouts; an honest deferred-work section.
