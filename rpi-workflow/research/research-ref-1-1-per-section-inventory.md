# Research ref 1.1 — per-section inventory (RPI-as-practiced survey)

Full captured survey material backing [research-findings-1-rpi-as-practiced.md](./research-findings-1-rpi-as-practiced.md). Light pass only — directory listings, gate-doc identification, and CONVENTIONS.md/SPIKE-PLAN.md full text where read; research/ADR bodies were not deep-read per scope.

## Sections surveyed and their directory shape

| Section | `research/` | `adrs/` | `plan/` | `impl/` | CONVENTIONS.md | Follows RPI shape |
|---|---|---|---|---|---|---|
| [`memory/`](../../memory/) | yes, `KAOS-R<n>` | yes, `adr_NNNN_<slug>` | yes, `M<n>` + `proposed-split.md` | yes | yes, section root | full |
| [`duckmemory/`](../../duckmemory/) | yes, `DUCK-R<n>` | yes, `adr_NNNN_<slug>` | yes, `proposed-split.md` only (no per-phase files found) | via `learnings/` | yes, section root | full |
| [`security-and-identity/`](../../security-and-identity/) | yes, bare `00<n>` | yes, split `adr-kaos/`/`adr-aib/` `ADR-KAOS-<n>`/`ADR-AIB-<n>` | yes, `P<n>` + `proposed-split.md` | yes | yes, section root (ADR-scoped only) | full, with ADR-owner fork; also has a dedicated `target-picture/` directory |
| [`security-and-identity-2/`](../../security-and-identity-2/) | yes, bare `00<n>`, restarts at 1 | yes, `adr_NNNN_<slug>` (drops the owner-split fork) | yes, `P<n>` continuing parent numbering (`P18`, `P19`) + `proposed_split.md` (underscore) | yes | none found | full, sequel to `security-and-identity/` |
| [`evals/`](../../evals/) | yes, `KAOS-E<n>` | yes, `adr_NNNN_<slug>` | yes, `P<n>` + `proposed-split.md` | yes | yes, section root | full |
| [`ethical-institute-rebrand/`](../../ethical-institute-rebrand/) | yes, topic-named (no numeric prefix) | yes, `adr-NNN-<slug>` (3-digit, hyphenated) | yes, `proposed-split.md`, milestones inline (no per-phase files) | none (impl in a separate downstream repo) | yes, nested at `research/conventions.md` | full, most divergent numbering |
| [`xai/`](../../xai/) | yes, bare `<n>`, stage `0` reserved for index/plan | yes, `adr_NNNN_<slug>` + `library-interface-overview.md` | yes, `proposed-split.md` + `S<n>` spike files | yes, `impl/learnings/` | none (conventions inlined in `research/0-research-plan.md`) | full, explicitly modeled on `memory/` |
| [`mcp-runtime-extensions/`](../../mcp-runtime-extensions/) | no | no | flat `PLAN-MCP-EXTENSION.md` + `PLAN-MCP-EXTENSION-DESIGN.md` at section root | no | no | none — predates/outside RPI convention |
| [`kaos-code-harness/`](../../kaos-code-harness/) | no | no | no | no | no | none as directories, but `SPIKE-PLAN.md` → `spikes/` → `RESULTS.md` is the fullest spike-pattern precedent in the corpus |
| [`kaos-autonomous-blog/`](../../kaos-autonomous-blog/), [`pydantic-ai-server/`](../../pydantic-ai-server/), [`pydantic-ai-server-post/`](../../pydantic-ai-server-post/), [`otel-blogpost/`](../../otel-blogpost/) | no | no | flat `PLAN-*`, `REPORT-*`, `BLOGPOST_*`, `PROGRESS.md`, `TODO.md` filenames at section root | n/a | no | none — ad hoc content-production sections, not design/build efforts |

## Gate-doc census

- `memory/research/`: [`KAOS-R7-target-picture.md`](../../memory/research/KAOS-R7-target-picture.md) — last of 7 base research docs (`R1`…`R7`), later extended by `R8`–`R11` follow-ons for the decision phase.
- `evals/research/`: [`KAOS-E7-target-picture.md`](../../evals/research/KAOS-E7-target-picture.md) — same pattern as memory, also has `KAOS-E0-research-index.md` as a separate index doc (evals is the one section with both an index-0 doc and a target-picture-7 doc).
- `security-and-identity/target-picture/`: 7 sequential docs (`001`…`007`) culminating in a "decision: identity model and source of truth" doc, then formalised as `adr-kaos/ADR-KAOS-000-target-picture.md` — the only section where the target picture is itself an ADR rather than a research doc.
- `xai/research/`: [`0-research-plan.md`](../../xai/research/0-research-plan.md) — written first (stage 0), not last; functions as both an index and a living status tracker (updated with a "Campaign results" addendum as spikes complete), closest analogue to what `proposed-research.md` should evolve into after approval rather than a static proposal.
- `duckmemory/`, `security-and-identity-2/`, `ethical-institute-rebrand/`: no distinct gate doc; `adr_high_level_components.md` (or `research/conventions.md` for the rebrand) informally carries synthesis duties.

## `plan/proposed-split.md` — shared content shape (verified in 4 of 7 instances read in full or in part)

Header block (Status / Date / Scope, with links to the ADRs and research baseline realised), a "Purpose" section stating the doc proposes sequencing not detail, a "Guiding principles for the split" bullet list, a "Current-state baseline (what already exists)" section, then "The proposed phases" with one subsection per phase (Goal / Scope / Realises / Depends on / Outputs / Demoable), each phase pointing at its own `<prefix><n>-<slug>.md` file for task-level detail. Confirmed in [`memory/plan/proposed-split.md`](../../memory/plan/proposed-split.md) and [`evals/plan/proposed-split.md`](../../evals/plan/proposed-split.md) (read in full); structure matches by grep/skim in `security-and-identity`, `duckmemory`, `xai`. `ethical-institute-rebrand/plan/proposed-split.md` diverges in form (no per-phase files, milestones inline, PR-structure-first framing) because its constraint is different — `master` deploys straight to GitHub Pages, so it explicitly rejects PR-per-phase as overhead. This is the one clearly-justified divergence found, cited in Finding 10 as the model for "diverge for a legible reason."

## CONVENTIONS.md — verbatim-shared clauses (source: `memory/`, `duckmemory/`, `evals/`, `security-and-identity/`, full text read)

Shared near word-for-word across `memory/CONVENTIONS.md`, `duckmemory/CONVENTIONS.md`, `evals/CONVENTIONS.md`:
- "**No hard line wraps inside paragraphs or list items.** Write each paragraph and each list item as a single continuous line and let the editor/renderer soft-wrap. Manual mid-sentence newlines break reading flow and create noisy diffs."
- "Separate paragraphs, list blocks, headings, tables, and code fences with blank lines."
- "Do not reference phases, tasks, plan steps, or TODO numbers in document bodies. Describe the work by what it is, not by its position in a process." (present in `memory/`, `duckmemory/`, `evals/`; absent from `security-and-identity/CONVENTIONS.md`, which is scoped only to ADR cross-referencing)
- "Commit one document per commit using comprehensive conventional commit messages in the `docs(<section>): …` form."
- Cross-reference rule: always link, never leave a bare `KAOS-R0X`/`DUCK-R0X`/etc. reference unlinked (except self-reference).

`security-and-identity/CONVENTIONS.md` is scoped narrowly: ADR numbering (`ADR-KAOS-<n>` vs `ADR-AIB-<n>`, independent sequences, `ADR-KAOS-000` as target-picture entry point), cross-reference rules, markdown style, and a terminology-lock paragraph pinning "enforcement is gateway-centric... out of scope (not future hardening)" against ADR-KAOS-000 — a section-specific guard against drift, not a generic template clause.

`xai/research/0-research-plan.md` "Phase order and conventions" section (no separate CONVENTIONS.md) states the same no-hard-wrap and no-phase-self-reference rules, plus section-specific ones: research doc numbering (`<n>-<name>.md`, spikes as `S<n>`), spike code lives in the *source* repo's gitignored `./tmp/`, one-doc-per-commit `docs(xai): …`, no session-URL trailer.

## `kaos-code-harness` spike-pattern — full text captured

[`SPIKE-PLAN.md`](../../kaos-code-harness/SPIKE-PLAN.md) (94 lines) and [`RESULTS.md`](../../kaos-code-harness/RESULTS.md) (~80 lines, verified sections) were read in full; their content is distilled into Finding 8 of the findings doc rather than reproduced here again. Key structural elements confirmed by direct read: "Ground rules" section (byte-sized commits, worktrees for parallel tracks, ~45 min self-limit, findings beat artifacts, negative results are results); three numbered waves each with Question/Deliverables/Gate/Steer-trigger subsections; `RESULTS.md`'s verdict table, "assumptions that were wrong" section, "recommended sequence," "deferred deliberately," and "what was not verified" closing sections.

## Not read (out of scope for this light pass)

Research/ADR document *bodies* (e.g. the content of `KAOS-R1`…`R11`, `adr_0001`…`adr_0008`, `security-and-identity-2`'s numbered research docs, `xai`'s stages 1–13) were not deep-read — only their filenames, numbering, and (for gate docs) opening sections were inspected, per the Area 1 scope ("No deep reading of the research/ADR bodies themselves"). `kaos-autonomous-blog/`, `otel-blogpost/`, `pydantic-ai-server/`, `pydantic-ai-server-post/` were listed but not opened — their flat, non-staged file naming (`REPORT-*`, `BLOGPOST_*`, `PLAN-*`) was visible from `ls` alone and confirms they sit outside the RPI convention entirely (blog/report production workflows, not research→ADR→plan→impl design efforts), so no further reading was warranted for this task.
