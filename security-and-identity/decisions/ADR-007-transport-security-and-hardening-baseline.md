# ADR-007: Transport security and hardening baseline

**Status**: Accepted.
**Date**: 2026-06-20

---

## Context

[ADR-002](./ADR-002-enforcement-topology.md) accepts SDK-first enforcement for KAOS 1.0 and defers GatewayAPI resource-boundary enforcement to a 1.1 extension.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) accepts AIB as the authorization and delegated-token broker, while deferring Kubernetes ServiceAccount/SPIFFE workload binding.

[ADR-005](./ADR-005-authorization-and-policy-model.md) accepts simple AIB grant tables for 1.0 and defers OPA/Rego, Keycloak Authorization Services, and MCP tool/argument policy.

[ADR-006](./ADR-006-approval-and-consent-execution-model.md) accepts fail-closed resource grants and fail-with-URL-and-retry for user consent and third-party re-authentication.

This ADR decides the baseline hardening model for TLS, network boundaries, and optional network-level hardening layers.


---

## Source facts

### KAOS Gateway API support is HTTP-first and optional today

Source files:

- `operator/chart/templates/gateway.yaml`
- `operator/chart/values.yaml`
- `operator/pkg/gateway/gateway.go`
- `operator/chart/templates/operator-configmap.yaml`

Relevant facts:

- Gateway API is disabled by default in chart values.
- The chart can create a `Gateway` when `gatewayAPI.enabled` and `gatewayAPI.createGateway` are true.
- The default listener is:
  - `port: 80`
  - `protocol: HTTP`
- Gateway listener TLS configuration is not currently modeled in chart values.
- Generated Gateway endpoints use `http://{gatewayHost}/...`.
- HTTPRoutes are created for Agents, MCPServers, and ModelAPIs when Gateway API is enabled.
- HTTPRoute rules include URL rewrite and request timeout support.

Implication:

- KAOS currently has a useful Gateway routing layer, but not a complete TLS/certificate management story.
- Requiring Gateway TLS as the only acceptable 1.0 mode would require chart/controller changes.
- Production hardening should still target external TLS termination, but the initial architecture should not depend on service mesh or in-cluster mTLS.

## Decision scope

This ADR fixes the following scope:

1. Whether TLS is required at the Gateway boundary in 1.0.
2. Whether cert-manager should be mandatory or recommended.
3. Whether in-cluster mTLS, SPIFFE, or service mesh are required initially.
4. Whether native Agent/MCPServer/ModelAPI TLS is required initially.
5. Whether NetworkPolicy is part of the mandatory baseline.
6. Which advanced network security layers are explicitly deferred.

---

## Annex: Alternatives considered

### Option A: Minimal 1.0 transport hardening with external TLS

This option keeps the initial KAOS/AIB integration simple. KAOS requires TLS at the external production boundary but does not introduce service mesh, SPIFFE, native intra-service TLS, in-cluster mTLS, NetworkPolicy, or mandatory cert-manager in 1.0.

The baseline is:

```text
External user/client traffic:
  terminate TLS at ingress/Gateway/load balancer/reverse proxy

KAOS runtime-to-runtime traffic:
  use SDK-level auth/context/grant checks
  keep direct in-cluster HTTP acceptable for 1.0
```

This option accepts that KAOS will not solve every network-level threat in the first iteration. It relies on ADR-002 through ADR-006 for SDK-level context propagation, authorization, and consent behavior. Network-level bypass hardening remains a future GatewayAPI/NetworkPolicy/service-mesh extension.

Pros:

- Keeps the first implementation small and understandable.
- Matches current KAOS Gateway and runtime capabilities.
- Avoids forcing a specific ingress controller, cert-manager setup, service mesh, or in-cluster certificate model.

Cons:

- Does not cryptographically protect every in-cluster hop.
- Does not prevent ClusterIP bypass by itself.
- Requires deployment guidance for production TLS rather than fully enforcing it in code.
- Leaves workload identity and service-to-service mTLS for later.

Best fit:

- KAOS 1.0.
- Development and early production deployments that want secure defaults without platform lock-in.

### Option B: Gateway TLS and cert-manager as mandatory 1.0 baseline

This option requires all external KAOS traffic to enter through a TLS-enabled Gateway and requires cert-manager as the default certificate automation mechanism.

Example target:

```text
Gateway:
  HTTPS listener on 443
  TLS certificate from cert-manager
  HTTPRoute for Agent/MCPServer/ModelAPI

Clients:
  only use https:// gateway URLs
```

This is a stronger production posture than Option A and is a good recommended deployment shape. However, KAOS's current chart creates HTTP listeners by default and does not expose full TLS/certificate configuration. Making this mandatory now would couple security architecture acceptance to Gateway chart work.

Pros:

- Stronger external transport security.
- Clear production posture.
- cert-manager is a common Kubernetes-native certificate automation tool.

Cons:

- Requires chart/controller work before the architecture can be implemented.
- Forces cert-manager even in environments with cloud load balancer certificates, corporate ingress, or external reverse proxies.
- Still does not solve in-cluster mTLS or ClusterIP bypass.

Best fit:

- Recommended production profile.
- Future chart enhancement, not mandatory for initial AIB integration.

### Option C: Full in-cluster mTLS and workload identity from the start

This option requires service-to-service mTLS, workload identity, and cryptographic binding for Agents, MCPServers, ModelAPIs, and AIB.

Possible mechanisms:

```text
SPIFFE/SPIRE identities
service mesh identities
Kubernetes projected ServiceAccount tokens
Gateway/client certificate validation
```

This is the strongest network and workload-identity posture. It would help prove that `kaos://agent/researcher` is actually running as the expected workload and not just claiming that identity in an SDK call.

However, ADR-001 and ADR-004 intentionally defer workload binding and ServiceAccount/SPIFFE identity. Requiring this now would expand the scope substantially and force KAOS to choose a mesh/workload identity strategy before the basic AIB integration is proven.

Pros:

- Strong service-to-service identity.
- Reduces risk of in-cluster spoofing.
- Helps prevent direct bypass of Gateway/SDK assumptions.
- Aligns with high-security production environments.

Cons:

- High operational complexity.
- Requires choosing or integrating SPIFFE, service mesh, or K8s SA token validation.
- Changes runtime/operator deployment model.
- Overkill for the first AIB integration.

Best fit:

- Future advanced security profile.
- Regulated or multi-tenant environments after the 1.0 model is validated.

### Option D: Configurable native intra-service TLS

This option adds first-class TLS support directly to KAOS-managed Agent, MCPServer, and ModelAPI services. Instead of only terminating TLS at the Gateway, each runtime can be configured to serve HTTPS using mounted certificates from Kubernetes Secrets or a certificate automation system.

Example:

```text
Agent -> https://mcpserver-github.namespace.svc.cluster.local
Agent -> https://modelapi-gpt.namespace.svc.cluster.local

MCPServer pod:
  mounts tls.crt/tls.key from a Secret
  serves HTTPS
```

This is different from full mTLS or service mesh. Native intra-service TLS encrypts the connection to the server, but it does not necessarily prove client workload identity unless mutual TLS is also configured. It is a useful middle layer between Gateway-only TLS and full mesh/SPIFFE identity.

To support this properly, KAOS would need runtime and operator changes:

- Agent runtime must support HTTPS URLs and CA/trust configuration for MCPServer, ModelAPI, and A2A calls.
- MCP runtimes must support serving HTTPS.
- Agent runtime must support serving HTTPS for inbound A2A/chat if exposed internally.
- ModelAPI integrations must support HTTPS or be wrapped behind a TLS-capable proxy.
- CRDs or chart values must model TLS Secret references, CA bundles, scheme selection, and possibly certificate rotation behavior.
- Probes, generated endpoints, and Gateway routes must use the correct scheme/ports.

Pros:

- Encrypts in-cluster traffic without requiring a full service mesh.
- Lets security-sensitive deployments harden service-to-service communication incrementally.
- Keeps the mechanism configurable per runtime/resource.
- Can be combined later with client certificate auth or workload identity.

Cons:

- Requires runtime support across Agent, MCPServer, and ModelAPI surfaces.
- Certificate provisioning and rotation become KAOS deployment concerns.
- Does not by itself prevent ClusterIP bypass or prove caller identity.
- More work than required for the first AIB authorization/token integration.

Best fit:

- Future configurable production hardening layer.
- Environments that want in-cluster encryption but do not want a service mesh.

### Option E: Gateway + NetworkPolicy boundary hardening

This option adds Kubernetes NetworkPolicies so Agents can only reach MCPServers, ModelAPIs, and AIB through approved paths, or so direct ClusterIP bypass is restricted.

Example:

```text
NetworkPolicy:
  allow Agent -> Gateway/AIB
  deny Agent -> MCPServer direct ClusterIP
  deny Agent -> ModelAPI direct ClusterIP
```

This is less complex than service mesh and can significantly improve enforcement if the cluster CNI supports NetworkPolicy correctly.

The limitation is that KAOS does not currently create these policies, and enforcement depends on the CNI. It also requires careful namespace, label, and traffic modeling to avoid breaking valid internal flows.

Pros:

- Stronger boundary than SDK-only checks.
- Kubernetes-native.
- Lower complexity than service mesh.
- Good fit for the GatewayAPI 1.1 resource-boundary extension.

Cons:

- Depends on CNI enforcement.
- Requires policy generation and operational testing.
- Can break workloads if labels/routes are wrong.
- Still does not provide cryptographic workload identity.

Best fit:

- Part of the 1.1 Gateway/resource-boundary hardening work.
- Production profile when Gateway enforcement is adopted.

### Option F: Service mesh as default platform baseline

This option requires a service mesh such as Istio or Linkerd for mTLS, traffic policy, identity, and observability.

This gives KAOS a mature transport-security substrate, but it makes KAOS security dependent on a heavy platform dependency and a specific operational model.

Pros:

- Strong mTLS and traffic policy.
- Mature observability and policy ecosystem.
- Good fit for organizations already standardized on a mesh.

Cons:

- Too much default complexity for KAOS.
- Forces platform choice.
- Can interact poorly with Gateway/API routing and local development.
- Does not replace AIB's consent, token exchange, or grant model.

Best fit:

- Optional advanced deployment profile, not default.

---

## Decision

Adopt **Option A: Minimal 1.0 transport hardening with external TLS**.

Use three profiles:

| Profile | Scope | Requirements |
|---|---|---|
| Minimal/dev | Local demos and development | HTTP allowed locally |
| Recommended production | First production target | TLS at external ingress/Gateway/reverse proxy |
| Advanced future | High-security environments | Gateway resource-boundary enforcement, NetworkPolicy, cert-manager chart support, native intra-service TLS, in-cluster mTLS/SPIFFE/service mesh, workload identity binding |

The 1.0 target should require:

1. External user/client traffic uses TLS in production.
2. Gateway TLS/cert-manager, native intra-service TLS, NetworkPolicy, service mesh, SPIFFE, and workload identity binding are deferred network hardening layers.

---

## Decision summary

1. KAOS 1.0 uses a minimal hardening baseline, not service mesh or mandatory in-cluster mTLS.
2. Production external user/client traffic must use TLS at ingress, Gateway, load balancer, or trusted reverse proxy.
3. cert-manager is recommended for Kubernetes-native certificate automation but not mandatory.
4. Gateway TLS support is a recommended chart/controller enhancement, not a prerequisite for the initial AIB integration.
5. Gateway + NetworkPolicy boundary hardening is bundled into the 1.1 Gateway/resource-boundary work.
6. Native Agent/MCPServer/ModelAPI TLS is a future configurable hardening layer, not mandatory for 1.0.
7. SPIFFE, service mesh, and cryptographic workload binding are deferred advanced-profile features.

