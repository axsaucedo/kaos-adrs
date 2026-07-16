# KAOS evals research conventions

Authoring conventions for the evals research documents in `research/` and the follow-on design artifacts under `evals/` (ADRs, plans, implementation notes).

## Scope

- This area investigates the path to a scalable, Kubernetes-native evaluation capability for KAOS agents: what "evals" means for an agent orchestration framework, whether to extend KAOS with a custom harness or adopt a third-party (OSS or commercial) evaluation framework, and how evals become a declarative, operator-managed capability.
- The research phase is **research only**. Documents there describe, compare, and recommend; they do not change KAOS source. During research the KAOS repository is read-only for this effort, and the only writes are to this `kaos-ai-docs` repository. Design (ADRs) and planning follow the research; implementation happens in the KAOS repository as its own phased track.

## Numbering

- Research documents use the `KAOS-E<n>` prefix, where `<n>` is the research stage (`KAOS-E1` … `KAOS-E7`).
- `KAOS-E1` documents the current KAOS evaluation-adjacent surface and is the requirements baseline that later stages refer back to.
- Per-tool deep dives in stage 5 use a compound suffix: `KAOS-E5-<n>-<toolname>` (for example `KAOS-E5-1-pydantic-evals`). The `<n>` ordering and tool set are fixed by the `KAOS-E4` shortlist.
- Numbers may continue past `KAOS-E7` for follow-on research that supports the architecture-decision records under `adrs/`, answering questions raised during the decision phase rather than belonging to the original staged pipeline.

## Cross-references

- Always reference another research document as a Markdown link, e.g. `[KAOS-E1](./KAOS-E1-evaluation-features-and-limitations.md)`.
- Use `./` for same-folder links within `research/`.
- Reference KAOS source as repository-relative paths (for example `pydantic-ai-server/pais/server.py`) and, where useful, include line ranges so claims are verifiable.
- Do not leave bare `KAOS-EX` text references unlinked (except a document referring to itself).

## Context discipline

- Each document is written from an explicitly curated set of inputs, not from accumulated conversation history. Re-read the exact source files and prior research documents a stage depends on, and exclude unrelated or superseded material.
- Where helpful, record the in-scope and out-of-scope inputs for a stage so the curation decision is explicit and auditable.
- External claims (framework capabilities, APIs, licensing, maturity) must be grounded in the tool's own documentation or repository and linked; do not assert capabilities from memory.

## Markdown style

- **No hard line wraps inside paragraphs or list items.** Write each paragraph and each list item as a single continuous line and let the editor/renderer soft-wrap. Manual mid-sentence newlines break reading flow and create noisy diffs.
- Separate paragraphs, list blocks, headings, tables, and code fences with blank lines.
- Do not reference phases, tasks, plan steps, or TODO numbers in document bodies. Describe the work by what it is, not by its position in a process.

## Commits

- Commit one document per commit using comprehensive conventional commit messages in the `docs(evals): …` form, describing exactly what was added or changed.
