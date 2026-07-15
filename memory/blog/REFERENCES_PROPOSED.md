# Proposed research-paper references for BLOGPOST_DRAFT_1

**Status**: **v2 — consolidated proposal** (2026-07-15), superseding the v1 KAOS-research-only proposal and the two external-report assessments below (kept for record). Grounded in the verified source bank `RESEARCH_SOURCES.md` (5 parallel research passes; every source verified against its live page). The prior posts' style holds: cite inline at the point of claim, no bibliography section.

## v2 — Consolidated citation proposal (~16 in-post citations)

### A. Lineage and taxonomy (§2)
1. **CoALA** (arxiv 2309.02427) — the taxonomy table's actual source.
2. **MemGPT** (2310.08560) + **Generative Agents** (2304.03442) — already in draft; keep.
3. **Framework convergence one-liner** — LangGraph persistence docs + Letta memory-blocks docs: the ecosystem draws the same short-term/long-term line (thread checkpointer vs store; in-context blocks vs archival).

### B. Long context doesn't solve memory (§3)
4. **LongMemEval** (2410.10813) — with the now-verified numbers: GPT-4o 60.6–64% over full 115K-token histories vs 87–92% with oracle retrieval.
5. **LoCoMo** (2402.17753) — long-context + RAG still lag humans, weakest on temporal reasoning.

### C. Engine selection (§5)
6. **Mem0 paper** (2504.19413, ECAI 2025) — cite *honestly*: full-context beats Mem0 on raw accuracy (72.9% vs 66.9%); the production case is −91% p95 latency (1.44s vs 17.1s) and >90% token savings. This makes our "memory is an efficiency/scale play, wrapped behind your own contract" argument stronger, not weaker.
7. **Zep paper** (2501.13956) — the capability-ceiling reference (DMR 94.8%, temporal KG); flag vendor-authored numbers as such.

### D. Tiers and the digest insight (§6)
8. **Recursively Summarizing** (2308.15022) — lineage for the rolling digest (replaces Reflexion in that paragraph).
9. **Storage Is Not Memory** (2605.04897) + **WhenLoss** (2605.24579) — the extraction counterpoint, now with teeth: verbatim-events + retrieval hits 93.0% LoCoMo vs Mem0's 61.4%, and write-side loss dominates in 4/6 systems. Cite and *answer*: KAOS keeps raw turns as the durable source of truth, so extraction is a recomputable projection, not a destructive act.
10. **Diagnosing Retrieval vs Utilization** (2603.02473) — the counter-counterpoint (retrieval quality dominates write-strategy choice by 20pp vs 3–8pp): one sentence acknowledging the fault line is contested.

### E. Scopes and security (§7)
11. **pgvector post-filtering recall demo** (Pachot, dev.to) + **Qdrant filterable-HNSW docs** — the pre-filtered-vector-query claim gets a concrete failure demo (15 requested, 11 returned) and a canonical vendor mechanism.
12. **MINJA** (2503.03704) + **AgentPoison** (2407.12784) — memory poisoning is evidenced, not hypothetical: >80% attack success at <0.1% poison rate; poisoning via ordinary queries alone.
13. **Cross-session stored prompt injection** (2606.04425) — the "stored XSS for agents" framing: content saved in one session executes as instructions in a later one.
14. **MPBench** (2606.04329) — agents that auto-write/auto-retrieve most aggressively are most exploitable — empirical backing for the additive, conservative `tools` knob and the automatic-baseline design.

### F. Topology and operations (§8)
15. **Agent-memory systems characterization** (2606.06448) — write- vs read-path cost split; the economics citation for extraction-off-the-hot-path. (Redis AMS's queue-based async extraction gets a passing mention as independent convergence on the same pattern.)

### G. When not to / closing (§11–12)
16. **Cost-performance break-even** (2603.04814) — fact-memory becomes cost-favorable after ~10 turns at 100k-token scale: turns "when to bother" from vibes into a heuristic.
17. *(optional)* **Momento** (2606.00832) — 2026 benchmarks shift to whether agents re-validate stale state, not just recall it.

### New content points to adopt (beyond citations)
- **§5 — honest accuracy framing**: state plainly that extraction-based memory trades raw accuracy for latency/cost at scale (Mem0's own table); our thesis is operability, so this strengthens it.
- **§6 — source-of-truth framing**: raw turns are the durable source; digest/facts/embeddings are recomputable projections — this is both the answer to Storage-Is-Not-Memory and the defense of fire-and-forget extraction.
- **§7 — memory-poisoning paragraph** (2–3 sentences after the scope callout): recalled memory is untrusted data; scope enforcement stops unauthorized *reads*, provenance is what bounds untrusted *writes* (TMA-NM/MemLineage support if a citation is wanted).
- **§7 — supersession ≠ erasure** (one sentence): bi-temporal invalidation keeps history; right-to-erasure destroys it — two different operations, and KAOS implements hard erasure.
- **§11 — the ~10-turn break-even** as a concrete "when it pays off" heuristic.

Full source bank with all ~40 verified sources (including the ones deliberately not cited): `RESEARCH_SOURCES.md`.

---

# v1 proposal and external-report assessments (superseded, kept for record)

## Already cited in the draft

| Paper | Where |
| --- | --- |
| MemGPT — LLMs as Operating Systems (Packer et al., 2023, arxiv 2310.08560) | §2 taxonomy intro |
| Generative Agents / Smallville (Park et al., 2023, arxiv 2304.03442) | §2 taxonomy intro |

## Proposed additions (7 — recommended)

| # | Paper | Where in the draft | Claim it grounds |
| --- | --- | --- | --- |
| 1 | **CoALA — Cognitive Architectures for Language Agents** (Sumers et al., 2023, arxiv 2309.02427) | §2, sentence introducing the taxonomy table | The episodic/semantic/procedural split is not our invention — it is the near-universal framing, systematized for agents by CoALA. The single most-cited framework in R2; the taxonomy table is essentially CoALA's. |
| 2 | **A Survey on the Memory Mechanism of LLM-based Agents** (2024, arxiv 2404.13501) | §2, same paragraph (alongside CoALA) | "For a broader research view" pointer — mirrors how the autonomous post cited its two survey papers in the definitional section. Its write/read/consolidation/forgetting operations framing also maps directly onto our recall/write/fold/forget verbs. |
| 3 | **LongMemEval** (2024, arxiv 2410.10813) | §3, after the naive embed-everything snippet | Kills the "just use a long context window" counterargument with data: long-context models drop 30–60% at ~115K tokens. This is the strongest evidence for why tiering exists at all — currently the section asserts it without support. |
| 4 | **LoCoMo — Evaluating Very Long-Term Conversational Memory** (2024, arxiv 2402.17753) | §3, same paragraph as LongMemEval | Even long-context + RAG remains far below human recall (~56% overall, ~73% on temporal reasoning) — grounds "neither survives contact with production" and foreshadows why temporal memory is hard (picked up in §6 deferral). |
| 5 | **Generative Agents** — second, deeper citation | §6 (tiers) or §2, when describing long-term recall | The canonical `relevance × importance × recency` retrieval-scoring formula that production systems (incl. Mem0-class engines) still use. The draft describes relevance-ranked recall without naming the lineage. |
| 6 | **Zep — A Temporal Knowledge Graph Architecture for Agent Memory** (2025, arxiv 2501.13956) | §5 selection table (Zep/Graphiti row) and §6 deferred-tiers paragraph | Grounds two claims: why Graphiti is "the capability ceiling" (reported DMR 94.8%, LongMemEval gains), and why temporal memory is deferred *behind a graph engine* — non-lossy invalidation (facts invalidated, not deleted) is the capability a vector store can't fake. |
| 7 | **Reflexion** (Shinn et al., 2023, arxiv 2303.11366) | §6, the folding/digest paragraph | The lineage of "background processes that synthesize higher-order memory from raw experience" — also creates continuity: the autonomous post already cited Reflexion, so this is a natural cross-series echo. |

## Considered, proposed to leave out (with reasons)

| Paper | Reason to omit |
| --- | --- |
| A-MEM (2025, arxiv 2502.12110) | Interesting (agent-controlled memory structure) but orthogonal to every claim in the post; would be a citation for its own sake. |
| HippoRAG (2024, arxiv 2405.14831) | Graph-retrieval technique below our altitude — we discuss engines, not retrieval algorithms. |
| EM-LLM (2024, arxiv 2407.09450) | KV-cache paging is model-internals territory; nothing in the post touches it. |
| Cognee paper (2025, arxiv 2505.24478) | The §5 table already links Cognee's repo; a paper link adds little for a candidate we didn't select. Could add to the table row if we want symmetry with the Zep row. |

## Assessment of the agent-memory deep-research report

Assessed: `~/Downloads/agent-memory-research-report.md` (deep-research survey produced *for this draft* by another model). Its core recommendations overlap with proposals 1–7 above — it independently arrives at MemGPT, Generative Agents, LoCoMo, LongMemEval, and the Zep paper for the same sections, which is good convergence signal. Beyond that overlap, the genuinely new items:

### Proposed additions from this report

| # | Resource | Where | What it adds | Recommendation |
| --- | --- | --- | --- | --- |
| 8 | **Recursively Summarizing Enables Long-Term Dialogue Memory** (2023, arxiv 2308.15022) | §6, the medium-term digest paragraph | The direct research lineage for the rolling-digest pattern — a better fit for that paragraph than Reflexion (proposal 7), which is about self-improvement rather than continuity summaries. Suggest it *joins or replaces* Reflexion there. | **Add** |
| 9 | **Storage Is Not Memory** (2026, arxiv 2605.04897 — **verified real**) | §6/§8, one sentence | The strongest published counterpoint to extraction-heavy designs: preserve verbatim events, improve retrieval. Citing the opposing view and answering it ("our raw turns *are* retained; projections are recomputable") makes the flagship digest insight rigorous rather than dogmatic. | **Add** |
| 10 | **WhenLoss** (2026, arxiv 2605.24579 — **verified real**) | §8, the fire-and-forget paragraph | Names the write-side vs retrieval-side loss distinction that our "short-term tier is the durable record" defense implicitly relies on. One clause + link. | **Add** |
| 11 | **LangGraph memory docs + Google ADK memory docs** | §2, the continuity-vs-learned-knowledge paragraph | One sentence of ecosystem convergence: major frameworks draw exactly this short-term/long-term line (LangGraph thread vs store; ADK Session/State vs MemoryService). Mirrors the autonomous post's framework-survey habit at 1/10th the size. | **Add** (links, not papers) |

### Substantive (non-citation) suggestions from the report worth adopting

These change wording, not structure — the report itself warns against diluting the post into a literature review:

1. **"Source of truth / derived projections" framing (report Revisions 2+4)** — one or two sentences in §6/§8: raw turns are the source of truth; digest, facts, and embeddings are derived projections, which is precisely *why* fire-and-forget extraction is tolerable (projections are recomputable) and why the digest rule is a trade-off, not a taboo. This is the report's best idea — it strengthens two of our flagship claims at once. **Adopt.**
2. **Memory-as-untrusted-data paragraph (report Revision 5)** — 2–3 sentences after the "never let the model choose the scope" callout in §7: scope enforcement stops unauthorized reads, but recalled content itself can carry injected instructions or poisoned facts; treat recalled memory as evidence with provenance, never as policy. Converges with the AgentDojo proposal below (the two together make one tight paragraph). **Adopt.**
3. **Erasure backups caveat (report Revision 6)** — one honest sentence in §7 or lesson 9: logical erasure across online tiers is not physical destruction in backups; the API contract should distinguish them. **Adopt (small).**
4. **Temporal semantics precision (report Revision 7)** — one sentence where temporal memory is deferred (§6): temporal memory means event/ingestion/valid time and supersession, not timestamps — which is why it needs a graph engine. Pairs with the Zep citation already proposed (#6). **Adopt (small).**

### Considered, proposed to leave out

| Suggestion | Reason to omit |
| --- | --- |
| MemoryBank (2305.10250) | Decay/forgetting gets one line in the post; a citation without a claim to carry. |
| "How to Evaluate Agent Memory" section (report Revision 3) | New section = scope creep vs the approved outline; LongMemEval (#3) already carries the evaluation point. Lightweight alternative if desired: 3 evaluation bullets added to the appendix checklist. |
| Three additional mermaid diagrams | The draft already has three; the "derived projections" idea is better carried by one sentence than a fourth diagram. |
| OpenAI memory note, Mem0/Redis repos | Already linked in the hook and §5. |
| Anthropic "Building Effective Agents" | Already cited twice in the autonomous post; re-citing here adds series repetition, not value. |
| pgvector/Qdrant filtering docs | Below the post's altitude — we make the pre-filtering point without teaching vendor query planners. |

**Net effect if approved**: citation set becomes ~10 papers + 2 framework-doc links (7 from KAOS research + 3 from this report, with Recursively-Summarizing possibly replacing Reflexion), plus four small wording adoptions. Still well under survey territory.

## Assessment of the security/identity deep-research report (superseded — wrong report, kept for record)

Assessed: `~/Downloads/agentic-security-identity-deep-research.md` (deep-research survey produced for the *security and identity* blog post). Verdict: **almost all of it belongs to that post, not this one** — OAuth/OIDC RFCs, token exchange, SPIFFE, Zanzibar/Cedar/OpenFGA, and the MCP threat-model material are about authenticating principals and authorizing tool calls, which the memory post deliberately treats as an adjacent concern (scope *derivation* assumes an authenticated identity exists; how it gets authenticated is the security post's story).

Two candidates do intersect with claims the memory post actually makes, both in §7 (scopes):

| # | Resource | Where | Claim it grounds | Recommendation |
| --- | --- | --- | --- | --- |
| 8 | **AgentDojo** (github.com/ethz-spylab/agentdojo, NeurIPS 2024 prompt-injection benchmark) | §7, the "never let the model choose the scope" callout | The rule is a prompt-injection defense, not just hygiene: benchmarks show tool-using agents are reliably manipulable via injected content, so a model-supplied scope argument turns any injection into a cross-tenant memory read. One clause + link makes the callout threat-grounded instead of asserted. | **Add** |
| 9 | **A Vision for Access Control in LLM-based Agent Systems** (arxiv 2510.11108) | §7, closing of the scope section | Positions "who can see which memory" as an instance of the emerging agent-access-control problem the research community is now naming. | **Optional** — add only if we want a forward-looking research pointer; the section stands without it. |

Explicitly rejected for this post (they would be citations without a claim):

- **OAuth/OIDC/token-exchange RFCs (8693, 9700, 8707, 9396, 9449), Keycloak docs** — delegation mechanics; the memory post only says scope derives from "authenticated identity" and A2A scope propagation is deferred. These anchor the security post.
- **SPIFFE / Kubernetes service accounts / NIST 800-207 zero trust** — workload-identity and enforcement-posture material; the memory post's fail-closed language is about query scoping, not network policy posture.
- **Zanzibar / Cedar / OpenFGA / NIST ABAC** — our scope model's whole point is that it is *not* an authorization system ("the store is the group"); citing ReBAC literature would invite the comparison the design deliberately avoids. If anything, that contrast belongs in the security post.
- **MCP security papers, AgentHarm, SafeClawBench, MCPSafetyScanner** — tool-supply-chain and harness-safety surface, out of this post's scope. (A future "memory poisoning" angle — adversarial content written into long-term memory and recalled later — is real and worth a post of its own, but this report contains no memory-poisoning sources, so nothing to cite here.)

## Placement principles

- Inline at the point of claim, `[title-ish anchor](https://arxiv.org/abs/...)`, matching how the autonomous post cited ReAct/Toolformer/Reflexion/Generative Agents.
- No standalone "References" section — the prior posts don't have one; the appendix stays a checklist.
- Cap at ~7 additions: §2–§3 get the foundational/benchmark cluster (where the reader needs convincing), §5–§6 get the engine-specific papers (where the decisions are defended). More than that and the post reads like a survey.
