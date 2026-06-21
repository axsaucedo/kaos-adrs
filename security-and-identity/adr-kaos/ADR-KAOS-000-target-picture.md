# ADR-KAOS-000: Security and identity target picture

**Status**: Accepted
**Date**: 2026-06-21

---

## Purpose

This ADR is the single, self-contained view of the KAOS security and identity target
architecture. It can be read independently. It states what the system is, how the pieces fit,
and who owns what. It omits source-level investigation, alternatives, and decision justification —
those live in the per-topic ADRs indexed at the end. It supersedes the former standalone
responsibility-matrix ADR; the matrix now lives here.

---

## One-paragraph summary

Kubernetes remains the source of truth for resource existence, topology, and logical identity.
Enforcement is **gateway-centric**: an Envoy-compatible Gateway authenticates requests, calls the
Agentic Identity Broker (AIB) for allow/deny resource decisions, and performs token exchange — all
inline. Every protected request carries **two identities**: a user **principal** (subject) issued by
Keycloak/OIDC, and the calling agent (**actor**) issued by **AIB**. Resource access is decided on the
**actor's own AIB identity, never on the user token's `azp`**, which makes multi-agent delegation
correct. The SDK is **propagation-only** — it carries the two identities across hops and manages the
agent's machine-token lifecycle, but it does not enforce. Authorization is data-first and
no-permission-by-default: KAOS CRD wiring declares *requested* access; AIB stores *approved* resource
grants and user-delegated third-party grants. The authorization integration is backend-neutral
(AIB default, OPA drop-in) over the standard Envoy `ext_authz` contract.

---

## Actors and components

| Component | Role |
|---|---|
| KAOS CRDs / operator | Source of truth for Agent/MCPServer/ModelAPI existence, topology, logical identity, requested access edges; mounts AIB agent credentials into pods; generates Gateway routes, `ext_authz`/`ext_proc` policy, and NetworkPolicy. |
| Gateway (Envoy-compatible) | The enforcement plane: `jwt_authn` (two providers), `ext_authz` → AIB, `ext_proc` → AIB token exchange, fail-closed. |
| AIB (external broker) | Agent identity issuance (per-agent credentials + AIB-signed actor tokens), approved KAOS resource grants, user-delegated third-party grants, consent, third-party OAuth sessions/token vault, token exchange, and `ext_authz` access decisions. |
| External IdP (Keycloak/Dex/OIDC) | Human authentication and user identity only. Not replaced by AIB; does not issue agent identities. |
| KAOS / AIB SDK | Propagation-only: carries subject + actor across hops and manages the agent machine-token lifecycle. Optional access-check/token-exchange helpers for custom off-gateway servers. |
| LiteLLM | ModelAPI internals: model allowlists, provider credentials, budgets, rate limits. |
| NetworkPolicy / CNI | Required bypass-prevention: denies direct ClusterIP workload-to-workload application traffic. |
| KAOS–AIB sync service | Lightweight external reconciliation of KAOS resources into AIB records; provisions per-agent credentials into Secrets. |

---

## Identity model

KAOS resources carry a first-class, user-configurable logical security identity through
`spec.security.id`, with a Kubernetes namespace/name default:

| Case | Resolved external identity |
|---|---|
| `spec.security.id` omitted | `kaos://{kind}/{namespace}/{name}` |
| `spec.security.id` provided | `kaos://{kind}/{id}` |

This identity is what AIB stores as `external_id`; it is stable across delete/recreate so grants
survive, human-readable, and namespace-independent when set. **`spec.security.id` is the only
per-resource security field** — authn/authz are operator-wide and identity/credentials are
auto-provisioned, so a CRD author cannot weaken the enforced posture.

The logical id is an *identifier*. Each identity-bearing **caller** (every Agent, and an MCPServer when
it calls out) additionally has an **AIB-issued authentication credential**: AIB registers the agent and
issues per-agent client credentials; the agent runs a `client_credentials` grant against AIB to obtain a
short-lived, AIB-signed **actor token** (`sub`/`azp` = its logical identity). **Keycloak issues human
tokens only; AIB issues agent identities.** Client auth defaults to `client_secret` (`private_key_jwt`
stronger); cryptographic pod binding via mTLS/SPIFFE is future hardening. See
[ADR-KAOS-001](./ADR-KAOS-001-identity-model-and-source-of-truth.md) and [ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md).

---

## Enforcement model

Enforcement is gateway-centric. There are two deployment states, plus future hardening — **not** a
ladder of profiles.

**Development (no gateway):** the SDK propagates context but nothing is enforced. Local/dev only.

**Secured (gateway enabled):** the required target. Protected runtime URLs use Gateway routes,
NetworkPolicy restricts ClusterIP bypass, and every request flows through the inline pipeline:

```text
caller request
  ( Authorization: Bearer <user subject, Keycloak>  +  x-agent-authorization: Bearer <agent actor, AIB> )
    -> jwt_authn   validate subject (userAuth.issuer) and actor (agentAuth.issuer)
    -> ext_authz   AIB decides actor (calling agent) -> target resource; user principal for delegated grants
    -> ext_proc    AIB token exchange when a delegated third-party token is required
  -> protected MCPServer / ModelAPI / Agent
```

The Gateway is the only enforcement point; the SDK only propagates the two identities. ModelAPI is
covered uniformly behind the Gateway (no per-runtime auth), with LiteLLM keeping model/budget internals.
**NetworkPolicy is required** so the Gateway cannot be bypassed via ClusterIP. mTLS/SPIFFE/service mesh
and pod-level workload binding are **future hardening**. See
[ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md), [ADR-KAOS-007](./ADR-KAOS-007-transport-security-and-hardening-baseline.md),
and [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md).

### Two-identity model and multi-agent delegation

The decision keys on the **actor** (the calling agent's own AIB identity), with the user **subject** used
for user-delegated third-party grants. This resolves the multi-agent delegation gap:

```text
user -> Agent A -> Agent B -> MCPServer Y   (A may access MCP X; B may access MCP Y)

Naive bug:  B forwards the user token (azp = A); reading azp attributes B's call to A.
Resolution: each agent authenticates as itself, so B's call carries actor = B.
            -> B -> Y allowed only if B is granted Y;  A -> Y denied even though A delegated to B.
```

Correct least privilege, no nested-actor chains. Resource-access decisions never read
`subject_token.azp`. Deep delegation-chain policy is out of scope.

---

## Authorization model

Authorization is data-first, not a policy language, and no-permission-by-default. Two grant families:

```text
requested edge        (KAOS CRD wiring; a request, not an approval)
  kaos://agent/researcher -> kaos://mcpserver/github, action=call

approved resource grant (AIB; platform/resource authorization)
  kaos://agent/researcher -> kaos://mcpserver/github, action=call, status=approved

user delegated grant   (AIB; user consents to third-party access by an agent)
  keycloak://kaos/alice -> kaos://agent/researcher -> github-issues-reader
```

The Gateway's `ext_authz` call to AIB allows a resource call only if a matching requested edge and
approved resource grant exist for the **actor**; a third-party token is provided only if a matching user
delegated grant and a usable third-party session also exist. CRD wiring declares capability, never
approval (`declared != granted`). CEL is used only for bounded claim extraction. The authz integration
is **backend-neutral**: the standard Envoy `ext_authz` contract plus neutral `kaos.resource`/`kaos.action`
context_extensions, so the backend is swappable with no Envoy/KAOS config change — **AIB default, OPA
drop-in** (opa-envoy). Keycloak Authorization Services and OPA-as-default remain optional future
integrations. See [ADR-KAOS-005](./ADR-KAOS-005-authorization-and-policy-model.md) and
[ADR-AIB-002](../adr-aib/ADR-AIB-002-aib-access-check-api.md).

---

## Runtime behavior

**Propagation & token lifecycle.** The SDK carries the user subject token and attaches the agent actor
token on outbound calls. Pods hold long-lived **credentials**, not long-lived tokens; actor tokens are
short-lived. The SDK uses refresh-ahead caching, file-watched credential reload on rotation, a single
reactive retry on 401, and backoff — so the instrumented call is the seamless "ensure-fresh + inject +
retry" path. The gateway pipeline runs inline in one pass.

**Fail closed.** Auth is a critical path: an expired/unrefreshable actor token yields 401/403; an
unreachable `ext_authz`/AIB yields 503. There is no fail-open knob and no silent allow.

**Failure / re-authentication outcomes** are surfaced via the gateway path (`ext_authz` denied responses /
`ext_proc` immediate responses), not application code, and never block synchronously:

| Outcome | Behavior |
|---|---|
| Missing platform resource grant | Fail closed: `platform_grant_missing`; no user-action URL. |
| Missing/expired user delegated grant | Fail: `user_grant_required`; user re-grants and retries. |
| Missing/unusable third-party OAuth session | Fail: `third_party_reauth_required` + re-auth URL; user reconnects and retries. |
| Autonomous run needs a user action | Record `user_action_required`; stop/skip the protected action. |
| Runtime/tool-argument approval | Not modeled yet; future. |

See [ADR-KAOS-003](./ADR-KAOS-003-user-request-context-propagation.md), [ADR-KAOS-006](./ADR-KAOS-006-re-authentication-execution-model.md),
and [ADR-AIB-001](../adr-aib/ADR-AIB-001-aib-python-sdk-design.md).

---

## Integration and lifecycle

KAOS separates **AIB lifecycle** (AIB and Keycloak are external; KAOS does not own/upgrade them) from
**AIB integration** (KAOS configures itself to use them). Integration follows the same flow as other
`kaos system install` integrations (otel, gateway): as a bootstrap convenience the CLI can install the
Keycloak + AIB Helm charts and wire the operator security config, or point at externally-managed
instances:

```text
kaos system install --aib-enabled --keycloak-enabled        # convenience: install charts + wire config
kaos system install --aib-enabled --idp-issuer ... --aib-issuer ... --aib-ext-authz-url ... --aib-ext-proc-url ...
```

Installing the charts is a bootstrap, not KAOS taking ownership. Automatic KAOS→AIB synchronization is a
**lightweight external sync service** (not KAOS core, not AIB core): it watches KAOS resources and
projects, at a high level, logical identities (`external_id`), requested access edges (kept distinct from
approved grants), third-party services and PermissionSets, **per-agent client credentials** (into Secrets,
which the operator mounts), and drift/status. AIB admin URL/credentials live in the sync-service config.
See [ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md).

### Operator-wide configuration (Helm)

```yaml
security:
  userAuth:                    # human users — standard OIDC; validated at the gateway (Keycloak default, swappable)
    issuer:  https://keycloak.<domain>/realms/kaos
    audience: kaos
    jwksUri: ""                # optional; discovered from issuer .well-known
  agentAuth:                   # agent identity + authorization via AIB
    issuer:  http://aib-enduser.aib-system.svc.cluster.local:8000   # AIB OIDC issuer: mints agent tokens + JWKS
    extAuthzUrl: aib-ext-authz.aib-system.svc.cluster.local:9002    # envoy ext_authz — access checks (AIB default; OPA drop-in)
    extProcUrl:  aib-extproc.aib-system.svc.cluster.local:50051     # envoy ext_proc — token exchange
    credentialSecretPrefix: kaos-aib                                # per-agent credential Secret (operator mounts; sync creates)
```

Per-resource config is `spec.security.id` only.

---

## AIB capabilities the target depends on

KAOS reuses AIB's implemented capabilities (OAuth2 authorization server with `client_credentials` +
JWKS, per-agent client credentials, RFC 8693 token exchange, JWT validation, CEL claim extraction, Envoy
ExtProc, user consent, third-party token vault). The target also depends on AIB additions, owned by AIB
and specified in `adr-aib/`:

- A first-class **access-check API** — `POST /api/access/check` for SDKs and an Envoy `ext_authz` service
  for the Gateway, returning allow/deny only, keyed on the actor —
  [ADR-AIB-002](../adr-aib/ADR-AIB-002-aib-access-check-api.md).
- A first-class **platform/resource grant model** distinct from user-delegated OAuth grants; until it
  exists, resource grants may be bootstrapped through a synthetic service + PermissionSet scopes, marked
  temporary — [ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md).

The propagation-only **Python SDK** (with the agent machine-token lifecycle) is specified in
[ADR-AIB-001](../adr-aib/ADR-AIB-001-aib-python-sdk-design.md).

---

## Responsibility matrix

| Concern | Owner | Optional/future owner | Notes |
|---|---|---|---|
| KAOS resource existence, topology, logical identity | KAOS CRDs/operator | — | Kubernetes is source of truth (ADR-KAOS-001). |
| Requested access edges | KAOS CRDs/operator | KAOS–AIB sync mirrors to AIB | Wiring is request, not approval. |
| Agent identity issuance | AIB (per-agent credentials + actor tokens) | — | `client_credentials`, local/hybrid mode. |
| User authentication / claims | Keycloak/Dex/OIDC | Enterprise IdP | AIB does not replace SSO; Keycloak/Dex/OIDC do not issue agent identities. |
| Approved KAOS resource grants | AIB | AIB first-class resource-grant model | Bootstrap may use synthetic PermissionSet encoding. |
| User delegated third-party grants / token vault | AIB | AIB | UserGrant + PermissionSet, sessions. |
| Access-check decisions | AIB `ext_authz` (+ HTTP for custom servers) | OPA drop-in | Allow/deny only, actor-keyed (ADR-AIB-002). |
| Token exchange for third-party APIs | AIB `ext_proc` at the gateway | SDK for custom servers | RFC 8693. |
| Enforcement (authn/authz/token-exchange) | Gateway (Envoy) | — | jwt_authn + ext_authz + ext_proc. |
| Bypass prevention | NetworkPolicy (required) + Gateway | mesh identity | Depends on CNI. |
| Context propagation + machine-token lifecycle | KAOS/AIB SDK | — | Propagation-only; no enforcement. |
| MCP tool/argument authorization | — | Future tool-permission model | Not at the gateway. |
| ModelAPI model/budget/rate policy | LiteLLM | — | Not AIB PermissionSets. |
| Transport TLS | Ingress/Gateway/reverse proxy | cert-manager/native TLS | External TLS baseline (ADR-KAOS-007). |
| Workload identity / mTLS | — | SPIFFE/mesh/K8s SA binding | Future hardening. |
| General policy language/PDP | AIB grant lookup | OPA/Rego or Keycloak AuthZ | Optional. |

### Build / adopt

| Area | Approach |
|---|---|
| KAOS logical identity, requested-edge extraction, operator credential-mount, Gateway/NetworkPolicy generation | Build in KAOS |
| KAOS–AIB sync service | Build externally; upstream reusable patterns to AIB if generic |
| AIB agent-identity issuance, access-check API, first-class resource grants | Build/upstream in AIB |
| AIB consent, token exchange, OAuth2 server | Adopt from AIB |
| Propagation SDK (+ machine-token lifecycle) | Build/upstream in the AIB SDK |
| LiteLLM model/budget integration | Adopt LiteLLM; build KAOS config wiring only |
| Keycloak/Dex OIDC | Adopt existing IdP tooling |
| OPA/Keycloak AuthZ PDP; native TLS/mesh/SPIFFE | Optional future hardening |

---

## ADR index

KAOS-owned (`adr-kaos/`):

| ADR | Topic |
|---|---|
| ADR-KAOS-000 (this) | Security and identity target picture |
| [ADR-KAOS-001](./ADR-KAOS-001-identity-model-and-source-of-truth.md) | Identity model and source of truth |
| [ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md) | Enforcement topology |
| [ADR-KAOS-003](./ADR-KAOS-003-user-request-context-propagation.md) | User and request context propagation |
| [ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md) | AIB responsibility boundary |
| [ADR-KAOS-005](./ADR-KAOS-005-authorization-and-policy-model.md) | Authorization and policy model |
| [ADR-KAOS-006](./ADR-KAOS-006-re-authentication-execution-model.md) | Re-authentication execution model |
| [ADR-KAOS-007](./ADR-KAOS-007-transport-security-and-hardening-baseline.md) | Transport security and hardening baseline |
| [ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md) | AIB integration and synchronization architecture |
| [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md) | Gateway API resource-boundary enforcement |

AIB-owned (`adr-aib/`):

| ADR | Topic |
|---|---|
| [ADR-AIB-001](../adr-aib/ADR-AIB-001-aib-python-sdk-design.md) | AIB Python SDK design |
| [ADR-AIB-002](../adr-aib/ADR-AIB-002-aib-access-check-api.md) | AIB access-check API |
