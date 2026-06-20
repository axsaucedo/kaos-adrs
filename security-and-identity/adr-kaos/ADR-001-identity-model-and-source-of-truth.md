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
- ADR-002 keeps Agent and MCPServer enforcement SDK-native in the baseline profile, and treats ModelAPI root access as AIB-manageable while leaving model/budget internals to LiteLLM.

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

- KAOS resources have a first-class `spec.security.id`.
- If omitted, identity defaults to kind/namespace/name.
- AIB `external_id` uses the resolved KAOS logical identity.
- A separate KAOS-AIB sync service reconciles KAOS resources into AIB records.
- Grants survive delete/recreate when the resolved logical identity is the same.
- ServiceAccounts are excluded from initial implementation.
- Workload verification is deferred.
- Agent, MCPServer, and ModelAPI remain in the identity target picture. ADR-002 uses those identities for SDK-native Agent/MCPServer enforcement and ModelAPI root access decisions.
- Autonomous run identity remains Agent-level plus correlation for now.

## Follow-up

Collision/adoption handling for explicit `spec.security.id` values must be specified before implementation. The target behavior is to reject duplicate active identities per kind and allow adoption only when the previous resource no longer exists.
