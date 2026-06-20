# ADR-000: Security and identity target picture

**Status**: Accepted
**Date**: 2026-06-20

---

## Purpose

This ADR is the single, self-contained view of the KAOS security and identity target
architecture. It can be read independently. It states what the system is, how the pieces
fit, and who owns what. It deliberately omits source-level investigation, alternatives,
and decision justification — those live in the per-topic ADRs indexed at the end.

It supersedes the former standalone responsibility-matrix ADR; the matrix now lives here.

---

## One-paragraph summary

KAOS keeps Kubernetes as the source of truth for resource existence, topology, and logical
identity. The Agentic Identity Broker (AIB) is the external authorization and delegated-token
broker. An external Identity Provider (Keycloak/Dex/OIDC) authenticates humans. Security is
enforced in layers: an always-present **SDK-native** layer carries request context and asks AIB
for decisions and tokens; an opt-in **Gateway resource-boundary** layer makes the Gateway the
default access path and enforces fail-closed authorization, token exchange, and bypass
prevention; and an optional **transport/workload hardening** layer adds TLS, mTLS, and workload
identity. Authorization is data-first: KAOS CRD wiring declares *requested* access; AIB stores
*approved* resource grants and user-delegated third-party grants; nothing is permitted by
default.

---

## Actors and components

| Component | Role in the target |
|---|---|
| KAOS CRDs / operator | Source of truth for Agent, MCPServer, ModelAPI existence, topology, logical identity, requested access edges, runtime wiring. |
| KAOS / AIB SDK | Application-level request context propagation and AIB client calls inside Agent and MCPServer runtimes. |
| AIB (external broker) | Approved KAOS resource grants, user-delegated third-party grants, consent, third-party OAuth sessions/token vault, token exchange, and access-check decisions. |
| External IdP (Keycloak/Dex/OIDC) | Human authentication, user identity, claims/groups. Not replaced by AIB. |
| LiteLLM | ModelAPI internals: model allowlists, provider credentials, budgets, rate limits. |
| Gateway API (Envoy-compatible) | Resource-boundary routing, fail-closed `ext_authz` authorization, ExtProc token exchange, header normalization. |
| NetworkPolicy / CNI | Direct ClusterIP bypass prevention in the Gateway resource-boundary profile. |
| KAOS–AIB sync service | Lightweight external reconciliation of KAOS resources into AIB records. |

---

## Identity model

KAOS resources carry a first-class, user-configurable security identity through
`spec.security.id`, with a Kubernetes namespace/name default:

| Case | Resolved external identity |
|---|---|
| `spec.security.id` omitted | `kaos://{kind}/{namespace}/{name}` |
| `spec.security.id` provided | `kaos://{kind}/{id}` |

This identity is what AIB stores as `external_id`. It is stable across delete/recreate so grants
survive, human-readable, and namespace-independent when an explicit ID is set. Cluster identity,
Kubernetes ServiceAccount binding, and SPIFFE/SPIRE workload identity are not part of the logical
identity model; they are options in the advanced/hardened profile. Agent, MCPServer, and ModelAPI
are all identity-bearing. See [ADR-001](./ADR-001-identity-model-and-source-of-truth.md).

---

## Enforcement layers

Security is enforced in three complementary layers. They are not sequential releases; they are
layers that a deployment combines through a profile.

### 1. SDK-native enforcement (always present)

The SDK is the only component with full semantic context: agent run state, session, tool call,
A2A delegation, and autonomous task correlation. It owns:

- parsing trusted inbound identity/context into a `RequestSecurityContext`,
- propagating non-secret context across A2A, MCP, and ModelAPI calls,
- AIB grant/access checks and token exchange,
- tool-level and argument-level decisions (where modeled),
- structured grant/re-authentication handling,
- audit metadata, without persisting raw bearer tokens.

See [ADR-003](./ADR-003-user-request-context-propagation.md) and the SDK design in
[ADR-009](../adr-aib/ADR-009-aib-python-sdk-design.md).

### 2. Gateway resource-boundary enforcement (opt-in profile)

When enabled, the Gateway becomes the default application access path for protected resources,
and adds guarantees the SDK alone cannot provide:

- Gateway routes injected into runtimes instead of direct ClusterIP URLs,
- Envoy `ext_authz` fail-closed authorization (route/resource-level `require_access`),
- AIB ExtProc token exchange where exchanged downstream tokens are required,
- normalized identity headers from a trusted boundary,
- NetworkPolicy to deny direct workload-to-workload ClusterIP bypass where the CNI supports it,
- boundary audit and coarse rejection before requests reach pods.

Gateway handles the coarse resource boundary; the SDK still handles semantics. See
[ADR-011](./ADR-011-gateway-api-resource-boundary-enforcement.md).

### 3. Transport and workload hardening (optional/advanced)

- Baseline: TLS terminated at external ingress/Gateway/load balancer/reverse proxy.
- Advanced/hardened: native intra-service TLS, in-cluster mTLS, SPIFFE/SPIRE or service-mesh
  identity, Kubernetes ServiceAccount/workload binding, cert-manager automation.

See [ADR-007](./ADR-007-transport-security-and-hardening-baseline.md).

---

## Deployment profiles

A deployment selects a profile rather than a version. Profiles are additive.

| Profile | Enforcement | Transport | Bypass prevention |
|---|---|---|---|
| Baseline | SDK-native | External TLS in production | Not enforced (direct ClusterIP allowed) |
| Gateway resource-boundary | SDK-native + Gateway routing + `ext_authz` + ExtProc | External TLS, optional Gateway TLS | NetworkPolicy where CNI supports it |
| Advanced/hardened | + workload identity and policy depth | + mTLS/SPIFFE/mesh | NetworkPolicy + mesh identity |

The baseline profile is sufficient for KAOS-owned Python Agents and FastMCP runtimes. The Gateway
resource-boundary profile is the path to strong, bypass-resistant resource isolation and non-SDK
runtime coverage. The advanced/hardened profile is for regulated or multi-tenant environments.

---

## Authorization model

Authorization is data-first, not a policy language. There are two distinct grant families, and
nothing is granted by default.

```text
requested edge        (KAOS CRD wiring; a request, not an approval)
  kaos://agent/researcher -> kaos://mcpserver/github, action=call

approved resource grant (AIB; platform/resource authorization)
  kaos://agent/researcher -> kaos://mcpserver/github, action=call, status=approved

user delegated grant   (AIB; user consents to third-party access by an agent)
  keycloak://kaos/alice -> kaos://agent/researcher -> github-issues-reader
```

Runtime decisions:

- Allow a resource call only if a matching **requested edge** and **approved resource grant** exist.
- Provide a third-party token only if a matching **user delegated grant** and a usable third-party
  OAuth session also exist.

CRD wiring declares capability, never approval (`declared != granted`). Policy is grant lookup
plus expiry/status checks. CEL is used only for bounded claim extraction and simple internal
checks. OPA/Rego and Keycloak Authorization Services are optional future enterprise PDP
integrations, not part of the default model. See
[ADR-004](./ADR-004-aib-responsibility-boundary.md) and
[ADR-005](./ADR-005-authorization-and-policy-model.md).

---

## Runtime behavior

### Request context propagation

Inbound user/principal/scope/subject-token context is captured at the boundary and propagated
through agent execution, A2A delegation, MCP calls, async tasks, and autonomous runs. Raw tokens
are never persisted in memory events or durable task state.

### Access checks and token exchange

The SDK (or the Gateway, in the Gateway profile) asks AIB:

- **access check** — may this actor access this resource? (allow/deny only),
- **token exchange** — return a delegated third-party token for this user/agent/resource.

These are distinct: an access check never performs third-party token exchange and never returns a
third-party token. See the AIB access-check API in
[ADR-012](../adr-aib/ADR-012-aib-access-check-api.md).

### Failure and re-authentication outcomes

Outcomes are kept separate and fail closed; synchronous requests never block waiting for a human:

| Outcome | Behavior |
|---|---|
| Missing platform resource grant | Fail closed: `platform_grant_missing`; no user-action URL. |
| Missing/expired user delegated grant | Fail: `user_grant_required`; user re-grants and retries. |
| Missing/unusable third-party OAuth session | Fail: `third_party_reauth_required` + re-auth URL; user reconnects and retries. |
| Autonomous run needs a user action | Record `user_action_required`; stop/skip the protected action. |
| Runtime human approval / MCP tool-argument approval | Not modeled yet; optional future work. |

See [ADR-006](./ADR-006-re-authentication-execution-model.md).

---

## Integration and lifecycle

KAOS does not install, upgrade, or lifecycle-manage AIB. AIB is installed externally through its
own Helm chart or platform path. KAOS provides configuration to use an existing AIB (for example a
`kaos system install --aib-enabled ...` CLI path that wires operator settings, SDK environment
variables, and credential references).

Automatic KAOS→AIB synchronization is a **lightweight external sync service** — not KAOS core and
not AIB core. It watches KAOS resources, computes desired AIB records using stable `external_id`
values, calls AIB admin APIs, mirrors requested edges (without auto-approving them), and reports
drift/status. It may be written in any language with Kubernetes watch support and does not require
a Kubebuilder operator or new CRDs. See
[ADR-010](./ADR-010-aib-integration-and-synchronization-architecture.md).

---

## AIB capabilities the target depends on

KAOS reuses AIB's implemented capabilities (agent/service/permission-set registry, user consent,
third-party OAuth sessions/token vault, RFC 8693 token exchange, JWT validation via JWKS, CEL
claim extraction, Envoy ExtProc). The target also depends on two AIB additions, owned by AIB and
specified in the `adr-aib/` folder:

- A first-class **access-check API** (`POST /api/access/check` for SDKs and an Envoy `ext_authz`
  service for the Gateway) returning allow/deny decisions only —
  [ADR-012](../adr-aib/ADR-012-aib-access-check-api.md).
- A first-class **platform/resource grant model** distinct from user-delegated OAuth grants. Until
  it exists, resource grants may be bootstrapped through a synthetic internal service plus
  PermissionSet scopes, explicitly marked temporary — [ADR-004](./ADR-004-aib-responsibility-boundary.md).

The **Python SDK** that carries request context and calls these APIs is specified in
[ADR-009](../adr-aib/ADR-009-aib-python-sdk-design.md).

---

## Responsibility matrix

The component that is the best fit owns each concern. AIB is not an all-purpose security platform.

| Concern | Owner | Optional/advanced owner | Notes |
|---|---|---|---|
| KAOS resource existence | KAOS CRDs/operator | — | Kubernetes is source of truth. |
| KAOS logical identity | KAOS CRDs/operator | — | `spec.security.id` / default identity (ADR-001). |
| Requested access edges | KAOS CRDs/operator | KAOS–AIB sync service mirrors to AIB | Wiring is request, not approval. |
| Approved KAOS resource grants | AIB | AIB first-class resource-grant model | Bootstrap may use synthetic PermissionSet encoding. |
| User authentication | Keycloak/Dex/OIDC | Enterprise IdP | AIB does not replace SSO. |
| User claims/groups | Keycloak/Dex/OIDC | Enterprise IdP | AIB consumes claims, does not own identity. |
| User delegated third-party grants | AIB | AIB | UserGrant + PermissionSet domain. |
| Third-party OAuth sessions/token vault | AIB | AIB | Not KAOS runtime state. |
| Token exchange for third-party APIs | AIB | AIB ExtProc at the Gateway | SDK-native by default; Gateway/ExtProc in the Gateway profile. |
| Access-check decisions | AIB access-check API | AIB `ext_authz` at the Gateway | Allow/deny only (ADR-012). |
| SDK request context propagation | KAOS/AIB SDK | Third-party AIB SDK + framework helpers | SDK design in ADR-009. |
| Agent/MCPServer root authorization | AIB grant checks via SDK | Gateway `ext_authz` + NetworkPolicy | Resource-level, not tool-level. |
| MCP tool/argument authorization | SDK/runtime (where modeled) | Future tool-permission model + AIB/OPA | Not in the default authorization model. |
| ModelAPI root authorization | AIB resource grants | Gateway resource-boundary enforcement | Root access only. |
| ModelAPI model/budget/rate policy | LiteLLM | LiteLLM/enterprise controls | Not AIB PermissionSets. |
| Gateway routes/policy | KAOS Gateway integration | Gateway + NetworkPolicy | AIB does not own route config. |
| Human approval / pause-resume | — | KAOS task/UI approval model | A2A `input-required` is a future path. |
| General policy language/PDP | Simple AIB grant lookup | OPA/Rego or Keycloak AuthZ | Optional enterprise extension. |
| Transport TLS | Ingress/Gateway/reverse proxy | Gateway TLS/cert-manager/native TLS | ADR-007. |
| Network bypass prevention | Gateway + NetworkPolicy (Gateway profile) | Mesh identity | Depends on CNI. |
| Workload identity/mTLS | — | SPIFFE/mesh/K8s SA binding | Advanced/hardened profile. |

### Build / adopt / upstream

| Area | Approach |
|---|---|
| KAOS logical identity and requested-edge extraction | Build in KAOS |
| KAOS–AIB sync service | Build externally; upstream reusable reconciliation patterns to AIB if generic |
| AIB first-class resource grants and access-check API | Build/upstream in AIB |
| AIB user consent and token exchange | Adopt from AIB |
| AIB SDK generic client pieces | Upstream to AIB where generic |
| KAOS runtime SDK adapters | Build in KAOS |
| Gateway/NetworkPolicy enforcement | Build in KAOS (Gateway profile) |
| LiteLLM model/budget integration | Adopt LiteLLM; build KAOS config wiring only |
| Keycloak/Dex OIDC integration | Adopt existing IdP tooling |
| OPA/Keycloak AuthZ PDP | Optional enterprise extension |
| Native TLS/service mesh/SPIFFE | Optional hardening profile |

---

## ADR index

KAOS-owned decisions (`adr-kaos/`):

| ADR | Topic |
|---|---|
| ADR-000 (this) | Security and identity target picture |
| [ADR-001](./ADR-001-identity-model-and-source-of-truth.md) | Identity model and source of truth |
| [ADR-002](./ADR-002-enforcement-topology.md) | Enforcement topology |
| [ADR-003](./ADR-003-user-request-context-propagation.md) | User and request context propagation |
| [ADR-004](./ADR-004-aib-responsibility-boundary.md) | AIB responsibility boundary |
| [ADR-005](./ADR-005-authorization-and-policy-model.md) | Authorization and policy model |
| [ADR-006](./ADR-006-re-authentication-execution-model.md) | Re-authentication execution model |
| [ADR-007](./ADR-007-transport-security-and-hardening-baseline.md) | Transport security and hardening baseline |
| [ADR-010](./ADR-010-aib-integration-and-synchronization-architecture.md) | AIB integration and synchronization architecture |
| [ADR-011](./ADR-011-gateway-api-resource-boundary-enforcement.md) | Gateway API resource-boundary enforcement |

AIB-owned decisions (`adr-aib/`):

| ADR | Topic |
|---|---|
| [ADR-009](../adr-aib/ADR-009-aib-python-sdk-design.md) | AIB Python SDK design |
| [ADR-012](../adr-aib/ADR-012-aib-access-check-api.md) | AIB access-check API |
