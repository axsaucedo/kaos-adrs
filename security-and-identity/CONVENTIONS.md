# Security & identity ADR conventions

Authoring conventions for the ADRs in `adr-kaos/` and `adr-aib/`.

## Numbering

- KAOS-owned ADRs use the `ADR-KAOS-<n>` prefix (`adr-kaos/`).
- AIB-owned ADRs use the `ADR-AIB-<n>` prefix (`adr-aib/`).
- Each sequence is independent. `ADR-KAOS-000` is the cohesive target picture and is the entry point.

## Cross-references

- Always reference another ADR as a Markdown link, e.g. `[ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md)`.
- Use `./` for same-folder links and `../adr-aib/` or `../adr-kaos/` for cross-folder links.
- Do not leave bare `ADR-KAOS-00X` text references unlinked (except a file referring to itself).

## Markdown style

- **No hard line wraps inside paragraphs or list items.** Write each paragraph and each list item as a single continuous line and let the editor/renderer soft-wrap. Manual mid-sentence newlines break reading flow and create noisy diffs.
- Separate paragraphs, list blocks, headings, tables, and code fences with blank lines.
- Keep terminology consistent with `ADR-KAOS-000`: enforcement is gateway-centric; the SDK is **not the enforcement boundary**; mTLS/SPIFFE/mesh/sidecars are **out of scope** (not "future hardening").
