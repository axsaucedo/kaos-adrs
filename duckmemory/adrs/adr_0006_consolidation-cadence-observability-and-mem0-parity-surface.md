# ADR-0006 — Consolidation cadence, window observability, reconciliation, and the mem0-parity surface

**Status:** Accepted (decisions D1–D8 and the rename plan); the facts-only/add()-first surface (§Open) is under active design — options recorded, decision pending.

## Context

Post-v0.1.0 design review with the owner (2026-07-10), walking the shipped surface against the
mem0 workflow ([KAOS-R5-1](../../memory/research/KAOS-R5-1-mem0.md)) and the KAOS tier model.
v0.1.0 ships the three tiers and the deterministic fold selection ([ADR-0001](./adr_0001_memory-model-and-lifecycle-operations.md)),
but leaves extraction host-side ([ADR-0004](./adr_0004_embedding-and-llm-integration-boundary.md) Layer 2, deferred with a reserved seam).
This review pinned down how that seam should be filled, what observability is missing, how
reconciliation differs from mem0's, and what a mem0-parity `add()` surface could look like.
Two P1/P2 facts constrain everything here: DuckDB has no triggers and macros cannot run DML,
and the extension cannot execute SQL after LOAD — so nothing in the engine can be "automatic
on INSERT"; but DML statements *can* call extension scalars, which is the unlock for
single-statement pipelines.

## Decisions

### D1 — Window budgets: global knobs + per-call override; per-session config only as a coalesce chain

`budget_tokens` / `fold_target_tokens` remain global `mem.meta` knobs with per-call overrides
(v0.1.0 behavior, confirmed sufficient). If stored per-session windows become needed, the
design is a coalesce chain (per-session config → global meta → built-in default) — no new
machinery.

### D2 — Fold is synchronous in-engine; the host owns scheduling; sync is the preferred auto mode

The engine is daemonless (P1): fold runs inside the calling statement/transaction, and
asynchrony is a host thread/connection. For the host-SDK `add()` wrapper (D4), **sync
fold-on-insert is the preferred default** (owner decision): "window ≤ budget before the next
prompt" is worth the occasional slow turn.

### D3 — Chunked folding (v0.2 engine work)

The v0.1.0 plan returns the entire over-target backlog in one batch, which breaks
small-context summarizers (50k backlog vs a 5k-context model). Fix: bound each fold to a
chunk (`fold_chunk_tokens` knob / `max_batch :=` plan parameter, oldest-first); each chunk
folds into its own digest version (`summary(prev digest + chunk)`), so every LLM call is
bounded regardless of backlog. Catch-up is a documented, sequential host loop —
`while memory_fold_needed(): fold_chunk()` — ~N bounded iterations for an N-chunk backlog.
`memory_fold_needed` stays a stateless view (one row per over-budget session, not a queue),
but the catch-up work is equivalent to draining one; a crash mid-loop leaves valid state.
No schema change: digest versioning + `covers_turns_to` already express the chain.

### D4 — The mem0-parity `add()` lives in the host SDK; the raw SQL loop is the engine surface

No triggers + no DML in macros + no post-LOAD SQL closes the in-engine path for a
single-call insert-and-fold. The single-call experience is a thin host wrapper — insert turn
→ check window → fold if over budget — with `fold: off | sync | async` (`off` = deterministic
baseline; `sync` = mem0 parity, preferred; `async` = for hosts that refuse write-path
latency). The 3-call SQL loop remains documented as the engine surface; the wrapper is the
canonical integration pattern (e.g. the KAOS `Memory` backend).

### D5 — `memory_window(session)` observability macro (v0.2 engine work)

Transparency is the real requirement behind "compaction on insert": agents must see how full
the window is and how close compaction is. Pure-SQL macro (the `fold_needed` expression
without the `HAVING`): `unfolded_turns, unfolded_tokens, budget, pct_used,
tokens_over_target, digest_version`. The `add()` wrapper returns it on every write.

### D6 — Fold contract: digest always, facts 0..n; extraction and folding are independent primitives

The digest is the fold's correctness obligation (turns leaving the window stay represented,
verbatim fallback at minimum); facts are best-effort extraction output (zero from small talk
is legitimate). `memory_extract(text)` is an independent scalar, so three cadences are
supported: extract-at-fold (batched, the Layer-2 default), digest-only fold
(`extract := false`, today's P2 path), and **extract-per-turn + fold-for-compaction** —
mem0's fact freshness with our window management, each primitive at its own rhythm.

### D7 — Reconciliation: batched, scope-explicit, separate from fold — with the full pipeline recorded

mem0's write pipeline (per `add()`, inline): LLM-extract candidates → embed each →
per-candidate vector-search of scope neighbors → second LLM call classifies
`ADD/UPDATE/DELETE/NONE` → apply, history table records the change. Facts always clean;
writes cost 2+ LLM calls and seconds. agentmemory inverts it: writes are instant DML, fold
appends (ADD-only), and `memory_reconcile(for_user := ..., in_namespace := ...)` is a
separate batch pass — cluster near-duplicates by embedding similarity within the explicit
scope, LLM merges/resolves contradictions per cluster. Scope is explicit (mem0's is implicit
— whatever IDs were passed to `add()` filter the neighbor search; it has no "reconcile user
u1 now" operation). This matches KAOS-R7's operator-scheduled consolidation model, and
mem0's own (vendor-reported, unverified) move to ADD-only writes points the same direction.
Completeness of the trigger → extract → embed → reconcile chain is a tracked requirement for
the Layer-2 design.

### D8 — Audit: `mem.turns` is the provenance half; a fact mutation log ships with reconcile

mem0's history table and our short-term turns are only partially equivalent. Turns are the
*source* audit — what was said, forever; every appended fact traces to them. mem0's history
is a *mutation* log — per memory id, `old_memory → new_memory, event`. In an ADD-only world
the two coincide; the moment reconcile rewrites or merges facts, turns cannot say what a
fact used to state or why it changed. Decision: a `facts_history` table (or a
supersedes-pointer scheme) is a hard prerequisite **bundled into the reconcile PR** — not
standalone v0.2 work, and not needed before mutation exists.

### Renames (each its own PR, before the larger work)

- Tables: `mem.turns → mem.short_term_turns`, `mem.digests → mem.medium_term_summaries`,
  `mem.facts → mem.long_term_facts` (`_turns` chosen over `_window`: consistent with
  `_summaries`/`_facts`, naming what the rows are — the window is a state over the rows).
  One PR.
- Library: `agentmemory → agent_memory` (crate, extension name, repo surface). One PR.

### Doc fix

`examples/demo.sql` comment is stale ("memory_embed() arrives in a later phase" — it shipped
in P3); reword to present literal vectors as the self-contained-demo choice.

## Open — the facts-only / add()-first surface (mem0 1-1)

Question under design: what the interface looks like if the short- and medium-term tiers are
removed and `add()` becomes the first-class flow. Removal means the host owns its transcript
(as mem0 apps do); the unlock is that DML can call extension scalars. Three recorded
options, composing rather than competing:

- **Option A — SQL-native add (ADD-only):** one `INSERT ... SELECT ... FROM
  unnest(memory_extract(...))` statement = extract → embed → store, atomically.
  `search/get/get_all/update/delete/delete_all` are `memory_recall_text` + plain DML.
  Matches mem0's reported current ADD-only algorithm 1-1; no reconciliation (periodic
  `memory_reconcile`) and no history (D8).
- **Option B — inline reconcile via `MERGE INTO`:** candidates matched to existing facts by
  `array_cosine_similarity(...) > threshold` in the `ON` clause; `WHEN MATCHED THEN UPDATE /
  WHEN NOT MATCHED THEN INSERT`. Classic-mem0 ADD/UPDATE in one atomic statement. Deltas:
  match is a cosine threshold, not an LLM judgment (true parity needs a
  `memory_reconcile_op(candidate, neighbors)` scalar feeding the MERGE); DELETE ops don't
  fit one MERGE; **requires an empirical spike** (MERGE + similarity ON-condition semantics,
  multi-match behavior, DuckDB ≥1.4 feature).
- **Option C — SDK-first:** `agent_memory` client exposing the literal mem0 API
  (`add/search/get_all/update/delete/history`) over Options A/B SQL plus LLM op
  classification across statements in one transaction — the only route to full classic-mem0
  parity including LLM-decided UPDATE/DELETE/NONE and the history log.

Open sub-question (owner to decide): whether facts-only is a **mode** (profile of the same
library — tiers optional, `add()` first-class) or a **replacement**. Note that D5's window
transparency has no meaning without the short-term tier (mem0 cannot answer "how full is my
context?" either). The answer affects the table-rename PR.

## Consequences

- **Positive.** The Layer-2 seam now has a concrete cadence model (three supported rhythms,
  D6), a bounded-cost fold under any backlog (D3), the missing observability surface (D5),
  and a recorded, honest 1-1 mapping to both classic and current mem0 — with the engine/SDK
  split made explicit rather than accidental (D4, Option C).
- **Negative.** Full classic-mem0 parity (LLM-decided ops + history) cannot live purely in
  the SQL surface — it requires either the MERGE spike to pass (B) or the SDK layer (C);
  the renames are breaking changes and must land before adoption grows.
- **Follow-on.** PR sequence: table rename → library rename → demo.sql doc fix → D3+D5
  (chunked fold + `memory_window`) → Layer-2 extraction (`memory_extract`, fold
  orchestration per D6) → reconcile + `facts_history` (D7+D8). MERGE spike scheduled before
  committing to Option B.
