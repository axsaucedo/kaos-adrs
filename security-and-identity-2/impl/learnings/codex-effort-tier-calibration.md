# Codex effort-tier calibration — high vs medium on a hard operator rework

**Date**: 2026-07-13
**Context**: During the P20 → AIB-native rework (remove the `ThirdPartyService` CRD; add a poll-based AIB reflector), the same task was run twice in parallel as a delegation calibration experiment: `gpt-5.6-sol` at **high** effort (the main path) and at **medium** effort (an isolated experiment), both branched from the identical base commit `571c3397`. Goal: calibrate whether the effort tier materially changes *code* quality, and at what token/time cost.

**Status of the finding**: preliminary — **not a clean A/B** (the two runs had different scopes; see caveat). A same-scope re-run is deferred. Documented here so the signal isn't lost.

## Setup

| | High (main path) | Medium (experiment) |
|---|---|---|
| Model / effort | gpt-5.6-sol / high | gpt-5.6-sol / medium |
| Branch | `feat/kaos-token-exchange` (main tree) | `exp/rework-medium` (isolated `git worktree`) |
| Base commit | `571c3397` | `571c3397` (same) |
| **Scope** | code **+ full live cluster validation** | **code only** (validation excluded by design) |
| Brief | full rework + reinstall-operator + wire flow | identical rework, stop after compile + unit tests |

Isolation via a separate worktree was essential — both agents edit the same repo; without it they would have clobbered each other's working tree.

## Raw results

| Metric | High | Medium | Δ |
|---|---|---|---|
| Tokens used | **410,230** | **344,267** | High +19% |
| Wall-clock | ~76 min | ~27 min | High 2.8× |
| Commits | 8 | 5 |
| Net diff vs base | +808 / −1569 | +580 / −1598 | comparable (both delete-heavy) |
| Core reflector file (`projector_aib_exchange.go`) | +584 | +450 | High ~30% larger |
| Cluster-op log lines (kubectl/helm/docker/curl, proxy for validation work) | 4,419 | 1,298 | High 3.4× |
| Unit/static tests | pass | pass (`make generate manifests` clean; 45/45 envtest) |

## The caveat that reframes the raw numbers

**Different scopes.** High did code **plus** image build + operator reinstall + reflection + wire attempts; medium did **code only**. So the raw 410k vs 344k *understates* how close they are on code — high's ~66k-token premium is dominated by its validation tail (3.4× the cluster-op lines), not the effort tier. Any "high costs 19% more" reading is wrong for the code-generation question.

## Key insights (token-efficiency angle)

1. **Validation — not effort tier — dominates cost.** Back out high's validation tail and its *code-only* spend was ≈ medium's or lower. Turning the effort dial up did **not** buy a large token increase for the same code. Budget tokens/time **by phase** (code vs live-validate), not by effort tier.
2. **Wall-clock ≠ tokens.** High's 2.8× duration was mostly *waiting on the cluster* (image builds, 180 s pod-readiness delays, 45 s poll intervals) — that burns clock, not model tokens. Never infer token cost from duration.
3. **Medium is token-competitive for pure codegen on a hard task.** 344k tokens produced an architecturally-complete, 30-file, delete-heavy rework with every hard part correct (read-only reflection, generated-route-only ext_proc invariant, stable-key identity migration, Session B untouched).
4. **High's quality edge was reasoning depth + feedback, not raw tokens.** Two concrete edges: (a) high added an *unprompted* robustness feature — projection-sink failure isolation (a failing unrelated projector no longer blocks reflection), with a test; medium had no equivalent. (b) High's code correctly *refuses to register unbound agents* because it hit AIB's live contract; medium's code registers *every* agent and would fail against real AIB. Edge (b) is **feedback, not intelligence** — medium had no cluster, so it could not observe a contract only visible live; its static choice was reasonable.
5. **Cheapest reliable recipe:** medium for the code, then a **separate bounded live-validation pass** (any tier) to catch contract reality — rather than paying high across the whole run. The value of "high" concentrates in (a) defensive depth on genuinely ambiguous design and (b) the live loop; neither needs high applied to every turn.

## Methodology fix for a clean A/B (deferred)

To isolate the *effort-tier* token cost, run both tiers at **identical scope** — either both code-only or both with the same validation — from the same base, and compare tokens + a blind diff-quality review. This run conflated tier with scope, so it answers "what did each task cost" but not "what does the tier alone cost for the same work."

## Bottom line

For pure code generation off a strong, self-contained brief, **medium was near-parity with high and token-competitive**; reserve **high** for live-integration debugging and design-ambiguous work where defensive depth pays. This is consistent with — and sharpens — the standing heuristic that sol low/medium are the pareto-optimal working range for coding.
