# 006 - Research sequencing and architectural decision sections

## Prompt

Ok it seems that we are now mixing the research approach. So yes, let's first start by carrying out the research in the codebase. But then let's go back to a similar approach to 002 on definnign the "research sequencing" where we go through each major architectural decision one by one, amking  a decision and then finalising the work. So for now first start with 1) research on the codebase components to gather the actual context. 2) then define a architectural sections and questions that can be used to define the major components and tradeoffs. then 3) to go through each of these components one by one so we finalise the resarch and move to next phase. 4) then we sign off the target picture, and hten we can move to defining the plan for the initial components and break it down into a set of phases to deliver.

## Response

## Research workflow reset

The research should now proceed in four stages:

1. **Codebase grounding**: establish what KAOS and AIB actually implement today.
2. **Decision sequencing**: define the architecture sections, questions, evidence needed, and decision outputs.
3. **Decision-by-decision research**: complete each section one at a time, make a recommendation, record tradeoffs, and mark it finalized or explicitly deferred.
4. **Target-picture signoff**: combine finalized decisions into a coherent architecture, then move to initial implementation planning and delivery phases.

The first stage is covered by `005-codebase-component-research.md`. This note defines stages 2 and 3.

## Principles for the research phase

1. **One major decision at a time**: avoid mixing enforcement topology, identity model, approval flow, and product boundaries in the same conclusion.
2. **Evidence before recommendation**: each decision note should cite KAOS source, AIB source, and external references where relevant.
3. **Keep security simple by default**: prefer minimum viable secure architecture first, with explicit optional advanced layers.
4. **Separate generic platform security from agent-specific delegation**: do not force AIB to solve problems that Keycloak, Dex, OPA, cert-manager, Gateway, or service mesh solve better.
5. **Separate target picture from first implementation**: target architecture may include future AIB features, but implementation planning comes later.
6. **Mark unresolved items explicitly**: if a decision depends on missing AIB features or KAOS UI/runtime capabilities, document the dependency instead of inventing certainty.

## Proposed architectural decision sections

### 1. Identity model and source of truth

Core question:

- What are the identities in the system, who owns them, and how are they bound to runtime workloads and requests?

Sub-questions:

- Is KAOS logical identity `namespace/name`, `namespace/name + UID`, a URI form, or an AIB UUID?
- How should KAOS resources map to AIB records?
- Should `external_id` in AIB represent KAOS identity?
- Is workload identity required in the initial architecture?
- If yes, should workload identity be based on Kubernetes ServiceAccounts, projected SA tokens, mTLS/SPIFFE, AIB credentials, or something simpler?
- Do Agents, MCPServers, and ModelAPIs need separate conceptual identities, or can they be modeled as KAOS-managed services with different roles?
- What metadata is authoritative in Kubernetes/KAOS vs AIB vs IdP?

Evidence needed:

- KAOS CRD metadata and status fields.
- Operator env injection and service account support.
- AIB Agent model and `external_id` behavior.
- Kubernetes ServiceAccount/projected-token behavior.
- Optional external references for SPIFFE/service mesh if considering advanced mode.

Decision output:

- Canonical identity vocabulary.
- Source-of-truth table.
- Initial vs future workload identity recommendation.
- Required KAOS/AIB metadata fields.

### 2. User/request context propagation

Core question:

- How does a user-authenticated request become a security context that survives agent execution, MCP calls, sub-agent delegation, and autonomous or async execution?

Sub-questions:

- Where should inbound user auth happen: Gateway, KAOS runtime, external IdP proxy, or UI/backend?
- Does KAOS need to store a per-run security context?
- What token or claims should be propagated to MCP calls?
- What token or claims should be propagated to A2A calls?
- Should the runtime propagate original user tokens, exchanged AIB tokens, opaque run IDs, or signed delegation tokens?
- How does propagation differ for user-driven synchronous requests, A2A async tasks, and autonomous startup runs?

Evidence needed:

- Agent `/v1/chat/completions` request handling.
- `AgentDeps` and Pydantic AI tool context.
- MCP client header support in Pydantic AI/FastMCP.
- `RemoteAgent` A2A request construction.
- AIB token exchange subject token/client assertion expectations.

Decision output:

- Request context model.
- Header/token propagation strategy.
- Required runtime changes.
- Explicit autonomous-run treatment.

### 3. Delegated OAuth/token broker boundary

Core question:

- What should AIB own in KAOS: token vault, consent, token exchange, policy, authorization, approval, identity registry, or only a subset?

Sub-questions:

- Is AIB the system of record for delegated grants?
- Should AIB issue KAOS runtime tokens or only exchange existing user/agent tokens for third-party tokens?
- Should AIB be the OAuth2 authorization server for agents, a broker in front of Keycloak/Dex, or a service called by KAOS/Gateway?
- Which AIB current features are directly useful, and which require upstream contributions?
- Should KAOS initially implement a minimal local integration and later move features into AIB?

Evidence needed:

- AIB admin/end-user routes.
- AIB token exchange service.
- AIB session/token vault behavior.
- AIB client credential/signing key behavior.
- Keycloak/Dex feature comparison after requirements are clear.

Decision output:

- AIB responsibility boundary.
- Required AIB extensions.
- What remains in KAOS.
- What should be delegated to external IdP/PDP systems.

### 4. Authorization and policy model

Core question:

- Where are authorization decisions defined and enforced for Agent, MCPServer, ModelAPI, third-party APIs, and tools?

Sub-questions:

- Are permissions defined centrally in AIB, in KAOS CRDs, in Keycloak, in OPA/Rego, or split across them?
- Is AIB's PermissionSet model sufficient for MCP resources/tools or only third-party OAuth scopes?
- Should KAOS CRDs declare requested permissions, required permissions, labels/tags, or no permissions at all?
- Should OPA/Rego be used as the authorization language, or should AIB CEL be enough?
- How do admin-approved policy and user-consented grants combine?
- How are autonomous grants represented and expired?

Evidence needed:

- AIB PermissionSet, ServiceRequirement, UserGrant, and CEL evaluator source.
- KAOS Agent/MCPServer topology fields.
- OPA/Keycloak AuthZ capabilities.
- Gateway/Envoy external auth integration patterns.

Decision output:

- Policy ownership model.
- Policy language recommendation.
- Permission data model for initial target picture.
- Admin vs user vs runtime approval separation.

### 5. Enforcement topology

Core question:

- Where should authentication, token exchange, and authorization be enforced: Gateway, sidecar/local proxy, native runtime/MCP server, service mesh, or a combination?

Sub-questions:

- Should all traffic go through Gateway where possible?
- Should Agent-to-MCP internal calls use direct ClusterIP service URLs, Gateway URLs, or sidecar-local URLs?
- Is a sidecar preferable for MCPServers/ModelAPIs because it avoids app changes and can be MCP-aware?
- Can Gateway/Envoy ExtProc provide enough context for MCP tool-level decisions?
- When is native FastMCP/runtime auth required?
- What is the first secure-but-simple topology?
- What are the failure modes: missing token, expired grant, re-auth required, policy denial, sidecar unavailable, AIB unavailable?

Evidence needed:

- KAOS Gateway route construction.
- Agent/MCP URL injection.
- AIB ExtProc behavior.
- FastMCP auth/header support.
- Envoy ext_authz/ExtProc capabilities.
- Service mesh tradeoffs.

Decision output:

- Enforcement topology recommendation.
- Initial topology and optional advanced topology.
- Required operator/runtime changes.
- What is explicitly not enforced initially.

### 6. Consent and re-authentication execution model

Core question:

- How should KAOS handle cases where an agent action needs user delegated consent, third-party re-authentication, a missing platform grant, or future runtime human approval?

Sub-questions:

- Which flows need pre-existing platform grants?
- Which flows should fail with consent or re-auth URL and retry?
- Is blocking wait acceptable for synchronous chat requests?
- Can current A2A `input-required` state support pause/resume, or does it need new methods and durable storage?
- Can KAOS UI/admin UI present consent/re-auth outcomes and support retry reliably?
- How should multi-agent delegation preserve context after consent/re-auth?
- How should autonomous runs be bounded by run expiry or grant expiry?

Evidence needed:

- KAOS A2A `TaskState.INPUT_REQUIRED` implementation and missing routes.
- KAOS memory/session model.
- KAOS UI/admin UI capabilities, if in scope for later source review.
- AIB consent SPA/API and token exchange re-auth errors.

Decision output:

- Approval model for initial target picture.
- Runtime behavior for each approval case.
- Required task/UI/AIB extensions.
- Explicit deferrals.

### 7. Transport security and hardening baseline

Core question:

- What hard security baseline should KAOS target without over-engineering the first iteration?

Sub-questions:

- Should TLS be required at Gateway only initially?
- Should cert-manager be the default certificate provisioning mechanism?
- Is in-cluster mTLS required initially or optional later?
- Should service mesh be optional advanced mode rather than default?
- How should secrets, signing keys, client credentials, and token vault encryption be managed?
- What minimum audit/telemetry requirements are needed?

Evidence needed:

- KAOS Gateway docs and chart config.
- cert-manager integration patterns.
- AIB signing key/encryption configuration.
- Kubernetes Secret usage in KAOS and AIB.
- Service mesh operational tradeoffs.

Decision output:

- Minimal security baseline.
- Recommended production baseline.
- Advanced optional baseline.
- Non-goals for initial implementation.

### 8. AIB vs Keycloak/Dex/OPA/service mesh responsibility matrix

Core question:

- Which components should solve which parts of the target architecture, and where would using AIB be unnecessary or inferior to existing security tools?

Sub-questions:

- Can Keycloak solve the user consent/delegated authorization problem as well or better than AIB?
- Can OPA solve policy evaluation better than AIB CEL, and should AIB call OPA rather than own policy logic?
- Should Dex only be treated as IdP/OIDC bridge, not authorization platform?
- Should service mesh solve service-to-service identity and mTLS while AIB solves delegated OAuth?
- Which features should be implemented in KAOS first because they are KAOS-specific orchestration concerns?
- Which features should be upstreamed to AIB because they are generic agent identity broker concerns?

Evidence needed:

- Requirements finalized from sections 1-7.
- Keycloak Authorization Services, UMA, token exchange, client policies.
- OPA/Rego and OPA-Envoy patterns.
- Dex OIDC limitations.
- Linkerd/Istio/mTLS identity model.
- AIB actual current capabilities.

Decision output:

- Responsibility matrix.
- Adopt/build/upstream recommendations.
- First implementation boundary.

### 9. AIB Python SDK design

Core question:

- What should a third-party AIB Python SDK provide, where should it integrate with popular Python agentic frameworks, and how should it keep request propagation, AIB grant checks, token exchange, consent, re-authentication, and delegated-token use consistent?

Sub-questions:

- What generic request context model should the SDK expose?
- What canonical propagation headers and redaction behavior should it provide?
- What AIB server operations should be high-level SDK methods rather than raw HTTP calls?
- How should expected outcomes distinguish allowed, platform approval required, user consent required, third-party re-authentication required, denied, and misconfigured cases?
- How should the SDK look in practice with FastAPI, Pydantic AI, FastMCP, and orchestrator wrappers?
- How should the SDK stay independent of orchestrator-specific resource identities and topology models?

Evidence needed:

- Finalized decisions from sections 1-8.
- FastAPI request/middleware/dependency patterns.
- Pydantic AI dependency and tool execution patterns.
- FastMCP context/auth/header extension points.
- AIB token exchange, grant, ExtProc, CEL, and admin/client APIs.
- Existing AIB client/server package boundaries and opportunities for a standalone Python SDK.

Decision output:

- SDK responsibility boundary.
- Initial Python package/module shape.
- FastAPI, Pydantic AI, FastMCP, and wrapper examples.
- Error/result model for denied grants, missing approval, and re-auth required.
- Token-handling and audit rules.
- Explicit non-goals for the SDK.

## Recommended decision sequencing

The order matters because later decisions depend on earlier ones.

### Phase A: foundation decisions

1. **Identity model and source of truth**
   - Finalize identity vocabulary and ownership first.
   - Without this, token claims, grants, and policies remain ambiguous.

2. **Enforcement topology**
   - Decide SDK-first, Gateway, sidecar, and ModelAPI enforcement boundaries.
   - This constrains where context propagation and AIB integration must be embedded.

3. **User/request context propagation**
   - Decide how identity moves through the chosen KAOS flows.
   - This depends on the enforcement topology and informs SDK requirements.

4. **Delegated OAuth/token broker boundary**
   - Decide exactly what AIB owns.
   - This should be based on actual AIB capabilities and the request context model.

### Phase B: security behavior decisions

5. **Authorization and policy model**
   - Define how permissions, grants, and policies are represented.
   - This depends on the identity model and AIB boundary.

6. **Consent and re-authentication execution model**
   - Decide preflight vs fail/retry vs pause/resume.
   - This depends on authorization model and KAOS task/runtime capabilities.

### Phase C: platform/security boundary decisions

7. **Transport security and hardening baseline**
   - Decide minimal/recommended/advanced security layers.
   - This can be informed by enforcement topology but should remain simple.

8. **AIB vs Keycloak/Dex/OPA/service mesh responsibility matrix**
   - Final comparison should happen after requirements are clear.
   - The output should decide what is in AIB, KAOS, external IdP/PDP, Gateway, or mesh.

### Phase D: implementation-shape decision

9. **AIB Python SDK design**
   - Decide the concrete third-party Python SDK boundary after architecture responsibilities are clear.
   - This should translate the target security model into framework-neutral request propagation and AIB server interaction surfaces without becoming the policy source of truth.

## Output format for each decision note

Each future research decision note should use this structure:

1. **Decision area**: the domain being finalized.
2. **Question**: the main architecture question.
3. **Source facts**: source-level facts from KAOS/AIB.
4. **External facts**: relevant best-practice or third-party tool facts.
5. **Options**: realistic alternatives only.
6. **Tradeoffs**: security, complexity, operational cost, extensibility, and fit with KAOS.
7. **Recommendation**: target-picture recommendation.
8. **Initial implementation implication**: not a full plan, only what this decision implies later.
9. **Deferred items**: future features or unanswered questions.
10. **Decision status**: proposed, accepted, rejected, or deferred.

## Immediate next step

Start with **Decision 1: Identity model and source of truth**.

This should finalize:

- KAOS logical identity format.
- How AIB `agent.id` and `agent.external_id` relate to KAOS resources.
- Whether Agents, MCPServers, and ModelAPIs share a generic KAOS service identity abstraction.
- Whether ServiceAccounts/workload identity are mandatory, optional, or deferred.
- What metadata belongs in KAOS CRDs vs AIB records.
