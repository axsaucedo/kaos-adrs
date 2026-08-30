# Proposed ADRs — RPI workflow plugin

Status: **proposed — awaiting approval**. Baseline: [000-initial-request](./000-initial-request.md). Inputs: [findings 1](../research/research-findings-1-rpi-as-practiced.md), [findings 2](../research/research-findings-2-machinery-and-prior-art.md), [findings 3](../research/research-findings-3-verification-patterns.md).

Steer applied from review of the research: keep it simple. The workflow already runs successfully as plain prompts, so the plugin is skill-per-stage guidance with file-based handoff — no CLI, no state machinery, no routers (HumanLayer ended up building a Golang CLI; we explicitly avoid that trajectory). The `writing-skills` principles (radical simplicity, steps-as-recipe, progressive disclosure) govern how every skill is authored.

## Proposed ADR set: one ADR

Per the baseline's "ideally only 1 ADR": the plugin is one coherent component (a set of stage skills sharing one docs-directory convention), with no separable large parts. **`adr_0001_rpi-plugin-skills-and-handoff.md`** covers everything. The reviewability concern from findings 2 (large artifacts stop being reviewable) is handled with a length budget on the ADR itself, not by splitting into more ADRs.

## Decisions the ADR will map (each: options → pros/cons → recommendation)

- **D1 — Plugin shape.** Options: (a) one skill per stage (`/new-project` entry + `rpi-research`, `rpi-adrs`, `rpi-plan`, `rpi-implement`), each ending by handing over to the next; (b) one monolithic skill; (c) HumanLayer-style create/iterate skill pairs per stage. Leaning (a): matches how the workflow is actually run as prompts, keeps each skill under a small instruction budget (findings 2: models follow ~150–200 instructions; CRISPY stages stay under 40), and stage skills stay usable standalone.
- **D2 — Handoff and docs-directory convention.** The state IS the files. Options for naming/layout, resolving the divergence found in findings 1 (nothing standardised except `proposed-split.md`): a fixed `research/ adrs/ plan/` layout with `proposed-<stage>.md` gate docs, `research-findings-<n>-<name>.md` + `research-ref-<n>-<m>-<name>.md`, `adr_NNNN_<slug>.md`. Resume rule lifted from HumanLayer: look at which files exist, suggest the next skill. Examples-first in the ADR: show a worked directory tree and each doc's skeleton.
- **D3 — Approval gates.** Prose gates in the main session only (platform constraint from findings 2: gate tools are stripped from subagents). Each stage skill ends with an explicit stop: present the proposal, wait for the user. No mechanism beyond that.
- **D4 — Spikes as a shared sub-pattern.** The kaos-code-harness spike pattern (waves, gates, steer triggers, self-limits, findings-beat-artifacts) encoded once and referenced from both the research and ADR stage skills via progressive disclosure, so neither stage assumes when multiple paths exist.
- **D5 — Verification encoding in the plan stage.** The three-tier manual-first ladder from findings 3 (ad-hoc `./tmp` scripts run iteratively → scripted smoke gate → opt-in e2e/Playwright/kind), workflow-shaped tests over input-equals-output tests, parallelise past a threshold with a stated cap, and a usage cheatsheet introduced in the ADR and kept current per landed PR.
- **D6 — Expected behaviour and length budgets.** Per-doc length budgets (short ADRs, short plans) and the expected end-to-end behaviour of a full run, written as a worked example.

## Spikes

None proposed. S1 is pre-answered by findings 2 plus the simplicity steer; S2 collapses into D2 (the convention is ours to define and trivially testable); S3 (gate reliability) is replaced by the `writing-skills` verification practice — blind subagent runs of each stage skill on a toy project, reviewing transcripts for skipped gates. That practice becomes part of the plan stage's verification instead.

## Process after approval

Create the single ADR, then walk D1–D6 one by one for your decision (take recommendation or override), then close with a caveats summary of anything that could be misread.
