# Proposed plan — RPI workflow plugin

Status: **approved (2026-08-30)** — P1 in progress. Decisions: [adr_0001](../adrs/adr_0001_rpi-workflow-plugin.md).

Deliverable: five skills in `EthicalML/agent-skills-marketplace` under `plugins/workflow-automations/skills/` — `new-project`, `rpi-research`, `rpi-adrs`, `rpi-plan`, `rpi-implement` — registered in the plugin manifest and passing `scripts/validate.sh`. Learnings from implementation land in `rpi-workflow/implement/learnings/` here as they happen.

## Phases and PR split

Two phases, two PRs. Fewer was considered (one PR) but the dogfood pass in P2 needs the P1 skills reviewed and stable enough to run against, and its fixes deserve their own review.

### P1 — Author the five skills (PR 1)

- Write each SKILL.md as a short recipe per the ADR decisions and the `writing-skills` principles: the stage's steps, its gate doc, its explicit end-of-stage handover, proportionality guidance, and (for `rpi-plan`/`rpi-implement`) the verification ladder and `learnings/` capture. `new-project` additionally sets up `adr/<NNN>-<name>/` and records the initial request.
- Register in `plugins/workflow-automations/.claude-plugin/plugin.json`, update the marketplace README, run `scripts/validate.sh`.
- One comprehensive commit per skill, plus one for registration/README.
- Verification before the PR opens (manual-first, per the ADR): for each skill, a blind sonnet subagent is given a toy task and the skill — never "judge this skill" — and the transcript is reviewed for skipped gates, wasted context, and re-read loops. Fixes are commits in the same PR; what each run taught goes to `implement/learnings/`. This is the workflow-shaped test: a stage actually runs end to end and stops at its gate. No trivial checks beyond `validate.sh` as the smoke gate; no Playwright (nothing visual here).

### P2 — Dogfood the full run and polish (PR 2)

- Run the complete flow — `/new-project` through `rpi-implement` — on one small real toy project in a scratch repo, with the plugin installed from the PR-1 branch. This validates the handovers and the resume rule (kill the session mid-flow once; a fresh session must find its place from the files alone).
- Apply fixes surfaced by the dogfood, update the plugin README with the usage cheatsheet (the `/new-project → approve gates → PR by PR` happy path), and land the accumulated learnings.
- If the dogfood surfaces nothing, PR 2 is just the cheatsheet and learnings — still worth its own small review.

## Verification summary

- Manual-first: blind subagent runs per skill (P1), full dogfood run (P2), scripts and scratch material in the gitignored `./tmp`.
- Smoke gate: `scripts/validate.sh` on every commit that touches skills.
- Workflow-shaped only: every check exercises a full stage or the full flow; no input-equals-output tests exist to write here.
- Parallelisation: the five P1 blind runs execute in parallel; each is small, so no further splitting.

## Review cheatsheet (kept current through implementation)

- Install: marketplace add → `/plugin install workflow-automations`.
- Start: `/new-project <scope>` → approve `proposed-research.md` → research fans out → approve `proposed-adrs.md` → decide D-by-D → approve `proposed-plan.md` → implementation PR by PR, learnings captured throughout.
- Resume anytime: open a session in the repo; the skills look at `adr/<NNN>-<name>/` and offer the next step.
