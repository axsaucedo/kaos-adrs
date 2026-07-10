# ADR-0007 — Storage generality (agent state, not just conversation memory) and the default interface

**Status:** Accepted.

## Context

Follow-on from [ADR-0006](./adr_0006_consolidation-cadence-observability-and-mem0-parity-surface.md): the owner resolved
the open facts-only question as **mode, not replacement** — the tiers stay, and a mem0-parity
`add()` becomes the first-class front door. That raised the deeper question this ADR decides:
for a *local embedded* database, is storing conversations enough, or should the store carry
the rest of an agent's state?

Two empirical references ground the answer. **GitHub Copilot CLI's sqlite**
(`~/.copilot/session-store.db` + per-session `session.db`) stores, beyond sessions and turns:
`checkpoints` with *structured* fields (`title, overview, work_done, technical_details,
important_files, next_steps`) — independently converging on our fold/digest concept and going
further by typing it; `session_files`/`session_refs` (the working set: entities a session is
about); and per-session `todos` + `todo_deps`, `inbox_entries`, `pr_urls`. **The
`agent_data_duckdb` extension** exposes `read_conversations / read_todos / read_plans /
read_history / read_stats / read_tokens` over five agent CLIs — market evidence that every
major coding agent persists conversations *plus todos plus plans*, each in an ad-hoc format,
which is precisely why a query plugin had to exist.

Agent state therefore factors into three categories: (1) conversation memory
(turns/summaries/facts — covered today), (2) task state (todos, plans, structured progress),
(3) working set (files, PRs, tickets, branches a session touches). mem0, as a remote
personalization service, rationally covers only (1)'s facts slice; an embedded file has no
such excuse — and "the agent's state file" is the honest ambition and the differentiation.

## Options and trade-offs

- **Option 1 — conversation-only; richer state is host tables.** Cheapest; but todos/plans
  then sit outside scope, recall, context assembly, and lifecycle — the entire value of being
  in the engine — and every host reinvents the schema (the ad-hoc mess agent_data papers over).
- **Option 2 — first-class typed tables** (`mem.todos`, `mem.plans`, `mem.working_set`,
  Copilot-style). Best per-type ergonomics; but N schemas to design/version/defend, and the
  scope/recall/lifecycle machinery multiplied per table. Over-engineering risk.
- **Option 3 — generalize the fact.** `long_term_facts.kind` is already an open column (the
  deliberate ADR-0001 seam). Keep one row shape — content + embedding + scope envelope +
  importance/pinned/TTL — add a defined `kind` vocabulary (`fact`,`todo`,`plan`,`entity`,…)
  and a `structured JSON` column for typed payloads (status, depends_on, file_path, …).
  Everything is scoped, recallable, foldable, and lifecycle-managed for free; typed views
  give Option-2 ergonomics on top.

## Decision

**Option 3.** One column (`structured JSON`), a `kind` vocabulary, and thin typed views
(`mem.todos`, `mem.plans`, `mem.working_set` as `SELECT … WHERE kind = …`). `memory_recall`
gains a `kind :=` filter; `memory_context` gains an opt-in open-todos section. The library's
framing becomes **the agent's state file**, with conversation memory as the founding tier,
not the boundary.

**Accepted trade-offs.** JSON payloads are weaker typing than dedicated tables (todo
dependencies as a JSON array vs a real edge table), and embedding todos/plans has marginal
recall value — `kind`-filtered exact queries will dominate for those. Both acceptable and
reversible: a `todo_deps` edge table can be added the day dependencies matter.

**Recorded candidate (not yet decided): structured digests.** Copilot's checkpoint schema is
evidence that `medium_term_summaries` wants typed fields (`next_steps`, `important_files`,
`work_done`) rather than one text blob — it is what makes session-resume useful rather than
merely possible. Candidate evolution, to be decided when the Layer-2 summarizer is designed
(the summarizer's output contract and the digest schema should be fixed together).

## The full surface (post ADR-0006 + this decision)

Nothing existing is removed or altered in meaning; the add()-first decision changes packaging
and presentation order. The raw-SQL user today notices only the renames.

**Engine SQL (the truth):**

- Tables: `mem.short_term_turns`, `mem.medium_term_summaries`, `mem.meta` unchanged
  (renamed); `mem.long_term_facts` + `structured JSON` + kind vocabulary;
  `mem.facts_history` new with reconcile (ADR-0006 D8); typed views new.
- Functions: `memory_recall(_text)` (+ `kind :=`), `memory_context(_text)` (+ todos
  section), `memory_stats`, `memory_expired`, `memory_embed`, `memory_fold_needed`
  unchanged; `memory_fold_plan` + chunk param (D3); **new** `memory_window(session)` (D5)
  and `memory_extract(text) -> STRUCT(content, kind, importance, structured)[]` (Layer 2).
- Apply steps (fold, reconcile, lifecycle) remain documented DML — the no-DML-in-macros
  constraint stands.

**SDK (`agent_memory` client — new artifact, the default interface):**

```python
m = Memory("agent.db", user_id="u1", agent_id="a1")     # scope defaults at construction

m.add(messages, session_id=None, fold="sync", infer=True)  # facts-only = 1-1 mem0;
                                                            # with session_id: turns + window + fold
m.search(query, kind=None) ; m.get / get_all / update / delete / delete_all / history / reset

m.context(session_id, query=None) ; m.window(session_id) ; m.fold(session_id)

m.add_todo(title, status="pending", depends_on=[...])   # sugar over kind='todo'
m.add_plan(title, steps=[...]) ; m.track(entity_type, value) ; m.todos(status=...)
```

The SDK holds no state — every call maps to the SQL above; the file is the product. Full
classic-mem0 parity (LLM-decided ops + history) lives here per ADR-0006 Option C; the
similarity-MERGE fast path (Option B) is an optimization contingent on its spike, never
required.

## Consequences

- **Positive.** Categories (2) and (3) of agent state are covered with one column and views —
  no new machinery, no new correctness surface; the product story sharpens from "conversation
  memory engine" to "agent state file", which a remote service structurally cannot match; the
  README can lead with three lines of Python while the SQL layer stays fully documented
  beneath.
- **Negative.** A second artifact to build, version, and release (the SDK package); the
  `kind` vocabulary becomes API surface (additions cheap, renames breaking); typed-view
  ergonomics will draw feature requests (deps, ordering, assignees) that must be resisted or
  graduated deliberately per the recorded trade-off.
- **Follow-on.** PR sequence from ADR-0006 extended: table rename → library rename →
  demo.sql fix → D3+D5 → **Option 3 schema (structured column, vocabulary, views, recall
  filter)** → Layer-2 extraction → reconcile + facts_history → SDK package. Structured-digest
  candidate revisited at Layer-2 summarizer design time.
