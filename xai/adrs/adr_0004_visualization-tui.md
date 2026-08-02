# ADR 0004 — Visualization: TUI-first debugging with static HTML export

- **Status.** Proposed
- **Date.** 2026-08-03
- **Depends on.** [ADR 0001](./adr_0001_trajectory-schema-and-ingestion.md), [ADR 0002](./adr_0002_decision-attribution-replay.md), [ADR 0003](./adr_0003_parametric-instrumentation.md), [stage 6 non-goals](../research/6-direction-synthesis.md)
- **Constrains.** The S8 integration spike and the implementation plan.

## Context

Trajectories, per-step signals, and replay results are inherently visual: a user debugging an agent failure wants to walk the trajectory tree, see where uncertainty spiked, launch an ablation replay on a suspect step, and watch the verdict arrive with its interval. The question is the delivery vehicle. The hard boundary from stage 6: xai is not a trace store or a dashboard — observability vendors own that cell, and competing there both dilutes the wedge and loses. Whatever ships must be pip-installable, work where engineers actually debug (terminals, SSH sessions, notebooks), and add zero operational surface.

## Decision

### Ship a Textual TUI as the interactive debugger, plus static HTML export; no web service

`xai debug <trace>` opens a three-pane Textual application:

1. **Trajectory tree** — the event tree with per-step badges: diagnostic findings, uncertainty sparkline summary, tie/non-completion flags, cost, provenance (engine, numerics mode).
2. **Step inspector** — messages, tool schemas/payloads (typed values: raw and parsed), replay-manifest slot states, per-step signal detail.
3. **Replay panel (the B debugger)** — select candidate context items, choose budget tier and δ, run `xai.explain` against a configured adapter, watch sequential batches land live, and read the ten-state verdict with effect, CI, counts, and fidelity. Prediction breakdowns (which candidates mattered, group→individual refinement) render as sortable tables.

`traj.to_html(path)` (and `report.to_html`, `result.to_html`) export self-contained static HTML for sharing and notebook embedding — rendered views of the same objects, no server behind them. The TUI is an optional extra (`pip install xai[tui]`) so the core library stays lean; the HTML export lives in core.

### The TUI is a view over the public API, never a privileged path

Everything the TUI does is a documented library call (`load`, `diagnose`, `explain`, accessors). This keeps it honest (nothing visual that the API cannot produce), testable (snapshot tests over rendered panes; Textual's pilot/test harness in CI), and defers nothing critical to screen-only code.

## Consequences

- Works over SSH and inside clusters (the KAOS operator-laptop case), ships in pip, adds no service to run or secure — consistent with the non-goals.
- Textual gives trees, tables, sparklines, and live-updating panes cheaply; the replay panel's "watch batches land" loop is a natural fit for its reactive model.
- A TUI cannot match a web UI for dense charts or sharing with non-terminal users; the static HTML export covers the sharing case, and notebooks cover exploratory charting via the dataframe (matplotlib idiom, as 2017 xai did).
- If a richer visual layer is ever justified, the static-HTML renderer is the seed (same view components, no architecture change); a served web UI would require revisiting the non-goal explicitly.

## Alternatives considered

- **No UI (library + notebooks only).** Rejected: the replay debug loop (pick candidates → run → watch → verdict) is genuinely interactive and materially better than notebook cells for incident debugging; leaving it out concedes the most demonstrable moment of the library's value.
- **Local web UI (FastAPI + SPA, `xai serve`).** Rejected for v1: heavier dependency and security surface, a served process to manage, and one step from becoming the dashboard we swore not to build; every concrete debugging need enumerated above is met in the terminal. Revisit only with a user-driven case the TUI demonstrably cannot serve.
- **Both TUI and web UI.** Rejected: double maintenance before either has users.
- **Rich (non-interactive pretty-printing) only.** Rejected as the endpoint, adopted as a floor: `repr`/`__rich__` niceties ship in core regardless; they do not cover the interactive replay loop.

## Follow-up

- S8 (integration spike) builds the TUI skeleton against real campaign artifacts and is the acceptance test for this decision — if the replay panel disappoints in practice, this ADR is revisited before implementation hardens.
- Snapshot-test harness for panes in CI from the first increment.
