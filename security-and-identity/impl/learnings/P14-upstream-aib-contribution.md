# P14 — Upstream contribution of the AIB-side work (learnings)

**Phase**: P14 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Date**: 2026-06-09

## Hypotheses

- **"We have access to the upstream repo, so we open fork-based PRs directly against it."** — *Refuted in practice.* `zalando-infosec/agentic-identity-broker` is **internal/read-only** from both available accounts (the EMU account has read; the personal account cannot fork an internal org repo). `axsaucedo/aib-tmp` exists as a **standalone** repo (a manual mirror), **not** a GitHub fork, so the cross-repo PR base/head relationship the plan assumed is not available. **Plan-delta:** P14 stages the stack as draft PRs *within* `aib-tmp` (base `main`, head `feature/*`), to be re-targeted upstream once push access lands. The deliverables (clean stacked branches + Conventional Commits) are unchanged; only the PR mechanics differ.
- **"Each earlier phase produced upstream-ready branches."** — *Mostly confirmed.* The branches built cleanly and rebased onto the foundation without overlap, but none carried the AIB **constitution** artefacts (per-feature ADR, `specs/NNN-*/` triad, per-dir `AGENTS.md`, OpenAPI/config docs, Ginkgo E2E). P14 had to author all of those before the PRs were contribution-grade — this is real work, not a formality.
- **"The SDK port is a straight copy."** — *Confirmed, with one caveat.* The KAOS `aib` package has **no** `pais` dependency (only `httpx` + stdlib), so the package and 7 of 8 test suites port verbatim. Only `test_aib_wiring.py` depends on the KAOS server runtime and is intentionally out of scope for the standalone SDK.

## Findings

- **AIB gating is local, not CI.** There are no `.github/workflows/*`; the Definition of Done is the local `just check` (fmt + vet + lint) and the very heavy `just verify` (adds `web-test`, `cdk-test`, mock-agent/upstream tests, `test-integration-all`, full `test-e2e`). Practical contribution runs `just check` + the fast `just test` + targeted E2E locally and defers the heaviest sub-targets to reviewer CI.
- **The access-check actor token is just a broker-signed `client_credentials` access token.** Its `sub` claim is the agent UUID, which the `ActorTokenValidator` resolves directly against the published JWKS. This made a genuine granted-path HTTP E2E feasible without internal signing access: register an agent + synthetic provider (`client_id = kaos-<segments>`) + covering permission set, mint via `/oauth2/token`, and `POST /api/access/check`.
- **A deprecated Envoy field was lurking.** The ext_authz response-header construction used `HeaderValueOption.Append` (a `*wrapperspb.BoolValue`), deprecated in `go-control-plane`. Migrated to `AppendAction: OVERWRITE_IF_EXISTS_OR_ADD`; the AGENTS.md rule "prefer the non-deprecated Envoy field accessors" now has teeth.
- **Polyglot-in-a-Go-monorepo is viable when isolated.** A `sdk/python/` subtree with its own `uv` venv, `pyproject.toml`, and `just sdk-*` targets (kept out of `check`/`verify`) leaves the Go DoD completely untouched while co-locating the SDK with the access-check contract it consumes — which is the whole point (header/reason changes and their client update land together).
- **Chart structure gotchas** surfaced while writing render tests: the awsKms timeout lives under `broker.encryption.awsKms.dynamodbTimeout`, the dev preset's `storage.type: memory` renders as `backend: memory` in the ConfigMap, and the extproc template is gated on `extProc.enabled` (default off).

## Groundwork uncovered

- **Upstream contribution mechanics need real push access.** Re-targeting the three draft PRs to `zalando-infosec/agentic-identity-broker` requires either a true fork (blocked for internal org repos) or write access. This is a credentials/permissions task, not an engineering one, and gates the actual upstreaming.

## Plan-deltas

- **P14 PR mechanics:** record that draft PRs are staged within `axsaucedo/aib-tmp` (not fork→upstream) until upstream push/fork access is available, then re-targeted in stack order (foundation → access-check → SDK). No change to the dependency order or deliverables.
- **PR naming:** the three PRs use the `PR-ADR-AIB-NNN` prefix mapping to their realised ADRs (000 foundation, 002 access-check, 001 SDK), matching the ADR-numbering convention rather than phase numbers.
