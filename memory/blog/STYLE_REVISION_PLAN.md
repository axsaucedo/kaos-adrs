# Style revision plan for BLOGPOST_DRAFT_2 → DRAFT_3

**Status**: Outline for review (v1). Applies the requested style rules to `BLOGPOST_DRAFT_2.md`. Nothing is rewritten until this plan is approved. The rules themselves are recorded at the end so they carry into future posts.

## Audit summary of DRAFT_2 against the rules

| Rule | Current state in draft 2 | Scale of change |
| --- | --- | --- |
| No em-dashes | **95 em-dashes** across the document | Every one replaced with a comma, colon, parenthesis, period, or plain '-' where a dash is genuinely needed |
| Straight quotes only | Already clean (0 curly quotes found) | No change |
| Banned word list | One hit: "journey" (intro); no testament/pivotal/leverage/etc. | 1 word replaced |
| "It's not X. It's Y" / antithesis patterns | ~27 instances of the `X, not Y` / "is not X — it is Y" family, including the thesis callout | The largest rewrite category; each either converted to a direct statement or deleted |
| Emphasis-only sentences (no added information) | ~10 instances ("That's the bar.", "Plumbing, in other words.", "The model is the least of your problems.", "A list, a slice, done.", "It worked fine, right up until it didn't.", "now with teeth", "This is not paranoia") | Deleted or merged into an informative sentence |
| Neutral academic register | Hook and several sections use rhetorical flourish ("rush across the ecosystem", "explosion of memory layers", "where the engine earns its keep", "seductive", "on fire", "deliberately contrarian call") | Rewritten plain; see per-section notes |
| Personable touches, max 1 per section | Currently several per section in places (§1, §6, §8, §12) | Thinned to at most one per section; each retained touch chosen explicitly below |

## Change categories with representative before → after examples

### 1. Em-dash elimination (95 instances)

- Before: `Short-term is the verbatim recent-turn window: session-scoped, plain relational rows, no embeddings. It is bounded by a **token budget** — not a turn count — because the context window is the real constraint`
- After: `Short-term is the verbatim recent-turn window: session-scoped, plain relational rows, no embeddings. It is bounded by a token budget rather than a turn count, because the limiting resource is context-window space and turns vary widely in size.`

- Before: `Centralizing inverts all four:`  (preceded by an em-dash chain)
- After: restructure the sentence into a list or two sentences; use ':' and ',' only.

### 2. Antithesis / "It's not X. It's Y" rewrites (~27 instances)

The content of these sentences is kept; the construction is replaced with direct statements.

- Thesis callout, before: `Memory is not a vector database bolted onto an agent. Memory is a tiered, scoped, degradable subsystem — and the hard part is not storing memories, it is deciding who sees them, when they fold, and how the agent behaves when memory fails.`
- After: `Production agent memory is a tiered, scoped, degradable subsystem. The difficult design problems are access scoping, consolidation timing, and failure behaviour, rather than storage itself.`

- §2 definitional paragraph, before: `Memory is not the context window — that is working state for one model call. It is not RAG — ...`
- After: convert to a short definition list that states what each adjacent concept *is* and how memory differs, e.g. `The context window holds working state for a single model call. RAG retrieves from a corpus the agent did not produce. Session history is a transcript. Task state is an external lifecycle contract. Memory, as used here, is the information an agent carries across turns and sessions to inform its reasoning; it overlaps with each of these but is reducible to none of them.` (one contrastive clause retained, pattern not repeated)

- §5, before: `extraction-based memory is a latency-and-cost play, not an accuracy play`
- After: `extraction-based memory improves latency and cost; it does not improve raw accuracy`

- §5 callout, before: `You are not choosing a memory product. You are choosing which 60% you don't have to build — and signing up to build the rest.`
- After: `Selecting a memory engine determines which capabilities are inherited and which must be built around it; the gaps accepted at selection time become the integration workload.`

- §6, before: `extraction becomes a recomputable optimization, not a destructive act`
- After: `extraction then operates as a recomputable optimization, since the source events remain available`

- §7, before: `This is not paranoia — memory is now a documented attack surface.`
- After: `Memory is a documented attack surface.` (the first clause carried no information)

- §11, before: `a recalled fact is a hypothesis about the present, not a guarantee`
- After: `a recalled fact should be treated as a hypothesis about the present state that may require re-validation`

### 3. Emphasis-only sentence deletions (~10 instances)

Deleted outright (the surrounding sentence already carries the point): `That's the bar.`, `Plumbing, in other words.`, `A list, a slice, done.`, `The model is the least of your problems.`, `now with teeth`, `It worked fine, right up until it didn't.` (this one is replaced by a factual clause: `it was sufficient until the requirements in the next section appeared`), `This fails quietly, not loudly` (merged into the pgvector sentence), `The justification is quantitative, not aspirational` (deleted; the numbers follow anyway).

### 4. Register normalization (rhetorical flourish → plain)

- `There is a rush across the agentic ecosystem to fix the same embarrassing problem` → `Most agent frameworks share the same limitation: state does not persist across sessions.`
- `The ecosystem's answer has been an explosion of dedicated memory layers` → `A number of dedicated memory layers have emerged in response`
- `we went through this journey end to end` → `we carried out this work end to end` (also removes the banned word)
- `Long-term is where the engine earns its keep` → `The long-term tier is the engine's primary responsibility`
- `Embedding is seductive — no new workload, no network hop` → `Embedding the engine avoids a new workload and a network hop`
- `the fallback when everything else is on fire` → `the fallback tier when the long-term store is unavailable`
- `One deliberately contrarian call` → `One decision that departs from common practice`
- `Kafka-shaped infrastructure` → `durable queue infrastructure`
- Section titles largely stay (they are structural), but `Closing: Boring Memory` becomes `Closing` or `Conclusions`, and the "boring" motif is reduced to a single, explained use (see personable budget).

### 5. Personable-touch budget (max 1 per section)

Retained, one each, everything else in that section neutralized:

- §1 hook: **"agents are goldfish"** stays (one image, then plain prose).
- §3: the first-person admission **"the original KAOS memory was exactly this"** stays (it is informative as well as personable).
- §6: an explicit opinion marker on the digest rule: `In my opinion this is the single most transferable design rule in this post` (replaces the current "the insight we would most want you to take away").
- §8: the honest admission about resisting premature infrastructure stays, reworded plainly.
- §13 closing: one echo of the trilogy's "boring" motif, stated once and explained (`the operational goal, as in the previous two posts, is that memory behaves predictably enough to be uninteresting`), replacing "That's the bar."
- All other sections: zero personable touches.

### 6. What does NOT change

- Structure: all 13 sections, all tables, all three mermaid diagrams, the YAML/bash/python blocks, the appendix checklist.
- All 17 citations and their placement.
- The `>` callout device is retained (it is structural, and the previous two posts establish it), but each callout's text is rewritten under the rules above.
- Technical claims and numbers: unchanged.

## Open questions for review

1. **Tension with the series style contract.** The two published posts are deliberately punchy ("boring debugging", "Autonomy is not the loop..."). This revision moves the memory post to a noticeably more neutral register than its siblings. Proceeding on the assumption this is intended; flagging that the three posts will read differently side by side.
2. The §2 definitional paragraph is inherently contrastive (memory vs context window vs RAG vs task state). The plan keeps one contrastive clause and converts the rest to positive definitions; full elimination would lose information.
3. `Momento`'s "stale state" caution and the "stored XSS for agents" phrase are quoted framings from sources; kept as quoted characterizations (quoting a source is allowed under the rules).

## Codified style rules (for this and future posts)

1. Neutral academic English; clear, concise, factual; register comparable to peer-reviewed journal articles.
2. No em-dashes. Use commas, colons, parentheses, or periods; plain '-' only where a dash is required (compounds, ranges).
3. Straight quotes (' and ") only.
4. Banned unless quoting a source: testament, underscore, propel, unwavering, heartfelt, embrace, foster, ignite, empower, amplify, catalyst, leverage, epitome, cornerstone, harness, noteworthy, unprecedented, profound, pivotal, journey. Use plain alternatives (shows, indicates, supports, argues).
5. Avoid formulaic LLM constructions: "It's not X. It's Y", "the real X is", "is less X and more Y", "at its core", "delving into", "is quietly ...", "this is another strong signal that ... moving from ... into ...".
6. Every sentence must add information; delete sentences whose only function is to emphasize a previous point.
7. Personable touches (first-person opinion, humour) at most one per section, and not in every section.
