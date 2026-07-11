# ADR 0003 — Authorization model and data schema: user + agent + resource

**Status**: Proposed
**Date**: 2026-07-11
**Depends on**: [ADR 0001](./adr_0001_enforcement-topology-pdp-and-policy-delivery.md) (the PDP evaluates this model), [ADR 0002](./adr_0002_agent-identity-issuers-and-aib-boundary.md) (issuers and identity mapping)
**Research**: [003](../research/003-user-agent-resource-authz-gap.md), [005](../research/005-control-plane-pdp-and-relationship-model.md)

## Context

Phase 1's implemented authorization is actor-only: `data.kaos.grants` maps agent → resources, and the subject (user) token, though parsed into the policy input, is never consulted ([research/003](../research/003-user-agent-resource-authz-gap.md)). This ADR decides the full user + agent + resource model: what facts constitute a decision, how the user dimension enters it, and the `data.kaos.*` schema that carries the facts.

Two implementation facts shape the model:

- **Subject propagation already exists.** The pais propagation SDK (`pydantic-ai-server/aib/instrument.py`) extracts the inbound user subject (principal + `Authorization` bearer) into a request-local context and forwards it unchanged on every outbound call, while the actor is always the local agent's own token — each hop authenticates as itself. Internal hops in a user-initiated chain therefore carry the user token today; the design does not need to build propagation, only to give the propagated subject semantics.
- **Autonomy is already declared in the CRD.** `Agent.spec.autonomous` (`operator/api/v1alpha1/agent_types.go`) activates self-looping execution. An autonomous agent's loop runs in-process — it receives no inbound request; all traffic it generates is outbound internal hops. Which agents legitimately originate subject-less work is thus already a declarative, reviewable fact the projection can compile.

Entry vs internal traffic: entry requests (a user or external system calling an agent) arrive on the gateway's externally exposed routes carrying a subject token and **no actor token**; internal hops (agent → MCP/model/peer, routed through the gateway's cluster-internal address by `gatewayRouting`) always carry an actor token. The classification is by construction — the internal address is a ClusterIP only resolvable and routable in-cluster (the standard north-south vs east-west split: Kubernetes Service vs Ingress, Istio ingress vs east-west gateway, internal vs internet-facing cloud LBs) — and it is backed by two independent signals: the route/listener the request arrived on, and the token shape (actor absent = entry). Network reachability is the classifier, not the security: each route's own token-and-grant requirements are enforced regardless of provenance, and NetworkPolicy (with `strictGatewayApi`) keeps the gateway the only application path, so nothing opts out of classification. The operator generates all routes, so "every externally attached route carries the entry policy" is a CI-testable invariant rather than a runtime detection problem.

## Options considered (source of the user dimension)

1. **`AccessGrant` CRD referencing IdP groups (chosen)** — a small namespaced CRD binding subjects (a user `sub`/email, or an IdP group reference) to resources. The edge is declarative, GitOps-reviewable, and cluster-RBAC-protected, while membership is administered in the IdP UI and arrives as a token claim — the Kubernetes RoleBinding shape (subjects from an external IdP, binding in-cluster), which Istio `AuthorizationPolicy` claim conditions and agentgateway's CEL-over-claims rules also mirror.
2. **Keycloak claims as the grant itself** — user→agent facts as roles/groups in the subject token only, zero KAOS storage. Rejected as the primary source: grant administration moves entirely into the IdP (the policy-in-IdP direction already rejected), grants stop being GitOps-reviewable, and `kaos-internal` (no IdP) could never express user grants.
3. **KAOS-owned user-grant data via manual modes** — a user dimension authored directly in the data document. Remains available (the manual/bring-your-own modes carry over) but is not the primary interface; the CRD compiles to exactly this.
4. **UserGrant-shaped schema (fork model)** — adopt the fork access-check model's fields (per-grant expiry, resource subsets, independent deny reasons). The *conjunction shape* is adopted (platform grant on the actor AND subject condition, independently deniable — [research/003](../research/003-user-agent-resource-authz-gap.md)); the extra fields are deferred (below).

## Decision

### 1. A subject is always required — there is no subject-less traffic

Every request on protected routes must carry a verifiable subject. No subject = deny, in every posture. G1's "autonomous gap" is not resolved by a configurable stance but eliminated: the case does not exist.

This is made possible by **autonomous self-subjecting**: when an agent's autonomous loop starts, the runtime seeds the propagation context's subject slot with the agent's **own actor token**. The subject of autonomous work is the agent itself — which is accurate: the agent is the principal on whose behalf the work happens. Consequently:

- Subject is a **user** identity → the user plane rules apply (below).
- Subject is an **agent** identity → allowed only if that agent has `spec.autonomous` set, a fact the projection compiles from the CRD into policy data. An agent self-subjecting without the flag is denied — autonomy is an explicit, PDP-enforced authorization declared in a reviewable spec, not an ambient capability. A compromised agent cannot fake it: the policy checks the CRD-projected flag, not the token's claims, and an agent never possesses another agent's actor token to replay into the subject slot.
- The resulting invariant: **the only way traffic flows without a user token is an autonomous-enabled agent passing its own token as the subject.**

### 2. Where each check applies: user grants gate entry, agent grants gate movement

- **Entry edge** (subject present, actor absent; externally attached route): the subject must be a user with an `AccessGrant` covering the target agent. This is where the user dimension is *authorized*.
- **Internal hops** (actor present): authorization is the actor's agent-grant (`resource_id in data.kaos.grants[actor_id]` — the phase-1 rule, unchanged). The propagated subject is required and signature-verified, and is recorded for attribution, but the subject does **not** need an `AccessGrant` to every downstream resource: granting a user access to an agent implies trusting that agent's declared wiring. Per-user *downstream* semantics are explicitly deferred (below).
- The rego conjunction per hop is therefore: valid subject (user, or autonomous-flagged agent) AND the hop-appropriate grant (AccessGrant at entry, agent-grant internally).

### 3. The `AccessGrant` CRD

Namespaced (the RoleBinding analogy: a namespace admin grants access to their own namespace's resources without cluster-wide rights; a cluster-scoped analogue is a later addition if cross-namespace need appears). Subjects are `User` (matches `sub`/email claim) or `Group` (matches a `groups` claim entry); resources are explicit references or a label selector, compiled to `kaos://` ids:

```yaml
apiVersion: kaos.tools/v1alpha1
kind: AccessGrant
metadata:
  name: researchers-use-research-stack
  namespace: team-a
spec:
  subjects:
    - kind: Group
      name: /engineering/researchers   # Keycloak group; arrives as "groups" claim
    - kind: User
      name: alice@corp.example
  resources:
    - kind: Agent
      name: researcher                 # → kaos://agent/team-a/researcher
    - kind: MCPServer
      name: papers-db
```

Scale property: grants scale with **groups × resource-sets, not users** — membership churn happens in the IdP with zero cluster changes, so a 500-person org with a handful of functional groups is tens of AccessGrants, not thousands. The explosion case (per-user × per-resource tuples) is the documented trigger for the ReBAC growth path (SpiceDB/OpenFGA), not something pre-built for.

**Without a user IdP** (e.g. `kaos-internal`): AccessGrants are accepted but marked unenforced — status condition `Enforced=False`, `reason=NoUserIdentityProvider`, warning event; the compiler skips user-subject grants. No admission webhook (extra component; breaks GitOps dry-runs). Enabling the user plane flips the same objects to enforced on the next reconcile. Declared-but-silently-ignored is the one forbidden state.

### 4. Group claims are provisioned, not assumed

Keycloak does not emit a `groups` claim by default — it requires a Group Membership protocol mapper on the client. A missing mapper means every `Group` subject silently never matches: valid tokens, correct PDP, all group grants deny — exactly the silent-failure state this design forbids. Therefore: the KAOS chart **provisions the mapper** in the presets that provision Keycloak (it already creates the realm and client), and bring-your-own-Keycloak documentation states the mapper as a hard requirement.

### 5. Granularity: resource-level

Grants target whole resources (`kaos://mcp/ns/name`), matching the enforcement point's visibility (ext_authz sees headers, not MCP payloads). Tool/route-level authorization (which agentgateway demonstrates at the gateway via MCP tool names) is a schema-compatible later extension — the grant lists gain an optional field; it is not designed now because it requires payload-inspection capability at the PEP that ext_authz-on-headers does not have.

### 6. Schema: `data.kaos.*` extended, published contract preserved

- `data.kaos.grants` — unchanged (actor → resource ids).
- `data.kaos.user_grants` — new: compiled from AccessGrants, keyed by subject matcher, e.g. `{"group:/engineering/researchers": ["kaos://agent/team-a/researcher", ...], "user:alice@corp.example": [...]}`.
- `data.kaos.agents` — new: per-agent facts from the CRD, initially `{"kaos://agent/<ns>/<name>": {autonomous: true|false, issuer_sub: "<sub>"}}` (the latter carrying ADR 0002's identity mapping, e.g. `system:serviceaccount:<ns>:<name>`).
- `data.kaos.jwks` — unchanged in meaning; multi-issuer per ADR 0002.

Existing keys keep their semantics; consumers of the published contract are unaffected unless they opt into the new keys.

### 7. Deferred — explicitly unsupported until revisited

- **Per-user downstream authorization** ("Bob may use agent A, but A may not touch MCP Y *for Bob*"; per-user data scoping inside a shared MCP; per-user downstream quotas): the subject is present and logged at every hop, so audit attribution works, but the authorization decision on internal hops does not consult per-user grants. The proper solution for per-user downstream *access* is scoped token exchange — ADR 0004's subject and one of its re-entry triggers. A header-level per-user-downstream rego rule remains cheap to add later precisely because the subject already reaches every hop.
- **Grant expiry / time-boxing** (the fork model's `ValidUntil`): revocation is deleting the AccessGrant (or the GitOps PR that removes it). One optional field plus a rego time check later if contractor/break-glass patterns demand it.
- **Tool-level granularity** (per §5).

## Consequences

- **G1 is closed semantically as well as topologically**: ADR 0001 made evaluation unconditional; this ADR makes the no-subject case a uniform deny rather than a configurable stance. There is no flag to get wrong.
- **A small runtime change**: seeding the subject slot at autonomous-loop start (the propagation SDK already handles everything else). A2A async tasks (`taskConfig`) triggered by a caller carry that caller's subject via existing propagation.
- **New operator surface**: the AccessGrant CRD + its compiler into `user_grants`, the `Enforced` status condition, and the Keycloak group mapper in chart provisioning.
- **Verification surface widens slightly**: the subject slot must accept agent-issuer tokens (autonomous case) — already supported by ADR 0002's multi-issuer `data.kaos.jwks`.
- **Honest limits are documented**: the user dimension is enforced at the entry edge; downstream hops are agent-plane with subject attribution. The deferred list above is the published "does not support" statement.
- **Migration from phase 1**: the static rego is replaced (subject-required conjunction instead of actor-only), `data.json` gains three keys, and no header plumbing changes.
