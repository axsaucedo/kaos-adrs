# P4 — network policy and TLS (progress)

**Phase**: P4 of [`../../plan/proposed-split.md`](../../plan/proposed-split.md)
**Plan**: [`../../plan/P4-network-policy-and-tls.md`](../../plan/P4-network-policy-and-tls.md)
**Status**: Implementation complete. KAOS now closes the gateway-bypass gap that the earlier authentication/authorization phases (P6–P10) depended on without realising it: it generates a per-workload NetworkPolicy that denies direct workload-to-workload traffic, repoints internal agent→ModelAPI/MCP/peer hops through the Envoy Gateway so the gateway's JWT/ext_authz/ext_proc filters actually apply to them, and terminates HTTPS at the gateway. In-cluster enforcement validation (which requires a NetworkPolicy-enforcing CNI) is performed in the dedicated end-to-end validation block that follows.
**Date**: 2026-06-23
**PR**: stacked onto `feat/sync-service-productionisation` (the P10 branch)

## Outcome

P6–P10 wired authentication and authorization at the Envoy Gateway, but the operator injects **direct `svc.cluster.local` URLs** for every internal hop (`MODEL_API_URL`, `MCP_SERVER_*_URL`, `PEER_AGENT_*_CARD_URL`). Internal agent→MCP/ModelAPI/peer traffic therefore bypassed the gateway entirely, so none of the gateway's authn/authz filters were enforced on it — there was no real end-to-end authorization path to validate. P4 closes that gap with two complementary mechanisms plus transport security:

- **NetworkPolicy (block the bypass)**: the operator reconciles an ingress-only `networking.k8s.io/v1` NetworkPolicy for every protected workload (Agent, MCPServer, ModelAPI) that allows ingress only from the gateway namespace and the operator namespace. Direct pod-to-pod traffic from another agent is denied, so a workload can only be reached through the gateway. The policy is owned by the workload (garbage-collected with it) and is a no-op unless agent-auth is operational and NetworkPolicy is enabled.
- **Gateway routing (reroute through the gateway)**: blocking alone would break agent→MCP traffic, because the injected URLs point straight at the backend service. When gateway routing is enabled the agent controller repoints those URLs to `http://<gatewayHost>/<ns>/<type>/<name>`, which the pre-existing HTTPRoutes (path-prefix `/{ns}/{type}/{name}` + URLRewrite to `/`, no hostname binding) forward to the correct backend. The gateway host is taken from explicit config or the Gateway resource's `.status.addresses[0]`; if neither resolves the controller falls back to direct URLs rather than silently breaking traffic. Off by default.
- **Gateway TLS (transport security)**: a `security.tls` block adds an HTTPS/443 listener to the Gateway with `certificateRefs`, supporting `selfSigned` (chart-generated, lookup-guarded reusable Secret), `certManager` (renders a `Certificate` from a configured `issuerRef`), and `provided` (references an existing `kubernetes.io/tls` Secret). With no mode set, only the HTTP listener is created and behaviour is unchanged.

## Deliverables

| Area | Deliverable |
|---|---|
| NetworkPolicy generator | `operator/pkg/security/networkpolicy.go` — `NetworkPolicyParams`, `constructNetworkPolicy` (ingress-only, allow-from gateway + operator namespaces, dedups when the two namespaces coincide), `ReconcileNetworkPolicy` (no-op unless `NetworkPolicyEnabled`, create-or-update, `SetControllerReference`). `networkpolicy_test.go` — shape/dedup/default-namespace + fake-client create/no-op tests. |
| Security config | `operator/pkg/security/config.go` — `GatewayNamespace`, `OperatorNamespace`, `NetworkPolicyDisabled`, `GatewayHost`, `GatewayRouting` fields; env consts; `parseBoolEnv`; `NetworkPolicyEnabled()`, `GatewayNamespaceOrDefault()`, `OperatorNamespaceOrDefault()`, `GatewayRoutingEnabled()`. Defaults: gateway ns `envoy-gateway-system`, operator ns `kaos-system`. |
| Controller wiring | `agent_controller.go` — `applyGatewayRouting` repoints modelapi/mcp/peer URLs before the deployment env is built; `mcpserver_controller.go` / `modelapi_controller.go` — `ReconcileNetworkPolicy` calls. `main.go` — `networkpolicies` RBAC marker; `config/rbac/role.yaml` regenerated. `agent_gateway_routing_test.go` — repoint on/off/no-host tests. |
| Gateway helper | `operator/pkg/gateway/gateway.go` — `StatusAddress(ctx, c)` reads the Gateway `.status.addresses[0].value`; `GatewayEndpoint(host, ns, type, name)` builds the routed URL. |
| Chart | `chart/values.yaml` — `security.gatewayNamespace`, `security.gatewayHost`, `security.networkPolicy.enabled` (true), `security.gatewayRouting.enabled` (false), `security.tls` (mode/certManager.issuerRef/secretName). `templates/operator-configmap.yaml` — env wiring. `templates/gateway.yaml` — HTTPS listener when `security.tls.mode` set. `templates/gateway-tls.yaml` — selfSigned Secret / certManager Certificate / provided. `templates/kaos-operator-rbac.yaml` — hand-mirrored `networkpolicies` rule. |
| CLI | `kaos-cli/kaos_cli/system/__init__.py` + `install.py` — `--network-policy/--no-network-policy`, `--gateway-routing/--no-gateway-routing`, `--gateway-host`, `--tls-mode`, `--tls-issuer-name`, `--tls-issuer-kind`, `--tls-secret-name`; threaded into `security.*` Helm `--set` args, defaulting to prior behaviour. |

## Validation

- **Operator unit tests**: `go test ./pkg/security/ ./pkg/gateway/ ./controllers/` → all pass; `gofmt`/`go vet` clean; `go build ./...` OK. New coverage: NetworkPolicy shape/dedup/default-namespace + reconcile create/no-op; gateway-routing repoint on/off/no-host; config knobs.
- **CLI tests**: `cd kaos-cli && python -m pytest tests/ -q` → 91 passed; `black --check` clean. New coverage: network-policy disable, gateway routing + host, all three TLS modes, and omission when defaults apply.
- **Chart**: `helm lint` clean; `helm template` renders correctly across all TLS modes (selfSigned → reusable Secret, certManager → Certificate, provided → references existing Secret, no mode → HTTP only) and renders NetworkPolicy/routing env + HTTPS listener together with auth wiring without conflict.
- **In-cluster NetworkPolicy enforcement** (direct ClusterIP curl denied, repointed gateway path allowed + authz-checked, TLS terminated): deferred to the genuine end-to-end validation block that follows P4, because the local `kind-kaos-e2e` cluster uses kindnet, which does **not** enforce NetworkPolicy. That block rebuilds a throwaway Calico KIND cluster (`disableDefaultCNI: true` + Calico) and runs the full authz dataflow against it.

## Notes

- NetworkPolicy enforcement depends on the CNI. kindnet (default KIND) accepts NetworkPolicy objects but does not enforce them; Calico/Cilium do. The objects are always generated; enforcement is a cluster-capability concern documented for the e2e block.
- Gateway routing is **default-off** to avoid changing traffic paths for installs that haven't opted into gateway-enforced authz. NetworkPolicy is **default-on** when agent-auth is operational, but only blocks; it never reroutes — the two must be enabled together for a working bypass-proof install.
