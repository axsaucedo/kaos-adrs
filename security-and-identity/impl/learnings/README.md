# Learnings

One file per phase, named `P<n>-<slug>.md`. Each note records, for that phase:

- **Hypotheses** — what we assumed going in, and whether each was confirmed or refuted.
- **Findings** — surprises, constraints, and facts discovered about KAOS, AIB, Envoy, or the cluster.
- **Groundwork uncovered** — prerequisite work the phase exposed (e.g. AIB image building, Postgres/migrations for the [1.5] deployability groundwork).
- **Plan-deltas** — concrete changes proposed to [`../../plan/proposed-split.md`](../../plan/proposed-split.md), including any phase reordering.

**P0 learnings are the most consequential**: they gate the rest of the work and can reorder later phases. Capture them thoroughly.

See [`../README.md`](../README.md) for the overall convention.
