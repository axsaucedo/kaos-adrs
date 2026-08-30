# Research ref 2-1 — HumanLayer: the original RPI, and its successor CRISPY

Captured material for [Area 2](proposed-research.md) sub-track 1. Full text and verbatim extracts; the distilled version lives in [research-findings-2-machinery-and-prior-art](research-findings-2-machinery-and-prior-art.md).

## 0. Attribution: HumanLayer, not Humanloop

The initial request refers to the originators as "HumanLoop". That is a misattribution. The research-plan-implement (RPI) workflow was created and popularised by **HumanLayer** (Dex Horthy), the company behind [12-factor agents](https://github.com/humanlayer/12-factor-agents). **Humanloop** is an unrelated LLM evaluation/prompt-management platform (humanloop.com) with no connection to RPI. All sources below are HumanLayer.

Primary sources:

- Essay + repo: <https://github.com/humanlayer/advanced-context-engineering-for-coding-agents> (`ace-fca.md`, "Getting AI to Work in Complex Codebases"), blog mirror <https://www.humanlayer.dev/blog/advanced-context-engineering>
- Talk: "Advanced Context Engineering for Coding Agents" (YC, 20 Aug 2025) <https://hlyr.dev/ace>
- Talk: "Everything We Got Wrong About RPI" (Mar 2026) <https://hlyr.dev/qrspi-mlops>, secondary write-up <https://www.zenml.io/llmops-database/evolving-ai-coding-agent-workflows-from-research-plan-implement-to-crispy>
- Original prompts: <https://github.com/humanlayer/humanlayer/blob/main/.claude/commands/> — `research_codebase.md`, `create_plan.md`, `implement_plan.md`
- Current packaging: <https://docs.humanlayer.com/reference/skills-workflows>, plugin repo <https://github.com/humanlayer/riptide-rpi>, multi-repo template <https://github.com/humanlayer/rpi-coordination-template>
- Later essay: `wsff.md` "Why Software Factories Fail" in the same ACE repo

## 1. The original RPI (Aug 2025) — as stated in ace-fca.md

The framing is **"frequent intentional compaction" (FCA)**: RPI is not the point, context management is. Verbatim:

> Essentially, this means designing your ENTIRE WORKFLOW around context management, and keeping utilization in the 40%-60% range (depends on complexity of the problem).

> the contents of your context window are the ONLY lever you have to affect the quality of your output.

Optimise the context window for, in order: **Correctness, Completeness, Size, Trajectory**. The worst things that can happen to a context window, in order: **Incorrect Information, Missing Information, Too much Noise**.

The three stages, verbatim:

> **Research** — Understand the codebase, the files relevant to the issue, and how information flows, and perhaps potential causes of a problem.
>
> **Plan** — Outline the exact steps we'll take to fix the issue, and the files we'll need to edit and how, being super precise about the testing / verification steps in each phase.
>
> **Implement** — Step through the plan, phase by phase. For complex work, I'll often compact the current status back into the original plan file after each implementation phase is verified.

Notable qualifiers stated in the same section: the split is "three (ish) steps" — "sometimes we skip the research and go straight to planning, and sometimes we'll do multiple passes of compacted research before we're ready to implement." Only implementation needs a git worktree; "we tend to do everything else on main."

The human-review leverage argument (the core reason for the gates):

> A bad line of a **plan** could lead to hundreds of bad lines of code. And a bad line of **research**, a misunderstanding of how the codebase works... could land you with thousands of bad lines of code.

Subagents are explicitly framed as a context-control device, not role-play:

> Subagents are not about playing house and anthropomorphizing roles. Subagents are about context control.

> The most common/straightforward use case for subagents is to let you use a fresh context window to do finding/searching/summarizing that enables the parent agent to get straight to work without clouding its context window with `Glob` / `Grep` / `Read` / etc calls.

Compaction targets are named explicitly — what eats context: "Searching for files; Understanding code flow; Applying edits; Test/build logs; Huge JSON blobs from tools." Compaction is "simply distilling them into structured artifacts."

Artifacts are stored in a `thoughts/` directory managed by a "thoughts tool" (`humanlayer thoughts init|status|sync`), synced to a separate repo; `thoughts/shared/research/`, `thoughts/shared/plans/`, `thoughts/<user>/tickets/`, plus a `thoughts/searchable/` hard-link mirror for grep.

## 2. The original prompts, in detail

### 2.1 `research_codebase.md` (213 lines, `model: opus`)

Structure: a slash command whose entire job is documentation, with an aggressive anti-opinion guard at the top:

> ## CRITICAL: YOUR ONLY JOB IS TO DOCUMENT AND EXPLAIN THE CODEBASE AS IT EXISTS TODAY
> - DO NOT suggest improvements or changes unless the user explicitly asks for them
> - DO NOT perform root cause analysis unless the user explicitly asks for them
> - DO NOT propose future enhancements unless the user explicitly asks for them
> - DO NOT critique the implementation or identify problems
> - ONLY describe what exists, where it exists, how it works, and how components interact

Flow: (1) emit a fixed ready-message and **wait for the user's research query** — an explicit stop-and-wait gate at the top of the stage; (2) read any user-mentioned files FULLY in the main context *before* spawning subagents ("Use the Read tool WITHOUT limit/offset parameters"); (3) decompose the question and spawn **parallel Task subagents**; (4) wait for ALL subagents before synthesising; (5) gather metadata via `hack/spec_metadata.sh`; (6) write the doc; (7) rewrite local file refs as GitHub permalinks; (8) `humanlayer thoughts sync` and present a summary; (9) append follow-ups to the same document rather than creating new ones.

The subagents are **named custom agents with fixed roles**, defined in `.claude/agents/`: `codebase-locator` (WHERE things live), `codebase-analyzer` (HOW code works), `codebase-pattern-finder` (existing examples), `thoughts-locator` / `thoughts-analyzer` (prior docs), `web-search-researcher` (external, only if the user explicitly asks; must return LINKS), plus `linear-ticket-reader` / `linear-searcher`. Prescribed usage order: locators first, then analyzers on the promising findings. The prompt tells the parent **not** to write detailed how-to-search prompts — "the agents already know" — and repeats the documentarian constraint for subagents too. The ACE essay notes the same command also exists in a generic form using the plain `Task()` tool with `general-agent`, which "works almost as well".

Artifact naming: `thoughts/shared/research/YYYY-MM-DD-ENG-XXXX-description.md` (ticket segment omitted when there is no ticket). YAML frontmatter carries `date`, `researcher`, `git_commit`, `branch`, `repository`, `topic`, `tags`, `status`, `last_updated`, `last_updated_by`. Body sections: Research Question, Summary, Detailed Findings, Code References (`path:line`), Architecture Documentation, Historical Context (from thoughts/), Related Research, Open Questions.

Repeated instructions worth stealing: "Always use parallel Task agents to maximize efficiency and minimize context usage"; "Keep the main agent focused on synthesis, not deep file reading"; "NEVER write the research document with placeholder values"; "Always run fresh codebase research — never rely solely on existing research documents."

### 2.2 `create_plan.md` (449 lines, `model: opus`)

Explicitly interactive and adversarial. Opening posture: "You should be skeptical, thorough, and work collaboratively with the user."

Five steps, each with a gate: (1) read all mentioned files fully, spawn locator/analyzer subagents, then **present understanding plus only the questions research could not answer** — "Only ask questions that you genuinely cannot answer through code investigation"; (2) research and discovery, where if the user corrects a misunderstanding, "DO NOT just accept the correction — spawn new research tasks to verify"; then present **Design Options 1..N with pros/cons plus Open Questions** and ask which aligns; (3) present a **phase outline only** and ask "Does this phasing make sense?" *before* writing details — a cheap structural gate; (4) write the full plan to `thoughts/shared/plans/YYYY-MM-DD-ENG-XXXX-description.md` using a fixed template; (5) sync, present the location, and iterate on feedback.

The plan template sections: Overview, Current State Analysis, Desired End State, Key Discoveries (with `file:line`), **What We're NOT Doing** (explicit scope fence), Implementation Approach, then `## Phase N` blocks each containing Changes Required (file-by-file, with code), and Success Criteria split into two named buckets:

> #### Automated Verification: (`make migrate`, `make test-component`, `npm run typecheck`, `make lint`, `make test-integration`)
> #### Manual Verification: (feature works via UI, performance under load, edge cases, no regressions)
>
> **Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

Then Testing Strategy (unit / integration / manual steps), Performance Considerations, Migration Notes, References (ticket, research doc, similar implementation `file:line`).

Hard rule at the end:

> **No Open Questions in Final Plan**: If you encounter open questions during planning, STOP. Research or ask for clarification immediately. Do NOT write the plan with unresolved questions. Every decision must be made before finalizing the plan.

Subagent fan-out best practices given verbatim: spawn multiple in parallel; each focused on one area; provide exactly-what-to-search / which-directories / what-to-extract / expected-output-format; "Be EXTREMELY specific about directories" (name `humanlayer-wui/`, not "UI"); specify read-only tools; request `file:line` references; wait for all; spawn follow-ups if results look wrong. Also: automated steps "should use `make` whenever possible".

### 2.3 `implement_plan.md` (84 lines, no model pin)

Much shorter and deliberately prose-y rather than checklist-y. Reads the plan **including existing `- [x]` checkmarks**, so a fresh session resumes purely from the file: "If the plan has existing checkmarks: trust that completed work is done; pick up from the first unchecked item." Checkboxes are ticked in the plan file itself with Edit, making the plan file the durable progress ledger.

Mismatch protocol:

> If you encounter a mismatch: STOP and think deeply about why the plan can't be followed. Present the issue clearly: Issue in Phase [N] / Expected / Found / Why this matters / How should I proceed?

Per-phase human gate, verbatim template:

> Phase [N] Complete - Ready for Manual Verification / Automated verification passed: … / Please perform the manual verification steps listed in the plan: … / Let me know when manual testing is complete so I can proceed to Phase [N+1].

Plus: "If instructed to execute multiple phases consecutively, skip the pause until the last phase. Otherwise, assume you are just doing one phase." And "do not check off items in the manual testing steps until confirmed by the user." Notably: "Use sub-tasks sparingly" during implementation — fan-out is a research/plan-stage tool, not an implementation-stage tool.

## 3. What HumanLayer says went wrong with RPI — and CRISPY (Mar 2026)

From "Everything We Got Wrong About RPI" (<https://hlyr.dev/qrspi-mlops>; write-up at <https://www.zenml.io/llmops-database/evolving-ai-coding-agent-workflows-from-research-plan-implement-to-crispy>). The stated failure modes of the original three-stage RPI:

1. **Research produced opinions, not facts.** Handing a ticket straight to a research agent made the model "generate opinions rather than objective facts". Fix: a separate, earlier stage that produces *research questions* in its own context window, so implementation opinions cannot contaminate research.
2. **The "magic words" problem.** ~50% of the time the planning agent skipped the interactive step and emitted a whole plan unprompted; users had to paste incantations like "work back and forth with me starting with your open questions" to get the intended behaviour. Fix: make the interaction its own stage rather than an instruction inside a bigger prompt.
3. **Instruction budget exhaustion.** Frontier models can consistently follow roughly **150–200 instructions**; an 85-instruction planning prompt plus system prompt, tool definitions and MCP configs blew the budget, so instructions were followed only partially. Fix: decompose into stages of **under 40 instructions each**.
4. **Plans were too long to review.** Plans ran ~1000 lines — comparable to the code — and the implemented code diverged from them, so reviewers had to read both. Review cost of a plan approached review cost of code, without the value.
5. **"Don't read the code" was wrong.** The original advice not to read AI-generated code was explicitly retracted; production experience required system replacements. Engineers should read and own the code, especially in regulated or paying-customer systems.

**CRISPY** — the seven-stage successor. The acronym is Context, Research, Iterate, Structure, Plan, sYnthesize, Implement:

| # | Stage | Purpose | Artifact | Budget |
|---|---|---|---|---|
| 1 | Context (questions) | Deterministically generate the research questions | research question list | <40 instructions |
| 2 | Research | Objective facts about the codebase, via deep vertical slices, using subagents | factual codebase documentation | <40 |
| 3 | Iterate (design discussion) | Early human/agent alignment on patterns and decisions | ~200-line markdown: current state, desired state, patterns, resolved decisions, open questions | <40 |
| 4 | Structure (outline) | Vertical plan with testing checkpoints, "analogous to C header files" | ~2-page structure outline | <40 |
| 5 | Plan | Tactical implementation detail | detailed plan | <40 |
| 6 | sYnthesize (work tree) | Set up worktrees / phase the work | code work breakdown | <40 |
| 7 | Implement | Write the code | PR with complete context | <40 |

Gates named: **design-discussion review** (the highest-leverage one — reviewing the ~200-line design document is described as "5x better leverage than reviewing a 1,000-line plan"; catches deprecated patterns before any code exists), **structure-outline approval** (verify vertical phasing and testing checkpoints), and **distributed decision-making** (code owners review the design discussion, front-loading alignment). Design-discussion review is stated as where "you catch 80% of the problems".

Context strategy: multiple context windows rather than one long conversation, with decisions written into "static markdown artifacts that can be reloaded into fresh context windows".

## 4. Current packaging (Aug 2026): a plugin of one skill per stage, create/iterate pairs

Source: <https://docs.humanlayer.com/reference/skills-workflows> and <https://docs.humanlayer.com/guide/skills-workflows>.

Four selectable **workflows** over a shared skill catalogue:

| Workflow | Phases | Artifact output |
|---|---|---|
| RPI | questions, research, design discussion, structure outline, implementation, PR | multiple `NN-` prefixed artifacts |
| PRD-Oriented | questions, research, PRD, TDD, structure outline, implementation, PR | includes PRD and TDD variants |
| Oneshot | implementation, PR | implements straight from `ticket.md` |
| Freeform | none | no structured artifacts |

Selection guidance: Oneshot when the task is "small and the correct result is clear"; RPI when it needs research and design discussion; PRD-oriented when product and technical design must be separated; Freeform otherwise.

**22 skills**, namespaced `rpi:`, in deliberate **create/iterate pairs** — one skill to produce the artifact, a sibling skill to revise the same artifact in place:

- `/rpi:create-research-plan` → `NN-research-questions-<slug>.md`; `/rpi:iterate-research-questions`
- `/rpi:create-research` → `NN-research-<slug>.md`; `/rpi:iterate-research`
- `/rpi:create-design-discussion` → `NN-design-discussion-<slug>.md`; `/rpi:iterate-design-discussion`
- `/rpi:create-prd` → `NN-prd-<slug>.md` (+ optional `mockup-<description>.html`); `/rpi:iterate-prd`
- `/rpi:create-tdd` → `NN-tdd-<slug>.md` (+ optional `diagram-<description>.html`); `/rpi:iterate-tdd`
- `/rpi:create-outline` → `NN-structure-outline-<slug>.md`; `/rpi:iterate-outline`
- `/rpi:create-plan` → `NN-plan-<slug>.md` (legacy RPI path); `/rpi:iterate-plan`
- `/rpi:configure-workspace` → `.humanlayer/workspace.json` (+ `.humanlayer/workspace.local.json`)
- `/rpi:create-worktree` → worktrees, task branches, copied files
- `/rpi:implement-plan` / `/rpi:implement-outline` → code, tests, commits, progress written back into the plan or outline
- `/rpi:iterate-implementation` → fixes to code and tests
- `/rpi:describe-pr` → GitHub PR, `pr-description.md`, optional `pr-walkthrough.html`
- `/rpi:ci-commit` → one or more focused git commits
- `/rpi:review-artifact-comments` → applies review comments back into an artifact

**Handoffs** (stated explicitly): Design → Outline is a *manual checkpoint* (feedback does not trigger implementation); PRD → TDD requires TDD creation; Outline/Plan → Implementation depends on a worktree timing setting; Implementation → PR hands off to `/rpi:describe-pr` automatically.

**Artifact precedence, later wins**: Plan > Structure Outline > TDD > PRD > Design Discussion > Research > Ticket. This is the conflict-resolution rule that lets a fresh session read a whole task directory without ambiguity.

Session continuity is explicitly file-based: "before you switch sessions, write every current decision from this session into the artifact", then "start a new session with the matching `/rpi:iterate-*` skill" and include the feedback in the prompt.

### 4.1 `humanlayer/riptide-rpi` — the shipped plugin skeleton

<https://github.com/humanlayer/riptide-rpi>. Layout is the standard Claude Code plugin marketplace shape: `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `skills/<name>/SKILL.md`. Install is `/plugin marketplace add humanlayer/riptide-rpi` then `/plugin install riptide-rpi@humanlayer-riptide-rpi`.

The one public skill, `rpi-setup-humanlayer`, is instructive as an **entry-point/router skill**. Its description is written to capture every phrasing of the trigger:

> use this skill when a user asks to set up RPI or a "research plan implement" workflow, or to do anything related to RPI skills. if the user says the acronym "RPI" or "rpi" or "humanlayer", you MUST use this skill! Example questions - "I want to set up rpi for ticket eng-1234" - "Whats the next rpi step for eng-5678"

Its body is (a) a hard **prerequisite gate** — check `which humanlayer`, `which linear`, `humanlayer thoughts status`, `humanlayer thoughts sync`, then print a test permalink — before anything else; (b) a task-setup path: fetch the ticket, `mkdir -p thoughts/tasks/eng-1234-description`, write `ticket.md` into it, then **tell the user which skill to invoke next** rather than invoking it; (c) a **status/resume path**: "Find task dir; List contents; Based on which files exist, suggest the next skill to use."

That last line is the whole cross-session handoff mechanism in one sentence: *the set of files present in the task directory is the state machine*. There is no database and no session state — the `NN-` numeric prefixes give order, the filenames give stage, and precedence resolves conflicts.

### 4.2 `humanlayer/rpi-coordination-template` — multi-repo RPI

<https://github.com/humanlayer/rpi-coordination-template> (updated Aug 2026). A sibling "coordination repo" cloned next to the working repos, from which all sessions are run; `.claude/settings.json` lists the others under `permissions.additionalDirectories`. Its `CLAUDE.md` is written entirely in **`<important if="...">` conditional blocks** keyed to the skill currently in use — the same technique as their `improve-claude-md` skill:

> `<important if="you are using the rpi:create-research skill">` Check to ensure the repos in question have the latest from the git remote… propose pull commands to the user
>
> `<important if="you are using the rpi:setup-worktree skill">` You will need to create worktrees for each repo mentioned in the task plan…

Worktree layout: a `workspaces/<task-slug>/` directory holding a worktree per involved repo plus a worktree of the coordination repo, with implementation run from the coordination worktree.

## 5. Later position: "Why Software Factories Fail" (wsff.md)

Same repo, more recent. Argues against the "lights-off software factory" framing (no human reads or writes code) — citing Faros AI data that PR review quality is down and incidents up since broad agent adoption, and the Stanford productivity study showing AI-shipped "extra code" is largely rework and that agents can be net-negative in large brownfield codebases. Relevant to this effort as a caution: the value is in the *review gates*, not in removing humans from the loop. Talk lineage listed there: ACE (Aug 2025) → "No Vibes Allowed" → "Everything We Got Wrong About RPI" (Mar 2026).

## 6. Derived observations for our plugin

- Our proposed four stages (research → ADRs → plan → implement) are RPI plus an explicit decision stage. HumanLayer's **design discussion** (stage 3 of CRISPY) is functionally our ADR stage: options, patterns, resolved decisions, open questions, ~200 lines, reviewed by code owners before any plan exists. Their measured claim that this is the highest-leverage gate is direct support for the ADR stage existing at all.
- Their `proposed-*` equivalent is the **research-questions artifact** produced by a dedicated stage — the same idea as our `proposed-research.md`, but generated in a separate context window specifically so the researcher cannot smuggle in opinions.
- Our request's "not 1+1=2 tests" and "manual verification" instincts map onto their Automated/Manual success-criteria split plus the per-phase pause-for-human-verification block, which is battle-tested prompt text we can adapt nearly verbatim.
- The **<40 instructions per stage** budget is the strongest argument against a single monolithic `/new-project` skill that carries all four stages.
- The **create/iterate skill pair** per stage is a pattern we do not currently have and which directly solves "resume mid-stage in a fresh session".
- The **artifact precedence order** and **`NN-` numeric prefixes** are cheap conventions that make a docs directory self-describing; our `research-findings-<n>` / `research-ref-<n>-<m>` naming already leans this way.
