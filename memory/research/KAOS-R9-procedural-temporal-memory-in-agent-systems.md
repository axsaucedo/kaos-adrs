# KAOS-R9 — Procedural, episodic, semantic, and temporal memory in production and coding-agent systems

This document examines how production and coding-agent systems implement the four long-term memory types that the framework survey ([KAOS-R8](./KAOS-R8-production-memory-adoption-in-frameworks.md)) found are rarely separated in practice: procedural (how-to / skills), semantic (timeless facts), episodic (records of past events), and temporal (facts with a validity interval). It is follow-on research feeding the architecture-decision phase — specifically the tier definitions and which tiers KAOS commits to versus defers ([adr_high_level_components](../adrs/adr_high_level_components.md) component 1). Its purpose is to give the memory-model decision a precise, example-grounded vocabulary and a clear read on which tiers are genuinely realised in production versus aspirational.

## Scope and method

The survey covers skill- and document-centric coding agents (Voyager, OpenHands, Claude Code, Cursor, Aider), memory-framework engines (Cognee, Zep/Graphiti, Letta/MemGPT), and two personal-assistant agents that specialise in procedural-plus-temporal documentation memory (OpenClaw and the NousResearch Hermes agent). Claims are drawn from official documentation and source where possible. Two project names were supplied informally and verified against the GitHub API during this research: `openclaw/openclaw` exists (≈380,841 stars, created November 2025, homepage openclaw.ai) and `NousResearch/hermes-agent` exists (≈204,844 stars, created July 2025, MIT, homepage hermes-agent.nousresearch.com). Both are real and active; high-level architecture is confirmed from official READMEs, while finer code-level details for Hermes derive partly from a third-party tutorial and are flagged accordingly.

## The four types, defined with examples

Running example: a developer ("Sam") working with a coding-and-personal agent.

- **Procedural — a reusable how-to / skill.** Action-oriented; retrieval yields steps or code, not data. *"To add an API endpoint: create a handler in `src/api/handlers/`, register it in the router, add a zod schema."* Realised as: Voyager's JavaScript skill library (`ckpt/skill/code/*.js`, retrieved by similarity); Claude Code Skills (`SKILL.md`, lazy-loaded with dynamic command injection); OpenHands microagents (`AGENTS.md` / keyword-triggered skill markdown); Cursor rules (`.cursor/rules/*.mdc`, pattern-scoped); Aider's `CONVENTIONS.md`; Letta's self-edited persona block.
- **Semantic — a timeless fact.** Believed stably true, no inherent expiry. *"Sam prefers pytest and httpx."* Realised as: `CLAUDE.md` / `AGENTS.md` project facts; Cognee and Graphiti `EntityNode` summaries (current-state view); Letta `human`/`persona` blocks; Aider's repo map.
- **Episodic — a record of a specific past event.** Tied to a time and context; enables "remember when…". *"On 2026-04-11 Sam asked me to refactor auth and objected that I used `requests` instead of `httpx`."* Realised as: Graphiti `EpisodicNode` (every fact traces back to the episode that produced it); Letta recall memory; Cognee session traces synced into the graph; Voyager's event recorder (weakly queryable); Claude Code auto-memory notes (an approximation — extracted from corrections, not raw events).
- **Temporal — a fact with a valid-from / valid-to interval.** A semantic fact annotated with validity, enabling point-in-time queries. *"Sam was on project Alpha from 2026-01 to 2026-03, then project Beta"* — so a query about February returns Alpha. Realised, in a rigorous bi-temporal form, essentially only by Graphiti (`valid_at` / `invalid_at` world time plus `expired_at` system time on every edge). Cognee evolves its graph over time but documents no bi-temporal schema; everyone else overwrites facts and loses history.

## The blurry line between semantic and temporal

The textbook distinction is that semantic facts are atemporal ("water boils at 100°C at sea level") while temporal facts hold only during an interval ("Alice is CEO of Acme"). In practice almost every semantic fact about the mutable world is a temporal fact with an open end; the difference is the *expectation* of change. A useful gradient: pure semantic (`π ≈ 3.14159`, never changes, no temporal fields needed); quasi-semantic (`CPython has a GIL`, rarely changes, updated manually); slow-temporal (`Sam is on project Alpha`, changes over months, temporal if history matters); fast-temporal (`the build is currently red`, changes in hours, must be temporal); pure episodic (`Sam corrected me on 2026-04-11`, a historical record, never superseded).

Graphiti draws the line most rigorously by collapsing semantic into temporal: all entity-to-entity facts are temporal by default, every edge carries `valid_at` / `invalid_at` (defaulting to null, meaning "valid until superseded"), and a contradiction sets `expired_at` on the old edge (system time) and creates a new edge, with the LLM inferring `valid_at` / `invalid_at` from the episode. A "timeless" fact is simply the degenerate case where `invalid_at` is null. Systems that keep a separate semantic bucket (Claude Code's `CLAUDE.md`, Letta's blocks, Cursor's rules) accept that the bucket may silently go stale.

The practical test that separates the types: can the system answer *"who was CEO in 2022?"* A current-state semantic store returns the present CEO or nothing — the past is lost; only a bi-temporal store (Graphiti/Zep) returns the correct historical answer. And episodic is distinct again — it is the *event that produced* the fact, not the fact itself.

## Comparative matrix

| System | Procedural | Semantic | Episodic | Temporal (bi-temporal) | Notes |
| --- | --- | --- | --- | --- | --- |
| Voyager | Strong (JS skill library + vector retrieval) | No | Weak (event log) | No | Research; canonical auto-skill-creation agent |
| OpenHands | Yes (`AGENTS.md` + keyword skills) | Partial (static `AGENTS.md`) | No | No | Production coding agent |
| Claude Code | Yes (`SKILL.md`, lazy, dynamic injection) | Yes (`CLAUDE.md` hierarchy) | Partial (auto-memory notes) | No | Commercial; production |
| Cursor | Yes (`.cursor/rules`, pattern-scoped) | Yes (always-on rules) | Partial (proprietary "memories") | No | Commercial; production |
| Aider | Partial (`CONVENTIONS.md`, static) | Yes (repo map, regenerated) | No | No | Production |
| Cognee | No | Yes (KG entity nodes) | Yes (session → graph) | Partial (evolving KG, no documented bi-temporal) | v1 mid-2026; no named production users |
| Zep / Graphiti | No | Yes (EntityNode summaries) | Yes (EpisodicNode + provenance) | Yes (full bi-temporal) | The temporal gold standard ([KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md)) |
| Letta / MemGPT | Yes (self-editing core memory blocks) | Yes (persona/human blocks) | Yes (recall memory store) | No | Most agent-as-editor-of-its-own-memory |
| OpenClaw | Yes (`SKILL.md` + agent-proposed Skill Workshop) | Yes (`MEMORY.md` + memory-wiki) | Yes (dated notes + memory search) | Partial (temporal conditions in prose; no schema) | ≈380k stars; production |
| Hermes Agent | Yes (auto-created, self-improving, versioned `SKILL.md`) | Yes (`MEMORY.md` + `USER.md` via Honcho) | Yes (FTS5 SQLite session search + LLM summaries) | Partial (version history in frontmatter; no schema) | ≈204k stars; production |

## OpenClaw and Hermes: procedural-plus-temporal-in-documentation specialists

These two personal-assistant agents are the clearest examples of the pattern of building procedural memory as skills and recording temporal/how-to knowledge directly inside the skill documents.

OpenClaw (`openclaw/openclaw`, homepage openclaw.ai) implements procedural memory as a two-tier skill architecture: static `SKILL.md` files plus a governed agent-proposal queue ("Skill Workshop") where the agent drafts skill proposals — optionally autonomously from durable conversation signals after successful turns — for human approval, with skills following an open skills standard and discoverable on a public registry. Temporal knowledge is encoded across overlapping plain-Markdown layers (`MEMORY.md`, dated daily notes, and a provenance-tracked memory-wiki), with explicit "action-sensitive" guidance to record when and under what conditions a memory applies; provenance and contradiction detection give soft supersession, but there are no per-fact validity timestamps. A Cognee plugin adds a graph-backed layer on top of the flat Markdown memory.

Hermes (`NousResearch/hermes-agent`, by NousResearch, MIT) implements the most sophisticated autonomous procedural-memory loop in the survey: skills are auto-created after complex tasks and self-improve in place during use (confirmed from the official README), with a `SKILL.md` frontmatter schema carrying a semver `version` bumped on each improvement and a `skill_manage` tool (`create`/`edit`/`patch`/`view`/`list`). Temporal knowledge is built into the skills themselves — the version number and an "Improvement Notes" changelog record a skill's history, and the skill-authoring guidance enforces an "anti-sediment" principle: a skill should get shorter and sharper over time rather than accumulate stale advice. Cross-session recall is three-layered: episodic via an FTS5 SQLite session database of LLM-generated session summaries (`hermes session search …`), semantic via always-injected `MEMORY.md` plus a `USER.md` user model maintained by the Honcho dialectic system, and procedural via the selectively-injected `SKILL.md` library.

Critically, neither implements a bi-temporal schema. They optimise for personal-agent continuity — the agent keeps getting better at knowing and helping a user — whereas Graphiti optimises for verifiable point-in-time fact queries. Asked "what did I prefer in January?", OpenClaw/Hermes would have to scan dated notes while Graphiti answers directly from edge validity. The concerns are complementary, which is exactly why a graph layer is sometimes bolted onto the Markdown approach.

## Key design observations

- Coding agents (Cursor, Aider, Claude Code, OpenHands) are procedural-first: they encode "how to work in this codebase" as rules and skills, with temporal and episodic recall absent or an afterthought.
- Memory-framework engines (Graphiti/Zep, Letta, Cognee) are fact-first: they model what is true about the world or user, with procedural skill libraries absent or an add-on.
- Only Graphiti implements genuine temporal reasoning; all others treat facts as current-state and degrade silently when the world changes.
- Letta is the only surveyed system that makes the agent a first-class editor of its own memory (surgical `core_memory_replace`), versus write-only auto-memory.
- An informal `AGENTS.md` / `CLAUDE.md` / `.cursor/rules` convergence has emerged as a cross-tool procedural/semantic context format — but still without validity timestamps, so it is documentation, not temporal memory.

## Implications for the KAOS memory model

- Working memory is table stakes and is committed regardless ([KAOS-R8](./KAOS-R8-production-memory-adoption-in-frameworks.md)).
- Semantic and episodic memory are the practical long-term core; production norm is to collapse them, so the KAOS metadata envelope should be able to *distinguish* them even when a single engine stores them together.
- True temporal (bi-temporal) memory is a genuine differentiator delivered essentially only by Graphiti-class engines, which supports treating it as a deferred capability tier rather than table stakes (the capability-ceiling framing of [KAOS-R7](./KAOS-R7-target-picture.md)).
- Procedural memory is coding-agent-centric and the least standardised, realised today as skills and self-edited prompt fragments; it is a strong fit for a later, agent-lifecycle-aware capability tier rather than the initial commitment.

## Context manifest

In scope (informing this document): the official documentation and source of the surveyed coding agents and memory engines; the Zep/Graphiti deep dive [KAOS-R5-2](./KAOS-R5-2-zep-graphiti.md) and the Cognee deep dive [KAOS-R5-3](./KAOS-R5-3-cognee.md); the framework adoption survey [KAOS-R8](./KAOS-R8-production-memory-adoption-in-frameworks.md); and GitHub API verification of the OpenClaw and Hermes repositories.

Out of scope: framework-level adoption signal and the external-engine-as-production-memory finding, which are covered in [KAOS-R8](./KAOS-R8-production-memory-adoption-in-frameworks.md); and any KAOS design commitment, which is the work of the architecture-decision records introduced by [adr_high_level_components](../adrs/adr_high_level_components.md).

## Confidence notes

High-level architecture claims for OpenClaw and Hermes are confirmed from official documentation and READMEs, and the repositories' existence and approximate star counts were verified against the GitHub API. Finer Hermes implementation details (for example the exact autonomous-skill-creation heuristics and the `memory_manager.py` / `skill_utils.py` internals) derive partly from a third-party tutorial and should be treated as indicative rather than authoritative. Star counts elsewhere in this document are approximate as of June 2026.
