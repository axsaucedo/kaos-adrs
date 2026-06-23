# Bypass prevention and transport security — implementation plan

**Branch (KAOS)**: `feat/network-policy-and-tls`, stacked off `feat/aib-install-and-sync`; PR targets `feat/aib-install-and-sync`
**Tracking issue**: axsaucedo/kaos#231

## Execution rules (TOP PRIORITY — every task)

- Numbered TODOs one by one, no skipping. Per task: change -> validate tests pass -> commit (comprehensive, functional message describing WHAT changed; NO phase/task/ADR references in messages, branches, code comments, or PR text) with the `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>` trailer on KAOS commits.
- Push to the PR and validate CI green. Run Go/python tests locally; KIND available — run 1-3 checks locally before relying on CI; prefer the full suite in CI. Be efficient with testing. Alpha: breaking changes OK, no migration docs.
- Scratch under `./tmp/` (gitignored); suppress noise to `./tmp/null` (create it if missing). Do NOT use `/tmp`.
- End: gitignored `REPORT.md` (all prior phases + this work), posted as a PR comment (not committed). Copy this plan to `kaos-ai-docs/security-and-identity/plan/P4-network-policy-and-tls.md` and write `impl/progress` + `impl/learnings` entries.

## Problem statement

Make the gateway the *only* application path into protected workloads, and encrypt the external boundary. Two capabilities: (1) the operator generates a Kubernetes `NetworkPolicy` per protected workload (Agent / MCPServer / ModelAPI) so direct workload-to-workload ClusterIP application traffic is denied and only the Gateway (plus required platform traffic) can reach the workload — the Gateway cannot be bypassed; (2) the install gains a first-class `security.tls` configuration (`selfSigned` / `certManager` / `provided`) that drives an HTTPS Gateway listener backed by a standard `kubernetes.io/tls` Secret. Both are gated on security being operational and default-off so non-secured installs are unchanged.

## Current-state grounding (researched)

- **Security config**: `operator/pkg/security/config.go` reads env vars (`SECURITY_AGENT_AUTH_EXT_AUTHZ_URL`, `_ISSUER`, `_CREDENTIAL_SECRET_PREFIX`). `Config.IsOperational()` is true when `ExtAuthzURL` is set. `ExtAuthzBackendRef()` parses the ext_authz host into `name`/`namespace`/`port`. Env vars are wired from chart `security.agentAuth.*` via `operator/chart/templates/operator-configmap.yaml` (lines ~33-41).
- **SecurityPolicy precedent (mirror this pattern)**: `operator/pkg/security/securitypolicy.go` has `constructSecurityPolicy(params, cfg)` (builds an unstructured Envoy `SecurityPolicy`) and `ReconcileSecurityPolicy(ctx, c, scheme, owner, params, cfg, log)` (create-or-update, no-op when `!IsOperational()`, sets controller reference). Unit tests in `securitypolicy_test.go`, config tests in `config_test.go`.
- **Controller hooks**: each of `controllers/agent_controller.go` (~line 327), `mcpserver_controller.go` (~line 220), `modelapi_controller.go` (~line 294) calls `ReconcileSecurityPolicy` inside `if secCfg := security.GetConfig(); secCfg.IsOperational() { ... }`, right after `gateway.ReconcileHTTPRoute`. This is the exact insertion point for NetworkPolicy reconciliation.
- **Workload pod labels (NetworkPolicy podSelector targets)**: Agent pods carry `{"app":"agent","agent":<name>}`; MCPServer pods `{"app":"mcpserver","mcpserver":<name>}`; ModelAPI pods `{"app":"modelapi","modelapi":<name>}` (set in each controller's `constructDeployment`).
- **Gateway chart**: `operator/chart/templates/gateway.yaml` renders a single HTTP listener (`port: {{ .Values.gatewayAPI.listenerPort | default 80 }}`, `protocol: HTTP`) when `gatewayAPI.enabled && gatewayAPI.createGateway`. `values.yaml` has a `gatewayAPI` block (`enabled`, `createGateway`, `gatewayName`, `gatewayClassName`, `gatewayNamespace`, `listenerPort`, `listenerProtocol`) and a `security` block (only `agentAuth.*` today). No TLS modeling exists. `pkg/gateway/gateway.go` builds endpoint URLs as `http://{gatewayHost}/...` (line ~79).
- **CLI install**: `kaos-cli/kaos_cli/system/__init__.py` declares flags (`--gateway-enabled`, `--auth-enabled`, etc.); `kaos-cli/kaos_cli/install.py` `install_command` wires `--set gatewayAPI.*` and, under `auth_enabled`, `_build_auth_operator_args(...)`. `GATEWAY_CLASS_NAME = "envoy-gateway"`; Envoy Gateway data plane runs in namespace `envoy-gateway-system`. Dry-run/YAML-validation tests live under `kaos-cli/tests/`.
- **CNI gotcha (critical for validation)**: `operator/hack/kind-with-registry.sh` creates the KIND cluster with the default **kindnet** CNI, which does **not** enforce `NetworkPolicy`. Generated policies are inert on the standard KIND cluster; proving "direct ClusterIP access is blocked" requires Calico (`disableDefaultCNI: true` + Calico install) in a throwaway cluster, or the limitation must be documented. ADR-KAOS-009: "effectiveness depends on the cluster CNI... must be validated per cluster."

## Design plan (how it fits)

### Part A — NetworkPolicy bypass prevention (operator + chart + CLI)

- New file `operator/pkg/security/networkpolicy.go` mirroring `securitypolicy.go`, but using the **typed** `k8s.io/api/networking/v1` `NetworkPolicy` (not unstructured — the type is in the operator's existing client scheme):
  - `type NetworkPolicyParams struct { Name, Namespace string; PodSelector map[string]string; Labels map[string]string }`.
  - `constructNetworkPolicy(params NetworkPolicyParams, cfg Config) *networkingv1.NetworkPolicy` — selects the protected workload's pods via `PodSelector`, `PolicyTypes: [Ingress]` only (see decision below), with ingress rules allowing traffic **from the Gateway data-plane namespace** and **from the operator namespace** (status polling), using `namespaceSelector` on the well-known `kubernetes.io/metadata.name` label. An empty `from` is NOT used (that would allow all); a default-deny baseline is achieved by selecting the pods with `PolicyTypes: [Ingress]` and only the explicit allow-from rules.
  - `ReconcileNetworkPolicy(ctx, c, scheme, owner, params, cfg, log)` — no-op unless `cfg.NetworkPolicyEnabled()`; create-or-update; `controllerutil.SetControllerReference(owner, ...)`; same structure as `ReconcileSecurityPolicy`.
- **Ingress-only design decision (explicit)**: the load-bearing requirement is denying *inbound* direct workload-to-protected-ClusterIP application traffic, which is an **ingress** policy on the protected pods. We deliberately do **not** restrict egress in this phase: ModelAPI proxies egress to external LLM providers and workloads need DNS/registry/gateway/AIB egress, so an egress allow-list risks breaking unrelated traffic. Egress hardening is deferred to later operational hardening (P12). This keeps the change safe while still closing the bypass. Document this in the learnings.
- **Probe caveat**: kubelet health probes originate from the node (host), not a pod; most CNIs permit host->pod, so probes are unaffected. Where a CNI blocks them, narrow host access is documented as a limitation (per ADR-KAOS-009).
- **Config additions** in `config.go`:
  - `GatewayNamespace string` (env `SECURITY_GATEWAY_NAMESPACE`, default `envoy-gateway-system` when empty) — ingress source for gateway traffic.
  - `OperatorNamespace string` (env `SECURITY_OPERATOR_NAMESPACE`, falling back to `POD_NAMESPACE` if present, else `kaos-system`) — ingress source so the operator can still poll ClusterIP status endpoints.
  - `NetworkPolicyDisabled bool` (env `SECURITY_NETWORK_POLICY_DISABLED`) — escape hatch for CNIs that misbehave; `NetworkPolicyEnabled()` returns `IsOperational() && !NetworkPolicyDisabled`. Default: enabled whenever security is operational (NetworkPolicy is part of the required secured target per ADR-KAOS-009).
- **Chart wiring**: add `security.networkPolicy.enabled` (default `true`), `security.gatewayNamespace` (default `envoy-gateway-system`) to `values.yaml`; surface the matching env vars in `operator-configmap.yaml` (and `SECURITY_OPERATOR_NAMESPACE` from `{{ .Release.Namespace }}`, `POD_NAMESPACE` via fieldRef in the deployment if not already present).

### Part B — Gateway TLS (chart + CLI)

- **values.yaml** — add a `security.tls` block:
  ```yaml
  security:
    tls:
      mode: ""                 # "" (disabled) | selfSigned | certManager | provided
      certManager:
        issuerRef:
          name: ""
          kind: ClusterIssuer  # ClusterIssuer | Issuer
      secretName: ""           # mode=provided: existing kubernetes.io/tls Secret
  ```
- **gateway.yaml** — when `security.tls.mode` is non-empty and the Gateway is created, add an HTTPS listener on `443` with `tls.mode: Terminate` and `certificateRefs: [{ kind: Secret, name: <resolved-secret> }]`, alongside the existing HTTP listener. Resolved secret name: `selfSigned`/`certManager` -> `{{ gatewayName }}-tls`; `provided` -> `security.tls.secretName`.
  - **selfSigned**: render a `kubernetes.io/tls` Secret using Sprig `genSelfSignedCert`, guarded by `lookup` so an existing Secret is reused on upgrade (avoid cert churn each `helm upgrade`). Template into a new `templates/gateway-tls.yaml`.
  - **certManager**: render a `cert-manager.io/v1` `Certificate` (in `templates/gateway-tls.yaml`) with `secretName: {{ gatewayName }}-tls` and `issuerRef` from `security.tls.certManager.issuerRef` (KAOS does not create the issuer).
  - **provided**: reference `security.tls.secretName` directly; render nothing extra.
- The HTTP listener remains for in-cluster routing/dev; external TLS termination is the secured boundary (per ADR-KAOS-007). `pkg/gateway/gateway.go` URL generation stays HTTP for in-cluster status/routing (out of scope to switch to https here).

### Part C — CLI flags

- `system/__init__.py`: add `--tls-mode` (`selfSigned|certManager|provided`), `--tls-issuer-name`, `--tls-issuer-kind`, `--tls-secret-name`, and `--network-policy/--no-network-policy` (default on when auth-enabled). Pass through to `install_command`.
- `install.py`: when `tls_mode` is set, append `--set security.tls.mode=...` and the relevant `certManager.issuerRef.*` / `secretName` values; wire `security.networkPolicy.enabled` and `security.gatewayNamespace`. Mirror the existing `_build_auth_operator_args` helper pattern.

## Numbered TODOs

1. **NetworkPolicy generation library + security config.** In `operator/pkg/security/`: extend `config.go` with `GatewayNamespace`, `OperatorNamespace`, `NetworkPolicyDisabled` fields + their env constants + `NetworkPolicyEnabled()` and defaulting helpers (`GatewayNamespaceOrDefault()`, `OperatorNamespaceOrDefault()`); add `networkpolicy.go` with `NetworkPolicyParams`, `constructNetworkPolicy`, and `ReconcileNetworkPolicy` (typed `networking/v1`, ingress-only, allow-from gateway + operator namespaces, no-op unless `NetworkPolicyEnabled()`). Add `networkpolicy_test.go` and extend `config_test.go`: assert podSelector matches workload labels, `PolicyTypes == [Ingress]`, ingress allows exactly the gateway + operator namespaces, no policy when disabled/non-operational, and default namespaces resolve correctly. **Validate**: `cd operator && go test ./pkg/security/... && make test-unit`; `gofmt`/`go vet`.

2. **Wire NetworkPolicy reconciliation into the three controllers.** In `agent_controller.go`, `mcpserver_controller.go`, `modelapi_controller.go`, inside the existing `if secCfg.IsOperational()` block (next to `ReconcileSecurityPolicy`), call `security.ReconcileNetworkPolicy(...)` with the workload's pod labels as `PodSelector` (`{"app":"agent","agent":name}` etc.) and a name like `<route-name>` or `kaos-<type>-<name>`. Ensure the `networking/v1` type is registered in the controller scheme (it is part of client-go's built-in scheme; confirm `main.go` clientgoscheme is added). **Validate**: add/extend an envtest (controllers) asserting a `NetworkPolicy` is created when `SECURITY_*` envs make security operational and absent when off; `cd operator && make test-unit` (envtest) green; `make manifests generate` clean (no CRD drift — NetworkPolicy is built-in, no new CRDs).

3. **Chart: surface NetworkPolicy + namespace config.** Add `security.networkPolicy.enabled` (default `true`) and `security.gatewayNamespace` (default `envoy-gateway-system`) to `operator/chart/values.yaml`; wire `SECURITY_NETWORK_POLICY_DISABLED`, `SECURITY_GATEWAY_NAMESPACE`, and `SECURITY_OPERATOR_NAMESPACE` (from `{{ .Release.Namespace }}`) in `operator-configmap.yaml`; ensure the operator Deployment exposes `POD_NAMESPACE` via fieldRef if `OperatorNamespace` falls back to it. **Validate**: `helm template operator/chart --set security.agentAuth.extAuthzUrl=svc:9002` shows the env vars; `--set security.networkPolicy.enabled=false` suppresses the disable flag appropriately; `helm lint operator/chart`.

4. **Gateway TLS chart support.** Add the `security.tls` block to `values.yaml`; add an HTTPS/443 listener with `certificateRefs` to `gateway.yaml` when `security.tls.mode` is set; add `templates/gateway-tls.yaml` rendering the selfSigned `kubernetes.io/tls` Secret (`genSelfSignedCert` + `lookup` reuse) or the cert-manager `Certificate`, and referencing the provided Secret for `mode=provided`. **Validate**: `helm template` for each of the three modes renders the expected listener + secret/certificate and is valid YAML; `mode=""` renders only the HTTP listener (unchanged); `helm lint`. Capture the three `helm template` outputs under `./tmp/` for the REPORT.

5. **CLI flags for TLS and NetworkPolicy.** Add `--tls-mode`, `--tls-issuer-name`, `--tls-issuer-kind`, `--tls-secret-name`, `--network-policy/--no-network-policy` to `system/__init__.py` and thread them into `install.py` as `--set security.tls.*`, `security.networkPolicy.enabled`, and `security.gatewayNamespace`. **Validate**: extend `kaos-cli/tests/` dry-run/YAML-validation tests to assert the new `--set` args appear for each TLS mode and netpol toggle; `cd kaos-cli && source .venv/bin/activate && python -m pytest tests/ -v`; `make lint`.

6. **End-to-end local KIND validation + docs + PR/REPORT.** Validate enforcement on a Calico-backed cluster (kindnet does not enforce NetworkPolicy): in `./tmp/security/`, script a throwaway KIND cluster with `disableDefaultCNI: true` + Calico, install KAOS with `--auth-enabled` and a TLS mode, deploy a sample Agent->MCPServer with a granted edge, then assert (a) gateway path works and is TLS-terminated, (b) a direct ClusterIP curl from a scratch pod to the protected MCPServer is denied. Document the kindnet limitation if Calico is unavailable. Write `impl/progress/P4-*.md` + `impl/learnings/P4-*.md`, copy this plan to `plan/P4-network-policy-and-tls.md`. Push `feat/network-policy-and-tls`, open the stacked PR into `feat/aib-install-and-sync`, dispatch `go-tests`/`python-tests`/`e2e` on the branch (stacked PRs into a non-main base don't auto-trigger), confirm CI green, write the gitignored `REPORT.md` (P0–P4) and post it as a PR comment.

## Validation per task

- Per-TODO: run the targeted unit/lint locally before committing — operator `go test ./pkg/security/...` + `make test-unit` (envtest) + `make manifests generate` (no drift); kaos-cli `pytest` + `make lint`; chart `helm template`/`helm lint`.
- Existing e2e suite must stay green with security default-off (NetworkPolicy + TLS only render when configured). The enforcement e2e (T6) is local-only (Calico) and documented in `REPORT.md`; the standard KIND e2e in CI runs unchanged.
- Push the stacked PR and dispatch `go-tests.yaml` / `python-tests.yaml` / `e2e-tests.yaml` via `workflow_dispatch --ref feat/network-policy-and-tls`.

## Commit / PR strategy

- `feat/network-policy-and-tls` stacked off `feat/aib-install-and-sync`; one comprehensive, functional commit per TODO; PR into `feat/aib-install-and-sync`; keep CI green; Copilot co-author trailer on KAOS commits (kaos-ai-docs commits follow that repo's no-trailer convention).
- Push under the `axsaucedo` gh account (the EMU account can't push/comment on the personal repo); **keep the commit author as the repo default** — do NOT override author email when switching gh accounts. Restore the EMU account after.
- `REPORT.md` gitignored; contents posted as a PR comment.

## Out of scope (later phases)

Egress NetworkPolicy restriction and broader operational hardening (P12); switching in-cluster route URLs to HTTPS / native intra-service TLS, mTLS, SPIFFE, service mesh (out of scope by ADR-KAOS-007); Keycloak/user-auth + gateway `jwt_authn` (P6); `ext_proc` token exchange (P7); CRD identity override (P8); sync/SDK productionisation (P9/P10); upstreaming AIB (P14).

## Post-P10 review addendum (learning-driven refinement)

Re-grounded against the live operator after P6–P10. Two corrections to the original scope:

- **Base branch**: this work now stacks off `feat/sync-service-productionisation` (the P10 tip), not `feat/aib-install-and-sync`. The stacked PR targets `feat/sync-service-productionisation`.
- **NetworkPolicy alone is insufficient for a genuine end-to-end.** The operator injects **direct** `svc.cluster.local` URLs into agents for every internal hop — `MODEL_API_URL` (`modelapi.Status.Endpoint`, agent_controller.go:559), `MCP_SERVER_<name>_URL` (`mcp.Status.Endpoint`, :236/702), and `PEER_AGENT_<name>_CARD_URL` (`peerAgent.Status.Endpoint`, :251/726). All are `http://<svc>.<ns>.svc.cluster.local:<port>`. So an ingress-only NetworkPolicy that allows only the gateway + operator namespaces would **break** agent→MCP/ModelAPI/peer traffic outright rather than reroute it — the agents are still configured to talk directly. Blocking is necessary but does not by itself *force* traffic through the gateway.

  The gateway routing infrastructure already exists and is sufficient to carry these hops: `gateway.ReconcileHTTPRoute` is called by all three controllers, routes use a path-prefix match `/{namespace}/{resourceType}/{resourceName}` with a `URLRewrite` `ReplacePrefixMatch: "/"` (gateway.go:113/142) and **no hostname binding**, so an in-cluster request to the gateway address on `/{ns}/{type}/{name}/<client-suffix>` matches and rewrites to `/<client-suffix>` before reaching the backend on its service port. `gateway.GatewayEndpoint(gatewayHost, ns, type, name)` already builds exactly `http://<gatewayHost>/<ns>/<type>/<name>` but is currently **unused**.

  Therefore P4 gains a **gateway-routing repoint** pillar (new TODO 3): when enabled, the agent controller injects `gateway.GatewayEndpoint(...)` URLs for MCP/ModelAPI/peer instead of the direct `Status.Endpoint`, so that once the NetworkPolicy denies the direct path, the same calls flow through the gateway where P6 `jwt_authn`, P7 `ext_proc` token exchange and AIB `ext_authz` actually apply. Gateway host resolution: a new `SECURITY_GATEWAY_HOST` config (set by chart/CLI), with the controller able to fall back to the Gateway resource `.status.addresses[0].value` (the MetalLB/LoadBalancer address, reachable in-cluster on KIND). Gated behind a default-off `GatewayRoutingEnabled()` (security operational **and** the routing flag on) so existing installs are unchanged; the manual e2e block enables it to obtain the genuine end-to-end authz path. This is the linchpin that makes the P6–P10 internal-authz machinery observable end-to-end.

### Revised numbered TODOs

1. NetworkPolicy generation library + security config (as above).
2. Wire NetworkPolicy reconciliation into the three controllers + envtest (as above).
3. **Gateway-routing repoint (new).** Add `GatewayHost` config (`SECURITY_GATEWAY_HOST`) + `GatewayRoutingEnabled()` (default off); resolve the gateway host (explicit config, else Gateway `.status.addresses[0].value`); in the agent controller, when routing is enabled, inject `gateway.GatewayEndpoint(host, ns, type, name)` for MODEL_API_URL / MCP_SERVER_*_URL / PEER_AGENT_*_CARD_URL instead of the direct `Status.Endpoint`. Unit + envtest: with routing on, injected URLs point at the gateway host with the `/{ns}/{type}/{name}` prefix; with routing off, direct svc URLs unchanged.
4. Chart: surface NetworkPolicy + namespace config + `security.gatewayHost` + `security.gatewayRouting.enabled`.
5. Gateway TLS chart support (as original TODO 4).
6. CLI flags for TLS, NetworkPolicy, and gateway routing (as original TODO 5, plus `--gateway-routing`/`--gateway-host`).
7. Calico KIND e2e (deny-direct + repointed gateway path works + TLS) + docs + PR/REPORT — the genuine P6–P10 end-to-end authz baseline. Stacked PR into `feat/sync-service-productionisation`.
