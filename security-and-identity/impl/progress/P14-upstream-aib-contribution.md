# P14 — Upstream contribution of the AIB-side work (progress)

**Phase**: P14 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Status**: In progress — three stacked DRAFT PRs opened on the staging fork, awaiting review.
**Date**: 2026-06-09
**PRs** (stacked, dependency order):

1. **PR-ADR-AIB-000** — Deployability foundation → [aib-tmp#5](https://github.com/axsaucedo/aib-tmp/pull/5)
2. **PR-ADR-AIB-002** — Access-check decision service (ext_authz + HTTP) → [aib-tmp#6](https://github.com/axsaucedo/aib-tmp/pull/6) *(stacked on #5)*
3. **PR-ADR-AIB-001** — Python SDK for context propagation and access checks → [aib-tmp#7](https://github.com/axsaucedo/aib-tmp/pull/7) *(stacked on #6)*

## Outcome

The three AIB-side deliverables built across the earlier phases were brought up to the AIB project's own contribution standard (binding constitution: per-feature ADR + `specs/NNN-*/` triad + per-directory `AGENTS.md` + OpenAPI parity + ≥80% new-code coverage + Ginkgo E2E with 1:1 spec traceability + green `just check`) and opened as **three stacked draft PRs** in dependency order. Because the upstream `zalando-infosec/agentic-identity-broker` is internal/read-only from the available accounts, the stack is staged on the personal fork `axsaucedo/aib-tmp` (draft PRs opened *within* the fork, base `main`), ready to be re-targeted upstream once push access is available. Commit identity is the repo-default Zalando author with Conventional Commits and **no** KAOS Copilot co-author trailer (external repo).

## Deliverables

| PR | Branch | Scope delivered |
|---|---|---|
| **#5 PR-ADR-AIB-000** | `feature/deployability-foundation` | Public `alpine:3` base for all three Dockerfiles, chart values-schema fix (`broker.encryption.awsKms.dynamodbTimeout`), `memory`-backed dev preset, KIND dev-image build target, optional (opt-in) ExtProc deployment. Compliance: `adrs/028-deployability-foundation.md`, `specs/033-aib-deployability-foundation/`, chart `AGENTS.md`, `helm template`-based chart-render tests in `tests/integration/helm_chart_test.go`, `ARCHITECTURE.md` entry. |
| **#6 PR-ADR-AIB-002** | `feature/access-check` | Fail-closed actor→resource→action decision service (`internal/domain/accesscheck`) with two thin adapters — HTTP `POST /api/access/check` and Envoy `ext_authz` gRPC `Check` (`cmd/access-check-grpc`) — sharing a stable reason vocabulary; folds the outcome-reason-codes work (`platform_grant_missing` vs `user_grant_required` split, structured re-auth). Compliance: `adrs/029-access-check-decision-service.md`, `specs/034-access-check-api/`, four package `AGENTS.md`, `docs/configuration.md` `access_check.*` section, `api/enduser/openapi.yaml`, Ginkgo E2E `tests/e2e/access_check_test.go` (granted / platform_grant_missing / invalid_actor_token / resource_unknown / request-validation). Also migrated the deprecated Envoy `HeaderValueOption.Append` boolean to the `AppendAction` enum. New-code coverage 84–98%. |
| **#7 PR-ADR-AIB-001** | `feature/python-sdk` | The `aib` package ported into an isolated `sdk/python/` subtree (`aib-sdk`): two-identity context propagation (`instrument.py`), RFC 8693 actor-token lifecycle (`identity.py`), access-check client + gateway-outcome interpretation (`client.py`), PEP 561 typed. Compliance: `adrs/030-python-sdk-subtree.md`, `specs/035-python-sdk/`, `sdk/python/AGENTS.md` + `README.md`, `pyproject.toml` (black + ty + pytest ≥80% gate), `just sdk-test`/`sdk-lint` targets kept **outside** `check`/`verify`. 66 tests pass, 89% coverage. |

## Validation

- **#5**: `just check` (0 lint issues) + chart-render integration tests green locally.
- **#6**: `just check` (0 issues after the Envoy `AppendAction` migration), the fast `just test` subset (race) green, full backend Ginkgo E2E (431 specs) green, access-check package coverage 84–98%.
- **#7**: `just sdk-lint` (black `--check` + `ty check`) green, `just sdk-test` 66 passed / 89% coverage; Go `just check` unaffected (subtree isolated).
- Heavy `just verify` sub-targets (`web-test`, `cdk-test`, `test-integration-all`, full `test-e2e`) are deferred to reviewer CI and noted in each PR.

## Follow-ups

- Re-target the three draft PRs from the `axsaucedo/aib-tmp` fork to `zalando-infosec/agentic-identity-broker:main` once direct push/fork access to the upstream is available, preserving the stack order.
- Reconcile upstream review feedback and land in dependency order (foundation → access-check → SDK).
- Upstream overlap to call out in review: `origin/013-token-exchange`, `origin/020-extproc-opa-authorization`, `origin/026-extproc-approval-sync` are adjacent to the access-check surface.
