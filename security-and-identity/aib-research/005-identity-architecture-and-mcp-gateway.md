# 005 - Identity architecture and MCP/Gateway integration

## Prompt

For the agent registry, does it make sense that KAOS has to push the info? Seems to me it makes more sense for AIB to implement integration to read the CRD info; kaos can just make sure to include metadata on the runtime accordingly, although a metadata store may be required for runtime metadata; review. For the mcp server, how would this work tho, would the mcp server receive a toekn from the agent that is sent from the user? or is the agent holding an identity itself? and then when the token is received would the mcp server need to query for exchnage of the token? In that case is there features in fastmcp to do this natively? or every mcp server would have to be extended to have this? Or would it be a sidecar?. For 3; it suggests that scopes are added to the crd, but doesn't it make more sense that the permissions are not on the agent infra level as that is unsafe? ie instead shoudlnt these be defined centrally? namely the agent has a unique identifier, (which i still dont understand which one it is eg is it supposed to get a secret token on startup or how?) and then this identifier is configured with respective permission sets in AIB which automatically define the scopes? Or this also being based on the user request? But yes for autonomous agents how do you think about an agent being an instanciation vs any number of instantiations, expand hre. 4) ok consent ui doesnt need any more steps or does it for kaos? or is the problem that kaos is built real time? 5) Ok but how do mcps have their own identity to use the token, si this given from startup or do the yuse the agent one? and if the latter it connects to my previous questions. 6) samq euqestion as prev; but also i don't understand this one, expand. 7) ok this connects to my previous question, i'll wait to be answered. 8) ok thi is also linked to my prev quesiton. 9) ok so it means that user driven requests are the most relevant; but we now support autonomous agent execution tho in KAOS, review this feature as this means that we do have calls that are not triggered by users. 10) expand this, as does this mean that we shoudl try to get all traffic through gateway to simplify all auth? 12) ok. 13) ok - lets nt get to impl yet. 14) same. 15) same. then the next sectio has #4 which suggests envoy agentgatewy in front of mcp trffic, does this make everyhitn simpler? eg no sidecars? link to my prev question. Also expand on my points and simplify as it seems too many points granular that repeat / overlap, let's merge a few on discussion. ON aspirational: 1) ok i see, keen to get my answers to the previous to understand better;however why is it not implemented? dont the current features be enough for this to work? ie if JWT token validation works then as the jWT is propagted would this not just be verified by the agents ? 2) ok, yes this is out of scope atm. 3)  ok i see, but is this an AIB feature or a kaos feature? 3) is this implemetned in AIB?. 4) ok but you say this is not in AIB?. 5) expand. 6) i dont get this one. 7) ok but why do we need this if we already have auth flow ui in aib? 8) ok butthis is AIB feature, is this not thre?

## Response

You're right: we should merge the model. The real architecture has **three identities**, not one:

| Identity | Meaning | Example |
|---|---|---|
| **Logical agent identity** | The KAOS `Agent` as a product/security principal | `namespace/researcher`, or AIB UUID mapped to that CRD |
| **Workload instance identity** | A concrete pod/replica proving it is allowed to act as that agent | Kubernetes ServiceAccount / pod-bound token / AIB runtime token |
| **User/request identity** | The human or external principal that initiated a request | `alice@example.com`, or absent for autonomous runs |

Most confusion comes from mixing these.

## 1. Agent registry: push vs pull

I agree with you: **AIB reading KAOS CRDs is cleaner than KAOS pushing everything manually**, if AIB is intended to become the identity/security plane.

Better model:

```text
KAOS Agent CRD / MCPServer CRD
        ↓ watched by
AIB Kubernetes integration/controller
        ↓ creates/updates
AIB agent records, resource records, permission bindings
```

KAOS should expose enough stable metadata: namespace, name, UID, service URL, labels/annotations, service account, agent card URL, MCP endpoint, owner/team, etc.

But there are two kinds of metadata:

| Metadata type | Best owner |
|---|---|
| **Infra/runtime metadata**: CRD UID, pod SA, service URL, namespace, replicas | KAOS/Kubernetes |
| **Security policy metadata**: permission sets, consent requirements, allowed resources, admin approvals | AIB |
| **Human docs/governance metadata**: display name, docs URL, owner | Either CRD annotations or AIB admin UI, but AIB should not blindly trust arbitrary user-provided CRD fields as authorization |

So yes: **AIB should probably have a Kubernetes sync adapter/controller**, not require KAOS operator to imperatively call AIB APIs. KAOS only needs to emit consistent metadata.

## 2. Should permissions/scopes live in the Agent CRD?

I mostly agree with your concern: **permissions should not be authoritative just because an agent author put them in infra YAML.**

The safe model is:

```text
Agent CRD says: "I am agent X; I may request capability group Y"
AIB says: "Agent X is approved for permission set Y with scopes Z"
User says: "I consent to agent X using Y for my account"
```

The CRD can declare **requested permissions** as metadata, but AIB should centrally approve and enforce them.

Bad model:

```yaml
spec:
  permissions:
    - github:repo:write
```

...and then the agent automatically gets that. Unsafe.

Better model:

```yaml
metadata:
  annotations:
    aib.security/agent-id: researcher
    aib.security/requested-profile: github-issue-writer
```

Then AIB maps `github-issue-writer` to actual scopes and approval policy.

## 3. What token does the MCP server receive?

There are several possible flows. The cleanest is to separate **agent token** and **user token**.

### User-triggered flow

```text
User invokes Agent
  -> request carries user identity / subject token
Agent calls MCP
  -> call carries:
      user/request token + agent identity token
MCP or gateway asks AIB:
  "Can agent X, for user Y, access resource Z?"
AIB returns downstream third-party token if allowed
MCP calls third-party API
```

So the agent is **not just holding the user token**, and not just holding its own identity. Ideally it carries both:

| Token | Purpose |
|---|---|
| **Agent/workload token** | Proves "this is KAOS agent X / pod instance Y" |
| **User/subject token** | Proves "this action is on behalf of user Y" |

AIB's RFC 8693 flow is mostly about exchanging a **subject token** for a downstream token after checking agent/user/resource/consent.

### Autonomous flow

No live user exists.

```text
Autonomous Agent
  -> uses agent/workload identity
  -> requests service token from AIB
  -> AIB checks centrally configured service/agent policy
```

This should not use "user consent" unless the autonomous goal is explicitly bound to a user/delegation. For autonomous agents, you need **agent-owned permissions** or **service-account-style grants**, centrally approved in AIB.

So AIB needs two authorization modes for KAOS:

| Mode | Trigger | Auth basis |
|---|---|---|
| **User-delegated** | Interactive/user request | user consent + agent identity |
| **Agent-owned/autonomous** | Self-loop/background task | agent policy/service grant + workload identity |

## 4. Does every MCP server need to be extended?

Not necessarily. There are three integration styles.

### Option A: MCP-native auth in each server

FastMCP supports HTTP auth patterns, including JWT verification via JWKS. So a FastMCP server can be configured to validate AIB-issued JWTs.

Conceptually:

```python
JWTVerifier(
  jwks_uri="https://aib/oauth2/jwks.json",
  issuer="https://aib",
  audience="my-mcp-server"
)
```

This handles **token validation**, but not automatically AIB-specific token exchange for third-party APIs. Tool code would still need to request/exchange tokens unless wrapped by a common helper.

Pros: fine-grained, tool-aware.
Cons: every MCP runtime/server needs integration or a shared KAOS wrapper.

### Option B: Gateway / Envoy ExtProc in front of MCP

```text
Agent -> Gateway/Envoy ExtProc -> MCP Server
              ↓
             AIB
```

The gateway validates/exchanges tokens before traffic reaches the MCP server.

Pros: simpler rollout, no per-MCP code changes, central enforcement.
Cons: less tool-level context unless MCP method/tool name is visible at that layer; harder to enforce "allow `get_issue` but deny `delete_repo`" unless the gateway parses MCP payloads.

This is why I said AIB's ExtProc path is relevant: it could simplify KAOS integration by putting auth at the traffic layer.

### Option C: Sidecar/local proxy per MCP server

```text
Agent -> MCP auth sidecar -> MCP server
              ↓
             AIB
```

Pros: no central gateway dependency; can be close to each MCP.
Cons: more pods/complexity; similar logic repeated across deployments.

My current preference for KAOS: **gateway/ExtProc for coarse-grained auth first**, then **MCP-native/FastMCP auth for fine-grained tool authorization later**.

## 5. Should all traffic go through Gateway?

For security consistency, probably yes for externally or cross-workload significant traffic:

```text
Agent <-> Agent
Agent -> MCP
External user -> Agent
MCP -> external protected API
```

Putting traffic through Gateway/ExtProc makes auth uniform and avoids modifying every runtime immediately.

But not necessarily **all internal pod traffic forever**. A practical split:

| Traffic | Gateway useful? |
|---|---|
| User -> Agent | Yes |
| Agent -> MCP | Yes, very useful |
| Agent -> Agent A2A | Yes, if enforcing A2A policy centrally |
| Agent -> ModelAPI | Maybe; useful for model access policy/audit |
| Internal health checks | Probably no |
| Same-pod sidecar calls | Usually no |

So yes: **Gateway/ExtProc likely makes the first AIB integration much simpler**, especially for MCP traffic.

## 6. Is JWT validation enough for A2A identity?

Partially, but not enough for the full "cryptographic A2A identity" story.

If AIB issues JWTs and agents validate them against JWKS, then agents can verify:

```text
"This request has a valid token issued by AIB"
"This token claims agent_id = X"
"This token is not expired"
"This token has audience = my-agent"
```

That is enough for **bearer-token-based agent identity**.

What is missing from the broader docs claim is stronger cryptographic proof such as:

```text
Agent signs this specific payload/task
Receiver verifies non-repudiable signature
Replay protection / request binding / task hash
Federated verification across brokers
```

JWT bearer auth proves possession of a token, not necessarily that the agent cryptographically signed the actual A2A message body. It is useful, but weaker than signed payload-level identity.

So current AIB can support **JWT-based A2A auth with integration**, but not necessarily the full signed-payload/federated cryptographic identity vision.

## 7. MCP identity: does MCP use its own identity or the agent's?

Both can exist, but they answer different questions.

| Identity | Used for |
|---|---|
| **Agent identity** | Who requested the action? |
| **MCP server identity** | Which tool service is executing the action? |
| **User identity** | On whose behalf? |

For a GitHub MCP call, AIB may need all three:

```text
user = alice
agent = incident-agent
mcp = github-mcp
resource = https://api.github.com
scope = issues:write
```

The MCP should usually have its **own workload identity** to authenticate to AIB as a trusted token-exchange client. It should not simply reuse the agent's identity, because then AIB cannot distinguish "agent asked" from "MCP executed."

Good model:

```text
Agent presents user+agent context to MCP
MCP authenticates itself to AIB as github-mcp
AIB checks: is github-mcp allowed to exchange for this resource, for this agent/user?
```

That gives better audit and blast-radius control.

## 8. Consent UI: is KAOS missing steps?

AIB's consent UI can be reused, but KAOS needs runtime behavior around it.

Missing KAOS-side pieces:

1. User identity must enter KAOS requests.
2. Agent/MCP calls must carry user context.
3. If consent/session is missing, AIB returns a consent/reauth URL.
4. KAOS must surface that URL to the user.
5. After consent, the user retries or the task resumes.

The issue is not "KAOS is real-time" exactly; it's that agent execution may be mid-tool-call. KAOS needs a pattern for:

```text
Tool call blocked -> consent required -> return URL -> resume/retry after consent
```

For autonomous agents, there may be no user to prompt, so missing consent should fail closed or use pre-approved agent-owned grants.

## 9. Autonomous agents change the model

This is important. KAOS autonomous execution means not every call is user-initiated.

So AIB integration must support:

### User-delegated agents

```text
User asks: "File a GitHub issue"
Agent acts for user
Consent required
Token belongs to user's GitHub account
```

### Autonomous/service agents

```text
Agent monitors cluster every 5 minutes
No human request in the loop
Uses agent-owned/service permissions
No per-user consent
```

### Hybrid autonomous agents

```text
User configures a goal once:
"Monitor my repo and open issues when CI fails"
```

This may require durable delegation:

```text
User grants agent X ongoing GitHub access until date Y
Autonomous agent later uses that grant without active user presence
```

This is powerful but risky. AIB would need clear expiry, revocation, audit, and scope limits.

## 10. What is "OAuth2 authorization server mode" in KAOS terms?

AIB can issue its own JWT access tokens. KAOS could use those tokens as internal credentials.

For example:

```text
Agent pod starts
  -> proves workload identity
  -> gets AIB token:
      sub = agent/researcher
      aud = mcp/github
      scope = mcp.call
      exp = short TTL

Agent calls MCP with that token
MCP validates via AIB JWKS
```

That is different from third-party token exchange. It is about **KAOS internal authentication**.

So:

| AIB feature | KAOS use |
|---|---|
| OAuth2 server mode | Issue internal KAOS/AIB tokens |
| JWKS | Let agents/MCP/gateway validate those tokens |
| Token exchange | Convert user/agent subject token into downstream third-party token |
| Token vault | Store downstream user OAuth tokens securely |

## 11. What is currently AIB vs KAOS responsibility?

| Capability | Mostly AIB | Mostly KAOS | Shared |
|---|---:|---:|---:|
| Store OAuth client secrets/tokens | Yes | No | |
| Consent UI/API | Yes | No | KAOS must surface links/results |
| Token exchange | Yes | No | KAOS must propagate correct tokens/context |
| JWT signing/JWKS | Yes | No | KAOS validates/configures audiences |
| Watch KAOS CRDs | Not currently, would be AIB integration | KAOS exposes metadata | Shared |
| Workload identity binding | Needs AIB support | Needs KAOS/K8s SA config | Shared |
| A2A auth enforcement | Not currently integrated | KAOS A2A runtime | Shared |
| MCP fine-grained tool auth | FastMCP can validate tokens | KAOS MCP runtimes/tool wrappers | Shared |
| Gateway/ExtProc routing | AIB has ExtProc component | KAOS Gateway config | Shared |
| Federation | Aspirational/out of scope | No | Future |

## Simplified target architecture

The cleanest mental model is this:

```text
KAOS = orchestrates agents, MCPs, model APIs, runtime execution
AIB = identity, consent, token vault, policy, token exchange
Gateway/ExtProc = enforcement point for traffic
FastMCP/MCP runtime = optional fine-grained resource server enforcement
```

And the identities are:

```text
logical agent: stable CRD/AIB identity
workload instance: pod/service-account-bound runtime proof
user: request principal, optional/absent for autonomous
mcp server: resource/tool service identity
```

## Bottom line

Your instincts are right:

1. **AIB should ideally read/sync KAOS CRDs**, not rely only on KAOS pushing records.
2. **Permission sets should be central in AIB**, not blindly trusted from Agent CRDs.
3. **Agents need their own identity**, but user-triggered calls also need user context.
4. **MCP servers should have their own identity too**, especially if they exchange tokens.
5. **FastMCP can validate JWTs natively**, but AIB token exchange still needs gateway, sidecar, or shared MCP integration.
6. **Gateway/ExtProc probably makes initial integration simpler** because it avoids modifying every MCP server.
7. **Autonomous agents require a separate agent-owned/service-grant model**, not only user consent.
8. **Current AIB JWT/JWKS features are enough for bearer-token agent auth**, but not the full signed-payload/federated cryptographic identity vision.
