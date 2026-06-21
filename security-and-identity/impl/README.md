# Implementation tracking

This folder tracks the execution of the security and identity implementation defined by the phase split in [`../plan/proposed-split.md`](../plan/proposed-split.md).

Each phase (`P0`–`P13`) is run as its own plan-implement iteration (one PR per phase) and is documented here in two places:

- **`progress/`** — what was done, status, the PR, and validation results for each phase. One file per phase, named `P<n>-<slug>.md` (e.g. `P0-feasibility-validation.md`).
- **`learnings/`** — what we discovered: hypotheses confirmed or refuted, surprises, groundwork uncovered, and plan-deltas. One file per phase, named `P<n>-<slug>.md`. **P0 learnings are the most important** — they can reorder later phases and define the AIB deployability groundwork.

## Conventions

- One progress doc and one learnings doc per phase; keep them in sync with the PR for that phase.
- Follow the markdown style in [`../CONVENTIONS.md`](../CONVENTIONS.md): no hard line wraps inside paragraphs or list items.
- Phase numbering and scope are authoritative in `proposed-split.md`; this folder records *what actually happened* against that plan.
- The detailed implementation plan for each phase lives alongside the split in [`../plan/`](../plan/) as `P<n>-<slug>.md` (e.g. `P2-gateway-ext-authz.md`); this folder records execution progress and learnings against that plan.
- Validation harnesses and scratch scripts for a phase live in the KAOS repo under `./tmp/security/` (gitignored), not here. This folder holds only the written progress/learnings.
