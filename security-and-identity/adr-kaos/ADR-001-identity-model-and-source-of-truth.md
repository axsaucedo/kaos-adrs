# ADR-001: Identity model and source of truth

**Status**: Accepted

---

## Decision

Use a first-class, user-configurable KAOS security identity through `spec.security.id`, with a simple namespace/name default when no explicit ID is provided.

Resolved identity format:

| Case | Resolved external identity |
|---|---|
| `spec.security.id` omitted | `kaos://{kind}/{namespace}/{name}` |
| `spec.security.id` provided | `kaos://{kind}/{id}` |

Examples:

```yaml
# Default identity
apiVersion: kaos.tools/v1alpha1
kind: Agent
metadata:
  namespace: default
  name: researcher
```

resolves to:

```text
kaos://agent/default/researcher
```

```yaml
# Explicit stable identity
apiVersion: kaos.tools/v1alpha1
kind: Agent
metadata:
  namespace: staging
  name: researcher-v2
spec:
  security:
    id: researcher
```

resolves to:

```text
kaos://agent/researcher
```

This allows users to keep the default Kubernetes namespace/name identity when they do not care about a separate stable security identity, while also allowing namespace-independent grant continuity when `spec.security.id` is explicitly set.

Target CRD model:

```yaml
spec:
  security:
    id: researcher
```

External AIB identity:

```text
kaos://agent/researcher
```

Default if omitted:

```text
kaos://agent/{namespace}/{name}
```

This gives:

- simple defaults,
- user-controlled continuity,
- namespace-independent identity when desired,
- grant survival across delete/recreate,
- human-readable IDs,
- a clean value for AIB `external_id`.

Explicit `spec.security.id` values should be unique per resource kind within a KAOS cluster unless a future shared-identity/adoption feature is explicitly introduced.

If users want the same logical identity across namespaces, that means they are intentionally representing the same security identity. The initial implementation should prevent accidental active duplicates and only allow safe adoption when the previous resource no longer exists.

This matches:

- grant survival,
- no cluster identity for now,
- first-class spec fields,
- AIB `external_id` mapping,
- the requirement that users may intentionally reuse the same logical identifier across namespaces.

### Per-agent authentication identity (AIB-issued)

The logical identity above is an *identifier* used for grant lookup. It is not, by itself, a way for
a workload to **authenticate as itself**. Multi-agent delegation requires that a calling agent prove
which agent it is (see ADR-004), so each identity-bearing **caller** (every Agent, and an MCPServer
when it calls out) also has a first-class **authentication credential**:

- The agent is registered with **AIB**, which issues it per-agent client credentials
  (`client_id`/`client_secret`) through its admin API.
- AIB acts as the OAuth2 authorization server for agents: the agent runs a `client_credentials` grant
  against AIB's token endpoint to obtain a short-lived, AIB-signed **actor token** whose `sub`/`azp`
  resolves to its KAOS logical identity.
- AIB issues agent identity tokens; **Keycloak/Dex/OIDC remain human-only** (see ADR-004 and ADR-000).
- Client authentication defaults to the `client_secret` (Argon2id-hashed by AIB); `private_key_jwt`
  is a stronger option; mTLS/SPIFFE workload binding remains future hardening.

The credential is provisioned by the external sync service into a Kubernetes Secret and **mounted into
the pod by the operator** (see ADR-010 and ADR-011). The trust assumption is possession of the
credential, protected by Kubernetes Secret isolation; cryptographic proof that the pod *is* the agent
(mTLS/SPIFFE) is deferred future hardening.

### CRD surface: `spec.security.id` only

`spec.security.id` is the **only** per-resource security field. Authentication and authorization are
configured operator-wide (see ADR-011), and identity/credentials are auto-provisioned. This is a
deliberate design choice: there are **no per-resource `authentication`/`authorization`/public
overrides**, so a CRD author cannot weaken the enforced security posture of the cluster. Requested
access edges are expressed through existing wiring fields (`spec.mcpServers`, `spec.modelAPI`,
`spec.agentNetwork`), not through `spec.security`.

## Context

KAOS resources are Kubernetes CRDs and already have Kubernetes object identity:

- kind
- namespace
- name
- UID
- labels/annotations
- lifecycle state

AIB has its own internal UUID-backed `AgentID`, `ServiceID`, `GrantID`, `PermissionSetID`, and other typed IDs. AIB also has string-backed `ExternalID`, intended for an external governance/system identifier.

KAOS needs a target identity model that keeps Kubernetes authoritative for resource existence/topology, lets AIB own grants/consent/token exchange, and avoids overcomplicating the first implementation.

## Accepted constraints

### Cluster identity

For now, do **not** include cluster identity in the KAOS logical identity.

Implication:

- Assume one AIB deployment per KAOS cluster, or at least do not optimize the first identity model for multi-cluster AIB.
- Multi-cluster scoping can be added later with `cluster_id` metadata or an identity prefix if required.

### Grant survival

Grants should survive Agent delete/recreate.

Implication:

- The logical identity must be stable across delete/recreate.
- Kubernetes UID should not automatically invalidate grants in the initial model.
- UID can still be useful for audit, reconciliation, and detecting replacement, but not as the default grant identity.

Tradeoff:

- This favors usability and continuity over strict lifecycle isolation.
- If a different workload is recreated with the same identity, it may inherit grants. This should be mitigated later through admin controls, ownership metadata, or optional workload identity.

### ServiceAccounts

Exclude ServiceAccounts from the initial implementation.

Implication:

- The first implementation should not require Kubernetes ServiceAccount token validation or workload identity binding.
- ServiceAccounts remain a future production hardening path.
- SPIFFE/SPIRE remains an even later advanced option.

### Identity-bearing resource types

Keep Agent, MCPServer, and ModelAPI in the target identity model for now.

Implication:

- Treat all three as KAOS-managed service identities conceptually.
- ADR-002 enforces Agent, MCPServer, and ModelAPI access at the gateway, while leaving ModelAPI model/budget internals to LiteLLM.

### CRD surface

Start with first-class spec fields, not annotations. Use `spec.security.<values>` as the target CRD surface rather than a standalone `spec.identity` section.

Implication:

- The target picture may propose a `spec.security` section.
- Initial implementation can still be phased, but the target contract should be schema-backed and documented.

### KAOS/AIB synchronization

Use a separate simple sync service, not KAOS operator push logic.

Implication:

- Kubernetes/KAOS remains authoritative for resources.
- A separate microservice watches KAOS CRDs and reconciles AIB records.
- This avoids coupling the operator reconciliation loop to AIB APIs and keeps the bridge replaceable.

### Workload verification for token exchange

Do not require workload identity verification for AIB token exchange initially.

Implication:

- Initial AIB flow can trust the relevant subject/client token model without additionally validating a ServiceAccount/SPIFFE identity.
- Workload binding can be added later.

### Autonomous run identity

Keep autonomous identity simple for now.

Implication:

- Autonomous runs use Agent identity plus run/session correlation initially.
- Run-bound grants or run-scoped identities are deferred beyond the ADR-006 approval/consent model.

## Consequences

- KAOS resources have a first-class `spec.security.id`, which is the only per-resource security field.
- If omitted, identity defaults to kind/namespace/name.
- AIB `external_id` uses the resolved KAOS logical identity.
- Each identity-bearing caller additionally has an AIB-issued per-agent authentication credential so it can authenticate as itself (the actor) for delegation; Keycloak stays human-only.
- A separate KAOS-AIB sync service reconciles KAOS resources into AIB records and provisions per-agent credentials into Secrets; the operator mounts them into pods.
- Grants survive delete/recreate when the resolved logical identity is the same.
- ServiceAccounts and SPIFFE/mTLS workload binding are deferred future hardening.
- Agent, MCPServer, and ModelAPI remain in the identity target picture. ADR-011 uses those identities for gateway-enforced access decisions.
- Autonomous run identity remains Agent-level plus correlation for now (actor-only, no user subject).

## Follow-up

Collision/adoption handling for explicit `spec.security.id` values must be specified before implementation. The target behavior is to reject duplicate active identities per kind and allow adoption only when the previous resource no longer exists.
