# P14 — Authorization models, framework enablement, and validation — implementation plan

**Repo / branch (KAOS)**: a feature branch stacked on [P13](./P13-opa-extproc-authorization-core.md) in the KAOS worktree (exact name at execution; no phase/ADR reference in the branch name).
**Realises**: [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md); completes [ADR 0002](../adrs/adr_0002_identity-and-authentication.md) / [ADR 0004](../adrs/adr_0004_component-architecture-and-projection.md).
**Depends on**: P13 (enforcement core: OPA-in-ext_proc, folded projection controller, Model-1 emitter, verification).

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change → validate tests pass → commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits. Commit author stays the repo default.
- Push to the PR and validate CI green. Run Go/python/CLI tests locally; KIND available — run 1–3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- End: gitignored `REPORT.md`, posted as a PR comment (not committed). Update `impl/progress/` + `impl/learnings/` in the docs repo.

## Problem statement

P13 lands the enforcement core with CRD projection as the single (implicit) source of truth. This phase makes both authorization models first-class with their **source-of-truth / override modes**, exposes the whole surface through the Helm chart and `kaos` CLI, proves every mode end-to-end on KIND, documents it with worked examples, and finalises the ADR set. The central constraints are **model parity** (both models answer "can user A reach resource X via agent B") and the **prune-safety invariant** (external/manual modes never prune or clobber admin-owned config). See [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md).

## Current-state grounding (verified)

- After P13: `Project() → DesiredState` is model-agnostic; the Model-2 AIB admin adapter is the only bespoke integration; the Model-1 emitter writes `data.kaos.grants` (+ optional `data.kaos.jwks`) into a ConfigMap mounted into the ext_proc pod via `policy.path`; the projection reconciler owns AIB calls, the ConfigMap, and the credential Secret; `SecurityEnabled` is decoupled from `ExtAuthzURL`; config carries model / posture / verification / populator selectors.
- Whole-world sentinel prune already exists for AIB records; it must be gated per mode. Model 1 has no delete step (it only writes/omits the data key), so its "no-clobber" is achieved by not owning the admin-authored key.
- CLI install uses a helm/kubectl integration-flag pattern (`kaos system install --gateway-enabled`, `--metallb-enabled`, …); CLI integration tests validate rendered YAML (dry-run).

## Design plan (target state)

1. **Default CRD projection (P-crd)** is authoritative for both models. Manual overrides are explicit opt-ins, symmetric across models where possible. See [ADR 0003](../adrs/adr_0003_authorization-models-and-policy-data.md).
2. **Model 1 manual:** **M1-a** — operator points `policy.path` at an admin-provided ConfigMap and manages nothing inside it (no schema lock-in). **M1-b** — operator owns the `policy.rego` key via server-side-apply field ownership and never writes `data.kaos.grants`; the `data.kaos.grants` schema is published as a public contract (alpha accepts freezing it).
3. **Model 2 external off-switch:** disable authorization projection and **force prune off**; KAOS keeps identity (agent registration + credential Secret); enforcement reads AIB live via token-exchange `granted_permission_sets`. AIB UI is authoritative.
4. **Prune-safety invariant:** apply/prune are mode-gated from the start; external and manual modes never prune or clobber admin-owned config; proven by a "no-clobber across reconciles" test.
5. **Enablement:** chart values and `kaos system install` flags select model / posture / verification / populator mode with simple safe defaults.

## TODOs

1. **Default CRD projection wiring.** Confirm and lock P-crd as the authoritative default for both models behind the populator-mode config; unit-test that projection produces the expected `data.kaos.grants` (Model 1) and AIB admin bodies (Model 2) from the same `DesiredState`.
2. **Model-1 M1-a (bring-your-own ConfigMap).** Add the mode where the operator points OPA `policy.path` at an admin-provided ConfigMap and does not manage its contents. Unit + e2e that operator reconciles leave the ConfigMap untouched.
3. **Model-1 M1-b (operator-rego + admin data).** Operator owns the `policy.rego` key via SSA field ownership and never writes the `data.kaos.grants` key; publish the `data.kaos.grants` (+ `data.kaos.jwks`) schema. E2e that the operator updates rego but never overwrites admin-authored grants across reconciles.
4. **Model-2 external off-switch.** Add the mode that disables authorization projection and **forces prune off** while keeping identity projection (agent registration + credential Secret) active; enforcement reads AIB live via `granted_permission_sets`. E2e that KAOS registers identity but writes no permission-sets and prunes nothing.
5. **Prune-safety tests.** Add explicit tests proving apply/prune are mode-gated: in every external/manual mode the operator leaves admin-owned data untouched across repeated reconciles and never issues a delete.
6. **Parity coverage.** Add a test/example proving both models answer "can user A reach resource X via agent B" from the four-fact-source input (subject + actor + resource), not just actor-keyed allow/deny.
7. **Chart enablement.** Add Helm values for model selection, enforcement posture, verification mode, and populator mode; wire them to the operator config from P13. Chart-render tests per combination.
8. **CLI enablement.** Add `kaos system install` flags (and any `kaos`-side helpers) setting those values with simple safe defaults; CLI dry-run/integration tests validating the rendered YAML for each combination.
9. **E2E matrix on KIND.** Both models × {demo, verified} × {P-crd, M1-a, M1-b, Model-2 off-switch}, with allow/deny and no-clobber assertions. Prefer the full matrix in PR CI; run 1–3 representative cases locally first.
10. **Docs + examples.** Worked examples for each mode; publish the `data.kaos.grants`/`data.kaos.jwks` schema; explicitly fence demo mode as non-production. Update `.github/copilot-instructions.md` and relevant `.github/instructions/*` to reflect the folded architecture and the authorization modes.
11. **Finalise ADRs (docs repo).** Move the [ADR set](../adrs/adr_high_level_components.md) from Proposed to Accepted post-hoc; confirm the historical note in [ADR 0001](../adrs/adr_0001_enforcement-topology-and-policy-engine.md) accurately records the evolution off #398/#399; ensure `proposed-split.md` and `followups.md` reflect the built state.
12. **Push, CI, REPORT.** Push the PR, dispatch Go/Python/CLI/E2E workflows (switch to the `axsaucedo` gh account for dispatch, then back), confirm green. Write `REPORT.md` (uncommitted) and post it as a PR comment; update `impl/progress/` + `impl/learnings/`.

## Validation per TODO

Operator: `cd operator && make generate manifests && make test-unit`. CLI: `cd kaos-cli && source .venv/bin/activate && python -m pytest tests/ -v`. Chart-render tests for each mode combination. E2E: prefer CI; run 1–3 locally on KIND first (port-forward the Envoy Gateway on macOS per the e2e instructions). Scratch in `./tmp`, suppressed output to `./tmp/null`.

## Commit / PR / CI strategy

One comprehensive conventional commit per TODO describing exactly what changed — no phase/task/ADR references in messages, branches, or comments — with the Copilot co-author trailer. Push to a single PR; validate CI green before the next TODO where practical. The e2e matrix is the heaviest cost — keep it in CI and reproduce 1–3 locally only when CI fails.

## Notes / risks

- The mode matrix multiplies the test surface; keep the e2e matrix in CI and representative cases local.
- Publishing `data.kaos.grants` as a public contract is a commitment; alpha's freedom to break mitigates it, but document the schema explicitly.
- The prune-safety invariant is security-sensitive: a regression that prunes admin-owned config in an external/manual mode is a data-loss bug — the no-clobber tests are mandatory, not optional.
- Demo mode is spoofable; documentation must fence it as non-production while keeping verified mode one flag away.
