# Research 005 — Control-plane PDP, identity planes, and the relationship model (converged design)

**Date**: 2026-07-11
**Sources**: design discussion converging research/001–004; operator code inspection (`controllers/authz_projection_controller.go` `PolicyProjector` seam, `internal/authz/adapters/projector_aib.go` `AIBAdmin` surface); external prior art cited inline.

This document records the converged phase-2 design from the cross-cutting discussion: where identities live, where relationships live, where decisions run, and what each preset means. The ADR index reflects these outcomes; individual ADRs formalize them.

## The foundational claim: identity providers do not ship decision points

No third-party IdP — Keycloak, AIB, or otherwise — exposes an authorization decision endpoint for a platform's internal traffic, and that is an industry-wide architectural choice, not a gap: IdPs authenticate and issue claims; the policy decision point (PDP) is owned by the platform being protected. Kubernetes works this way (identities from certs/OIDC, RBAC decided inside the API server against RoleBindings), Istio does (AuthorizationPolicy CRDs compiled by istiod into proxy config), and the agent-space projects do too: [agentgateway](https://agentgateway.dev/docs/kubernetes/main/mcp/auth/about/) enforces its own RBAC at the gateway with CEL rules over JWT claims and MCP tool names, and [Google's Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview) mints per-agent identities but decides authorization in the gateway, not the IdP. The Keycloak OPA plugin ([EOEPCA](https://github.com/EOEPCA/keycloak-opa-plugin)) confirms the direction: it lets *Keycloak* delegate its internal policy evaluation *to* OPA (Policy Provider SPI) — it is not an enforcement surface Envoy could call. KAOS owning the authz endpoint is therefore the standard architecture, not a workaround for an AIB/Keycloak deficiency.

## The design: three planes with one owner each

### 1. Identity plane — who exists

- **Users**: the OIDC provider (Keycloak default). Subject tokens carry `sub`, roles, and groups; group membership is administered in the IdP UI. The IdP stores who exists, never who-may-do-what.
- **Agents**: preset-selectable issuer behind one abstraction (ADR 0002):
  - **Kubernetes ServiceAccount projected tokens** for in-cluster-only postures: the kubelet projects an auto-rotated token, the API server is a genuine OIDC issuer (discovery + JWKS), no secrets to mint or rotate, zero IdP projection. The `sub` is `system:serviceaccount:<ns>:<name>`; mapping to `kaos://agent/<ns>/<name>` is a one-line entry in projected policy data.
  - **OIDC provider clients provisioned via RFC 7591/7592 Dynamic Client Registration** when agent identity must participate in the broader OAuth world: agents called from outside the cluster, agents acting as OAuth clients to third parties, multi-cluster trust domains, or the future consent/delegation path (F9). Keycloak supports DCR natively; AIB's admin API is the per-provider fallback behind the same projector seam.
- **Resources** (MCP servers, model APIs, memory): targets, not token holders — identified by the `kaos://<slug>/<ns>/<name>` scheme stamped per route as `x-kaos-target-resource`. No credentials needed.

### 2. Relationship plane — who may reach what (source of truth: KAOS CRDs)

The guide is the Kubernetes RBAC analogy: identities live externally, *bindings* live in the cluster as declarative, GitOps-reviewable objects.

- **agent→agent / agent→mcp / agent→model / agent→memory**: already expressed by the workload specs (`mcpServers`, `agentNetwork.access`, model and memory references). The projection derives the grant graph from them; wiring an agent to a tool *is* granting it. Nothing new to store.
- **user→kaos-resource**: one new, small CRD — working name `AccessGrant` — binding subjects to resources: `subjects` (a user `sub`/email, or a Keycloak role/group reference) → `resources` (explicit `kaos://` ids or a label selector). Referencing IdP groups keeps the *edge* ("group `/researchers` may use agent `researcher`") declarative and cluster-RBAC-protected while *membership* is managed day-to-day in the IdP UI with zero sync — it arrives in the token as a claim.
- **A dedicated relationship store is not warranted at this scale.** Zanzibar-style systems ([SpiceDB/OpenFGA vs OPA](https://www.permit.io/blog/zanzibar-vs-opa)) earn their keep with millions of tuples, nested-group resolution, and list-filtering queries; KAOS's graph is small, cluster-scoped, and already declaratively stored in etcd via CRDs. A ReBAC database is the documented growth path if the graph ever outgrows a projected document — not the starting point.

### 3. Decision plane — who says yes/no (KAOS-owned PDP behind ext_authz)

- **Deployment shape**: a separate lightweight PDP Deployment (2 replicas, PodDisruptionBudget), *not* in the operator process — in-process would put the control plane in the data path, failing (closed) all inter-agent traffic on every operator restart or upgrade. The data path must depend only on data-path components.
- **Implementation**: stock OPA image with the built-in `envoy_ext_authz_grpc` plugin (zero KAOS service code; only the rego and data document are KAOS-authored — both already exist from phase 1). Alternatives recorded in ADR 0001: a small Go ext_authz server (typed decisions, one fewer image, but owns a security-critical server and loses bring-your-own-rego) and [Authorino](https://docs.kuadrant.io/1.0.x/authorino/docs/user-guides/keycloak-authorization-services/) (off-the-shelf ext_authz that can evaluate Keycloak Authorization Services and inline rego — the buy option).
- **Fail-closed everywhere**: ext_authz `failOpen: false`; PDP unavailable → 403. The filter evaluates every request on internal routes, subject token or not, closing G1 by construction.

## CRDs are the store; the ConfigMap is a compile target

The CRDs are the single source of truth, but the PDP cannot consume Kubernetes objects — OPA evaluates a JSON data document. The projected ConfigMap is the *compile target*, a derived artifact and never a second store: delete it and the operator regenerates it. This mirrors Istio (istiod compiles AuthorizationPolicy into proxy config) and Kubernetes RBAC (the API server consumes compiled binding state). The alternative — the PDP watching CRDs directly (e.g. OPA kube-mgmt) — was rejected: derivation logic would move from tested Go into rego, the PDP would need K8s API watch permissions (putting API-server availability on the data path), and the manual/bring-your-own-data modes plus the atomic-snapshot property (one reconcile = one consistent document) would be lost.

## What is stored where

| Fact | Store | Admin surface |
|---|---|---|
| User identities & group membership | OIDC provider (Keycloak default) | IdP UI |
| Agent identities & credentials | K8s ServiceAccounts (internal preset) or IdP clients via DCR | Operator, automatic from Agent CRDs |
| agent→resource edges | Existing Agent/MCPServer/ModelAPI specs | kubectl / GitOps (already) |
| user→resource edges | `AccessGrant` CRD (subjects may reference IdP groups) | kubectl / GitOps; membership in IdP UI |
| Compiled decision data | Projected ConfigMap (`data.kaos.*`, extended with user dimension) | Operator (automated) or manual modes |
| The decision | KAOS PDP (stock OPA) behind gateway ext_authz | KAOS chart |

No component stores a fact another component owns.

## IdP projection shrinks to credential provisioning

With authorization out of the IdP, the projector's only remaining job is: ensure a client exists per agent and deliver its secret as a K8s Secret (create/rotate/delete — the DCR surface). Registering services, binding permission sets, and the grant graph all leave the IdP and live in the ConfigMap compile path. This is why a generic DCR-based `OIDCProjector` is realistic where a full authz-model sync never was; the existing `PolicyProjector` seam (`controllers/authz_projection_controller.go`) already accommodates it as a third adapter. Under the ServiceAccount issuer, IdP projection disappears entirely.

**AIB permission sets are exchange-scoped**: they are AIB's token-exchange-time concept and re-enter only if/when F9 (consent-based third-party delegation) is adopted. The AIB adapter's base surface is credential provisioning; permission-set binding is an optional extra enabled only with the exchange feature, and never leaks into the PDP path.

## Preset semantics under the new topology

`kaos-internal` was demo-grade in phase 1 for one reason: without AIB there was no decision point at all. The new topology removes that reason — the PDP is present in every preset — so the preset graduates to an honestly scoped production posture:

- **`kaos-internal` — agent-plane security**: ServiceAccount-token agent identity, PDP enforcing agent→resource, fail-closed, G1 closed, zero external dependencies. No user dimension: user access is governed by cluster credentials (K8s RBAC), exactly as Kubernetes itself operates without an OIDC provider. Production-capable for what it claims; documented as not providing user→resource control.
- **Keycloak-backed presets — add the user plane**: same PDP, same graph, plus subject-token verification and `AccessGrant` enforcement. Agent issuer per ADR 0002 (DCR clients, or AIB for the F9 path).
- **Demo conveniences** (e.g. `agentJwtVerification=skip`) stop being a preset property and remain explicitly quarantined flags.

**`AccessGrant` without a user IdP**: accepted but marked unenforced — the projection reconciler sets a status condition `Enforced=False`, `reason=NoUserIdentityProvider`, emits a warning event, and the compiler skips projecting user-subject grants. No admission webhook (extra component; breaks GitOps dry-runs). Enabling the user plane flips the same objects to enforced on the next reconcile with no changes. Declared-but-silently-ignored is the one dishonest state this design forbids.

## Token exchange (F9) stays orthogonal

Nothing in this design blocks re-adding AIB's ext_proc exchange later for third-party delegation; it composes as an additional filter alongside ext_authz. It is deferred as an extension because it carries its own unsolved problems independent of authorization: the consent UX, where the consent screen lives, and how vaulted third-party sessions get established. It becomes worth solving when a concrete third-party use case exists — with the authorization path no longer depending on it.
