# Proposed research — RPI workflow plugin

Status: **proposed — awaiting approval**. Baseline: [000-initial-request](../adrs/000-initial-request.md).

Goal of the research stage: ground the design of the RPI plugin in (a) how the workflow has actually been practiced across kaos-ai-docs sections, (b) what the Claude Code plugin/skill machinery supports, and (c) prior art, so the ADR stage can choose between concrete, validated options rather than assumptions.

Dogfooding note: this research uses the plugin's own proposed naming — `research-findings-<n>-<name>.md` (distilled, kept) and `research-ref-<n>-<m>-<name>.md` (full captured source text, split as needed). Each area below becomes one findings doc; each is independently runnable by a subagent in parallel.

## Area 1 — Internal: the RPI workflow as practiced (kaos-ai-docs archaeology)

The de-facto spec of the workflow lives in the sections that already followed it: `memory/` (R1–R11 research → 6 ADRs → M0–M8 plan → impl), `duckmemory/`, `security-and-identity/` and `security-and-identity-2/`, `kaos-code-harness/` (SPIKE-PLAN → spikes → RESULTS), plus `evals/`, `mcp-runtime-extensions/`, and others as found.

- Extract the common pipeline: proposal docs → approval gates → numbered research → ADR set → milestone plan → implementation; and per-section `CONVENTIONS.md` rules (numbering, cross-referencing, context discipline, markdown style, commit conventions).
- Extract the spike pattern from `kaos-code-harness/SPIKE-PLAN.md`: waves, gates, steer triggers, self-limits, worktrees, "findings beat artifacts", "negative results are results".
- Capture divergences between sections and which conventions proved sticky vs abandoned — those divergences are exactly where the plugin must either standardise or stay flexible.
- Output: `research-findings-1-rpi-as-practiced.md` — the canonical workflow description the plugin must encode, with refs to concrete exemplar docs.

## Area 2 — Internal: marketplace plugin and skill conventions

The deliverable lands in `EthicalML/agent-skills-marketplace` (public), likely under `plugins/workflow-automations/`.

- How existing skills are authored: `writing-skills`, `create-agent-harness`, `dependabot-fix-all` (multi-agent orchestration precedent), `release-repo`; plugin.json / marketplace.json registration; `scripts/validate.sh` requirements; AGENTS.md constraints (public repo — no private references, which affects how the workflow's examples are written).
- Output: `research-findings-2-marketplace-conventions.md`.

## Area 3 — External: Claude Code plugin/skill machinery

What the platform supports determines the plugin's shape; this must be verified against current docs, not assumed.

- Slash commands vs skills vs agents in plugins; skill frontmatter and user-invocable skills; how a skill drives subagent fan-out; how approval gates are expressed (explicit stop-and-wait vs AskUserQuestion); whether/how state carries across sessions (the answer is almost certainly "files on disk by convention" — confirm what conventions exist for a docs-directory handoff between stages).
- Output: `research-findings-3-claude-plugin-machinery.md`.

## Area 4 — External: prior art in phased workflow plugins/systems

- Anthropic official skills and community plugins that implement research/plan/implement or spec-driven flows: e.g. superpowers (brainstorm → plan → implement), GitHub spec-kit, OpenSpec, BMAD-method, and Claude Code's own plan mode. What they got right, what to deliberately avoid (over-ceremony, template bloat), and how they gate on user approval.
- Output: `research-findings-4-prior-art.md`.

## Area 5 — External + internal: verification companions

The plan stage's verification philosophy needs concrete reference implementations to point at.

- `zalando-markets/agent-marketplace` → `plugins/databricks/skills/streamlit-verification-playwright` (Playwright visual verification companion pattern); kaos repo's kind-based e2e validation; how to encode: workflow-level tests over input-equals-output tests, manual-first `./tmp` scripts run iteratively, parallelisation past a time threshold, cheatsheets for user review.
- Output: `research-findings-5-verification-patterns.md`.

## Candidate spikes (proposed, decided after findings land)

Per the workflow itself: where multiple paths exist, validate with spikes rather than assume. Current candidates — to be confirmed or pruned once areas 1–4 report:

- **S1 — plugin shape.** One `/new-project` command routing a single skill vs one skill per stage (`rpi-research`, `rpi-adrs`, `rpi-plan`, `rpi-implement`). Build both minimally, run each through a toy project, compare on: resumability mid-stage, context cost, and whether stage skills are usable standalone.
- **S2 — stage handoff.** Validate that a fresh session can pick up mid-workflow purely from the docs directory (proposal docs + an index/status convention), with no conversation context.

## Execution

- Areas 1–5 run as parallel subagents, each writing its findings + ref docs directly into `research/` here.
- Each landed doc gets its own comprehensive `docs(rpi-workflow): …` commit.
- Self-limit per area: ~30 min; an area that cannot finish reports where it got to as the finding.
