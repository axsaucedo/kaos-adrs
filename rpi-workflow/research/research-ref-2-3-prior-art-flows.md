# Research ref 2-3 — Prior art in phased / spec-driven agent workflows

Captured material for [Area 2](proposed-research.md) sub-track 3. Repos were read at HEAD in August 2026: superpowers at `b36e082` (v6.3.0, 2026-08-12), spec-kit at `51e52be` (post-1.0.0, 2026-08-28), OpenSpec v1.11.0. Distilled version in [research-findings-2-machinery-and-prior-art](research-findings-2-machinery-and-prior-art.md).

## 1. obra/superpowers (Jesse Vincent)

<https://github.com/obra/superpowers>

**Stages.** README "Basic Workflow": brainstorming → using-git-worktrees → writing-plans → subagent-driven-development (SDD) *or* executing-plans → test-driven-development → requesting-code-review → finishing-a-development-branch.

Brainstorming is a **three-path router** (new in v6.3): classify the task aloud, then take one of:

- **Spike** — a feasibility question. Answer, not code. No documents; anything built is labelled throwaway.
- **Bounded** — a well-scoped change to existing code: clarifying questions → short design *in chat* → approval → implement. Explicitly "No spec file, no implementation plan document."
- **Architectural** — nine steps: explore context → clarifying questions one at a time → propose 2–3 approaches with a recommendation → present the design section-by-section with approval after each → write the design doc → spec self-review → user reviews the spec → invoke writing-plans.

Ratchet rule: "When in doubt between two paths, take the heavier one. The ratchet is one-way" — discovering hidden complexity upgrades the path mid-task; nothing ever downgrades.

**Gating.** The core mechanism is a `<HARD-GATE>` block:

> Do NOT invoke any implementation skill, write any code… until you have told your human partner what you intend and they have approved it… **the ceremony scales with the task; the approval gate never does**.

Plus an explicit anti-pattern: "'Too Simple To Need Approval' — What scales with simplicity is the artifact, never the approval."

Approval prompts are **scripted verbatim**, e.g. the execution handoff menu: "Plan complete and saved to `docs/superpowers/plans/<filename>.md`. Two execution options: 1. Subagent-Driven (recommended)… 2. Inline Execution… Which approach?" — and a finishing menu (merge locally / push+PR / keep branch).

Crucially, **inside execution the human gate is deliberately removed**: "Rulings, not stalls. A running plan does not wait on a human." Only irreversible, destructive, security-relevant or outside-worktree actions stop it; every autonomous decision is ledgered as `Ruling: <what> — <why> — <cost if wrong>` and rolled up into a single "Rulings I made" list at the end. A separate verification-before-completion skill states: "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE… Skip any step = lying, not verifying."

**Artifacts.** Design/spec at `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` (committed). Plan at `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` with a mandatory header (Goal, Architecture, Tech Stack, Spec path, Global Constraints) and a per-task template carrying `**Files:** Create/Modify/Test` and `**Interfaces:** Consumes/Produces` with exact signatures — because the implementer subagent sees only its own task. Ephemeral SDD workspace at `.superpowers/sdd/<plan-basename>/` holding `progress.md` (ledger), `task-N-brief.md`, `task-N-report.md` and review packages; self-gitignored and deleted after a clean final review. Shell helpers: `sdd-workspace`, `task-brief`, `review-package`.

**Packaging.** Surprising and directly relevant: **no slash commands and no agent definitions**. 14 skills plus one `SessionStart` hook (matcher `startup|clear|compact`) that injects the full text of the dispatcher skill `using-superpowers/SKILL.md` (~485 words) into every session — "If you think there is even a 1% chance a skill might apply… you ABSOLUTELY MUST invoke the skill", and "Before entering plan mode: if you haven't already brainstormed, invoke the brainstorming skill first". Skills chain by name via `**REQUIRED SUB-SKILL:**` markers. Frontmatter convention is exactly `name` + `description` (≤1024 chars, third person, starting "Use when…"). A `<SUBAGENT-STOP>` guard at the top of the dispatcher stops the mandate recursing into workers. Subagent role prompts are sibling markdown files (`implementer-prompt.md`, `task-reviewer-prompt.md`) rather than `agents/` definitions. Per-harness shims exist (`.codex-plugin/`, `.cursor-plugin/`, …).

**Adopt.** The constant-approval / scaling-artifact principle; the three-path router; the SessionStart-injected dispatcher; artifacts-as-files ("everything you paste into a dispatch prompt… stays resident in your context — hand artifacts over as files"; subagents return under 15 lines and write the rest to disk); the plan-scoped recovery ledger, motivated by "controllers that lost their place have re-dispatched entire completed task sequences — the single most expensive failure observed"; "rulings, not stalls" with the auditable roll-up; explicit model-per-role dispatch ("turn count beats token price"); the writing-skills rule that a description must not summarise the workflow, because agents then shortcut straight from the description.

**Avoid.** 20,748 words across 14 skills (SDD alone is 4,825 words plus 476 lines of prompt templates); the five-round fix loop with model-tier escalation and a three-outcome "breaker" state machine most tasks never enter; the O(n²) pre-flight task-pair conflict scan; five separate review surfaces per feature; five near-identical "rationalization tables"; absolute TDD ("delete code written before the test"); the visual-companion browser subsystem; plans that inline complete code (you write the implementation twice); the escalating shouty "Iron Law" register — it works there because it is empirically grounded, but borrowed tone without the evidence is just noise.

## 2. github/spec-kit

<https://github.com/github/spec-kit>

**Stages.** `/speckit.constitution` (one-time; a semver-bumped `.specify/memory/constitution.md` with a "Sync Impact Report") → `/speckit.specify` → `/speckit.clarify` (optional) → `/speckit.plan` (Phase 0 `research.md`; Phase 1 `data-model.md` + `contracts/` + `quickstart.md`; a Constitution Check gate before Phase 0, re-checked after Phase 1) → `/speckit.tasks` → `/speckit.analyze` (optional, strictly read-only) → `/speckit.checklist` (optional) → `/speckit.implement` → `/speckit.converge`.

`/speckit.converge` is new and interesting: an **append-only reconciliation** pass that assesses the code against spec/plan/tasks and appends a `## Phase N: Convergence` section of typed gap tasks (`missing | partial | contradicts | unrequested`) with source refs like `FR-003`. If the state has converged, `tasks.md` must be "byte-for-byte unchanged".

**Gating.** Layered:

- `NEEDS CLARIFICATION` markers, **hard-capped at 3** in `/specify`, with an explicit *don't-ask* list ("Make informed guesses… data retention, performance targets, error handling, auth method") and a priority order (scope > security > UX > technical).
- `/clarify`: **max 5 questions, exactly one at a time**, each multiple-choice (2–5 options) with a "Why it matters" line and `**Recommended:** Option [X]` so the user can simply say "yes". Answers are written incrementally into a `## Clarifications / ### Session YYYY-MM-DD` block.
- A self-validating `checklists/requirements.md` (16 fixed items, max 3 self-review iterations).
- The Constitution Check gate in the plan template, plus a Complexity Tracking table for justified violations. Note the drift: the famous Nine Articles / "Phase -1 gates" survive only in `spec-driven.md` prose; the shipped constitution template is now blank `[PRINCIPLE_N]` placeholders.
- The one genuine hard stop: `/implement` scans checklists and, if any items are unchecked, "**STOP** and ask: 'Some checklists have unchecked items. Do you want to proceed anyway? (yes/no)'". Checkbox marks are **reviewer-owned** — the agent is forbidden from ticking them.
- Clear write-capability partitioning per command: `/analyze` cannot write, `/implement` cannot tick boxes, `/converge` can only append.

**Artifacts.** `specs/NNN-short-name/` (3-digit sequential or timestamp prefix; the branch name is decoupled via `.specify/feature.json`), containing `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, `tasks.md`, `checklists/`. ID conventions: `FR-001` requirements, `SC-001` success criteria, `US1/P1` prioritised independently-testable story slices, `T001` tasks with `[P]` parallel markers and mandatory file paths. Tests are now **optional** ("only include them if explicitly requested"). Volume: roughly 600 lines of templates plus 2,400 lines of command prompts.

**Packaging.** A Python CLI: `uv tool install specify-cli`, `specify init --integration claude`. For Claude Code it now materialises **skills** (`.claude/skills/speckit-specify/SKILL.md`), not commands. 40+ integrations with per-tool format rewriting; a four-layer template resolution (project overrides > presets > extensions > core); extension hooks (`before_specify`, `after_plan`, …) in `.specify/extensions.yml`; role bundles.

**Adopt.** Question budgets with recommended defaults plus the don't-ask list; question-quality rules ("never use a topic label as the question"); converge-as-append-only reconciliation with typed gaps; read-only vs mutating command partitioning; reviewer-owned checkboxes as the human gate; artifact-directory / branch-name decoupling; `[P]` markers and P1 MVP slices; tech-agnostic success-criteria examples.

**Avoid.** ~400 lines of extension-hook boilerplate pasted into nearly every command prompt (a sixth of the instruction surface, dead weight if you have no extensions); a 252-line tasks template that is mostly sample content the command is then told to delete; an 11-category ambiguity taxonomy that yields at most 5 questions plus a coverage table nobody reads; a 60-line hardcoded gitignore table inside `/implement`; checklist proliferation needing paragraphs to explain which checkbox semantics apply to which file; the hollowed-out constitution (three commands ceremonially load a placeholder file, with an explicit "skip gracefully if unfilled" escape hatch); and, most importantly, a six-command minimum path producing 7+ artifacts with **nothing that scales the ceremony down to task size**.

## 3. OpenSpec (Fission-AI/OpenSpec)

<https://github.com/Fission-AI/OpenSpec>, v1.11.0, npm `@fission-ai/openspec`. Note `/openspec:proposal|apply|archive` are legacy; the current surface is `/opsx:*`.

**Stages.** Core profile: `/opsx:explore` → `/opsx:propose` → `/opsx:apply` → `/opsx:update` → `/opsx:sync` → `/opsx:archive`. Artifact flow inside a change: proposal → specs → design → tasks → implement, i.e. "why / what / how / steps". An expanded profile adds `new/continue/ff/verify/bulk-archive/onboard`.

**Gating.** Deliberately **none** — "fluid not rigid… enablers, not gates." Artifact dependencies are an advisory YAML DAG (`requires: [proposal]`), pluggable via `openspec schema fork` (the workflow itself is data). The only controls are a prompt-level "Planning boundary" in the propose skill (produce planning artifacts only, then *stop and wait for a new user request* before applying — even if the original prompt said "build it"); `openspec validate [--strict|--archived]` (structural; `--archived` fails if archived changes have unchecked tasks, designed as a pre-commit hook); and archive *warning* on incomplete tasks. Real gating is delegated to the git PR flow.

**Artifacts.** The structural idea nobody else has: a persistent `openspec/specs/<domain>/spec.md` as source of truth, plus `changes/<change-id>/` containing **delta specs** with `## ADDED / MODIFIED / REMOVED Requirements` sections. Archiving folds the delta into the living spec and moves the change to `changes/archive/YYYY-MM-DD-<name>/`. Spec format: `### Requirement:` with SHALL statements and `#### Scenario:` GIVEN/WHEN/THEN, plain markdown, RFC-2119. Per change: `proposal.md`, optional `design.md`, `tasks.md` (hierarchical `- [ ] 1.1`), and `.openspec.yaml` escape hatches (`skip_specs: true` for refactors). Specs are behaviour contracts, not implementation plans; "progressive rigor" — Lite by default, Full for cross-team/API/security work.

**Packaging.** An npm CLI as the engine; `openspec init` generates skills and slash commands for 30+ tools (`.claude/commands/opsx/*.md`, `.cursor/commands/`, `.github/prompts/`, Gemini TOML, …), and `openspec update` regenerates them. Skills call the CLI (`allowed-tools: Bash(openspec:*)`) rather than reimplementing it — CLI is the engine, skills are the steering wheel. Everything supports `--json` for agent consumption.

**Adopt.** Delta specs merging into a persistent truth (everyone else's per-feature specs go stale); the specs / changes / archive lifecycle; validate-as-pre-commit; schema-as-data; escape hatches so the process never forces a fake spec.

**Avoid.** ~7,700 lines of overlapping docs for what is a markdown convention; 13-command surface creep (propose/new/ff/continue all mean "make the artifacts", and the core/expanded profile split exists to hide this); a `design.md` that is often redundant; zero enforcement, so nothing stops an agent skipping straight to code; telemetry on by default.

**Vs spec-kit**, in OpenSpec's own words: "Thorough but heavyweight. Rigid phase gates, lots of Markdown, Python setup. OpenSpec is lighter and lets you iterate freely." Concretely: no gates vs a forward-only pipeline; deltas vs full per-feature specs; no constitution; a living spec corpus after archive vs feature folders that never merge back.

## 4. Claude Code plan mode as a gate

Sources: <https://code.claude.com/docs/en/permission-modes>, `/hooks`, `/tools-reference`, `/sub-agents`, `/skills`, `/plugins-reference`, `/settings-reference`, `/workflows`.

**Mechanics.** Plan mode is a *permission mode* (Shift+Tab cycle, `--permission-mode plan`, a `/plan` prompt prefix, or the `defaultMode` setting), not a tool allowlist. Reads and read-only shell are allowed; edits are blocked until the `ExitPlanMode` approval prompt, whose options are yes+auto / yes+manual-approve / no-keep-planning. `Ctrl+G` opens the plan in `$EDITOR`. There is also an `EnterPlanMode` tool the model can call itself.

**The plan IS persisted to disk** — contrary to common belief. Claude writes it to a file before calling `ExitPlanMode`; hooks receive both `plan` and `planFilePath`; the location is the `plansDirectory` setting (default `~/.claude/plans`, and it can be set to `./plans` in-repo). What is *not* tracked is any multi-stage state.

**Limits as a gate.** Single-shot: plan → approve → the mode switches. There is no per-phase gating built in, but re-entry is cheap, so a staged workflow is N plan-mode round trips. Three constraints matter enormously for a plugin:

- `ExitPlanMode` is stripped from subagents unless the agent frontmatter sets `permissionMode: plan`, **and plugin-shipped agents cannot set `permissionMode` at all** (it is ignored for security reasons).
- `EnterPlanMode` is always stripped from subagents, so a skill running with `context: fork` also cannot raise the gate.
- `ExitPlanMode` blocks in headless `-p` mode.
- In sessions where bypassPermissions is available, plan mode is **advisory only** — the blocks are not enforced.

**Hooks integration.** There is no dedicated plan-approval event, but `PreToolUse` matches `ExitPlanMode` and can deny with a reason to force replanning — this is how a plugin can *enforce* stage preconditions on the native gate. `PostToolUse` delivers the approved plan plus its file path. Hooks can call `setMode` to push the session back into `plan` at a stage boundary. `AskUserQuestion` is the structured-choice primitive for menu-style approvals.

**How the other tools relate to it.** superpowers *wraps* plan mode: after writing its own plan file it enters plan mode, summarises into the native plan, and calls `ExitPlanMode` so the native Approve panel renders it (<https://github.com/obra/superpowers/issues/1260>). spec-kit and OpenSpec treat repo files as the system of record and plan mode as an optional confirmation surface.

Also worth noting as the closest built-in multi-stage primitive: the first-party `workflows/` plugin component, which does JS orchestration of phased background subagents with its own approval card.

## 5. Others, briefly

- **AWS Kiro** (<https://kiro.dev/docs/specs/>): `.kiro/specs/<feature>/{requirements.md, design.md, tasks.md}` with EARS-format requirements ("WHEN … THE SYSTEM SHALL …") and Mermaid designs, plus always-loaded steering docs `.kiro/steering/{product,tech,structure}.md`. Real per-phase human approval (Requirements → Design → Tasks), a "Quick Spec" bypass for small work, and concurrent task "waves". Proprietary IDE. Adopt: EARS discipline, steering docs, the Quick Spec down-scaling valve.
- **cc-sdd** (<https://github.com/gotalab/cc-sdd>): Kiro as a portable skill pack (`npx cc-sdd`, 8 platforms): `/kiro-discovery → spec-init → requirements → design → tasks → impl`, per-phase approval plus per-task independent review, mandated TDD. Medium-high ceremony.
- **BMAD-METHOD** (<https://github.com/bmad-code-org/BMAD-METHOD>): six agent personas (analyst/PM/architect/SM/dev/QA), `docs/{prd.md, architecture.md, stories/}`. The signature mechanic is **sharding** the PRD and architecture so each story file carries only its context slice. Gates are persona-handoff checklists. Highest ceremony of the set; sharding is the transferable idea.
- **Agent OS** (<https://buildermethods.com/agent-os>): extracts standards *from* your codebase and injects them on demand. Low ceremony, weak docs, no gate mechanism.

## 6. Comparison

| Tool | Stages | Gate mechanism | Artifact naming | Packaging | Ceremony | Steal this |
|---|---|---|---|---|---|---|
| **superpowers** | brainstorm (3-path router) → worktree → write-plan → SDD/execute → review → finish | prompt-level `<HARD-GATE>` + scripted verbatim approval menus; native plan mode wrapped for the final gate; no gates *during* execution ("rulings, not stalls") | `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`, `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`, ephemeral `.superpowers/sdd/<plan>/` ledger + briefs | pure skills + one SessionStart hook injecting a dispatcher skill; no commands, no `agents/` | high (20k+ words) | constant approval / scaling artifact; router; ledger; artifacts-as-files subagent handoff |
| **spec-kit** | constitution → specify → clarify → plan → tasks → analyze → implement → converge | capped NEEDS-CLARIFICATION (≤3) + ≤5-question `/clarify` with recommended defaults; constitution check; reviewer-owned checkboxes → hard STOP in `/implement` | `specs/NNN-slug/{spec,plan,research,data-model,tasks}.md`, `contracts/`, `checklists/`; FR-/SC-/T-/US- IDs, `[P]` markers | Python CLI (`uvx specify init`) materialising per-tool skills/commands for 40+ agents | high | question budgets + don't-ask list; append-only `/converge`; read-only vs mutating partitioning |
| **OpenSpec** | explore → propose → apply → update → sync → archive | none by design — advisory schema DAG, prompt "planning boundary", `validate --strict/--archived`, git PR as the real gate | `openspec/specs/<domain>/spec.md` (living truth) + `changes/<id>/{proposal,design,tasks}.md` + delta specs (ADDED/MODIFIED/REMOVED) → `changes/archive/` | npm CLI engine + generated skills/commands for 30+ tools | low-med | delta specs folding into a persistent spec corpus; schema-as-data; escape hatches |
| **Claude plan mode** | single plan → approve (re-enterable per stage) | native `ExitPlanMode` UI; hookable via `PreToolUse` deny; advisory in bypass sessions; unavailable to plugin subagents and forked skills | plan file in `plansDirectory` (default `~/.claude/plans`, settable to `./plans`) | built-in; plugins add hooks/skills/workflows around it | low | use as the per-stage approval *surface*; enforce via `PreToolUse(ExitPlanMode)` |
| **Kiro / cc-sdd** | (discovery →) requirements → design → tasks → impl | explicit human approval per phase; "Quick Spec" bypass; per-task review (cc-sdd) | `.kiro/specs/<f>/{requirements,design,tasks}.md` (EARS) + `.kiro/steering/` | proprietary IDE / `npx cc-sdd` skill pack | med-high | EARS acceptance criteria; steering docs; the Quick Spec down-scaling valve |
| **BMAD** | clarify → plan → build+verify → learn (persona handoffs) | persona handoff checklists | `docs/{prd,architecture}.md` (sharded) + `docs/stories/*.md` | `npx bmad-method install` | highest | context sharding for per-story briefs |
