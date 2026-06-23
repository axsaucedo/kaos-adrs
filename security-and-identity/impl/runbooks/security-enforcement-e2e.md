# Runbook: security enforcement end-to-end validation (NetworkPolicy + gateway routing + gateway authz)

This is a reproducible how-to for the manual end-to-end validation of the KAOS security/identity enforcement path. It is written to serve two purposes: (1) a human runbook to bring the enforcement path up in a throwaway cluster and confirm it works, and (2) the executable specification for a programmatic e2e test suite. Each manual step below is paired with the assertion a programmatic test should make and the relevant existing e2e helper.

## Why this exists and what it proves

KAOS injects direct `svc.cluster.local` URLs for MCP/ModelAPI/peer endpoints, so by default internal agent->MCP/ModelAPI traffic bypasses the Envoy Gateway entirely and gateway authz never runs on that path. Two operator features close this: per-workload `NetworkPolicy` (block direct pod-to-pod) and gateway routing (rewrite the agent's injected URLs to go through the gateway). This runbook proves the combined guarantee end to end: the direct bypass is blocked, internal traffic is rerouted through the gateway, and the gateway enforces authz on that rerouted path.

## Critical environment constraint: the CNI must enforce NetworkPolicy

The default KIND CNI (kindnet) **accepts** `NetworkPolicy` objects but does **not enforce** them. Any test that asserts a direct connection is *blocked* must run on a NetworkPolicy-enforcing CNI such as Calico or Cilium. Assertions that only check the operator *generated* the right objects/URLs (NetworkPolicy objects exist, agent env is gateway-routed) work on kindnet too. A programmatic suite should therefore split into two tiers: a generation tier (CI-runnable on kindnet) and an enforcement tier (requires a Calico/Cilium cluster, run manually or in a dedicated CI lane).

## Prerequisites

- A built KAOS operator image that includes the Gateway-read RBAC rule (the operator reads the Gateway status address for routing, which requires `gateways` get/list/watch RBAC; without it the routing watch wedges reconciliation). Any operator at or after that fix is required — an older operator will appear to install fine but silently fall back to direct URLs.
- Locally built/available images for the operator, the agent runtime, and the python-string MCP runtime, loadable into the cluster.
- `kaos` CLI, `kubectl`, `helm`, `docker`, `kind` on PATH.

## Step 1 — Calico KIND cluster (enforcement tier)

```yaml
# tmp/security/e2e/kind-calico.yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  disableDefaultCNI: true
  podSubnet: "192.168.0.0/16"
nodes:
- role: control-plane
```

```bash
kind create cluster --name kaos-sec-e2e --config tmp/security/e2e/kind-calico.yaml
kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.27.3/manifests/calico.yaml
# Wait ~90s for calico-node and coredns to be Ready before proceeding.
kubectl -n kube-system rollout status ds/calico-node --timeout=180s
```

Programmatic equivalent: a session-scoped fixture that creates (or reuses, via an env flag like `KAOS_SEC_E2E_CLUSTER`) a Calico cluster. The enforcement tier must skip itself with a clear message when the active context's CNI does not enforce NetworkPolicy, so the generation tier can still run on the standard kindnet `kaos-e2e` cluster.

## Step 2 — Build and load images

```bash
# Operator built from the branch under test (MUST include the gateways RBAC rule).
(cd operator && docker build -t kaos-operator:sec-e2e .)
kind load docker-image kaos-operator:sec-e2e --name kaos-sec-e2e
# Agent runtime + python-string MCP runtime (use the repo's current dev tags).
kind load docker-image axsauze/kaos-agent:<dev-tag> --name kaos-sec-e2e
kind load docker-image axsauze/kaos-mcp-python-string:<dev-tag> --name kaos-sec-e2e
```

Programmatic equivalent: reuse the existing e2e image-build/load harness; parametrise the operator tag so the suite always tests the operator under change.

## Step 3 — Install KAOS with auth wiring + NetworkPolicy + gateway routing

The key insight that keeps this validation lightweight: NetworkPolicy generation and the operator-side auth wiring are gated only on `IsOperational()`, which is true as soon as `security.agentAuth.extAuthzUrl` is set. The ext_authz backend does **not** need to actually work for the P4 enforcement path (block + reroute + gateway JWT) to be generated and validated. So the full broker/Keycloak/ext_proc stack is **not** required for this enforcement runbook.

```bash
kaos system install \
  --gateway-enabled --metallb-enabled \
  --auth-enabled --no-user-auth --no-token-exchange \
  --network-policy --gateway-routing \
  --operator-image kaos-operator:sec-e2e
# No --aib-chart-path (assumes broker already present / not needed for enforcement),
# no --sync-chart-path (no credential provisioning needed for the deny+enforce path).
```

`--network-policy` AND `--gateway-routing` must be enabled **together**: NetworkPolicy on with routing off would block legitimate agent->MCP traffic (the agent would still hold direct URLs). This pairing requirement is intentional and is the first thing a programmatic test should encode.

Programmatic equivalent: an install fixture that runs the CLI with these flags and asserts the resulting operator configmap (`kaos-operator-config`) carries `SECURITY_AGENT_AUTH_EXT_AUTHZ_URL`, `SECURITY_GATEWAY_ROUTING_ENABLED=true`, `SECURITY_GATEWAY_NAMESPACE`, `SECURITY_OPERATOR_NAMESPACE`.

## Step 4 — Deploy a real workload

```yaml
# tmp/security/e2e/e2e-workload.yaml (namespace e2e-sec)
apiVersion: kaos.tools/v1alpha1
kind: ModelAPI
metadata: { name: e2e-modelapi }
spec:
  mode: Proxy
  proxyConfig:
    models: ["*"]
    provider: openai
    apiKey: { value: "dummy-key" }
---
apiVersion: kaos.tools/v1alpha1
kind: MCPServer
metadata: { name: e2e-echo-mcp }
spec:
  runtime: python-string
  params: |
    def echo(message: str) -> str:
        """Echo the provided message back."""
        return f"Echo: {message}"
---
apiVersion: kaos.tools/v1alpha1
kind: Agent
metadata: { name: e2e-agent }
spec:
  modelAPI: e2e-modelapi
  model: "gpt-test"
  mcpServers: [e2e-echo-mcp]
  config:
    description: "E2E agent for network policy validation"
    instructions: "You are a test agent."
    reasoningLoopMaxSteps: 3
```

```bash
kubectl create namespace e2e-sec
kubectl apply -n e2e-sec -f tmp/security/e2e/e2e-workload.yaml
# Wait for the agent to reach Ready (this also proves the gateways-RBAC watch is healthy:
# if RBAC is missing the agent hangs at "Waiting: ModelAPI is not ready").
kubectl wait -n e2e-sec --for=condition=Ready agent/e2e-agent --timeout=180s
```

Programmatic equivalent: use `create_custom_resource` + `wait_for_deployment` / `wait_for_modelapi_ready` from `operator/tests/e2e/conftest.py`. Asserting the agent reaches Ready is itself the regression guard for the gateways-RBAC bug — add an explicit operator-log check for `gateways.gateway.networking.k8s.io is forbidden` and fail if present.

## Step 5 — Assert generation (generation tier, CI-runnable on kindnet)

```bash
# 5a. Three ingress-only NetworkPolicies generated (agent, mcp, modelapi).
kubectl get networkpolicy -n e2e-sec
# 5b. Agent env is gateway-routed, NOT direct cluster-local.
kubectl get deploy -n e2e-sec e2e-agent -o jsonpath='{.spec.template.spec.containers[0].env}' | tr ',' '\n' | grep -E 'MCP_SERVER_.*_URL|MODEL_API_URL'
# Expect values like http://<gateway-ip>/e2e-sec/mcp/e2e-echo-mcp and
# http://<gateway-ip>/e2e-sec/modelapi/e2e-modelapi (NOT *.svc.cluster.local).
```

Programmatic assertions: (a) exactly three NetworkPolicy objects with ingress rules allowing only the gateway and operator namespaces; (b) the agent Deployment's `MCP_SERVER_*_URL` and `MODEL_API_URL` env values match the gateway-routed form, not the direct service DNS. Both run on kindnet.

## Step 6 — Assert enforcement (enforcement tier, requires Calico/Cilium)

```bash
GW=$(kubectl get gateway -A -o jsonpath='{.items[0].status.addresses[0].value}')

# TEST A — direct ClusterIP bypass must be BLOCKED.
# From a scratch pod in a DIFFERENT namespace, curl the MCP Service ClusterIP directly.
# Expect: connection times out (NetworkPolicy denies the bypass).
kubectl run sec-test-a --rm -i --restart=Never --image=curlimages/curl:8.10.1 -n default -- \
  -s -o /dev/null -w 'http=%{http_code}\n' --max-time 10 \
  "http://<mcp-clusterip>:<port>/"   # -> times out / non-200 (BLOCKED)

# TEST B — the gateway path is reachable and ENFORCES authz.
kubectl run sec-test-b --rm -i --restart=Never --image=curlimages/curl:8.10.1 -n default -- \
  -s -o /dev/null -w 'http=%{http_code}\n' --max-time 10 \
  "http://$GW/e2e-sec/mcp/e2e-echo-mcp"   # -> 401 with www-authenticate: Bearer
```

- TEST A proves the direct bypass is closed (Calico enforces the NetworkPolicy).
- TEST B proves traffic reaches the gateway and the gateway's JWT SecurityPolicy fail-closes unauthenticated requests (HTTP 401, `www-authenticate: Bearer realm=...`). Note the SecurityPolicy may report `Accepted=Invalid` if its ext_authz backend (`aib-access-check-grpc`) is absent in a broker-less install; Envoy Gateway still fail-closes the JWT portion, so 401 is the correct expected result.

Programmatic assertions: TEST A expects a connection failure/timeout (assert non-success, ideally a transport error); TEST B expects HTTP 401 and a `www-authenticate` Bearer challenge header. The enforcement tier must be marked to skip on a non-enforcing CNI.

## Step 7 — (Optional) positive-decision path

A valid-token -> 200 result is **not** reachable from this lightweight install. It requires the full chain: the broker's access-check ext_authz service (`aib-access-check-grpc`, not deployed by the broker dev preset), a sync-provisioned agent credential Secret, a granted authorization edge, and a correctly minted actor token. The broker dev preset (in-memory, local OAuth2, `X-Remote-User` preauth) comes up healthy and serves JWKS at `/oauth2/jwks.json` — the exact URI the gateway's `jwt.remoteJWKS` uses, so the JWT validation chain is correctly wired — but it omits the access-check service, so the generated SecurityPolicy is `Accepted=Invalid` (`ExtAuth: service not found`). The positive matrix (Keycloak user-JWT, ext_proc token swap, identity-override actor token + SDK lifecycle, sync watch/leader/rotation) is a dedicated full-stack follow-up; each piece is validated component-wise in its own phase. Track the dev-preset access-check omission as a chart/CLI gap: either ship the access-check service in the dev chart or gate ext_authz wiring on its availability.

## Cleanup

```bash
kubectl delete namespace e2e-sec --ignore-not-found
kind delete cluster --name kaos-sec-e2e
```

## Suggested programmatic test layout

- `operator/tests/e2e/test_security_generation_e2e.py` (generation tier, kindnet/CI): install with `--network-policy --gateway-routing`; assert the three NetworkPolicy objects, the gateway-routed agent env, the operator configmap keys, and the absence of `gateways ... forbidden` in operator logs (gateways-RBAC regression guard).
- `operator/tests/e2e/test_security_enforcement_e2e.py` (enforcement tier, Calico-gated, skipped when the CNI does not enforce NetworkPolicy): TEST A direct-bypass-blocked and TEST B gateway-path-401, reusing `gateway_url` from `conftest.py`.
- Both tiers reuse `create_custom_resource`, `wait_for_deployment`, and `wait_for_modelapi_ready`. Gate the enforcement tier behind an env flag (e.g. `KAOS_SEC_E2E_ENFORCEMENT=1`) so the default CI run stays on kindnet.

## Step 8 — Operational-correctness outcome story (enforcement tier)

These checks extend the deny baseline above into the structured-outcome layer. They require the broker deployed with the access-check ext_authz service (`aib-access-check-grpc:9191`) and, for the re-auth check, the ext_proc token-exchange wiring. All outcomes are detected by the runtime from response headers (`x-kaos-access-reason`, `x-kaos-reauth-url`) — a non-secured gateway never sets these, so the security-off path is unchanged.

```bash
# 8a. Denied platform grant -> structured reason in the synchronous response.
# Call an agent whose actor has no approved platform grant for the target MCP/ModelAPI.
# The gateway ext_authz denies with x-kaos-access-reason: platform_grant_missing (no URL);
# the chat/A2A reply states the denied resource + reason, and the run does NOT hang.
# Verify the SDK surfaced it (not a generic 500): the assistant message names the resource
# and reason; the memory carries an access_outcome event.

# 8b. User-grant-required -> reason without a renewal URL.
# For a resource needing a user-delegated grant that is missing/expired, the denied reason
# is user_grant_required (still no dedicated URL on the ext_authz path).

# 8c. Third-party re-auth -> reauth_url on the ext_proc path.
# A token-exchange that needs user re-consent returns the ext_proc immediate response:
# HTTP 200, headers x-kaos-access-reason: third_party_reauth_required + x-kaos-reauth-url,
# JSON-RPC error data.reason/data.reauth_url. The sync reply says "reconnect <service> at <url>".

# 8d. Autonomous run -> one user_action_required event + stop.
# Trigger the same denial inside an autonomous agent. Assert the Task has exactly one
# user_action_required event and task.metadata["user_action_required"] is set, and the run
# ends (COMPLETED) without re-hitting the denial every iteration.

# 8e. Requested-only -> denied until the grant is approved.
# A CRD reference projects the requestable catalog + the bootstrap binding. Until the binding
# exists in the broker the access-check denies; once the permission set is bound the actor is
# allowed. (The first-class approval gate is a later phase; here the binding == bootstrap grant.)

# 8f. OPA drop-in equivalence (config-only swap).
kubectl apply -f docs/security/opa-drop-in/opa-envoy.yaml
kubectl -n opa-system rollout status deploy/opa-envoy
kaos system install --auth-enabled \
  --ext-authz-url opa-envoy.opa-system.svc.cluster.local:9191 --wait
# A granted edge allows and an ungranted one denies equivalently to AIB — no Envoy/KAOS change.

# 8g. Egress + TLS hardening.
# Install with egress NetworkPolicy enabled and a TLS mode; assert a secured workload can reach
# DNS/gateway/operator/AIB (and provider egress for ModelAPI) but not arbitrary off-list egress,
# and that the gateway path is TLS-terminated at the pinned minimum version (1.2).
```

These map one-to-one to the P12 outcome behaviours and are the basis for the automated outcome-tier e2e (mock third-party API that echoes the inbound Authorization to prove the ext_proc swap, plus an agent with and without an approved grant). AIB remains the default authorization backend; the OPA check is a demonstration of backend-neutrality.
