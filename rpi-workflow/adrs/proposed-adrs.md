# Proposed ADRs — RPI workflow plugin

Status: **proposed (v2) — awaiting approval**. Baseline: [000-initial-request](./000-initial-request.md). Inputs: [findings 1](../research/research-findings-1-rpi-as-practiced.md), [findings 2](../research/research-findings-2-machinery-and-prior-art.md), [findings 3](../research/research-findings-3-verification-patterns.md).

## What this document is

This is the gate doc for the ADR stage: it proposes which ADRs will exist and which decisions each one maps, all derived from the research findings. The ADRs themselves do not exist yet — on approval of this doc they are created, and we then walk each decision one by one for your call (take the recommendation or override).

Disambiguation on "one ADR": the baseline's "ideally only 1 ADR unless the change has major separable parts" is a rule the *plugin encodes for future projects* (it lands inside the `rpi-adrs` stage skill as guidance). It is not automatically the right count for *this* design effort — that is decided here on its own merits, below.

Steer applied: keep it simple. The workflow already runs successfully as plain prompts, so the plugin is skill-per-stage guidance with file-based handoff — no CLI, no state machinery, no routers (HumanLayer's trajectory into a Golang CLI is explicitly what we avoid). The `writing-skills` principles govern how every skill is authored.

## Proposed ADR set

**Recommendation: two ADRs.** The plugin has two genuinely separable concerns — the workflow architecture (skills, handoff, gates) and the verification/quality approach (which cuts across the plan stage, the spike sub-pattern, and how the skills themselves are validated). Each stays well under the reviewability length budget flagged in findings 2.

- `adr_0001_workflow-architecture.md` — plugin shape, stage skills and handoff, docs-directory convention, approval gates. Maps D1–D3 and D6.
- `adr_0002_verification-and-quality.md` — spike sub-pattern, plan-stage verification ladder, blind-subagent validation of the skills themselves. Maps D4–D5.

Alternatives: one ADR covering all six decisions (simplest, but D1–D6 in one doc crowds the review); three or more (over-split for a plugin this size — no third separable concern exists). If you prefer one, D4–D5 fold into adr_0001 as sections.

## Decisions (all derived from the research; each gets options + pros/cons in the ADR body)

- **D1 — Plugin shape.** Options: (a) one skill per stage (`new-project` entry + `rpi-research`, `rpi-adrs`, `rpi-plan`, `rpi-implement`), each ending by handing over to the next; (b) one monolithic skill; (c) HumanLayer-style create/iterate pairs per stage. **Recommendation: (a)** — matches how you already run this as prompts, keeps each skill within a small instruction budget (findings 2: ~150–200 followable instructions; CRISPY stages stay under 40), and each stage skill remains usable standalone.
- **D2 — Handoff and docs-directory convention.** The state IS the files; no platform convention exists (findings 2), so we define it: fixed `research/ adrs/ plan/` layout, `proposed-<stage>.md` gate docs, `research-findings-<n>-<name>.md` + `research-ref-<n>-<m>-<name>.md`, `adr_NNNN_<slug>.md`, resume rule = look at which files exist, suggest the next skill. **Recommendation: adopt exactly this convention** (it is what this very effort is running), shown examples-first in the ADR as a worked directory tree with doc skeletons.
- **D3 — Approval gates.** **Recommendation: prose gates in the main session only** — each stage skill ends with an explicit stop presenting the proposal doc and waiting for the user. Platform constraint (findings 2): gate tooling is stripped from subagents, so gates never live inside forked work. No mechanism beyond the prose stop.
- **D4 — Spikes as a shared sub-pattern.** **Recommendation: encode the kaos-code-harness spike pattern once** (waves, gates, steer triggers, self-limits, findings-beat-artifacts) in a shared doc referenced via progressive disclosure from both the research and ADR stage skills, so neither stage assumes when multiple viable paths exist.
- **D5 — Verification encoding in the plan stage.** **Recommendation: the three-tier manual-first ladder from findings 3** — ad-hoc `./tmp` scripts run iteratively → scripted smoke gate → opt-in e2e (Playwright visual / kind) — plus workflow-shaped tests over input-equals-output tests, parallelisation past a threshold with a stated cap, and a usage cheatsheet introduced in the ADRs and kept current per landed PR.
- **D6 — Expected behaviour and length budgets.** **Recommendation: per-doc length budgets** (short ADRs and plans — findings 2: 1000-line plans cost as much to review as code) and a worked end-to-end example of a full run as the expected-behaviour spec.

## Spikes

None. S1 is answered by findings 2 plus the simplicity steer; S2 collapses into D2; S3 (gate reliability) is replaced by `writing-skills` blind-subagent runs of each stage skill on a toy project, which becomes part of D5.

## Process after approval

Create the two ADRs → walk D1–D6 one by one for your decision → close with a caveats summary of anything that could be misread.
