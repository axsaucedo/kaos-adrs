# 007 - Decision 1 research: identity model and source of truth

## Prompt

Ok all clear. Let's move to the research, and let's start with the 1st. Provide me with the research, includng questions that require answer from me (host) which can include pros/cons / tradeoffs from each options, etc, whcih should be complete to then make a decision for the section.

## Response

## Decision area

Identity model and source of truth.

This section answers:

- What identities exist in the KAOS + AIB target picture?
- Which system owns each identity?
- How should KAOS logical resources map to AIB records?
- Whether ServiceAccounts/workload identity are required initially.
- What needs host decision before finalizing the target picture.

This is not yet the final decision. It is the evidence-backed research package for the host decision.

## Source facts from KAOS

### KAOS resources already have Kubernetes identity

Source files:

- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

KAOS resources are Kubernetes CRDs and therefore already have:

- `metadata.namespace`
- `metadata.name`
- `metadata.uid`
- labels and annotations
- creation/deletion lifecycle

Current CRD-level identity/security fields:

| Resource | Current first-class identity/security fields |
|---|---|
| `Agent` | No `spec.identity`; no `spec.serviceAccountName`; has `spec.agentNetwork`, `spec.mcpServers`, `spec.modelAPI`, `spec.container`, `spec.podSpec` |
| `MCPServer` | Has `spec.serviceAccountName`; no `spec.identity`; has `spec.container`, `spec.podSpec`, `spec.gatewayRoute` |
| `ModelAPI` | No `spec.identity`; no `spec.serviceAccountName`; has `spec.container`, `spec.podSpec`, `spec.gatewayRoute` |

Implication:

- `namespace/name` is already a natural human-facing logical identifier.
- `metadata.uid` is the safe lifecycle identifier.
- There is not yet a uniform KAOS identity section across Agent, MCPServer, and ModelAPI.

### KAOS runtime receives partial identity only

Source files:

- `operator/controllers/agent_controller.go`
- `pydantic-ai-server/pais/serverutils.py`
- `pydantic-ai-server/pais/server.py`

The Agent controller injects:

- `AGENT_NAME`
- model endpoint/model name
- MCP server names and direct URLs
- peer agent names and direct URLs
- autonomous/task/memory config

It does not currently inject:

- namespace
- resource UID
- cluster identity
- service account identity
- AIB agent ID
- AIB external ID
- user/request principal
- run/security context

Implication:

- KAOS logical identity exists in Kubernetes, but runtime identity is currently only `AGENT_NAME`.
- If runtime needs to create signed requests, token exchange requests, audit events, or approval requests, it will need more identity metadata.

### KAOS MCPServer has explicit ServiceAccount support; Agent and ModelAPI rely on podSpec override

Source files:

- `operator/api/v1alpha1/mcpserver_types.go`
- `operator/controllers/mcpserver_controller.go`
- `operator/api/v1alpha1/agent_types.go`
- `operator/api/v1alpha1/modelapi_types.go`

MCPServer has:

- `spec.serviceAccountName`

Agent and ModelAPI do not have first-class `serviceAccountName`, but both expose:

- `spec.podSpec`

Implication:

- Workload identity via Kubernetes ServiceAccount is already easiest for MCPServer.
- Agent/ModelAPI can technically use ServiceAccounts today through podSpec override, but this is not ergonomic or uniform.
- A target picture can either keep ServiceAccount optional/advanced or introduce a uniform `spec.identity`/`spec.security` section later.

### KAOS Gateway identity is path-based, not security-based

Source files:

- `operator/pkg/gateway/gateway.go`
- `operator/controllers/agent_controller.go`
- `operator/controllers/mcpserver_controller.go`

Gateway paths use:

```text
/{namespace}/{resourceType}/{resourceName}
```

with resource types:

- `agent`
- `modelapi`
- `mcp`

Implication:

- KAOS already has a route identity for externally reachable resources.
- This route identity is not currently tied to authn/authz policy.
- It could become a useful protected resource URI or route key, but should not be confused with workload identity.

### KAOS task/run identity is not yet security-grade

Source files:

- `pydantic-ai-server/pais/a2a.py`
- `pydantic-ai-server/pais/server.py`

Current task/session identifiers:

- Memory session IDs from `X-Session-ID` or generated session IDs.
- A2A task IDs like `task_<random>`.
- Autonomous startup tasks with metadata `{"trigger":"startup"}`.

Implication:

- KAOS has correlation IDs, but not security identities for runs.
- Autonomous runs may need explicit run identity or grant binding later, but this is separate from CRD/workload identity.

## Source facts from AIB

### AIB has internal UUID-backed entity IDs

Source files:

- `agentic-identity-broker/internal/domain/id/uuid_ids_gen.go`
- `agentic-identity-broker/internal/domain/id/string_ids.go`

AIB typed IDs include:

- `AgentID`
- `ServiceID`
- `GrantID`
- `SessionID`
- `PermissionSetID`
- `CredentialID`
- `SigningKeyID`

These are UUID-backed, except string-backed types such as:

- `ClientID`
- `ExternalID`
- `Principal`
- `KeyID`

Implication:

- AIB's primary agent identity is an internal UUID, not KAOS `namespace/name`.
- `ExternalID` is the intended bridge for an external governance/system identifier.

### AIB Agent model can store an external KAOS identity

Source file:

- `agentic-identity-broker/internal/domain/storage/agent.go`

AIB Agent fields include:

- `ID` as internal UUID.
- optional `ClientID`.
- optional `ExternalID`.
- display name and description.
- governance/documentation/interface URLs.
- service requirements.
- permission set associations.
- redirect URIs.
- allowed scopes.
- client metadata document URIs.

Implication:

- KAOS resource identity should probably map to AIB `external_id`, while AIB keeps its internal UUID.
- AIB grants and token exchange currently operate on AIB internal Agent UUID.
- Token claims may need to carry either AIB UUID directly or a KAOS identity that AIB resolves to UUID.

### AIB grants bind user principal to AIB Agent UUID

Source file:

- `agentic-identity-broker/internal/domain/storage/user_grant.go`

User grants include:

- `Principal`
- `AgentID`
- optional `ValidUntil`
- granted permission set entries

Implication:

- User consent is granted to an AIB agent record.
- If KAOS delete/recreates an Agent with the same `namespace/name`, the architecture must decide whether old grants survive or are invalidated.
- This is exactly why `namespace/name` alone is risky as the only durable identity.

### AIB token exchange extracts principal and agent ID from claims

Source files:

- `agentic-identity-broker/internal/domain/tokenexchange/cel_evaluator.go`
- `agentic-identity-broker/internal/domain/tokenexchange/service.go`

AIB token exchange uses CEL to extract:

- principal from subject token claims
- agent ID from subject token claims

The service expects the extracted agent ID to resolve to an AIB Agent UUID, unless configured to resolve by client ID in some modes.

Implication:

- The KAOS/AIB target picture must define token claims precisely.
- AIB can be adapted by configuration if claims carry an AIB UUID, or by extension if claims carry KAOS identity.
- Long term, a KAOS identity watcher/reconciler can maintain AIB records and mapping.

## External security facts

### Kubernetes ServiceAccounts are workload identities

External references:

- Kubernetes Service Accounts concept docs.
- Kubernetes Service Account administration docs.

Relevant facts:

- A ServiceAccount is a non-human account that provides a distinct identity for application processes running in Pods.
- ServiceAccounts are namespaced.
- ServiceAccounts are separate from human user accounts.
- ServiceAccount tokens can be bound to objects such as Pods.
- Bound tokens include private claims such as bound object name and UID.
- TokenReview can validate tokens and reveal authenticated identity and bound-object metadata.

Implication:

- ServiceAccounts are the Kubernetes-native way to identify workloads.
- They are stronger than trusting a pod environment variable that says `AGENT_NAME=foo`.
- They are still not the same as KAOS logical identity; they are runtime/workload identity.

### SPIFFE/SPIRE is a stronger workload identity framework, but heavier

External reference:

- SPIFFE overview.

Relevant facts:

- SPIFFE defines workload identities and short-lived identity documents called SVIDs.
- Workloads can authenticate using X.509 SVIDs or JWT SVIDs.
- SPIFFE is useful in dynamic distributed systems and supports heterogeneous environments.
- SPIRE, Istio, cert-manager, and others implement parts of this ecosystem.

Implication:

- SPIFFE/SPIRE or service mesh identity could be a future advanced option.
- It is likely too heavy as a mandatory first KAOS security dependency unless target users already run a mesh.

## Identity categories for KAOS target picture

The architecture should separate these identities:

| Identity | Meaning | Candidate owner | Example |
|---|---|---|---|
| Logical KAOS resource identity | The declarative resource users/admins reason about | Kubernetes/KAOS | `kaos://agent/default/researcher` |
| Lifecycle identity | The exact Kubernetes object incarnation | Kubernetes | `metadata.uid` |
| AIB internal identity | AIB database primary key for grants/token exchange | AIB | UUID `AgentID` |
| Workload identity | The running pod/process allowed to act as the logical resource | Kubernetes SA / mesh / AIB credential | `system:serviceaccount:ns:sa` |
| Request/user identity | Human or upstream caller | IdP / Gateway / AIB pre-auth | OIDC `sub`, email |
| Run/task identity | A bounded invocation/autonomous run | KAOS runtime, maybe AIB later | `task_x`, run UUID |
| Protected resource identity | Resource being accessed | KAOS/Gateway/AIB | MCP route URI, third-party service URI |

Key point:

- The target picture should not collapse these into one ID.
- `namespace/name` can be the logical identity, but it should not alone prove that a running pod is allowed to act as that identity.

## Options for KAOS logical identity

### Option 1: `namespace/name` only

Example:

```text
default/researcher
```

Pros:

- Simple and Kubernetes-native.
- Easy for humans.
- Easy to derive from CRDs and routes.
- Stable across normal updates.

Cons:

- Unsafe across delete/recreate: a new object can inherit old grants if the name is reused.
- Ambiguous across clusters.
- Not URI-shaped for claims/resources unless wrapped.
- Does not distinguish Agent/MCPServer/ModelAPI unless kind is added.

Assessment:

- Good as a display identity.
- Too weak as the only grant/security identity.

### Option 2: kind + namespace/name URI

Example:

```text
kaos://agent/default/researcher
kaos://mcp/default/github-tools
kaos://modelapi/default/openai
```

Pros:

- Human-readable.
- Kind-aware.
- Works well as AIB `external_id`.
- Works well in logs, audit, UI, policy references, and token claims.
- Can represent Agents, MCPServers, and ModelAPIs uniformly.

Cons:

- Still unsafe across delete/recreate unless paired with UID.
- Needs cluster scoping if multi-cluster AIB is in scope.
- AIB `external_id` is `VARCHAR(255)`, so the format should remain compact.

Assessment:

- Strong candidate for logical identity.
- Should be paired with UID for lifecycle-sensitive bindings.

### Option 3: kind + namespace/name + UID

Example:

```text
kaos://agent/default/researcher?uid=2f1...
```

or separate fields:

```text
external_id: kaos://agent/default/researcher
kubernetes_uid: 2f1...
```

Pros:

- Prevents accidental grant inheritance on delete/recreate.
- Preserves human-readable identity.
- Aligns with Kubernetes lifecycle semantics.
- Supports safe reconciliation from CRDs to AIB records.

Cons:

- More complex for users and policy references.
- If UID is embedded directly into the external ID, identities change on recreate.
- AIB currently has only `external_id`, not a dedicated `kubernetes_uid` field.

Assessment:

- Best security model if implemented as logical external ID plus separate lifecycle binding metadata.
- If AIB cannot store separate UID yet, KAOS/AIB integration may need an upstream AIB extension.

### Option 4: AIB UUID as the primary visible identity

Example:

```text
agent_id=9ee1c...
```

Pros:

- Matches AIB grants/token exchange model.
- Stable and unambiguous inside AIB.
- Simple for token exchange once mapping exists.

Cons:

- Not Kubernetes-native.
- Poor UX for KAOS users.
- Requires KAOS to learn/store AIB IDs.
- Makes AIB too authoritative for resource identity that is actually owned by Kubernetes.
- Complicates disaster recovery/reconciliation if AIB data is lost or rebuilt.

Assessment:

- Useful internal AIB identity.
- Should not be the primary KAOS identity.

## Options for workload identity

### Option A: No workload identity initially; trust runtime env/config

Pros:

- Simplest.
- Minimal implementation cost.
- Works for early prototype and local demos.

Cons:

- Any pod with network/token access could claim to be an Agent by setting env vars.
- Weak binding between KAOS CRD and running workload.
- Not suitable for strong production authorization.

Use when:

- Prototype only.
- Initial target picture explicitly marks this as insecure/development mode.

### Option B: Optional Kubernetes ServiceAccount binding

Pros:

- Kubernetes-native.
- Already first-class for MCPServer.
- Can be added uniformly for Agent/ModelAPI later.
- Supports least privilege and RBAC.
- Can be validated with Kubernetes TokenReview if needed.
- Pod-bound tokens include object UID metadata.

Cons:

- Requires more operator/CRD design.
- Needs token audience and validation design.
- ServiceAccount identity says which workload is calling, not which user delegated access.
- Does not automatically solve third-party OAuth or user consent.

Use when:

- Target picture wants a production-ready path without mandating service mesh.

### Option C: Managed ServiceAccount per KAOS resource

Example:

```text
agent-researcher
mcpserver-github-tools
modelapi-openai
```

Pros:

- Stronger default binding.
- Easier least privilege.
- Avoids users manually wiring ServiceAccounts.
- Good basis for policy and audit.

Cons:

- Operator must create/manage ServiceAccounts and maybe RBAC.
- Migration complexity for existing resources.
- Some users may want to bring their own ServiceAccount.
- More objects and lifecycle management.

Use when:

- KAOS wants secure-by-default resource identity.

### Option D: Service mesh/SPIFFE identity

Pros:

- Strong service-to-service identity.
- mTLS and workload identity become infrastructure-level.
- Can support advanced zero-trust posture.

Cons:

- Operationally heavy.
- Introduces external dependency.
- Not all KAOS users will run a mesh.
- Still does not solve AIB delegated OAuth by itself.

Use when:

- Advanced production mode.
- Environments already have mesh/SPIFFE.

## Options for AIB synchronization/source of truth

### Option 1: KAOS operator pushes to AIB admin APIs

Pros:

- Can be implemented without changing AIB.
- Operator already watches Agents/MCPServers/ModelAPIs.
- Fastest first integration.

Cons:

- Couples KAOS operator to AIB availability and API semantics.
- Operator becomes responsible for AIB record reconciliation.
- Source-of-truth boundary is less clean.
- Harder to use AIB with other Kubernetes-native agent systems.

Assessment:

- Practical bootstrap option.
- Less ideal as target architecture.

### Option 2: AIB watches KAOS CRDs

Pros:

- Cleaner source-of-truth model.
- Kubernetes remains authoritative for resource existence/topology.
- AIB owns its projection/mapping/policy records.
- Avoids KAOS pushing identity state imperatively.
- More reusable if AIB wants Kubernetes-native integrations.

Cons:

- Requires AIB Kubernetes integration that does not currently exist.
- Requires RBAC, watches, mapping logic, and conflict handling.
- AIB must understand KAOS CRDs or a generic metadata contract.

Assessment:

- Best target architecture if AIB is intended to become Kubernetes-native.
- Likely an upstream AIB feature.

### Option 3: Separate sync controller

Pros:

- Decouples KAOS operator and AIB core.
- Can be developed independently.
- Could live in KAOS, AIB, or a bridge project.

Cons:

- Adds another component.
- Ownership may be unclear.
- More deployment/ops complexity.

Assessment:

- Useful compromise if AIB core should not depend on Kubernetes libraries.

## Source-of-truth proposal

Recommended source-of-truth boundaries for the target picture:

| Data | Authoritative system | Notes |
|---|---|---|
| KAOS resource existence | Kubernetes API | Agent/MCPServer/ModelAPI CRDs |
| KAOS logical identity | Kubernetes/KAOS | Derived from kind/namespace/name, with UID lifecycle guard |
| Runtime workload identity | Kubernetes ServiceAccount or mesh | Optional initially, recommended production |
| Human/user identity | External IdP | Keycloak/Dex/OIDC/etc. |
| AIB internal Agent UUID | AIB | Database primary key |
| AIB mapping to KAOS identity | AIB projection from KAOS | `external_id` plus lifecycle metadata if added |
| User delegated grants | AIB | User principal to AIB Agent UUID |
| OAuth2 sessions/token vault | AIB | Per user/service tokens |
| Third-party service registry | AIB, possibly seeded by admin | Not KAOS CRD-owned unless modeling MCP as protected service |
| KAOS topology | Kubernetes/KAOS | `Agent.spec.mcpServers`, `modelAPI`, `agentNetwork.access` |
| Requested permission profile | Open question | Could be KAOS metadata, AIB policy, or both |
| Approved permission/policy | AIB/external policy system | Should not be blindly granted from Agent CRD |

## Provisional recommendation

The recommended target-picture direction is:

1. Use a **KAOS logical identity URI** as the human-facing and cross-system external identifier:

   ```text
   kaos://{kind}/{namespace}/{name}
   ```

   Examples:

   ```text
   kaos://agent/default/researcher
   kaos://mcp/default/github-tools
   kaos://modelapi/default/openai
   ```

2. Pair that logical identity with Kubernetes `metadata.uid` as a lifecycle guard.

   Preferred model:

   ```text
   external_id = kaos://agent/default/researcher
   kubernetes_uid = <metadata.uid>
   ```

   If AIB cannot store UID separately yet, this becomes a required AIB extension or bridge-controller metadata field.

3. Let AIB keep its internal UUIDs.

   KAOS should not make AIB UUIDs the primary user-facing identity. AIB grants can still bind to AIB UUID internally after reconciling from KAOS identity.

4. Treat Agent, MCPServer, and ModelAPI as **KAOS-managed service identities** with different roles.

   This simplifies Gateway, audit, policy, and future mTLS/mesh models.

5. Do not make ServiceAccount binding mandatory for the first conceptual integration, but include it as the recommended production workload identity.

   Suggested maturity levels:

   | Level | Workload identity |
   |---|---|
   | Dev/prototype | env/config only, explicitly weak |
   | Initial secure | optional/user-provided ServiceAccount, first-class where possible |
   | Recommended production | managed or required per-resource ServiceAccount |
   | Advanced | mesh/SPIFFE/mTLS integration |

6. Prefer AIB watching KAOS CRDs, or a separate sync controller, over KAOS operator pushing AIB records as the long-term target.

   A KAOS operator push remains viable as a bootstrap implementation, but not ideal as the target picture.

## Host questions required to finalize this section

### Q1. Should KAOS identity be cluster-scoped?

Options:

| Option | Example | Pros | Cons |
|---|---|---|---|
| No cluster in identity | `kaos://agent/ns/name` | Simple, short, good for single-cluster | Ambiguous if one AIB manages multiple clusters |
| Include cluster name | `kaos://cluster/prod/agent/ns/name` | Human-readable multi-cluster support | Cluster names can change/collide |
| Include cluster UID | `kaos://cluster/{uid}/agent/ns/name` | Globally safer | Less human-readable, longer |
| Store cluster separately | `external_id=kaos://agent/ns/name`, `cluster_id=...` | Cleanest model | Requires AIB/schema extension |

Provisional recommendation:

- If AIB may manage multiple KAOS clusters, include cluster identity as a separate field if possible.
- If not, keep identity simple initially and reserve cluster scoping for later.

Host decision needed:

- Is multi-cluster AIB in scope for the target picture, or can we assume one AIB per KAOS cluster initially?

### Q2. Should grants survive Agent delete/recreate with the same namespace/name?

Options:

| Option | Behavior | Pros | Cons |
|---|---|---|---|
| Grants survive by name | Same `namespace/name` keeps grants | Convenient | Unsafe if a different agent reuses the name |
| Grants invalidated by UID change | Delete/recreate requires re-approval | Safer, Kubernetes-aligned | More friction |
| Admin-controlled adoption | Recreated agent can adopt old identity if explicitly approved | Balanced | More implementation complexity |

Provisional recommendation:

- Invalidate or require explicit adoption when UID changes.

Host decision needed:

- Should safety win by default, even if it means re-consent after delete/recreate?

### Q3. Should ServiceAccount identity be required in the initial target picture?

Options:

| Option | Pros | Cons |
|---|---|---|
| Not required | Simple, fast, low friction | Weak workload binding |
| Optional first-class | Good balance, supports production | More CRD/operator work |
| Required per resource | Secure by default | Highest migration/complexity |
| Mesh/SPIFFE required | Strongest platform posture | Too heavy for many KAOS users |

Provisional recommendation:

- Optional first-class ServiceAccount initially; recommended/managed ServiceAccount for production.

Host decision needed:

- Should KAOS target secure-by-default ServiceAccounts early, or keep them optional for now?

### Q4. Should Agent, MCPServer, and ModelAPI all become first-class identity-bearing resources?

Options:

| Option | Pros | Cons |
|---|---|---|
| Agent only | Minimal, matches AIB current model | Ignores MCP/ModelAPI service identity and enforcement |
| Agent + MCPServer | Covers most tool delegation | ModelAPI auth still separate |
| Agent + MCPServer + ModelAPI | Uniform service identity model | More design work |

Provisional recommendation:

- Treat all three as identity-bearing KAOS-managed services, even if AIB initially only stores Agent records.

Host decision needed:

- Should ModelAPI identity be part of the target picture now, or deferred?

### Q5. Should identity metadata be annotations first or first-class spec fields?

Options:

| Option | Pros | Cons |
|---|---|---|
| Annotations | Fast, non-breaking, flexible | Weak schema, harder UX/discovery |
| First-class `spec.identity` | Clear contract, validation, docs | Requires CRD changes |
| Both | Prototype annotations, graduate to spec | Migration path required |

Provisional recommendation:

- Target picture should define first-class fields eventually.
- Initial implementation may use annotations if we want low-risk prototyping.

Host decision needed:

- Is the target picture allowed to propose CRD changes such as `spec.identity`/`spec.security`, or should it avoid CRD API changes initially?

### Q6. Should AIB consume KAOS CRDs directly or should KAOS push records to AIB?

Options:

| Option | Pros | Cons |
|---|---|---|
| KAOS pushes to AIB | Fastest without AIB changes | Less clean boundary |
| AIB watches KAOS CRDs | Clean target architecture | Requires AIB Kubernetes integration |
| Separate bridge controller | Decoupled | Adds component |

Provisional recommendation:

- Target: AIB watcher or bridge controller.
- Bootstrap: KAOS push is acceptable only if explicitly marked as first implementation shortcut.

Host decision needed:

- Should the target picture assume upstream AIB Kubernetes integration is acceptable, or should it bias toward KAOS-owned integration first?

### Q7. What should AIB `external_id` contain?

Options:

| Option | Example | Pros | Cons |
|---|---|---|---|
| Logical URI only | `kaos://agent/ns/name` | Simple, stable | Needs separate UID guard |
| URI with UID | `kaos://agent/ns/name?uid=...` | Single-field safety | Less stable, awkward UX |
| Opaque KAOS ID | `agent.ns.name.uid` | Compact | Less expressive |
| AIB schema extension | `external_id` + `external_uid` + `cluster_id` | Cleanest | Requires AIB changes |

Provisional recommendation:

- `external_id = kaos://{kind}/{namespace}/{name}` plus separate UID/cluster metadata.

Host decision needed:

- Are AIB schema extensions in scope for the target picture?

### Q8. Should workload identity be used to authorize AIB token exchange?

Options:

| Option | Meaning | Pros | Cons |
|---|---|---|---|
| No | AIB trusts subject/client tokens only | Simpler | Weaker workload binding |
| Yes, via SA token | AIB validates pod/workload SA identity | Kubernetes-native | Requires token audience/TokenReview/JWT validation design |
| Yes, via client credential | Agent holds AIB-issued credential | AIB-native | Secret distribution/rotation problem |
| Yes, via mesh/SPIFFE | Workload mTLS/JWT identity | Strong | Operationally heavy |

Provisional recommendation:

- Not required for the earliest flow, but target production design should include workload binding either via ServiceAccount or mesh.

Host decision needed:

- Should AIB trust only user/agent OAuth tokens initially, or must it also verify the calling workload?

### Q9. Should autonomous runs have their own identity?

Options:

| Option | Pros | Cons |
|---|---|---|
| No, use Agent identity only | Simple | Poor audit/expiry boundaries |
| Run ID as correlation only | Good audit, low complexity | Not authorization-grade |
| Run ID as grant-bound identity | Strong control and expiry | Requires more AIB/KAOS changes |

Provisional recommendation:

- Treat autonomous run ID as correlation initially.
- Later bind autonomous grants to run IDs or run windows when approval/consent model is designed.

Host decision needed:

- For the target picture, should autonomous authorization be agent-level, run-level, or explicitly deferred to approval-flow research?

## Proposed decision if host agrees

If the host accepts the provisional recommendations, the final decision for this section would be:

1. KAOS logical identity is:

   ```text
   kaos://{kind}/{namespace}/{name}
   ```

2. Kubernetes `metadata.uid` is mandatory lifecycle metadata for safe AIB binding.
3. AIB stores its own UUID primary keys and maps KAOS identity through `external_id` plus lifecycle metadata.
4. Kubernetes/KAOS owns resource existence and topology.
5. AIB owns delegated grants, consent, token vault, and internal identity mapping.
6. Human identity comes from an external IdP.
7. Workload identity is optional in the first implementation but recommended for production via ServiceAccounts.
8. Agents, MCPServers, and ModelAPIs are all identity-bearing KAOS-managed services in the target picture.
9. AIB should eventually watch KAOS CRDs or use a bridge controller; KAOS operator push is only a bootstrap option.

## Decision status

Status: **proposed, awaiting host answers**.

The next step is to answer the host questions above, then finalize this section before moving to Decision 2: user/request context propagation.
