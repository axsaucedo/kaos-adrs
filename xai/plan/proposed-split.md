# Proposed split — from xai 0.3.0 (tabular, 2017) to the agentic A/B/F library

This plan defines how the `xai` repository restructures to deliver the four ADRs ([interface overview](../adrs/library-interface-overview.md), [0001](../adrs/adr_0001_trajectory-schema-and-ingestion.md), [0002](../adrs/adr_0002_decision-attribution-replay.md), [0003](../adrs/adr_0003_parametric-instrumentation.md), [0004](../adrs/adr_0004_visualization-tui.md)). Current state: `xai==0.3.0`, a single flat package (`xai/__init__.py` ~1,150 lines of pandas/matplotlib tabular fairness tooling plus `xai/data`), pyproject/setuptools, pandas 2.x, tests, mkdocs.

## Versioning and compatibility posture

- **The 2017 tabular API is kept, frozen, and moved — not deleted.** It has real users and embodies the brand's history. It relocates to `xai.tabular` with the top-level names re-exported through a deprecation shim for one minor series (import `xai.imbalance_plot` works with a `DeprecationWarning` pointing at `xai.tabular.imbalance_plot`).
- **Version arc:** `0.4.0` ships the new core (A) alongside `xai.tabular` and the shims; `0.5.0` adds B; `0.6.0` adds F client-side + the TUI; `1.0.0` locks the canonical schema as a stability promise. Server-side instrumentation ships as separate distributions on their own cadence (below) because engine pins churn faster than the analysis library.

## Package layout (target)

```text
xai/
├── __init__.py            # new public surface: load, load_langfuse, load_otlp, explain, Trajectory
├── schema/                # ADR 0001: canonical model, typed values, provenance enums, JSON (de)serialization
├── ingest/                # adapters: langfuse.py, otlp.py (OTel GenAI + OpenInference), json.py; spec pins + fixtures
├── trajectory/            # Trajectory object, events accessors, replay-manifest view, signals view
├── diagnose/              # layer-A deterministic diagnostics (incl. non-completion/spiral, uncertainty spikes)
├── replay/                # ADR 0002: adapter protocol (5 ops), checkpoint/intervention dataclasses,
│   │                      #   stat engine (Wilson/Newcombe/sequential/Holm), taxonomy, budgets, guided screening
│   └── adapters/          # reference adapters: openai_endpoint.py (from S2-P4), synthetic.py (the unit-SCM testbed)
├── parametric/            # ADR 0003 client side: signal accessors, calibrator objects, probe registry + fail-closed loaders
├── viz/                   # ADR 0004: static HTML export (core), rich reprs
├── tui/                   # ADR 0004: Textual app (extra: xai[tui])
├── tabular/               # the frozen 2017 API, moved verbatim + its data/
└── _compat.py             # deprecation shims for the old top-level names
```

Separate distributions (same monorepo, `packages/` directory, independent version pins):

```text
packages/xai-serve-vllm/     # logits processor (Tier 1) + the version-pinned runner patch (Tier 2), per vLLM pin
packages/xai-serve-sglang/   # forward-hooks module (Tier 2) + logits path (Tier 1), per SGLang pin
packages/xai-serve-llamacpp/ # cb_eval plugin + build recipe (covers the Ollama-via-llama-server story)
packages/xai-cost-ebpf/     # eBPF/CUPTI cost channel tooling (specialist tier)
```

Rationale: the analysis library must never break because an engine bumped a private surface; the serve packages pin engines tightly and release on their own cadence, all emitting the one canonical span shape that `xai` core consumes.

## What migrates from the spike code (proven, not rewritten from scratch)

| Spike asset | Destination |
|---|---|
| S1 adapters + alignment/round-trip checks | `xai/ingest/` + `tests/ingest/` with the S1 exports as immutable fixtures |
| S2 `replay_kernel.py`, `stat_engine.py`, calibration grid | `xai/replay/` + `tests/replay/` (the calibration grid becomes a slow-marker test tier) |
| S2-P4 real-model adapter | `xai/replay/adapters/openai_endpoint.py` |
| S7 signal extraction + battery + tie/drift analyses | `packages/xai-serve-llamacpp` + `xai/parametric/` calibration tooling + tests |
| S6 probe registry objects + fail-closed loaders | `xai/parametric/registry.py` (SEP entry `prototype-restricted`; refusal entry `research-only`) |
| S3 vLLM/SGLang artifacts (logits processor, hook module, patch) | the respective `packages/xai-serve-*` |
| Stage-9 spec | `docs/` schema reference + `xai/schema/` docstrings (single source: the spec) |

## Dependency policy

Core: pandas, numpy, scipy (already present) + opentelemetry-sdk (ingest/emit). Extras: `xai[tui]` → textual; `xai[langfuse]` → langfuse client for the export API path (file-based OTLP needs nothing); serve packages own their engine deps entirely. matplotlib stays (tabular + notebook charting); no FastAPI/web deps anywhere (ADR 0004).

## Test and verification strategy

- **Contract tests** (fast, every CI run): ingest fixtures → canonical assertions (the S1 suites); span-shape contract for the serve packages against recorded fixtures; probe-registry rejection tests.
- **Statistical validity tier** (slow marker, scheduled + release-gated): the S2 calibration grid at reduced replication (FPR/coverage/abstention bounds), the planted-cause benchmark harness.
- **TUI snapshot tests** via Textual's pilot harness.
- **Serve-package integration tier** (manual/scheduled, needs engines): the S3/S7 verification loops (HF-oracle tolerance, batching self-consistency, trace continuation) as runnable scripts per package.

## Documentation and launch motion

mkdocs gains an "Agentic" top section (quickstart = the interface overview's journey; per-integration guides; the honest-labeling and abstention contracts as first-class doc pages). The 2017 docs move under "Tabular (legacy)". Launch pairs with the Institute's awesome-list "Agent Explainability & Audit" category per stage 5.

## Sequencing (implementation increments)

1. **Increment A (0.4.0):** `schema/`, `ingest/`, `trajectory/`, `diagnose/`, `tabular/` move + shims, HTML export floor. Gate: S1 fixtures pass through the packaged code paths.
2. **Increment B (0.5.0):** `replay/` with both reference adapters, benchmark harness. Gate: reduced calibration grid green in CI.
3. **Increment F+TUI (0.6.0):** `parametric/`, `tui/`, first serve package (SGLang or llama.cpp first — smallest pin surface). Gate: end-to-end on a live local engine reproducing the S7 numbers.
4. **1.0.0:** schema stability declaration after the increments have soaked.

**Spike S8 executed this validation (2026-08-03, branch `spike/s8-integration`, six commits, 30 tests green, end-to-end demo functional in recorded and live modes): the split is viable with ten concrete amendments — see [S8 learnings](../impl/learnings/S8-integration.md).** The amendments bind increment A: schema owns dtype policy (pandas-3 nulls), validation at the canonical boundary not per adapter, `explain()` keeps a public progress stream, adapter-reported cost units, fidelity never defaults to perfect, candidate identity shared between trace and checkpoint, per-token internal-event volumetrics get lazy projection, extractor context (max-step budget) travels with signals, and the llama.cpp serve package's first requirement is a server-side extractor hook (or unified runner) for token-identity capture, which the stock OpenAI endpoint cannot provide.
