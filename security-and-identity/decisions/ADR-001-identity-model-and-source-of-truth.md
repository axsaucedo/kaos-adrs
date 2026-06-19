# ADR-001: Identity model and source of truth

## Status

Proposed, pending final host decision on logical identity format.

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

## Accepted constraints from host

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
- Revisit after enforcement topology decisions, because sidecar/Gateway/native enforcement choices may change how useful MCPServer/ModelAPI identities are in the first implementation.

### CRD surface

Start with first-class spec fields, not annotations.

Implication:

- The target picture may propose a `spec.identity` or similar section.
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
- Run-bound grants or run-scoped identities are deferred to approval/consent research.

## Open question: logical identity format

The main unresolved point is whether KAOS logical identity should be derived from namespace/name, generated as a UUID, or user-configurable.

This matters because grants are intended to survive delete/recreate and because the host may want the same logical identifier to be usable across namespaces.

## Options for logical identity

### Option A: namespace/name-derived URI

Example:

```text
kaos://agent/default/researcher
kaos://mcp/default/github-tools
kaos://modelapi/default/openai
```

Pros:

- Very simple.
- Easy to understand and debug.
- Directly maps to Kubernetes resources.
- No generated identifiers or extra admission/defaulting logic.
- Good for GitOps and declarative YAML.

Cons:

- Identity changes if the resource moves namespaces.
- The same logical agent in another namespace gets a different identity.
- Grants survive delete/recreate by name, which is convenient but can be unsafe if names are reused.
- Does not satisfy the use case where the host wants one logical identifier shared across namespaces.

Best fit:

- Single namespace or namespace-as-security-boundary deployments.
- Users expect grants/policy to be tied to the Kubernetes resource location.

### Option B: user-configurable stable logical ID with namespace/name default

Example CRD shape:

```yaml
spec:
  identity:
    id: researcher
```

External identity:

```text
kaos://agent/researcher
```

If omitted, default could be:

```text
kaos://agent/default/researcher
```

Pros:

- Keeps the simple namespace/name default.
- Allows users to intentionally share a logical identity across namespaces.
- Supports stable grant identity across resource moves/recreates.
- Good for teams that treat namespace as environment or deployment location rather than identity boundary.
- Keeps the identity human-readable.

Cons:

- Requires uniqueness and collision rules.
- If two resources use the same identity, they may share grants/policy intentionally or accidentally.
- Needs validation/defaulting behavior.
- The system must define whether `spec.identity.id` is global per kind, per namespace, or allowed to alias multiple resources.

Best fit:

- Flexible KAOS target picture where identity can be decoupled from Kubernetes placement.
- Likely the best fit for the host's stated concern.

Key design choice inside this option:

| Variant | Meaning | Tradeoff |
|---|---|---|
| Global per kind | `kaos://agent/researcher` must be unique across namespaces | Prevents accidental sharing but blocks same identity in multiple namespaces |
| Shared alias allowed | Multiple resources can intentionally use `researcher` | Enables portability but must be treated as a powerful trust decision |
| Scoped plus alias | Resource has unique identity and optional alias/group | More precise but more complex |

### Option C: generated KAOS UUID stored in spec

Example:

```yaml
spec:
  identity:
    id: 4efc3a8b-...
```

External identity:

```text
kaos://agent/4efc3a8b-...
```

Pros:

- Collision-resistant.
- Namespace-independent.
- Grants naturally survive namespace moves if the ID is preserved.
- Avoids name reuse ambiguity if users preserve IDs deliberately.

Cons:

- Poor UX and audit readability.
- Requires generation/defaulting, likely via webhook or CLI.
- If generated on create and resource is deleted/recreated from YAML without the ID, grants will not survive.
- GitOps workflows dislike server-mutated spec fields unless carefully handled.
- Users still need to manage/copy the UUID if they want continuity.

Best fit:

- Systems that prioritize opaque stable identity over human readability.
- Less ideal for KAOS unless paired with display names/aliases.

### Option D: generated KAOS UUID stored in status

Pros:

- Does not mutate user spec.
- Clean separation between desired spec and assigned identity.

Cons:

- Does not survive delete/recreate unless copied elsewhere.
- Bad fit with the host requirement that grants survive.
- Harder for users to declaratively control.

Assessment:

- Not recommended for this decision.

### Option E: AIB UUID as primary identity

Pros:

- Directly matches AIB grant model.
- No separate AIB mapping needed after registration.

Cons:

- Makes AIB authoritative for KAOS resource identity.
- Bad Kubernetes UX.
- Harder to recover/reconcile if AIB state is rebuilt.
- Couples KAOS YAML to AIB internals.

Assessment:

- Not recommended as the KAOS logical identity.

## Recommended resolution for Q1

Use a first-class, user-configurable KAOS logical identity with a simple default.

Proposed model:

```yaml
spec:
  identity:
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

However, this requires a policy for collisions/aliases.

The safest initial rule is:

```text
spec.identity.id must be unique per resource kind within a KAOS cluster.
```

If users want the same logical identity across namespaces, that means they are intentionally representing the same identity. This should either:

1. be allowed only if the old resource no longer exists, or
2. require an explicit shared-identity/adoption flag later.

## Remaining host choice

Choose one of these Q1 variants:

### Q1-A: Simple namespace/name identity

Use:

```text
kaos://{kind}/{namespace}/{name}
```

Best if namespace should remain part of identity.

### Q1-B: User-configurable identity with namespace/name default

Use:

```text
spec.identity.id: researcher
external_id: kaos://agent/researcher
```

Default:

```text
kaos://agent/{namespace}/{name}
```

Best if users may want namespace-independent identities.

### Q1-C: Generated UUID identity

Use:

```text
spec.identity.id: <uuid>
external_id: kaos://agent/<uuid>
```

Best if opaque uniqueness matters more than readability.

## Current preferred answer

Prefer **Q1-B: user-configurable identity with namespace/name default**.

This best matches:

- grant survival,
- no cluster identity for now,
- first-class spec fields,
- AIB `external_id` mapping,
- host concern that users may want the same logical identifier in different namespaces.

## Resulting provisional ADR

If Q1-B is accepted:

1. KAOS resources have a first-class `spec.identity.id`.
2. If omitted, identity defaults to kind/namespace/name.
3. AIB `external_id` uses the resolved KAOS logical identity.
4. A separate KAOS-AIB sync service reconciles KAOS resources into AIB records.
5. Grants survive delete/recreate when the resolved logical identity is the same.
6. ServiceAccounts are excluded from initial implementation.
7. Workload verification is deferred.
8. Agent, MCPServer, and ModelAPI remain in the identity target picture, subject to later enforcement-topology validation.
9. Autonomous run identity remains Agent-level plus correlation for now.

## Decision status

Pending host answer on Q1 variant.
