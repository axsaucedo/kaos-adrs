# CLI simplification, final end-to-end validation, and comprehensive documentation — implementation plan

**Branch (KAOS)**: `feat/cli-simplification-and-final-validation`, stacked on the P15 branch (`feat/strict-gatewayapi-networkpolicy`); retarget to `main` once the lower PRs merge.
**Tracking issue**: TBD.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1-3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null`. Do NOT use `/tmp`.
- Operator Go commands require `GOTOOLCHAIN=go1.26.0`; integration/envtest needs `KUBEBUILDER_ASSETS=<repo>/operator/bin/k8s/1.28.3-darwin-arm64`.
- End: gitignored `REPORT.md`, posted as a PR comment (not committed).

## Problem statement

Two gaps remain after the P13→P14→P15 authorization stack:

1. **The install surface is unusable in practice.** `kaos system install` exposes ~40 flags (`--ext-authz-url`, `--auth-issuer`, `--token-exchange`, `--ext-proc-url`, `--aib-chart-path`, `--user-auth`, `--keycloak-*`, `--network-policy*`, `--gateway-routing`, `--tls-*`, `--authz-provider`, `--authz-gateway-extension`, `--agent-jwt-verification`, `--policy-data-source`, `--policy-rego-override`, `--admin-url`, `--policy-configmap-*`, …). A user cannot reasonably compose a working secured install from these primitives; the correct combinations are tribal knowledge encoded only in test fixtures.

2. **The `aib` provider has never been validated end-to-end on a live cluster, and its enforcement is not fully wired.** The operator projects identity/permission-sets into the broker and the install wires token-exchange, but nothing enables the AIB ext_proc **OPA authorization** decision (`EXTPROC_AUTHORIZATION_*` + a mounted rego reading `granted_permission_sets`). The `kaos` (ConfigMap/demo) provider is only covered by an opt-in e2e and unit tests. There is no soup-to-nuts Keycloak→AIB→KAOS allow/deny proof, and no user-facing walkthrough.

P16 closes both by driving a **final manual end-to-end validation first**, using its findings as the single source of truth for (a) the fixes needed to make both providers actually enforce, (b) the two-preset simplified CLI, and (c) comprehensive documentation.

## Current-state grounding (researched)

- **CLI**: `kaos-cli/kaos_cli/system/__init__.py` `install()` has 54 `typer.Option` declarations (~40 functional install flags). The install orchestration lives in `kaos-cli/kaos_cli/install.py` (`install_system`, `_install_aib`, `_build_aib_extproc_args`, `_provision_token_exchange`, `_keycloak_realm_json`, `_default_*` helpers). Dry-run assertions in `kaos-cli/tests/test_cli_integration.py`.
- **Provider wiring today**: `--auth-enabled` installs AIB + Keycloak, sets `security.agentAuth.extProcUrl`/`adminUrl`, enables ExtProc **token exchange** (`extProc.enabled`, `oauth2.clientId/secret/assertion`) and provisions an ExtProc OAuth client + dummy third-party service. It does **not** set any `EXTPROC_AUTHORIZATION_*` (OPA allow/deny) nor mount a rego for the `aib` provider.
- **AIB ext_proc OPA capability (confirmed in the binary)**: `internal/extproc/authorization/authorizer.go` loads a rego from `authorization.policy.path` (file/dir, compile-once) or `authorization.policy.config_file` (bundle/SDK). The loader binds env with prefix `EXTPROC` + `.`→`_` (`EXTPROC_AUTHORIZATION_ENABLED`, `EXTPROC_AUTHORIZATION_POLICY_PATH`, `EXTPROC_AUTHORIZATION_POLICY_PACKAGE`, `EXTPROC_AUTHORIZATION_POLICY_DECISION`). The AIB chart in the working worktree templates only the token-exchange CEL authorization, not the ext_proc OPA block — so OPA authz is delivered via env + a volume mount regardless of the chart.
- **Operator projection**: `kaos` provider → `ConfigMapProjector` writes `policy.rego` (+ optional `data.json`) to a ConfigMap; `aib` provider → `BrokerProjector` registers services/permission-sets/agents and mints per-agent credential Secrets. For the `aib` provider the operator emits no rego ConfigMap today.
- **`#222` structural constraints (learnings)**: OPA is skipped when no user subject bearer is present (G1 autonomous gap); exchange runs before OPA on body-bearing requests; the exchange is subject-only (azp-freeze). Keying rego on the `x-agent-authorization` actor header side-steps azp for allow/deny but the agent runtime must inject that header per hop, and ext_proc must run in body mode.
- **Docs**: `docs/security/` has `authorization.md` (config reference), `aib-222-verification/` (in-AIB-checkout evidence), `opa-drop-in/` (old ext_authz swap). No install/walkthrough. Memory docs (`docs/python-framework/memory.md`, `docs/examples/redis-memory.md`) are the structural model for the new comprehensive security docs. Sidebar in `docs/.vitepress/config.ts`.
- **Prior manual E2E docs**: `kaos-ai-docs/security-and-identity/impl/learnings/manual-e2e-*.md` — the format to mirror for the final pass (Environment / What was validated / Bugs found+fixed / Findings / Scope boundary / Recommended follow-ups).
- **Cluster**: a KIND cluster (`kind-kaos-e2e`, kindnet CNI) is available. kindnet does not enforce NetworkPolicy — strict-gateway enforcement (`--gateway-api-strict`, P15) requires a Calico cluster.

## Design plan (how it fits)

### CLI target surface (drastic simplification)

Collapse the ~40 functional flags into a small, preset-driven surface. Retain infra/escape flags; fold all auth/authz/network primitives into three presets.

**Kept flags** (infra + escape hatch):
`--namespace`, `--release-name`, `--version`, `--wait`, `--chart-path`, `--set` (repeatable escape hatch), `--metallb-enabled`, `--monitoring-enabled`, `--redis-enabled`, `--gateway-enabled` (Gateway API install; the "--gatewayapi-enabled" in the brief).

**New security flags** (the whole secured surface):
- `--auth-enabled <mode>` — default value `aib-keycloak`; alternative `kaos-internal`. Presence enables security; absence = today's unsecured install.
  - `aib-keycloak`: full stack — install Keycloak + AIB, wire user auth (Keycloak issuer/audience), token exchange (ext_proc), the `aib` authorization provider with **OPA allow/deny actually enabled** (mount the operator/broker rego reading `granted_permission_sets`, set `EXTPROC_AUTHORIZATION_*`), verified agent-JWT mode, gateway routing, and per-agent credential mounting. This is the production-shaped preset.
  - `kaos-internal`: AIB-free demo — `kaos` provider, `automated` policy data source (operator writes `policy.rego` + `data.json` to the policy ConfigMap), demo verification, no Keycloak/AIB. The lightweight in-cluster enforcement preset.
- `--gateway-api-strict` — the P15 strict-gateway switch (`security.strictGatewayApi.enabled`); turns on NetworkPolicy isolation + gateway routing independent of auth. Composed on top of either preset or standalone.

**Removed/hidden flags**: all the auth/authz/network primitives become preset-derived defaults, reachable only via `--set` for advanced overrides. Advanced chart paths (`--aib-chart-path`, `--aib-values`, `--keycloak-chart-path`) are retained as hidden/advanced options because dev installs still need to point at local unpublished charts.

The three presets are implemented as **preset expanders** in `install.py` that produce the exact validated `--set`/helm argument lists proven by the manual E2E — no new mechanism, just curated defaults.

### Manual E2E (first, drives everything)

Stand up each preset on KIND and prove real allow/deny on the P4-routed data path, mirroring the `manual-e2e-*` format. The pass produces: (1) the concrete fixes to make `aib` enforce (OPA enablement + rego mount + actor-header injection confirmation), (2) the exact `--set` lists the presets must emit, (3) the walkthrough content for the docs.

### Documentation

A comprehensive `docs/security/` set modeled on the memory docs, incorporating ADR context (ADR 0001 enforcement topology, 0002 identity/authn, 0003 authorization models, 0004 component architecture/projection): overview + architecture, install with the three presets, identity model, authorization models & policy-data schema, verification modes, an end-to-end walkthrough per preset, and troubleshooting. Wire into the sidebar.

## Numbered TODOs

1. **Final manual end-to-end validation (demo preset).** On the KIND cluster, install the `kaos-internal` shape (kaos provider, automated policy data, gateway routing), deploy an Agent + MCPServer + ModelAPI, and prove allow/deny on the gateway-routed path (granted edge allowed; ungranted denied, fail-closed). Capture exact working `--set` values and any bugs. Write `impl/learnings/manual-e2e-final-validation.md` (demo section). **Validate**: real requests through the gateway. Fix any operator/chart bugs found and commit each fix functionally.
2. **Final manual end-to-end validation (keycloak+aib preset) + enforcement wiring.** Install Keycloak + AIB + KAOS aib provider; enable the AIB ext_proc **OPA authorization** (mount the rego reading `granted_permission_sets`, set `EXTPROC_AUTHORIZATION_*`); confirm per-hop `x-agent-authorization` injection and body-mode. Prove user-token allow/deny end-to-end (and record the G1 no-bearer autonomous bypass as a known constraint). Extend the learnings doc (aib section) with the exact working config. Commit the wiring changes (operator/chart/CLI helpers) that make aib actually enforce. **Validate**: real Keycloak-token requests through the gateway; allow reaches backend with exchanged token, deny blocked.
3. **Simplified CLI presets.** Add `--auth-enabled <aib-keycloak|kaos-internal>` and `--gateway-api-strict`; implement preset expanders in `install.py` emitting the validated `--set` lists from TODOs 1-2; remove/hide the superseded primitive flags (keep infra + `--set` + advanced hidden chart paths). Update `kaos-cli/tests/test_cli_integration.py` dry-run assertions to cover both presets and strict. **Validate**: `cd kaos-cli && .venv/bin/python -m pytest tests/`. Commit.
4. **CLI preset live re-validation.** Re-run both presets via the *new* flags on KIND (demo fully; keycloak-aib to the extent the cluster allows) to confirm the simplified surface reproduces the manually-validated installs. Record in the learnings doc. Fix discrepancies. Commit any adjustments.
5. **Comprehensive security documentation.** Author the `docs/security/` set (overview/architecture, install-with-presets, identity model, authorization models + policy-data schema, verification modes, end-to-end walkthrough per preset, troubleshooting) with ADR context; wire the sidebar in `docs/.vitepress/config.ts`; `npm run build` clean. Update `.github/copilot-instructions.md` + `.github/instructions/*` and the CLI docs to the simplified surface. **Validate**: `cd docs && npm run build`. Commit.
6. **Plan/learnings finalisation.** Update `proposed-split.md` (add P16, mark statuses), `impl/progress`, and finalise the learnings doc. Commit.

## Validation summary

- Manual KIND E2E: both presets prove allow/deny on the gateway-routed path (demo fully enforcing; aib enforcing with OPA enabled).
- Go: `go build/vet ./...`, `go test ./pkg/... ./controllers/...` green for any operator/chart changes.
- CLI: full `pytest` green; dry-run assertions cover both presets + strict.
- Docs: `npm run build` clean; sidebar renders.

## Risks / open questions

- **aib OPA rego delivery.** Whether to mount the operator-projected ConfigMap into the ext_proc pod (`policy.path`) or ship a static broker-side rego — decide from the E2E; prefer reusing the operator's projected policy for a single source of truth.
- **G1 autonomous gap.** aib preset does not enforce autonomous (no-bearer) runs; document as a known limitation (followup F3).
- **Keycloak token acquisition in an automated pass.** Interactive login may be unavoidable for a true user token; prefer a direct-grant/service-account token to keep the pass programmatic, else request one token from the HOST once.
- **Strict-gateway enforcement needs Calico.** The available kindnet cluster cannot prove NetworkPolicy denial; strict validation is deferred to a Calico cluster (shared with P15 TODO 5/6) — record rather than block.
- **Preset over-collapse.** Ensure `--set` still allows every previously-flag-controlled value so no capability is lost, only the default composition simplified.
