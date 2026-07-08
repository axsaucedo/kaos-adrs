# Strict gateway-only traffic, decoupled from authorization — implementation plan

**Branch (KAOS)**: `feat/strict-gatewayapi-networkpolicy`, the **top of the P13 → P14 → P15 stacked series** (stacked on the P14 branch; retarget to `main` once the lower PRs merge). Builds directly on the P13 security-config decoupling that separates the "security enabled" predicate from `ExtAuthzURL`.
**Tracking issue**: TBD.

**Relationship to P16**: P15 lands the strict-gateway *mechanism* (operator config + chart + one CLI flag) and exposes it as **`--gateway-api-strict`** (helm `security.strictGatewayApi.enabled`, env `SECURITY_STRICT_GATEWAY_API_ENABLED`). P16 then folds this flag into the drastically-simplified two-preset install surface and validates it in the final end-to-end pass. Use the flag name **`--gateway-api-strict`** everywhere for consistency with P16.

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1-3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null` (create it if missing). Do NOT use `/tmp`.
- Operator Go commands require `GOTOOLCHAIN=go1.26.0`; integration/envtest needs `KUBEBUILDER_ASSETS=<repo>/operator/bin/k8s/1.28.3-darwin-arm64`. Helmify (`make helm`) clobbers `chart/values.yaml`, `chart/templates/deployment.yaml`, and unrelated `chart/crds/*`; restore the ones you did not intend to change.
- End: gitignored `REPORT.md` (this work), posted as a PR comment (not committed). Copy this plan is already in `kaos-ai-docs/security-and-identity/plan/P15-strict-gatewayapi-decoupling.md`; write `impl/progress` + `impl/learnings` entries.

## Problem statement

Today the operator only generates bypass-prevention `NetworkPolicy` (and honours gateway-routed internal URLs) when the full authorization stack is operational — i.e. when `security.agentAuth.extAuthzUrl` is set. This means a deployment cannot get "the gateway is the only application path between workloads" (deny direct ClusterIP, force all agent->MCP/ModelAPI/peer traffic through the Envoy Gateway) without also standing up ext_authz. Those are two independent concerns: network-level isolation is useful on its own (defence in depth, forcing traffic through the gateway where jwt_authn/TLS still apply) even when access-check authorization is not deployed.

This phase **decouples network isolation + gateway routing from ext_authz** and exposes it as a single positively-named switch. The current inverse escape hatch `security.networkPolicy.enabled` (which only ever emits `SECURITY_NETWORK_POLICY_DISABLED=true` when set to `false`) is **renamed to a positive `security.strictGatewayApi.enabled`** so the name states the intent ("gateway-only strict traffic") rather than the mechanism. The default stays off; non-secured installs are unchanged. The phase also **measures the e2e runtime delta** of running the suite under strict gateway traffic and decides whether it runs inline or as its own shard.

## Current-state grounding (researched)

- **Coupling lives in Go, not the chart.** `operator/pkg/security/config.go`:
  - `IsOperational()` (~L154) = `ExtAuthzURL != ""`.
  - `NetworkPolicyEnabled()` (~L254) = `IsOperational() && !NetworkPolicyDisabled` — this is the load-bearing coupling to remove.
  - `NetworkPolicyEgressEnabled()` (~L262) = `NetworkPolicyEnabled() && NetworkPolicyEgress`.
  - `GatewayRoutingEnabled()` (~L293) = `GatewayRouting` (already independent of ext_authz; a positive flag `SECURITY_GATEWAY_ROUTING_ENABLED`).
  - Struct fields (`NetworkPolicyDisabled`, `NetworkPolicyEgress`, `GatewayRouting`) at ~L70-93; env consts block at ~L97-111; `GetConfig()` reads them at ~L118-138.
- **Chart already emits the relevant env unconditionally (only its own guards).** `operator/chart/templates/operator-configmap.yaml`: the "Bypass-prevention and gateway-routing" region (~L59-77) emits `SECURITY_OPERATOR_NAMESPACE`, and — each behind its own `if` — `SECURITY_NETWORK_POLICY_DISABLED` (`when .networkPolicy && not .networkPolicy.enabled`), `SECURITY_NETWORK_POLICY_EGRESS_ENABLED`, and `SECURITY_GATEWAY_ROUTING_ENABLED`. These are NOT nested under the `extAuthzUrl` conditional, so standalone rendering already works at the chart layer — only the Go `IsOperational()` gate blocks standalone behaviour at runtime.
- **values.yaml** (~L125-140): `security.networkPolicy.enabled: true`, `security.networkPolicy.egress.enabled: false`, `security.gatewayRouting.enabled: false`, plus `security.gatewayNamespace`, `security.gatewayHost`.
- **Consumers of the gates** (non-test): `operator/pkg/security/networkpolicy.go` (`ReconcileNetworkPolicy` no-ops unless `NetworkPolicyEnabled()`), `operator/controllers/agent_controller.go` (NetworkPolicy reconcile + gateway-routed URL injection). **Verify the MemoryStore controller** also honours the same `security.GetConfig()` path (M4 added Gateway API + NetworkPolicy parity for MemoryStore — confirm it reconciles NetworkPolicy under the new flag too).
- **CLI** `kaos-cli/kaos_cli/system/__init__.py`: `--network-policy/--no-network-policy` (default `True`, help "Effective only with --auth-enabled"), `--network-policy-egress`, `--gateway-routing/--no-gateway-routing`, `--gateway-host`. `kaos-cli/kaos_cli/install.py` (~L601-625) emits `--set security.networkPolicy.enabled=false` and `security.networkPolicy.egress.enabled=true`. Dry-run assertions in `kaos-cli/tests/test_cli_integration.py` (~L1033-1066).
- **CNI gotcha (critical for validation).** The KIND e2e cluster uses the default **kindnet** CNI, which does **not** enforce `NetworkPolicy`. Generated policies are inert there; proving "direct ClusterIP is denied" requires recreating the cluster with `disableDefaultCNI: true` + Calico. Calico rollout is the dominant added cost for any strict-gateway e2e run, not the tests themselves.
- **UI tests** currently assume direct workload access and **will fail** under strict gateway routing until updated (already flagged). Track/exclude them explicitly.

## Design decision to make explicit (record the tradeoff in the PR)

What does the strict switch bundle?

- **Option A (recommended).** One positive flag `security.strictGatewayApi.enabled` that turns on **both** NetworkPolicy isolation **and** gateway routing, independent of `extAuthzUrl`. Rationale: the two are only useful together — NetworkPolicy without gateway routing breaks connectivity (workloads can no longer reach each other directly and nothing redirects them through the gateway); gateway routing without NetworkPolicy is trivially bypassable. Bundling prevents the incoherent half-configured states that exist implicitly today. Keep `egress` as an independent sub-toggle (egress isolation can break provider calls). Preserve the ext_authz-driven path so secured installs keep generating NetworkPolicy automatically.
  - *Pros*: one coherent switch, no broken-connectivity foot-guns, name matches intent. *Cons*: slightly less granular (cannot enable NP-only).
- **Option B.** Keep NetworkPolicy and gateway routing as two independent flags, each decoupled from `IsOperational()`.
  - *Pros*: maximal granularity. *Cons*: re-exposes the NP-on/routing-off broken state that today is implicitly prevented; more support surface.

Proceed with **Option A** unless review prefers B.

## Design plan (how it fits)

`operator/pkg/security/config.go`:
- Add field `StrictGatewayAPI bool` + env const `SECURITY_STRICT_GATEWAY_API_ENABLED`; read it in `GetConfig()` via `parseBoolEnv`.
- Rewrite `NetworkPolicyEnabled()` to `return c.StrictGatewayAPI || (c.IsOperational() && !c.NetworkPolicyDisabled)` — standalone strict OR the existing auth-driven path with its escape hatch.
- Make `GatewayRoutingEnabled()` return `c.GatewayRouting || c.StrictGatewayAPI` (Option A bundling).
- Update the doc comments that currently say NetworkPolicy "requires security to be operational".
- Decide the fate of the old `NetworkPolicyDisabled` hatch: keep it (still meaningful for the auth-driven path on misbehaving CNIs) but document that under `strictGatewayApi.enabled` the strict flag wins.

`operator/chart/values.yaml` + `operator/chart/templates/operator-configmap.yaml`:
- Add `security.strictGatewayApi.enabled: false` with an explanatory comment. Emit `SECURITY_STRICT_GATEWAY_API_ENABLED: "true"` when set (outside the `extAuthzUrl` conditional, next to the other bypass-prevention env).
- Rename the inverse hatch: replace `security.networkPolicy.enabled` semantics. Cleanest for alpha (no migration docs): drop `security.networkPolicy.enabled` and fold the disable-hatch into a clearly-named key (e.g. keep `security.networkPolicy.egress.enabled` for egress, and represent "force off" as simply not setting `strictGatewayApi.enabled` and leaving ext_authz unset). Confirm no template still references the removed key. Document the values-schema change prominently in the PR body.

`kaos-cli` (`system/__init__.py` + `install.py`):
- Add `--gateway-api-strict/--no-gateway-api-strict` (default off) mapping to `--set security.strictGatewayApi.enabled=true`. Update `--network-policy` help (drop the "Effective only with --auth-enabled" caveat, or remove the flag if fully superseded — decide and keep `--network-policy-egress` working). This flag is retained by the P16 simplified surface.
- Update `kaos-cli/tests/test_cli_integration.py` dry-run assertions.

## Numbered TODOs

1. **Decouple NetworkPolicy + gateway routing from ext_authz (security config).** In `operator/pkg/security/config.go` add `StrictGatewayAPI` field, `SECURITY_STRICT_GATEWAY_API_ENABLED` const, and `GetConfig()` wiring; rewrite `NetworkPolicyEnabled()` and `GatewayRoutingEnabled()` per Option A; fix comments. Extend `operator/pkg/security/config_test.go`: strict-on with `ExtAuthzURL` empty enables NetworkPolicy and gateway routing; strict-off falls back to the ext_authz path; escape-hatch interaction. **Validate**: `GOTOOLCHAIN=go1.26.0 go test ./pkg/security/... && go build ./... && go vet ./...`. Commit.
2. **Confirm controller behaviour under the standalone flag.** Verify `networkpolicy.go`, `agent_controller.go`, and the **MemoryStore** controller all reconcile NetworkPolicy / inject gateway-routed URLs when only `strictGatewayApi` is set (no ext_authz). Add/extend an integration or unit assertion proving a NetworkPolicy is generated with `StrictGatewayAPI=true` and `ExtAuthzURL=""`. **Validate**: `GOTOOLCHAIN=go1.26.0 KUBEBUILDER_ASSETS=... go test ./controllers/... ./pkg/...`. Commit.
3. **Chart wiring + rename.** Add `security.strictGatewayApi.enabled` to `values.yaml`; emit `SECURITY_STRICT_GATEWAY_API_ENABLED` in `operator-configmap.yaml`; remove/rename the old `networkPolicy.enabled` inverse hatch; keep egress toggle. Run `make helm` and restore clobbered files. **Validate**: `helm template` with/without the flag and with `extAuthzUrl` empty shows the NetworkPolicy env + (Option A) gateway-routing env appearing standalone; confirm no dangling references to the removed key. Commit.
4. **CLI flag.** Add `--gateway-api-strict/--no-gateway-api-strict` to `system/__init__.py`; wire `--set security.strictGatewayApi.enabled=true` in `install.py`; adjust `--network-policy` help/behaviour. Update `kaos-cli/tests/test_cli_integration.py`. **Validate**: `cd kaos-cli && .venv/bin/python -m pytest tests/ -k "install or network or gateway"`. Commit.
5. **Runtime-delta assessment (deliverable).** Measure, with the KIND e2e suite: (a) baseline current cluster-create + test wall-clock, and (b) strict-gateway wall-clock — cluster recreated with `disableDefaultCNI: true` + Calico, installed with `--strict-gateway-api`, all component traffic via the gateway host. Report both cluster-bringup delta (Calico rollout dominates) and test-phase delta. Note the UI-test failures under strict routing. Write findings to `impl/learnings/`. Be token/time-efficient — one focused pass, not repeated full runs.
6. **Strict e2e enforcement validation.** With the Calico cluster from (5), deploy an Agent + MCPServer + ModelAPI and prove: direct ClusterIP application traffic is **denied**, and the gateway path **works** end to end. If the runtime delta is large, land the strict-gateway e2e as its **own shard triggered only on relevant changes** (mirroring the memory-e2e shard) rather than converting the whole suite. Decide inline-vs-shard from the (5) numbers and record it. Commit any CI wiring.
7. **Docs.** Update `docs/` gateway/security pages and the security instruction notes to describe `strictGatewayApi.enabled` as a standalone switch (works without ext_authz), the CNI requirement (Calico) for enforcement, and the UI/strict-routing interaction. Update the values comments. Commit.

## Validation summary

- Unit: `go test ./pkg/security/...`; build + vet clean.
- Integration/envtest: NetworkPolicy generated under `strictGatewayApi` alone.
- Helm render: strict env appears with `extAuthzUrl` empty; no references to the removed key.
- CLI: dry-run assertions updated and green.
- Manual KIND (Calico): direct ClusterIP denied, gateway path works; runtime delta measured and written up.

## Risks / open questions

- **Values rename back-compat.** Pre-1.0 clean rename vs. a deprecation alias for `security.networkPolicy.enabled` — decide and state in the PR (alpha: clean rename acceptable, no migration docs).
- **MemoryStore parity.** Confirm M4's MemoryStore gateway/NetworkPolicy generation fully honours the standalone flag.
- **Calico in CI.** Cost vs. keeping strict e2e as an opt-in shard — driven by TODO 5 numbers.
- **UI under strict routing.** Frontend must move onto the gateway path before its tests pass under strict; keep excluded/tracked until then.
