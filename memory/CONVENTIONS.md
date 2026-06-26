# KAOS memory research conventions

Authoring conventions for the memory research documents in `research/` and any follow-on design artifacts under `memory/`.

## Scope

- This area investigates the path to production-grade memory for KAOS: extending the existing custom implementation versus adopting a third-party (OSS or commercial) memory provider.
- The current phase is **research only**. Documents here describe, compare, and recommend; they do not change KAOS source. The KAOS repository is read-only for this effort, and the only writes are to this `kaos-ai-docs` repository.

## Numbering

- Research documents use the `KAOS-R<n>` prefix, where `<n>` is the research stage (`KAOS-R1` … `KAOS-R7`).
- `KAOS-R1` documents the current KAOS memory implementation and is the requirements baseline that later stages refer back to.
- Per-tool deep dives in stage 5 use a compound suffix: `KAOS-R5-<n>-<toolname>` (for example `KAOS-R5-1-mem0`). The `<n>` ordering and tool set are fixed by the `KAOS-R4` shortlist.

## Cross-references

- Always reference another research document as a Markdown link, e.g. `[KAOS-R1](./KAOS-R1-memory-features-and-limitations.md)`.
- Use `./` for same-folder links within `research/`.
- Reference KAOS source as repository-relative paths (for example `pydantic-ai-server/pais/memory.py`) and, where useful, include line ranges so claims are verifiable.
- Do not leave bare `KAOS-R0X` text references unlinked (except a document referring to itself).

## Context discipline

- Each document is written from an explicitly curated set of inputs, not from accumulated conversation history. Re-read the exact source files and prior research documents a stage depends on, and exclude unrelated or superseded material.
- Where helpful, record the in-scope and out-of-scope inputs for a stage so the curation decision is explicit and auditable.

## Markdown style

- **No hard line wraps inside paragraphs or list items.** Write each paragraph and each list item as a single continuous line and let the editor/renderer soft-wrap. Manual mid-sentence newlines break reading flow and create noisy diffs.
- Separate paragraphs, list blocks, headings, tables, and code fences with blank lines.
- Do not reference phases, tasks, plan steps, or TODO numbers in document bodies. Describe the work by what it is, not by its position in a process.

## Commits

- Commit one document per commit using comprehensive conventional commit messages in the `docs(memory): …` form, describing exactly what was added or changed.
