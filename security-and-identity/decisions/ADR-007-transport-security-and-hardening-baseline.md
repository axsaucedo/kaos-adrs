# ADR-007: Transport security and hardening baseline

**Status**: Proposed. Requires host decisions before acceptance.
**Date**: 2026-06-20

---

## Context

[ADR-003](./ADR-003-enforcement-topology.md) accepts SDK-first enforcement for KAOS 1.0 and defers GatewayAPI resource-boundary enforcement to a 1.1 extension.

[ADR-004](./ADR-004-aib-responsibility-boundary.md) accepts AIB as the authorization and delegated-token broker, while deferring Kubernetes ServiceAccount/SPIFFE workload binding.

[ADR-005](./ADR-005-authorization-and-policy-model.md) accepts simple AIB grant tables for 1.0 and defers OPA/Rego, Keycloak Authorization Services, and MCP tool/argument policy.

[ADR-006](./ADR-006-approval-and-consent-execution-model.md) accepts fail-closed resource grants and fail-with-URL-and-retry for user consent and third-party re-authentication.

This ADR decides the baseline hardening model around transport security, secrets, token vault protection, telemetry, and optional advanced layers.

The core question is:

```text
What hard security baseline should KAOS target without over-engineering the first AIB integration?
```

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

### KAOS operator chart has a basic secure container baseline

Source files:

- `operator/chart/values.yaml`
- `operator/chart/templates/deployment.yaml`

Relevant facts:

- Operator pod security context sets:
  - `runAsNonRoot: true`,
  - `runAsUser: 65532`.
- Operator container security context sets:
  - `allowPrivilegeEscalation: false`,
  - drop all capabilities,
  - `readOnlyRootFilesystem: true`.
- The operator ServiceAccount is configurable.

Implication:

- The control plane already has a reasonable container hardening baseline.
- The same standard should be treated as the target for new AIB-related KAOS components where practical.

### KAOS data plane exposes escape hatches through container and pod overrides

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

Relevant facts:

- Agent, MCPServer, and ModelAPI all expose `spec.container` and `spec.podSpec`.
- `spec.container.env` can inject arbitrary environment variables.
- `spec.podSpec` can override generated pod spec details.
- MCPServer supports `spec.serviceAccountName`.
- ModelAPI supports API keys from either direct value or `SecretKeyRef`.
- ModelAPI custom LiteLLM config can come from literal string or `SecretKeyRef`.
- Current ModelAPI controller generates a ConfigMap for LiteLLM config and supports direct API key env var values, though secret references are also supported.

Implication:

- KAOS needs secure defaults, but users can intentionally override runtime/container settings.
- The target security posture should recommend Kubernetes Secrets for credentials and avoid literal secrets in CRDs.
- A future hardening pass should reduce accidental secret exposure in generated ConfigMaps and plain env values.

### AIB has explicit encryption and signing-key surfaces

Source files:

- `agentic-identity-broker/internal/ports/config.go`
- `agentic-identity-broker/internal/ports/encryption.go`
- `agentic-identity-broker/internal/ports/oauth2server.go`
- `agentic-identity-broker/internal/ports/thirdparty_provider.go`

Relevant facts:

- AIB has an `EncryptionPort` for encrypt/decrypt with additional authenticated data.
- Production encryption is intended to use envelope encryption with context binding.
- Third-party OAuth provider secrets are stored encrypted; repositories treat secrets as opaque ciphertext.
- Encryption supports:
  - AWS KMS hierarchical keyring backend,
  - memory/raw AES key backend.
- AIB local OAuth server mode has signing-key lifecycle ports and signing-key bootstrap coordination.
- Third-party OAuth state uses a JWE signing key.
- AIB has security config flags to skip third-party HTTPS validation and CIMD SSRF validation, both explicitly marked development/test only.
- AIB's authentication config supports reverse-proxy pre-auth and optional JWT validation.
- CORS defaults are secure by default when allowed origins are empty.

Implication:

- Production AIB deployments should use a real durable encrypted storage backend and managed key material.
- Development-only skip flags and memory encryption backends should not be part of the production baseline.
- KAOS should not duplicate AIB token-vault encryption; it should require AIB to be deployed with production-grade encryption and storage.

### KAOS telemetry exists but is optional

Source files:

- `operator/chart/values.yaml`
- `operator/pkg/util/telemetry.go`
- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

Relevant facts:

- Global telemetry is disabled by default.
- Agent, MCPServer, and ModelAPI have telemetry configuration surfaces.
- ModelAPI Hosted/Ollama mode warns that native OTel is not supported.

Implication:

- Audit/security event requirements should be explicit; generic telemetry alone is not enough.
- Raw tokens and secrets must not be emitted in logs, traces, memory, or events.

---

## Decision problem

KAOS needs to decide:

1. Whether TLS is required at the Gateway boundary in 1.0.
2. Whether cert-manager should be mandatory or recommended.
3. Whether in-cluster mTLS, SPIFFE, or service mesh are required initially.
4. How secrets, signing keys, and token-vault encryption should be handled.
5. Whether NetworkPolicy is part of the mandatory baseline.
6. What hardening is required for logs, telemetry, and audit events.
7. Which advanced security layers are explicitly deferred.

---

## Options

### Option A: Minimal 1.0 hardening with external TLS and AIB-managed secret protection

This option keeps the initial KAOS/AIB integration simple. KAOS requires secure handling at the main trust boundaries but does not introduce service mesh, SPIFFE, in-cluster mTLS, or mandatory cert-manager in 1.0.

The baseline is:

```text
External user/client traffic:
  terminate TLS at ingress/Gateway/load balancer/reverse proxy

KAOS runtime-to-runtime traffic:
  use SDK-level auth/context/grant checks
  keep direct in-cluster HTTP acceptable for 1.0

AIB token vault:
  production storage + encryption backend
  no plaintext token persistence outside AIB

Secrets:
  Kubernetes Secrets or external secret manager
  no literal production credentials in CRDs

Logs/telemetry:
  no raw tokens/secrets
  security decisions recorded as metadata only
```

This option accepts that KAOS will not solve every network-level threat in the first iteration. It relies on ADR-002 through ADR-006 for SDK-level context propagation, authorization, and consent behavior. Network-level bypass hardening remains a future GatewayAPI/NetworkPolicy/service-mesh extension.

Pros:

- Keeps the first implementation small and understandable.
- Matches current KAOS Gateway and runtime capabilities.
- Avoids forcing a specific ingress controller, cert-manager setup, service mesh, or cloud KMS provider.
- Lets AIB own token-vault encryption instead of duplicating secret storage in KAOS.

Cons:

- Does not cryptographically protect every in-cluster hop.
- Does not prevent ClusterIP bypass by itself.
- Requires deployment guidance for production TLS/secrets rather than fully enforcing it in code.
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

### Option D: Gateway + NetworkPolicy boundary hardening

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

- 1.1 Gateway/resource-boundary hardening.
- Production profile when Gateway enforcement is adopted.

### Option E: Service mesh as default platform baseline

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

## Provisional recommendation

Adopt **Option A: Minimal 1.0 hardening with external TLS and AIB-managed secret protection**.

Use three profiles:

| Profile | Scope | Requirements |
|---|---|---|
| Minimal/dev | Local demos and development | HTTP allowed locally, memory/local storage allowed, dev skip flags allowed only for local test |
| Recommended production | First production target | TLS at external ingress/Gateway/reverse proxy, Kubernetes Secrets/external secret manager, AIB durable storage and encryption backend, no plaintext production credentials in CRDs, no raw tokens in logs/telemetry |
| Advanced future | High-security environments | Gateway resource-boundary enforcement, NetworkPolicy, cert-manager chart support, in-cluster mTLS/SPIFFE/service mesh, workload identity binding |

The 1.0 target should require:

1. External user/client traffic uses TLS in production.
2. AIB production deployments use durable storage and a production encryption backend.
3. AIB dev-only skip flags are never enabled in production.
4. Raw OAuth tokens, AIB exchanged tokens, client secrets, signing keys, and encryption keys are never persisted in KAOS memory/events/logs.
5. Production credentials are referenced through Kubernetes Secrets or external secret management, not literal CRD fields.
6. Gateway TLS/cert-manager, NetworkPolicy, service mesh, SPIFFE, and workload identity binding are deferred hardening layers.

---

## Host questions required to finalize ADR-007

### Q1. Should external TLS be required for production but not block the initial architecture?

Recommended answer:

- Yes. Production traffic should use TLS at ingress/Gateway/reverse proxy, but AIB integration should not require cert-manager or Gateway TLS chart support in 1.0.

Tradeoff:

- Keeps 1.0 implementable while documenting the production requirement clearly.

### Q2. Should cert-manager be mandatory?

Recommended answer:

- No. cert-manager should be recommended as a Kubernetes-native certificate option, but not mandatory because some deployments terminate TLS at cloud load balancers or corporate ingress layers.

Tradeoff:

- More flexible, but less prescriptive.

### Q3. Should in-cluster mTLS/SPIFFE/service mesh be required in 1.0?

Recommended answer:

- No. Defer to advanced/future profile.

Tradeoff:

- Lower implementation complexity, but in-cluster traffic is not cryptographically bound to workload identity in 1.0.

### Q4. Should NetworkPolicy be mandatory in 1.0?

Recommended answer:

- No. Treat NetworkPolicy as part of the Gateway/resource-boundary hardening extension.

Tradeoff:

- Avoids CNI-dependent complexity, but direct ClusterIP bypass prevention is not solved by default.

### Q5. Should KAOS store or cache delegated third-party tokens?

Recommended answer:

- No. AIB owns token vault storage and encryption. KAOS runtimes may use delegated tokens transiently for calls but must not persist raw tokens in memory/events/logs.

Tradeoff:

- Clearer secret ownership, but runtime integrations must carefully avoid leaking transient tokens.

### Q6. Should literal production secrets in CRDs be allowed?

Recommended answer:

- No for production guidance. Existing direct-value fields may remain for compatibility/dev, but production docs and future validation should steer users to Kubernetes Secrets or external secret managers.

Tradeoff:

- Safer operational posture, while preserving current CRD flexibility.

### Q7. What minimum audit/telemetry should be required?

Recommended answer:

- Record security decision metadata: principal identity, source identity, target identity, action, grant/consent decision code, and correlation IDs. Do not record raw tokens, client secrets, signing keys, OAuth authorization codes, or encryption keys.

Tradeoff:

- Provides useful auditability without exposing sensitive material.

---

## Proposed ADR-007 decision if host agrees

1. KAOS 1.0 uses a minimal hardening baseline, not service mesh or mandatory in-cluster mTLS.
2. Production external user/client traffic must use TLS at ingress, Gateway, load balancer, or trusted reverse proxy.
3. cert-manager is recommended for Kubernetes-native certificate automation but not mandatory.
4. Gateway TLS support is a recommended chart/controller enhancement, not a prerequisite for the initial AIB integration.
5. NetworkPolicy is deferred to the Gateway/resource-boundary hardening extension.
6. SPIFFE, service mesh, and cryptographic workload binding are deferred advanced-profile features.
7. AIB owns token vault storage and encryption; KAOS must not persist delegated third-party tokens.
8. AIB production deployments must use durable storage and production-grade encryption/key management.
9. AIB development skip flags for HTTPS/SSRF validation must not be enabled in production.
10. Production credentials should be provided through Kubernetes Secrets or external secret management, not literal CRD values.
11. Security logs/telemetry must include decision metadata and correlation IDs but never raw tokens or secrets.
12. Existing KAOS operator container hardening remains the baseline pattern for new KAOS-managed security components where practical.

## Decision status

Awaiting host answers.
