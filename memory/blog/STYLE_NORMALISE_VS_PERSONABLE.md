# Proposal: normalise vs personablise the remaining style items (draft 3 → draft 4)

**Status**: Proposal for review (v1). Covers the two deferred categories from `STYLE_REVISION_PLAN.md`: the antithesis constructions ("X, not Y" / "It's not X. It's Y") and the register/flourish items, plus the personable-touch decisions. Rewrite style per feedback: flowing sentences with connectives (however, although, rather than, instead of, whereas), no swapping '.' for ';', no em-dashes. Personable touches marked **P** (max one per section); everything else marked **N** (normalise).

## Personable budget across the post (the P items)

| Section | P item |
| --- | --- |
| §1 hook | the "greets you today like a stranger" image (goldfish removed, see row 1) |
| §3 | the existing first-person admission that KAOS started with the naive version (already in draft, no change) |
| §5 | "Interestingly enough, ..." on the accuracy finding (row 8) |
| §6 | "in my opinion ... the most transferable design rule" on the digest (row 17) |
| §8 | "the decision I expect readers to push back on" on the no-queue call (row 24) |
| §13 | "your agents get to be the interesting part" closing line (kept as-is) |

All other sections carry zero personable touches.

## Per-instance proposal

| # | § | Current (draft 3) | Tag | Proposed |
| --- | --- | --- | --- | --- |
| 1 | 1 | "There is a rush across the agentic ecosystem to fix the same embarrassing problem: agents are goldfish. Every session starts from zero, every hard-won fact evaporates when the conversation ends, and the 'personal assistant' you configured yesterday greets you today like a stranger." | N+P | "Most agent systems share the same limitation: nothing persists across sessions. Every session starts from zero, facts established in one conversation are gone in the next, and the 'personal assistant' you configured yesterday greets you today like a stranger." (goldfish removed; the stranger image is the section's one personable touch) |
| 2 | 1 | "The ecosystem's answer has been an explosion of dedicated memory layers" | N | "A number of dedicated memory layers have emerged in response" |
| 3 | 2 | "Memory is not the context window, which is... It is not RAG, which is... It is not session history, which is... And it is not task state: ..." | N | "The context window holds working state for a single model call. RAG retrieves over a corpus the agent did not produce. Session history is a transcript. Task state, as we argued in the autonomous post, is an external lifecycle contract. Memory overlaps with each of these, however it is none of them: it is the information an agent carries across turns and sessions to inform its reasoning, and it needs its own machinery." (one contrastive clause retained, pattern not repeated) |
| 4 | 3 | "A bigger window buys you a longer transcript, not memory." | N | "A bigger window gives you a longer transcript, although it still provides none of the distillation, scoping, or recall that memory requires." |
| 5 | 3 | Thesis callout: "Memory is not a vector database bolted onto an agent. Memory is a tiered, scoped, degradable subsystem, and the hard part is not storing memories: it is deciding who sees them, when they fold, and how the agent behaves when memory fails." | N | "Production memory is a tiered, scoped, degradable subsystem rather than a vector database bolted onto an agent. The difficult parts are deciding who sees each memory, when it folds, and how the agent behaves when memory fails, rather than the storage itself." |
| 6 | 5 | "not a bare substrate (pgvector, Qdrant, Chroma, Neo4j are backend choices *within* a design, not the design)" | N | "rather than a bare substrate (pgvector, Qdrant, Chroma, and Neo4j are backend choices within a design rather than the memory layer itself)" |
| 7 | 5 | "(vendor-authored numbers, but the *design* is the point)" | N | "(the numbers are vendor-authored, although the design itself is what matters here)" |
| 8 | 5 | "One thing the vendors' own numbers make clear, and worth stating plainly because most memory marketing does not: **extraction-based memory is a latency-and-cost play, not an accuracy play.**" | **P** | "Interestingly enough, working through the vendors' own numbers I learned that extraction-based memory improves latency and cost, however it does not improve raw accuracy, which most memory marketing leaves unstated." |
| 9 | 5 | Callout: "You are not choosing a memory product. You are choosing which 60% you don't have to build, and signing up to build the rest." | N | "Adopting a memory engine means choosing which 60% of the system you do not have to build, and committing to build the remaining 40% around it." |
| 10 | 5 | "provide message history, not memory" | N | "provide message history only, so long-term memory remains the application's responsibility" |
| 11 | 5 | "the norm is an external engine wrapped behind the application's own contract, not adopted wholesale" | N | "the norm is to wrap an external engine behind the application's own contract instead of adopting it wholesale" |
| 12 | 6 | "This tier is also the fallback when everything else is on fire." | N | "This tier is also the fallback when the long-term store is unavailable." |
| 13 | 6 | "**Long-term** is where the engine earns its keep" | N | "The **long-term** tier is where the adopted engine does its work" |
| 14 | 6 | "Projections can be recomputed from the source; the source can never be recomputed from a projection." | N | "Projections can be recomputed from the source, whereas the source can never be recomputed from a projection." |
| 15 | 6 | "You do not have to pick a winner in that debate; you have to design so you are not betting on one." | N | "Rather than picking a winner in that debate, the design goal is to avoid betting on either side." |
| 16 | 6 | "extraction becomes a recomputable optimization, not a destructive act" | N | "extraction then becomes a recomputable optimization instead of a destructive act" |
| 17 | 6 | "The tier that generated the most debate, and the insight we would most want you to take away, is the medium-term digest:" | **P** | "The medium-term digest is the tier that generated the most internal debate, and in my opinion it carries the most transferable design rule in this post:" |
| 18 | 6 | "Temporal memory is not 'timestamps on facts': it means separating..." | N | "Temporal memory involves more than attaching timestamps to facts: it means separating..." |
| 19 | 7 | "the answer has to be structural, not a convention" | N | "the answer has to be structural rather than a convention" |
| 20 | 7 | "**Isolation strength is a deployment choice, not a code path.**" | N | "**Isolation strength is a deployment choice rather than a code path.**" |
| 21 | 7 | "Scope is derived server-side..., never from model- or tool-supplied arguments." / "the model supplies the *query*; the service supplies the *scope*" | N | "Scope is derived server-side from the authenticated agent identity and request context, and never from model- or tool-supplied arguments. When the agent's `search_memory` tool fires, the model supplies the query while the service supplies the scope." |
| 22 | 7 | "treat recalled memory as untrusted data with provenance: evidence the model may weigh, never instructions that override policy" | N | "treat recalled memory as untrusted data with provenance, which the model may weigh as evidence although it must never be allowed to override system policy" |
| 23 | 7 | "the scope filter must be applied **inside** the vector query, not as a post-filter" | N | "the scope filter must be applied inside the vector query instead of as a post-filter" |
| 24 | 8 | "One deliberately contrarian call to close the section: background extraction is **in-process fire-and-forget, with no durable job queue.**" | **P** | "The decision I expect readers to push back on: background extraction is in-process fire-and-forget, with no durable job queue." |
| 25 | 8 | "Embedding is seductive: no new workload, no network hop." | N | "Embedding the engine looks attractive at first, since it adds no new workload and no network hop." |
| 26 | 8 | Callout: "**Memory is augmentation, not a dependency.** A memory outage should degrade an agent, never stop it." | N | "**Memory is augmentation rather than a hard dependency.** A memory outage should degrade an agent and never stop it." |
| 27 | 8 | "a lost extraction costs one recomputable projection, not data" | N | "a lost extraction costs one recomputable projection rather than any data" |
| 28 | 8 | "resisting the reflex to build Kafka-shaped infrastructure before the failure mode has been observed even once" | N | "instead of building durable queue infrastructure before the failure mode has been observed even once" |
| 29 | 8 | Rationale table: "Token budgets, not turn counts" / "an outage degrades, never stops, an agent" | N | "Token budgets rather than turn counts" / "an outage degrades an agent, never stops it" |
| 30 | 8 | "Note the models are references to `ModelAPI` resources, not provider keys" | N | "Note the models are references to `ModelAPI` resources rather than provider keys" |
| 31 | 11 | "memory without deletion is a liability, not a feature" | N | "memory without deletion is a liability rather than a feature" |
| 32 | 11 | "remembering is not the same as staying current" | N | "remembering and staying current are different problems" |
| 33 | 11 | "a recalled fact is a hypothesis about the present, not a guarantee" | N | "a recalled fact is a hypothesis about the present state that may require re-validation" |
| 34 | 12 | Lesson headings/bodies: "augmentation, not a dependency" / "tokens, not turns" / "attacks, not hypotheticals" / "at scale, not raw accuracy" | N | "augmentation rather than a dependency" / "tokens rather than turns" / "demonstrated attacks rather than hypotheticals" / "at scale rather than raw accuracy" |
| 35 | App. | Checklist: "bounded by tokens, not turns" / "pre-filtered, not post-filtered" / "with provenance, never as policy" | N | "bounded by tokens rather than turns" / "pre-filtered rather than post-filtered" / "with provenance rather than as policy" |

## Items proposed to keep as-is

- §5 "no candidate dominates" and the per-candidate trade-off sentences: contrastive but informative, no formulaic pattern.
- §7 "you have a compliance incident waiting for a trigger": a factual consequence, mildly vivid but additive.
- §7/§9 "the fail-closed rule from earlier applied at the tool boundary": additive.
- §13 "your agents get to be the interesting part": the closing section's single personable touch.
- Quoted framings from sources ("stored XSS for agents"): quoting is allowed under the rules.

## Notes

- Rows 5, 26: these are the two `>` callouts; the "rather than" forms keep them quotable without the antithesis pattern.
- Row 8 replaces the §5 bolded claim with a personable sentence; if you prefer the claim to stay bold and impersonal, the N alternative is: "Extraction-based memory improves latency and cost, however it does not improve raw accuracy, which most memory marketing leaves unstated."
- Rows 34–35 change several short headings/checklist items mechanically; flagged together since the pattern is identical.
