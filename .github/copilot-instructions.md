# Copilot instructions — kaos-ai-docs

This repository is an Obsidian vault holding KAOS design notes, blog drafts, research, and the security/identity ADR set under `security-and-identity/`.

## Git workflow

- Commit directly to `main` (master). Do **not** create feature branches for changes in this repo.
- Use clear, conventional-style commit messages (e.g. `docs(security): ...`).
- Include the Copilot co-author trailer on commits.

## Security & identity ADRs

- The ADR authoring conventions (numbering, cross-reference links, markdown style) live in `security-and-identity/CONVENTIONS.md`. Follow them when editing anything under `security-and-identity/`.
- In particular: no hard line wraps inside paragraphs or list items — write each paragraph and list item as a single continuous line and let the editor soft-wrap.
- `security-and-identity/adr-kaos/ADR-KAOS-000-target-picture.md` is the cohesive entry point; keep terminology consistent with it.
