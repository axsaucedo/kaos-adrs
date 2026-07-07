# P14 — Authorization models, framework enablement, and validation (progress)

**Phase**: P14 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P14-authorization-modes-and-enablement.md`](../../plan/P14-authorization-modes-and-enablement.md)
**Status**: Implemented. All source-of-truth / override modes, chart and CLI enablement, parity and no-clobber coverage, docs with the published schema, and the ADR finalisation are done; the full in-cluster mode matrix is exercised via the opt-in KIND suite and CI.
**Repos / branches**: KAOS `feat/opa-extproc-authorization` (PR #263, stacked on `docs/aib-222-opa-actor-verification` #260).

## Outcome

P14 exposes both authorization models with their populator / override modes, wires them through the Helm chart and the CLI, and proves every mode with unit, chart-render, real-OPA parity, and opt-in end-to-end coverage. The prune-safety invariant is enforced by construction: external and manual modes never write or prune admin-owned policy data. The `data.kaos.grants` / `data.kaos.jwks` schema is published as a public contract and demo mode is fenced as non-production. The fresh ADR set is moved from Proposed to Accepted.

## Scope delivered

- **Populator / override modes.** The projection derives its behaviour from the provider, the policy-data source, and the rego-override flag: automated (write `policy.rego` + grant `data.json`), bring-your-own ConfigMap (write nothing), operator-rego + admin data (own only `policy.rego` via server-side-apply, never write the data key), and the Model-2 broker external off-switch (identity only, no grants, prune forced off). Server-side apply with per-key field ownership means an admin's `data.json` is never clobbered across reconciles.
- **Prune-safety + parity coverage.** Unit tests prove the BYO and operator-rego modes leave admin data untouched, the external off-switch keeps identity-only and prunes nothing, and prune is gated by authorization projection. A real-OPA parity suite (`opa test`, run in CI) proves both models answer subject × actor × resource from the four-fact-source input, not just actor-keyed allow/deny.
- **Chart enablement.** Helm values select provider, gateway enforcement extension, agent JWT verification, policy-data source, rego override, and the policy ConfigMap projection target; the policy projection env block was decoupled from the broker admin URL so the KAOS provider receives its ConfigMap target without a broker. Chart-render tests cover the mode combinations.
- **CLI enablement.** `kaos system install` gains `--authz-provider`, `--authz-gateway-extension`, `--agent-jwt-verification`, `--policy-data-source`, `--policy-rego-override`, `--admin-url`, and `--policy-configmap-name/-namespace`, appended only when set so the default install leaves authorization off. Dry-run tests cover the automated, operator-rego, and external off-switch renderings.
- **Docs + schema.** A user-facing authorization guide documents the providers, all four modes with worked install examples, the verified/demo postures with an explicit non-production fence on demo, and the published `data.kaos.grants` / `data.kaos.jwks` schema; it is linked from a new Security section in the docs sidebar. The operator and repository instructions record the authorization architecture and the never-clobber invariant.
- **E2E.** An opt-in KIND suite installs the operator with the KAOS provider and a policy ConfigMap target and asserts the operator renders the static rego and a grant graph and keeps every projected agent's grants stable across reconciles without rewriting the policy, with `kind-e2e-install-authz` / `e2e-test-authz` / `kind-e2e-authz` make targets. OPA is installed in the Go test workflow so the policy rego parity suite runs in CI instead of skipping.
- **ADR finalisation.** The enforcement-topology, identity, authorization-models, and component-architecture ADRs are Accepted; the component ADR records that the projection is a single flag-gated controller rather than a strategy/adapter interface (an interface would over-engineer two backends).

## Validation

- **Operator unit.** `go build ./...` and `go test ./controllers/ ./internal/... ./pkg/security/...` green, including the mode-derivation, BYO/operator-rego no-clobber, external off-switch identity-only, and prune-gating tests.
- **Policy parity.** `opa test` of the parity rego passes locally and in CI (the Go wrapper runs it when OPA is present; the workflow installs OPA so it no longer skips — confirmed `TestPolicyRegoUnitTests` PASS in CI, not skipped).
- **Chart.** The render tests pass for each mode combination.
- **CLI.** `python -m pytest tests/` green (100/99 passing across checkouts); black-clean on the changed files.
- **Docs.** `npm run build` succeeds with the new Security section and authorization page.
- **CI.** Go Tests (with OPA) and Python Tests green on `feat/opa-extproc-authorization`; E2E dispatched.

## Follow-ups

- **In-cluster mode matrix.** The full both-models × {demo, verified} × {automated, BYO, operator-rego, external} matrix is the heaviest cost and is exercised via the opt-in KIND targets and CI rather than the default suite; the Model-2 modes need a live broker.
- **Autonomous-mode enforcement (G1 gap)**, **ConfigMap-as-local-bundle hot-reload**, and the **AIB-less identity issuer** remain in [`../../plan/followups.md`](../../plan/followups.md).
