# ADR-KAOS-007: Transport security and hardening baseline

**Status**: Accepted
**Date**: 2026-06-20

---

## Decision

Adopt **external TLS at the ingress/gateway boundary** as the baseline transport requirement, and make Gateway-listener TLS **first-class and configurable** in the KAOS install so a secured deployment has a working certificate path out of the box.

Because KAOS security enforcement is gateway-centric, security enabled means:

1. The Envoy-compatible Gateway is enabled and is the required enforcement path.
2. External user/client traffic uses TLS at the ingress, Gateway, load balancer, or trusted reverse proxy boundary.
3. NetworkPolicy restricts direct ClusterIP workload-to-workload traffic for KAOS workloads so resource-to-resource calls cannot bypass the gateway. Ingress restriction is the baseline; an optional egress NetworkPolicy (default-off, gated by `SECURITY_NETWORK_POLICY_EGRESS_ENABLED`) additionally constrains outbound traffic to the allowed set — DNS, the gateway, the operator, and AIB — with ModelAPI workloads additionally permitted provider egress.
4. The Gateway HTTPS listener negotiates a minimum TLS version of 1.2, enforced through a Gateway `ClientTrafficPolicy`.
5. Resource-to-resource authorization happens at the gateway through Envoy `jwt_authn`, `ext_authz`, and `ext_proc`, not in Python/SDK code.

Without the gateway, KAOS provides propagation only for local/dev use and no resource-to-resource enforcement.

### Gateway TLS configuration

KAOS exposes a `security.tls` block that configures the HTTPS Gateway listener using common Kubernetes practice. There are three modes, all producing a standard `kubernetes.io/tls` Secret that the Gateway listener references:

```yaml
security:
  tls:
    mode: selfSigned            # selfSigned | certManager | provided
    certManager:                # mode=certManager: reuse an existing cluster issuer (no new issuer is created)
      issuerRef:
        name: letsencrypt-prod
        kind: ClusterIssuer      # ClusterIssuer | Issuer
    secretName: ""              # mode=provided: name of an existing tls.crt/tls.key Secret
```

- **`selfSigned` (default, simplest).** The CLI/operator generates a self-signed certificate Secret and points the Gateway HTTPS listener at it. This gives a working TLS endpoint for dev, KIND, and quick installs with no external dependency. Clients trust it explicitly or skip verification in dev.
- **`certManager` (recommended for production when present).** If cert-manager is already installed, KAOS creates a `Certificate` referencing an **existing** `Issuer`/`ClusterIssuer` (`issuerRef`); cert-manager provisions and rotates the Secret. KAOS does not install or own cert-manager and does not create issuers.
- **`provided`.** The operator references an existing TLS Secret (from a cloud LB controller, corporate PKI, or a manually-created Secret). KAOS wires it to the listener and does no certificate management.

The Gateway listener is rendered as HTTPS/443 with the resolved Secret when `security.tls` is set; plain HTTP remains the default only for non-secured/dev installs. The HTTPS listener negotiates a minimum TLS version of 1.2 through a Gateway `ClientTrafficPolicy`. cert-manager remains optional — it is one mode, not a hard dependency.

mTLS, SPIFFE, service mesh, native intra-service (in-cluster pod-to-pod) TLS, and cryptographic workload binding are **out of scope** (not deferred): the gateway-terminated external TLS plus NetworkPolicy is the accepted transport posture, revisited only if a concrete requirement appears.

---

## Context

[ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md) accepts the Envoy-compatible Gateway as the enforcement plane: `jwt_authn` validates inbound tokens, `ext_authz` asks AIB for allow/deny resource decisions, and `ext_proc` performs RFC 8693 token exchange.

[ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md) accepts AIB as the authorization and delegated-token broker, while placing Kubernetes ServiceAccount/SPIFFE workload binding out of scope.

[ADR-KAOS-005](./ADR-KAOS-005-authorization-and-policy-model.md) accepts simple AIB grant tables for resource authorization and treats OPA/Rego, Keycloak Authorization Services, and MCP tool/argument policy as optional policy extensions.

[ADR-KAOS-006](./ADR-KAOS-006-re-authentication-execution-model.md) accepts fail-closed resource grants, user-grant-required outcomes, and fail-with-URL-and-retry for third-party re-authentication surfaced through the gateway path.

This ADR decides the transport security and network boundary requirements for the gateway-centric security model.

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
- Gateway listener TLS is modeled in chart values through the `security.tls` block decided by this ADR (`selfSigned`/`certManager`/`provided`), rendering an HTTPS/443 listener backed by a `kubernetes.io/tls` Secret; plain HTTP/80 remains the default for non-secured/dev installs.
- Generated Gateway endpoints use `http://{gatewayHost}/...`.
- HTTPRoutes are created for Agents, MCPServers, and ModelAPIs when Gateway API is enabled.
- HTTPRoute rules include URL rewrite and request timeout support.

Implication:

- KAOS currently has a useful Gateway routing layer but no TLS/certificate values; this ADR adds a first-class `security.tls` block (selfSigned/certManager/provided) so the Gateway listener has a working certificate path.
- The chart needs an HTTPS listener and a `kubernetes.io/tls` Secret reference driven by `security.tls`; `selfSigned` generates the Secret, `certManager` provisions it via an existing issuer, `provided` reuses one.
- Security-enabled deployments need gateway enforcement plus NetworkPolicy bypass prevention regardless of which TLS mode supplies the certificate.

## Decision scope

This ADR fixes the following scope:

1. Whether TLS is required at the ingress/gateway boundary.
2. Whether cert-manager should be mandatory or recommended.
3. Whether in-cluster mTLS, SPIFFE, or service mesh are required by default.
4. Whether native Agent/MCPServer/ModelAPI TLS is required by default.
5. Whether NetworkPolicy is part of the mandatory secured target.
6. Which network security layers are out of scope (revisit only on concrete need).

---

## Annex: Alternatives considered

### Option A: External TLS without additional in-cluster hardening

This option requires TLS at the external production boundary but does not introduce service mesh, SPIFFE, native intra-service TLS, in-cluster mTLS, or mandatory cert-manager.

The minimal transport posture is:

```text
External user/client traffic:
  terminate TLS at ingress/Gateway/load balancer/reverse proxy

KAOS runtime-to-runtime traffic:
  carry verified identity/context for gateway enforcement
  require NetworkPolicy in security-enabled deployments to prevent direct ClusterIP bypass
```

This option remains useful because it avoids forcing a specific ingress controller, cert-manager setup, service mesh, or in-cluster certificate model. However, external TLS by itself is not enough for the secured target unless paired with gateway enforcement and NetworkPolicy bypass prevention.

Pros:

- Keeps the default transport requirement small and understandable.
- Matches current KAOS Gateway and runtime capabilities.
- Avoids forcing a specific ingress controller, cert-manager setup, service mesh, or in-cluster certificate model.

Cons:

- Does not cryptographically protect every in-cluster hop.
- Requires deployment guidance for production TLS rather than fully enforcing certificate provisioning in KAOS code.
- Must be paired with gateway enforcement and NetworkPolicy to prevent ClusterIP bypass.

Best fit:

- External transport requirement for the secured target.
- Development and production deployments that want secure transport without platform lock-in.

### Option B: Gateway TLS and cert-manager as mandatory transport automation

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

This is a strong production posture and a good Kubernetes-native deployment shape. However, KAOS's current chart creates HTTP listeners by default and does not expose full TLS/certificate configuration. Making cert-manager mandatory would force a certificate automation choice even in environments with cloud load balancer certificates, corporate ingress, or external reverse proxies.

Pros:

- Strong external transport security.
- Clear production posture.
- cert-manager is a common Kubernetes-native certificate automation tool.

Cons:

- Requires chart/controller work before it can be fully managed by KAOS.
- Forces cert-manager even in environments with cloud load balancer certificates, corporate ingress, or external reverse proxies.
- Still does not solve in-cluster mTLS or ClusterIP bypass by itself.

Best fit:

- Future optional chart/controller enhancement for Kubernetes-native certificate automation.

### Option C: Full in-cluster mTLS and workload identity as the default

This option requires service-to-service mTLS, workload identity, and cryptographic binding for Agents, MCPServers, ModelAPIs, and AIB.

Possible mechanisms:

```text
SPIFFE/SPIRE identities
service mesh identities
Kubernetes projected ServiceAccount tokens
Gateway/client certificate validation
```

This is the strongest network and workload-identity posture. It would help prove that `kaos://agent/researcher` is actually running as the expected workload and not just claiming that identity.

However, requiring this by default would expand the scope substantially and force KAOS to choose a mesh/workload identity strategy before the basic AIB integration is proven.

Pros:

- Strong service-to-service identity.
- Reduces risk of in-cluster spoofing.
- Helps prevent direct bypass of gateway assumptions.
- Aligns with high-security production environments.

Cons:

- High operational complexity.
- Requires choosing or integrating SPIFFE, service mesh, or Kubernetes ServiceAccount token validation.
- Changes runtime/operator deployment shape.
- More than required for the AIB authorization/token integration.

Best fit:

- Future optional hardening for regulated or multi-tenant environments.

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

This is different from full mTLS or service mesh. Native intra-service TLS encrypts the connection to the server, but it does not necessarily prove client workload identity unless mutual TLS is also configured. It is a useful middle layer between gateway-only TLS and full mesh/SPIFFE identity.

To support this properly, KAOS would need runtime and operator changes:

- Agent runtime must support HTTPS URLs and CA/trust configuration for MCPServer, ModelAPI, and A2A calls.
- MCP runtimes must support serving HTTPS.
- Agent runtime must support serving HTTPS for inbound A2A/chat if exposed internally.
- ModelAPI integrations must support HTTPS or be wrapped behind a TLS-capable proxy.
- CRDs or chart values must model TLS Secret references, CA bundles, scheme selection, and certificate rotation behavior.
- Probes, generated endpoints, and Gateway routes must use the correct scheme/ports.

Pros:

- Encrypts in-cluster traffic without requiring a full service mesh.
- Lets security-sensitive deployments harden service-to-service communication incrementally.
- Keeps the mechanism configurable per runtime/resource.
- Can be combined with client certificate auth or workload identity.

Cons:

- Requires runtime support across Agent, MCPServer, and ModelAPI surfaces.
- Certificate provisioning and rotation become KAOS deployment concerns.
- Does not by itself prevent ClusterIP bypass or prove caller identity.
- More work than required for the AIB authorization/token integration.

Best fit:

- Future optional hardening layer for environments that want in-cluster encryption but do not want a service mesh.

### Option E: Gateway + NetworkPolicy boundary hardening

This option adds Kubernetes NetworkPolicies so Agents, MCPServers, and ModelAPIs use the gateway path for protected resource-to-resource calls and direct ClusterIP bypass is restricted.

Example:

```text
NetworkPolicy (ingress, baseline):
  allow KAOS workload -> Gateway/AIB
  deny Agent -> MCPServer direct ClusterIP
  deny Agent -> ModelAPI direct ClusterIP

NetworkPolicy (egress, optional, default-off via SECURITY_NETWORK_POLICY_EGRESS_ENABLED):
  allow KAOS workload -> DNS, Gateway, operator, AIB
  allow ModelAPI workload -> provider egress
  deny other outbound
```

This is less complex than service mesh and is required for gateway-centric enforcement. The gateway can only be the enforcement plane if workloads cannot bypass it with direct ClusterIP calls.

The limitation is that enforcement depends on the CNI. It also requires careful namespace, label, and traffic modeling to avoid breaking valid internal flows.

Pros:

- Prevents bypass of gateway authorization.
- Kubernetes-native.
- Lower complexity than service mesh.
- Required for the secured target when security is enabled.

Cons:

- Depends on CNI enforcement.
- Requires policy generation and operational testing.
- Can break workloads if labels/routes are wrong.
- Still does not provide cryptographic workload identity.

Best fit:

- Required part of the security-enabled target model.

### Option F: Service mesh as the default platform requirement

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

- Future optional hardening for organizations that already operate a mesh.

---

## Decision summary

1. External TLS at the ingress, Gateway, load balancer, or trusted reverse proxy boundary is the baseline transport requirement.
2. When KAOS security is enabled, the Envoy-compatible Gateway is required and is the enforcement path.
3. NetworkPolicy restricting direct ClusterIP workload-to-workload access is required when security is enabled because it prevents bypassing the gateway. Ingress restriction is the baseline; an optional egress NetworkPolicy (default-off, gated by `SECURITY_NETWORK_POLICY_EGRESS_ENABLED`) constrains outbound traffic to DNS, the gateway, the operator, and AIB, with ModelAPI workloads additionally allowed provider egress.
4. Resource-to-resource authorization happens at the gateway through `jwt_authn`, `ext_authz`, and `ext_proc`, not in Python/SDK code.
5. Gateway-listener TLS is first-class and configurable via `security.tls` with three modes: `selfSigned` (default; generated cert for dev/simple installs), `certManager` (provision via an existing cluster issuer; KAOS does not install cert-manager), and `provided` (reuse an existing TLS Secret). The HTTPS listener enforces a minimum TLS version of 1.2 via a Gateway `ClientTrafficPolicy`.
6. cert-manager is one supported mode, not mandatory; deployments may use self-signed, cloud load balancer certificates, corporate ingress, or trusted reverse proxies.
7. Native Agent/MCPServer/ModelAPI (in-cluster pod-to-pod) TLS is out of scope, revisited only on concrete need.
8. mTLS, SPIFFE, service mesh, sidecars, and cryptographic workload binding are out of scope (not deferred), revisited only on concrete need.
