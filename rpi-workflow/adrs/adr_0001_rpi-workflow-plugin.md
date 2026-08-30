# ADR 0001 — RPI workflow plugin: skills, handoff, and verification

Status: accepted (2026-08-30). Baseline: [000-initial-request](./000-initial-request.md). Gate doc: [proposed-adrs](./proposed-adrs.md). Research: [findings 1](../research/research-findings-1-rpi-as-practiced.md), [findings 2](../research/research-findings-2-machinery-and-prior-art.md), [findings 3](../research/research-findings-3-verification-patterns.md).

## Context

The RPI (research → ADRs → plan → implement) workflow already works well when driven by hand with prompts. This plugin packages it as marketplace skills so each stage carries its guidance with it. Guiding constraint throughout: keep it simple — the model is smart enough to structure the work; the skills give initial structure and the non-negotiables, and stay proportionate to the size of the project. HumanLayer, the originators of RPI, drifted into a Golang CLI and 1000-line plans and later retracted much of it; we deliberately stay at the prompts-and-files level.

## Decision 1 — Plugin shape: one skill per stage

Skills in `plugins/workflow-automations/`: `new-project` (entry: capture scope, set up the docs directory) plus `rpi-research`, `rpi-adrs`, `rpi-plan`, `rpi-implement`. Each skill is a short recipe for its stage and ends by handing over (Decision 3).

Options considered: one monolithic skill (rejected: one doc carrying four stages blows the instruction budget — models reliably follow ~150–200 instructions and the original RPI failed partly on this); create/iterate skill pairs per stage as HumanLayer ships today (rejected: doubles the surface for little gain; iteration is just re-running the stage skill on the existing docs).

## Decision 2 — Docs live in `adr/<NNN>-<name>/` with a fixed stage layout

Each project effort gets a numbered folder, and the state IS the files — no databases, no state machinery. Worked example, which is also the resume mechanism (a fresh session looks at which files exist and offers the next step):

```
adr/001-design/
  research/
    proposed-research.md            # gate: approved before fan-out
    research-findings-1-<name>.md   # distilled, the part that is kept
    research-ref-1-1-<name>.md      # full captured source text (1-2, 2-1, ... as needed)
  adrs/
    proposed-adrs.md                # gate: which ADRs and which decisions
    adr_0001_<slug>.md
  plan/
    proposed-plan.md                # gate: phases, PR split, verification approach
    P1-<name>.md
  implement/
    learnings/
      L1-<topic>.md                 # captured comprehensively as implementation progresses
```

The `implement/learnings/` folder is deliberate: implementation surfaces reusable knowledge constantly (what broke, what the docs got wrong, what a harness should later assert) and it is written down as it happens, not reconstructed afterwards.

Options considered: the historical kaos-ai-docs layouts (rejected as-is: research across sections never standardised on naming — `KAOS-R<n>`, `00<n>`, bare `<n>` — so the plugin fixes one scheme); per-section conventions files (not needed: the convention lives in the skills).

## Decision 3 — Stage handover: explicit end, user chooses next

A stage ends explicitly: the skill presents what was produced, and the user either approves the gate doc, asks for changes, or picks the next stage. On approval the skill offers the handover ("research is done — kick off rpi-adrs?") rather than silently continuing. Gates always run in the main session, never inside subagents (the platform strips gate tooling from forked work, and skipped gates were the original RPI's biggest failure — the workflow only works if the stop is real).

## Decision 4 — Structure as guidance, not restriction

The skills give the initial structure (the layout above, the gate docs, the non-negotiables like "don't assume — validate paths that fork") but do not over-prescribe. Every project differs, and the effort must stay proportionate to the size of the feature: a small feature may collapse research to a single findings doc and one short ADR; a large one fans out subagents and runs parallel spikes. Spikes stay a judgement call prompted by the research and ADR skills ("if multiple viable paths exist, propose spikes"), not a formal encoded sub-pattern.

Option considered and rejected: encoding the full kaos-code-harness spike machinery (waves, gates, steer triggers) as a shared sub-skill — too much ceremony for the common case.

## Decision 5 — Verification: eager, iterative, manual-first

Planned explicitly in the plan stage and executed eagerly during implementation — never one massive verification section at the end. The working loop:

1. Manual first: quick scripts in the gitignored `./tmp`, run iteratively — never assume something works, run it. Hand over to the user early so things are proven to actually work before locking anything into tests.
2. Then a scripted smoke gate once the manual loop stabilises.
3. Then, where warranted, e2e: Playwright visual verification for UI-heavy work (see `create-streamlit-app`/`verify-streamlit-app` in this marketplace), kind-based cluster validation for Kubernetes work. Built from the accumulated learnings — the manual loop's discoveries are exactly what the harness later asserts.

Tests validate multi-step workflows, not that inputs equal outputs; "1+1=2" tests are avoided unless they explicitly make sense. Verification stays fast: parallelise once something takes too long, with a stated cap and reason. Each project keeps a short usage cheatsheet (how the thing is expected to be used), introduced in the ADRs and kept current through the plan and implementation.

The plugin's own skills are verified the same way: blind subagent runs on a toy project, reviewing the transcript for skipped gates and wasted context.

## Decision 6 — Docs are short and written like a human

Every doc in the workflow is short (a plan phase or ADR that approaches code-review cost has failed) but never cryptic: simple terms, plain sentences, nothing brushed away behind jargon. Short means dense and clear, not terse and obscure.

## Expected behaviour of a full run

`/new-project` captures scope and creates `adr/<NNN>-<name>/` with the initial-request record → `rpi-research` proposes areas, gates on `proposed-research.md`, fans out subagents, commits findings as they land → `rpi-adrs` gates on `proposed-adrs.md` (ideally one ADR unless the change has genuinely separable large parts), walks decisions one by one with the user, closes with a caveats summary → `rpi-plan` gates on `proposed-plan.md` with minimal phases and minimal-but-reviewable PRs, comprehensive commits, and the verification approach from Decision 5 → `rpi-implement` goes PR by PR with review between, parallelising where possible and writing `learnings/` as it goes. Every stage commits its docs comprehensively as they land.

## Caveats

- The "ideally one ADR" guidance is for projects using the plugin; a genuinely separable change (e.g. a large frontend next to a backend) still warrants more — the skill says so rather than hard-limiting.
- This effort's own docs predate Decision 2 and live in `kaos-ai-docs/rpi-workflow/` with a near-identical but not identical layout (`impl` vs `implement/learnings`); they stay where they are as history unless we choose to migrate.
- The resume rule depends on the layout being respected — if docs are placed outside the convention, a fresh session won't find them; the skills always write inside the project's `adr/<NNN>-<name>/` folder.
- `./tmp` must actually be gitignored in the target repo; the plan skill checks and adds it rather than assuming.
