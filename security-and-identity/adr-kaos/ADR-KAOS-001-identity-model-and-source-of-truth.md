# ADR-KAOS-001: Identity model and source of truth

**Status**: Accepted, then amended — the `spec.security.id` identity override and its collision/adoption handling were removed. Logical identity is now **always** `kaos://{kind}/{namespace}/{name}`. The original decision is retained below as the historical record; the Amendment section that follows is authoritative where the two differ.

---

## Amendment: identity override removed

The `spec.security.id` override (and the namespace-independent `kaos://{kind}/{id}` form it produced) has been **removed**. Logical identity is always the namespace-scoped default `kaos://{kind}/{namespace}/{name}`, which is unique by construction.

**What changed**

- The CRD `spec.security` surface (`SecuritySpec`/`security.id`) is gone from Agent, MCPServer and ModelAPI.
- The operator-side `pkg/identity` package, including `conflict.go` and the three controller conflict gates, is removed; `AGENT_AUTH_IDENTITY` is now injected inline as `kaos://agent/{namespace}/{name}`.
- The sync projection no longer threads a security id or computes winners/conflicts; both the operator and the sync service derive identity directly from namespace/name and therefore agree by construction with no cross-component resolution to keep in sync.

**Why**

The override's only benefit was identity continuity across a namespace move or rename — speculative for current alpha usage. Because an explicit id is shared by construction, it required collision/adoption resolution (oldest-creationTimestamp wins) implemented twice (operator and sync) that had to agree byte-for-byte on a security-sensitive path. The design also forbade concurrent shared identity (a duplicate marked the younger resource `Failed`), so it did not even serve the most plausible future "shared identity" use case. Removing it deletes every winner/adoption code path on both planes and makes identity trivially unique.

**Deferred design note (shared identity)**

A future "single logical identity intentionally shared across multiple instances or namespaces" capability is out of scope. If it is ever introduced it must be designed to **permit concurrent holders**; the removed oldest-wins model would actively fight that use case and would have to be redesigned regardless, so removing it now burns no useful future foundation. Until then, every Agent/MCPServer/ModelAPI has exactly one identity, derived from its namespace and name.

The original decision text below — first-class `spec.security.id`, the override resolution table, the oldest-wins collision follow-up — is **superseded** by this amendment.

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

The logical identity above is an *identifier* used for grant lookup. It is not, by itself, a way for a workload to **authenticate as itself**. Multi-agent delegation requires that a calling agent prove which agent it is (see [ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md)), so each identity-bearing **caller** (every Agent, and an MCPServer when it calls out) also has a first-class **authentication credential**:

- The agent is registered with **AIB**, which issues it per-agent client credentials (`client_id`/`client_secret`) through its admin API.
- AIB acts as the OAuth2 authorization server for agents: the agent runs a `client_credentials` grant against AIB's token endpoint to obtain a short-lived, AIB-signed **actor token** whose `sub`/`azp` resolves to its KAOS logical identity.
- AIB issues agent identity tokens; **Keycloak/Dex/OIDC remain human-only** (see [ADR-KAOS-004](./ADR-KAOS-004-aib-responsibility-boundary.md) and [ADR-KAOS-000](./ADR-KAOS-000-target-picture.md)).
- Client authentication defaults to the `client_secret` (Argon2id-hashed by AIB); `private_key_jwt` is a stronger option; mTLS/SPIFFE workload binding is out of scope (revisit only on concrete need).

The credential is provisioned by the external sync service into a Kubernetes Secret and **mounted into the pod by the operator** (see [ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md) and [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md)). The trust assumption is possession of the credential, protected by Kubernetes Secret isolation; cryptographic proof that the pod *is* the agent (mTLS/SPIFFE) is out of scope (revisit only on concrete need).

### CRD surface: `spec.security.id` only

`spec.security.id` is the **only** per-resource security field. Authentication and authorization are configured operator-wide (see [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md)), and identity/credentials are auto-provisioned. This is a deliberate design choice: there are **no per-resource `authentication`/`authorization`/public overrides**, so a CRD author cannot weaken the enforced security posture of the cluster. Requested access edges are expressed through existing wiring fields (`spec.mcpServers`, `spec.modelAPI`, `spec.agentNetwork`), not through `spec.security`.

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

For now, do **not** include kubernetes cluster identity in the KAOS logical identity; we currently assume cluster contained identity (as opposed to assuming one AIB that oversees multiple k8s clusters with KAOS installed..

Implication:

- Assume one AIB deployment per KAOS cluster, or at least do not optimize the first identity model for multi-cluster AIB.
- Multi-cluster scoping can be added later with `cluster_id` metadata or an identity prefix if required.

### Grant survival

Grants should survive Agent delete/recreate. This means that when a kaos resource is deleted, the permissions do not get automatically removed.

Implication:

- The logical identity must be stable across delete/recreate.
- Kubernetes UID should not automatically invalidate grants in the initial model.
- UID can still be useful for audit, reconciliation, and detecting replacement, but not as the default grant identity.

Tradeoff:

- This favors usability and continuity over strict lifecycle isolation.
- If a different workload is recreated with the same identity, it may inherit grants. This should be mitigated later through admin controls, ownership metadata, or optional workload identity.

### ServiceAccounts

Exclude ServiceAccounts from the initial implementation; workload/agent identity is provided by AIB integration, see [ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md).

Implication:

- The first implementation should not require Kubernetes ServiceAccount token validation or workload identity binding.
- ServiceAccounts are out of scope; agent identity comes from AIB integration (see [ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md)).
- SPIFFE/SPIRE is out of scope; revisited only if a concrete workload-attestation requirement appears.

### Identity-bearing resource types

Keep Agent, MCPServer, and ModelAPI in the target identity model for now.

Implication:

- Treat all three as KAOS-managed service identities conceptually.
- [ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md) enforces Agent, MCPServer, and ModelAPI access at the gateway, while leaving ModelAPI model/budget internals to LiteLLM.

### CRD surface

Start with first-class spec fields, not annotations. Use `spec.security.<values>` as the target CRD surface rather than a standalone `spec.identity` section.

Implication:

- The target picture may propose a `spec.security` section.
- Initial implementation can still be phased, but the target contract should be schema-backed and documented.

### KAOS/AIB synchronization

Use a separate simple sync service, not KAOS operator push logic. See [ADR-KAOS-008](./ADR-KAOS-008-aib-integration-and-synchronization-architecture.md).

Implication:

- Kubernetes/KAOS remains authoritative for resources.
- A separate microservice watches KAOS CRDs and reconciles AIB records.
- This avoids coupling the operator reconciliation loop to AIB APIs and keeps the bridge replaceable.

### Workload verification for token exchange

Distinguish **agent authentication** from **workload (pod) identity verification**. Agent authentication *is* required: a caller must present its AIB-issued actor token (obtained via `client_credentials` using its per-agent client credential) for the gateway and AIB token exchange to act on it. What is **out of scope** is cryptographically verifying that the *pod* running the workload is bound to that identity (Kubernetes ServiceAccount / SPIFFE attestation).

Implication:

- AIB token exchange trusts the verified agent actor token and user subject token; it does not additionally validate a ServiceAccount/SPIFFE workload attestation.
- The trust assumption is **possession** of the agent credential, protected by Kubernetes Secret isolation and NetworkPolicy.
- Cryptographic pod-to-identity binding (mTLS/SPIFFE) is out of scope and revisited only on concrete need (see [ADR-KAOS-002](./ADR-KAOS-002-enforcement-topology.md)).

### Autonomous run identity

Keep autonomous identity simple for now.

Implication:

- Autonomous runs use Agent identity plus run/session correlation initially.
- Run-bound grants or run-scoped identities are deferred beyond the [ADR-KAOS-006](./ADR-KAOS-006-re-authentication-execution-model.md) approval/consent model.

## Consequences

- KAOS resources have a first-class `spec.security.id`, which is the only per-resource security field.
- If omitted, identity defaults to kind/namespace/name.
- AIB `external_id` uses the resolved KAOS logical identity.
- Each identity-bearing caller additionally has an AIB-issued per-agent authentication credential so it can authenticate as itself (the actor) for delegation; Keycloak stays human-only.
- A separate KAOS-AIB sync service reconciles KAOS resources into AIB records and provisions per-agent credentials into Secrets; the operator mounts them into pods.
- Grants survive delete/recreate when the resolved logical identity is the same.
- ServiceAccounts and SPIFFE/mTLS workload binding are out of scope (revisit only on concrete need).
- Agent, MCPServer, and ModelAPI remain in the identity target picture. [ADR-KAOS-009](./ADR-KAOS-009-gateway-api-resource-boundary-enforcement.md) uses those identities for gateway-enforced access decisions.
- Autonomous run identity remains Agent-level plus correlation for now (actor-only, no user subject).

## Follow-up

Collision/adoption handling for explicit `spec.security.id` values must be specified before implementation. The target behavior is to reject duplicate active identities per kind and allow adoption only when the previous resource no longer exists.
