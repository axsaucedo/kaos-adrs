# Research findings 1 — the RPI workflow as practiced

Status: distilled findings from a light survey of `research`/`adrs`/`plan`/`impl` directories across [`memory/`](../../memory/), [`duckmemory/`](../../duckmemory/), [`security-and-identity/`](../../security-and-identity/), [`security-and-identity-2/`](../../security-and-identity-2/), [`evals/`](../../evals/), [`ethical-institute-rebrand/`](../../ethical-institute-rebrand/), [`xai/`](../../xai/), [`mcp-runtime-extensions/`](../../mcp-runtime-extensions/), and [`kaos-code-harness/`](../../kaos-code-harness/). Full survey material is in [research-ref-1-1-per-section-inventory.md](./research-ref-1-1-per-section-inventory.md). Area 1 of [proposed-research.md](./proposed-research.md); baseline is [000-initial-request](../adrs/000-initial-request.md).

## Finding 1 — the four-stage shape is consistent, but only seven of twelve surveyed sections actually practice it

`memory/`, `duckmemory/`, `security-and-identity/`, `security-and-identity-2/`, `evals/`, `ethical-institute-rebrand/`, and `xai/` all follow the same directory shape: `research/` → `adrs/` → `plan/` → `impl/` (with `impl/learnings/` for spike/phase writeups). `xai/research/0-research-plan.md` states this explicitly: "This docs area follows the same structure and order as the `memory/` effort in this repository." The other five sections surveyed (`mcp-runtime-extensions/`, `kaos-autonomous-blog/`, `kaos-code-harness/`, `pydantic-ai-server(-post)/`, `otel-blogpost/`) predate or sit outside the RPI convention — `mcp-runtime-extensions/` is a single flat `PLAN-*.md` pair with no `research/`/`adrs/` split, and the blog/report sections use ad hoc `REPORT-*`/`BLOGPOST_*`/`PLAN-*` filenames with no stage directories at all. `kaos-code-harness/` is the odd one out: it has no `research/`/`adrs/`/`plan/` directories, but its `SPIKE-PLAN.md` → `spikes/` → `RESULTS.md` triad is exactly the spike/validation sub-pattern the RPI plugin needs to encode (see Finding 5).

## Finding 2 — every section gates ADRs on a research-side index/target-picture doc, but the gate doc's name is never the same twice

Every RPI-shaped section has one research document that functions as the ADR-stage gate — the point where scattered numbered research collapses into a single decision-ready picture — but no two sections name it the same way:

| Section | Gate doc | Filename pattern |
|---|---|---|
| `memory/` | [KAOS-R7-target-picture.md](../../memory/research/KAOS-R7-target-picture.md) | last numbered research doc, suffixed `-target-picture` |
| `evals/` | [KAOS-E7-target-picture.md](../../evals/research/KAOS-E7-target-picture.md) | same pattern, different prefix letter |
| `security-and-identity/` | [target-picture/](../../security-and-identity/target-picture/) directory, 7 docs, culminating in `ADR-KAOS-000-target-picture.md` | a whole sub-stage, not one doc — the target picture is itself ADR-000 |
| `xai/` | [0-research-plan.md](../../xai/research/0-research-plan.md) | stage **0**, an index-and-plan doc written first, not last |
| `duckmemory/`, `security-and-identity-2/`, `ethical-institute-rebrand/` | no distinct gate doc found | the last numbered research file or `adr_high_level_components.md` implicitly serves the role |

There is no `proposed-research.md`-equivalent file in any surveyed section's `research/` directory — the "propose research areas for approval" step that `000-initial-request.md` specifies for the new plugin has **no precedent in the practiced-history sections**; it appears to be a refinement introduced with the `rpi-workflow` effort itself (this section's own `proposed-research.md` is the first instance found in the corpus).

## Finding 3 — the plan stage's gate doc is the one thing that did standardise: `proposed-split.md` (or a `_` variant)

Every RPI-shaped section's `plan/` directory opens with a `proposed-split.md` (`security-and-identity-2/` spells it `proposed_split.md`, an underscore/hyphen slip) — see [memory](../../memory/plan/proposed-split.md), [duckmemory](../../duckmemory/plan/proposed-split.md), [evals](../../evals/plan/proposed-split.md), [security-and-identity](../../security-and-identity/plan/proposed-split.md), [security-and-identity-2](../../security-and-identity-2/plan/proposed_split.md), [ethical-institute-rebrand](../../ethical-institute-rebrand/plan/proposed-split.md), [xai](../../xai/plan/proposed-split.md). This is the single most consistent gate-doc convention across the entire corpus, and it matches `000-initial-request.md`'s `proposed-plan.md` naming closely enough that the plugin should standardise on `proposed-split.md` (matching seven-for-seven practiced instances) over the ADR's own `proposed-plan.md` wording, or reconcile the two explicitly. Its content shape is also consistent: status/date/scope header, "purpose" section stating it proposes sequencing not detail, a "guiding principles for the split" list (validate-first, bottom-up, one-phase-one-PR, mocks-break-upstream-dependencies, build-on-what-exists), a "current-state baseline" section, then the phase list with `<n>-<slug>.md` per-phase plan files.

## Finding 4 — per-phase plan numbering diverges even within the same convention: `M<n>` vs `P<n>` vs `S<n>` vs bare `<n>`

| Section | Phase-file prefix | Example |
|---|---|---|
| `memory/` | `M<n>` (milestone) | `M0-feasibility-validation.md` … `M8-…` |
| `evals/` | `P<n>` (phase) | `P1-eval-library-and-runner.md` |
| `security-and-identity/` | `P<n>` | `P0-feasibility-validation.md` … `P17-…` |
| `security-and-identity-2/` | `P<n>`, continuing the parent numbering | `P18-agent-plane-pdp-and-issuers.md`, `P19-…` |
| `xai/` | `S<n>` (spike), separate from the numeric research stages | `S1-trace-ingestion.md` … `S8-…` |
| `ethical-institute-rebrand/` | `Milestone <letter>` inline in one doc, no per-phase files | `Milestone A`, `A'`, `B`, `C`, `D` |

`M`/`P` are interchangeable in intent (both mean "one phase = one plan-implement iteration = one PR, stacked") — the letter tracks the section's own vocabulary ("milestone" vs "phase") rather than a meaningful distinction. `security-and-identity-2` is notable as the one case of numbering continuing across a section boundary (`P18` picks up after `security-and-identity/`'s `P17`), showing the convention supports sequels. `xai` is the outlier: its `S<n>` files are spikes gating ADRs, not implementation phases — a third role (`0`-prefixed research index, `<n>` research stages, `S<n>` spikes) layered onto the same directory.

## Finding 5 — research-stage numbering never standardised on a single prefix, and per-tool/per-component deep-dives always get a compound suffix

| Section | Research prefix | Deep-dive compound suffix |
|---|---|---|
| `memory/` | `KAOS-R<n>` | `KAOS-R5-<n>-<toolname>` (e.g. `KAOS-R5-1-mem0.md`) |
| `evals/` | `KAOS-E<n>` | `KAOS-E5-<n>-<toolname>` |
| `duckmemory/` | `DUCK-R<n>` | none observed (project too small) |
| `security-and-identity/` | bare `00<n>` | none — flat numbered list |
| `security-and-identity-2/` | bare `00<n>`, restarting from 1 | none |
| `xai/` | bare `<n>`, plus `deep-research-prompts/` sub-dir for externally-delegated deep research | none, but stage `0` is reserved for the index/plan |
| `ethical-institute-rebrand/` | no numbering, topic-named files (`homepage-deltas.md`, `mdx-composition-decision.md`) | n/a |

The `KAOS-<letter><n>` prefix (project-initials + stage number) is `memory/`'s and `evals/`'s convention and does not appear anywhere else — it reads as a two-instance pattern, not yet a corpus-wide standard. `security-and-identity-2` restarting its research numbering at `001` rather than continuing `security-and-identity`'s `008` (while its **plan** stage does continue the sequence, per Finding 4) shows research numbering resets per section-generation even when plan numbering doesn't — the two stages are not bound to the same numbering discipline. The plugin's own dogfooding convention in `proposed-research.md` (`research-findings-<n>-<name>.md` / `research-ref-<n>-<m>-<name>.md`) matches nothing in the practiced corpus exactly; it is closest to `memory/`'s `KAOS-R5-<n>-<toolname>` compound-suffix idea generalised to every area, plus a distinct findings/ref split that no surveyed section makes (sections keep raw research and distilled research in the same numbered file).

## Finding 6 — ADR numbering and directory shape is the most stable convention, with one structural fork

Five of six sections with ADRs use `adr_NNNN_<slug>.md` (zero-padded four digits, snake_case slug) plus a non-numbered `adr_high_level_components.md` index: `memory/`, `duckmemory/`, `security-and-identity-2/`, `evals/`, `xai/` (`xai/adrs/` additionally has `library-interface-overview.md`, an examples-first interface doc alongside the ADRs — the clearest precedent for `000-initial-request.md`'s "examples-first, interfaces" ADR requirement). `security-and-identity/` (v1) forks this: it splits ADRs into two owner-prefixed sequences, `adr-kaos/ADR-KAOS-<n>-<slug>.md` and `adr-aib/ADR-AIB-<n>-<slug>.md` (see its [CONVENTIONS.md](../../security-and-identity/CONVENTIONS.md)), with `ADR-KAOS-000` doubling as the target-picture entry point (Finding 2). `security-and-identity-2/` (v2, same problem domain) drops the owner split and the `000`-as-target-picture pattern entirely and returns to the plain `adr_0001_…` shape — i.e. the project's own second generation abandoned its predecessor's structural fork. `ethical-institute-rebrand/` uses a third shape, `adr-NNN-<slug>.md` (hyphenated, three-digit, no leading zero-pad to four).

## Finding 7 — CONVENTIONS.md is present in most sections and the content that repeats verbatim is the load-bearing signal

`memory/CONVENTIONS.md`, `duckmemory/CONVENTIONS.md`, `evals/CONVENTIONS.md` are near-identical in structure (Scope → Numbering → Cross-references → Context discipline → Markdown style → Commits) and share near-verbatim clauses:
- "No hard line wraps inside paragraphs or list items… let the editor/renderer soft-wrap" — appears word-for-word in all three, and as the first mandatory convention in this very task's brief. This is the single most consistently-enforced convention in the corpus.
- "Do not reference phases, tasks, plan steps, or TODO numbers in document bodies. Describe the work by what it is, not by its position in a process." — appears in all three, absent from `security-and-identity/CONVENTIONS.md` (which is scoped only to ADR numbering, not the whole pipeline) and unwritten-but-followed in `xai/`.
- "Commit one document per commit using comprehensive conventional commit messages in the `docs(<section>): …` form" — appears in all three and matches `000-initial-request.md`'s "all research must be registered with comprehensive commits as it lands."
- "Context discipline" (re-read exact source files per stage rather than relying on conversation history; record in-scope/out-of-scope inputs) appears in `memory/` and `evals/` but not `duckmemory/` — likely because `duckmemory/` is a smaller, single-threaded effort where curation isn't yet a problem.

`security-and-identity/CONVENTIONS.md` is scoped narrowly to ADR cross-referencing and terminology-locking ("enforcement is gateway-centric... out of scope, not future hardening") rather than the whole pipeline — a reminder that CONVENTIONS.md's job varies by section rather than having one fixed shape. `ethical-institute-rebrand/research/conventions.md` is nested inside `research/` rather than at the section root, and `security-and-identity-2/`, `xai/`, `kaos-code-harness/` have no CONVENTIONS.md at all — `xai/` instead embeds its conventions inline in `0-research-plan.md`'s "Phase order and conventions" section.

## Finding 8 — the spike pattern is fully formed in `kaos-code-harness/` and echoed loosely elsewhere, but only that section names it a first-class artifact

[`kaos-code-harness/SPIKE-PLAN.md`](../../kaos-code-harness/SPIKE-PLAN.md) → `spikes/` → [`RESULTS.md`](../../kaos-code-harness/RESULTS.md) is the fullest expression of the spike discipline `000-initial-request.md` asks for, and it is the pattern to lift wholesale:
- **Waves and gates**: spikes grouped into dependency-ordered waves (wave 1 picks the harness; wave 2 runs three architecture spikes in parallel worktrees against wave 1's pick; wave 3 depends on wave 2's answer). Each spike states a **Question**, **Deliverables**, and a pass/fail **Gate** before it starts.
- **Steer triggers**: named in advance — "If `pi` turns out to lack a usable non-interactive mode... Codex CLI becomes the scaffold and waves 2–3 rebuild against it" — matching this very task's brief's own "steer triggers" vocabulary.
- **Self-limits**: "~45 minutes of active work per spike. Past that, write down where it got to and what blocked it," worded almost identically to `proposed-research.md`'s "~30 min" self-limit for research areas — the self-limit convention is itself inherited/scaled from this spike pattern.
- **Worktrees**: "Each wave-2 spike runs on its own branch in its own worktree off `kaos-ai-docs`, merged back to `main` for review when its gate passes" — parallel tracks are isolated by git worktree, not just by subagent.
- **Findings-beat-artifacts / negative-results-are-results**: stated as explicit ground rules — "A spike's deliverable is `FINDINGS.md`. Code exists to make the findings honest, not to be reused" and "'This does not work, here is exactly where it breaks' is a passing spike." `RESULTS.md` then delivers on this: it leads with a verdict table, dedicates a top section to "The two assumptions that were wrong" (a design draft's load-bearing assumptions falsified by spike evidence), and closes with an explicit "What was not verified" section — negative/uncertain findings kept as first-class content, not hidden.

Elsewhere, the spike idea appears diluted into the phase-gate discipline itself rather than as a separate artifact type: `memory/plan/proposed-split.md`'s M0 phase ("Validate first (M0), then build... not throwaway scaffolding — it is real, runnable checks that gate the build") and `evals/plan/proposed-split.md`'s "opens with an engine-validation task whose findings gate the rest of the phase" both fold spike-like validation into phase 0/task 1 of the plan stage rather than running it as a pre-ADR spike wave. `xai/plan/`'s `S<n>-*.md` files (Finding 4) are the one other place spikes get dedicated files, and their results land in `impl/learnings/` rather than a single consolidated `RESULTS.md`. The plugin should treat "spike wave with named gates + steer triggers + self-limit + FINDINGS.md + worktree isolation" as a reusable sub-skill invocable from any stage (research, ADR, or plan), not something bolted only onto research as `000-initial-request.md`'s wording might suggest.

## Finding 9 — `./tmp/` for manual/scripted verification and gitignored spike scratch space is universal and never named differently

Every section that runs validation code puts it under a gitignored `./tmp/` (or `./tmp/<section>/`) in the *source* repository being worked on, never in `kaos-ai-docs` itself: `memory/plan/proposed-split.md`'s M0 ("artifacts live in `./tmp/memory/`, gitignored; findings written to `impl/learnings/`"), `evals/plan/proposed-split.md`'s engine-validation task ("working checks in `./tmp/evals/`"), `xai/research/0-research-plan.md`'s spike rule ("Runnable validation code lives under the source repo's `./tmp/` (gitignored)... Suppress noise to `./tmp/null`, never `/tmp`"), `kaos-code-harness/SPIKE-PLAN.md`'s worktree-per-spike rule. This matches the user's own global `~/.claude/CLAUDE.md` convention verbatim ("Whenever you want to create tmp files, always create them under `./tmp`... Similarly you can use `./tmp/dev/null` instead of `/dev/null`") — the practiced convention and the global instruction are the same rule, reinforcing it as non-negotiable for the plugin.

## Finding 10 — what the plugin should standardise vs leave flexible

Standardise (sticky across nearly every RPI-shaped section, low cost to enforce, high value as shared vocabulary):
- Four-stage directory shape `research/` → `adrs/` → `plan/` → `impl/` (`impl/learnings/`, `impl/progress/`).
- `plan/proposed-split.md` as the plan-stage gate doc, with its established content shape (Finding 3).
- `adr_NNNN_<slug>.md` + `adr_high_level_components.md` index as the ADR default, with the owner-split fork (Finding 6) offered as an explicit alternative only when the ADR body genuinely separates by owner/component.
- The CONVENTIONS.md content that repeats verbatim: no hard line wraps, no phase/step self-reference in body text, one-doc-per-commit `docs(<section>): …`, context discipline (curate inputs per stage, don't just inherit conversation).
- `./tmp/` for all scratch/spike code in the source repo, never `/tmp`.
- The spike sub-pattern from `kaos-code-harness/` as a named, reusable unit: waves, explicit gates, named steer triggers, ~30–45 min self-limits, `FINDINGS.md`/`RESULTS.md` as the deliverable, worktree isolation for parallel tracks, negative results kept as first-class content.

Leave flexible (diverged every time without apparent cost, or diverged for a legible reason):
- Research-stage file-prefix scheme (`KAOS-R<n>`, `DUCK-R<n>`, bare `00<n>`, bare `<n>`, topic-named) — let each project pick a short prefix once at kickoff and stay consistent within itself; do not force a marketplace-wide prefix.
- Plan-stage phase-file prefix (`M<n>` vs `P<n>` vs `S<n>`) — cosmetic; both mean the same "one phase = one PR" unit.
- Whether a distinct research-stage gate doc exists at all, and what it's called (`*-target-picture.md`, a `target-picture/` sub-stage, a stage-`0` index, or none) — depends on whether the research is large enough to need a synthesis checkpoint before ADRs; small efforts (`duckmemory/`) skip it without apparent harm.
- CONVENTIONS.md's presence/location/scope — some sections need a dedicated file, others (small, single-threaded) get by with conventions inlined in the research-plan doc; `security-and-identity/`'s narrowly-scoped ADR-only conventions file shows the file's job is whatever a section actually needs guarded, not a fixed template.
