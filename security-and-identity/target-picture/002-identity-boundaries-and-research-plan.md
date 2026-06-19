# 002 - Identity boundaries and research plan

## Prompt

1. For the KAOS logical agent Identity why can't we use the agent name of agent_name and namespace as the unique identifier for this?; Explain futher the KAOS workload identity. Mainly what I don't understand is what's the connection with service accounts. And why can't this be achieved without service accounts? / Why is it more desirable specifically with service accounts?; In regards to thea MCP server identity  I don't understand what it means for not having AIP binding. Whether this is a feature missing, as yes, indeed we haven't even started implementing AIP, so you can't expect there to be any integrations to try and understand what this means. Also, I wonder whether there needs to be, conceptually, a separation of different components, as the authentication/authorisation of MCP servers/Model API/agents, or whether all of these can just be services that require authentication/authorisation.; In regards to the AIV identity records, I'm not sure what exactly this entails, but I don't understand why Chaos and AIV need to keep in sync. Expand on why this is needed. 2. Okay, this is relatively clear (caveat with questions from previos); in regard to the question about meta database, where is it authoritative? It feels to me that it's relatively straightforward. Let's flesh this out also as part of the target picture. I want to understand if there are any grey areas. Obviously, many can be construed, but it's just whether there are any where there genuinely is no clarity either way. To me, it sounds like this is a relatively clear and easy one.3. Okay, for this one, we will need to do thorough research to identify what is the best approach. My suggestion will be that the way that we approach this is that once we identify all of the key areas, we go through each of them in thorough detail so that they are finalised and documented, and then they will pass globally to then integrate into a coherent target picture. 4. Okay, so now for this one, most of them make sense.
1. One of the key questions that does come to my mind is: why do we need to have a separation of the concept of an MCP server token and an agent token? That's number one, and I would like to understand a bit more.
2. Number two is: where would the authentication and validation be most relevant to be carried out?
This is going to be also relevant for the next section of the authorisation flow that is in sync. If we take an example such as an agent wanting to request permissions, at least from a current KAOS architecture (given that it's a synchronous request-response), it would be significantly more fiddly to implement, I would assume, if this is carried out as the request is identified at the MCP server level. For example, if we have a multi-agent system where multiple agent steps are carried out, then the state of the current request-response flow would have to be interrupted. It would have to go back again in order for this to then receive the authentication flow and then proceed. However, it sounds like this is something that we can discuss as part of the next point in more detail. 5. I suggested point 5 is the one that, to me, is the most abstract and unclear, especially in the context of the real-time architecture of Chaos. Currently, the way that Chaos would operate is having a synchronous request-response flow in the context of a multi-agent system, where let's say you have one lead agent and two sub-worker agents, each of them with multiple MCP servers. Let's assume that the MCP server calls will require a combination of user approval as well as admin approval. There would be key questions on how it would be possible to pose the current state of execution and carry out the run. The simplest, likely in the current architecture, would just be to make sure that the current session, for example, has a big pause until the user approves it, ideally also through the AIV flow or through an asynchronous approach. This is something that we would have to think about. Otherwise, it would be highly complex if we needed to solve and store the state, say, for example, the lead agent delegates to a subagent. This agent does an MCP call after multiple loops, and then it requires approval if it was expected to return with a user with an error. Once the user approves, it would require the lead agent to send the same request path or at least similar context to the worker agents. To me, this sounds like it poses a higher level of nondeterministic behaviour, although it could still be an option. If it's an easier approach, this is something that will have to be fleshed out in much more detail. 6. 1, 2, and 3 are relatively clear.  Agent-to-agent delegation: it sounded like this is something that signed payloads are not yet supported, so we can pause it for now, but perhaps add it as the target picture as a potential future extension.1. To me, it seems like this is where external validation may be relevant, and this is where authorisation is starting to sound to me less about agentic systems and more about normal microservices.
2. We'll discuss this as a separate topic as well that I want to understand a bit more, where AI/ML is actually needed, where we're better off actually just using a third-party authorisation authentication service. For the consent or approval missing piece, refer to the answer to the previous topic, as I covered it more extensively on the challenges and limitations, and this is something that will have to dive deeper. 7. I would say that keeping it simple should be one of the key principles as we approach this.a We could easily over-engineer this and then end up making a massive complication, where perhaps the focus may be just adding some more simple features that allow us to add a lot of this. TLS, it's something that I think would be worth likely the easiest would be using something like search manager.a And potentially having something that is generated at the installation level or such. Secrets are currently managed manually. Adding a secret manager would be overcomplicating. Similarly, for the rest of the components, it seems to me that it's too much. ---- OK, now in terms of putting together the target picture and the RPI that looks OK. Let's proceed with breaking this down further. I would like to now create a plan on how we flesh these things further. Let's focus just on the research piece. The plan we implement is not relevant at this point. Let's make sure that we are able to make some decisions on each of the architectural requirements. Let's put together a plan on how we will proceed to define some of these. For the research, external research that was identified, carry it out already immediately as we go through all of those topics before actually you present the plan, so that it's in context of that as well. I would like for you to also make sure that you research other projects, whether it's agentic systems projects, but likely those are less mature in terms of the security and identity piece. Instead, focus on likely service mesh projects, as well as other initiatives and case studies, blog posts, etc., or especially from identity provider blog posts which cover how different approaches to identity and authorisation are carried out. I'm certain that this is not a new challenge. Finally, I will want to dive into a controversial question which is in regards to AIV. There are things that I am currently looking at that, to me, sound like perhaps they don't need to be specifically AIV, or perhaps it could, namely, be on authorisation. What parts of this could be solved much more easily with an existing service mesh authentication, authorisation, plus external security tooling like DEX or Keycloak, etc.?

As part of this, I would like to flesh out what are the components that make sense completely outside versus what are the things that may be completely inside. There are other questions about what are things that perhaps may be better implemented within chaos as opposed to adopting AIV, or perhaps the first iteration implemented purely within chaos and then integrated with AIV as further features are done. As part of this, I also want to understand whether things like OPA/Rego should be used within AIV authorisation management language.

## Response

## Immediate clarifications

### 1. Logical agent identity can use namespace/name, but should not rely on it alone

`namespace/name` is a good human-readable logical identifier:

```text
agent: default/researcher
mcp: default/github-tools
modelapi: default/team-api
```

For many KAOS flows, this is probably enough as the **display identity** and policy subject. The caveat is lifecycle:

- Kubernetes `namespace/name` is unique only among currently existing objects.
- If `default/researcher` is deleted and recreated, it may or may not be intended to inherit previous grants.
- Kubernetes UID distinguishes object incarnations.

Recommended target model:

| Identifier | Use |
|---|---|
| `namespace/name` | Stable user-facing identity and default policy subject. |
| Kubernetes UID | Lifecycle guard to detect delete/recreate and prevent accidental grant inheritance. |
| AIB internal ID | Optional database primary key and external OAuth client identifier. |

Default safety rule: **deleting and recreating an Agent with the same name should not automatically inherit sensitive grants unless explicitly configured.**

### 2. Workload identity and ServiceAccounts

Workload identity answers a different question from logical identity:

```text
Logical identity: "this is the researcher Agent"
Workload identity: "this specific pod is allowed to act as researcher"
```

ServiceAccounts matter because Kubernetes already uses them as the native in-cluster workload identity mechanism. Kubernetes docs define ServiceAccounts as identities for pod processes, and modern ServiceAccount tokens are bounded/projection-based and invalidated with pod/service account lifecycle.

Why ServiceAccounts are desirable:

- Native Kubernetes object and RBAC subject.
- Already attached to Pods through `spec.serviceAccountName`.
- Works with TokenRequest/projected tokens instead of long-lived static secrets.
- Service meshes often derive workload identity from ServiceAccount. Linkerd, for example, issues mTLS certificates bound to the pod's Kubernetes ServiceAccount.
- Avoids inventing a new workload identity bootstrap mechanism.

Can this be achieved without ServiceAccounts? Yes:

| Alternative | Tradeoff |
|---|---|
| Static AIB client secret in Kubernetes Secret | Simple, but rotation and leakage risk. |
| AIB-issued bootstrap token | Possible, but KAOS/AIB must solve secure delivery and rotation. |
| SPIFFE/SPIRE identity | Strong workload identity, but adds infrastructure. |
| Service mesh identity | Strong transport identity, but requires mesh adoption. |
| mTLS certs from cert-manager | Useful for TLS, but still need issuance/binding semantics. |

Initial target should probably use ServiceAccounts as the default workload binding, while allowing future SPIFFE/mesh integration.

### 3. MCPServer, ModelAPI, and Agent identity can be unified as service identities

It is not necessary to invent completely separate identity systems for Agents, MCPServers, and ModelAPIs. Conceptually they can all be:

```text
KAOS-managed services that require authentication and authorization
```

The distinction is in **resource type and policy**, not in the primitive identity mechanism:

| Resource | Identity primitive | Policy examples |
|---|---|---|
| Agent | `kaos://agent/ns/name` | Who may invoke/delegate to it? What MCPs may it use? |
| MCPServer | `kaos://mcp/ns/name` | Who may call it? Which tools/resources are exposed? |
| ModelAPI | `kaos://modelapi/ns/name` | Which agents may use it? Quotas/models? |

"No AIB binding" just means no current integration maps those KAOS resource identities to AIB records, credentials, audiences, protected resources, or policy subjects. It is not a criticism of the current state; it is the integration to design.

### 4. Why KAOS and AIB need to stay in sync

AIB needs a view of KAOS resources if it is making security decisions about them.

Examples:

- If an Agent is deleted, AIB should revoke or deactivate its runtime credentials.
- If an MCPServer endpoint changes, AIB/Gateway policy needs the current protected resource mapping.
- If a ServiceAccount changes, workload binding changes.
- If an autonomous run ends, its grant should expire or be revoked.
- If a resource is recreated with a new UID, AIB must decide whether grants carry over.

This does not mean AIB owns all KAOS metadata. It means AIB needs enough synchronized state to avoid making stale authorization decisions.

### 5. Metadata authority boundaries are mostly clear

This should be explicit in the target picture:

| Data | Source of truth |
|---|---|
| Resource existence, namespace/name, UID | Kubernetes API |
| Desired agent/tool/model topology | KAOS CRDs |
| Runtime readiness/endpoints/status | KAOS status + Kubernetes Services/HTTPRoutes |
| Human user identity | External IdP |
| Workload pod identity | Kubernetes ServiceAccount, or mesh/SPIFFE if adopted |
| Security policy, permission sets, grants, consent | AIB |
| Third-party OAuth tokens/secrets | AIB token vault |
| TLS certificates | cert-manager, Gateway, mesh, or SPIFFE stack |
| Network-level policy | Kubernetes NetworkPolicy, Gateway, or mesh |

Genuine grey areas:

- **Owner/team/display metadata**: could live in KAOS annotations/spec or AIB admin UI.
- **Requested permission profile**: KAOS may declare intent; AIB approves/enforces.
- **Route/resource mapping**: KAOS creates routes, but AIB may need a security resource model.
- **Autonomous run metadata**: KAOS owns task execution; AIB owns grant validity.
- **Tool-level resource taxonomy**: MCP runtime knows tools; AIB/Gateway needs a normalized policy view.

### 6. Why separate agent token and MCP token/client identity?

They answer different audit and trust questions:

```text
Agent token: who requested the action?
MCP/server identity: which service is executing or exchanging the token?
User token: on whose behalf?
```

For a GitHub issue creation:

```text
user = alice
agent = incident-agent
mcp = github-mcp
resource = GitHub issues
action = create
```

If MCP simply reuses the agent token, AIB cannot distinguish the requester from the executor. Separate identities help:

- Audit: "agent X requested, MCP Y executed."
- Least privilege: only GitHub MCP can exchange for GitHub tokens.
- Blast radius: compromised agent token cannot directly act as every MCP.
- Policy: AIB can check user + agent + MCP + resource.

Could the first implementation avoid this separation? Yes. For a simpler MVP, use agent/user identity at the Gateway or MCP and add MCP workload identity later. The target picture should still include separate service identity because it is cleaner and scales better.

### 7. Where authentication and validation are most relevant

Layered validation is clearer than one magic enforcement point:

| Hop | Best validation point |
|---|---|
| User -> Agent | Gateway/auth proxy validates user; Agent runtime receives trusted context/token. |
| Agent -> MCP | Gateway/sidecar validates agent/workload token and user context. |
| MCP -> AIB token exchange | AIB validates subject token, exchange client, consent, and policy. |
| MCP -> downstream API | Downstream API validates exchanged token/scope. |
| Agent -> ModelAPI | Gateway/sidecar or ModelAPI validates agent token and policy. |
| Agent -> Agent | Gateway/sidecar or receiving Agent validates bearer token; signed payload deferred. |

The synchronous KAOS request-response model argues against discovering missing consent only deep inside an MCP call where possible. Research should evaluate:

- preflight permission discovery,
- fail-with-approval URL,
- blocking wait,
- async pause/resume,
- approval-before-run for known profiles.

### 8. Approval flow is the most complex target domain

The current KAOS execution model is synchronous and potentially multi-agent:

```text
lead agent -> worker agent -> MCP call -> approval required
```

If approval is discovered late, resuming exactly the same path is hard and may be nondeterministic.

Candidate approaches:

| Approach | Fit for current KAOS | Tradeoff |
|---|---|---|
| **Preflight approval** | Best if required permissions are known before run. | Hard for dynamic LLM tool choice. |
| **Fail with approval URL, then retry** | Simple and deterministic. | User repeats request; not seamless. |
| **Block synchronous request until approved** | Simple conceptually. | Long HTTP request, timeouts, poor UX for admin approvals. |
| **Async task pause/resume** | Best long-term UX. | Requires durable state and deterministic resume model. |
| **Approval as tool result** | Agent receives "approval required" and asks user. | May introduce nondeterministic retry paths. |

Initial recommendation: **do not start with full pause/resume.** Start with preflight where possible plus fail-with-approval URL/retry. Add async pause/resume only after KAOS has durable task semantics suitable for it.

### 9. This is mostly normal microservice security

Many parts are not agent-specific:

- workload identity,
- TLS/mTLS,
- JWT validation,
- service-to-service authorization,
- ingress auth,
- policy decision/enforcement points.

The agent-specific parts are:

- mapping logical agents to workloads and tool access,
- user-delegated agent consent,
- autonomous run grants,
- approval UX for tool execution,
- audit chains across agent reasoning, delegation, and tool calls.

This supports a "keep it simple" principle: use established microservice security where possible; build only the agent-specific layer.

### 10. Hard security should stay simple initially

Suggested initial posture:

- Use existing IdP or lightweight Dex/Keycloak for user auth.
- Use Gateway TLS with cert-manager.
- Use Kubernetes ServiceAccounts for workload binding.
- Use short-lived tokens where feasible.
- Avoid custom certificate lifecycle.
- Avoid adding a secret manager in the first iteration.
- Avoid mandatory mesh/SPIFFE in the first iteration, but keep the design compatible.

## External research findings already gathered

| Source | Relevant finding |
|---|---|
| Kubernetes ServiceAccounts | ServiceAccounts are native identities for pod processes; modern tokens can be bounded, projected, and invalidated with pod lifecycle. |
| Kubernetes authentication | Kubernetes distinguishes normal users from ServiceAccounts; normal users come from external identity systems. |
| SPIFFE/SPIRE | Provides workload identities via short-lived X.509/JWT SVIDs and workload API; useful if KAOS later needs stronger workload identity. |
| Linkerd mTLS | mTLS certificates are bound to Kubernetes ServiceAccount identity and automatically rotated; illustrates why SA is a common workload identity anchor. |
| cert-manager | Manages TLS certificates and renewal; can use multiple CAs and avoid custom certificate lifecycle. |
| Envoy external authorization | Envoy can delegate authz decisions to an external service and fails closed by default unless configured otherwise. |
| Envoy external processing | ExtProc can inspect/modify headers, body, trailers, and return immediate responses; relevant for token exchange and approval-required responses. |
| Envoy OAuth2 filter | Can perform OAuth2 login/redirect and forward bearer tokens upstream; useful for gateway-level user auth patterns. |
| Gateway API HTTPRoute | Provides path/header/host routing to Kubernetes Services; KAOS already uses HTTPRoute-style routing. |
| Dex | Federated OIDC identity service; useful lightweight in-cluster IdP/broker option. |
| Keycloak Authorization Services | Provides resource, scope, policy, permission, PDP/PEP model and UMA-style authorization services. |
| OPA/Rego | Declarative policy engine for structured JSON decisions. OPA is not source of truth; it evaluates policy over input and replicated/external data. |
| OPA Envoy plugin | Can enforce fine-grained context-aware access control with Envoy without modifying microservices. |

## Research-only plan

The plan below is intentionally research-only. No implementation plan yet.

### Research track 1: Identity model and source of truth

Questions:

1. Should the target logical ID be `namespace/name`, Kubernetes UID, AIB UUID, or a combination?
2. What happens on delete/recreate?
3. Are Agents, MCPServers, and ModelAPIs all represented as `kaos://<kind>/<namespace>/<name>` service identities?
4. What metadata belongs in KAOS CRDs vs AIB records?
5. What is the minimum `spec.identity` or annotation model needed?

Deliverable:

- Identity model decision record.
- Source-of-truth table.
- Lifecycle examples for create/update/delete/recreate/rollout.

### Research track 2: Workload identity and transport security

Questions:

1. Is Kubernetes ServiceAccount identity sufficient for initial workload binding?
2. Do we need projected service account tokens?
3. Do we need mTLS initially, or only Gateway TLS?
4. Should cert-manager be a recommended dependency?
5. Should mesh/SPIFFE be supported as optional production hardening?

Deliverable:

- Security baseline recommendation: minimal, recommended, advanced.
- Comparison: ServiceAccount tokens vs AIB secrets vs mesh/SPIFFE.

### Research track 3: Enforcement topology

Questions:

1. Gateway/ExtProc vs sidecar vs native FastMCP: which is best for first implementation?
2. What traffic must be routed through enforcement?
3. Can Envoy/ExtProc realistically parse enough MCP payload for tool-level policy?
4. What does OPA-Envoy add or replace?
5. What failure mode is acceptable: fail closed, fail open, degraded?

Deliverable:

- Enforcement topology comparison.
- Recommended initial topology.
- Future topology options.

### Research track 4: User identity and token propagation

Questions:

1. Should user auth be handled by Gateway OAuth2, oauth2-proxy, Dex, Keycloak, or existing enterprise IdP?
2. What token/claims reach the Agent runtime?
3. How does KAOS preserve user context through multi-agent and MCP calls?
4. What headers or metadata are safe to propagate?
5. How do we avoid trusting spoofed headers?

Deliverable:

- User identity flow for user->agent->MCP.
- Minimal KAOS runtime requirements.
- IdP/gateway recommendation.

### Research track 5: AIB vs external authorization services

Questions:

1. Which parts should AIB own uniquely?
2. Which parts can Keycloak Authorization Services, OPA, Envoy, or mesh solve better?
3. Is AIB a PDP, a token broker, a consent vault, or all three?
4. Should AIB use CEL as current code suggests, OPA/Rego, Keycloak-style resource policies, or pluggable policy?
5. Should OPA/Rego be embedded in AIB, run as a sidecar/service, or not used initially?

Deliverable:

- AIB responsibility boundary.
- "Build in KAOS vs contribute to AIB vs use external service" matrix.
- Policy language recommendation.

### Research track 6: Consent and approval flow

Questions:

1. What approval layers exist: admin approval, user consent, runtime/HITL approval, autonomous run authorization?
2. Which are required for initial implementation?
3. Can preflight approval avoid mid-run interruption?
4. What happens when approval is discovered in a worker agent after several loops?
5. Do we fail/retry, block, or pause/resume?

Deliverable:

- Approval flow taxonomy.
- Initial approval UX recommendation.
- Future async pause/resume design constraints.

### Research track 7: Autonomous agents

Questions:

1. Are autonomous permissions service-owned, user-delegated, or both?
2. How are grants tied to run ID, expiry, owner, and revocation?
3. What happens if grant expires or is revoked mid-run?
4. How does audit distinguish autonomous action from user request action?

Deliverable:

- Autonomous authorization model.
- Grant lifecycle and audit model.

### Research track 8: ModelAPI, memory, and non-MCP surfaces

Questions:

1. Should ModelAPI access be authenticated/authorized in the first target?
2. Should model usage include user and agent identity for audit/quota?
3. What sensitive data appears in memory/task stores?
4. What redaction/retention baseline is needed?

Deliverable:

- Non-MCP security scope decision.
- ModelAPI and memory security recommendations.

## Research sequencing

Suggested order:

1. **Identity/source of truth** - needed by everything else.
2. **User identity/token propagation** - determines KAOS runtime requirements.
3. **Enforcement topology** - Gateway vs sidecar vs native.
4. **AIB vs external authorization boundary** - determines what to build where.
5. **Consent/approval flow** - hardest interaction with synchronous KAOS.
6. **Workload/TLS security baseline** - keep simple but production-aware.
7. **Autonomous grants** - builds on identity and approval.
8. **ModelAPI/memory** - target-picture completeness, likely later implementation.

## Provisional architectural principle

Keep KAOS-specific security small:

```text
KAOS should propagate context and expose metadata.
AIB should own agent/user delegation, consent, token vault, and token exchange.
Existing infrastructure should own generic authn/authz transport primitives where possible.
```

Avoid building custom versions of:

- human IdP,
- certificate lifecycle,
- service mesh,
- generic policy engine,
- secret manager,
- signed payload framework.

Only build KAOS/AIB-specific pieces where the problem is genuinely agentic:

- logical agent identity,
- user-delegated agent permissions,
- autonomous run grants,
- MCP/tool approval UX,
- audit across reasoning/delegation/tool execution.
