# Proposed research — RPI workflow plugin

Status: **approved (v2, 2026-08-30) — fan-out in progress** across three parallel subagents (opus/sonnet mix). Baseline: [000-initial-request](../adrs/000-initial-request.md).

Goal of the research stage: ground the design of the RPI plugin in (a) how the workflow has actually been practiced across kaos-ai-docs sections, (b) what the Claude Code plugin/skill machinery supports and how prior art has packaged similar flows, and (c) concrete verification patterns, so the ADR stage can choose between validated options rather than assumptions.

Dogfooding note: this research uses the plugin's own proposed naming — `research-findings-<n>-<name>.md` (distilled, kept) and `research-ref-<n>-<m>-<name>.md` (full captured source text, split as needed). Each area is independently runnable by a subagent in parallel.

## Area 1 — Internal: the RPI workflow as practiced (light pass)

The proposal docs are the workflow's fingerprint; they are not standardised across sections, and the divergence itself is signal. Keep this light:

- Read the `proposed-*` (or equivalently-named) proposal/gate docs across sections — `memory/`, `duckmemory/`, `security-and-identity/` and `-2`, `evals/`, `mcp-runtime-extensions/`, others as found — plus `kaos-code-harness/SPIKE-PLAN.md` for the spike pattern (waves, gates, steer triggers, self-limits, findings-beat-artifacts).
- Capture: what each proposal doc gates, what shape stuck, where naming/numbering diverged. No deep reading of the research/ADR bodies themselves.
- Output: `research-findings-1-rpi-as-practiced.md`.

## Area 2 — External: plugin machinery and prior art (incl. the original RPI creators)

- The original RPI skills: search for the creators of the research-plan-implement workflow (referred to as HumanLoop; verify — likely HumanLayer's Advanced Context Engineering / RPI skills) and capture how the originals structure stages, gates, and docs.
- Claude Code plugin/skill machinery: slash commands vs skills vs agents in plugins; how a skill drives subagent fan-out; approval-gate mechanics; cross-session state (files-on-disk conventions for a docs-directory handoff between stages).
- Other prior art in phased/spec-driven flows: superpowers (brainstorm → plan → implement), GitHub spec-kit, OpenSpec, Claude Code plan mode — what to adopt, what ceremony to deliberately avoid.
- Output: `research-findings-2-machinery-and-prior-art.md`.

## Area 3 — External + internal: verification companions

- The OSS ports of the data-app creation skill and its Playwright visual-verification companion now public in `EthicalML/agent-skills-marketplace` [PR #10](https://github.com/EthicalML/agent-skills-marketplace/pull/10) as `plugins/workflow-automations/skills/create-streamlit-app` and `verify-streamlit-app` (hygiene iterations ongoing); kaos repo's kind-based e2e validation; how to encode: workflow-level tests over input-equals-output tests, manual-first `./tmp` scripts run iteratively, parallelisation past a time threshold, cheatsheets for user review.
- Output: `research-findings-3-verification-patterns.md`.

## Candidate spikes (proposed, decided after findings land)

Per the workflow itself: where multiple paths exist, validate with spikes rather than assume. To be confirmed or pruned once areas 1–2 report:

- **S1 — plugin shape.** One `/new-project` command routing a single skill vs one skill per stage (`rpi-research`, `rpi-adrs`, `rpi-plan`, `rpi-implement`). Build both minimally, run each through a toy project, compare on: resumability mid-stage, context cost, and whether stage skills are usable standalone.
- **S2 — stage handoff.** Validate that a fresh session can pick up mid-workflow purely from the docs directory (proposal docs + an index/status convention), with no conversation context.

## Execution

- Areas 1–3 run as parallel subagents, each writing its findings + ref docs directly into `research/` here.
- Each landed doc gets its own comprehensive `docs(rpi-workflow): …` commit.
- Self-limit per area: ~30 min; an area that cannot finish reports where it got to as the finding.
