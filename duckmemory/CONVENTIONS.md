# DuckMemory research and design conventions

Authoring conventions for the DuckMemory documents under `duckmemory/`: research in `research/`, architecture decision records in `adrs/`, and delivery planning in `plan/`.

## Scope

- This area designs **DuckMemory**: a standalone, embedded DuckDB extension that serves as a full end-to-end agent memory engine directly inside a DuckDB database. The project is independent of KAOS — it has its own memory model and no KAOS dependency — but the KAOS memory effort ([memory/](../memory/)) is a primary evidence base and its learnings are cited rather than rediscovered.
- The current phase is **research and design only**. Documents here describe, compare, decide, and plan; implementation happens later in a dedicated repository (Rust, following the `agent_data_duckdb` extension skeleton).

## Numbering

- Research documents use the `DUCK-R<n>` prefix (for example `DUCK-R1-duckdb-extension-ecosystem.md`). Numbers are assigned in authoring order; follow-on research raised during the decision phase continues the sequence.
- ADRs use `adr_NNNN_<slug>.md` with a zero-padded sequence number and a short kebab-case slug. The index `adr_high_level_components.md` is not itself a numbered decision.

## Cross-references

- Reference another document in this repository as a Markdown link with a relative path, e.g. `[DUCK-R1](./DUCK-R1-duckdb-extension-ecosystem.md)` within `research/`, or `[memory adr_0001](../../memory/adrs/adr_0001_memory-model-and-lifecycle-operations.md)` for the KAOS memory ADRs.
- Reference external evidence (DuckDB docs, extension repositories) as Markdown links to the source URL so claims are verifiable.
- Reference the `agent_data_duckdb` reference implementation by repository-relative path (for example `agent_data_duckdb/src/vtab.rs`).

## Markdown style

- **No hard line wraps inside paragraphs or list items.** Write each paragraph and each list item as a single continuous line and let the editor/renderer soft-wrap.
- Separate paragraphs, list blocks, headings, tables, and code fences with blank lines.
- Do not reference phases, tasks, plan steps, or TODO numbers in document bodies. Describe the work by what it is, not by its position in a process.

## Commits

- Commit one document per commit using comprehensive conventional commit messages in the `docs(duckmemory): …` form.
