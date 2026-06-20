# 006 - CRD sync, identity, gateway/sidecar, and autonomous runs

## Prompt

1. ok and is it enough to refresh on crds or shoudl it laso register on webhooks? also what extensions are needed to ensure that kaos makes all info available that AIB requires? 2. ok but adding these as metadata still seems to me like agent-id is mayeb ok as annotations, but why annotations instead of actual spec components? Is the suggestion that AIB would inject things based on annotations? 3. OK but does that mean that currently AIB doesn't support this? Or it does support this? 4. why would fastmcp native be requred for fine grained tool authorization? Why can't this be achieved with envoy? namely once the token is provided woudln't the token provided by default have specific granular permissions only for tools on the upstream services? or do you mean that you mean authorization enforced at the mcp server level? 5. ok, currently the traffic is not configured to go through the envoy proxy, is this prefered than having a side car? It seems to me that a sidecar may allow more flexibility or at least a tradeoff of having a side car for every pod esp for mcpserver and modelapi, but there it means that finegrained permissions can be enforced without the need to modify aplication code; explain when we'd prefer side car vs envoy specifically. 6. ok but this does sound like even a potential nice-to-have / optional dependign on the project, as it likely is overkill for a large % of internal usecases. 7. ok. 8. how would this be implemented in kaos? is there a clear straightforward or is there multiple options with tradeoffs? 9. ok it seems expiry can be linked to the autonomous delegation run which likely also will have a run end date. 10. ok. 11. ok.

## Response

## 1. CRD refresh, webhooks, and KAOS metadata extensions

**Watching/reconciling CRDs is the right primary mechanism.** Webhooks are useful, but they should not be the source of truth.

Recommended split:

| Mechanism | Role |
|---|---|
| **AIB Kubernetes controller/watch** | Source-of-truth sync loop. Watches `Agent`, `MCPServer`, maybe `ModelAPI`, Services, ServiceAccounts, Deployments/Pods. Handles drift and retries. |
| **Admission webhook** | Optional fast validation/defaulting. Reject invalid identity references, enforce required labels/spec fields, maybe inject annotations. |
| **Mutating webhook** | Optional runtime injection. Add env vars, projected tokens, sidecar/proxy config, or labels if the AIB integration is enabled. |
| **Periodic resync** | Safety net for missed events or controller downtime. |

So: **CRD watch is enough for correctness; webhooks are useful for UX, policy, and injection.**

KAOS likely needs to expose/add:

| Needed by AIB | Where KAOS could expose it |
|---|---|
| Stable logical identity | `status.uid`/Kubernetes UID plus optional `spec.identity.id` or annotation |
| Agent/MCP kind and endpoint | Status endpoint, Service labels, HTTPRoute labels |
| Runtime ServiceAccount | Existing/future `spec.serviceAccountName` for Agent, already present for MCPServer |
| Owner/team/display metadata | `spec.identity`, annotations, or AIB-side registry |
| Requested capability profile | `spec.identity.requestedProfiles` or annotations |
| Gateway exposure info | HTTPRoute labels/status |
| Autonomous run metadata | Task/run ID, goal ID, expiry/end time, bound user/service grant if any |

## 2. Annotation vs spec fields

Your instinct is right: if identity becomes a first-class KAOS feature, **it should not stay only in annotations**.

Use annotations for early experiments because they are non-breaking and do not require CRD schema changes:

```yaml
metadata:
  annotations:
    aib.kaos.tools/agent-id: researcher
```

But a mature KAOS integration should probably have explicit spec fields:

```yaml
spec:
  identity:
    enabled: true
    id: researcher
    requestedProfiles:
      - github-issue-writer
    serviceAccountName: agent-researcher
```

Important: even with spec fields, KAOS should express **identity intent and requested profiles**, not grant authority by itself. AIB remains the authority that approves/mints/enforces actual permission sets.

So the answer is:

- **Prototype**: annotations.
- **Productized KAOS feature**: explicit `spec.identity`.
- **AIB should not blindly inject permissions because an annotation says so.**

## 3. Does current AIB support user token + agent token + MCP identity?

**Partially, not completely.**

Current AIB supports important pieces:

| Piece | Current AIB support |
|---|---|
| Agent registry | Yes |
| Agent client credentials | Yes |
| JWT signing/JWKS | Yes |
| User consent and grants | Yes |
| Stored third-party OAuth tokens | Yes |
| RFC 8693 token exchange | Yes |
| ExtProc exchange component | Yes |

But the full KAOS flow needs additional integration/features:

| Needed for KAOS flow | Current state |
|---|---|
| KAOS Agent CRD sync into AIB | Not present |
| Pod/workload identity binding to AIB agent | Not present as KAOS integration |
| KAOS runtime propagating user identity to MCP calls | Not present |
| MCP identity as separate exchange client | Conceptually possible, but not KAOS-wired |
| AIB policy that reasons over user + agent + MCP + tool/resource | Partially possible for resource/token exchange, not complete for KAOS tools |

So current AIB is enough to build a prototype, but not enough for a clean end-to-end KAOS identity model without additional work.

## 4. Fine-grained tool authorization: FastMCP vs Envoy

You are right that **Envoy can enforce some fine-grained rules**, but it depends what "fine-grained" means.

There are two layers:

### Downstream resource scopes

Example: GitHub token only has `issues:write`, not `repo:admin`.

This can be enforced by AIB/token exchange and does **not** require FastMCP-native authorization. The downstream API rejects anything outside the token's scopes.

```text
Agent -> MCP -> GitHub
             token has only issues:write
```

### MCP tool-level authorization

Example: same `kubernetes-mcp` exposes:

- `list_pods`
- `get_logs`
- `delete_deployment`
- `exec_into_pod`

These may all talk to the Kubernetes API, but the authorization question is at the **MCP tool** level: can this agent invoke this tool with these arguments?

Envoy can enforce this only if it parses MCP JSON-RPC/streamable HTTP bodies and understands tool names/arguments. That is possible, but more custom. FastMCP-native enforcement is easier because the MCP server already knows:

```text
tool name
tool arguments
caller token claims
server/resource identity
```

So the answer:

- **AIB scopes can protect downstream APIs without MCP-native auth.**
- **MCP-native auth is useful when the thing being protected is the tool invocation itself**, especially for local tools, Kubernetes tools, filesystem tools, code execution tools, or tools whose downstream API scopes are too coarse.
- **Envoy can do it**, but only with MCP-aware body parsing/policy, which is more complex than header/token enforcement.

## 5. Gateway/Envoy vs sidecar

Both are valid. They optimize for different things.

### Prefer central Gateway/Envoy when:

| Good fit | Why |
|---|---|
| Agent -> MCP traffic already goes through Gateway | Central enforcement, no per-pod overhead |
| You want a fast first integration | Avoid modifying every MCP runtime |
| Coarse auth is enough | Validate/exchange token based on route/resource |
| You want uniform audit | One place to log token exchange decisions |
| You want fewer moving pieces per workload | No sidecar in every pod |

Flow:

```text
Agent -> Gateway/ExtProc -> MCP
              |
             AIB
```

### Prefer sidecar/local proxy when:

| Good fit | Why |
|---|---|
| Traffic is internal service-to-service and not routed through Gateway | Avoid forcing all internal calls through central ingress |
| You need per-workload customization | Different policy per MCP/ModelAPI |
| You want app-code-free local enforcement | Sidecar can inspect local traffic before app sees it |
| You need egress mediation | MCP -> external API token exchange/proxying |
| You want resilience/local caching near the workload | Avoid central gateway bottleneck for every internal call |

Flow:

```text
Agent -> MCP sidecar -> MCP app
             |
            AIB
```

### Practical KAOS recommendation

Start with **Gateway/ExtProc for Agent -> MCP and user -> Agent** if KAOS enables Gateway API. It is simpler and lower-touch.

Use **sidecars** for:

- MCP servers that need egress token mediation.
- ModelAPI access control if model calls need policy/audit.
- Clusters where internal traffic should not hairpin through a central Gateway.
- Fine-grained MCP enforcement without modifying the MCP app.

This is a tradeoff, not a universal rule.

## 6. Signed payload A2A identity is optional

Agreed. For many internal use cases, **JWT bearer auth is enough**.

Recommended maturity ladder:

1. No auth / namespace-local trust.
2. JWT bearer auth with AIB JWKS.
3. Audience-scoped short-lived tokens.
4. Gateway/sidecar policy checks.
5. Signed A2A task payloads with replay protection.
6. Federation.

KAOS probably does not need step 5 immediately unless it targets high-assurance cross-org, regulated, or adversarial multi-agent deployments.

## 8. Consent/reauth implementation options in KAOS

There are multiple options with tradeoffs.

### Option A: Fail with consent URL

Tool call fails with a structured error:

```json
{
  "error": "consent_required",
  "url": "https://aib/consent/session/..."
}
```

Agent returns: "I need approval; open this URL."

Pros: simplest.
Cons: user must retry; awkward for long-running tasks.

### Option B: MCP elicitation / URL-required response

AIB ExtProc already has a concept similar to returning a URL elicitation error. KAOS/MCP could surface that as a structured MCP response.

Pros: aligns with agent/tool protocol patterns.
Cons: KAOS runtime must preserve and present that structured response cleanly.

### Option C: Pause/resume task

KAOS task enters `blocked_waiting_for_consent`, stores state, resumes after AIB callback or user retry.

Pros: best UX for long-running workflows.
Cons: needs durable task state and callback/resume semantics.

### Option D: Pre-consent before execution

Before starting a task, KAOS/AIB determines required permissions and asks for consent.

Pros: avoids mid-run blockage.
Cons: hard for dynamic agents; LLM may choose tools at runtime.

Practical recommendation:

1. Start with **fail with consent URL**.
2. Add structured MCP/agent elicitation.
3. Later add durable pause/resume for autonomous and long-running tasks.

## 9. Autonomous expiry tied to run end date

Yes. This is the cleanest safety model.

For autonomous runs, AIB grants should be bounded by:

```text
grant subject = agent identity
optional user binding = user who authorized the run
run_id = autonomous task/run ID
scope = approved permission set
valid_until = run end date / max duration
revocable = yes
auditable = yes
```

This lets KAOS say:

```text
This autonomous agent may use GitHub issues:write only for this run,
only until 2026-06-30,
only for repo X,
and only under user Alice's delegation or admin-approved service grant.
```

For always-on autonomous agents, the same model still works, but the grant should have an explicit renewal period and owner.

## Consolidated answers

1. **CRD watching is the primary sync mechanism; webhooks are optional but useful for validation/defaulting/injection.**
2. **Annotations are fine for prototype integration, but mature KAOS should expose `spec.identity`; AIB remains the authority over actual permissions.**
3. **Current AIB supports pieces of the user+agent+MCP token model, but not a full KAOS-wired implementation.**
4. **FastMCP-native auth is not required for downstream API scopes; it is useful for MCP tool-level authorization. Envoy can do it only if it becomes MCP-aware.**
5. **Gateway/ExtProc is simpler for first integration; sidecars are better for per-workload flexibility, local enforcement, and egress mediation.**
6. **Signed payload A2A is optional/advanced; JWT bearer auth is probably enough for many internal KAOS deployments.**
7. **MCP servers should ideally have their own workload identity, distinct from agent and user identity.**
8. **Consent integration has options: fail-with-URL first, then structured elicitation, then pause/resume.**
9. **Autonomous grants should be tied to run ID, owner, scope, and expiry/end date.**
